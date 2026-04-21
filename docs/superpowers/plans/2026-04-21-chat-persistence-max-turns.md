# Chat Persistence & Max Turns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-side chat history persistence per agent and a configurable max-messages-per-session limit for chat agents.

**Architecture:** A new standalone `chat_store.py` module handles file I/O for history (one JSON file per agent in `/data/`). `handlers_chat.py` is modified to load/save history from the store instead of trusting the client-sent array. A new `handlers_chat_history.py` exposes GET/DELETE endpoints for the frontend to load history on agent selection and clear it on "Nuova conversazione".

**Tech Stack:** Python 3.11, aiohttp, JSON files (atomic write), vanilla JS in existing index.html/config.html.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `hiris/app/chat_store.py` | Load/append/clear per-agent history JSON files |
| Create | `hiris/app/api/handlers_chat_history.py` | GET + DELETE /api/agents/{id}/chat-history |
| Create | `tests/test_chat_store.py` | Unit tests for chat_store |
| Create | `tests/test_handlers_chat_history.py` | Unit tests for history endpoints |
| Modify | `hiris/app/agent_engine.py` | Add `max_chat_turns: int = 0` field to Agent |
| Modify | `hiris/app/server.py` | Add `app["data_dir"]`, import + register new routes |
| Modify | `hiris/app/api/handlers_chat.py` | Use server history, check max turns, persist exchange |
| Modify | `hiris/app/static/index.html` | Load history on agent select, turn counter, new conversation |
| Modify | `hiris/app/static/config.html` | `max_chat_turns` field for chat agents |
| Modify | `tests/test_api.py` | Add `data_dir` to fixture, update version, update chat tests |
| Modify | `hiris/app/server.py` | Version bump 0.1.6 → 0.1.7 |

---

## Task 1: `chat_store.py` — History file I/O module

**Files:**
- Create: `hiris/app/chat_store.py`
- Create: `tests/test_chat_store.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/test_chat_store.py`:

```python
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from hiris.app.chat_store import load_history, append_messages, clear_history, _path


def test_load_history_returns_empty_when_no_file(tmp_path):
    result = load_history("agent1", str(tmp_path))
    assert result == []


def test_append_and_load_roundtrip(tmp_path):
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    append_messages("agent1", msgs, str(tmp_path))
    loaded = load_history("agent1", str(tmp_path))
    assert loaded == msgs


def test_load_strips_timestamps_from_output(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "test"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert "timestamp" not in result[0]


def test_load_filters_messages_older_than_30_days(tmp_path):
    path = _path("agent1", str(tmp_path))
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "schema_version": 1, "agent_id": "agent1",
        "messages": [
            {"role": "user", "content": "old", "timestamp": old_ts},
            {"role": "assistant", "content": "new", "timestamp": new_ts},
        ]
    }
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    result = load_history("agent1", str(tmp_path))
    assert len(result) == 1
    assert result[0]["content"] == "new"


def test_append_messages_accumulates(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "first"}], str(tmp_path))
    append_messages("agent1", [{"role": "assistant", "content": "second"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert len(result) == 2
    assert result[0]["content"] == "first"
    assert result[1]["content"] == "second"


def test_clear_history_removes_file(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "x"}], str(tmp_path))
    clear_history("agent1", str(tmp_path))
    assert load_history("agent1", str(tmp_path)) == []


def test_clear_history_noop_when_no_file(tmp_path):
    clear_history("agent1", str(tmp_path))  # must not raise


def test_load_history_returns_empty_on_corrupt_file(tmp_path):
    path = _path("agent1", str(tmp_path))
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w") as f:
        f.write("not json{{{")
    result = load_history("agent1", str(tmp_path))
    assert result == []


def test_different_agents_have_separate_histories(tmp_path):
    append_messages("agent-a", [{"role": "user", "content": "for A"}], str(tmp_path))
    append_messages("agent-b", [{"role": "user", "content": "for B"}], str(tmp_path))
    assert load_history("agent-a", str(tmp_path))[0]["content"] == "for A"
    assert load_history("agent-b", str(tmp_path))[0]["content"] == "for B"
```

- [ ] **Step 1.2: Run tests — expect failure**

