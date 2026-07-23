from __future__ import annotations
from aiohttp import web


async def handle_list_suggestions(request: web.Request) -> web.Response:
    store = request.app.get("suggestion_store")
    if store is None:
        return web.json_response({"suggestions": []})
    return web.json_response({"suggestions": store.list()})


async def handle_undo_suggestion(request: web.Request) -> web.Response:
    try:
        sid = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"ok": False}, status=400)

    store = request.app.get("suggestion_store")
    data_dir = request.app.get("data_dir")
    if store is None or data_dir is None:
        return web.json_response({"ok": False})

    from ..brain.suggestions import undo
    ok = undo(store, data_dir, sid)
    return web.json_response({"ok": bool(ok)})
