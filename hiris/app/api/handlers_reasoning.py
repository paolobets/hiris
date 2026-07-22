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
    ex = request.app.get("execute_decision")
    if ex is not None:
        try:
            outcome = await ex(decision, (job or {}).get("wake") or {})
        except Exception:
            logger.exception("execute_decision failed")
            outcome = "error"
    return web.json_response({"ok": True, "outcome": outcome})
