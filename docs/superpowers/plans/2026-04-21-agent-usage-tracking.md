# Per-Agent Usage Tracking — Plan C

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each agent its own lifetime token and cost usage (input tokens, output tokens, cost in EUR), allow resetting per-agent counters, and let the user manually block an agent or set a budget ceiling that triggers automatic disabling.

**Architecture:** Four layers — (1) `ClaudeRunner` accumulates per-agent totals alongside global totals, persisted in the same `usage.json` under a `"per_agent"` key; (2) `AgentEngine._run_agent` passes `agent_id` to `chat()`; (3) two new HTTP endpoints; (4) a "📊 Consumi" collapsible section in the agent panel in `config.html`.

**Tech Stack:** Python 3.11 + aiohttp, vanilla JS, existing dark-theme CSS variables.

> **Execution order:** This plan should be executed after Plan A and Plan B, or on its own branch. If run independently, the `agent_id` param added to `chat()` in Task 9 is the only change to `ClaudeRunner`; it does not conflict with Plan B's `system_override` param.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `hiris/app/claude_runner.py` | Modify | Add `agent_id` param to `chat()`, accumulate `_per_agent_usage`, add `get_agent_usage` / `reset_agent_usage` methods |
| `hiris/app/agent_engine.py` | Modify | Pass `agent_id=agent.id` to `chat()`; add `budget_eur_limit` field to Agent; auto-disable on budget breach |
| `hiris/app/api/handlers_agents.py` | Modify | Add `handle_get_agent_usage` and `handle_reset_agent_usage` |
| `hiris/app/server.py` | Modify | Register the two new routes |
| `hiris/app/static/config.html` | Modify | "Consumi" collapsible section: stats table + reset + disable buttons + budget input |
| `tests/test_claude_runner.py` | Modify | Tests for per-agent accumulation |
| `tests/test_agent_engine.py` | Modify | Tests for budget auto-disable |

---

### Task 9: Per-agent usage accumulation in ClaudeRunner

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_claude_runner.py`:

```python
def test_get_agent_usage_returns_zeros_for_unknown_agent():
    from unittest.mock import MagicMock, AsyncMock
    from hiris.app.claude_runner import ClaudeRunner
    runner = ClaudeRunner(
        api_key="test", ha_client=MagicMock(),
        notify_config={}, usage_path="",
    )
    usage = runner.get_agent_usage("agent-xyz")
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["cost_usd"] == 0.0
    assert usage["last_run"] is None


def test_per_agent_usage_accumulates_after_chat(monkeypatch):
    """chat() with agent_id accumulates tokens in _per_agent_usage."""
    import asyncio
    from unittest.mock import MagicMock, AsyncMock, patch
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test", ha_client=MagicMock(),
        notify_config={}, usage_path="",
    )

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(type="text", text="ok")]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    async def fake_call(**kwargs):
        return mock_response

    runner._call_api = fake_call

    asyncio.get_event_loop().run_until_complete(
        runner.chat(user_message="hello", agent_id="agent-abc")
    )

    usage = runner.get_agent_usage("agent-abc")
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["requests"] == 1
    assert usage["cost_usd"] > 0
    assert usage["last_run"] is not None


