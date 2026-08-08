import pytest
from aiohttp import web
from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.api.handlers_brain import (
    handle_list_advisories, handle_ack_advisory, handle_dismiss_advisory,
)

_CAND = {"check_id": "low_battery", "severity": "warn", "title": "Bat",
         "evidence": {}, "suggested_fix": "fix", "fix_kind": "manual",
         "source_ref": "low_battery:sensor.a"}


def _app(tmp_path):
    app = web.Application()
    adv = AdvisoryStore(str(tmp_path / "a.db"))
    adv.reconcile([_CAND], {"low_battery"}, now="2026-07-28T08:00:00Z")
    app["advisory_store"] = adv
    app.router.add_get("/api/brain/advisories", handle_list_advisories)
    app.router.add_post("/api/brain/advisories/{id}/ack", handle_ack_advisory)
    app.router.add_post("/api/brain/advisories/{id}/dismiss", handle_dismiss_advisory)
    return app


@pytest.mark.asyncio
async def test_advisories_list_and_ack(tmp_path, aiohttp_client):
    """fetta E3 Task 5: era test_reasoning_and_advisories, che mescolava
    /api/brain/reasoning (uscita col Brain auto-proponente -- handle_brain_
    reasoning e reasoning_log sono usciti) e /api/brain/advisories (viva
    fino al Task 6). Potato al solo soggetto vivo."""
    client = await aiohttp_client(_app(tmp_path))
    a = await client.get("/api/brain/advisories?status=open")
    body = await a.json()
    assert len(body["advisories"]) == 1
    aid = body["advisories"][0]["id"]
    ack = await client.post(f"/api/brain/advisories/{aid}/ack",
                            headers={"X-Requested-With": "fetch"})
    assert (await ack.json())["ok"] is True


# fetta E3 Task 5: test_feed_merges (esercitava /api/brain/feed, che
# leggeva reasoning_log + advisory_store + proposal_store + knowledge_store
# via brain.feed) e' uscito -- soggetto (handle_brain_feed, brain.feed)
# cancellato per intero col Brain auto-proponente. Nessun successore.


@pytest.mark.asyncio
async def test_ack_bad_id(tmp_path, aiohttp_client):
    client = await aiohttp_client(_app(tmp_path))
    r = await client.post("/api/brain/advisories/9999/ack",
                          headers={"X-Requested-With": "fetch"})
    assert r.status == 409