```bash
cd /c/Work/Sviluppo/hiris/.claude/worktrees/busy-nash-eca7c9
python -m pytest tests/test_chat_store.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'hiris.app.chat_store'`

- [ ] **Step 1.3: Implement `chat_store.py`**

Create `hiris/app/chat_store.py`:

```python
import json
import os
from datetime import datetime, timezone, timedelta

HISTORY_RETENTION_DAYS = 30
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _path(agent_id: str, data_dir: str) -> str:
    return os.path.join(data_dir, f"chat_history_{agent_id}.json")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime(_TS_FMT)


def _load_raw(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("messages", [])
    except Exception:
        return []


def load_history(agent_id: str, data_dir: str) -> list[dict]:
    """Return [{role, content}] for Claude API, filtered to last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
    result = []
    for m in _load_raw(_path(agent_id, data_dir)):
        ts = m.get("timestamp", "")
        try:
            msg_dt = datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)
            if msg_dt < cutoff:
                continue
        except (ValueError, TypeError):
            pass
        result.append({"role": m["role"], "content": m["content"]})
    return result


def append_messages(agent_id: str, messages: list[dict], data_dir: str) -> None:
    """Append [{role, content}] with current timestamp and save atomically."""
    path = _path(agent_id, data_dir)
    raw = _load_raw(path)
    ts = _now_ts()
    for m in messages:
        raw.append({"role": m["role"], "content": m["content"], "timestamp": ts})
    _write(agent_id, raw, path, data_dir)


def clear_history(agent_id: str, data_dir: str) -> None:
    """Delete the history file for the given agent."""
    try:
        os.remove(_path(agent_id, data_dir))
    except FileNotFoundError:
        pass


def _write(agent_id: str, raw_messages: list[dict], path: str, data_dir: str) -> None:
    os.makedirs(data_dir, exist_ok=True)
    data = {"schema_version": 1, "agent_id": agent_id, "messages": raw_messages}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
```

- [ ] **Step 1.4: Run tests — expect all pass**

```bash
python -m pytest tests/test_chat_store.py -v
```

Expected: 9 tests PASSED

- [ ] **Step 1.5: Commit**

```bash
git add hiris/app/chat_store.py tests/test_chat_store.py
git commit -m "feat: add chat_store module for per-agent history persistence"
```

---

## Task 2: Add `max_chat_turns` to Agent dataclass

**Files:**
- Modify: `hiris/app/agent_engine.py`

- [ ] **Step 2.1: Add field to Agent dataclass**

In `hiris/app/agent_engine.py`, find the `Agent` dataclass (line 20). Add after `budget_eur_limit`:

```python
    budget_eur_limit: float = 0.0
    max_chat_turns: int = 0
```

- [ ] **Step 2.2: Add to `UPDATABLE_FIELDS`**

Find `UPDATABLE_FIELDS` (around line 196). Add `"max_chat_turns"`:

```python
    UPDATABLE_FIELDS = {
        "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
        "strategic_context", "allowed_entities", "allowed_services",
        "model", "max_tokens", "restrict_to_home", "require_confirmation",
        "actions", "budget_eur_limit", "max_chat_turns",
    }
```

- [ ] **Step 2.3: Add to `_load()` deserialization**

In `_load()`, find the `Agent(...)` constructor call (around line 88). Add after `budget_eur_limit`:

```python
                    budget_eur_limit=raw.get("budget_eur_limit", 0.0),
                    max_chat_turns=int(raw.get("max_chat_turns", 0)),
```

- [ ] **Step 2.4: Add to `create_agent()`**

In `create_agent()` (around line 166), add after `budget_eur_limit`:

```python
            budget_eur_limit=float(data.get("budget_eur_limit", 0.0)),
            max_chat_turns=int(data.get("max_chat_turns", 0)),
```

- [ ] **Step 2.5: Add `"max_chat_turns"` to `_INT_FIELDS` in `update_agent()`**

In `update_agent()` (around line 202), add `_INT_FIELDS`:

