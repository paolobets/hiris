import pytest
from aiohttp import web
from hiris.app.brain.reasoning_log import ReasoningLog
from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.api.handlers_brain import (
    handle_brain_feed, handle_brain_reasoning, handle_list_advisories,
    handle_ack_advisory, handle_dismiss_advisory,
)

_CAND = {"check_id": "low_battery", "severity": "warn", "title": "Bat",
         "evidence": {}, "suggested_fix": "fix", "fix_kind": "manual",
         "source_ref": "low_battery:sensor.a"}


def _app(tmp_path):
    app = web.Application()
    rlog = ReasoningLog(str(tmp_path / "r.db"))
    rlog.capture(mode="holistic", text="Ho dedotto qualcosa")
    adv = AdvisoryStore(str(tmp_path / "a.db"))
    adv.reconcile([_CAND], {"low_battery"}, now="2026-07-28T08:00:00Z")
    app["reasoning_log"] = rlog
    app["advisory_store"] = adv
    app.router.add_get("/api/brain/feed", handle_brain_feed)
    app.router.add_get("/api/brain/reasoning", handle_brain_reasoning)
    app.router.add_get("/api/brain/advisories", handle_list_advisories)
    app.router.add_post("/api/brain/advisories/{id}/ack", handle_ack_advisory)
    app.router.add_post("/api/brain/advisories/{id}/dismiss", handle_dismiss_advisory)
    return app


@pytest.mark.asyncio
async def test_reasoning_and_advisories(tmp_path, aiohttp_client):
    client = await aiohttp_client(_app(tmp_path))
    r = await client.get("/api/brain/reasoning")
    assert r.status == 200 and len((await r.json())["reasoning"]) == 1
    a = await client.get("/api/brain/advisories?status=open")
    body = await a.json()
    assert len(body["advisories"]) == 1
    aid = body["advisories"][0]["id"]
    ack = await client.post(f"/api/brain/advisories/{aid}/ack",
                            headers={"X-Requested-With": "fetch"})
    assert (await ack.json())["ok"] is True


@pytest.mark.asyncio
async def test_feed_merges(tmp_path, aiohttp_client):
    client = await aiohttp_client(_app(tmp_path))
    r = await client.get("/api/brain/feed")
    items = (await r.json())["items"]
    types = {i["type"] for i in items}
    assert "reasoning" in types and "advisory" in types


@pytest.mark.asyncio
async def test_ack_bad_id(tmp_path, aiohttp_client):
    client = await aiohttp_client(_app(tmp_path))
    r = await client.post("/api/brain/advisories/9999/ack",
                          headers={"X-Requested-With": "fetch"})
    assert r.status == 409
