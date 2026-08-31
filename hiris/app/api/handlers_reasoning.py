from __future__ import annotations

import logging
import time

from aiohttp import web

logger = logging.getLogger(__name__)


def _now(request):
    return (request.app.get("_clock") or time.time)()


async def handle_reasoning_claim(request: web.Request) -> web.Response:
    q = request.app.get("reasoning_queue")
    if q is None:
        return web.json_response({"job": None})
    return web.json_response({"job": q.claim(_now(request))})


async def handle_reasoning_submit(request: web.Request) -> web.Response:
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
        # se c'e' stata, e' gia' arrivata per un'altra strada -- `concludi`
        # attraverso `POST /api/mcp`, che chiude la promessa e fa partire la
        # notifica nel momento in cui il modello decide, senza aspettare qui.
        #
        # Questo ramo serve al caso opposto: il turno e' finito e `concludi`
        # non e' mai stato chiamato. La promessa non puo' restare `in_corso` --
        # sarebbe invisibile, e peggio di una fallita.
        #
        # L'id viene da `wake`, non dal contesto: `q.submit()` qui sopra ha
        # gia' azzerato `context_json` (porta il nucleo per intero e non deve
        # restare su disco). `wake` no, ed e' per questo che
        # `schedulatore/turno._accoda_al_ponte` ce lo mette.
        from ..schedulatore.turno import _senza_conclusione

        ident = ((job or {}).get("wake") or {}).get("promessa_id") or ""
        store = request.app.get("promesse")
        row = store.read(ident) if (store is not None and ident) else None
        if row is None:
            logger.warning(
                "consegna di un turno di promessa senza promessa (job_id=%s, "
                "id=%r): non c'e' niente da chiudere", job_id, ident)
            outcome = "promessa_sconosciuta"
        elif row.get("stato") != "in_corso":
            # `concludi` e' gia' arrivato: la promessa e' chiusa e non si
            # riapre. Riaprirla cancellerebbe un testo che l'utente puo' gia'
            # aver letto -- o peggio, farebbe partire una seconda notifica.
            outcome = "promessa_gia_conclusa"
        else:
            store.concludi(
                ident, state="fallita", now=_now(request),
                reason=_senza_conclusione(decision.get("reply")))
            outcome = "promessa_senza_conclusione"
        return web.json_response({"ok": True, "outcome": outcome})

    if (job or {}).get("kind") == "chat":
        # Chat-via-abbonamento (Slice 4b): a chat job's submit writes the
        # reply into chat_store — it must NEVER actuate the house through
        # execute_decision. Fail-closed: missing reply -> no write, but the
        # job stays "decided" (already committed by q.submit above).
        #
        # fetta E4 Task 5 ("un bot solo"): submit_chat_reply non prende piu'
        # un chatbot_id -- chat_store non ne ha piu' bisogno, c'e' UNA
        # cronologia. Non estraiamo piu' nulla dal context_json: un job
        # rimasto in reasoning.db da prima di questo task puo' ancora
        # portare chatbot_id/agent_id dentro il suo context (scritto da un
        # server piu' vecchio) -- quella chiave e' semplicemente ignorata,
        # non impedisce piu' la consegna (prima, un context legacy con solo
        # `agent_id` avrebbe fatto risolvere `chatbot_id` a `None` e saltare
        # la scrittura: quel guasto non esiste piu' per costruzione).
        reply = decision.get("reply")
        submit_chat_reply = request.app.get("submit_chat_reply")
        if submit_chat_reply is not None and reply:
            try:
                await submit_chat_reply(reply)
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
    logger.warning(
        "reasoning submit: nessun execute_decision wired -- l'attuazione "
        "remota della revisione olistica non esiste piu' (job_id=%s, kind=%s), "
        "decisione solo registrata", job_id, (job or {}).get("kind"))
    return web.json_response({"ok": True, "outcome": outcome})