```python
        _BOOL_FIELDS = {"restrict_to_home", "require_confirmation"}
        _FLOAT_FIELDS = {"budget_eur_limit"}
        _INT_FIELDS = {"max_chat_turns"}
        for key in self.UPDATABLE_FIELDS:
            if key in data:
                if key in _BOOL_FIELDS:
                    setattr(agent, key, bool(data[key]))
                elif key in _FLOAT_FIELDS:
                    setattr(agent, key, float(data[key]))
                elif key in _INT_FIELDS:
                    setattr(agent, key, int(data[key]))
                else:
                    setattr(agent, key, data[key])
```

- [ ] **Step 2.6: Run existing tests to verify no regressions**

```bash
python -m pytest tests/test_agent_engine.py -v
```

Expected: all PASSED

- [ ] **Step 2.7: Commit**

```bash
git add hiris/app/agent_engine.py
git commit -m "feat: add max_chat_turns field to Agent dataclass"
```

---

## Task 3: `server.py` — expose `data_dir`, register new routes

**Files:**
- Modify: `hiris/app/server.py`

- [ ] **Step 3.1: Add `data_dir` to app in `_on_startup`**

In `_on_startup` (around line 45), after `data_path = os.environ.get(...)`, add:

```python
    data_path = os.environ.get("AGENTS_DATA_PATH", "/data/agents.json")
    app["data_dir"] = os.path.dirname(os.path.abspath(data_path))
    engine = AgentEngine(ha_client=ha_client, data_path=data_path)
```

- [ ] **Step 3.2: Import new handler**

At the top of `server.py`, add the import after the existing handler imports:

```python
from .api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history
```

- [ ] **Step 3.3: Register new routes in `create_app()`**

In `create_app()`, after the existing agent routes, add:

```python
    app.router.add_get("/api/agents/{agent_id}/chat-history", handle_get_chat_history)
    app.router.add_delete("/api/agents/{agent_id}/chat-history", handle_clear_chat_history)
```

- [ ] **Step 3.4: Run health check to verify app starts**

```bash
python -m pytest tests/test_api.py::test_health_endpoint -v
```

Expected: the test will fail because `handlers_chat_history` doesn't exist yet — that is correct for now. Skip if you get ImportError; we will fix in Task 4.

- [ ] **Step 3.5: Commit**

```bash
git add hiris/app/server.py
git commit -m "feat: expose data_dir in app context, register chat-history routes"
```

---

## Task 4: `handlers_chat_history.py` — GET + DELETE endpoints

**Files:**
- Create: `hiris/app/api/handlers_chat_history.py`
- Create: `tests/test_handlers_chat_history.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_handlers_chat_history.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_chat_history import handle_get_chat_history, handle_clear_chat_history


def _make_app(data_dir: str) -> MagicMock:
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: data_dir if k == "data_dir" else None)
    return app


@pytest.mark.asyncio
async def test_get_chat_history_returns_messages(tmp_path):
    from hiris.app.chat_store import append_messages
    append_messages("agent-x", [{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request("GET", "/api/agents/agent-x/chat-history", app=app)
    request.match_info = {"agent_id": "agent-x"}

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == [{"role": "user", "content": "ciao"}]


@pytest.mark.asyncio
async def test_get_chat_history_empty_when_no_file(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request("GET", "/api/agents/missing/chat-history", app=app)
    request.match_info = {"agent_id": "missing"}

    resp = await handle_get_chat_history(request)
    data = json.loads(resp.body)
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_clear_chat_history_removes_messages(tmp_path):
    from hiris.app.chat_store import append_messages, load_history
    append_messages("agent-x", [{"role": "user", "content": "ciao"}], str(tmp_path))

    app = _make_app(str(tmp_path))
    request = make_mocked_request("DELETE", "/api/agents/agent-x/chat-history", app=app)
    request.match_info = {"agent_id": "agent-x"}

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
    assert load_history("agent-x", str(tmp_path)) == []


@pytest.mark.asyncio
async def test_clear_chat_history_noop_when_no_file(tmp_path):
    app = _make_app(str(tmp_path))
    request = make_mocked_request("DELETE", "/api/agents/missing/chat-history", app=app)
    request.match_info = {"agent_id": "missing"}

    resp = await handle_clear_chat_history(request)
    data = json.loads(resp.body)
    assert data["ok"] is True
```

- [ ] **Step 4.2: Run tests — expect failure**

```bash
python -m pytest tests/test_handlers_chat_history.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'hiris.app.api.handlers_chat_history'`

