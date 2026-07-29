"""User-defined "Agentbot" CRUD API (Slice 5b, Task 6; renamed from "lens"
in SP-4 Fase A Task 4).

Thin HTTP layer over `watcher.agentbots` (Task 1's validated store; the
module file was renamed from its Fase A filename in SP-4 Fase B Task 5 --
it contains only Agentbot symbols): every mutation (POST/PUT/DELETE) validates via
`agentbots.validate_agentbot` (create/update) or checks existence
(update/delete), persists via `agentbots.save_agentbots`/`upsert_agentbot`/
`delete_agentbot`, re-registers the scheduler jobs
(`app["register_agentbot_schedules"]`, Task 5) so a schedule
edit/delete/create applies immediately, and refreshes the in-memory
Agentbot cache below -- in that order (save -> register_schedules ->
refresh-cache), mirroring `handlers_gateway_policy.apply_saved_policy`'s
"save first, then apply live" shape.

Auth/CSRF: NOT handled here. Like every other config route
(`handlers_sentinel.py`, `handlers_gateway_policy.py`), protection comes
from the app-level `internal_auth_middleware` + `csrf_middleware`
(`server.py`, applied to every `/api/*` route via `web.Application(
middlewares=[...])`) -- there is no per-route auth to replicate, only
route registration under the same `app.router`.

In-memory Agentbot cache (Task 4 review): the Guardian's event-Agentbot
source used to call `watcher.agentbots.load_agentbots(data_dir)` -- a disk
read + full re-validation of every Agentbot -- on EVERY `state_changed`
event. `set_agentbots`/`get_event_agentbots` hold a live, in-place-mutated
list on `app["user_agentbots"]` instead (aiohttp forbids rebinding
`app[key]` once the app has started, so the holder is cleared+extended,
never reassigned -- same trick as `handlers_gateway_policy.
apply_saved_policy`'s `gateway_settings`/`execute_policy` holders).
`server.py` populates it once at startup and repoints the Guardian's
`get_user_agentbots` callback to `get_event_agentbots(app)`.
"""
from __future__ import annotations

from aiohttp import web

from ..watcher import agentbots as _store


def set_agentbots(app, agentbots: list[dict]) -> None:
    """(Re)populate the in-memory Agentbot cache in place. Called once at
    startup (with the current disk contents) and after every CRUD mutation
    (with the freshly-saved, cleaned list) -- never rebinds
    `app["user_agentbots"]` after the first call, since aiohttp forbids
    `app[key] = ...` once the app has started."""
    holder = app.get("user_agentbots")
    if not isinstance(holder, list):
        app["user_agentbots"] = holder = []
    holder[:] = agentbots


def get_event_agentbots(app) -> list[dict]:
    """The enabled, EVENT-triggered, RULE-mode Agentbots currently in the
    in-memory cache -- what the Guardian's per-`state_changed` dispatch
    reads (never the disk; see module docstring). Missing/uninitialized
    cache -> [].

    Fase 1 fix-wave IMPORTANT: `mode` gate added -- the plan's constraint is
    "solo mode='rule' e' raggiungibile" (an objective Agentbot is heavier,
    an LLM turn, and is meant to be launched manually/on a schedule/by a
    rule, never directly off an event). `validate_agentbot` already forbids
    the objective+event combination at the store layer, but this is the
    actual runtime dispatch gate -- defense in depth against anything that
    lands in the cache without going through that validator, and against a
    future mode that doesn't share the same trigger restriction."""
    return [
        a for a in (app.get("user_agentbots") or [])
        if isinstance(a, dict) and a.get("enabled")
        and (a.get("trigger") or {}).get("type") == "event"
        and a.get("mode", "rule") == "rule"
    ]


