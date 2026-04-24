# HIRIS HA Dashboard Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate HIRIS into HA dashboards and Retro Panel via `X-HIRIS-Internal-Token` inter-addon middleware, an HA Lovelace chat card, and an MQTT publisher for agent state entities.

**Architecture:** Phase 1 — middleware auth + polling; a vanilla JS Lovelace card calls HIRIS via HA Ingress using `hass.callApi()` and SSE streaming. Retro Panel backend proxies via Docker-internal token auth. Phase 2 — MQTTPublisher exposes agent states as native HA entities; card auto-detects and switches to WebSocket push.

**Tech Stack:** Python 3.11, aiohttp, aiomqtt ≥ 2.0.0, vanilla JS custom element (no build step, no external deps).

---

## File Structure

**New files:**
- `hiris/app/api/middleware_internal_auth.py` — aiohttp middleware validating `X-HIRIS-Internal-Token`
- `hiris/app/static/hiris-chat-card.js` — HA Lovelace custom card (vanilla JS, shadow DOM)
- `hiris/app/mqtt_publisher.py` — MQTT publisher for agent state/discovery
- `tests/test_internal_auth_middleware.py`
- `tests/test_handlers_agents.py`
- `tests/test_chat_sse.py`
- `tests/test_mqtt_publisher.py`

**Modified files:**
- `hiris/config.yaml` — add `internal_token`, `mqtt_host/port/user/password` options
- `hiris/run.sh` — export `INTERNAL_TOKEN`, `MQTT_*` env vars
- `hiris/app/server.py` — wire middleware + MQTT startup/cleanup, store `internal_token` in app
- `hiris/app/agent_engine.py` — add `_running_agents` set, `get_agent_status()`, `set_mqtt_publisher()`, MQTT publish hooks
- `hiris/app/api/handlers_agents.py` — enrich `handle_list_agents` with `status`, `budget_eur`, `budget_limit_eur`
- `hiris/app/api/handlers_chat.py` — add SSE streaming path
- `hiris/app/claude_runner.py` — add `chat_stream()` async generator
- `hiris/requirements.txt` — add `aiomqtt>=2.0.0`
- `tests/test_api.py` — update version assertion
- `docs/ROADMAP.md` — mark v0.5 dashboard items done
- `README.md` — add HA Dashboard Integration section

---

## Task 1: X-HIRIS-Internal-Token Middleware

**Files:**
- Create: `hiris/app/api/middleware_internal_auth.py`
- Modify: `hiris/config.yaml` (options + schema blocks)
- Modify: `hiris/run.sh` (after existing exports)
- Modify: `hiris/app/server.py` (import, `_on_startup`, `create_app`)
- Test: `tests/test_internal_auth_middleware.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_internal_auth_middleware.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


def _make_app(tmp_path, token):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = token
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def client_no_token(aiohttp_client, tmp_path):
    return await aiohttp_client(_make_app(tmp_path, ""))


@pytest_asyncio.fixture
async def client_with_token(aiohttp_client, tmp_path):
    return await aiohttp_client(_make_app(tmp_path, "secret-token-abc"))


@pytest.mark.asyncio
async def test_no_secret_configured_all_requests_pass(client_no_token):
    """When internal_token is empty, all requests pass regardless of headers."""
    resp = await client_no_token.get("/api/health")
    assert resp.status == 200


@pytest.mark.asyncio
async def test_valid_token_accepted(client_with_token):
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-HIRIS-Internal-Token": "secret-token-abc"},
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_wrong_token_rejected(client_with_token):
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-HIRIS-Internal-Token": "wrong-token"},
    )
    assert resp.status == 401
    data = await resp.json()
    assert data["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_missing_token_rejected(client_with_token):
    resp = await client_with_token.get("/api/health")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_header_bypasses_auth(client_with_token):
    """Requests with X-Ingress-Path (from HA Supervisor) bypass token check."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"},
    )
    assert resp.status == 200
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /c/Work/Sviluppo/hiris
pytest tests/test_internal_auth_middleware.py -v 2>&1 | head -40
```
Expected: FAIL — `internal_token` key causes KeyError or middleware doesn't exist.

- [ ] **Step 3: Create the middleware file**

Create `hiris/app/api/middleware_internal_auth.py`:

```python
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


@web.middleware
async def internal_auth_middleware(request: web.Request, handler) -> web.Response:
    if request.headers.get("X-Ingress-Path"):
        return await handler(request)
    token = request.app.get("internal_token", "")
    if token and request.headers.get("X-HIRIS-Internal-Token") != token:
        logger.warning("Unauthorized inter-addon request from %s", request.remote)
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)
```

- [ ] **Step 4: Wire middleware into server.py**

In `hiris/app/server.py`:

1. Add import after the existing imports (around line 18):
```python
from .api.middleware_internal_auth import internal_auth_middleware
```

2. In `_on_startup`, add the following line right before `ha_client = HAClient(...)` (around line 34):
```python
    app["internal_token"] = os.environ.get("INTERNAL_TOKEN", "")
```

3. In `create_app`, change line 164 from:
```python
    app = web.Application(middlewares=[_security_headers])
```
to:
```python
    app = web.Application(middlewares=[internal_auth_middleware, _security_headers])
```