def test_reset_agent_usage_clears_counters(monkeypatch):
    import asyncio
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test", ha_client=MagicMock(),
        notify_config={}, usage_path="",
    )
    runner._per_agent_usage["agent-abc"] = {
        "input_tokens": 500, "output_tokens": 200,
        "requests": 3, "cost_usd": 0.002, "last_run": "2026-01-01T00:00:00Z",
    }
    runner.reset_agent_usage("agent-abc")
    usage = runner.get_agent_usage("agent-abc")
    assert usage["input_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["last_run"] is None


def test_per_agent_usage_persists_and_reloads(tmp_path):
    import asyncio
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    usage_file = str(tmp_path / "usage.json")
    runner = ClaudeRunner(
        api_key="test", ha_client=MagicMock(),
        notify_config={}, usage_path=usage_file,
    )
    runner._per_agent_usage["agent-persist"] = {
        "input_tokens": 1000, "output_tokens": 400,
        "requests": 5, "cost_usd": 0.005, "last_run": "2026-04-01T10:00:00Z",
    }
    runner._save_usage()

    runner2 = ClaudeRunner(
        api_key="test", ha_client=MagicMock(),
        notify_config={}, usage_path=usage_file,
    )
    usage = runner2.get_agent_usage("agent-persist")
    assert usage["input_tokens"] == 1000
    assert usage["requests"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_claude_runner.py::test_get_agent_usage_returns_zeros_for_unknown_agent tests/test_claude_runner.py::test_per_agent_usage_accumulates_after_chat -v
```

Expected: `AttributeError` — `get_agent_usage` and `_per_agent_usage` do not exist yet.

- [ ] **Step 3: Add `_per_agent_usage` and related code to ClaudeRunner**

In `hiris/app/claude_runner.py`, in the `ClaudeRunner.__init__` method, add after `self.usage_last_reset` line:

```python
        self._per_agent_usage: dict[str, dict] = {}
```

- [ ] **Step 4: Update `_load_usage` to load per-agent data**

In the `_load_usage` method, after loading the global fields, add:

```python
            self._per_agent_usage = data.get("per_agent", {})
```

- [ ] **Step 5: Update `_save_usage` to persist per-agent data**

In the `data` dict inside `_save_usage`, add the key:

```python
            data = {
                "schema_version": 1,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_requests": self.total_requests,
                "last_reset": self.usage_last_reset,
                "total_cost_usd": self.total_cost_usd,
                "total_rate_limit_errors": self.total_rate_limit_errors,
                "per_agent": self._per_agent_usage,
            }
```

- [ ] **Step 6: Add `agent_id` parameter to `chat()`**

Change the `chat` method signature from:

```python
    async def chat(
        self,
        user_message: str,
        system_prompt: str = "...",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
    ) -> str:
```

To (add `agent_id` at the end):

```python
    async def chat(
        self,
        user_message: str,
        system_prompt: str = "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
    ) -> str:
```

- [ ] **Step 7: Accumulate per-agent totals inside `chat()`**

At the start of `chat()`, before the tool loop, add the per-agent `requests` and `last_run` increment:

```python
        if agent_id:
            if agent_id not in self._per_agent_usage:
                self._per_agent_usage[agent_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                }
            self._per_agent_usage[agent_id]["requests"] += 1
            self._per_agent_usage[agent_id]["last_run"] = datetime.now(timezone.utc).isoformat()
```

Inside the tool loop, after the existing lines that accumulate global totals (lines 210-216):

```python
            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            self.total_input_tokens += inp
            self.total_output_tokens += out
            self.total_requests += 1
            prices = _PRICING.get(effective_model, _PRICING["claude-sonnet-4-6"])
            self.total_cost_usd += (inp * prices["input"] + out * prices["output"]) / 1_000_000
            self._save_usage()
```

Add immediately after `self._save_usage()`:

```python
            if agent_id and agent_id in self._per_agent_usage:
                pau = self._per_agent_usage[agent_id]
                pau["input_tokens"] += inp
                pau["output_tokens"] += out
                pau["cost_usd"] += (inp * prices["input"] + out * prices["output"]) / 1_000_000
```

- [ ] **Step 8: Add `get_agent_usage` and `reset_agent_usage` methods**

Add after `reset_usage()` method:

```python
    def get_agent_usage(self, agent_id: str) -> dict:
        """Return usage stats for a specific agent. Returns zero-filled dict if not found."""
        return dict(self._per_agent_usage.get(agent_id, {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
        }))

    def reset_agent_usage(self, agent_id: str) -> None:
        """Reset usage counters for a specific agent."""
        self._per_agent_usage[agent_id] = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
        }
        self._save_usage()
```

- [ ] **Step 9: Run tests — verify they pass**

```
pytest tests/test_claude_runner.py::test_get_agent_usage_returns_zeros_for_unknown_agent tests/test_claude_runner.py::test_per_agent_usage_accumulates_after_chat tests/test_claude_runner.py::test_reset_agent_usage_clears_counters tests/test_claude_runner.py::test_per_agent_usage_persists_and_reloads -v
```

Expected: all PASS.

- [ ] **Step 10: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add hiris/app/claude_runner.py tests/test_claude_runner.py
git commit -m "$(cat <<'EOF'
feat: per-agent usage accumulation in ClaudeRunner

chat() accepts optional agent_id; accumulates input/output tokens,
cost, requests and last_run per agent in _per_agent_usage dict.
Persisted in usage.json under "per_agent" key. Backward compatible.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Pass agent_id from AgentEngine to chat()

**Files:**
- Modify: `hiris/app/agent_engine.py`

- [ ] **Step 1: Update the `chat()` call in `_run_agent`**

Find the `chat()` call in `_run_agent` (around line 330):

```python
            result = await self._claude_runner.chat(
                user_message=user_message,
                system_prompt=effective_prompt,
                allowed_tools=agent.allowed_tools or None,
                allowed_entities=agent.allowed_entities or None,
                allowed_services=agent.allowed_services or None,
                model=agent.model,
                max_tokens=agent.max_tokens,
                agent_type=agent.type,
                restrict_to_home=agent.restrict_to_home,
                require_confirmation=agent.require_confirmation,
            )
```

Add `agent_id=agent.id` as the last keyword argument:

```python
            result = await self._claude_runner.chat(
                user_message=user_message,
                system_prompt=effective_prompt,
                allowed_tools=agent.allowed_tools or None,
                allowed_entities=agent.allowed_entities or None,
                allowed_services=agent.allowed_services or None,
                model=agent.model,
                max_tokens=agent.max_tokens,
                agent_type=agent.type,
                restrict_to_home=agent.restrict_to_home,
                require_confirmation=agent.require_confirmation,
                agent_id=agent.id,
            )
```

- [ ] **Step 2: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add hiris/app/agent_engine.py
git commit -m "$(cat <<'EOF'
feat: pass agent_id to chat() for per-agent usage attribution

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Per-agent usage HTTP endpoints

**Files:**
- Modify: `hiris/app/api/handlers_agents.py`
- Modify: `hiris/app/server.py`
- Modify: `tests/test_handlers_agents.py` (or create if not yet done)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_handlers_agents.py`:

```python
@pytest.mark.asyncio
async def test_get_agent_usage_returns_stats():
    from unittest.mock import MagicMock, AsyncMock
    from aiohttp.test_utils import make_mocked_request
    from hiris.app.api.handlers_agents import handle_get_agent_usage

    runner = MagicMock()
    runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 1000, "output_tokens": 400,
        "requests": 5, "cost_usd": 0.005, "last_run": "2026-04-21T10:00:00Z",
    })
    engine = MagicMock()
    engine.get_agent.return_value = MagicMock(id="agent-1")

    app = MagicMock()
    def getitem(k):
        if k == "claude_runner": return runner
        if k == "engine": return engine
        return None
    app.__getitem__ = MagicMock(side_effect=getitem)

    request = make_mocked_request("GET", "/api/agents/agent-1/usage", app=app)
    request.match_info = {"agent_id": "agent-1"}

    import json
    resp = await handle_get_agent_usage(request)
    data = json.loads(resp.body)
    assert data["requests"] == 5
    assert data["input_tokens"] == 1000
    assert "cost_eur" in data


@pytest.mark.asyncio
async def test_reset_agent_usage():
    from unittest.mock import MagicMock, AsyncMock
    from aiohttp.test_utils import make_mocked_request
    from hiris.app.api.handlers_agents import handle_reset_agent_usage

    runner = MagicMock()
    runner.reset_agent_usage = MagicMock()
    engine = MagicMock()
    engine.get_agent.return_value = MagicMock(id="agent-1")

    app = MagicMock()
    def getitem(k):
        if k == "claude_runner": return runner
        if k == "engine": return engine
        return None
    app.__getitem__ = MagicMock(side_effect=getitem)

    request = make_mocked_request("POST", "/api/agents/agent-1/usage/reset", app=app)
    request.match_info = {"agent_id": "agent-1"}

    resp = await handle_reset_agent_usage(request)
    assert resp.status == 200
    runner.reset_agent_usage.assert_called_once_with("agent-1")
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_handlers_agents.py::test_get_agent_usage_returns_stats -v
```

Expected: `ImportError` — `handle_get_agent_usage` not defined.

- [ ] **Step 3: Implement the two handlers**

Add to the end of `hiris/app/api/handlers_agents.py`:

```python
_EUR_RATE = 0.92

async def handle_get_agent_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    engine = request.app["engine"]
    if not engine.get_agent(agent_id):
        return web.json_response({"error": "Not found"}, status=404)
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    usage = runner.get_agent_usage(agent_id)
    cost_usd = usage.get("cost_usd", 0.0)
    return web.json_response({
        "agent_id": agent_id,
        "requests": usage.get("requests", 0),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_usd * _EUR_RATE, 6),
        "last_run": usage.get("last_run"),
    })


async def handle_reset_agent_usage(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    engine = request.app["engine"]
    if not engine.get_agent(agent_id):
        return web.json_response({"error": "Not found"}, status=404)
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_agent_usage(agent_id)
    return web.json_response({"reset": True, "agent_id": agent_id})
```

- [ ] **Step 4: Register the routes in server.py**

Add the two new imports to the existing import line in `server.py`:

```python
from .api.handlers_agents import (
    handle_list_agents, handle_create_agent, handle_get_agent,
    handle_update_agent, handle_delete_agent, handle_run_agent,
    handle_list_entities, handle_get_agent_usage, handle_reset_agent_usage,
)
```

Add the two routes in `create_app()` after `handle_run_agent`:

```python
    app.router.add_get("/api/agents/{agent_id}/usage", handle_get_agent_usage)
    app.router.add_post("/api/agents/{agent_id}/usage/reset", handle_reset_agent_usage)
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_handlers_agents.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hiris/app/api/handlers_agents.py hiris/app/server.py tests/test_handlers_agents.py
git commit -m "$(cat <<'EOF'
feat: add GET/POST /api/agents/{id}/usage endpoints

GET returns per-agent token/cost stats, POST resets them.
Both 404 if agent not found, 503 if runner not configured.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: "Consumi" collapsible section in config.html

**Files:**
- Modify: `hiris/app/static/config.html`

Add a `<details>` section immediately after the existing `<details class="log-section">` in the agent form (line 493-496). The section shows:
- A stats grid: Richieste, Token IN, Token OUT, Costo totale
- Last run timestamp
- Buttons: "Azzera contatori agente" + "Disabilita/Riabilita agente"
- Budget limit input (number, in EUR, 0 = nessun limite)

- [ ] **Step 1: Add the HTML block**

Find:

```html
        <details class="log-section">
          <summary>Log esecuzioni (ultime 20)</summary>
          <div id="log-body"><div class="log-empty">Nessuna esecuzione registrata.</div></div>
        </details>
```

After (not replacing) this block, add:

```html
        <details class="usage-section" id="agent-usage-section">
          <summary>📊 Consumi agente</summary>
          <div class="usage-content">
            <div class="usage-grid">
              <div class="usage-stat"><div class="us-val" id="u-ag-requests">—</div><div class="us-label">Richieste</div></div>
              <div class="usage-stat"><div class="us-val" id="u-ag-input">—</div><div class="us-label">Token IN</div></div>
              <div class="usage-stat"><div class="us-val" id="u-ag-output">—</div><div class="us-label">Token OUT</div></div>
              <div class="usage-stat"><div class="us-val" id="u-ag-cost">—</div><div class="us-label">Costo stimato</div></div>
            </div>
            <div class="usage-last-run">Ultima esecuzione: <span id="u-ag-last-run">—</span></div>
            <div class="usage-actions">
              <button type="button" id="u-ag-reset-btn" class="btn-usage-reset">↺ Azzera contatori</button>
              <button type="button" id="u-ag-toggle-btn" class="btn-usage-block">⊘ Blocca agente</button>
            </div>
            <div class="usage-budget">
              <label>Budget massimo (€, 0 = nessun limite)</label>
              <input type="number" id="u-ag-budget" min="0" step="0.01" value="0" placeholder="0.00">
              <button type="button" id="u-ag-budget-save-btn" class="btn-usage-reset">Salva soglia</button>
            </div>
          </div>
        </details>
```

- [ ] **Step 2: Add CSS for usage section**

In the `<style>` block, add:

```css
/* Per-agent usage section */
.usage-section { border: 1px solid var(--border); border-radius: 6px; margin-top: 12px; }
.usage-section summary {
  padding: 10px 14px; cursor: pointer; font-size: 13px; color: var(--text-muted);
  list-style: none; user-select: none;
}
.usage-section summary::-webkit-details-marker { display: none; }
.usage-section[open] summary { border-bottom: 1px solid var(--border); color: var(--text); }
.usage-content { padding: 14px; }
.usage-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px;
}
.usage-stat {
  background: var(--surface-3); border-radius: 6px; padding: 10px 8px; text-align: center;
}
.us-val { font-size: 18px; font-weight: 600; color: var(--accent); }
.us-label { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
.usage-last-run { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
.usage-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.btn-usage-reset {
  padding: 6px 14px; border-radius: 5px; border: 1px solid var(--border);
  background: var(--surface-4); color: var(--text-muted); font-size: 12px; cursor: pointer;
}
.btn-usage-reset:hover { background: var(--surface-hover); color: var(--text); }
.btn-usage-block {
  padding: 6px 14px; border-radius: 5px; border: 1px solid var(--danger-bg);
  background: #7f1d1d22; color: var(--danger-text); font-size: 12px; cursor: pointer;
}
.btn-usage-block:hover { background: var(--danger-bg); }
.btn-usage-enable {
  padding: 6px 14px; border-radius: 5px; border: 1px solid #16532244;
  background: #16532222; color: var(--success); font-size: 12px; cursor: pointer;
}
.btn-usage-enable:hover { background: #16532244; }
.usage-budget { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.usage-budget label { font-size: 12px; color: var(--text-muted); }
.usage-budget input {
  width: 80px; padding: 4px 8px; background: var(--input-bg); border: 1px solid var(--border);
  color: var(--text); border-radius: 4px; font-size: 13px;
}
```

- [ ] **Step 3: Add JS for usage section**

Before the closing `</script>` tag, add:

```javascript
// ── Per-agent usage section ───────────────────────────────────────────────────
async function loadAgentUsage(agentId) {
  if (!agentId) return;
  try {
    var r = await fetch('api/agents/' + agentId + '/usage');
    if (!r.ok) return;
    var d = await r.json();
    document.getElementById('u-ag-requests').textContent = d.requests ?? '—';
    document.getElementById('u-ag-input').textContent = fmtNum(d.input_tokens);
    document.getElementById('u-ag-output').textContent = fmtNum(d.output_tokens);
    document.getElementById('u-ag-cost').textContent = d.cost_eur != null ? '€' + d.cost_eur.toFixed(4) : '—';
    var lr = d.last_run ? new Date(d.last_run).toLocaleString('it-IT') : 'mai';
    document.getElementById('u-ag-last-run').textContent = lr;
  } catch(e) {}
}

document.getElementById('u-ag-reset-btn').onclick = async function() {
  if (!currentId || !confirm('Azzerare i contatori di consumo per questo agente?')) return;
  try {
    await fetch('api/agents/' + currentId + '/usage/reset', { method: 'POST' });
    await loadAgentUsage(currentId);
  } catch(e) {}
};

document.getElementById('u-ag-toggle-btn').onclick = async function() {
  if (!currentId) return;
  var agent = agents.find(function(a) { return a.id === currentId; });
  if (!agent) return;
  var newEnabled = !agent.enabled;
  var confirmMsg = newEnabled
    ? 'Riabilitare questo agente?'
    : 'Bloccare questo agente? Non verrà più eseguito automaticamente.';
  if (!confirm(confirmMsg)) return;
  try {
    var r = await fetch('api/agents/' + currentId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newEnabled }),
    });
    var updated = await r.json();
    await loadAgents();
    openAgent(updated);
  } catch(e) {}
};

document.getElementById('u-ag-budget-save-btn').onclick = async function() {
  if (!currentId) return;
  var budget = parseFloat(document.getElementById('u-ag-budget').value) || 0;
  try {
    await fetch('api/agents/' + currentId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget_eur_limit: budget }),
    });
    alert(budget > 0 ? 'Soglia di budget salvata: €' + budget.toFixed(2) : 'Nessun limite di budget impostato.');
  } catch(e) {}
};

