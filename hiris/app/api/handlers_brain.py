from __future__ import annotations

from aiohttp import web

# fetta E3 Task 5: handle_brain_feed (componeva reasoning_log + advisory_store
# + proposal_store + knowledge_store via brain.feed) e handle_brain_reasoning
# (leggeva il solo reasoning_log) sono usciti col Brain auto-proponente --
# erano l'unica superficie che leggeva reasoning_log/ReasoningLog, uscito con
# loro. brain.feed e' uscito nella stessa mossa (nessun altro lettore). Le
# advisories, sotto, restano fino al Task 6.

_ADV_STATUSES = frozenset({"open", "acknowledged", "resolved", "dismissed"})


async def handle_list_advisories(request: web.Request) -> web.Response:
    adv = request.app.get("advisory_store")
    if adv is None:
        return web.json_response({"advisories": []})
    status = request.rel_url.query.get("status") or None
    if status is not None and status not in _ADV_STATUSES:
        return web.json_response({"error": f"Invalid status: {status!r}"}, status=400)
    return web.json_response({"advisories": adv.list(status=status)})


async def _set_status(request: web.Request, status: str) -> web.Response:
    adv = request.app.get("advisory_store")
    if adv is None:
        return web.json_response({"error": "AdvisoryStore not initialized"}, status=503)
    try:
        aid = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"ok": False}, status=400)
    ok = adv.set_status(aid, status)
    if not ok:
        return web.json_response({"ok": False, "error": "not found"}, status=409)
    return web.json_response({"ok": True})


async def handle_ack_advisory(request: web.Request) -> web.Response:
    return await _set_status(request, "acknowledged")


async def handle_dismiss_advisory(request: web.Request) -> web.Response:
    return await _set_status(request, "dismissed")
