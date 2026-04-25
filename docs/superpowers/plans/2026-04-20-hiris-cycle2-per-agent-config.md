# HIRIS Cycle 2 — Per-Agent Config, HomeProfile & Rate-Limit Retry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-agent model/max_tokens/restrict_to_home, inject a live HomeProfile snapshot in every system prompt, and add rate-limit retry with error tracking.

**Architecture:** Agent dataclass gains three new fields; ClaudeRunner.chat() accepts them per-call (removing the global restrict_to_home from __init__); a new `home_profile.py` generates a ~200-token state summary injected automatically; an inner retry loop in ClaudeRunner handles 429/529 with exponential back-off; config.html gets a model selector, Tab Azioni guided checkboxes replacing the services textarea, and the five missing tools.

**Tech Stack:** Python 3.11, aiohttp, anthropic SDK (APIStatusError), fastembed (existing), vanilla JS/HTML

---

## File Map

| File | Change |
|---|---|
| `hiris/app/agent_engine.py` | Add `model`, `max_tokens`, `restrict_to_home` to Agent + serialization |
| `hiris/app/claude_runner.py` | `AUTO_MODEL_MAP`, `resolve_model()`, `_PRICING`, `_call_api()`, per-request params, `total_cost_usd`, `total_rate_limit_errors`, remove `self._restrict_to_home` |
| `hiris/app/api/handlers_chat.py` | Pass `model`, `max_tokens`, `agent_type`, `restrict_to_home` to `runner.chat()` |
| `hiris/app/api/handlers_usage.py` | Remove MODEL import, use `runner.total_cost_usd`, add `total_rate_limit_errors`, fix haiku pricing key |
| `hiris/app/proxy/home_profile.py` | **NEW** — `generate_home_profile(entity_cache) -> str` |
| `hiris/config.yaml` | Remove `restrict_chat_to_home` option/schema; bump version to `0.1.0` |
| `hiris/run.sh` | Remove RESTRICT_CHAT_TO_HOME export; fix version log |
| `hiris/app/server.py` | Remove restrict_to_home env read + ClaudeRunner param |
| `hiris/app/static/config.html` | TOOLS + 5 missing tools; model/max_tokens/restrict fieldset; Tab Azioni |
| `tests/test_agent_engine.py` | Tests for new Agent fields |
| `tests/test_claude_runner.py` | Tests for resolve_model, per-request params, retry, home profile injection |
| `tests/test_home_profile.py` | **NEW** — unit tests for generate_home_profile |
| `tests/test_api.py` | Update version assertion to `0.1.0` |

---

## Task 1: Agent dataclass — model, max_tokens, restrict_to_home

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Test: `tests/test_agent_engine.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_agent_engine.py`:

```python
def test_agent_model_defaults_to_auto(engine):
    agent = engine.create_agent({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.model == "auto"
    assert agent.max_tokens == 4096
    assert agent.restrict_to_home is False


def test_agent_per_agent_config_persists(engine):
    agent = engine.create_agent({
        "name": "Haiku Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "restrict_to_home": True,
    })
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
    assert loaded.model == "claude-haiku-4-5-20251001"
    assert loaded.max_tokens == 1024
    assert loaded.restrict_to_home is True


def test_agent_update_model_and_max_tokens(engine):
    agent = engine.create_agent({
        "name": "Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_agent(agent.id, {"model": "claude-sonnet-4-6", "max_tokens": 2048})
    assert updated.model == "claude-sonnet-4-6"
    assert updated.max_tokens == 2048
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_engine.py::test_agent_model_defaults_to_auto -xvs
```

Expected: `AttributeError: 'Agent' object has no attribute 'model'`

- [ ] **Step 3: Add fields to Agent dataclass**

In `hiris/app/agent_engine.py`, find the `Agent` dataclass (line ~18) and add three fields after `is_default`:

```python
@dataclass
class Agent:
    id: str
    name: str
    type: str  # monitor | reactive | preventive | chat
    trigger: dict
    system_prompt: str
    allowed_tools: list[str]
    enabled: bool
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    strategic_context: str = ""
    allowed_entities: list[str] = field(default_factory=list)
    allowed_services: list[str] = field(default_factory=list)
    is_default: bool = False
    model: str = "auto"
    max_tokens: int = 4096
    restrict_to_home: bool = False
```

- [ ] **Step 4: Update UPDATABLE_FIELDS**

```python
UPDATABLE_FIELDS = {
    "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
    "strategic_context", "allowed_entities", "allowed_services",
    "model", "max_tokens", "restrict_to_home",
}
```