- [ ] **Step 4.3: Implement `handlers_chat_history.py`**

Create `hiris/app/api/handlers_chat_history.py`:

```python
import logging
from aiohttp import web
from ..chat_store import load_history, clear_history

logger = logging.getLogger(__name__)


async def handle_get_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    data_dir = request.app["data_dir"]
    messages = load_history(agent_id, data_dir)
    return web.json_response({"messages": messages})


async def handle_clear_chat_history(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    data_dir = request.app["data_dir"]
    clear_history(agent_id, data_dir)
    return web.json_response({"ok": True})
```

- [ ] **Step 4.4: Run tests — expect all pass**

```bash
python -m pytest tests/test_handlers_chat_history.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 4.5: Commit**

```bash
git add hiris/app/api/handlers_chat_history.py tests/test_handlers_chat_history.py
git commit -m "feat: add GET/DELETE /api/agents/{id}/chat-history endpoints"
```

---

## Task 5: Modify `handlers_chat.py` — server history + max turns

**Files:**
- Modify: `hiris/app/api/handlers_chat.py`
- Modify: `tests/test_api.py`

- [ ] **Step 5.1: Update `test_api.py` — add `data_dir` to fixture and add new test**

In `tests/test_api.py`, update the `client` fixture to add `app["data_dir"]`:

```python
@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Test response")
    mock_runner.last_tool_calls = []
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)

    app.on_startup.clear()
    app.on_cleanup.clear()

    return await aiohttp_client(app)
```

Also update `test_health_endpoint` version string from `"0.1.6"` to `"0.1.7"`:

```python
    assert data["version"] == "0.1.7"
```

Add a new test at the end of the file:

```python
@pytest.mark.asyncio
async def test_chat_max_turns_blocks_when_limit_reached(client):
    from hiris.app.agent_engine import Agent
    from hiris.app.chat_store import append_messages
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._agents["agent-limited"] = Agent(
        id="agent-limited", name="Limited", type="chat",
        trigger={"type": "manual"},
        system_prompt="test",
        allowed_tools=[], enabled=True, is_default=False,
        max_chat_turns=2,
    )
    # Pre-fill 2 user turns
    append_messages("agent-limited", [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply2"},
    ], data_dir)

    resp = await client.post("/api/chat", json={
        "message": "third message",
        "agent_id": "agent-limited",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data.get("error") == "max_turns_reached"
    assert data["turns"] == 2
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_chat_persists_exchange_in_history(client):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    from hiris.app.chat_store import load_history
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"},
        system_prompt="test",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="stored response")

    await client.post("/api/chat", json={"message": "persist me"})

    history = load_history(DEFAULT_AGENT_ID, data_dir)
    assert any(m["content"] == "persist me" for m in history)
    assert any(m["content"] == "stored response" for m in history)
```

- [ ] **Step 5.2: Run tests — expect failures on new tests**

```bash
python -m pytest tests/test_api.py::test_chat_max_turns_blocks_when_limit_reached tests/test_api.py::test_chat_persists_exchange_in_history -v
```

Expected: both FAIL (handler not yet changed)

- [ ] **Step 5.3: Rewrite `handlers_chat.py`**

Replace the entire content of `hiris/app/api/handlers_chat.py`:

```python
import logging

from aiohttp import web

from ..chat_store import load_history, append_messages

logger = logging.getLogger(__name__)


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message required"}, status=400)

    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response(
            {"error": "Claude runner not configured — set CLAUDE_API_KEY"}, status=503
        )

    agent_id = body.get("agent_id")
    data_dir = request.app.get("data_dir", "/data")
    engine = request.app["engine"]

    agent = None
    if agent_id:
        agent = engine.get_agent(agent_id)
    if agent is None:
        agent = engine.get_default_agent()

    effective_agent_id = getattr(agent, "id", None) if agent else None

    # Load server-side history (client-sent history field is ignored)
    history = load_history(effective_agent_id, data_dir) if effective_agent_id else []

    # Enforce max turns limit
    max_turns = getattr(agent, "max_chat_turns", 0) if agent else 0
    if max_turns > 0:
        turn_count = sum(1 for m in history if m["role"] == "user")
        if turn_count >= max_turns:
            return web.json_response({
                "error": "max_turns_reached",
                "turns": turn_count,
                "limit": max_turns,
            })

    if agent:
        if agent.strategic_context:
            system_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
        else:
            system_prompt = agent.system_prompt or (
                "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
            )
        allowed_tools = agent.allowed_tools or None
        allowed_entities = agent.allowed_entities or None
        allowed_services = agent.allowed_services or None
    else:
        logger.warning("No agent found (requested: %s). Using fallback prompt.", agent_id)
        system_prompt = "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente."
        allowed_tools = None
        allowed_entities = None
        allowed_services = None

    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    agent_type = getattr(agent, "type", "chat") if agent else "chat"
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False

    response = await runner.chat(
        user_message=message,
        system_prompt=system_prompt,
        conversation_history=history,
        allowed_tools=allowed_tools,
        allowed_entities=allowed_entities,
        allowed_services=allowed_services,
        model=agent_model,
        max_tokens=agent_max_tokens,
        agent_type=agent_type,
        restrict_to_home=agent_restrict,
        require_confirmation=agent_require_confirmation,
        agent_id=effective_agent_id,
    )

    # Persist the new user+assistant exchange
    if effective_agent_id:
        append_messages(effective_agent_id, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response},
        ], data_dir)

    raw = getattr(runner, "last_tool_calls", None)
    tools_called = raw if isinstance(raw, list) else []
    return web.json_response({"response": response, "debug": {"tools_called": tools_called}})
