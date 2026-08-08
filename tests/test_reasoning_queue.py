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


# ---------------------------------------------------------------------------
# ReasoningQueue.has_pending_chat -- spostati qui da test_chat_caps.py
# (fetta E4 Task 5, "un bot solo"): il metodo perde il parametro
# `chatbot_id` (c'e' UNA conversazione, non piu' una per chatbot -- "in
# flight per questo id" e "in flight" erano gia' la stessa domanda), quindi
# non c'e' piu' nulla da "scopare per agente" da testare: sono unit test
# della coda, la loro casa naturale e' qui insieme alle altre.
# I casi rimossi rispetto all'originale (has_pending_chat_scoped_to_agent_id,
# has_pending_chat_false_for_missing_agent_id,
# has_pending_chat_recognizes_legacy_agent_id_context_key) pinnavano
# esattamente lo scoping-per-id e il fallback agent_id/chatbot_id nel
# context_json che il Task 5 ha tolto: verificato che cadono per costruzione
# prima di rimuoverli (`TypeError: has_pending_chat() takes from 1 to 2
# positional arguments but 3 were given` chiamando `q.has_pending_chat(id,
# now=...)` con due argomenti posizionali contro la nuova firma).
# ---------------------------------------------------------------------------

def test_has_pending_chat_false_when_no_jobs(q):
    assert q.has_pending_chat() is False


def test_has_pending_chat_true_for_pending_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    # `now` explicit and still before deadline_ts (100.0) -- job is
    # genuinely in-flight, not merely unswept-but-expired.
    assert q.has_pending_chat(now=50.0) is True


def test_has_pending_chat_true_for_claimed_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    q.claim(now=2.0)
    assert q.has_pending_chat(now=50.0) is True


def test_has_pending_chat_false_after_submit_resolves_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    claimed = q.claim(now=2.0)
    q.submit(claimed["job_id"], claimed["nonce"], {"reply": "ciao"}, now=3.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_false_after_expiry(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    q.sweep_expired(now=200.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_ignores_non_chat_kinds(q):
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
              "severity_hint": "info", "evidence": {}, "ts": 1.0},
              {}, deadline_ts=100.0, now=1.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_false_for_expired_but_unswept_job(q):
    """Task 5 fix (Task 3 review, MEDIUM), preservato attraverso la
    semplificazione del Task 5 ("un bot solo"): un job chat il cui deadline
    e' gia' passato ma che non e' mai stato spazzato (es. BRIDGE_ENABLED
    off, o lo sweep dei 2 minuti non e' ancora girato) non deve contare come
    "in flight" -- altrimenti risponderebbe 409 per sempre senza modo di
    liberarsi. Ancora status='pending' nel DB (nessuna sweep_expired qui),
    ma `now` e' oltre il suo deadline_ts."""
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    # Still 'pending' in the DB -- no sweep_expired call -- but `now` (200.0)
    # is already past deadline_ts (100.0).
    assert q.has_pending_chat(now=200.0) is False
