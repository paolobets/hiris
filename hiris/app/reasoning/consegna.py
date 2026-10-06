"""La consegna di un turno del ponte: cio' che segue la risposta del piano.

Il lavoratore del ponte (`agent/runner.run_loop`) gira DENTRO il processo
dell'add-on: prende il turno dalla coda (`ReasoningQueue.claim`), lo ragiona e
lo consegna qui, senza passare per HTTP. Fino al 06/10/2026 (A-23) faceva le
due cose chiamando se stesso su `/api/reasoning/claim` e
`/api/reasoning/submit` ogni tre secondi, e questa logica viveva nel gestore
della seconda rotta: per togliere il giro HTTP andava prima tirata fuori da
li'. Le due rotte sono uscite insieme al giro, e con loro il loro cancello
(`_ponte_soltanto`, A-4 dell'audit del 21/09/2026): una rotta che non esiste
non si deve difendere.

Cosa fa una consegna, per specie di turno:
- **promessa**: chiude la promessa che il turno ha lasciato `in_corso` senza
  chiamare «conclude»;
- **chat**: scrive la risposta nel filo di chi l'ha chiesta;
- **«Rendila automatica»**: chiude la proposta da fare a mano col legame
  alla costruzione nata nel turno, o scrive perche' non si e' potuta fare
  (`mind/automate_turn.deliver`). Non ha un giro periodico che raccolga: e'
  un gesto di chi amministra, e la pagina aspetta questa consegna;
- **gli altri attori**: niente -- la decisione resta registrata, e la va a
  prendere il giro che ha accodato il turno.
"""
from __future__ import annotations

import logging

from ..mind.observer import SCOPE_TURN_KIND

logger = logging.getLogger(__name__)