- [ ] **Step 5: Update _load() to deserialize new fields**

In `_load()`, in the `Agent(...)` constructor call (lines ~76-90), add after `allowed_services=...`:

```python
model=raw.get("model", "auto"),
max_tokens=raw.get("max_tokens", 4096),
restrict_to_home=raw.get("restrict_to_home", False),
```

- [ ] **Step 6: Update create_agent() to accept new fields**

In `create_agent()`, in the `Agent(...)` constructor call, add after `allowed_services=...`:

```python
model=data.get("model", "auto"),
max_tokens=data.get("max_tokens", 4096),
restrict_to_home=data.get("restrict_to_home", False),
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_agent_engine.py -xvs
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "feat: add model, max_tokens, restrict_to_home to Agent dataclass"
```

---

## Task 2: ClaudeRunner — per-request params, AUTO_MODEL_MAP, remove global restrict

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests for resolve_model and per-request params**

Add to `tests/test_claude_runner.py` (at the top with other imports):

```python
import anthropic
```

Then add tests:

```python
from hiris.app.claude_runner import resolve_model, AUTO_MODEL_MAP


def test_resolve_model_auto_chat_returns_sonnet():
    assert resolve_model("auto", "chat") == "claude-sonnet-4-6"


def test_resolve_model_auto_monitor_returns_haiku():
    assert resolve_model("auto", "monitor") == "claude-haiku-4-5-20251001"


def test_resolve_model_auto_reactive_returns_haiku():
    assert resolve_model("auto", "reactive") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_overrides_auto():
    assert resolve_model("claude-sonnet-4-6", "monitor") == "claude-sonnet-4-6"


def test_resolve_model_auto_unknown_type_defaults_to_sonnet():
    assert resolve_model("auto", "unknown_type") == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_chat_uses_resolved_model_for_monitor(runner):
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 10
    success.usage.output_tokens = 5
    runner._client.messages.create = AsyncMock(return_value=success)
    await runner.chat("Test", model="auto", agent_type="monitor")
    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_claude_runner.py::test_resolve_model_auto_chat_returns_sonnet -xvs
```

Expected: `ImportError: cannot import name 'resolve_model' from 'hiris.app.claude_runner'`

- [ ] **Step 3: Add AUTO_MODEL_MAP, resolve_model, _PRICING to claude_runner.py**

After the existing `MAX_TOOL_ITERATIONS = 10` line, add:

```python
import asyncio

MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]

AUTO_MODEL_MAP: dict[str, str] = {
    "chat": "claude-sonnet-4-6",
    "monitor": "claude-haiku-4-5-20251001",
    "reactive": "claude-haiku-4-5-20251001",
    "preventive": "claude-haiku-4-5-20251001",
}

_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":          {"input": 3.0,  "output": 15.0},
    "claude-opus-4-7":            {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001":  {"input": 0.25, "output": 1.25},
}


def resolve_model(model: str, agent_type: str) -> str:
    if model == "auto":
        return AUTO_MODEL_MAP.get(agent_type, MODEL)
    return model
```

Note: `import asyncio` goes at the top of the file with other stdlib imports.

- [ ] **Step 4: Update ClaudeRunner.__init__ — remove restrict_to_home param**

Current `__init__` signature:
```python
def __init__(
    self,
    api_key: str,
    ha_client: HAClient,
    notify_config: dict,
    restrict_to_home: bool = False,
    usage_path: str = "",
    entity_cache=None,
    embedding_index=None,
) -> None:
```

New signature (remove `restrict_to_home=False`, remove `self._restrict_to_home = restrict_to_home`):
```python
def __init__(
    self,
    api_key: str,
    ha_client: HAClient,
    notify_config: dict,
    usage_path: str = "",
    entity_cache=None,
    embedding_index=None,
) -> None:
    self._client = anthropic.AsyncAnthropic(api_key=api_key)
    self._ha = ha_client
    self._notify_config = notify_config
    self._usage_path = usage_path
    self._cache = entity_cache
    self._index = embedding_index
    self.last_tool_calls: list[dict] = []
    self.total_input_tokens: int = 0
    self.total_output_tokens: int = 0
    self.total_requests: int = 0
    self.total_cost_usd: float = 0.0
    self.total_rate_limit_errors: int = 0
    self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
    self._load_usage()
```

- [ ] **Step 5: Update _load_usage, _save_usage, reset_usage for new counters**

