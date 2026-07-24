"""Slice 4b Task 3: separate chat daily cap + one-in-flight-per-conversation
guard, applied ONLY to the async subscription path (Task 2's
``_enqueue_chat_job`` branch of ``handle_chat``). The sync path (flag off) is
untouched.

Real APIs verified before writing this test (matches Task 2's report /
tests/test_chat_subscription_path.py):
- handle_chat gates on app["chat_via_subscription"] AND app["reasoning_queue"]
  present (``_bridge_on``) before taking the async branch.
- ReasoningQueue.enqueue(kind, wake, context, deadline_ts, *, job_id=None, now)
  stores context as JSON; the chat job context carries "agent_id" (NOT
  "conversation_id" -- chat_store has no separate conversation_id concept,
  confirmed in Task 1/2).
- ReasoningQueue.submit(job_id, nonce, decision, now) -> bool resolves a job
  (status -> 'decided'), the only way to make a previously-enqueued chat job
  stop counting as "in flight" (pending/claimed).

New in this task:
- ReasoningQueue.has_pending_chat(agent_id) -> bool: a kind="chat" job in
  pending/claimed state whose context_json carries this agent_id.
- ReasoningQueue.count_chat_today(now=None) -> int: kind="chat" jobs whose
  created_ts falls on the same local calendar day as `now` (defaults to
  time.time()). Takes an explicit `now` -- like every other method on this
  class (enqueue/claim/submit/sweep_expired) -- so tests don't depend on wall
  clock.
"""
import os
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, MagicMock

from hiris.app.api.handlers_chat import handle_chat
from hiris.app.chat_store import close_all_stores
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _make_agent(agent_id="test-agent"):
    agent = MagicMock()
    agent.id = agent_id
    agent.is_default = False
    agent.system_prompt = "You are a helpful assistant."
    agent.strategic_context = "Home context."
    agent.allowed_tools = None
    agent.allowed_entities = None
    agent.allowed_services = None
    agent.model = "auto"
    agent.max_tokens = 4096
    agent.type = "chat"
    agent.restrict_to_home = False
    agent.require_confirmation = False
    agent.max_chat_turns = 0
    agent.response_mode = "auto"
    agent.thinking_budget = 0
    agent.knowledge_access = {}
    return agent


def _make_app(tmp_path, *, chat_via_subscription=True, with_queue=True,
              chat_daily_cap=None, agent_id="test-agent", runner=None):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)

    agent = _make_agent(agent_id)
    engine = MagicMock()
    engine.get_agent.return_value = agent
    engine.get_default_agent.return_value = agent

    if runner is None:
        runner = AsyncMock()
        runner.chat = AsyncMock(return_value="sync reply")
        runner.last_tool_calls = []
        runner.last_thinking_blocks = []

    app = web.Application()
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["engine"] = engine
    app["data_dir"] = data_dir
    app["chat_via_subscription"] = chat_via_subscription
    if chat_daily_cap is not None:
        app["chat_daily_cap"] = chat_daily_cap

    q = None
    if with_queue:
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q

    app.router.add_post("/api/chat", handle_chat)
    return app, q, runner, agent, data_dir


# ---------------------------------------------------------------------------
# ReasoningQueue.has_pending_chat
# ---------------------------------------------------------------------------