function updateAgentUsageToggleBtn(agent) {
  var btn = document.getElementById('u-ag-toggle-btn');
  if (!agent) return;
  if (agent.enabled) {
    btn.textContent = '⊘ Blocca agente';
    btn.className = 'btn-usage-block';
  } else {
    btn.textContent = '✓ Riabilita agente';
    btn.className = 'btn-usage-enable';
  }
}
```

- [ ] **Step 4: Call `loadAgentUsage` and `updateAgentUsageToggleBtn` from `openAgent`**

In the `openAgent` function, add at the end:

```javascript
      loadAgentUsage(a.id);
      updateAgentUsageToggleBtn(a);
      document.getElementById('u-ag-budget').value = a.budget_eur_limit || 0;
```

- [ ] **Step 5: Add `budget_eur_limit` to Agent dataclass and UPDATABLE_FIELDS**

In `hiris/app/agent_engine.py`, in the Agent dataclass, add after the `actions` field:

```python
    budget_eur_limit: float = 0.0
```

Add `"budget_eur_limit"` to `UPDATABLE_FIELDS`:

```python
UPDATABLE_FIELDS = {
    ...,
    "actions",
    "budget_eur_limit",
}
```

- [ ] **Step 6: Manual smoke test**

1. Open agent designer, select an agent
2. Open "📊 Consumi agente" section
3. Stats show — (no usage yet)
4. Run the agent → refresh → stats populate with real token counts
5. Click "↺ Azzera contatori" → stats reset to 0
6. Click "⊘ Blocca agente" → agent becomes disabled, button changes to "✓ Riabilita agente"
7. Click "✓ Riabilita agente" → agent re-enabled
8. Set budget €0.01, click "Salva soglia" → next run that exceeds budget auto-disables (see Task 13)

- [ ] **Step 7: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add hiris/app/static/config.html hiris/app/agent_engine.py
git commit -m "$(cat <<'EOF'
feat: per-agent usage tab in agent designer

Shows lifetime token and cost stats per agent. Block/unblock button,
reset counter button, and budget threshold field (saved to agent).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Budget auto-disable

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Modify: `tests/test_agent_engine.py`

When `budget_eur_limit > 0` and the agent's cumulative cost (in EUR) reaches or exceeds the limit after a run, the engine automatically disables the agent.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_engine.py`:

