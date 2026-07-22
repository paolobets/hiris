import pytest
from aiohttp import web
from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
from hiris.app.reasoning.queue import ReasoningQueue


def _app(tmp_path):
    app = web.Application()
    q = ReasoningQueue(str(tmp_path / "r.db"))
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0
    executed = []
    async def _exec(decision, wake): executed.append((decision, wake)); return "notify"
    app["execute_decision"] = _exec
    app["_executed_ref"] = executed
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)
    return app, q


@pytest.mark.asyncio
async def test_claim_returns_null_when_empty(aiohttp_client, tmp_path):
    app, q = _app(tmp_path)
    client = await aiohttp_client(app)
    r = await client.post("/api/reasoning/claim")
    assert (await r.json())["job"] is None


@pytest.mark.asyncio
async def test_claim_then_submit_executes(aiohttp_client, tmp_path):
    app, q = _app(tmp_path)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
              "evidence": {}, "ts": 1.0}, {"snapshot": {}}, deadline_ts=100.0, job_id="J", now=1.0)
    client = await aiohttp_client(app)
    c = await (await client.post("/api/reasoning/claim")).json()
    assert c["job"]["job_id"] == "J"
    r = await client.post("/api/reasoning/submit", json={"job_id": "J", "nonce": c["job"]["nonce"],
        "decision": {"verdict": "anomalia", "severity": "info", "message": "ok", "action": None}})
    body = await r.json()
    assert body["ok"] is True and body["outcome"] == "notify"
    assert app["_executed_ref"]  # execute_decision chiamato


@pytest.mark.asyncio
async def test_submit_bad_nonce_409(aiohttp_client, tmp_path):
    app, q = _app(tmp_path)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    await q.claim(now=10.0) if False else q.claim(now=10.0)
    client = await aiohttp_client(app)
    r = await client.post("/api/reasoning/submit", json={"job_id": "J", "nonce": "bad", "decision": {}})
    assert r.status == 409 and (await r.json())["ok"] is False