- [ ] **Step 5: Add `internal_token` to config.yaml and run.sh**

In `hiris/config.yaml`, in the `options` block add after `local_model_name: ""`:
```yaml
  internal_token: ""
```
In the `schema` block add after `local_model_name: str`:
```yaml
  internal_token: str
```

In `hiris/run.sh`, add after the existing `export LOCAL_MODEL_NAME=...` line:
```bash
export INTERNAL_TOKEN=$(bashio::config 'internal_token' '')
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/test_internal_auth_middleware.py tests/test_api.py -v 2>&1 | tail -20
```
Expected: All 5 middleware tests pass. All existing test_api.py tests pass (token is "" by default → no auth enforced).

- [ ] **Step 7: Commit**

```bash
git add hiris/app/api/middleware_internal_auth.py hiris/app/server.py hiris/config.yaml hiris/run.sh tests/test_internal_auth_middleware.py
git commit -m "feat: add X-HIRIS-Internal-Token inter-addon auth middleware"
```

---

## Task 2: Enrich /api/agents Response for Dashboard

**Files:**
- Modify: `hiris/app/agent_engine.py` (add `_running_agents`, `get_agent_status()`)
- Modify: `hiris/app/api/handlers_agents.py` (enrich `handle_list_agents`)
- Test: `tests/test_handlers_agents.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_handlers_agents.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 100, "output_tokens": 50,
        "requests": 2, "cost_usd": 0.13, "last_run": None,
    })
    engine.set_claude_runner(mock_runner)
    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["llm_router"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = ""
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_list_agents_has_status_field(client):
    resp = await client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    assert isinstance(agents, list)
    for agent in agents:
        assert "status" in agent
        assert agent["status"] in ("idle", "running", "error")


@pytest.mark.asyncio
async def test_list_agents_has_budget_fields(client):
    resp = await client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    for agent in agents:
        assert "budget_eur" in agent
        assert "budget_limit_eur" in agent
        assert isinstance(agent["budget_eur"], float)
        assert isinstance(agent["budget_limit_eur"], float)


@pytest.mark.asyncio
async def test_list_agents_budget_computed_from_usage(client):
    resp = await client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    # mock_runner returns cost_usd=0.13, EUR rate=0.92 → 0.1196
    for agent in agents:
        assert agent["budget_eur"] == round(0.13 * 0.92, 4)


@pytest.mark.asyncio
async def test_created_agent_has_all_dashboard_fields(client):
    resp = await client.post("/api/agents", json={
        "name": "Test",
        "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "test",
    })
    assert resp.status == 201

    resp = await client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    required = {"id", "name", "type", "enabled", "status", "last_run",
                "budget_eur", "budget_limit_eur", "is_default"}
    for agent in agents:
        missing = required - set(agent.keys())
        assert not missing, f"Missing fields: {missing}"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_handlers_agents.py -v 2>&1 | tail -20
```
Expected: FAIL — `status`, `budget_eur`, `budget_limit_eur` not in response.

- [ ] **Step 3: Add `_running_agents` and `get_agent_status()` to AgentEngine**

In `hiris/app/agent_engine.py`:

1. In `AgentEngine.__init__`, add after `self._entity_cache: Any = None` (around line 51):
```python
        self._running_agents: set[str] = set()
        self._mqtt_publisher = None
```

2. Add `set_mqtt_publisher()` method after `set_entity_cache()` (around line 57):
```python
    def set_mqtt_publisher(self, publisher) -> None:
        self._mqtt_publisher = publisher
```

3. Add `get_agent_status()` method after `list_agents()` (after line 343):
```python
    def get_agent_status(self, agent_id: str) -> str:
        if agent_id in self._running_agents:
            return "running"
        agent = self._agents.get(agent_id)
        if agent is None or not agent.enabled:
            return "idle"
        return "idle"
```

4. In `_run_agent` (around line 429), add `self._running_agents.add(agent.id)` before the `try:` block, and wrap with `finally` to discard:

Find the block starting at `async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:`. The current structure is:
```python
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = ...
        out_before = ...
        try:
            agent.last_run = ...
            ...
        except ...:
            ...
        return result
```

Change to:
```python
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        self._running_agents.add(agent.id)
        try:
            # ... existing try body unchanged ...
        except Exception as exc:
            # ... existing except unchanged ...
        finally:
            self._running_agents.discard(agent.id)
        return result
```

The `return result` that currently follows the `except` block must be moved inside the `try` block (before the `finally`) or kept after. Since the existing code uses `result` which is set in the try block, move `return result` to after the finally by keeping it at the same indentation level — Python executes `finally` before returning, so the pattern:
```python
        self._running_agents.add(agent.id)
        try:
            # ... body that sets result ...
        except Exception as exc:
            logger.error(...)
            result = ""
        finally:
            self._running_agents.discard(agent.id)
        return result
```
is correct. Ensure `result = ""` is initialized before the try block as a fallback.

- [ ] **Step 4: Update `handle_list_agents` in handlers_agents.py**

Move `_EUR_RATE = 0.92` from line 113 to the top of the file (after imports, before the first function). Then replace the existing `handle_list_agents` function (lines 15–17):

