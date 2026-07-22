import pytest
from hiris.app.reasoning.queue import ReasoningQueue

@pytest.mark.asyncio
async def test_bridge_enqueue_claim_submit_execute(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    executed = []
    async def execute_decision(decision, wake): executed.append((decision, wake)); return "propose"
    # enqueue (come farebbe _holistic_reason con bridge ON)
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home"}, {"snapshot": {"presence": {"present": False}}},
              deadline_ts=1000.0, job_id="J", now=1.0)
    # claim (come il runner via API)
    c = q.claim(now=10.0)
    assert c["job_id"] == "J" and c["context"]["snapshot"]["presence"]["present"] is False
    # submit (runner) → valida + esegui
    ok = q.submit("J", c["nonce"], {"verdict": "anomalia", "severity": "warn", "message": "Nota", "action": None}, now=11.0)
    assert ok
    job = q.get("J")
    out = await execute_decision(job["decision"], job["wake"])
    assert out == "propose" and executed
    q.close()
