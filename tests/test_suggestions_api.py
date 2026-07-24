import pytest
from aiohttp import web
from hiris.app.api.handlers_suggestions import handle_list_suggestions, handle_undo_suggestion
from hiris.app.brain.cognitive_loop import auto_tune_detectors
from hiris.app.brain.suggestions import SuggestionStore
from hiris.app.watcher.policy import apply_brain_detector, load_policy, save_policy


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


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class _FakeHistoryStore:
    """Minimal fake matching HistoryStore.baseline_for's signature/shape
    (same convention as tests/test_cognitive_loop.py)."""

    def __init__(self, baselines: dict):
        self._baselines = baselines

    def baseline_for(self, entity_id, days=14, today=None):
        return self._baselines.get(
            entity_id, {"mean": None, "on_hours": None, "n_days": 0})


class _StubGuardian:
    """Records every set_policy(policy) call so the test can assert the
    live guardian actually saw the restored threshold."""

    def __init__(self):
        self.calls = []

    def set_policy(self, policy):
        self.calls.append(policy)


@pytest.mark.asyncio
async def test_undo_of_brain_tuning_refreshes_live_guardian_policy(tmp_path, aiohttp_client):
    """Whole-branch review I1: undo() restores max_watt on DISK via
    remove_brain_tuning, but the live Guardian runs off a policy override
    snapshot that undo alone never touches. handle_undo_suggestion must
    call guardian.set_policy(load_policy(data_dir)) so the running
    DETECTORS loop actually sees the restored (pre-tuning) value, not the
    stale tuned one. Setup mirrors test_cognitive_loop.py's Task 5B undo
    test (test_recall_finds_tune_trace_then_real_undo_restores_value_and_
    keeps_entities): a real on-disk policy is tuned via auto_tune_detectors
    (max_watt 3000 -> 1600), recorded as an undoable brain-tune suggestion
    row in a real SuggestionStore, then undone through the real route."""
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {
        "enabled": True, "entities": ["sensor.plug_power"], "max_watt": 3000}}})
    history = _FakeHistoryStore({
        "sensor.plug_power": {"mean": 800.0, "on_hours": None, "n_days": 14},
    })
    sstore = SuggestionStore(str(tmp_path / "s.db"))
    try:
        applied = await auto_tune_detectors(
            data_dir=dd, policy=load_policy(dd), history_store=history,
            knowledge_store=None, embedder=_FakeEmbedder(), store=sstore,
        )
        assert applied == [{"detector": "power", "params": {"max_watt": 1600}}]
        assert load_policy(dd)["detectors"]["power"]["max_watt"] == 1600

        rows = sstore.list()
        assert len(rows) == 1
        assert rows[0]["delta"] == {"detector": "power", "source_ref": "brain-tune:power"}
        sid = rows[0]["id"]

        guardian = _StubGuardian()
        app = web.Application()
        app["suggestion_store"] = sstore
        app["data_dir"] = dd
        app["guardian"] = guardian
        app.router.add_post("/api/suggestions/{id}/undo", handle_undo_suggestion)

        client = await aiohttp_client(app)
        resp = await client.post(f"/api/suggestions/{sid}/undo")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True

        # Restored value on disk (undo's own job -- pre-existing behavior).
        pol = load_policy(dd)
        assert pol["detectors"]["power"]["max_watt"] == 3000

        # The point of this test: the stub guardian was actually refreshed,
        # and with the RESTORED value (3000), not the tuned one (1600) --
        # proving the live guardian sees the undo's effect immediately.
        assert len(guardian.calls) == 1
        assert guardian.calls[0]["detectors"]["power"]["max_watt"] == 3000
    finally:
        sstore.close()