```python
# Old:
async def handle_list_agents(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    return web.json_response(list(engine.list_agents().values()))
```

```python
# New:
async def handle_list_agents(request: web.Request) -> web.Response:
    engine = request.app["engine"]
    runner = request.app.get("llm_router") or request.app.get("claude_runner")
    result = []
    for agent_id, agent_data in engine.list_agents().items():
        entry = dict(agent_data)
        entry["status"] = engine.get_agent_status(agent_id)
        budget_eur = 0.0
        if runner:
            usage = runner.get_agent_usage(agent_id)
            budget_eur = round(usage.get("cost_usd", 0.0) * _EUR_RATE, 4)
        entry["budget_eur"] = budget_eur
        entry["budget_limit_eur"] = float(entry.get("budget_eur_limit", 0.0))
        result.append(entry)
    return web.json_response(result)
```

Also remove the duplicate `_EUR_RATE = 0.92` that remains at the original line 113 position.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_handlers_agents.py tests/test_api.py -v 2>&1 | tail -20
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/agent_engine.py hiris/app/api/handlers_agents.py tests/test_handlers_agents.py
git commit -m "feat: enrich GET /api/agents with status, budget_eur, budget_limit_eur"
```

---

## Task 3: SSE Streaming for /api/chat

**Files:**
- Modify: `hiris/app/claude_runner.py` (add `chat_stream()` async generator)
- Modify: `hiris/app/api/handlers_chat.py` (SSE path + `import json`)
- Test: `tests/test_chat_sse.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_chat_sse.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="SSE test response text")
    mock_runner.last_tool_calls = []
    mock_runner.get_agent_usage = MagicMock(return_value={"cost_usd": 0.0})

    async def fake_chat_stream(**kwargs):
        import json
        yield f'data: {json.dumps({"type": "token", "text": "SSE test"})}\n\n'
        yield f'data: {json.dumps({"type": "done", "agent_id": None, "tool_calls": []})}\n\n'

    mock_runner.chat_stream = fake_chat_stream
    engine.set_claude_runner(mock_runner)
    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["llm_router"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = ""
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_chat_sse_via_stream_body_param(client):
    resp = await client.post("/api/chat", json={"message": "Test SSE", "stream": True})
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_chat_sse_via_accept_header(client):
    resp = await client.post(
        "/api/chat",
        json={"message": "Test SSE"},
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_chat_json_still_works(client):
    """Non-SSE requests still return JSON."""
    resp = await client.post("/api/chat", json={"message": "Hello"})
    assert resp.status == 200
    data = await resp.json()
    assert "response" in data
    assert data["response"] == "SSE test response text"


@pytest.mark.asyncio
async def test_chat_sse_body_contains_events(client):
    resp = await client.post("/api/chat", json={"message": "Test", "stream": True})
    body = await resp.text()
    assert "data:" in body
    assert '"type"' in body
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_chat_sse.py -v 2>&1 | tail -20
```
Expected: FAIL — SSE request returns JSON, not `text/event-stream`.

- [ ] **Step 3: Add `chat_stream()` to ClaudeRunner**

In `hiris/app/claude_runner.py`, add the following method to the `ClaudeRunner` class after the `chat()` method. Find the end of `chat()` and add:

```python
    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        allowed_tools=None,
        conversation_history=None,
        allowed_entities=None,
        allowed_services=None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id=None,
        visible_entity_ids=None,
    ):
        """Async generator yielding SSE-formatted lines for the chat response.

        Yields lines in the form:
          'data: {"type": "token", "text": "<chunk>"}\\n\\n'
          'data: {"type": "done", "agent_id": "<id>", "tool_calls": [...]}\\n\\n'
          'data: {"type": "error", "message": "<msg>"}\\n\\n'
        """
        import json as _json
        try:
            result = await self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
                context_str=context_str,
                allowed_tools=allowed_tools,
                conversation_history=conversation_history,
                allowed_entities=allowed_entities,
                allowed_services=allowed_services,
                model=model,
                max_tokens=max_tokens,
                agent_type=agent_type,
                restrict_to_home=restrict_to_home,
                require_confirmation=require_confirmation,
                agent_id=agent_id,
                visible_entity_ids=visible_entity_ids,
            )
        except Exception as exc:
            yield f'data: {_json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f'data: {_json.dumps({"type": "token", "text": result[i:i + chunk_size]})}\n\n'

        tool_calls = self.last_tool_calls if isinstance(self.last_tool_calls, list) else []
        yield f'data: {_json.dumps({"type": "done", "agent_id": agent_id, "tool_calls": tool_calls})}\n\n'