async def _apply_mutation(app, clean: list[dict]) -> None:
    """Common post-save step for every mutating handler: re-register the
    scheduler jobs (Task 5), THEN refresh the in-memory cache other readers
    (the Guardian) use -- both against the just-saved, authoritative
    `clean` list, never a fresh disk read (save_agentbots/upsert_agentbot/
    delete_agentbot already return exactly what's on disk now)."""
    register = app.get("register_agentbot_schedules")
    if register is not None:
        await register(app)
    # Cache/disk consistency across interleaved mutations depends on
    # `register_agentbot_schedules` containing NO `await` between reading
    # the just-saved list and this `set_agentbots` call -- a future yield
    # point in there would let a second concurrent mutation's
    # save+cache-refresh interleave in between, leaving the cache stale/out
    # of order.
    set_agentbots(app, clean)


def _data_dir(request: web.Request) -> str:
    return request.app.get("data_dir") or "/data"


async def handle_list_agentbots(request: web.Request) -> web.Response:
    """GET /api/agentbots -- current Agentbot list. Serves the in-memory
    cache when populated (avoids yet another disk read); falls back to
    disk otherwise (e.g. a direct call before startup has initialized the
    cache)."""
    holder = request.app.get("user_agentbots")
    if holder is None:
        holder = _store.load_agentbots(_data_dir(request))
    return web.json_response({"agentbots": holder})


async def handle_create_agentbot(request: web.Request) -> web.Response:
    """POST /api/agentbots -- validate + create. 400 on an invalid
    Agentbot.

    A create must always mint a FRESH id, never reuse one --
    `validate_agentbot` only re-mints `id` when it's malformed, so a
    format-valid id copied from a GET/import/retried request
    (`^[0-9a-f]{12}$`) would otherwise be honored and `upsert_agentbot`
    would silently REPLACE that existing Agentbot while this handler
    still reports 201 Created. Stripping any client `id` here forces
    `validate_agentbot` to always mint a new one."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    body = body if isinstance(body, dict) else {}
    body = {k: v for k, v in body.items() if k != "id"}
    cleaned = _store.validate_agentbot(body)
    if cleaned is None:
        return web.json_response({"error": "invalid agentbot"}, status=400)
    data_dir = _data_dir(request)
    all_agentbots = _store.upsert_agentbot(data_dir, cleaned)
    await _apply_mutation(request.app, all_agentbots)
    return web.json_response({"ok": True, "agentbot": cleaned, "agentbots": all_agentbots}, status=201)


async def handle_update_agentbot(request: web.Request) -> web.Response:
    """PUT /api/agentbots/{id} -- validate + update. 404 if the id doesn't
    exist yet, 400 on an invalid Agentbot body."""
    agentbot_id = request.match_info.get("id", "")
    data_dir = _data_dir(request)
    current = _store.load_agentbots(data_dir)
    if not any(a.get("id") == agentbot_id for a in current):
        return web.json_response({"error": "not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "invalid agentbot"}, status=400)
    # The path id is authoritative -- a client-supplied body["id"] can never
    # smuggle an update onto a DIFFERENT existing Agentbot than the URL
    # names.
    body = {**body, "id": agentbot_id}
    cleaned = _store.validate_agentbot(body)
    if cleaned is None:
        return web.json_response({"error": "invalid agentbot"}, status=400)
    all_agentbots = _store.upsert_agentbot(data_dir, cleaned)
    await _apply_mutation(request.app, all_agentbots)
    return web.json_response({"ok": True, "agentbot": cleaned, "agentbots": all_agentbots})


async def handle_delete_agentbot(request: web.Request) -> web.Response:
    """DELETE /api/agentbots/{id}. 404 if the id doesn't exist."""
    agentbot_id = request.match_info.get("id", "")
    data_dir = _data_dir(request)
    current = _store.load_agentbots(data_dir)
    if not any(a.get("id") == agentbot_id for a in current):
        return web.json_response({"error": "not found"}, status=404)
    all_agentbots = _store.delete_agentbot(data_dir, agentbot_id)
    await _apply_mutation(request.app, all_agentbots)
    return web.json_response({"ok": True, "agentbots": all_agentbots})
