from __future__ import annotations

from aiohttp import web

from ..brain import feed as _feed

_ADV_STATUSES = frozenset({"open", "acknowledged", "resolved", "dismissed"})


async def handle_brain_feed(request: web.Request) -> web.Response:
    q = request.rel_url.query
    try:
        limit = min(int(q.get("limit", "50")), 200)
    except ValueError:
        limit = 50
    type_filter = q.get("type") or None

    rlog = request.app.get("reasoning_log")
    adv = request.app.get("advisory_store")
    prop = request.app.get("proposal_store")
    ks = request.app.get("knowledge_store")

    r_items = _feed.reasoning_items(rlog.list(limit=100)) if rlog is not None else []
    a_items = _feed.advisory_items(adv.list()) if adv is not None else []
    p_items = _feed.proposal_items(await prop.list(status="pending")) if prop is not None else []
    b_items = _feed.brain_action_items(
        ks.list_items(kind="brain-action", limit=100)) if ks is not None else []

    items = _feed.merge_feed(r_items, a_items, p_items, b_items,
                             limit=limit, type_filter=type_filter)
    return web.json_response({"items": items})


async def handle_brain_reasoning(request: web.Request) -> web.Response:
    rlog = request.app.get("reasoning_log")
    if rlog is None:
        return web.json_response({"reasoning": []})
    try:
        limit = min(int(request.rel_url.query.get("limit", "50")), 200)
    except ValueError:
        limit = 50
    return web.json_response({"reasoning": rlog.list(limit=limit)})


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