```

- [ ] **Step 4: Add SSE path to handlers_chat.py**

In `hiris/app/api/handlers_chat.py`:

1. Add `import json` after the existing imports (after `import logging`):
```python
import json
```

2. After the `agent_require_confirmation = ...` line (currently the last `getattr` before `response = await runner.chat(...)`), add the SSE detection and streaming path:

```python
    wants_stream = (
        "text/event-stream" in request.headers.get("Accept", "")
        or body.get("stream") is True
    )

    if wants_stream:
        stream_resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        await stream_resp.prepare(request)
        collected_tokens: list[str] = []
        async for chunk in runner.chat_stream(
            user_message=message,
            system_prompt=system_prompt,
            context_str=context_str,
            conversation_history=context_history,
            allowed_tools=allowed_tools,
            allowed_entities=allowed_entities,
            allowed_services=allowed_services,
            model=agent_model,
            max_tokens=agent_max_tokens,
            agent_type=agent_type,
            restrict_to_home=agent_restrict,
            require_confirmation=agent_require_confirmation,
            agent_id=effective_agent_id,
            visible_entity_ids=visible_ids,
        ):
            await stream_resp.write(chunk.encode())
            try:
                evt = json.loads(chunk.removeprefix("data: ").strip())
                if evt.get("type") == "token":
                    collected_tokens.append(evt.get("text", ""))
            except Exception:
                pass
        await stream_resp.write_eof()
        full_response = "".join(collected_tokens)
        if effective_agent_id and full_response:
            append_messages(effective_agent_id, [
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_response},
            ], data_dir)
        return stream_resp
```

The existing `response = await runner.chat(...)` block and the final `return web.json_response(...)` remain unchanged after the `if wants_stream:` block (they handle the non-streaming case).

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_chat_sse.py tests/test_api.py -v 2>&1 | tail -20
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/claude_runner.py hiris/app/api/handlers_chat.py tests/test_chat_sse.py
git commit -m "feat: add SSE streaming support for /api/chat"
```

---

## Task 4: HA Lovelace Card hiris-chat-card.js

**Files:**
- Create: `hiris/app/static/hiris-chat-card.js`

- [ ] **Step 1: Create the card file**

Create `hiris/app/static/hiris-chat-card.js` with the full implementation:

```javascript
// hiris-chat-card.js — HA Lovelace custom card for HIRIS chat
// Add to configuration.yaml:
//   lovelace:
//     resources:
//       - url: /api/hassio_ingress/hiris/static/hiris-chat-card.js
//         type: module
// Dashboard config:
//   type: custom:hiris-chat-card
//   agent_id: hiris-default
//   title: "Assistente Casa"
//   hiris_slug: hiris

const POLL_MS = 30_000;
const CHAT_TIMEOUT_MS = 30_000;
const EUR_RATE = 0.92;

class HirisCard extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    this._agentId = null;
    this._slug = 'hiris';
    this._title = 'HIRIS Chat';
    this._hass = null;
    this._status = 'idle';
    this._enabled = true;
    this._budgetEur = 0;
    this._budgetLimitEur = 0;
    this._messages = [];
    this._polling = null;
    this._loading = false;
    this._error = null;
    this._render();
  }

  static getConfigElement() { return document.createElement('div'); }
  static getStubConfig() {
    return { agent_id: '', title: 'HIRIS Chat', hiris_slug: 'hiris' };
  }

  setConfig(config) {
    if (!config.agent_id) throw new Error('agent_id is required');
    this._agentId = config.agent_id;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Phase 2: auto-detect MQTT entities pushed by MQTTPublisher
    const statusKey = `sensor.hiris_${this._agentId}_status`;
    if (hass.states[statusKey]) {
      this._status = hass.states[statusKey].state || 'idle';
      const budgetKey = `sensor.hiris_${this._agentId}_budget_eur`;
      this._budgetEur = parseFloat(hass.states[budgetKey]?.state || '0');
      const switchKey = `switch.hiris_${this._agentId}_enabled`;
      this._enabled = hass.states[switchKey]?.state !== 'off';
      this._render();
    } else if (!this._polling) {
      this._startPolling();
    }
  }

  connectedCallback() {
    if (this._agentId && !this._polling) this._startPolling();
  }

  disconnectedCallback() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }

  _startPolling() {
    this._fetchStatus();
    this._polling = setInterval(() => this._fetchStatus(), POLL_MS);
  }

  async _fetchStatus() {
    if (!this._hass) return;
    try {
      const agents = await this._hass.callApi('GET', `hassio_ingress/${this._slug}/api/agents`);
      const agent = agents.find(a => a.id === this._agentId);
      if (agent) {
        this._status = agent.status || 'idle';
        this._enabled = !!agent.enabled;
        this._budgetEur = agent.budget_eur || 0;
        this._budgetLimitEur = agent.budget_limit_eur || 0;
        this._error = null;
      } else {
        this._error = 'Agente non configurato';
      }
    } catch (e) {
      this._error = '⚠ HIRIS non disponibile';
    }
    this._render();
  }

  async _sendMessage(text) {
    if (!text.trim() || this._loading) return;
    this._loading = true;
    this._messages.push({ role: 'user', text });
    const assistantMsg = { role: 'assistant', text: '', streaming: true };
    this._messages.push(assistantMsg);
    this._render();

    try {
      const hassUrl = this._hass.connection.options.hassUrl || '';
      const token = this._hass.connection.options.auth?.data?.access_token || '';
      const url = `${hassUrl}/api/hassio_ingress/${this._slug}/api/chat`;

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, agent_id: this._agentId, stream: true }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const ct = resp.headers.get('Content-Type') || '';

      if (ct.includes('text/event-stream')) {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'token') { assistantMsg.text += evt.text; this._render(); }
              if (evt.type === 'done') { assistantMsg.streaming = false; }
              if (evt.type === 'error') {
                assistantMsg.text = `Errore: ${evt.message}`;
                assistantMsg.streaming = false;
              }
            } catch {}
          }
        }
      } else {
        const data = await resp.json();
        assistantMsg.text = data.response || 'Nessuna risposta';
        assistantMsg.streaming = false;
      }
    } catch (e) {
      assistantMsg.text = e.name === 'AbortError'
        ? 'Timeout — riprova'
        : `Errore: ${e.message}`;
      assistantMsg.streaming = false;
    } finally {
      this._loading = false;
      this._render();
      await this._fetchStatus();
    }
  }

  async _toggleAgent() {
    if (!this._hass) return;
    try {
      await this._hass.callApi(
        'PUT',
        `hassio_ingress/${this._slug}/api/agents/${this._agentId}`,
        { enabled: !this._enabled },
      );
      await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
    }
  }

  _statusColor() {
    return {
      idle: '#4caf50', running: '#2196f3', error: '#f44336',
      unavailable: '#9e9e9e',
    }[this._status] || '#9e9e9e';
  }

  _render() {
    const pct = this._budgetLimitEur > 0
      ? Math.min(100, (this._budgetEur / this._budgetLimitEur) * 100)
      : 0;
    const color = this._statusColor();
    const msgs = this._messages.map(m => `
      <div class="msg ${m.role}">
        ${m.text.replace(/</g, '&lt;').replace(/\n/g, '<br>')}
        ${m.streaming ? '<span class="cursor">▌</span>' : ''}
      </div>`).join('');

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .card { background: var(--card-background-color,#fff); border-radius: 12px;
          overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
        .header { display: flex; align-items: center; justify-content: space-between;
          padding: 12px 16px; border-bottom: 1px solid var(--divider-color,#e0e0e0); }
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
        .status { display: flex; align-items: center; gap: 6px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: ${color}; }
        .status-text { font-size: 12px; color: var(--secondary-text-color,#666); }
        .toggle { cursor: pointer; font-size: 18px; background: none; border: none;
          padding: 0; line-height: 1; }
        .budget-bar { height: 4px; background: var(--divider-color,#eee); }
        .budget-fill { height: 100%; width: ${pct}%; background: var(--primary-color,#03a9f4);
          transition: width .3s; }
        .budget-text { font-size: 11px; color: var(--secondary-text-color,#888);
          padding: 2px 16px 4px; }
        .messages { height: 200px; overflow-y: auto; padding: 12px 16px;
          display: flex; flex-direction: column; gap: 8px; }
        .msg { max-width: 85%; padding: 8px 12px; border-radius: 12px;
          font-size: 14px; line-height: 1.4; word-break: break-word; }
        .msg.user { align-self: flex-end; background: var(--primary-color,#03a9f4);
          color: #fff; border-radius: 12px 12px 2px 12px; }
        .msg.assistant { align-self: flex-start;
          background: var(--secondary-background-color,#f5f5f5);
          color: var(--primary-text-color,#333); border-radius: 12px 12px 12px 2px; }
        .cursor { animation: blink 1s step-start infinite; }
        @keyframes blink { 50% { opacity: 0; } }
        .empty { color: #aaa; text-align: center; padding-top: 60px; font-size: 13px; }
        .error-badge { padding: 8px 16px; color: var(--warning-color,#ff9800);
          font-size: 13px; text-align: center; }
        .input-row { display: flex; gap: 8px; padding: 12px 16px;
          border-top: 1px solid var(--divider-color,#e0e0e0); }
        .input { flex: 1; padding: 8px 12px; border: 1px solid var(--divider-color,#e0e0e0);
          border-radius: 20px; font-size: 14px; outline: none;
          background: var(--secondary-background-color,#f5f5f5);
          color: var(--primary-text-color,#333); }
        .send { padding: 8px 16px; background: var(--primary-color,#03a9f4); color: #fff;
          border: none; border-radius: 20px; cursor: pointer; font-size: 14px; }
        .send:disabled { opacity: .5; cursor: default; }
      </style>
      <div class="card">
        <div class="header">
          <span class="title">🤖 ${this._title}</span>
          <div class="status">
            <span class="dot"></span>
            <span class="status-text">${this._status}</span>
            <button class="toggle" id="tog" title="${this._enabled ? 'Disabilita' : 'Abilita'}">
              ${this._enabled ? '🔘' : '⭕'}
            </button>
          </div>
        </div>
        ${this._budgetLimitEur > 0 ? `
          <div class="budget-bar"><div class="budget-fill"></div></div>
          <div class="budget-text">€${this._budgetEur.toFixed(2)} / €${this._budgetLimitEur.toFixed(2)}</div>
        ` : ''}
        ${this._error ? `<div class="error-badge">${this._error}</div>` : ''}
        <div class="messages" id="msgs">
          ${msgs || '<div class="empty">Scrivi un messaggio per iniziare…</div>'}
        </div>
        <div class="input-row">
          <input class="input" id="inp" type="text" placeholder="Scrivi un messaggio…"
            ${!this._enabled ? 'disabled' : ''} />
          <button class="send" id="snd" ${this._loading || !this._enabled ? 'disabled' : ''}>↑</button>
        </div>
      </div>`;

    const inp = this._shadow.getElementById('inp');
    const snd = this._shadow.getElementById('snd');
    const tog = this._shadow.getElementById('tog');
    const msgs = this._shadow.getElementById('msgs');

    if (msgs) msgs.scrollTop = msgs.scrollHeight;
    if (snd) snd.onclick = () => {
      const t = inp?.value.trim();
      if (t) { inp.value = ''; this._sendMessage(t); }
    };
    if (inp) inp.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); snd?.click(); }
    };
    if (tog) tog.onclick = () => this._toggleAgent();
  }
}