async def consegna(app, job_id: str, nonce: str, decision: dict,
                  now: float) -> str | None:
    """Consegna la decisione di un turno preso dalla coda.

    `None` quando la coda la rifiuta (nonce sbagliato, turno non piu' preso in
    carico o gia' scaduto: `ReasoningQueue.submit`) -- e allora non succede
    nient'altro. Altrimenti l'esito della consegna, una parola sola.
    """
    q = app.get("reasoning_queue")
    decision = decision or {}
    if q is None or not q.submit(job_id, nonce, decision, now):
        return None
    job = q.get(job_id)
    outcome = "recorded"

    if (job or {}).get("kind") == "promessa":
        # Fetta «le promesse seguono la catena» (22/08/2026). La consegna di un
        # turno di promessa NON porta la risposta all'utente: la conclusione,
        # se c'e' stata, e' gia' arrivata per un'altra strada -- `conclude`
        # attraverso `POST /api/mcp`, che chiude la promessa e fa partire la
        # notifica nel momento in cui il modello decide, senza aspettare qui.
        #
        # Questo ramo serve al caso opposto: il turno e' finito e `conclude`
        # non e' mai stato chiamato. La promessa non puo' restare `in_corso` --
        # sarebbe invisibile, e peggio di una fallita.
        #
        # L'id viene da `wake`, non dal contesto: `q.submit()` qui sopra ha
        # gia' azzerato `context_json` (porta il nucleo per intero e non deve
        # restare su disco). `wake` no, ed e' per questo che
        # `keeper/exchange._enqueue_to_bridge` ce lo mette.
        from ..keeper.exchange import _senza_conclusione
        from ..keeper.outcome import tell_failure

        ident = ((job or {}).get("wake") or {}).get("promessa_id") or ""
        store = app.get("agenda")
        row = store.read(ident) if (store is not None and ident) else None
        if row is None:
            logger.warning(
                "consegna di un turno di promessa senza promessa (job_id=%s, "
                "id=%r): non c'e' niente da chiudere", job_id, ident)
            outcome = "promessa_sconosciuta"
        elif row.get("stato") != "in_corso":
            # `conclude` e' gia' arrivato: la promessa e' chiusa e non si
            # riapre. Riaprirla cancellerebbe un testo che l'utente puo' gia'
            # aver letto -- o peggio, farebbe partire una seconda notifica.
            outcome = "promessa_gia_conclusa"
        else:
            reply = decision.get("reply")
            reason = _senza_conclusione(reply)
            # Ruling 3.8: una riga breve nel filo di chi l'ha chiesta, nessuna
            # push -- la stessa forma della scadenza (`keeper/outcome.py`). La
            # risposta del modello citata nel motivo passa dal filtro dei
            # veleni da sola (`quoted`).
            if store.concludi(ident, state="fallita", now=now, reason=reason):
                tell_failure(app.get("data_dir"), row, reason,
                             quoted=reply if isinstance(reply, str) and reply.strip()
                             else None)
            # Rilievo R1 della revisione indipendente sul tratto
            # `v3.22.2..HEAD`: il registro degli esiti vedeva il successo
            # della chat e la scadenza, e niente delle promesse. Una promessa
            # mantenuta dal ponte si conclude altrove (`api/handlers_mcp`,
            # dove sta il `.successo(...)` gemello di questa riga) -- questo
            # e' il ramo in cui il turno E' finito e NON ha chiamato
            # «conclude»: il piano ha risposto, e ha risposto senza seguire
            # il protocollo. Non e' una scadenza (`family="scaduto"` e' per
            # chi non risponde affatto, vedi `handlers_chat.py`) ne' un
            # rifiuto con causa nota: e' `family="altro"`, come ogni guasto
            # che si misura senza inventarne il perche'.
            registry = app.get("occurrence_registry")
            if registry is not None:
                registry.fallimento(
                    "subscription", family="altro", code=None,
                    message="promessa sul ponte finita senza chiamare «conclude»",
                    durata_s=now - float(job.get("created_ts", now)))
            outcome = "promessa_senza_conclusione"
        return outcome

    if (job or {}).get("kind") == "chat":
        # Chat-via-abbonamento (Slice 4b): a chat job's submit writes the
        # reply into chat_store — it must NEVER actuate the house through
        # execute_decision. Fail-closed: missing reply -> no write, but the
        # job stays "decided" (already committed by q.submit above).
        #
        # Fetta «le chat divise»: la risposta va nel FILO del job -- chi ha
        # scritto il messaggio, da dove -- letto dalle colonne della coda
        # (`job["thread"]`), non dal `context`, che `q.submit()` qui sopra ha
        # gia' azzerato. Un job di chat accodato PRIMA di questa versione non
        # ha filo: la risposta non si scrive in un filo inventato (sarebbe la
        # chat di qualcun altro), si dichiara nel log e si lascia cadere.
        # Un `chatbot_id`/`agent_id` rimasto nel context di un job vecchio
        # resta ignorato, come dalla fetta E4.
        reply = decision.get("reply")
        thread = (job or {}).get("thread")
        submit_chat_reply = app.get("submit_chat_reply")
        if thread is None:
            logger.warning(
                "consegna di un turno di chat senza filo (job_id=%s): accodato "
                "prima delle chat divise, la risposta non si scrive in nessuna "
                "cronologia", job_id)
            outcome = "chat_reply_senza_filo"
        elif submit_chat_reply is not None and reply:
            try:
                await submit_chat_reply(reply, thread)
                outcome = "chat_reply_recorded"
            except Exception:
                logger.exception("submit_chat_reply failed")
                outcome = "error"
        else:
            outcome = "chat_reply_skipped"
        return outcome

    from ..mind import automate_turn

    if (job or {}).get("kind") == automate_turn.AUTOMATE_TURN_KIND:
        return "automazione_" + automate_turn.deliver(app, job, decision)

    # Qui arrivano i turni che non sono ne' di chat ne' di promessa: quelli
    # degli attori. Non c'e' niente da attuare -- la decisione resta
    # "recorded" -- e la risposta se la va a prendere dalla coda il giro
    # periodico che ha accodato il turno (`_collect_scope_turn`,
    # `_collect_recipe_turn`, `_collect_analyst_turn`, `_collect_actuator_turn`
    # in `server.py`).
    #
    # Il log qui sotto tace solo per lo scope (dall'11/09/2026). Per le altre
    # specie degli attori scatta a ogni consegna, con una frase su un
    # meccanismo -- la revisione olistica -- uscito da mesi.
    if (job or {}).get("kind") != SCOPE_TURN_KIND:
        logger.warning(
            "reasoning submit: nessun execute_decision wired -- l'attuazione "
            "remota della revisione olistica non esiste piu' (job_id=%s, kind=%s), "
            "decisione solo registrata", job_id, (job or {}).get("kind"))
    return outcome
