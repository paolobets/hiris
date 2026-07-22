import pytest
from hiris.app.reasoning.queue import ReasoningQueue

@pytest.fixture
def q(tmp_path):
    x = ReasoningQueue(str(tmp_path / "r.db")); yield x; x.close()

def test_enqueue_claim_oldest_first(q):
    a = q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {"x": 1}}, deadline_ts=100.0, job_id="A", now=1.0)
    b = q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {"x": 2}}, deadline_ts=100.0, job_id="B", now=2.0)
    c = q.claim(now=10.0)
    assert c["job_id"] == "A" and c["nonce"] and c["context"]["snapshot"]["x"] == 1
    c2 = q.claim(now=10.0)
    assert c2["job_id"] == "B"
    assert q.claim(now=10.0) is None  # nessun altro pending

def test_claim_skips_expired(q):
    q.enqueue("holistic", {}, {}, deadline_ts=5.0, job_id="OLD", now=1.0)
    assert q.claim(now=10.0) is None  # già scaduto → non claimabile

def test_submit_valid_and_nonce_rules(q):
    q.enqueue("holistic", {"signal_kind": "holistic"}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    c = q.claim(now=10.0)
    assert q.submit("J", "wrong-nonce", {"verdict": "anomalia"}, now=11.0) is False
    assert q.submit("J", c["nonce"], {"verdict": "anomalia", "message": "ok"}, now=11.0) is True
    # doppia submit rifiutata (non più 'claimed')
    assert q.submit("J", c["nonce"], {"verdict": "anomalia"}, now=12.0) is False
    assert q.get("J")["status"] == "decided"

def test_submit_expired_rejected(q):
    q.enqueue("holistic", {}, {}, deadline_ts=20.0, job_id="J", now=1.0)
    c = q.claim(now=10.0)
    assert q.submit("J", c["nonce"], {"verdict": "anomalia"}, now=25.0) is False  # scaduto

def test_sweep_expired_marks_and_returns(q):
    q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {}}, deadline_ts=5.0, job_id="E", now=1.0)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="LIVE", now=1.0)
    swept = q.sweep_expired(now=10.0)
    assert [s["job_id"] for s in swept] == ["E"]
    assert q.get("E")["status"] == "expired"
    assert q.get("LIVE")["status"] == "pending"
    assert q.sweep_expired(now=10.0) == []  # già marcato

def test_prune(q):
    q.enqueue("holistic", {}, {}, deadline_ts=5.0, job_id="E", now=1.0)
    q.sweep_expired(now=10.0)
    assert q.prune(before_ts=100.0) == 1
    assert q.get("E") is None
