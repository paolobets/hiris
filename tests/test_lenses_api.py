"""TDD for Slice 5b Task 6 -- CRUD /api/lenses + re-register schedules +
in-memory lens cache refresh.

These tests exercise the handlers directly against a bare `aiohttp.web.
Application()` (same pattern as `test_sentinel_api.py`/`test_gateway_policy.py`):
auth/CSRF is an app-level middleware (`internal_auth_middleware`,
`csrf_middleware` in `server.py`), never per-route, so a bare app without
those middlewares exercises the exact same route/handler wiring a protected
request would reach after clearing them -- there is nothing route-local to
test.

`register_lens_schedules` is faked with a spy (mirrors `test_scheduled_lenses
.py`'s fakes) so these tests never boot the real scheduler/HA client.
"""
from __future__ import annotations

import pytest
from aiohttp import web

from hiris.app.api.handlers_lenses import (
    get_event_lenses,
    handle_create_lens,
    handle_delete_lens,
    handle_list_lenses,
    handle_update_lens,
    set_lenses,
)
from hiris.app.watcher.lenses import load_lenses, save_lenses


class _RegisterSpy:
    def __init__(self):
        self.calls = 0

    async def __call__(self, app):
        self.calls += 1


def _app(tmp_path, *, register=None):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["register_lens_schedules"] = register if register is not None else _RegisterSpy()
    # Mirrors server.py's `_on_startup`: the cache holder is initialized
    # BEFORE the app starts serving, so mutating it in-place later never
    # hits aiohttp's "changing state of started application" deprecation.
    app["user_lenses"] = []
    app.router.add_get("/api/lenses", handle_list_lenses)
    app.router.add_post("/api/lenses", handle_create_lens)
    app.router.add_put("/api/lenses/{id}", handle_update_lens)
    app.router.add_delete("/api/lenses/{id}", handle_delete_lens)
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
    r = await client.get("/api/lenses")
    assert r.status == 200
    assert (await r.json())["lenses"] == []

    # create
    r = await client.post("/api/lenses", json=VALID_EVENT_LENS)
    assert r.status == 201
    body = await r.json()
    assert body["ok"] is True
    lens = body["lens"]
    lens_id = lens["id"]
    assert lens["name"] == "Porta aperta"
    assert spy.calls == 1

    # list now contains it
    r = await client.get("/api/lenses")
    listed = (await r.json())["lenses"]
    assert [l["id"] for l in listed] == [lens_id]

    # update
    updated_body = {**VALID_EVENT_LENS, "name": "Porta aperta (agg.)", "severity": "alert"}
    r = await client.put(f"/api/lenses/{lens_id}", json=updated_body)
    assert r.status == 200
    updated = (await r.json())["lens"]
    assert updated["id"] == lens_id            # id from the URL, not re-minted
    assert updated["name"] == "Porta aperta (agg.)"
    assert updated["severity"] == "alert"
    assert spy.calls == 2

    r = await client.get("/api/lenses")
    listed = (await r.json())["lenses"]
    assert len(listed) == 1 and listed[0]["severity"] == "alert"

    # delete
    r = await client.delete(f"/api/lenses/{lens_id}")
    assert r.status == 200
    assert (await r.json())["lenses"] == []
    assert spy.calls == 3

    r = await client.get("/api/lenses")
    assert (await r.json())["lenses"] == []

    # persisted to disk too (not just the in-memory cache)
    assert load_lenses(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# Invalid lens -> 400
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_invalid_lens_is_400(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.post("/api/lenses", json=INVALID_LENS)
    assert r.status == 400
    assert "error" in (await r.json())
    # never saved, never re-registered
    assert load_lenses(str(tmp_path)) == []
    assert spy.calls == 0


@pytest.mark.asyncio
async def test_create_non_dict_body_is_400(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)
    r = await client.post("/api/lenses", json=["not", "a", "dict"])
    assert r.status == 400


@pytest.mark.asyncio
async def test_update_invalid_lens_is_400(aiohttp_client, tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    existing = load_lenses(str(tmp_path))[0]
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.put(f"/api/lenses/{existing['id']}", json=INVALID_LENS)
    assert r.status == 400
    # unchanged on disk, no re-register
    assert load_lenses(str(tmp_path)) == [existing]
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# 404s
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_missing_id_is_404(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.put("/api/lenses/deadbeef0000", json=VALID_EVENT_LENS)
    assert r.status == 404
    assert spy.calls == 0


@pytest.mark.asyncio
async def test_delete_missing_id_is_404(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.delete("/api/lenses/deadbeef0000")
    assert r.status == 404
    assert spy.calls == 0


# ---------------------------------------------------------------------------
# register_lens_schedules is invoked after every mutation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_lens_schedules_called_after_post_put_delete(aiohttp_client, tmp_path):
    spy = _RegisterSpy()
    app = _app(tmp_path, register=spy)
    client = await aiohttp_client(app)

    r = await client.post("/api/lenses", json=VALID_EVENT_LENS)
    lens_id = (await r.json())["lens"]["id"]
    assert spy.calls == 1

    await client.put(f"/api/lenses/{lens_id}", json=VALID_EVENT_LENS)
    assert spy.calls == 2

    await client.delete(f"/api/lenses/{lens_id}")
    assert spy.calls == 3


@pytest.mark.asyncio
async def test_missing_register_lens_schedules_does_not_crash(aiohttp_client, tmp_path):
    """`register_lens_schedules` absent from `app` (e.g. a minimal test app)
    must not break the mutation -- it's an optional live-apply step."""
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["user_lenses"] = []
    app.router.add_post("/api/lenses", handle_create_lens)
    client = await aiohttp_client(app)

    r = await client.post("/api/lenses", json=VALID_EVENT_LENS)
    assert r.status == 201


# ---------------------------------------------------------------------------
# In-memory cache refresh (Task 4 review / Task 6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_refreshed_after_create_update_delete(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)

    r = await client.post("/api/lenses", json=VALID_EVENT_LENS)
    lens_id = (await r.json())["lens"]["id"]

    assert app["user_lenses"] == load_lenses(str(tmp_path))
    assert [l["id"] for l in app["user_lenses"]] == [lens_id]

    await client.put(f"/api/lenses/{lens_id}", json={**VALID_EVENT_LENS, "severity": "alert"})
    assert app["user_lenses"][0]["severity"] == "alert"

    await client.delete(f"/api/lenses/{lens_id}")
    assert app["user_lenses"] == []


@pytest.mark.asyncio
async def test_list_endpoint_serves_the_cache_not_disk(aiohttp_client, tmp_path):
    """GET /api/lenses must reflect the in-memory cache (Task 6) once it's
    populated -- proven here by making the cache and disk disagree."""
    app = _app(tmp_path)
    set_lenses(app, [{"id": "abcdef012345", "name": "cache-only", "enabled": True}])
    client = await aiohttp_client(app)

    r = await client.get("/api/lenses")
    listed = (await r.json())["lenses"]
    assert listed == [{"id": "abcdef012345", "name": "cache-only", "enabled": True}]
    # disk is (and stays) empty -- the handler never fell back to it
    assert load_lenses(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# get_event_lenses (Guardian's repointed read path) reads the cache, not disk
# ---------------------------------------------------------------------------

def test_get_event_lenses_filters_enabled_event_lenses_from_cache():
    app = {}
    set_lenses(app, [
        {"id": "1" * 12, "enabled": True, "trigger": {"type": "event", "entity_id": "a"}},
        {"id": "2" * 12, "enabled": False, "trigger": {"type": "event", "entity_id": "b"}},
        {"id": "3" * 12, "enabled": True, "trigger": {"type": "schedule", "interval_min": 5}},
    ])
    out = get_event_lenses(app)
    assert [l["id"] for l in out] == ["1" * 12]


def test_get_event_lenses_never_touches_disk():
    """No `data_dir` key at all in `app` -- if this read disk it would raise/
    fail; reading only the cache must work regardless."""
    app = {"user_lenses": [
        {"id": "9" * 12, "enabled": True, "trigger": {"type": "event", "entity_id": "x"}},
    ]}
    assert [l["id"] for l in get_event_lenses(app)] == ["9" * 12]


def test_get_event_lenses_empty_cache_is_empty_list():
    assert get_event_lenses({}) == []


def test_set_lenses_mutates_in_place_never_rebinds():
    """aiohttp forbids `app[key] = ...` after startup -- `set_lenses` must
    mutate the SAME list object across calls, not create a new one."""
    app = {}
    set_lenses(app, [{"id": "a"}])
    holder = app["user_lenses"]
    set_lenses(app, [{"id": "b"}, {"id": "c"}])
    assert app["user_lenses"] is holder
    assert holder == [{"id": "b"}, {"id": "c"}]