```

- [ ] **Step 5.4: Run all tests — expect all pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: all PASSED (including the two new tests)

- [ ] **Step 5.5: Commit**

```bash
git add hiris/app/api/handlers_chat.py tests/test_api.py
git commit -m "feat: handlers_chat uses server-side history and enforces max_chat_turns"
```

---

## Task 6: `index.html` — history load, turn counter, new conversation button

**Files:**
- Modify: `hiris/app/static/index.html`

**Overview of JS changes:**
- Remove `histories` dict and `currentHistory()` function (no longer needed)
- Add `agentMaxTurns` and `agentTurnCounts` dicts
- Modify `setActiveAgent` to fetch history from server
- Add `updateTurnCounter()` and `checkTurnLimit()` helpers
- Modify `sendMessage` to update counter + check limit (remove old history tracking)
- Add "Nuova conversazione" button in header
- Add turn counter element below input box

- [ ] **Step 6.1: Add "Nuova conversazione" button to chat header**

In `index.html`, find the element with `id="header-title"`. The header area currently has something like:
```html
<div ... id="header-title">HIRIS</div>
```

Add a "Nuova conversazione" button immediately after the header title element. Search for `id="header-title"` and add after its closing tag:

```html
<button id="new-conv-btn" onclick="clearConversation()" title="Nuova conversazione" style="
  background:none; border:1px solid var(--border); border-radius:6px; padding:3px 10px;
  color:var(--text-muted); font-size:12px; cursor:pointer; white-space:nowrap;
  transition:background 0.15s, color 0.15s;
" onmouseover="this.style.background='var(--surface-hover)';this.style.color='var(--text)'"
   onmouseout="this.style.background='none';this.style.color='var(--text-muted)'">
  &#x21BA; Nuova conv.
</button>
```

- [ ] **Step 6.2: Add turn counter element below the input box**

Find the `<textarea>` input element (`id="input-box"` or similar — search for `id="chat-input"` or the send button). Below the input row, add:

```html
<div id="turn-counter" style="display:none; font-size:11px; text-align:right; padding:2px 4px 0 0; color:var(--text-muted)"></div>
<div id="session-ended-msg" style="display:none; font-size:12px; text-align:center; padding:6px; color:var(--conn-off); background:var(--surface); border-top:1px solid var(--border)">
  Sessione completata — avvia una nuova conversazione
</div>
```

- [ ] **Step 6.3: Replace JS history tracking with server-driven logic**

In the `<script>` section of `index.html`:

**Remove** these lines (find and delete them):
```javascript
var histories = {};
function currentHistory() {
  if (!histories[activeAgentId]) histories[activeAgentId] = [];
  return histories[activeAgentId];
}
```

**Add** these new variables and functions right after `var activeAgentId = null;` (or near the other var declarations at the top of the script):

```javascript
var agentMaxTurns = {};
var agentTurnCounts = {};

