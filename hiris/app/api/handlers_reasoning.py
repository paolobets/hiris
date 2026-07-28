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

    ex = request.app.get("execute_decision")
    if ex is not None:
        try:
            outcome = await ex(decision, (job or {}).get("wake") or {})
        except Exception:
            logger.exception("execute_decision failed")
            outcome = "error"
    return web.json_response({"ok": True, "outcome": outcome})