In `_load_usage()`, add after existing loads:
```python
self.total_cost_usd = data.get("total_cost_usd", 0.0)
self.total_rate_limit_errors = data.get("total_rate_limit_errors", 0)
```

In `_save_usage()`, add to `data` dict:
```python
"total_cost_usd": self.total_cost_usd,
"total_rate_limit_errors": self.total_rate_limit_errors,
```

In `reset_usage()`, add:
```python
self.total_cost_usd = 0.0
self.total_rate_limit_errors = 0
```

- [ ] **Step 6: Update chat() signature — add per-request params**

New `chat()` signature:

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
) -> str:
    self.last_tool_calls = []
    effective_system = system_prompt
    if restrict_to_home:
        effective_system = f"{system_prompt}\n\n---\n\n{RESTRICT_PROMPT}"
    effective_model = resolve_model(model, agent_type)
    tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
    messages: list[dict] = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            response = await self._call_api(
                model=effective_model,
                max_tokens=max_tokens,
                system=effective_system,
                tools=tools,
                messages=messages,
            )
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            return f"Claude API error: {exc}"

        inp = response.usage.input_tokens
        out = response.usage.output_tokens
        self.total_input_tokens += inp
        self.total_output_tokens += out
        self.total_requests += 1
        prices = _PRICING.get(effective_model, _PRICING["claude-sonnet-4-6"])
        self.total_cost_usd += (inp * prices["input"] + out * prices["output"]) / 1_000_000
        self._save_usage()

        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return "\n".join(text_blocks)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await self._dispatch_tool(
                        block.name, block.input,
                        allowed_entities=allowed_entities,
                        allowed_services=allowed_services,
                    )
                    self.last_tool_calls.append({"tool": block.name, "input": block.input})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return "\n".join(text_blocks) if text_blocks else f"Stopped: {response.stop_reason}"

    return "Max tool iterations reached."
```

- [ ] **Step 7: Add _call_api helper method (rate limit retry)**

Add after `chat()`:

```python
async def _call_api(self, **kwargs) -> Any:
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 529) and attempt < MAX_RETRIES:
                self.total_rate_limit_errors += 1
                delay = RETRY_DELAYS[attempt]
                logger.warning("Rate limit (attempt %d/%d), retry in %ds", attempt + 1, MAX_RETRIES, delay)
                await asyncio.sleep(delay)
            else:
                raise
```

- [ ] **Step 8: Update restricted_runner fixture in test_claude_runner.py**

Replace the fixture and two tests that reference `restrict_to_home=True` in constructor:

```python
@pytest.fixture
def restricted_runner(mock_ha):
    with patch("anthropic.AsyncAnthropic"):
        return ClaudeRunner(
            api_key="test-key",
            ha_client=mock_ha,
            notify_config={},
        )


@pytest.mark.asyncio
async def test_restrict_to_home_injects_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao", restrict_to_home=True)
    system_used = captured[0]["system"]
    assert "SOLO" in system_used or "solo" in system_used.lower()
    assert RESTRICT_PROMPT in system_used


