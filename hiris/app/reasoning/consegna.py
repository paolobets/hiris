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
- **gli attori**: niente -- la decisione resta registrata, e la va a prendere
  il giro che ha accodato il turno;
- **«Rifalla»**: scrive l'esito nel filo della proposta
  (`mind/proposal_redo.deliver`), perche' non c'e' un giro che passi;
- **«Rendila automatica»**: chiude la proposta da fare a mano col legame
  alla costruzione nata nel turno, o scrive perche' non si e' potuta fare
  (`mind/automate_turn.deliver`). Non ha un giro periodico che raccolga: e'
  un gesto di chi amministra, e la pagina aspetta questa consegna.

E la strada opposta, il turno di promessa che **non** arriva:
`close_expired_promise`, chiamata dalla spazzata della coda
(`conservazione.reasoning_sweep`). Spostata qui da `server.py` l'08/10/2026
(Tappa 8, Task 6), accanto al suo gemello: dal Task 4 (D-24) i due
chiudono la promessa con lo stesso giro, `keeper/outcome.fail_unfinished`.
"""
from __future__ import annotations

import logging
import time

from aiohttp import web

from ..mind.proposal_redo import WAKE_KEY as REDO_KEY
from ..mind.proposer_turn import PROPOSAL_TURN_KIND
from ..provider_occurrences import OCCURRENCES_KEY
from ..providers import SUBSCRIPTION
from .queue import REASONING_QUEUE_KEY

#: Le chiavi di `app` che questo modulo possiede: `web.AppKey`, mai una
#: stringa (X-32, Chiusura dello sprint).
SUBMIT_CHAT_REPLY_KEY = web.AppKey("submit_chat_reply")

logger = logging.getLogger(__name__)


async def consegna(app, job_id: str, nonce: str, decision: dict,
                  now: float) -> bool:
    """Consegna la decisione di un turno preso dalla coda.

    `False` quando la coda la rifiuta (nonce sbagliato, turno non piu' preso
    in carico o gia' scaduto: `ReasoningQueue.submit`) -- e allora non
    succede nient'altro. `True` quando la decisione e' registrata, qualunque
    cosa sia successa dopo.

    **Torna un si' o un no, non una parola d'esito** (M-72, Chiusura). Fino
    qui ogni ramo produceva la sua parola (`recorded`, `chat_reply_*`,
    `promessa_*`, `automazione_*`, `rifalla_*`, `error`), e l'unico lettore,
    `agent/runner.serve`, guardava solo se fosse `None`: otto valori che
    leggevano soltanto le prove, e una `error` che usciva come consegna
    riuscita. Cio' che va saputo di un ramo lo dice il ramo stesso, nel
    registro dell'add-on, e il resto lo dice l'archivio che il ramo scrive.
    """
    q = app.get(REASONING_QUEUE_KEY)
    decision = decision or {}
    if q is None or not q.submit(job_id, nonce, decision, now):
        return False
    job = q.get(job_id)

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
        from ..keeper.outcome import UNKNOWN, fail_unfinished
        from ..keeper.promise import unfinished_reason

        ident = ((job or {}).get("wake") or {}).get("promessa_id") or ""
        reply = decision.get("reply")
        # Il giro di chiusura e' quello della scadenza (`keeper/outcome.
        # fail_unfinished`, D-24). Qui la famiglia e' `altro`: il turno E'
        # finito e NON ha chiamato «conclude» -- il piano ha risposto, senza
        # seguire il protocollo. Non e' una scadenza (`scaduto` e' per chi non
        # risponde affatto, vedi `handlers_chat.py`) ne' un rifiuto con causa
        # nota: e' `altro`, come ogni guasto che si misura senza inventarne il
        # perche'. Una promessa mantenuta dal ponte si conclude altrove
        # (`api/handlers_mcp`, dove sta il `.successo(...)` gemello).
        closed = fail_unfinished(
            app, ident, reason=unfinished_reason(reply), now=now, family="altro",
            message="promessa sul ponte finita senza chiamare «conclude»",
            durata_s=now - float((job or {}).get("created_ts", now)),
            quoted=reply if isinstance(reply, str) and reply.strip() else None)
        if closed == UNKNOWN:
            logger.warning(
                "consegna di un turno di promessa senza promessa (job_id=%s, "
                "id=%r): non c'e' niente da chiudere", job_id, ident)
        return True

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
        submit_chat_reply = app.get(SUBMIT_CHAT_REPLY_KEY)
        if thread is None:
            logger.warning(
                "consegna di un turno di chat senza filo (job_id=%s): accodato "
                "prima delle chat divise, la risposta non si scrive in nessuna "
                "cronologia", job_id)
        elif submit_chat_reply is not None and reply:
            try:
                await submit_chat_reply(reply, thread)
            except Exception:
                logger.exception("submit_chat_reply failed")
        return True

    from ..mind import automate_turn

    if (job or {}).get("kind") == automate_turn.AUTOMATE_TURN_KIND:
        automate_turn.deliver(app, job, decision)
        return True

    if (job or {}).get("kind") == PROPOSAL_TURN_KIND \
            and ((job or {}).get("wake") or {}).get(REDO_KEY):
        # Un «Rifalla» (attori, Task 4.4): c'e' una persona che aspetta davanti
        # alla pagina, e nessun giro periodico che passi a raccogliere. La
        # risposta si scrive nel filo della proposta adesso; la pagina la
        # trova alla sua prossima lettura.
        from ..mind.proposal_redo import deliver

        try:
            deliver(app, job, decision)
        except Exception:
            logger.exception("consegna di un «Rifalla» non riuscita (job_id=%s)",
                             job_id)
        return True

    # Qui arrivano i turni che non sono ne' di chat ne' di promessa: quelli
    # degli attori. Non c'e' niente da attuare -- la decisione resta
    # registrata -- e la risposta se la va a prendere dalla coda il giro
    # periodico che ha accodato il turno (i raccoglitori in `server.py` e
    # `mind/proposer_round._collect`). E' la consegna normale di un attore, e
    # non si annota: fino alla Chiusura (S-23) qui scattava un WARNING a ogni
    # consegna che non fosse dell'osservatore, su un meccanismo -- la
    # revisione olistica -- uscito da mesi.
    return True


def close_expired_promise(app, job: dict) -> None:
    """Il turno del piano e' scaduto: la promessa fallisce dichiarando l'attesa.

    E' l'unico punto che impedisce a una promessa servita dal ponte di
    restare `in_corso` per sempre quando il piano non risponde. `risana()` la
    chiuderebbe soltanto al prossimo riavvio -- cioe' forse mai.

    L'id viene da `wake`: `sweep_expired` azzera `context_json` come fa
    `submit`, e `wake` e' la sola parte del job che sopravvive.
    """
    from ..keeper.outcome import CLOSED, fail_unfinished
    from ..keeper.promise import bridge_silence_reason

    ident = (job.get("wake") or {}).get("promessa_id") or ""
    # **L'attesa e' quella del turno** (S-02, Tappa 6 Task 2): la scadenza
    # viaggia col job, e la `scadenza_min` di ADESSO puo' essere un'altra --
    # l'utente puo' averla cambiata mentre il turno era in coda. Stessa durata
    # che il registro degli esiti riceve: una sola, letta una volta.
    durata_s = (float(job.get("deadline_ts", 0.0))
                - float(job.get("created_ts", 0.0)))
    minuti = round(durata_s / 60)
    closed = fail_unfinished(
        app, ident, reason=bridge_silence_reason(SUBSCRIPTION.name, minuti),
        now=time.time(), family="scaduto",
        message="nessuna conclusione entro la scadenza del ponte (promessa)",
        durata_s=durata_s)
    if closed == CLOSED:
        logger.warning(
            "promessa %s: il turno sul piano e' scaduto dopo %d minuti",
            ident, minuti)


def _chat_reply_submitter(app, data_dir: str):
    """La consegna del ponte per i turni `kind="chat"`, pubblicata
    dall'avvio in `app["submit_chat_reply"]`.

    Viveva annidata in `_on_startup`; e' una funzione di modulo dal
    03/10/2026 (Tappa 1 dello sprint «Una fonte sola di verita'», D1) perche'
    le prove la possano costruire su un'app e una cartella loro invece di
    ritagliarla dal testo. Stesso codice, chiamata dallo stesso punto.
    """
    # Chat-via-abbonamento (Slice 4b, Task 1): submit-branch for kind="chat"
    # jobs — writes the runner's reply into chat_store instead of actuating
    # the house. Fetta «le chat divise»: la risposta va nel filo del job
    # (`thread`, letto dalla coda da `reasoning/consegna`) -- la
    # cronologia di chi ha scritto, non una sola per tutti.
    from ..chat_store import _is_toxic_assistant as _is_toxic_chat_reply
    from ..chat_store import append_messages as _append_chat_messages
    from ..chat_thread import ChatThread

    async def _submit_chat_reply(reply_text: str, thread: ChatThread) -> None:
        if not reply_text:
            return
        # Final-review Fix 3 (Slice 4b): mirror the sync path's persistence
        # guard (handlers_chat.py) so a reply that arrived via the async
        # runner gets the same treatment as one from the local runner.
        if _is_toxic_chat_reply(reply_text):
            # Drop silently from the history, same as the sync path: the next
            # turn must not inherit a poisoned/leaked history. There's no
            # HTTP response here to carry a visible error (the caller already
            # got a 202 long ago) -- the poll route's chat_reply_skipped
            # handling is the user-facing side of this.
            #
            # Rilievo R1 della revisione indipendente sul tratto
            # `v3.22.2..HEAD`: la guardia sopra non deve tacere due volte.
            # Fino a questa correzione un turno del ponte tornato con uno dei
            # cinque sentinella d'errore (`chat_store.BRIDGE_SENTINELS`)
            # spariva qui senza lasciare NIENTE nel registro degli esiti --
            # non e' la stessa cosa di "non l'ho interrogato" (`occurrence()
            # is None`): il ponte ha risposto, e ha risposto con un
            # fallimento. Confondere le due e' la stessa contraddizione da
            # cui e' nato il Task 6 (Modelli che diceva «non l'hai ancora
            # usato» con turni riusciti in `consumo_giorno`), spostata dal
            # successo al fallimento. Il testo del sentinella non e' una
            # causa nota (nessun codice HTTP, nessuna credenziale, nessun
            # modello) -- e' `family="altro"`, come ogni guasto che il
            # prodotto misura senza inventarne il perche'.
            registry = app.get(OCCURRENCES_KEY)
            if registry is not None:
                registry.fallimento(
                    SUBSCRIPTION.id, family="altro", code=None,
                    message=reply_text, durata_s=0.0)
            return
        # Task 6 (collaudo-3.22, indagine-abbonamento.md): QUI, e non prima
        # -- e non in `agent/runner.py::_logga_uso`, dove parte gia' Consumi.
        # Il ponte non passa mai da `LLMRouter.chat()` (l'unico chiamante di
        # `.successo(...)` fino a questa fetta): la pagina Modelli non aveva
        # nessun modo di sapere che il ponte avesse MAI risposto, e diceva
        # «non l'hai ancora usato» a un proprietario con 105 turni riusciti
        # da fine agosto (`GET /api/usage`, `last_use` di oggi).
        #
        # `_logga_uso` (che alimenta Consumi) e' PIU' A MONTE di questo punto:
        # gira dentro `_invoca`, prima che il chiamante guardi `invocation.rc`
        # o `occurrence.has_result` -- un turno con `rc != 0` o senza evento
        # finale puo' comunque avere un `usage` non vuoto (il conteggio dei
        # token puo' arrivare anche su un esito d'errore) e farebbe scrivere
        # un successo su un turno che non lo e' stato. Qui invece il successo
        # e' un fatto GIA' accertato: siamo dopo il filtro di tossicita' che
        # scarta i cinque sentinella d'errore del ponte
        # (`chat_store.BRIDGE_SENTINELS`) e dopo il controllo «reply non
        # vuota» -- se il codice arriva a questa riga, e' perche' sta per
        # scrivere in cronologia una risposta vera, la stessa che l'utente
        # sta per leggere. E' anche il motivo per cui NON sta in
        # `reasoning/consegna` (proposta dell'audit L3 dell'agosto
        # scorso, H2): li' la guardia e' solo «reply non vuota», che i
        # sentinella la superano -- registrare il successo li' avrebbe
        # sostituito la bugia di oggi con la bugia opposta.
        registry = app.get(OCCURRENCES_KEY)
        if registry is not None:
            registry.successo(SUBSCRIPTION.id)
        _append_chat_messages([{"role": "assistant", "content": reply_text}], data_dir,
                              thread=thread)
    return _submit_chat_reply
