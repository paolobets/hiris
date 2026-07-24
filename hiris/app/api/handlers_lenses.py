"""User-defined "lens" CRUD API (Slice 5b, Task 6).

Thin HTTP layer over `watcher.lenses` (Task 1's validated store): every
mutation (POST/PUT/DELETE) validates via `lenses.validate_lens`
(create/update) or checks existence (update/delete), persists via
`lenses.save_lenses`/`upsert_lens`/`delete_lens`, re-registers the
scheduler jobs (`app["register_lens_schedules"]`, Task 5) so a schedule
edit/delete/create applies immediately, and refreshes the in-memory lens
cache below -- in that order (save -> register_schedules -> refresh-cache),
mirroring `handlers_gateway_policy.apply_saved_policy`'s
"save first, then apply live" shape.

Auth/CSRF: NOT handled here. Like every other config route
(`handlers_sentinel.py`, `handlers_gateway_policy.py`), protection comes
from the app-level `internal_auth_middleware` + `csrf_middleware`
(`server.py`, applied to every `/api/*` route via `web.Application(
middlewares=[...])`) -- there is no per-route auth to replicate, only
route registration under the same `app.router`.

In-memory lens cache (Task 4 review): the Guardian's event-lens source
used to call `watcher.lenses.load_lenses(data_dir)` -- a disk read +
full re-validation of every lens -- on EVERY `state_changed` event.
`set_lenses`/`get_event_lenses` hold a live, in-place-mutated list on
`app["user_lenses"]` instead (aiohttp forbids rebinding `app[key]` once
the app has started, so the holder is cleared+extended, never
reassigned -- same trick as `handlers_gateway_policy.apply_saved_policy`'s
`gateway_settings`/`execute_policy` holders). `server.py` populates it once
at startup and repoints the Guardian's `get_user_lenses` callback to
`get_event_lenses(app)`.
"""
from __future__ import annotations

from aiohttp import web

from ..watcher import lenses as _store


def set_lenses(app, lenses: list[dict]) -> None:
    """(Re)populate the in-memory lens cache in place. Called once at
    startup (with the current disk contents) and after every CRUD mutation
    (with the freshly-saved, cleaned list) -- never rebinds `app["user_lenses"]`
    after the first call, since aiohttp forbids `app[key] = ...` once the
    app has started."""
    holder = app.get("user_lenses")
    if not isinstance(holder, list):
        app["user_lenses"] = holder = []
    holder[:] = lenses


def get_event_lenses(app) -> list[dict]:
    """The enabled, EVENT-triggered lenses currently in the in-memory cache
    -- what the Guardian's per-`state_changed` dispatch reads (never the
    disk; see module docstring). Missing/uninitialized cache -> []."""
    return [
        l for l in (app.get("user_lenses") or [])
        if isinstance(l, dict) and l.get("enabled")
        and (l.get("trigger") or {}).get("type") == "event"
    ]


async def _apply_mutation(app, clean: list[dict]) -> None:
    """Common post-save step for every mutating handler: re-register the
    scheduler jobs (Task 5), THEN refresh the in-memory cache other readers
    (the Guardian) use -- both against the just-saved, authoritative
    `clean` list, never a fresh disk read (save_lenses/upsert_lens/
    delete_lens already return exactly what's on disk now)."""
    register = app.get("register_lens_schedules")
    if register is not None:
        await register(app)
    set_lenses(app, clean)


def _data_dir(request: web.Request) -> str:
    return request.app.get("data_dir") or "/data"


async def handle_list_lenses(request: web.Request) -> web.Response:
    """GET /api/lenses -- current lens list. Serves the in-memory cache when
    populated (avoids yet another disk read); falls back to disk otherwise
    (e.g. a direct call before startup has initialized the cache)."""
    holder = request.app.get("user_lenses")
    if holder is None:
        holder = _store.load_lenses(_data_dir(request))
    return web.json_response({"lenses": holder})


async def handle_create_lens(request: web.Request) -> web.Response:
    """POST /api/lenses -- validate + create. 400 on an invalid lens."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    cleaned = _store.validate_lens(body if isinstance(body, dict) else {})
    if cleaned is None:
        return web.json_response({"error": "invalid lens"}, status=400)
    data_dir = _data_dir(request)
    all_lenses = _store.upsert_lens(data_dir, cleaned)
    await _apply_mutation(request.app, all_lenses)
    return web.json_response({"ok": True, "lens": cleaned, "lenses": all_lenses}, status=201)


async def handle_update_lens(request: web.Request) -> web.Response:
    """PUT /api/lenses/{id} -- validate + update. 404 if the id doesn't
    exist yet, 400 on an invalid lens body."""
    lens_id = request.match_info.get("id", "")
    data_dir = _data_dir(request)
    current = _store.load_lenses(data_dir)
    if not any(l.get("id") == lens_id for l in current):
        return web.json_response({"error": "not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "invalid lens"}, status=400)
    # The path id is authoritative -- a client-supplied body["id"] can never
    # smuggle an update onto a DIFFERENT existing lens than the URL names.
    body = {**body, "id": lens_id}
    cleaned = _store.validate_lens(body)
    if cleaned is None:
        return web.json_response({"error": "invalid lens"}, status=400)
    all_lenses = _store.upsert_lens(data_dir, cleaned)
    await _apply_mutation(request.app, all_lenses)
    return web.json_response({"ok": True, "lens": cleaned, "lenses": all_lenses})


async def handle_delete_lens(request: web.Request) -> web.Response:
    """DELETE /api/lenses/{id}. 404 if the id doesn't exist."""
    lens_id = request.match_info.get("id", "")
    data_dir = _data_dir(request)
    current = _store.load_lenses(data_dir)
    if not any(l.get("id") == lens_id for l in current):
        return web.json_response({"error": "not found"}, status=404)
    all_lenses = _store.delete_lens(data_dir, lens_id)
    await _apply_mutation(request.app, all_lenses)
    return web.json_response({"ok": True, "lenses": all_lenses})