customElements.define('hiris-chat-card', HirisCard);
```

- [ ] **Step 2: Verify file exists and server can serve it**

```bash
python3 -c "
import os
p = 'hiris/app/static/hiris-chat-card.js'
size = os.path.getsize(p)
print(f'OK — {size} bytes')
"
```
Expected: `OK — <N> bytes` (should be > 5000).

- [ ] **Step 3: Manual test instructions**

In a running HIRIS HA add-on, add to `configuration.yaml`:
```yaml
lovelace:
  resources:
    - url: /api/hassio_ingress/hiris/static/hiris-chat-card.js
      type: module
```
Add to any Lovelace dashboard:
```yaml
type: custom:hiris-chat-card
agent_id: hiris-default
title: "Assistente Casa"
hiris_slug: hiris
```
Verify: card renders with status dot + toggle, status polls every 30s, message sends and receives response (SSE typing effect visible), toggle enables/disables agent, timeout shows "Timeout — riprova".

- [ ] **Step 4: Commit**

```bash
git add hiris/app/static/hiris-chat-card.js
git commit -m "feat: add hiris-chat-card HA Lovelace custom card (vanilla JS, shadow DOM)"
```

---

## Task 5: MQTT Publisher (Phase 2)

**Files:**
- Create: `hiris/app/mqtt_publisher.py`
- Modify: `hiris/requirements.txt`
- Modify: `hiris/config.yaml`
- Modify: `hiris/run.sh`
- Modify: `hiris/app/server.py`
- Modify: `hiris/app/agent_engine.py` (hook MQTT publish after run)
- Test: `tests/test_mqtt_publisher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mqtt_publisher.py`:

```python
import pytest
from hiris.app.mqtt_publisher import MQTTPublisher
from hiris.app.agent_engine import Agent


def _make_agent(**kwargs):
    defaults = dict(
        id="test-001", name="Test Agent", type="chat",
        trigger={"type": "manual"}, system_prompt="",
        allowed_tools=[], enabled=True, last_run=None,
        budget_eur_limit=5.0,
    )
    defaults.update(kwargs)
    return Agent(**defaults)


@pytest.mark.asyncio
async def test_start_disabled_when_host_empty():
    pub = MQTTPublisher()
    await pub.start(host="", port=1883, user="", password="")
    assert not pub.is_connected


@pytest.mark.asyncio
async def test_stop_without_start_does_not_raise():
    pub = MQTTPublisher()
    await pub.stop()


def test_build_discovery_payload_sensor():
    pub = MQTTPublisher()
    agent = _make_agent()
    p = pub._build_discovery_payload(agent, "status", "sensor")
    assert p["unique_id"] == "hiris_test-001_status"
    assert p["state_topic"] == "hiris/agents/test-001/status"
    assert p["device"]["name"] == "HIRIS Test Agent"
    assert "command_topic" not in p


def test_build_discovery_payload_switch():
    pub = MQTTPublisher()
    agent = _make_agent()
    p = pub._build_discovery_payload(agent, "enabled", "switch")
    assert "command_topic" in p
    assert p["command_topic"] == "hiris/agents/test-001/enabled/set"


def test_build_state_topics_idle_enabled():
    pub = MQTTPublisher()
    agent = _make_agent()
    topics = pub._build_state_topics(agent, budget_eur=0.12, status="idle")
    assert topics["hiris/agents/test-001/status"] == "idle"
    assert topics["hiris/agents/test-001/enabled"] == "ON"
    assert topics["hiris/agents/test-001/budget_eur"] == "0.12"


def test_build_state_topics_disabled():
    pub = MQTTPublisher()
    agent = _make_agent(enabled=False)
    topics = pub._build_state_topics(agent, budget_eur=0.0, status="idle")
    assert topics["hiris/agents/test-001/enabled"] == "OFF"


@pytest.mark.asyncio
async def test_publish_noop_when_not_connected():
    pub = MQTTPublisher()
    agent = _make_agent()
    await pub.publish_agent_state(agent, budget_eur=0.0, status="idle")  # must not raise
    await pub.publish_discovery(agent)  # must not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_mqtt_publisher.py -v 2>&1 | tail -20
```
Expected: FAIL — `hiris.app.mqtt_publisher` module not found.

- [ ] **Step 3: Add aiomqtt to requirements.txt**

In `hiris/requirements.txt`, add:
```
aiomqtt>=2.0.0
```

Install locally:
```bash
pip install "aiomqtt>=2.0.0"
```

- [ ] **Step 4: Create hiris/app/mqtt_publisher.py**

```python
import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DISCOVERY_PREFIX = "homeassistant"
_STATE_PREFIX = "hiris/agents"
_RECONNECT_MAX = 60