```python
@pytest.mark.asyncio
async def test_agent_auto_disabled_when_budget_exceeded(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_agent({
        "name": "Budget Test", "type": "monitor",
        "trigger": {"type": "manual"},
        "budget_eur_limit": 0.001,  # €0.001 — very low, will be exceeded
    })

    mock_runner = MagicMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    # Simulate usage exceeding budget
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 5000, "output_tokens": 2000,
        "requests": 1, "cost_usd": 0.005,  # > €0.001 limit
        "last_run": "2026-04-21T10:00:00Z",
    })
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)

    # Agent should be auto-disabled after budget exceeded
    assert agent.enabled is False

    await engine.stop()


@pytest.mark.asyncio
async def test_agent_not_disabled_when_budget_not_exceeded(tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    await engine.start()

    agent = engine.create_agent({
        "name": "No Budget Test", "type": "monitor",
        "trigger": {"type": "manual"},
        "budget_eur_limit": 10.0,  # high limit — will not be exceeded
    })

    mock_runner = MagicMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 100, "output_tokens": 50,
        "requests": 1, "cost_usd": 0.0001,
        "last_run": "2026-04-21T10:00:00Z",
    })
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)

    assert agent.enabled is True  # not disabled

    await engine.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_agent_engine.py::test_agent_auto_disabled_when_budget_exceeded -v
```

