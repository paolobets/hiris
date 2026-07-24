"""Slice 4b Task 2: async subscription path for handle_chat.

When ``app["chat_via_subscription"]`` is truthy AND the reasoning-queue
bridge is wired (``app["reasoning_queue"]`` present — see
``handlers_chat._bridge_on``), ``handle_chat`` must:
  1. persist the user turn to chat_store (keyed by agent_id) BEFORE
     enqueueing — otherwise a session could start on an assistant turn,
     which the Claude API rejects (contract from Task 1's report);
  2. enqueue a ``kind="chat"`` reasoning job whose context carries
     ``agent_id`` (NOT ``conversation_id`` — that's the real chat_store key,
     confirmed in Task 1);
  3. return HTTP 202 ``{"status": "pending", "job_id": ...}`` WITHOUT
     calling the runner.

Otherwise (flag off, or bridge not wired) the existing synchronous path is
unchanged — runner is called, 200 is returned.

A new ``GET /api/chat/reply/{job_id}`` route polls the same queue
(``ReasoningQueue.get``) and returns ``{"status": "pending"}`` until a
decision exists, then ``{"status": "done", "reply": ...}``.

Real APIs verified before writing this test (matches Task 1's report):
- ReasoningQueue.enqueue(kind, wake, context, deadline_ts, *, job_id=None, now)
- ReasoningQueue.get(job_id) -> dict with "kind"/"context"/"decision" (decision
  is None until ReasoningQueue.submit() has been called)
- ReasoningQueue.submit(job_id, nonce, decision, now) -> bool
- chat_store.append_messages(agent_id, messages, data_dir) /
  chat_store.load_history(agent_id, data_dir)
"""
import os
import time

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, MagicMock

from hiris.app.api.handlers_chat import handle_chat, handle_chat_reply_poll
from hiris.app.chat_store import close_all_stores, load_history
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


def _make_agent():
    agent = MagicMock()
    agent.id = "test-agent"
    agent.is_default = False
    agent.system_prompt = "You are a helpful assistant."
    agent.strategic_context = "Home context."
    agent.allowed_tools = None
    agent.allowed_entities = None
    agent.allowed_services = None
    agent.model = "auto"
    agent.max_tokens = 4096
    agent.restrict_to_home = False
    agent.require_confirmation = False
    agent.max_chat_turns = 0
    agent.response_mode = "auto"
    agent.thinking_budget = 0
    agent.knowledge_access = {}
    return agent


def _make_app(tmp_path, *, chat_via_subscription=False, with_queue=True, runner=None):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)

    agent = _make_agent()
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

    q = None
    if with_queue:
        q = ReasoningQueue(str(tmp_path / "reasoning.db"))
        app["reasoning_queue"] = q

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)
    return app, q, runner, agent, data_dir


# ---------------------------------------------------------------------------
# Flag + bridge gating
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_on_bridge_on_enqueues_pending_no_runner_call(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 202
        body = await resp.json()
        assert body["status"] == "pending"
        assert isinstance(body["job_id"], str) and body["job_id"]

    runner.chat.assert_not_called()

    job = q.get(body["job_id"])
    assert job["kind"] == "chat"
    assert job["context"]["agent_id"] == agent.id


@pytest.mark.asyncio
async def test_flag_on_bridge_off_falls_back_to_sync(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=False)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


@pytest.mark.asyncio
async def test_flag_off_uses_sync_path_even_with_bridge_on(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=False, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao", "agent_id": agent.id})
        assert resp.status == 200
        body = await resp.json()
        assert body["response"] == "sync reply"

    runner.chat.assert_called_once()


# ---------------------------------------------------------------------------
# Final-review Fix 1: max_chat_turns must be enforced BEFORE the subscription
# branch, not just on the sync path. Before the fix, an agent with a session
# turn limit chatted indefinitely once chat_via_subscription was on, because
# the check sat after the subscription branch's early return (unreachable in
# that mode).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_max_turns_reached_blocks_subscription_path(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    agent.max_chat_turns = 1
    from hiris.app.chat_store import append_messages
    append_messages(agent.id, [
        {"role": "user", "content": "prima"},
        {"role": "assistant", "content": "risposta"},
    ], data_dir)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert resp.status == 200
        body = await resp.json()
        assert body.get("error") == "max_turns_reached"
        assert body["turns"] == 1
        assert body["limit"] == 1

    runner.chat.assert_not_called()
    # Nothing must have been enqueued into the reasoning queue either.
    assert q.claim(now=time.time()) is None


@pytest.mark.asyncio
async def test_max_turns_not_reached_still_enqueues_on_subscription_path(tmp_path):
    """Sanity check: the hoisted check must not block turns that are still
    under the limit -- the subscription path must remain reachable."""
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    agent.max_chat_turns = 5
    from hiris.app.chat_store import append_messages
    append_messages(agent.id, [
        {"role": "user", "content": "prima"},
        {"role": "assistant", "content": "risposta"},
    ], data_dir)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "seconda", "agent_id": agent.id})
        assert resp.status == 202
        body = await resp.json()
        assert body["status"] == "pending"

    runner.chat.assert_not_called()