def test_has_pending_chat_false_when_no_jobs(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    assert q.has_pending_chat("agentX") is False


def test_has_pending_chat_true_for_pending_job(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    # `now` explicit and still before deadline_ts (100.0) -- job is
    # genuinely in-flight, not merely unswept-but-expired.
    assert q.has_pending_chat("agentX", now=50.0) is True


def test_has_pending_chat_true_for_claimed_job(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    q.claim(now=2.0)
    assert q.has_pending_chat("agentX", now=50.0) is True


def test_has_pending_chat_false_after_submit_resolves_job(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    claimed = q.claim(now=2.0)
    q.submit(claimed["job_id"], claimed["nonce"], {"reply": "ciao"}, now=3.0)
    assert q.has_pending_chat("agentX") is False


def test_has_pending_chat_false_after_expiry(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    q.sweep_expired(now=200.0)
    assert q.has_pending_chat("agentX") is False


def test_has_pending_chat_scoped_to_agent_id_not_other_conversations(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    assert q.has_pending_chat("agentY") is False


def test_has_pending_chat_ignores_non_chat_kinds(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
              "severity_hint": "info", "evidence": {}, "ts": 1.0},
              {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    assert q.has_pending_chat("agentX") is False


def test_has_pending_chat_false_for_missing_agent_id(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    assert q.has_pending_chat(None) is False
    assert q.has_pending_chat("") is False


def test_has_pending_chat_false_for_expired_but_unswept_job(tmp_path):
    """Task 5 fix (Task 3 review, MEDIUM): a chat job whose deadline has
    already passed but was never swept (e.g. BRIDGE_ENABLED off, or the
    2-minute sweep just hasn't run yet) must NOT count as in-flight --
    otherwise it 409s the conversation forever with no way to clear it.
    Still status='pending' in the DB (no sweep_expired call here), but
    `now` is past its deadline_ts."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    q.enqueue("chat", {}, {"agent_id": "agentX"}, deadline_ts=100.0, now=1.0)
    # Still 'pending' in the DB -- no sweep_expired call -- but `now` (200.0)
    # is already past deadline_ts (100.0).
    assert q.has_pending_chat("agentX", now=200.0) is False



# ---------------------------------------------------------------------------
# ReasoningQueue.count_chat_today
# ---------------------------------------------------------------------------

def test_count_chat_today_zero_when_no_jobs(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    assert q.count_chat_today(now=1_700_000_000.0) == 0


def test_count_chat_today_counts_jobs_created_same_day(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0  # arbitrary anchor timestamp
    q.enqueue("chat", {}, {"agent_id": "a1"}, deadline_ts=base + 300, now=base)
    q.enqueue("chat", {}, {"agent_id": "a2"}, deadline_ts=base + 300, now=base + 60)
    assert q.count_chat_today(now=base + 120) == 2


def test_count_chat_today_excludes_other_days(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    yesterday = base - 86400
    q.enqueue("chat", {}, {"agent_id": "a1"}, deadline_ts=yesterday + 300, now=yesterday)
    q.enqueue("chat", {}, {"agent_id": "a2"}, deadline_ts=base + 300, now=base)
    assert q.count_chat_today(now=base) == 1


def test_count_chat_today_excludes_non_chat_kinds(tmp_path):
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
              "severity_hint": "info", "evidence": {}, "ts": base},
              {}, deadline_ts=base + 300, now=base)
    assert q.count_chat_today(now=base) == 0


def test_count_chat_today_counts_regardless_of_status(tmp_path):
    """The cap is about how many chat turns were enqueued today, not how many
    are still in flight -- a resolved/expired job still consumed the cap."""
    q = ReasoningQueue(str(tmp_path / "r.db"))
    base = 1_700_000_000.0
    q.enqueue("chat", {}, {"agent_id": "a1"}, deadline_ts=base + 300, now=base)
    claimed = q.claim(now=base + 1)
    q.submit(claimed["job_id"], claimed["nonce"], {"reply": "x"}, now=base + 2)
    q.enqueue("chat", {}, {"agent_id": "a2"}, deadline_ts=base + 300, now=base + 3)
    q.sweep_expired(now=base + 10_000_000)  # would expire a2 if far enough, unrelated to count
    assert q.count_chat_today(now=base) == 2


# ---------------------------------------------------------------------------
# handle_chat guards -- subscription path ONLY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_enqueue_same_conversation_returns_409(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "agent_id": agent.id})
        assert first.status == 202

        second = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert second.status == 409
        body = await second.json()
        assert body == {"error": "C'è già una risposta in arrivo per questa conversazione."}


@pytest.mark.asyncio
async def test_409_guard_scoped_per_conversation_not_global(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path)
    other_agent = _make_agent("other-agent")
    app["engine"].get_agent.side_effect = lambda aid: agent if aid == agent.id else other_agent

    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "agent_id": agent.id})
        assert first.status == 202

        other = await client.post("/api/chat", json={"message": "altra conv", "agent_id": other_agent.id})
        assert other.status == 202


@pytest.mark.asyncio
async def test_409_guard_clears_once_first_job_resolved(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "agent_id": agent.id})
        job_id = (await first.json())["job_id"]

        claimed = q.claim(now=time.time())
        q.submit(job_id, claimed["nonce"], {"reply": "ok"}, now=time.time())

        second = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert second.status == 202


@pytest.mark.asyncio
async def test_daily_cap_reached_returns_429(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_daily_cap=1)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "agent_id": agent.id})
        assert first.status == 202
        job_id = (await first.json())["job_id"]

        # Resolve the first job so the 409 in-flight guard doesn't mask the 429.
        claimed = q.claim(now=time.time())
        q.submit(job_id, claimed["nonce"], {"reply": "ok"}, now=time.time())

        second = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert second.status == 429
        body = await second.json()
        assert body == {"error": "Limite giornaliero di messaggi chat raggiunto."}


@pytest.mark.asyncio
async def test_daily_cap_default_is_generous_enough_for_normal_use(tmp_path):
    # No chat_daily_cap set on the app -> handler must fall back to a sane
    # default (50) rather than crashing or capping at 0/None.
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_daily_cap=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 202


@pytest.mark.asyncio
async def test_flag_off_guards_do_not_apply_sync_path_unchanged(tmp_path):
    """With chat_via_subscription OFF, handle_chat must use the sync path
    regardless of pending jobs or the daily cap -- guards are subscription-only."""
    app, q, runner, agent, data_dir = _make_app(
        tmp_path, chat_via_subscription=False, chat_daily_cap=0)
    # Pre-seed a "pending" chat job for this agent directly on the queue --
    # if the guard wrongly applied to the sync path this would still 409.
    q.enqueue("chat", {}, {"agent_id": agent.id}, deadline_ts=time.time() + 300, now=time.time())

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


@pytest.mark.asyncio
async def test_bridge_off_falls_back_to_sync_guards_do_not_apply(tmp_path):
    """chat_via_subscription on but bridge not wired (no reasoning_queue) ->
    existing Task 2 fallback to sync path; the new guards must not blow up
    without a queue to query."""
    app, q, runner, agent, data_dir = _make_app(
        tmp_path, chat_via_subscription=True, with_queue=False, chat_daily_cap=0)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"


@pytest.mark.asyncio
async def test_409_takes_precedence_when_both_conditions_true(tmp_path):
    """Order matters for the user-facing message: an in-flight reply for THIS
    conversation is the more specific/actionable signal, so it wins over the
    daily cap even if the cap is also exhausted."""
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_daily_cap=1)
    async with TestClient(TestServer(app)) as client:
        first = await client.post("/api/chat", json={"message": "prima", "agent_id": agent.id})
        assert first.status == 202
        # First job still pending (not resolved) AND cap (1) already consumed.
        second = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert second.status == 409