function updateTurnCounter() {
  var counter = document.getElementById('turn-counter');
  var max = agentMaxTurns[activeAgentId] || 0;
  if (!activeAgentId || max === 0) { counter.style.display = 'none'; return; }
  var current = agentTurnCounts[activeAgentId] || 0;
  counter.style.display = '';
  counter.textContent = current + ' / ' + max + ' messaggi';
  counter.style.color = current >= max ? 'var(--conn-off)' : 'var(--text-muted)';
}

function checkTurnLimit() {
  var max = agentMaxTurns[activeAgentId] || 0;
  var sessionMsg = document.getElementById('session-ended-msg');
  if (max === 0) {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    if (sessionMsg) sessionMsg.style.display = 'none';
    return;
  }
  var current = agentTurnCounts[activeAgentId] || 0;
  var reached = current >= max;
  inputEl.disabled = reached;
  sendBtn.disabled = reached;
  if (sessionMsg) sessionMsg.style.display = reached ? '' : 'none';
}

async function clearConversation() {
  if (!activeAgentId) return;
  try {
    await fetch('api/agents/' + activeAgentId + '/chat-history', { method: 'DELETE' });
  } catch(e) {}
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = '';
  hasMessages = false;
  agentTurnCounts[activeAgentId] = 0;
  updateTurnCounter();
  checkTurnLimit();
}
```

- [ ] **Step 6.4: Update `loadAgents` to store `max_chat_turns`**

In `loadAgents`, find where each agent `a` is processed. After iterating through agents, store the max_chat_turns. Find the line `chatAgents.forEach(function(a) {` and inside that callback, add:

```javascript
      agentMaxTurns[a.id] = a.max_chat_turns || 0;
```

- [ ] **Step 6.5: Update `setActiveAgent` to load history from server**

Replace the existing `setActiveAgent` function with:

```javascript
async function setActiveAgent(agentId, agentName) {
  if (agentId === activeAgentId) return;
  activeAgentId = agentId;
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = '';
  hasMessages = false;
  document.getElementById('header-title').textContent = agentName;
  agentTurnCounts[agentId] = 0;
  updateTurnCounter();
  checkTurnLimit();
  try {
    var r = await fetch('api/agents/' + agentId + '/chat-history');
    if (r.ok) {
      var data = await r.json();
      var msgs = data.messages || [];
      msgs.forEach(function(m) {
        appendMsg(m.role === 'user' ? 'user' : 'assistant', m.content);
      });
      agentTurnCounts[agentId] = msgs.filter(function(m) { return m.role === 'user'; }).length;
      updateTurnCounter();
      checkTurnLimit();
    }
  } catch(e) {}
  loadAgents();
}
```

- [ ] **Step 6.6: Update `sendMessage` — remove old history tracking, add counter update**

Replace the existing `sendMessage` function with:

```javascript
async function sendMessage(text) {
  text = (text !== undefined) ? text : inputEl.value.trim();
  if (!text) return;
  inputEl.value = '';
  autoResize();
  sendBtn.disabled = true;
  appendMsg('user', text);
  var typing = showTyping();
  try {
    var r = await fetch('api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: text,
        agent_id: activeAgentId,
      }),
    });
    var data = await r.json();
    typing.remove();
    if (data.error === 'max_turns_reached') {
      appendMsg('assistant', 'Sessione completata. Avvia una nuova conversazione.');
      checkTurnLimit();
      return;
    }
    appendMsg('assistant', data.response || data.error || 'Errore sconosciuto');
    if (data.debug && data.debug.tools_called && data.debug.tools_called.length > 0) {
      appendDebug(data.debug.tools_called);
    }
    agentTurnCounts[activeAgentId] = (agentTurnCounts[activeAgentId] || 0) + 1;
    updateTurnCounter();
    checkTurnLimit();
  } catch(e) {
    typing.remove();
    appendMsg('assistant', 'Errore di connessione. Riprova tra poco.');
  }
  if (!inputEl.disabled) {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}