# ---------------------------------------------------------------------------
# User message persisted BEFORE enqueue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_message_persisted_before_enqueue(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "salva questo", "agent_id": agent.id})
        assert resp.status == 202

    history = load_history(agent.id, data_dir)
    assert history == [{"role": "user", "content": "salva questo"}]


@pytest.mark.asyncio
async def test_job_context_history_includes_current_user_turn(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "prima domanda", "agent_id": agent.id})
        body = await resp.json()

    job = q.get(body["job_id"])
    history = job["context"]["history"]
    assert history[-1] == {"role": "user", "content": "prima domanda"}
    # No leading assistant turn (Claude API would reject it).
    assert history[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Poll route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_pending_then_done(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

        poll1 = await client.get(f"/api/chat/reply/{job_id}")
        assert poll1.status == 200
        assert (await poll1.json()) == {"status": "pending"}

        # Simulate the external runner claiming + submitting a decision,
        # exactly like Task 1's submit path.
        claimed = q.claim(now=5.0)
        assert claimed["job_id"] == job_id
        ok = q.submit(job_id, claimed["nonce"], {"reply": "ecco la risposta"}, now=6.0)
        assert ok is True

        poll2 = await client.get(f"/api/chat/reply/{job_id}")
        assert poll2.status == 200
        assert (await poll2.json()) == {"status": "done", "reply": "ecco la risposta"}


@pytest.mark.asyncio
async def test_poll_route_unknown_job_id_404(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chat/reply/does-not-exist")
        assert resp.status == 404


# ---------------------------------------------------------------------------
# Poll route: terminal states (Task 2, Fix 2) -- an expired job, a failed
# job, or a decided job whose decision carries no usable reply (Task 1's
# chat_reply_skipped outcome) must all poll as a TERMINAL error, never as
# pending-forever. Only genuinely still-in-flight jobs poll as "pending".
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_route_expired_job_returns_error_not_pending(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

        # Simulate the ponte-push sweep expiring the job (deadline passed,
        # no runner ever claimed/submitted it).
        q.sweep_expired(now=time.time() + 10 * 60)
        assert q.get(job_id)["status"] == "expired"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"
        assert "message" in body and body["message"]


@pytest.mark.asyncio
async def test_poll_route_failed_job_returns_error_not_pending(tmp_path):
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

    # ReasoningQueue has no public API to force status='failed' directly;
    # write it through the same connection the queue already owns so this
    # test doesn't depend on internal column layout beyond the 'status' field
    # documented in reasoning/queue.py's _row().
    with q._lock:
        q._conn.execute("UPDATE reasoning_jobs SET status='failed' WHERE job_id=?", (job_id,))
        q._conn.commit()

    async with TestClient(TestServer(app)) as client:
        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"


@pytest.mark.asyncio
async def test_poll_route_decided_without_usable_reply_returns_error(tmp_path):
    """Mirrors Task 1's chat_reply_skipped outcome: the job reached
    'decided' but the decision carries no truthy 'reply' (e.g. the runner's
    decision was empty/garbage). The UI must stop polling, not spin forever."""
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        ok = q.submit(job_id, claimed["nonce"], {"message": "no reply field here"}, now=6.0)
        assert ok is True
        assert q.get(job_id)["status"] == "decided"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        body = await poll.json()
        assert body["status"] == "error"


@pytest.mark.asyncio
async def test_poll_route_pending_job_still_returns_pending(tmp_path):
    """Sanity check: a genuinely in-flight job (not yet claimed) still polls
    as pending -- the terminal-state handling must not regress this."""
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        assert (await poll.json()) == {"status": "pending"}


@pytest.mark.asyncio
async def test_poll_route_claimed_job_still_returns_pending(tmp_path):
    """A job claimed by the external runner but not yet submitted is still
    in-flight -- must poll as pending, not error."""
    app, q, runner, agent, data_dir = _make_app(tmp_path, chat_via_subscription=True, with_queue=True)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "domanda", "agent_id": agent.id})
        job_id = (await resp.json())["job_id"]

        claimed = q.claim(now=5.0)
        assert claimed["job_id"] == job_id
        assert q.get(job_id)["status"] == "claimed"

        poll = await client.get(f"/api/chat/reply/{job_id}")
        assert poll.status == 200
        assert (await poll.json()) == {"status": "pending"}


# ---------------------------------------------------------------------------
# Task 5: server.py wiring -- the addon option only takes effect when the
# bridge is ALSO truly usable (BRIDGE_ENABLED), otherwise chat jobs would be
# enqueued into a queue nothing sweeps/claims/prunes -> eternal pending + DB
# growth (the queue itself is created unconditionally in _on_startup, so
# handlers_chat._bridge_on's "queue present" check alone can't catch this).
#
# Full _on_startup is HA-client/engine/mqtt-heavy and out of scope for a unit
# test here -- verified at the source level instead, same convention as
# test_coverage_wiring.py's test_coverage_review_runs_before_bridge_enabled_branch
# and test_suggestion_store_instantiated_in_server_source (both README'd as
# "runtime wiring verified separately via manual/integration checks").
# ---------------------------------------------------------------------------

def test_chat_via_subscription_wiring_requires_bridge_enabled_in_source():
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'app["chat_via_subscription"] =' in src
    # The assigned expression must combine the CHAT_VIA_SUBSCRIPTION config
    # read with a BRIDGE_ENABLED check -- not the config flag alone.
    assign_pos = src.index('app["chat_via_subscription"] =')
    tail = src[assign_pos:assign_pos + 400]
    assert "CHAT_VIA_SUBSCRIPTION" in tail or "_chat_via_subscription_cfg" in tail
    assert "_bridge_enabled" in tail or "BRIDGE_ENABLED" in tail


def test_chat_via_subscription_env_var_read_same_convention_as_bridge_enabled():
    """CHAT_VIA_SUBSCRIPTION must be parsed with the exact same truthy-string
    convention used everywhere else in this module for boolean env vars
    (BRIDGE_ENABLED, BRIDGE_FALLBACK, SENTINEL_ALLOW_GREEN_AUTO, ...) --
    '1'/'true'/'yes'/'on' -- so ops behavior is consistent across knobs."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assert 'os.environ.get("CHAT_VIA_SUBSCRIPTION", "0") in ("1", "true", "yes", "on")' in src


@pytest.mark.parametrize("cfg,bridge,expected", [
    (True, True, True),
    (True, False, False),
    (False, True, False),
    (False, False, False),
])
def test_chat_via_subscription_gate_truth_table(cfg, bridge, expected):
    """Final-review Fix 2: exercises the REAL gate combinator
    (``server._chat_subscription_active``), not a hand-copied truth table --
    so an ``and`` -> ``or`` regression in the actual function fails this
    test. Config flag alone must NEVER activate the async path when the
    bridge (BRIDGE_ENABLED) is off, and vice versa."""
    from hiris.app.server import _chat_subscription_active

    assert _chat_subscription_active(cfg, bridge) is expected


def test_on_startup_wires_chat_via_subscription_through_the_real_gate_function():
    """Complements the truth-table test above: pins that _on_startup's
    wiring point actually CALLS _chat_subscription_active rather than
    reimplementing the boolean logic inline (where an ``and``->``or``
    regression would be invisible to the truth-table test, which only
    exercises the extracted function directly)."""
    import inspect
    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    assign_pos = src.index('app["chat_via_subscription"] =')
    line_end = src.index("\n", assign_pos)
    assert "_chat_subscription_active(" in src[assign_pos:line_end]
