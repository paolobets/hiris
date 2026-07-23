import pytest
from aiohttp import web
from hiris.app.api.handlers_suggestions import handle_list_suggestions, handle_undo_suggestion
from hiris.app.brain.suggestions import SuggestionStore
from hiris.app.watcher.policy import apply_brain_detector


def _make_app(tmp_path, with_store=True):
    app = web.Application()
    if with_store:
        store = SuggestionStore(str(tmp_path / "s.db"))
        app["suggestion_store"] = store
        app["data_dir"] = str(tmp_path)
    app.router.add_get("/api/suggestions", handle_list_suggestions)
    app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)
    return app


@pytest.mark.asyncio
async def test_list_and_undo_suggestion(tmp_path, aiohttp_client):
    app = _make_app(tmp_path)
    store = app["suggestion_store"]
    data_dir = app["data_dir"]

    config = {"detector": "power", "entity": "sensor.plug_1"}
    delta = apply_brain_detector(data_dir, config["detector"], config["entity"], {})
    sid = store.record("coverage", "Copri sensor.plug_1", "rationale", config, "applied", delta)

    client = await aiohttp_client(app)

    r = await client.get("/api/suggestions")
    assert r.status == 200
    body = await r.json()
    assert len(body["suggestions"]) == 1
    assert body["suggestions"][0]["id"] == sid
    assert body["suggestions"][0]["status"] == "applied"

    r = await client.post(f"/api/suggestions/{sid}/undo")
    assert r.status == 200
    body = await r.json()
    assert body["ok"] is True

    r = await client.get("/api/suggestions")
    body = await r.json()
    assert body["suggestions"][0]["status"] == "dismissed"


@pytest.mark.asyncio
async def test_undo_bad_id_returns_400(tmp_path, aiohttp_client):
    app = _make_app(tmp_path)
    client = await aiohttp_client(app)
    r = await client.post("/api/suggestions/not-an-int/undo")
    assert r.status == 400
    body = await r.json()
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_list_suggestions_defensive_no_store(aiohttp_client):
    app = web.Application()
    app.router.add_get("/api/suggestions", handle_list_suggestions)
    client = await aiohttp_client(app)
    r = await client.get("/api/suggestions")
    assert r.status == 200
    body = await r.json()
    assert body == {"suggestions": []}


@pytest.mark.asyncio
async def test_undo_defensive_no_store(aiohttp_client):
    app = web.Application()
    app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)
    client = await aiohttp_client(app)
    r = await client.post("/api/suggestions/1/undo")
    assert r.status == 200
    body = await r.json()
    assert body == {"ok": False}
