from __future__ import annotations

import logging
import time

from aiohttp import web

from ..chat_thread import thread_to_context
from ..mind.observer import SCOPE_TURN_KIND

logger = logging.getLogger(__name__)


#: Chi puo' parlare con queste due rotte. **Una sola classe**: il worker del
#: ponte, che porta una credenziale di turno.
#:
#: Reperto A-4 dell'audit del 21/09/2026, chiuso il 22. `claim` restituisce il
#: job col `context` deserializzato per intero -- il nucleo della casa e i
#: ricordi -- piu' un nonce fresco; con quel nonce `submit`, sul ramo `chat`,
#: scrive un testo arbitrario nella conversazione **come risposta di HIRIS**.
#: L'utente legge un'istruzione ostile credendola l'assistente, ed e' lui a
#: eseguirla.
#:
#: La rotta gemella dello stesso worker (`/api/mcp`) restringeva
#: l'autenticazione da sempre; queste due erano nate senza, e non si potevano
#: chiudere finche' il gateway MCP le chiamava col segreto condiviso. Il 22/09
#: il proprietario ha dichiarato quel progetto morto: resta il worker, e basta.
_AMMESSO = "turno"

_SOLO_PONTE = ("queste rotte servono il worker del ponte e nient’altro: "
            "richiedono una credenziale di turno")


def _ponte_soltanto(request) -> web.Response | None:
    """`None` se puo' passare, la risposta di rifiuto altrimenti.

    Si guarda `auth_via` -- il verdetto del confine -- e non si ricopia nessun
    confronto di segreti: un secondo posto in cui si decide chi e' autenticato
    e' un secondo posto che puo' divergere. Stessa forma di `handlers_mcp`.
    """
    if request.get("auth_via") != _AMMESSO:
        logger.warning(
            "reasoning: %s rifiutata a %s (autenticazione vista: %s)",
            request.path if hasattr(request, "path") else "?",
            getattr(request, "remote", "?"), request.get("auth_via"))
        return web.json_response({"errore": _SOLO_PONTE}, status=401)
    return None


def _now(request):
    return (request.app.get("_clock") or time.time)()


async def handle_reasoning_claim(request: web.Request) -> web.Response:
    negato = _ponte_soltanto(request)
    if negato is not None:
        return negato
    q = request.app.get("reasoning_queue")
    if q is None:
        return web.json_response({"job": None})
    job = q.claim(_now(request))
    # Il filo del job e' un `ChatThread` dentro il processo, che `json_response`
    # non sa serializzare: senza questa riga solleva per ogni job di chat che
    # ne porta uno, cioe' il ponte non riceve piu' nessun turno di chat
    # (trovato dal Task 3 delle chat divise). Il runner il filo del claim non
    # lo legge -- consegna per `job_id`, e il filo lo ritrova il server dalla
    # coda: la serializzazione c'e' solo perche' la risposta resti JSON.
    if job is not None and job.get("thread") is not None:
        job = {**job, "thread": thread_to_context(job["thread"])}
    return web.json_response({"job": job})


async def handle_reasoning_submit(request: web.Request) -> web.Response:
    negato = _ponte_soltanto(request)
    if negato is not None:
        return negato
    q = request.app.get("reasoning_queue")
    if q is None:
        return web.json_response({"ok": False, "error": "queue unavailable"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)
    job_id = body.get("job_id"); nonce = body.get("nonce"); decision = body.get("decision") or {}
    if not q.submit(job_id, nonce, decision, _now(request)):
        return web.json_response({"ok": False, "error": "invalid or expired"}, status=409)
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
        store = request.app.get("agenda")
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
            now = _now(request)
            reply = decision.get("reply")
            reason = _senza_conclusione(reply)
            # Ruling 3.8: una riga breve nel filo di chi l'ha chiesta, nessuna
            # push -- la stessa forma della scadenza (`keeper/outcome.py`). La
            # risposta del modello citata nel motivo passa dal filtro dei
            # veleni da sola (`quoted`).
            if store.concludi(ident, state="fallita", now=now, reason=reason):
                tell_failure(request.app.get("data_dir"), row, reason,
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
            registry = request.app.get("occurrence_registry")
            if registry is not None:
                registry.fallimento(
                    "subscription", family="altro", code=None,
                    message="promessa sul ponte finita senza chiamare «conclude»",
                    durata_s=now - float(job.get("created_ts", now)))
            outcome = "promessa_senza_conclusione"
        return web.json_response({"ok": True, "outcome": outcome})

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
        submit_chat_reply = request.app.get("submit_chat_reply")
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
        return web.json_response({"ok": True, "outcome": outcome})

    # fetta E3 Task 9 (rilievo 1 della review indipendente sul blocco 5-8):
    # l'hook `app["execute_decision"]` -- l'ultimo punto del prodotto in cui
    # un callable cablato in `app` avrebbe potuto attuare una Decisione --
    # e' uscito per intero. Era sopravvissuto al Task 7 senza una parola,
    # benche' la review del blocco 1 lo assegnasse "al piu' tardi col Task
    # 7" e il Task 5 lo differisse qui per iscritto. Verificato con grep
    # (`execute_decision` su tutto `hiris/app`): server.py non lo scrive in
    # `app[...]` da `101189a` (Task 4) -- oggi lo cablava solo la suite di
    # test (`test_reasoning_wiring.py`, `test_reasoning_api.py`), mai
    # produzione. Un submit non-chat puo' arrivare qui solo da un job
    # scaduto/legacy: non tace (il silenzio non e' distinguibile da
    # un'assenza di problemi), ma non attua piu' nulla -- resta "recorded",
    # com'era gia' il default anche quando l'hook esisteva-ma-non-cablato.
    # **Un turno dell'osservatore consegnato non e' un job legacy.** La sua
    # risposta se la va a prendere il giro periodico (`server.
    # _collect_scope_turn`, che legge la coda): qui non c'e' niente da
    # attuare, e non c'e' niente da dichiarare. Senza questo ramo ogni
    # consegna dell'osservatore -- cioe' il caso normale, piu' volte al giorno
    # -- scriveva nel log che «l'attuazione remota della revisione olistica
    # non esiste piu'», una frase su un meccanismo uscito mesi fa che con
    # questo turno non c'entra niente (rilievo della review indipendente,
    # 11/09/2026).
    if (job or {}).get("kind") != SCOPE_TURN_KIND:
        logger.warning(
            "reasoning submit: nessun execute_decision wired -- l'attuazione "
            "remota della revisione olistica non esiste piu' (job_id=%s, kind=%s), "
            "decisione solo registrata", job_id, (job or {}).get("kind"))
    return web.json_response({"ok": True, "outcome": outcome})