Expected: FAIL — auto-disable logic not implemented yet.

- [ ] **Step 3: Implement auto-disable in `_run_agent`**

In `hiris/app/agent_engine.py`, in `_run_agent`, after `self._append_execution_log(...)` and `self._save()`, add:

```python
            # Auto-disable if budget_eur_limit exceeded
            if agent.budget_eur_limit > 0 and self._claude_runner:
                try:
                    usage = self._claude_runner.get_agent_usage(agent.id)
                    cost_eur = usage.get("cost_usd", 0.0) * 0.92
                    if cost_eur >= agent.budget_eur_limit:
                        logger.warning(
                            "Agent %s auto-disabled: cost €%.4f >= limit €%.4f",
                            agent.name, cost_eur, agent.budget_eur_limit,
                        )
                        agent.enabled = False
                        self._save()
                except Exception as exc:
                    logger.warning("Budget check failed for %s: %s", agent.name, exc)
```

Add the same block in the `except` branch (after `self._save()` on failure) to also check budget on failed runs:

```python
            if agent.budget_eur_limit > 0 and self._claude_runner:
                try:
                    usage = self._claude_runner.get_agent_usage(agent.id)
                    cost_eur = usage.get("cost_usd", 0.0) * 0.92
                    if cost_eur >= agent.budget_eur_limit:
                        logger.warning(
                            "Agent %s auto-disabled on failure: cost €%.4f >= limit €%.4f",
                            agent.name, cost_eur, agent.budget_eur_limit,
                        )
                        agent.enabled = False
                        self._save()
                except Exception as exc:
                    logger.warning("Budget check failed for %s: %s", agent.name, exc)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_agent_engine.py::test_agent_auto_disabled_when_budget_exceeded tests/test_agent_engine.py::test_agent_not_disabled_when_budget_not_exceeded -v
```

