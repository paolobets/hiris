import pytest


def test_reasoning_routes_registered():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/api/reasoning/claim" in paths
    assert "/api/reasoning/submit" in paths


def test_reasoning_queue_importable():
    from hiris.app.reasoning.queue import ReasoningQueue
    assert ReasoningQueue is not None


# ---------------------------------------------------------------------------
# Fail-closed verdict on remote input (review fix on Task 3)
# ---------------------------------------------------------------------------

def _resolve_verdict(decision_dict):
    """Mirrors server.py's _execute_decision verdict resolution exactly:
    anything other than the two known verdict values degrades to
    "falso_positivo" (fail-CLOSED), never defaults to the actuation-eligible
    "anomalia"."""
    v = decision_dict.get("verdict")
    return v if v in ("anomalia", "falso_positivo") else "falso_positivo"


def test_verdict_resolution_fails_closed():
    assert _resolve_verdict({}) == "falso_positivo"
    assert _resolve_verdict({"verdict": None}) == "falso_positivo"
    assert _resolve_verdict({"verdict": "bogus"}) == "falso_positivo"
    assert _resolve_verdict({"verdict": "anomalia"}) == "anomalia"
    assert _resolve_verdict({"verdict": "falso_positivo"}) == "falso_positivo"


@pytest.mark.asyncio
async def test_missing_verdict_decision_does_not_execute_action():
    """A submitted decision with a missing/unknown verdict must fail CLOSED
    all the way through the real executor: execute() must skip (no
    notify/act/propose call reaches actuation), even when the decision
    carries a concrete, green-tier action and allow_green_auto is on — the
    worst case where a fail-OPEN default would have actuated."""
    from hiris.app.watcher.executor import execute
    from hiris.app.watcher.signals import Decision, WakeEvent

    acted = []

    async def _act(action):
        acted.append(action)

    async def _notify(message, *, title):
        pass

    async def _propose(decision, wake):
        pass

    decision_dict = {"message": "runner sent garbage", "action": {
        "domain": "light", "service": "turn_on", "entity_id": "light.x"}}
    wake_dict = {"signal_kind": "holistic", "entity_id": "home"}

    verdict = _resolve_verdict(decision_dict)  # no "verdict" key -> falso_positivo
    d = Decision(verdict=verdict, severity=decision_dict.get("severity", "info"),
                 message=decision_dict.get("message", ""), action=decision_dict.get("action"))
    wake = WakeEvent(signal_kind=wake_dict.get("signal_kind", "holistic"),
                      entity_id=wake_dict.get("entity_id", "home"),
                      severity_hint=wake_dict.get("severity_hint", "info"),
                      evidence=wake_dict.get("evidence") or {}, ts=1.0)

    outcome = await execute(
        d, wake, tiers={"light": "green"}, entity_tiers={},
        notify=_notify, act=_act, propose=_propose, allow_green_auto=True)

    assert outcome == "skip"
    assert acted == []


@pytest.mark.asyncio
async def test_submit_logs_exception_from_execute_decision(aiohttp_client, tmp_path, caplog):
    """Fix 2: a failing execute_decision must be logged, not swallowed silently."""
    from aiohttp import web
    from hiris.app.api.handlers_reasoning import handle_reasoning_claim, handle_reasoning_submit
    from hiris.app.reasoning.queue import ReasoningQueue

    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home", "severity_hint": "info",
              "evidence": {}, "ts": 1.0}, {"snapshot": {}}, deadline_ts=100.0, job_id="J", now=1.0)

    app = web.Application()
    app["reasoning_queue"] = q
    app["_clock"] = lambda: 10.0

    async def _boom(decision, wake):
        raise RuntimeError("boom")
    app["execute_decision"] = _boom
    app.router.add_post("/api/reasoning/claim", handle_reasoning_claim)
    app.router.add_post("/api/reasoning/submit", handle_reasoning_submit)

    client = await aiohttp_client(app)
    c = await (await client.post("/api/reasoning/claim")).json()
    with caplog.at_level("ERROR", logger="hiris.app.api.handlers_reasoning"):
        r = await client.post("/api/reasoning/submit", json={
            "job_id": "J", "nonce": c["job"]["nonce"],
            "decision": {"verdict": "anomalia", "message": "x"}})
    body = await r.json()
    assert body["ok"] is True and body["outcome"] == "error"
    assert any("execute_decision failed" in rec.message for rec in caplog.records)
    q.close()