@pytest.mark.asyncio
async def test_restrict_to_home_false_does_not_inject(runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Prompt originale", restrict_to_home=False)
    assert captured[0]["system"] == "Prompt originale"
```

- [ ] **Step 9: Run all tests to verify they pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_claude_runner.py -xvs
```

Expected: all pass

- [ ] **Step 10: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/claude_runner.py tests/test_claude_runner.py
git commit -m "feat: per-request model/max_tokens/restrict_to_home in ClaudeRunner, resolve_model, rate-limit retry skeleton"
```

---

## Task 3: Wire handlers_chat.py and _run_agent() with per-agent config

**Files:**
- Modify: `hiris/app/api/handlers_chat.py`
- Modify: `hiris/app/agent_engine.py` (only `_run_agent`)
- Test: `tests/test_api.py` (one new test), `tests/test_agent_engine.py` (one new test)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_chat_passes_model_to_runner(client):
    from hiris.app.agent_engine import Agent
    engine = client.app["engine"]
    engine._agents["agent-haiku-001"] = Agent(
        id="agent-haiku-001", name="Haiku Agent", type="monitor",
        trigger={"type": "manual"}, system_prompt="Monitor test",
        allowed_tools=[], enabled=True, is_default=False,
        model="claude-haiku-4-5-20251001", max_tokens=1024, restrict_to_home=False,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="ok")

    await client.post("/api/chat", json={"message": "test", "agent_id": "agent-haiku-001"})

    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 1024
    assert call_kwargs["agent_type"] == "monitor"
```

Add to `tests/test_agent_engine.py`:

```python
@pytest.mark.asyncio
async def test_run_agent_passes_per_agent_config_to_runner(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="result")
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Config Test", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Test prompt", "allowed_tools": [], "enabled": False,
        "model": "claude-haiku-4-5-20251001", "max_tokens": 512, "restrict_to_home": True,
    })
    await engine._run_agent(agent)

    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 512
    assert call_kwargs["agent_type"] == "monitor"
    assert call_kwargs["restrict_to_home"] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_api.py::test_chat_passes_model_to_runner tests/test_agent_engine.py::test_run_agent_passes_per_agent_config_to_runner -xvs
```

Expected: `AssertionError` — model/max_tokens/agent_type not in kwargs

- [ ] **Step 3: Update handlers_chat.py**

Replace the `runner.chat(...)` call at the end of `handle_chat`:

```python
    # resolve per-agent config (with fallbacks for the no-agent path)
    agent_model = getattr(agent, "model", "auto") if agent else "auto"
    agent_max_tokens = getattr(agent, "max_tokens", 4096) if agent else 4096
    agent_type = getattr(agent, "type", "chat") if agent else "chat"
    agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False

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
    )
```

- [ ] **Step 4: Update _run_agent() in agent_engine.py**

Replace the `await self._claude_runner.chat(...)` call:

```python
            result = await self._claude_runner.chat(
                user_message=f"[Agent trigger: {agent.trigger.get('type')}]",
                system_prompt=effective_prompt,
                allowed_tools=agent.allowed_tools or None,
                allowed_entities=agent.allowed_entities or None,
                allowed_services=agent.allowed_services or None,
                model=agent.model,
                max_tokens=agent.max_tokens,
                agent_type=agent.type,
                restrict_to_home=agent.restrict_to_home,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_api.py tests/test_agent_engine.py -xvs
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/api/handlers_chat.py hiris/app/agent_engine.py tests/test_api.py tests/test_agent_engine.py
git commit -m "feat: wire per-agent model/max_tokens/restrict_to_home through handlers and run_agent"
```

---

## Task 4: Remove global restrict_to_home from config.yaml, run.sh, server.py

**Files:**
- Modify: `hiris/config.yaml`
- Modify: `hiris/run.sh`
- Modify: `hiris/app/server.py`

No new tests (existing tests prove nothing broke).

- [ ] **Step 1: Edit config.yaml — remove restrict_chat_to_home**

Remove the two lines from `config.yaml`:
- In `options:`: `restrict_chat_to_home: false`
- In `schema:`: `restrict_chat_to_home: bool`

Resulting options/schema blocks:
```yaml
options:
  claude_api_key: ""
  log_level: "info"
  theme: "auto"
schema:
  claude_api_key: password
  log_level: "list(debug|info|warning|error)"
  theme: "list(light|dark|auto)"
```

- [ ] **Step 2: Edit run.sh — remove RESTRICT_CHAT_TO_HOME, fix log line**

New content:
```bash
#!/usr/bin/with-contenv bashio

export LOG_LEVEL=$(bashio::config 'log_level' 'info')
export CLAUDE_API_KEY=$(bashio::config 'claude_api_key')
export THEME=$(bashio::config 'theme' 'auto')

bashio::log.info "Starting HIRIS v0.1.0"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Theme: ${THEME}"

cd /usr/lib/hiris
exec python3 -m app.main
```

- [ ] **Step 3: Edit server.py — remove restrict_to_home env read and ClaudeRunner param**

In `_on_startup`, remove these three lines:
```python
restrict_raw = os.environ.get("RESTRICT_CHAT_TO_HOME", "false").lower()
restrict_to_home = restrict_raw in ("true", "1", "yes")
```
And remove the `restrict_to_home=restrict_to_home,` kwarg from the `ClaudeRunner(...)` call.

The ClaudeRunner instantiation becomes:
```python
        runner = ClaudeRunner(
            api_key=api_key,
            ha_client=ha_client,
            notify_config=notify_config,
            usage_path=usage_path,
            entity_cache=entity_cache,
            embedding_index=embedding_index,
        )
```

- [ ] **Step 4: Run full test suite**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/ -x
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/config.yaml hiris/run.sh hiris/app/server.py
git commit -m "feat: remove global restrict_to_home — now per-agent field"
```

---

## Task 5: HomeProfile — new proxy/home_profile.py + inject in chat()

**Files:**
- Create: `hiris/app/proxy/home_profile.py`
- Modify: `hiris/app/claude_runner.py`
- Create: `tests/test_home_profile.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_home_profile.py`:

```python
from unittest.mock import MagicMock
from hiris.app.proxy.home_profile import generate_home_profile


def _make_cache(entities):
    cache = MagicMock()
    cache.get_all_useful.return_value = entities
    return cache


def test_generate_home_profile_starts_with_casa():
    cache = _make_cache([])
    result = generate_home_profile(cache)
    assert result.startswith("CASA [aggiornato")


def test_generate_home_profile_counts_on_entities():
    cache = _make_cache([
        {"id": "light.living", "state": "on",  "name": "Living", "unit": ""},
        {"id": "light.kitchen","state": "on",  "name": "Kitchen","unit": ""},
        {"id": "switch.pump",  "state": "on",  "name": "Pump",   "unit": ""},
        {"id": "sensor.temp",  "state": "22.5","name": "Temp",   "unit": "°C"},
    ])
    result = generate_home_profile(cache)
    assert "Accesi(3):" in result
    assert "light(2)" in result
    assert "switch(1)" in result


def test_generate_home_profile_empty_cache():
    cache = _make_cache([])
    result = generate_home_profile(cache)
    assert "Accesi(0):" in result


def test_generate_home_profile_reports_climate():
    cache = _make_cache([
        {"id": "climate.soggiorno", "state": "heat", "name": "Soggiorno", "unit": ""},
    ])
    result = generate_home_profile(cache)
    assert "Soggiorno: heat" in result


def test_generate_home_profile_no_climate():
    cache = _make_cache([
        {"id": "light.test", "state": "on", "name": "Test", "unit": ""},
    ])
    result = generate_home_profile(cache)
    assert "Clima:" in result
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_home_profile.py -xvs
```

Expected: `ModuleNotFoundError: No module named 'hiris.app.proxy.home_profile'`

- [ ] **Step 3: Create hiris/app/proxy/home_profile.py**

```python
from __future__ import annotations
from datetime import datetime, timezone
from .entity_cache import EntityCache


def generate_home_profile(entity_cache: EntityCache) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M")
    entities = entity_cache.get_all_useful()

    on_entities = [e for e in entities if e.get("state") == "on"]
    on_by_domain: dict[str, int] = {}
    for e in on_entities:
        domain = e["id"].split(".")[0]
        on_by_domain[domain] = on_by_domain.get(domain, 0) + 1

    on_count = len(on_entities)
    on_summary = (
        ", ".join(f"{d}({n})" for d, n in sorted(on_by_domain.items()))
        if on_by_domain else "nessuno"
    )

    climate = [e for e in entities if e["id"].startswith("climate.")]
    climate_str = (
        ", ".join(f"{(e.get('name') or e['id'])}: {e['state']}" for e in climate[:3])
        if climate else "n/a"
    )

    return (
        f"CASA [aggiornato {now}]:\n"
        f"Accesi({on_count}): {on_summary}\n"
        f"Clima: {climate_str}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_home_profile.py -xvs
```

Expected: all pass

- [ ] **Step 5: Write failing tests for chat() injection**

Add to `tests/test_claude_runner.py`:

```python
@pytest.mark.asyncio
async def test_chat_injects_home_profile_when_cache_available(runner):
    cache = MagicMock()
    cache.get_all_useful.return_value = [
        {"id": "light.test", "state": "on", "name": "Test", "unit": ""},
    ]
    runner._cache = cache

    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2
    runner._client.messages.create = AsyncMock(return_value=success)

    await runner.chat("Ciao", system_prompt="Base prompt")

    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert "CASA [aggiornato" in call_kwargs["system"]
    assert "Base prompt" in call_kwargs["system"]


@pytest.mark.asyncio
async def test_chat_skips_home_profile_when_no_cache(runner):
    runner._cache = None

    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2
    runner._client.messages.create = AsyncMock(return_value=success)

    await runner.chat("Ciao", system_prompt="Solo prompt")

    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert "CASA" not in call_kwargs["system"]
    assert call_kwargs["system"] == "Solo prompt"
```

- [ ] **Step 6: Run to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_claude_runner.py::test_chat_injects_home_profile_when_cache_available -xvs
```

Expected: `AssertionError: "CASA [aggiornato" not in system`

- [ ] **Step 7: Inject home profile in ClaudeRunner.chat()**

In `chat()`, after the `restrict_to_home` block and before `effective_model = resolve_model(...)`:

```python
    if self._cache is not None:
        from .proxy.home_profile import generate_home_profile
        effective_system = f"{effective_system}\n\n---\n\n{generate_home_profile(self._cache)}"
```

- [ ] **Step 8: Run all tests**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/ -x
```

Expected: all pass (note: `test_restrict_to_home_false_does_not_inject` uses `runner` fixture which has `_cache=None` by default, so no profile is injected — still passes)

- [ ] **Step 9: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/proxy/home_profile.py hiris/app/claude_runner.py tests/test_home_profile.py tests/test_claude_runner.py
git commit -m "feat: HomeProfile snapshot injected in every system prompt"
```

---

## Task 6: Rate limit retry + usage counter + handlers_usage.py fix

**Files:**
- Modify: `hiris/app/claude_runner.py` (already has `_call_api` skeleton from Task 2)
- Modify: `hiris/app/api/handlers_usage.py`
- Test: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests for retry behavior**

Add to `tests/test_claude_runner.py`:

```python
from hiris.app.claude_runner import MAX_RETRIES, RETRY_DELAYS


@pytest.mark.asyncio
async def test_rate_limit_retries_once_and_succeeds(runner):
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 10
    success.usage.output_tokens = 5

    exc_429 = anthropic.APIStatusError(
        "rate limited", response=MagicMock(status_code=429), body={}
    )
    runner._client.messages.create = AsyncMock(side_effect=[exc_429, success])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await runner.chat("Ciao")

    assert result == "ok"
    assert runner.total_rate_limit_errors == 1
    mock_sleep.assert_awaited_once_with(RETRY_DELAYS[0])


@pytest.mark.asyncio
async def test_rate_limit_exhausts_retries_returns_error(runner):
    exc_429 = anthropic.APIStatusError(
        "rate limited", response=MagicMock(status_code=429), body={}
    )
    runner._client.messages.create = AsyncMock(side_effect=exc_429)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await runner.chat("Ciao")

    assert "Claude API error" in result
    assert runner.total_rate_limit_errors == MAX_RETRIES
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_claude_runner.py::test_rate_limit_retries_once_and_succeeds -xvs
```

Expected: fail — `_call_api` doesn't exist yet (skeleton was added in Task 2 body, but if not yet committed, add it now)

Verify `_call_api` is in `claude_runner.py`:
```bash
grep -n "_call_api" /c/Work/Sviluppo/hiris/hiris/app/claude_runner.py
```

If not present (Task 2 code wasn't included), add it now (full implementation from Task 2 Step 7).

- [ ] **Step 3: Run tests to verify retry tests pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_claude_runner.py -xvs
```

Expected: all pass

- [ ] **Step 4: Fix handlers_usage.py**

Replace the entire file:

```python
from aiohttp import web

_EUR_RATE = 0.92  # approximate USD→EUR


async def handle_usage(request: web.Request) -> web.Response:
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)

    inp = getattr(runner, "total_input_tokens", 0)
    out = getattr(runner, "total_output_tokens", 0)
    reqs = getattr(runner, "total_requests", 0)
    rate_errors = getattr(runner, "total_rate_limit_errors", 0)
    cost_usd = getattr(runner, "total_cost_usd", 0.0)
    cost_eur = cost_usd * _EUR_RATE

    return web.json_response({
        "total_requests": reqs,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "total_rate_limit_errors": rate_errors,
        "cost_usd": round(cost_usd, 6),
        "cost_eur": round(cost_eur, 6),
        "last_reset": getattr(runner, "usage_last_reset", None),
    })


async def handle_reset_usage(request: web.Request) -> web.Response:
    runner = request.app.get("claude_runner")
    if runner is None:
        return web.json_response({"error": "runner not configured"}, status=503)
    runner.reset_usage()
    return web.json_response({"reset": True, "last_reset": runner.usage_last_reset})
```

- [ ] **Step 5: Run full test suite**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/ -x
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/claude_runner.py hiris/app/api/handlers_usage.py tests/test_claude_runner.py
git commit -m "feat: rate-limit retry with back-off, per-model cost tracking, fix haiku pricing key"
```

---

## Task 7: config.html UI — model selector, Tab Azioni, missing tools

**Files:**
- Modify: `hiris/app/static/config.html`

No automated tests — verify manually in browser.

- [ ] **Step 1: Add 5 missing tools to TOOLS array (line ~431)**

Replace the `var TOOLS = [...]` block:

```js
    var TOOLS = [
      { id: 'get_entity_states',    label: 'get_entity_states',    desc: 'Legge stato entità HA (luce, clima, sensori…)' },
      { id: 'get_home_status',      label: 'get_home_status',      desc: 'Panoramica compatta di tutti i dispositivi utili' },
      { id: 'get_entities_on',      label: 'get_entities_on',      desc: 'Tutti i dispositivi attualmente accesi' },
      { id: 'search_entities',      label: 'search_entities',      desc: 'Ricerca semantica di entità per linguaggio naturale' },
      { id: 'get_entities_by_domain', label: 'get_entities_by_domain', desc: 'Tutte le entità di un dominio (es. light, sensor)' },
      { id: 'get_area_entities',    label: 'get_area_entities',    desc: 'Scopre stanze/aree e i dispositivi associati' },
      { id: 'get_energy_history',   label: 'get_energy_history',   desc: 'Storico consumi energetici' },
      { id: 'get_weather_forecast', label: 'get_weather_forecast', desc: 'Previsioni meteo (Open-Meteo)' },
      { id: 'call_ha_service',      label: 'call_ha_service',      desc: 'Chiama un servizio HA (luci, clima, switch…)' },
      { id: 'send_notification',    label: 'send_notification',    desc: 'Invia notifica (HA push / Telegram / RetroPanel)' },
      { id: 'get_ha_automations',   label: 'get_ha_automations',   desc: 'Elenco automazioni HA' },
      { id: 'trigger_automation',   label: 'trigger_automation',   desc: 'Avvia un\'automazione HA' },
      { id: 'toggle_automation',    label: 'toggle_automation',    desc: 'Abilita/disabilita automazione HA' },
    ];
```

- [ ] **Step 2: Add ACTIONS array for Tab Azioni (after TOOLS array)**

```js
    var ACTIONS = [
      { id: 'light.*',         label: 'Luci',         desc: 'Accendi, spegni, regola intensità e colore' },
      { id: 'climate.*',       label: 'Clima',        desc: 'Termostati e condizionatori' },
      { id: 'switch.*',        label: 'Switch',       desc: 'Interruttori e prese smart' },
      { id: 'cover.*',         label: 'Tapparelle',   desc: 'Tende, tapparelle e serrande' },
      { id: 'notify.*',        label: 'Notifiche',    desc: 'Servizi di notifica push' },
      { id: 'input_boolean.*', label: 'Input Boolean',desc: 'Toggle e variabili booleane virtuali' },
    ];
```

- [ ] **Step 3: Add buildActionChecks and getSelectedActions functions (after buildToolChecks)**

```js
    function buildActionChecks(selected) {
      var el = document.getElementById('action-checks');
      el.innerHTML = '';
      ACTIONS.forEach(function(a) {
        var item = document.createElement('div');
        item.className = 'tool-item';
        var chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.value = a.id;
        chk.checked = selected.indexOf(a.id) >= 0;
        chk.id = 'action-' + a.id.replace('.*', '');
        var lbl = document.createElement('label');
        lbl.htmlFor = chk.id;
        lbl.appendChild(chk);
        lbl.appendChild(document.createTextNode(' ' + a.label));
        var desc = document.createElement('div');
        desc.className = 'tool-desc';
        desc.textContent = a.desc;
        item.appendChild(lbl);
        item.appendChild(desc);
        el.appendChild(item);
      });
    }

    function getSelectedActions() {
      return Array.from(document.querySelectorAll('#action-checks input:checked')).map(function(i) { return i.value; });
    }
```

- [ ] **Step 4: Add "Modello AI" fieldset to HTML form**

Insert after the closing `</fieldset>` of "Istruzioni" and before the opening `<fieldset>` of "Permessi" (around line 381):

```html
        <fieldset>
          <legend>Modello AI</legend>
          <p class="hint">Seleziona il modello Claude. <em>auto</em> usa Haiku per monitor/reactive/preventive e Sonnet per chat.</p>
          <label>Modello</label>
          <select id="f-model">
            <option value="auto">auto — segue tipo agente</option>
            <option value="claude-haiku-4-5-20251001">Haiku (veloce, economico)</option>
            <option value="claude-sonnet-4-6">Sonnet (più capace)</option>
          </select>
          <label>Max token risposta</label>
          <input type="number" id="f-max-tokens" value="4096" min="256" max="16000">
          <p class="hint">Limita la lunghezza massima della risposta. Default: 4096.</p>
          <label style="flex-direction:row;display:flex;align-items:center;gap:0.5rem;margin-top:0.5rem">
            <input type="checkbox" id="f-restrict"> Limita conversazione alla casa
          </label>
          <p class="hint">L'agente risponderà solo a domande di domotica e smart home.</p>
        </fieldset>
```

- [ ] **Step 5: Replace services textarea in HTML with Tab Azioni checkboxes**

Replace the `<div id="f-services-section" ...>` block:

```html
          <div id="f-services-section" style="margin-top:1rem; display:none">
            <label>Azioni permesse</label>
            <p class="hint">Seleziona i domini su cui questo agente può intervenire tramite call_ha_service.</p>
            <div class="tool-checkboxes" id="action-checks"></div>
          </div>
```

- [ ] **Step 6: Update openAgent() to populate new fields**

In the `openAgent(a)` function, after the existing field assignments, add:

```js
      document.getElementById('f-model').value = a.model || 'auto';
      document.getElementById('f-max-tokens').value = a.max_tokens || 4096;
      document.getElementById('f-restrict').checked = !!a.restrict_to_home;
      buildActionChecks(a.allowed_services || []);
```

Remove the old line:
```js
      document.getElementById('f-services').value = (a.allowed_services || []).join('\n');
```

- [ ] **Step 7: Update new-btn onclick to reset new fields**

In `document.getElementById('new-btn').onclick`, add after `document.getElementById('f-services').value = '';`:

```js
      document.getElementById('f-model').value = 'auto';
      document.getElementById('f-max-tokens').value = 4096;
      document.getElementById('f-restrict').checked = false;
      buildActionChecks([]);
```

Remove the old line:
```js
      document.getElementById('f-services').value = '';
```

- [ ] **Step 8: Update buildPayload() to use new fields**

In `buildPayload()`:
- Remove: `var svcRaw = document.getElementById('f-services').value.trim();`
- Remove: `allowed_services: svcRaw ? svcRaw.split('\n').map(function(s) { return s.trim(); }).filter(Boolean) : [],`
- Add:

```js
      model: document.getElementById('f-model').value,
      max_tokens: parseInt(document.getElementById('f-max-tokens').value) || 4096,
      restrict_to_home: document.getElementById('f-restrict').checked,
      allowed_services: getSelectedActions(),
```

- [ ] **Step 9: Run full Python test suite to confirm no regressions**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/ -x
```

Expected: all pass

- [ ] **Step 10: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/static/config.html
git commit -m "feat: model selector, Tab Azioni, and 5 missing tools in Agent Designer UI"
```

---

## Task 8: Version bump to 0.1.0

**Files:**
- Modify: `hiris/config.yaml` (already set to 0.1.0 if Task 4 was done — verify)
- Modify: `hiris/app/server.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

In `tests/test_api.py`, update:

```python
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/test_api.py::test_health_endpoint -xvs
```

Expected: `AssertionError: assert '0.0.9' == '0.1.0'`

- [ ] **Step 3: Update server.py health response**

Change line in `_handle_health`:
```python
    return web.json_response({"status": "ok", "version": "0.1.0"})
```

- [ ] **Step 4: Verify config.yaml version**

```bash
grep "^version:" /c/Work/Sviluppo/hiris/hiris/config.yaml
```

If still `"0.0.9"`, update to `"0.1.0"`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /c/Work/Sviluppo/hiris && python -m pytest tests/ -x
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /c/Work/Sviluppo/hiris && git add hiris/app/server.py hiris/config.yaml tests/test_api.py
git commit -m "chore: bump version to 0.1.0"
```

---

## Self-Review

**Spec coverage:**
- ✅ Per-agent model/max_tokens/restrict_to_home: Tasks 1, 2, 3
- ✅ AUTO_MODEL_MAP + resolve_model: Task 2
- ✅ Remove global restrict_to_home: Tasks 2, 4
- ✅ HomeProfile injected in system prompt: Task 5
- ✅ Rate limit retry (MAX_RETRIES=3, RETRY_DELAYS=[5,15,45]): Task 6 (_call_api added in Task 2, tested in Task 6)
- ✅ total_rate_limit_errors counter + usage API: Task 6
- ✅ Fix haiku pricing key: Task 6
- ✅ UI model selector + max_tokens + restrict: Task 7
- ✅ Tab Azioni guided checkboxes: Task 7
- ✅ 5 missing tools in TOOLS array: Task 7
- ✅ Version bump: Task 8

**Type consistency:** `agent.model` (str) → `runner.chat(model=str)` → `resolve_model(model, agent_type) -> str` → passed as `model=` to `_call_api`. Consistent throughout. `max_tokens: int` consistent. `restrict_to_home: bool` consistent.

**No placeholders detected.**