Expected: both PASS.

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "$(cat <<'EOF'
feat: auto-disable agent when budget_eur_limit is exceeded

After each run, if budget_eur_limit > 0 and cumulative cost in EUR
>= limit, agent is automatically disabled and a warning is logged.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Per-agent cumulative token/cost tracking | Task 9 |
| Lifetime totals survive process restart | Task 9 (persisted in usage.json) |
| AgentEngine attributes usage to agent_id | Task 10 |
| GET /api/agents/{id}/usage endpoint | Task 11 |
| POST /api/agents/{id}/usage/reset endpoint | Task 11 |
| UI: per-agent usage stats section | Task 12 |
| UI: "Blocca/Riabilita agente" button | Task 12 |
| UI: "Azzera contatori" button | Task 12 |
| Budget threshold field per agent | Tasks 12 + 13 |
| Auto-disable on budget exceeded | Task 13 |

### No Placeholders

All steps include actual code. No "TBD" or vague instructions.

### Type Consistency

- `_per_agent_usage` dict schema: `{"input_tokens": int, "output_tokens": int, "requests": int, "cost_usd": float, "last_run": str | None}` — consistent across Task 9 (accumulation), Task 11 (endpoint), Task 12 (JS display).
- `budget_eur_limit: float = 0.0` — added to Agent dataclass in Task 12, checked in Task 13. EUR conversion `* 0.92` consistent with `_EUR_RATE` in `handlers_usage.py`.
- `handle_get_agent_usage` / `handle_reset_agent_usage` — consistent naming with existing handlers pattern.
- `loadAgentUsage(agentId)` JS function — called from `openAgent(a)` with `a.id`.
