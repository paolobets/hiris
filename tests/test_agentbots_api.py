"""TDD for Slice 5b Task 6 -- CRUD /api/agentbots (renamed from the old
lens-CRUD route in SP-4 Fase A Task 4) + re-register schedules + in-memory
Agentbot cache refresh.

These tests exercise the handlers directly against a bare `aiohttp.web.
Application()` (same pattern as `test_sentinel_api.py`/`test_gateway_policy.py`):
auth/CSRF is an app-level middleware (`internal_auth_middleware`,
`csrf_middleware` in `server.py`), never per-route, so a bare app without
those middlewares exercises the exact same route/handler wiring a protected
request would reach after clearing them -- there is nothing route-local to
test.

`register_agentbot_schedules` is faked with a spy (mirrors
`test_scheduled_agentbots.py`'s fakes) so these tests never boot the real
scheduler/HA client.
"""
from __future__ import annotations

import pytest
from aiohttp import web

from hiris.app.api.handlers_agentbots import (
    get_event_agentbots,
    handle_create_agentbot,
    handle_delete_agentbot,
    handle_list_agentbots,
    handle_update_agentbot,
    set_agentbots,
)
from hiris.app.watcher.agentbots import load_agentbots, save_agentbots


class _RegisterSpy:
    def __init__(self):
        self.calls = 0

    async def __call__(self, app):
        self.calls += 1


def _app(tmp_path, *, register=None):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["register_agentbot_schedules"] = register if register is not None else _RegisterSpy()
    # Mirrors server.py's `_on_startup`: the cache holder is initialized
    # BEFORE the app starts serving, so mutating it in-place later never
    # hits aiohttp's "changing state of started application" deprecation.
    app["user_agentbots"] = []
    app.router.add_get("/api/agentbots", handle_list_agentbots)
    app.router.add_post("/api/agentbots", handle_create_agentbot)
    app.router.add_put("/api/agentbots/{id}", handle_update_agentbot)
    app.router.add_delete("/api/agentbots/{id}", handle_delete_agentbot)
    return app


VALID_EVENT_LENS = {
    "name": "Porta aperta",
    "trigger": {"type": "event", "entity_id": "binary_sensor.door", "operator": "==", "threshold": "on"},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "porta aperta"},
    "severity": "warn",
}

INVALID_LENS = {
    "name": "Rotta",
    "trigger": {"type": "event"},  # missing entity_id/operator/threshold
    "action": {"type": "notify"},
}


