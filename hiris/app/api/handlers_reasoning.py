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

    if (job or {}).get("kind") == "chat":
        # Chat-via-abbonamento (Slice 4b): a chat job's submit writes the
        # reply into chat_store — it must NEVER actuate the house through
        # execute_decision. Fail-closed: missing chatbot_id/reply -> no write,
        # but the job stays "decided" (already committed by q.submit above).
        # Retro-compat (one-deploy window): jobs enqueued before the
        # agent_id->chatbot_id rename still carry the legacy key. Fall back
        # to it so an in-flight pre-deploy job's reply isn't dropped.
        _ctx = (job or {}).get("context") or {}
        chatbot_id = _ctx.get("chatbot_id") or _ctx.get("agent_id")
        reply = decision.get("reply")
        submit_chat_reply = request.app.get("submit_chat_reply")
        if submit_chat_reply is not None and chatbot_id and reply:
            try:
                await submit_chat_reply(chatbot_id, reply)
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
