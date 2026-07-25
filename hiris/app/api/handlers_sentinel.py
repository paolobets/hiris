"""Sentinella API handlers — policy config + timeline observability."""
from __future__ import annotations

from aiohttp import web
from ..watcher.policy import load_policy, save_policy, PolicyValidationError, SENTINEL_DETECTORS


async def handle_get_sentinel_policy(request: web.Request) -> web.Response:
    """GET /api/sentinel/policy — return detector config + metadata."""
    data_dir = request.app.get("data_dir") or "/data"
    pol = load_policy(data_dir)
    return web.json_response({**pol, "detectors_meta": SENTINEL_DETECTORS})


async def handle_save_sentinel_policy(request: web.Request) -> web.Response:
    """POST /api/sentinel/policy — update detector config, return cleaned policy."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    try:
        clean = save_policy(data_dir, body if isinstance(body, dict) else {})
    except PolicyValidationError as exc:
        # Review C/#8: a malformed detector value (wrong type / out of
        # range) must never be persisted nor applied live -- reject with a
        # 4xx instead of the 200 the happy path returns.
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    guardian = request.app.get("guardian")
    if guardian is not None and hasattr(guardian, "set_policy"):
        guardian.set_policy(clean)   # applica live (vedi Task 9)
    return web.json_response({"ok": True, **clean})


async def handle_sentinel_timeline(request: web.Request) -> web.Response:
    """GET /api/sentinel/timeline — return recent sentinel events (limit, default 50, cap 200)."""
    store = request.app.get("sentinel_store")
    if store is None:
        return web.json_response({"events": []})
    try:
        limit = min(int(request.query.get("limit", "50")), 200)
    except ValueError:
        limit = 50
    return web.json_response({"events": store.recent_events(limit)})