# ---------------------------------------------------------------------------
# CRUD end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crud_end_to_end(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    # empty list initially
    r = await client.get("/api/agentbots")
    assert r.status == 200
    assert (await r.json())["agentbots"] == []

    # create
    r = await client.post("/api/agentbots", json=VALID_EVENT_LENS)
    assert r.status == 201
    body = await r.json()
    assert body["ok"] is True
    lens = body["agentbot"]
    lens_id = lens["id"]
    assert lens["name"] == "Porta aperta"
    assert spy.calls == 1

    # list now contains it
    r = await client.get("/api/agentbots")
    listed = (await r.json())["agentbots"]
    assert [l["id"] for l in listed] == [lens_id]

    # update
    updated_body = {**VALID_EVENT_LENS, "name": "Porta aperta (agg.)", "severity": "alert"}
    r = await client.put(f"/api/agentbots/{lens_id}", json=updated_body)
    assert r.status == 200
    updated = (await r.json())["agentbot"]
    assert updated["id"] == lens_id            # id from the URL, not re-minted
    assert updated["name"] == "Porta aperta (agg.)"
    assert updated["severity"] == "alert"
    assert spy.calls == 2

    r = await client.get("/api/agentbots")
    listed = (await r.json())["agentbots"]
    assert len(listed) == 1 and listed[0]["severity"] == "alert"

    # delete
    r = await client.delete(f"/api/agentbots/{lens_id}")
    assert r.status == 200
    assert (await r.json())["agentbots"] == []
    assert spy.calls == 3

    r = await client.get("/api/agentbots")
    assert (await r.json())["agentbots"] == []

    # persisted to disk too (not just the in-memory cache)
    assert load_agentbots(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# Invalid lens -> 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_invalid_lens_is_400(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.post("/api/agentbots", json=INVALID_LENS)
    assert r.status == 400
    assert "error" in (await r.json())
    # never saved, never re-registered
    assert load_agentbots(str(tmp_path)) == []
    assert spy.calls == 0


@pytest.mark.asyncio
async def test_create_with_existing_id_in_body_creates_new_lens_not_overwrite(aiohttp_client, tmp_path):
    """POST must always CREATE. A body carrying a format-valid `id` copied
    from an existing lens (GET/import/retried request) must NOT let
    `upsert_agentbot` replace that existing lens -- the handler must strip
    any client-supplied `id` before validating/saving, so a fresh id is
    always minted and the original lens is left untouched."""
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    # create the original lens
    r = await client.post("/api/agentbots", json=VALID_EVENT_LENS)
    assert r.status == 201
    original = (await r.json())["agentbot"]
    original_id = original["id"]

    # POST again, this time smuggling the existing id in the body, with a
    # different name so an overwrite would be observable.
    hijack_body = {**VALID_EVENT_LENS, "id": original_id, "name": "Hijack"}
    r = await client.post("/api/agentbots", json=hijack_body)
    assert r.status == 201
    created = (await r.json())["agentbot"]

    # a brand-new id was minted -- never the client-supplied one
    assert created["id"] != original_id
    assert created["name"] == "Hijack"

    # both lenses now exist, the original untouched
    all_lenses = load_agentbots(str(tmp_path))
    assert len(all_lenses) == 2
    by_id = {l["id"]: l for l in all_lenses}
    assert by_id[original_id]["name"] == "Porta aperta"
    assert by_id[created["id"]]["name"] == "Hijack"


@pytest.mark.asyncio
async def test_create_non_dict_body_is_400(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)
    r = await client.post("/api/agentbots", json=["not", "a", "dict"])
    assert r.status == 400


@pytest.mark.asyncio
async def test_update_invalid_lens_is_400(aiohttp_client, tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS])
    existing = load_agentbots(str(tmp_path))[0]
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.put(f"/api/agentbots/{existing['id']}", json=INVALID_LENS)
    assert r.status == 400
    # unchanged on disk, no re-register
    assert load_agentbots(str(tmp_path)) == [existing]
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_missing_id_is_404(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.put("/api/agentbots/deadbeef0000", json=VALID_EVENT_LENS)
    assert r.status == 404
    assert spy.calls == 0


@pytest.mark.asyncio
async def test_delete_missing_id_is_404(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.delete("/api/agentbots/deadbeef0000")
    assert r.status == 404
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# register_agentbot_schedules is invoked after every mutation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_agentbot_schedules_called_after_post_put_delete(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.post("/api/agentbots", json=VALID_EVENT_LENS)
    lens_id = (await r.json())["agentbot"]["id"]
    assert spy.calls == 1

    await client.put(f"/api/agentbots/{lens_id}", json=VALID_EVENT_LENS)
    assert spy.calls == 2

    await client.delete(f"/api/agentbots/{lens_id}")
    assert spy.calls == 3


@pytest.mark.asyncio
async def test_missing_register_agentbot_schedules_does_not_crash(aiohttp_client, tmp_path):
    """`register_agentbot_schedules` absent from `app` (e.g. a minimal test
    app) must not break the mutation -- it's an optional live-apply step."""
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["user_agentbots"] = []
    app.router.add_post("/api/agentbots", handle_create_agentbot)
    client = await aiohttp_client(app)

    r = await client.post("/api/agentbots", json=VALID_EVENT_LENS)
    assert r.status == 201


# ---------------------------------------------------------------------------
# In-memory cache refresh (Task 4 review / Task 6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_refreshed_after_create_update_delete(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)

    r = await client.post("/api/agentbots", json=VALID_EVENT_LENS)
    lens_id = (await r.json())["agentbot"]["id"]

    assert app["user_agentbots"] == load_agentbots(str(tmp_path))
    assert [l["id"] for l in app["user_agentbots"]] == [lens_id]

    await client.put(f"/api/agentbots/{lens_id}", json={**VALID_EVENT_LENS, "severity": "alert"})
    assert app["user_agentbots"][0]["severity"] == "alert"

    await client.delete(f"/api/agentbots/{lens_id}")
    assert app["user_agentbots"] == []


@pytest.mark.asyncio
async def test_list_endpoint_serves_the_cache_not_disk(aiohttp_client, tmp_path):
    """GET /api/agentbots must reflect the in-memory cache (Task 6) once
    it's populated -- proven here by making the cache and disk disagree."""
    app = _app(tmp_path)
    set_agentbots(app, [{"id": "abcdef012345", "name": "cache-only", "enabled": True}])
    client = await aiohttp_client(app)

    r = await client.get("/api/agentbots")
    listed = (await r.json())["agentbots"]
    assert listed == [{"id": "abcdef012345", "name": "cache-only", "enabled": True}]
    # disk is (and stays) empty -- the handler never fell back to it
    assert load_agentbots(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# get_event_agentbots (Guardian's repointed read path) reads the cache, not
# disk
# ---------------------------------------------------------------------------

def test_get_event_agentbots_filters_enabled_event_lenses_from_cache():
    app = {}
    set_agentbots(app, [
        {"id": "1" * 12, "enabled": True, "trigger": {"type": "event", "entity_id": "a"}},
        {"id": "2" * 12, "enabled": False, "trigger": {"type": "event", "entity_id": "b"}},
        {"id": "3" * 12, "enabled": True, "trigger": {"type": "schedule", "interval_min": 5}},
    ])
    out = get_event_agentbots(app)
    assert [l["id"] for l in out] == ["1" * 12]


def test_get_event_agentbots_never_touches_disk():
    """No `data_dir` key at all in `app` -- if this read disk it would raise/
    fail; reading only the cache must work regardless."""
    app = {"user_agentbots": [
        {"id": "9" * 12, "enabled": True, "trigger": {"type": "event", "entity_id": "x"}},
    ]}
    assert [l["id"] for l in get_event_agentbots(app)] == ["9" * 12]


def test_get_event_agentbots_empty_cache_is_empty_list():
    assert get_event_agentbots({}) == []


def test_set_agentbots_mutates_in_place_never_rebinds():
    """aiohttp forbids `app[key] = ...` after startup -- `set_agentbots`
    must mutate the SAME list object across calls, not create a new one."""
    app = {}
    set_agentbots(app, [{"id": "a"}])
    holder = app["user_agentbots"]
    set_agentbots(app, [{"id": "b"}, {"id": "c"}])
    assert app["user_agentbots"] is holder
    assert holder == [{"id": "b"}, {"id": "c"}]