```

- [ ] **Step 6.7: Commit**

```bash
git add hiris/app/static/index.html
git commit -m "feat: load chat history from server, add turn counter and new conversation button"
```

---

## Task 7: `config.html` — `max_chat_turns` field for chat agents

**Files:**
- Modify: `hiris/app/static/config.html`

- [ ] **Step 7.1: Add `max_chat_turns` HTML input in "Modello AI" fieldset**

In `config.html`, find the line with `id="f-max-tokens"` (around line 606):

```html
          <input type="number" id="f-max-tokens" value="4096" min="256" max="16000">
          <p class="hint">Limita la lunghezza massima della risposta. Default: 4096.</p>
```

After that `<p class="hint">`, add:

```html
          <div id="max-turns-row" style="display:none">
            <label>Max messaggi per sessione</label>
            <input type="number" id="f-max-chat-turns" value="0" min="0" max="9999">
            <p class="hint">Numero massimo di scambi in una sessione chat. 0 = illimitato. Visibile all&apos;utente sotto il box di input.</p>
          </div>
```

- [ ] **Step 7.2: Show/hide `max-turns-row` based on agent type**

In `config.html`, find the JS function that handles type changes (look for `f-type` select or wherever the agent type is set). There should be a section that shows/hides certain fieldsets based on type.

Find where the form is shown/populated for an agent (around the `loadAgent` or `showAgent` function, near line 987). Add visibility control:

```javascript
      // Show max_chat_turns only for chat agents
      var maxTurnsRow = document.getElementById('max-turns-row');
      if (maxTurnsRow) {
        maxTurnsRow.style.display = (a.type === 'chat') ? '' : 'none';
      }
      document.getElementById('f-max-chat-turns').value = a.max_chat_turns || 0;
```

Also add the same show/hide in the "new agent" form reset (near line 1023, find the reset block):

```javascript
      if (document.getElementById('max-turns-row')) {
        document.getElementById('max-turns-row').style.display = 'none';
      }
      document.getElementById('f-max-chat-turns').value = 0;
```

Also add a listener on the type `<select>` change (find `id="f-type"` change handler, or add one):

```javascript
      document.getElementById('f-type').addEventListener('change', function() {
        var maxTurnsRow = document.getElementById('max-turns-row');
        if (maxTurnsRow) {
          maxTurnsRow.style.display = this.value === 'chat' ? '' : 'none';
        }
      });
```

- [ ] **Step 7.3: Include `max_chat_turns` in form save payload**

Find the object literal passed to the save API call (around line 1055, where `model`, `max_tokens`, etc. are collected). Add:

```javascript
        max_chat_turns: parseInt(document.getElementById('f-max-chat-turns').value) || 0,
```

- [ ] **Step 7.4: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "feat: add max_chat_turns field to agent designer for chat agents"
```

---

## Task 8: Version bump + full test suite

**Files:**
- Modify: `hiris/app/server.py`
- Modify: `tests/test_api.py` (already updated in Task 5)

- [ ] **Step 8.1: Bump version in `server.py`**

Find `"version": "0.1.6"` in `_handle_health` and update to `"0.1.7"`.

- [ ] **Step 8.2: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASSED, no errors.

If `test_health_endpoint` fails on version: you already updated it in Task 5 — check the file.

- [ ] **Step 8.3: Final commit**

```bash
git add hiris/app/server.py
git commit -m "chore: bump version to 0.1.7"
```

---

## Self-Review Notes

- `chat_store._path` is exported for use in tests (prefixed with `_` but imported directly — acceptable for test use)
- `test_api.py` fixture adds `app["data_dir"] = str(tmp_path)` — the existing `test_chat_no_runner` test creates its own app without going through the fixture; it doesn't call `handle_chat` with an agent_id so `data_dir` is not needed in that test (handler falls back to `"/data"` via `request.app.get("data_dir", "/data")`)
- `handlers_chat.py` uses `request.app.get("data_dir", "/data")` not `request.app["data_dir"]` — this prevents a `KeyError` in tests that don't set `data_dir`
- The frontend `sendMessage` no longer sends `history` in the request body — the backend ignores any `history` field anyway (it was never used after this change), so old clients are backward compatible
- `setActiveAgent` is now `async` — ensure the `onclick` handler in the agent list uses it correctly (JS `async function` in onclick works fine; the browser won't await it but that is acceptable for fire-and-forget navigation)