class MQTTPublisher:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._host = ""
        self._port = 1883
        self._user = ""
        self._password = ""
        self._pending: asyncio.Queue = asyncio.Queue()

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self, host: str, port: int = 1883, user: str = "", password: str = "") -> None:
        if not host:
            logger.info("MQTT host not configured — publisher disabled")
            return
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._task = asyncio.create_task(self._connect_loop(), name="mqtt_publisher")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False

    async def _connect_loop(self) -> None:
        try:
            import aiomqtt
        except ImportError:
            logger.error("aiomqtt not installed — run: pip install aiomqtt>=2.0.0")
            return

        backoff = 1
        while True:
            try:
                kwargs: dict = {"hostname": self._host, "port": self._port}
                if self._user:
                    kwargs["username"] = self._user
                if self._password:
                    kwargs["password"] = self._password
                async with aiomqtt.Client(**kwargs) as client:
                    self._connected = True
                    backoff = 1
                    logger.info("MQTT connected to %s:%d", self._host, self._port)
                    while True:
                        topic, payload = await self._pending.get()
                        await client.publish(topic, payload, retain=True)
                        self._pending.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._connected = False
                logger.warning("MQTT disconnected: %s. Reconnecting in %ds", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX)

    def _build_discovery_payload(self, agent, metric: str, component: str) -> dict:
        payload: dict = {
            "unique_id": f"hiris_{agent.id}_{metric}",
            "name": metric.replace("_", " ").title(),
            "state_topic": f"{_STATE_PREFIX}/{agent.id}/{metric}",
            "device": {
                "identifiers": [f"hiris_{agent.id}"],
                "name": f"HIRIS {agent.name}",
                "manufacturer": "HIRIS",
                "model": agent.type,
            },
        }
        if component == "switch":
            payload["command_topic"] = f"{_STATE_PREFIX}/{agent.id}/{metric}/set"
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
        elif metric == "budget_eur":
            payload["unit_of_measurement"] = "EUR"
            payload["device_class"] = "monetary"
        return payload

    def _build_state_topics(self, agent, budget_eur: float = 0.0, status: str = "idle") -> dict:
        return {
            f"{_STATE_PREFIX}/{agent.id}/status": status,
            f"{_STATE_PREFIX}/{agent.id}/enabled": "ON" if agent.enabled else "OFF",
            f"{_STATE_PREFIX}/{agent.id}/budget_eur": str(round(budget_eur, 4)),
            f"{_STATE_PREFIX}/{agent.id}/last_run": agent.last_run or "",
        }

    async def publish_discovery(self, agent) -> None:
        if not self._connected:
            return
        metrics = [
            ("status", "sensor"),
            ("last_run", "sensor"),
            ("budget_eur", "sensor"),
            ("enabled", "switch"),
        ]
        for metric, component in metrics:
            payload = self._build_discovery_payload(agent, metric, component)
            topic = f"{_DISCOVERY_PREFIX}/{component}/hiris_{agent.id}_{metric}/config"
            await self._pending.put((topic, json.dumps(payload)))

    async def publish_agent_state(self, agent, budget_eur: float = 0.0, status: str = "idle") -> None:
        if not self._connected:
            return
        for topic, payload in self._build_state_topics(agent, budget_eur=budget_eur, status=status).items():
            await self._pending.put((topic, payload))
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_mqtt_publisher.py -v 2>&1 | tail -20
```
Expected: All 7 tests pass.

- [ ] **Step 6: Add MQTT options to config.yaml and run.sh**

In `hiris/config.yaml`, in `options` block add after `internal_token: ""`:
```yaml
  mqtt_host: ""
  mqtt_port: 1883
  mqtt_user: ""
  mqtt_password: ""
```
In `schema` block add after `internal_token: str`:
```yaml
  mqtt_host: str
  mqtt_port: int
  mqtt_user: str
  mqtt_password: password
```

In `hiris/run.sh`, add after `export INTERNAL_TOKEN=...`:
```bash
export MQTT_HOST=$(bashio::config 'mqtt_host' '')
export MQTT_PORT=$(bashio::config 'mqtt_port' '1883')
export MQTT_USER=$(bashio::config 'mqtt_user' '')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password' '')
```

- [ ] **Step 7: Wire MQTTPublisher into server.py**

In `hiris/app/server.py`:

1. Add import at top:
```python
from .mqtt_publisher import MQTTPublisher
```

2. In `_on_startup`, after `await task_engine.start()` (around line 97), add:
```python
    mqtt_pub = MQTTPublisher()
    await mqtt_pub.start(
        host=os.environ.get("MQTT_HOST", ""),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        user=os.environ.get("MQTT_USER", ""),
        password=os.environ.get("MQTT_PASSWORD", ""),
    )
    app["mqtt_publisher"] = mqtt_pub
    engine.set_mqtt_publisher(mqtt_pub)
