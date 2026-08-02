from __future__ import annotations
import asyncio

from aiohttp import web

from ..brain.identity import resolve_owner


async def handle_list_pending(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    if store is None:
        # Uno store assente NON e' una coda vuota. Rispondere 200 con una
        # lista vuota rendeva "non ho potuto leggere" indistinguibile da "non
        # c'e' niente da approvare": chi guarda la coda in chat concluderebbe
        # che non ha nulla in sospeso mentre i ricordi restano pending e non
        # richiamabili. Stesso 503 delle rotte di scrittura qui sotto; `items`
        # resta presente e vuoto perche' la forma della risposta non cambi.
        return web.json_response(
            {"error": "knowledge store not configured", "items": []}, status=503
        )
    # Owner-scope (review B/#16 IDOR fix): only the caller's own pending
    # items plus shared 'home' items -- never another user's private rows.
    # resolve_owner() fails closed to 'home' when identity is unknown.
    owner = resolve_owner(request)
    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(
        None, lambda: store.list_items(status="pending", owner=owner)
    )
    return web.json_response({"items": items})


async def handle_approve(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    if store is None:
        return web.json_response({"error": "knowledge store not configured"}, status=503)
    try:
        item_id = int(request.match_info["id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "invalid id"}, status=400)
    # Owner-scope (review B/#16 IDOR fix): reject cross-owner approvals.
    owner = resolve_owner(request)
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, lambda: store.approve(item_id, owner=owner))
    if not ok:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"ok": True})


async def handle_reject(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    if store is None:
        return web.json_response({"error": "knowledge store not configured"}, status=503)
    try:
        item_id = int(request.match_info["id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "invalid id"}, status=400)
    # Owner-scope (review B/#16 IDOR fix): reject cross-owner rejections.
    owner = resolve_owner(request)
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, lambda: store.delete_item(item_id, owner=owner))
    if not ok:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"ok": True})


async def handle_manual_add(request: web.Request) -> web.Response:
    store = request.app.get("knowledge_store")
    if store is None:
        return web.json_response({"error": "knowledge store not configured"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    content = (body.get("content") or "").strip()
    if not content:
        return web.json_response({"error": "content required"}, status=400)

    embedder = request.app.get("embedding_provider")
    emb: list[float] = []
    if embedder is not None:
        try:
            emb = await embedder.embed(content)
        except Exception:
            emb = []

    owner = resolve_owner(request)
    loop = asyncio.get_running_loop()
    item_id = await loop.run_in_executor(
        None,
        lambda: store.add_item(
            kind=body.get("kind", "note"),
            content=content,
            owner=owner,
            title=body.get("title", ""),
            amount=body.get("amount"),
            due_date=body.get("due_date"),
            category=body.get("category"),
            embedding=emb or None,
            sensitivity=body.get("sensitivity", "normal"),
            source="manual",
            status="approved",
        ),
    )
    return web.json_response({"id": item_id, "status": "approved"})
