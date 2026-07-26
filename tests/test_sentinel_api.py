import pytest
from aiohttp import web
from hiris.app.api.handlers_sentinel import (
    handle_get_sentinel_policy, handle_save_sentinel_policy, handle_sentinel_timeline)
from hiris.app.watcher.sentinel_store import SentinelStore


@pytest.mark.asyncio
async def test_policy_get_and_save(aiohttp_client, tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["sentinel_store"] = SentinelStore(str(tmp_path / "s.db"))
    app.router.add_get("/api/sentinel/policy", handle_get_sentinel_policy)
    app.router.add_post("/api/sentinel/policy", handle_save_sentinel_policy)
    client = await aiohttp_client(app)

    r = await client.get("/api/sentinel/policy")
    body = await r.json()
    assert r.status == 200 and "detectors_meta" in body

    r = await client.post("/api/sentinel/policy",
                          json={"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 12}}})
    assert (await r.json())["detectors"]["battery"]["enabled"] is True


@pytest.mark.asyncio
async def test_save_rejects_string_max_watt(aiohttp_client, tmp_path):
    """Review C/#8: a malformed POST (string threshold instead of numeric)
    must be rejected with a 4xx, never persisted, never applied live."""
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app.router.add_post("/api/sentinel/policy", handle_save_sentinel_policy)
    client = await aiohttp_client(app)

    r = await client.post("/api/sentinel/policy",
                          json={"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                                         "max_watt": "high"}}})
    assert r.status == 400
    body = await r.json()
    assert body["ok"] is False

    from hiris.app.watcher.policy import load_policy
    pol = load_policy(str(tmp_path))
    assert pol["detectors"]["power"]["max_watt"] == 3000  # default, untouched


@pytest.mark.asyncio
async def test_save_rejects_string_entities(aiohttp_client, tmp_path):
    """Review C/#8: string `entities` (instead of a list) must be rejected --
    a substring-matched string would cause false positives in the guardian's
    entity filter if it ever reached disk/live policy."""
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app.router.add_post("/api/sentinel/policy", handle_save_sentinel_policy)
    client = await aiohttp_client(app)

    r = await client.post("/api/sentinel/policy",
                          json={"detectors": {"power": {"enabled": True, "entities": "light.x"}}})
    assert r.status == 400
    body = await r.json()
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_save_still_applies_live_on_valid_policy(aiohttp_client, tmp_path):
    """Legit configs (valid types/ranges) must still save AND apply live
    unchanged -- guards against the 4xx path accidentally swallowing the
    happy path too."""
    class _StubGuardian:
        def __init__(self):
            self.calls = []

        def set_policy(self, policy):
            self.calls.append(policy)

    app = web.Application()
    app["data_dir"] = str(tmp_path)
    guardian = _StubGuardian()
    app["guardian"] = guardian
    app.router.add_post("/api/sentinel/policy", handle_save_sentinel_policy)
    client = await aiohttp_client(app)

    r = await client.post("/api/sentinel/policy",
                          json={"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                                         "max_watt": 2500}}})
    assert r.status == 200
    body = await r.json()
    assert body["ok"] is True
    assert body["detectors"]["power"]["max_watt"] == 2500
    assert len(guardian.calls) == 1
    assert guardian.calls[0]["detectors"]["power"]["max_watt"] == 2500


@pytest.mark.asyncio
async def test_timeline(aiohttp_client, tmp_path):
    app = web.Application()
    store = SentinelStore(str(tmp_path / "s.db"))
    store.record_event({"ts": 1.0, "kind": "battery", "entity_id": "sensor.b",
                        "verdict": "anomalia", "severity": "info", "outcome": "notify", "message": "8%"})
    app["sentinel_store"] = store
    app.router.add_get("/api/sentinel/timeline", handle_sentinel_timeline)
    client = await aiohttp_client(app)
    r = await client.get("/api/sentinel/timeline")
    assert r.status == 200 and (await r.json())["events"][0]["kind"] == "battery"


@pytest.mark.asyncio
async def test_timeline_negative_limit_does_not_bypass_200_cap(aiohttp_client, tmp_path):
    """Task L/3: SQLite treats a negative LIMIT as "unlimited" -- a
    `?limit=-1` query param must never bypass the documented 200-row cap;
    it must be clamped into [1, 200] like any other out-of-range value."""
    app = web.Application()
    store = SentinelStore(str(tmp_path / "s.db"))
    for i in range(210):
        store.record_event({"ts": float(i), "kind": "battery", "entity_id": "sensor.b",
                            "verdict": "anomalia", "severity": "info", "outcome": "notify",
                            "message": str(i)})
    app["sentinel_store"] = store
    app.router.add_get("/api/sentinel/timeline", handle_sentinel_timeline)
    client = await aiohttp_client(app)

    r = await client.get("/api/sentinel/timeline?limit=-1")
    assert r.status == 200
    events = (await r.json())["events"]
    assert len(events) <= 200
