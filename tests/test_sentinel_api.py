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