```

3. In `_on_cleanup`, add before `await app["ha_client"].stop()`:
```python
    if "mqtt_publisher" in app:
        await app["mqtt_publisher"].stop()
```

- [ ] **Step 8: Hook MQTT publish into AgentEngine._run_agent**

In `hiris/app/agent_engine.py`, in `_run_agent`, inside the `finally` block (added in Task 2), after `self._running_agents.discard(agent.id)`, add:

```python
            if self._mqtt_publisher:
                runner = self._claude_runner
                budget_eur = 0.0
                if runner and hasattr(runner, "get_agent_usage"):
                    usage = runner.get_agent_usage(agent.id)
                    budget_eur = round(usage.get("cost_usd", 0.0) * 0.92, 4)
                asyncio.create_task(
                    self._mqtt_publisher.publish_agent_state(
                        agent, budget_eur=budget_eur, status="idle"
                    ),
                    name=f"mqtt_pub_{agent.id}",
                )
```

Also hook discovery publish in `create_agent()`. Find the method and after `self._agents[agent.id] = agent` add:
```python
        if self._mqtt_publisher:
            asyncio.create_task(
                self._mqtt_publisher.publish_discovery(agent),
                name=f"mqtt_disc_{agent.id}",
            )
```

- [ ] **Step 9: Run full test suite**

```bash
cd /c/Work/Sviluppo/hiris
pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add hiris/app/mqtt_publisher.py hiris/requirements.txt hiris/config.yaml hiris/run.sh hiris/app/server.py hiris/app/agent_engine.py tests/test_mqtt_publisher.py
git commit -m "feat: MQTT publisher for agent state entities (phase 2)"
```

---

## Task 6: Version Bump + README + ROADMAP Update

**Files:**
- Modify: `hiris/app/server.py` (version string in `_handle_health`)
- Modify: `hiris/config.yaml` (version field)
- Modify: `tests/test_api.py` (version assertion on line 55)
- Modify: `docs/ROADMAP.md`
- Modify: `README.md`

- [ ] **Step 1: Bump version to 0.5.0**

In `hiris/app/server.py`, change around line 217:
```python
# Old:
    return web.json_response({"status": "ok", "version": "0.4.2"})
# New:
    return web.json_response({"status": "ok", "version": "0.5.0"})
```

In `hiris/config.yaml`, line 3:
```yaml
# Old:
version: "0.4.2"
# New:
version: "0.5.0"
```

In `tests/test_api.py`, line 55:
```python
# Old:
    assert data["version"] == "0.4.2"
# New:
    assert data["version"] == "0.5.0"
```

- [ ] **Step 2: Verify version bump passes tests**

```bash
pytest tests/test_api.py::test_health_endpoint -v
```
Expected: PASS.

- [ ] **Step 3: Update docs/ROADMAP.md**

In the v0.5 section of `docs/ROADMAP.md`, mark the following items as completed (change `[ ]` to `[x]`):
- HA Lovelace custom card `hiris-chat-card`
- `X-HIRIS-Internal-Token` inter-addon auth middleware
- MQTT publisher — agent state entities (phase 2)
- Spec doc for Retro Panel team

Also update the Priority Stack: remove the HA dashboard items from pending work since they are now complete.

- [ ] **Step 4: Add HA Dashboard Integration section to README.md**

Find the README and add a new section `## HA Dashboard Integration` after the Configuration section:

```markdown
## HA Dashboard Integration

### Lovelace Chat Card

Add to `configuration.yaml`:

```yaml
lovelace:
  resources:
    - url: /api/hassio_ingress/hiris/static/hiris-chat-card.js
      type: module
```

Add to any Lovelace dashboard:

```yaml
type: custom:hiris-chat-card
agent_id: hiris-default       # required — agent ID to use
title: "Assistente Casa"      # optional, default: "HIRIS Chat"
hiris_slug: hiris             # optional, default: "hiris"
```

The card shows agent status, budget bar, full chat history, and an enable/disable toggle. It streams responses token-by-token via SSE.

### Inter-Addon Auth (Retro Panel / external systems)

Set `internal_token` in add-on options to require a shared secret on non-Ingress requests. HA Ingress requests always bypass this check. Leave empty to disable (default).

### MQTT Agent Entities (Phase 2)

Set `mqtt_host` in add-on options to publish agent states as native HA entities. Requires a Mosquitto (or compatible) broker:

| Entity | Type | Values |
|--------|------|--------|
| `sensor.hiris_{id}_status` | sensor | `idle` \| `running` \| `error` |
| `sensor.hiris_{id}_last_run` | sensor | ISO 8601 timestamp |
| `sensor.hiris_{id}_budget_eur` | sensor | float (EUR) |
| `switch.hiris_{id}_enabled` | switch | `on` / `off` |

When MQTT entities are present, the Lovelace card switches automatically from polling to WebSocket push.
```

- [ ] **Step 5: Run full test suite one final time**

```bash
cd /c/Work/Sviluppo/hiris
pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: All tests pass.

- [ ] **Step 6: Final commit**

```bash
git add hiris/app/server.py hiris/config.yaml tests/test_api.py docs/ROADMAP.md README.md
git commit -m "chore: bump version to 0.5.0, add README dashboard section, update ROADMAP"
```
