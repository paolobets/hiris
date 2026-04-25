# HIRIS Cycle 3 — Strategic Context Templates, Require Confirmation & Execution Log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three UX/safety wins — a Strategic Context template picker, an opt-in confirmation gate before real actions, and a per-agent execution log — bundled as v0.1.1.

**Architecture:** Templates are pure client-side JS (no backend, no persistence). `require_confirmation` is a new `Agent` boolean that, when true, appends a short Italian prompt to the system prompt before Claude is called (same wiring pattern as `restrict_to_home`). `execution_log` is a rolling 20-record list on `Agent`, written inside `_run_agent()` from counters already exposed on `ClaudeRunner` (`total_input_tokens`, `total_output_tokens`, `last_tool_calls`); it is NOT user-editable so it stays out of `UPDATABLE_FIELDS`.

**Tech Stack:** Python 3.11, aiohttp, anthropic SDK, pytest/pytest-asyncio, vanilla JS/HTML (no framework).

---

## File Map

| File | Change |
|---|---|
| `hiris/app/static/config.html` | Add TEMPLATES array + `<select id="f-template">`; add `<input id="f-require-confirmation">` in Stato fieldset; add "Log esecuzioni" collapsible section; extend `openAgent()`, `new-btn onclick`, `buildPayload()` |
| `hiris/app/agent_engine.py` | Add `require_confirmation: bool`, `execution_log: list[dict]` to `Agent`; add `require_confirmation` to `UPDATABLE_FIELDS`; extend `create_agent`, `_load`, `_run_agent` |
| `hiris/app/claude_runner.py` | Add `REQUIRE_CONFIRMATION_PROMPT`; accept `require_confirmation: bool` in `chat()`; append to effective system prompt when true |
| `hiris/app/api/handlers_chat.py` | Read `agent.require_confirmation` and pass through to `runner.chat()` |
| `hiris/config.yaml` | Bump `version` to `0.1.1` |
| `hiris/app/server.py` | Bump `/api/health` version response to `0.1.1` |
| `tests/test_agent_engine.py` | Tests for `require_confirmation` plumbing + `execution_log` records |
| `tests/test_claude_runner.py` | Tests for `require_confirmation` prompt injection |
| `tests/test_api.py` | Update version assertion to `0.1.1` |

---

## Task 1: Strategic Context Templates (config.html only)

**Files:**
- Modify: `hiris/app/static/config.html`

No backend, no tests. Pure JS addition. All existing patterns (var-based JS, string concat for DOM, `document.getElementById`) preserved.

- [ ] **Step 1: Add the TEMPLATES constant**

In `hiris/app/static/config.html`, locate the line `var TOOLS = [` and insert the following **immediately above** it, inside the same `<script>` block:

```javascript
    var TEMPLATES = [
      {
        id: 'energy-solar',
        label: 'Monitor Energia Solare',
        strategic: 'SISTEMA ENERGETICO:\n- Usa search_entities("produzione solare") per trovare il sensore fotovoltaico\n- Usa search_entities("batteria percentuale") per lo stato batteria\n- Usa search_entities("consumo totale potenza") per il consumo casa\n- Usa search_entities("importazione rete") per l\'importazione rete\n\nSOGLIE:\n- Importazione > 100W sostenuta: stai comprando energia — avvisa\n- Batteria < 15%: livello critico — avvisa\n- Surplus solare > 300W: momento ottimale per carichi\n\nCARICHI DIFFERIBILI: lavatrice, lavastoviglie, forno elettrico\nPICCO SOLARE: tipicamente 10:00-14:00',
        prompt: 'Analizza lo stato energetico. Se rilevi importazione dalla rete o batteria bassa, invia notifica. Se c\'è surplus solare, suggerisci un\'azione.',
      },
      {
        id: 'security',
        label: 'Sicurezza Casa',
        strategic: 'SENSORI:\n- Porte/finestre: search_entities("porta aperta") o search_entities("finestra aperta")\n- Movimento: search_entities("sensore movimento")\n- Persone in casa: person.* (state="home" = presente)\n\nREGOLE:\n- Porta/finestra aperta oltre 30 min: notifica\n- Movimento con nessuno in casa: notifica urgente\n- Controlla presenze con get_home_status() prima di agire',
        prompt: 'Controlla sicurezza casa: porte, finestre, sensori movimento. Notifica anomalie.',
      },
      {
        id: 'family-presence',
        label: 'Presenza Famiglia',
        strategic: 'PERSONE:\n- Tracker: search_entities("persona") — state="home" significa in casa\n\nAZIONI TIPICHE:\n- Arrivo: pre-riscalda climate, accendi luci benvenuto\n- Partenza: spegni climate, luci off, verifica serrature\n\nABITUDINI:\n- Rientro tipico: [modifica qui]\n- Temperatura preferita: [modifica qui, es. 21°C diurno / 18°C notturno]',
        prompt: 'Verifica presenze. Se cambiano, adatta riscaldamento e luci di conseguenza.',
      },
      {
        id: 'climate',
        label: 'Monitor Clima',
        strategic: 'TERMOSTATI: get_entities_by_domain("climate")\nMETEO: get_weather_forecast(hours=24)\n\nPREFERENCE:\n- Temperatura diurna: [es. 21°C]\n- Temperatura notturna: [es. 18°C]\n- Orario diurno: 07:00-23:00\n\nREGOLE:\n- Non riscaldare con finestre aperte (search_entities("finestra"))\n- Anticipa riscaldamento di 30 min rispetto al rientro\n- In estate: preferisci ventilazione naturale a condizionamento',
        prompt: 'Analizza temperatura attuale vs preferita. Ottimizza riscaldamento. Segnala anomalie.',
      },
    ];
```

- [ ] **Step 2: Add the template selector to the Istruzioni fieldset**

Locate the `<fieldset>` with `<legend>Istruzioni</legend>` and replace it with:

```html
        <fieldset>
          <legend>Istruzioni</legend>
          <p class="hint">Il Contesto Strategico viene anteposto al System Prompt &mdash; usalo per descrivere la casa e le abitudini della famiglia.</p>
          <label>Template contesto</label>
          <select id="f-template">
            <option value="">— nessun template —</option>
          </select>
          <p class="hint">Seleziona un template per precompilare Contesto Strategico e System Prompt. Puoi modificarli liberamente dopo.</p>
          <label>Contesto Strategico</label>
          <textarea id="f-strategic" rows="5" placeholder="Es: La famiglia &egrave; composta da 2 adulti. Rientro tipico: 16:00 nei giorni feriali in inverno, 18:30 in estate. Temperatura preferita in casa: 21&deg;C. Di notte (dopo le 23:00): 18&deg;C.
Sensori presenza: person.paolo, person.elena
Termostati: climate.soggiorno, climate.camera_da_letto"></textarea>
          <p class="hint">Informazioni stabili sulla casa e le abitudini. Precedono sempre il System Prompt.</p>
          <label>System Prompt</label>
          <textarea id="f-prompt" rows="4" placeholder="Descrivi il comportamento specifico dell&apos;agente&#8230;
Es: Analizza i consumi energetici dell&apos;ultima ora. Se rilevi un consumo anomalo (&gt;20% della media settimanale), invia una notifica."></textarea>
          <p class="hint">Istruzioni operative specifiche per questo agente.</p>
        </fieldset>
```

- [ ] **Step 3: Add `populateTemplateSelector()` function**

Immediately after the `TEMPLATES` array (before `var TRIGGER_TYPE_MAP`), add:

```javascript
    function populateTemplateSelector() {
      var sel = document.getElementById('f-template');
      if (!sel || sel.options.length > 1) return;
      TEMPLATES.forEach(function(t) {
        var opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = t.label;
        sel.appendChild(opt);
      });
      sel.addEventListener('change', function(e) {
        var id = e.target.value;
        if (!id) return;
        var tpl = TEMPLATES.filter(function(x) { return x.id === id; })[0];
        if (!tpl) return;
        document.getElementById('f-strategic').value = tpl.strategic;
        document.getElementById('f-prompt').value = tpl.prompt;
      });
    }
```

- [ ] **Step 4: Call `populateTemplateSelector()` on load; reset selector in `openAgent` and new-btn**

Locate the first `loadAgents();` call (before `fmtNum`) and replace it with:

```javascript
    populateTemplateSelector();
    loadAgents();
```

Inside `openAgent(a)`, add as the **first line** after `currentId = a.id;`:

```javascript
      document.getElementById('f-template').value = '';
```

Inside `new-btn onclick`, add as the **first line** after `currentId = null;`:

```javascript
      document.getElementById('f-template').value = '';
```

- [ ] **Step 5: Run Python tests to confirm no regressions**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/ -q
```

Expected: 120 passed, 3 warnings.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "feat(ui): add strategic context templates to agent designer"
```

---

## Task 2: `require_confirmation` — backend (dataclass + runner + handler)

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Modify: `hiris/app/claude_runner.py`
- Modify: `hiris/app/api/handlers_chat.py`
- Test: `tests/test_agent_engine.py`
- Test: `tests/test_claude_runner.py`

- [ ] **Step 1: Write failing tests in `tests/test_agent_engine.py`**

Append to `tests/test_agent_engine.py`:

```python
@pytest.mark.asyncio
async def test_run_agent_passes_require_confirmation_to_runner(engine):
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Conf Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "do stuff", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    await engine.run_agent(agent)
    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["require_confirmation"] is True


def test_agent_require_confirmation_defaults_false(engine):
    agent = engine.create_agent({
        "name": "Default", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    assert agent.require_confirmation is False


def test_update_agent_require_confirmation(engine):
    agent = engine.create_agent({
        "name": "Flip", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    updated = engine.update_agent(agent.id, {"require_confirmation": True})
    assert updated.require_confirmation is True


def test_agent_require_confirmation_persists(engine):
    agent = engine.create_agent({
        "name": "Persist Conf", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
        "require_confirmation": True,
    })
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
    assert loaded.require_confirmation is True
```

- [ ] **Step 2: Run to verify failures**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_agent_engine.py::test_run_agent_passes_require_confirmation_to_runner tests/test_agent_engine.py::test_agent_require_confirmation_defaults_false tests/test_agent_engine.py::test_update_agent_require_confirmation tests/test_agent_engine.py::test_agent_require_confirmation_persists -v
```

Expected: 4 FAILED — `TypeError: __init__() got an unexpected keyword argument 'require_confirmation'`.

- [ ] **Step 3: Add `require_confirmation` to the `Agent` dataclass**

In `hiris/app/agent_engine.py`, replace the `@dataclass class Agent:` block (lines 18-35) with:

```python
@dataclass
class Agent:
    id: str
    name: str
    type: str  # monitor | reactive | preventive | chat
    trigger: dict  # {type: schedule|state_changed|manual, interval_minutes?, entity_id?, cron?}
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
    require_confirmation: bool = False
```

- [ ] **Step 4: Wire `require_confirmation` through `_load`, `create_agent`, `UPDATABLE_FIELDS`, `_run_agent`**

**4a.** In `_load()`, inside the `Agent(...)` constructor call, add just before the closing `)`:

```python
                    restrict_to_home=raw.get("restrict_to_home", False),
                    require_confirmation=raw.get("require_confirmation", False),
                )
```

**4b.** In `create_agent()`, inside the `Agent(...)` constructor call, add just before the closing `)`:

```python
            restrict_to_home=bool(data.get("restrict_to_home", False)),
            require_confirmation=bool(data.get("require_confirmation", False)),
        )
```

**4c.** Replace `UPDATABLE_FIELDS` with:

```python
    UPDATABLE_FIELDS = {
        "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
        "strategic_context", "allowed_entities", "allowed_services",
        "model", "max_tokens", "restrict_to_home", "require_confirmation",
    }
```

**4d.** In `_run_agent()`, replace the `await self._claude_runner.chat(...)` call with:

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
                require_confirmation=agent.require_confirmation,
            )
```

- [ ] **Step 5: Write failing runner tests in `tests/test_claude_runner.py`**

Append to `tests/test_claude_runner.py`:

```python
@pytest.mark.asyncio
async def test_require_confirmation_injects_prompt(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT
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
    await runner.chat("Ciao", system_prompt="Base", require_confirmation=True)
    system_used = captured[0]["system"]
    assert REQUIRE_CONFIRMATION_PROMPT in system_used
    assert "Base" in system_used


@pytest.mark.asyncio
async def test_require_confirmation_false_does_not_inject(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT
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
    await runner.chat("Ciao", system_prompt="Base", require_confirmation=False)
    system_used = captured[0]["system"]
    assert REQUIRE_CONFIRMATION_PROMPT not in system_used


@pytest.mark.asyncio
async def test_require_confirmation_combines_with_restrict(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT, RESTRICT_PROMPT
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
    await runner.chat("Ciao", system_prompt="Base", restrict_to_home=True, require_confirmation=True)
    system_used = captured[0]["system"]
    assert "Base" in system_used
    assert RESTRICT_PROMPT in system_used
    assert REQUIRE_CONFIRMATION_PROMPT in system_used
```

- [ ] **Step 6: Run runner tests to verify failures**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_claude_runner.py::test_require_confirmation_injects_prompt tests/test_claude_runner.py::test_require_confirmation_false_does_not_inject tests/test_claude_runner.py::test_require_confirmation_combines_with_restrict -v
```

Expected: 3 FAILED — `ImportError: cannot import name 'REQUIRE_CONFIRMATION_PROMPT'`.

- [ ] **Step 7: Add `REQUIRE_CONFIRMATION_PROMPT` and `require_confirmation` param to `claude_runner.py`**

In `hiris/app/claude_runner.py`, locate `RESTRICT_PROMPT = (...)` and add immediately below it:

```python
REQUIRE_CONFIRMATION_PROMPT = (
    "Prima di chiamare call_ha_service per eseguire un'azione reale, "
    "descrivi l'azione che intendi eseguire e chiedi conferma con il formato: "
    "'Proposta: [descrizione azione]. Confermi? (sì/no)'. "
    "Esegui call_ha_service SOLO se il messaggio più recente dell'utente "
    "contiene 'sì', 'si', 'ok', 'conferma' o 'yes' (case insensitive)."
)
```

Update the `chat()` signature — add `require_confirmation: bool = False` as the last parameter:

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
    ) -> str:
```

Inside `chat()`, replace the prompt injection block:

```python
        self.last_tool_calls = []
        effective_system = system_prompt
        if restrict_to_home:
            effective_system = f"{effective_system}\n\n---\n\n{RESTRICT_PROMPT}"
        if require_confirmation:
            effective_system = f"{effective_system}\n\n---\n\n{REQUIRE_CONFIRMATION_PROMPT}"
        if self._cache is not None:
            effective_system = f"{effective_system}\n\n---\n\n{generate_home_profile(self._cache)}"
```

- [ ] **Step 8: Wire through `handlers_chat.py`**

In `hiris/app/api/handlers_chat.py`, after the line `agent_restrict = getattr(agent, "restrict_to_home", False) if agent else False`, add:

```python
    agent_require_confirmation = getattr(agent, "require_confirmation", False) if agent else False
```

Extend the `runner.chat(...)` call to include the new kwarg as the last argument:

```python
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
    )
```

- [ ] **Step 9: Run all tests — all pass**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_agent_engine.py tests/test_claude_runner.py -v
```

Expected: all GREEN (120+ tests including the 7 new ones).

- [ ] **Step 10: Commit**

```bash
git add hiris/app/agent_engine.py hiris/app/claude_runner.py hiris/app/api/handlers_chat.py tests/test_agent_engine.py tests/test_claude_runner.py
git commit -m "feat: add require_confirmation gate for call_ha_service"
```

---

## Task 3: `require_confirmation` — UI in config.html

**Files:**
- Modify: `hiris/app/static/config.html`

No tests — pure UI.

- [ ] **Step 1: Add checkbox to the Stato fieldset**

Locate the `<fieldset>` with `<legend>Stato</legend>` and replace it with:

```html
        <fieldset>
          <legend>Stato</legend>
          <label style="flex-direction:row;display:flex;align-items:center;gap:0.5rem;margin-top:0">
            <input type="checkbox" id="f-enabled"> Agente abilitato
          </label>
          <p class="hint">Gli agenti disabilitati non vengono eseguiti automaticamente ma possono essere avviati manualmente.</p>
          <label style="flex-direction:row;display:flex;align-items:center;gap:0.5rem;margin-top:0.75rem">
            <input type="checkbox" id="f-require-confirmation"> Richiedi conferma prima delle azioni
          </label>
          <p class="hint">Se attivo, l&apos;agente descrive l&apos;azione e attende conferma (&quot;s&igrave;&quot;, &quot;ok&quot;, &quot;conferma&quot;) prima di chiamare call_ha_service.</p>
        </fieldset>
```

- [ ] **Step 2: Populate the checkbox in `openAgent(a)`**

In `openAgent(a)`, after the line `document.getElementById('f-restrict').checked = !!a.restrict_to_home;`, add:

```javascript
      document.getElementById('f-require-confirmation').checked = !!a.require_confirmation;
```

- [ ] **Step 3: Reset in new-btn handler**

In `new-btn onclick`, after `document.getElementById('f-restrict').checked = false;`, add:

```javascript
      document.getElementById('f-require-confirmation').checked = false;
```

- [ ] **Step 4: Include in `buildPayload()`**

In `buildPayload()`, after `restrict_to_home: document.getElementById('f-restrict').checked,`, add:

```javascript
        require_confirmation: document.getElementById('f-require-confirmation').checked,
```

- [ ] **Step 5: Run Python tests to confirm no regressions**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/ -q
```

Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "feat(ui): add require_confirmation checkbox to agent designer"
```

---

## Task 4: Execution log — backend

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Test: `tests/test_agent_engine.py`

- [ ] **Step 1: Write failing tests in `tests/test_agent_engine.py`**

Append to `tests/test_agent_engine.py`:

```python
@pytest.mark.asyncio
async def test_run_agent_appends_execution_log_record(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = [{"tool": "get_home_status", "input": {}}]
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0

    async def chat_side_effect(**kwargs):
        mock_runner.total_input_tokens += 120
        mock_runner.total_output_tokens += 30
        return "Tutto ok, niente da fare."
    mock_runner.chat = AsyncMock(side_effect=chat_side_effect)
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Log Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)

    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["trigger"] == "schedule"
    assert rec["tool_calls"] == ["get_home_status"]
    assert rec["input_tokens"] == 120
    assert rec["output_tokens"] == 30
    assert rec["result_summary"].startswith("Tutto ok")
    assert rec["success"] is True
    assert rec["timestamp"] == agent.last_run


@pytest.mark.asyncio
async def test_run_agent_execution_log_caps_at_20(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.chat = AsyncMock(return_value="ok")
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Cap Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    for _ in range(25):
        await engine.run_agent(agent)
    assert len(agent.execution_log) == 20


@pytest.mark.asyncio
async def test_run_agent_execution_log_marks_error(engine):
    mock_runner = AsyncMock()
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    mock_runner.chat = AsyncMock(side_effect=RuntimeError("boom"))
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Err Agent", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    await engine.run_agent(agent)
    assert len(agent.execution_log) == 1
    rec = agent.execution_log[0]
    assert rec["success"] is False
    assert rec["result_summary"].startswith("Error:")


def test_execution_log_not_in_updatable_fields(engine):
    assert "execution_log" not in AgentEngine.UPDATABLE_FIELDS


def test_execution_log_persists_across_reload(engine):
    agent = engine.create_agent({
        "name": "Persist Log", "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "", "allowed_tools": [], "enabled": False,
    })
    agent.execution_log = [{
        "timestamp": "2026-04-20T10:00:00+00:00",
        "trigger": "schedule",
        "tool_calls": ["get_home_status"],
        "input_tokens": 50,
        "output_tokens": 10,
        "result_summary": "ok",
        "success": True,
    }]
    engine._save()
    engine2 = AgentEngine(ha_client=engine._ha, data_path=engine._data_path)
    engine2._load()
    loaded = engine2.get_agent(agent.id)
    assert len(loaded.execution_log) == 1
    assert loaded.execution_log[0]["trigger"] == "schedule"
```

- [ ] **Step 2: Run to verify failures**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_agent_engine.py::test_run_agent_appends_execution_log_record tests/test_agent_engine.py::test_run_agent_execution_log_caps_at_20 tests/test_agent_engine.py::test_run_agent_execution_log_marks_error tests/test_agent_engine.py::test_execution_log_not_in_updatable_fields tests/test_agent_engine.py::test_execution_log_persists_across_reload -v
```

Expected: 5 FAILED — `AttributeError: 'Agent' object has no attribute 'execution_log'`.

- [ ] **Step 3: Add `execution_log` to the `Agent` dataclass**

In `hiris/app/agent_engine.py`, replace the `@dataclass class Agent:` block with (last field added):

```python
@dataclass
class Agent:
    id: str
    name: str
    type: str  # monitor | reactive | preventive | chat
    trigger: dict  # {type: schedule|state_changed|manual, interval_minutes?, entity_id?, cron?}
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
    require_confirmation: bool = False
    execution_log: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Hydrate `execution_log` in `_load()`**

In `_load()`, inside the `Agent(...)` constructor call, add just before the closing `)`:

```python
                    require_confirmation=raw.get("require_confirmation", False),
                    execution_log=raw.get("execution_log", []),
                )
```

(`UPDATABLE_FIELDS` is NOT changed — execution_log is append-only, not user-editable.)

- [ ] **Step 5: Rewrite `_run_agent()` to append records**

In `hiris/app/agent_engine.py`, replace the entire `_run_agent()` method with:

```python
    async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:
        if not self._claude_runner:
            logger.warning("No Claude runner configured")
            return ""
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        try:
            agent.last_run = datetime.now(timezone.utc).isoformat()
            if agent.strategic_context:
                effective_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
            else:
                effective_prompt = agent.system_prompt
            if context:
                effective_prompt = f"{effective_prompt}\n\nContext: {context}"
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
                require_confirmation=agent.require_confirmation,
            )
            agent.last_result = result
            self._append_execution_log(agent, result, inp_before, out_before, success=True)
            self._save()
            return result
        except Exception as exc:
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            self._append_execution_log(agent, agent.last_result, inp_before, out_before, success=False)
            self._save()
            return agent.last_result

    def _append_execution_log(
        self,
        agent: Agent,
        result: str,
        inp_before: int,
        out_before: int,
        success: bool,
    ) -> None:
        inp_after = getattr(self._claude_runner, "total_input_tokens", 0)
        out_after = getattr(self._claude_runner, "total_output_tokens", 0)
        tool_calls = [
            t.get("tool", "") for t in (getattr(self._claude_runner, "last_tool_calls", None) or [])
        ]
        record = {
            "timestamp": agent.last_run,
            "trigger": agent.trigger.get("type", "unknown"),
            "tool_calls": tool_calls,
            "input_tokens": inp_after - inp_before,
            "output_tokens": out_after - out_before,
            "result_summary": (result or "")[:200],
            "success": success and not (result or "").startswith("Error:"),
        }
        agent.execution_log = (agent.execution_log + [record])[-20:]
```

- [ ] **Step 6: Run all agent tests — all pass**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_agent_engine.py -v
```

Expected: all GREEN (existing tests + 5 new ones).

- [ ] **Step 7: Commit**

```bash
git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "feat: record last 20 executions per agent in execution_log"
```

---

## Task 5: Execution log — UI in config.html

**Files:**
- Modify: `hiris/app/static/config.html`

No tests — pure UI.

- [ ] **Step 1: Add CSS styles for the log section**

In the `<style>` block, just before the closing `</style>` tag, append:

```css
    details.log-section {
      margin-top: 1rem;
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      background: var(--surface-2);
      padding: 0.4rem 0.8rem;
    }
    details.log-section summary {
      cursor: pointer;
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 0.4rem 0;
    }
    .log-empty {
      font-size: 0.8rem;
      color: var(--muted-alt);
      padding: 0.5rem 0.2rem;
    }
    .log-list {
      list-style: none;
      margin: 0.4rem 0 0.6rem 0;
      padding: 0;
      max-height: 260px;
      overflow-y: auto;
    }
    .log-list li {
      display: grid;
      grid-template-columns: 120px 60px 1fr 90px;
      gap: 0.5rem;
      align-items: center;
      font-size: 0.75rem;
      padding: 0.35rem 0.25rem;
      border-bottom: 1px solid var(--border-subtle);
    }
    .log-list li:last-child { border-bottom: none; }
    .log-time { color: var(--text-muted); font-family: 'Courier New', Consolas, monospace; }
    .log-success { color: var(--run-color); font-weight: 600; }
    .log-error { color: var(--danger); font-weight: 600; }
    .log-summary {
      color: var(--text);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .log-tokens {
      color: var(--muted-alt);
      font-family: 'Courier New', Consolas, monospace;
      text-align: right;
    }
```

- [ ] **Step 2: Add the `<details>` block in the form**

Locate `<pre id="run-output"></pre>` and insert immediately after it (before the closing `</div>` of `id="form"`):

```html
        <details class="log-section">
          <summary>Log esecuzioni (ultime 20)</summary>
          <div id="log-body"><div class="log-empty">Nessuna esecuzione registrata.</div></div>
        </details>
```

- [ ] **Step 3: Add the `renderExecutionLog(a)` function**

In the `<script>` block, just after the `esc(t)` function, add:

```javascript
    function renderExecutionLog(a) {
      var body = document.getElementById('log-body');
      if (!body) return;
      var log = (a && a.execution_log) || [];
      if (log.length === 0) {
        body.innerHTML = '<div class="log-empty">Nessuna esecuzione registrata.</div>';
        return;
      }
      var rows = log.slice().reverse().map(function(r) {
        var t = r.timestamp ? new Date(r.timestamp) : null;
        var timeStr = t ? t.toLocaleString('it-IT', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '—';
        var statusCls = r.success ? 'log-success' : 'log-error';
        var statusTxt = r.success ? '\u2713 ok' : '\u2717 err';
        var tools = (r.tool_calls || []).join(', ');
        var summary = r.result_summary || '';
        var titleAttr = esc(summary) + (tools ? (' — tools: ' + esc(tools)) : '');
        var tokens = (r.input_tokens || 0) + '\u2193 / ' + (r.output_tokens || 0) + '\u2191';
        return '<li>' +
          '<span class="log-time">' + esc(timeStr) + '</span>' +
          '<span class="' + statusCls + '">' + statusTxt + '</span>' +
          '<span class="log-summary" title="' + titleAttr + '">' + esc(summary || tools || '\u2014') + '</span>' +
          '<span class="log-tokens">' + esc(tokens) + '</span>' +
        '</li>';
      }).join('');
      body.innerHTML = '<ul class="log-list">' + rows + '</ul>';
    }
```

- [ ] **Step 4: Populate log in `openAgent(a)` and clear in new-btn**

In `openAgent(a)`, add as the **last line** in the function body (just before the closing `}`):

```javascript
      renderExecutionLog(a);
```

In `new-btn onclick`, add as the **last line** in the handler body:

```javascript
      renderExecutionLog(null);
```

- [ ] **Step 5: Run Python tests to confirm no regressions**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/ -q
```

Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "feat(ui): show last 20 executions in agent designer"
```

---

## Task 6: Version bump to 0.1.1

**Files:**
- Modify: `hiris/config.yaml`
- Modify: `hiris/app/server.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Update failing test in `tests/test_api.py`**

In `tests/test_api.py`, change:

```python
    assert data["version"] == "0.1.0"
```

to:

```python
    assert data["version"] == "0.1.1"
```

- [ ] **Step 2: Run to verify it fails**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/test_api.py -v -k health
```

Expected: FAILED with `AssertionError: assert '0.1.0' == '0.1.1'`.

- [ ] **Step 3: Bump `hiris/config.yaml`**

In `hiris/config.yaml`, change:

```yaml
version: "0.1.0"
```

to:

```yaml
version: "0.1.1"
```

- [ ] **Step 4: Bump `hiris/app/server.py` health response**

In `hiris/app/server.py`, in `_handle_health()`, change:

```python
    return web.json_response({"status": "ok", "version": "0.1.0"})
```

to:

```python
    return web.json_response({"status": "ok", "version": "0.1.1"})
```

- [ ] **Step 5: Run full test suite — all pass**

```
cd C:\Work\Sviluppo\hiris && py -m pytest tests/ -v
```

Expected: all GREEN.

- [ ] **Step 6: Commit**

```bash
git add hiris/config.yaml hiris/app/server.py tests/test_api.py
git commit -m "chore: bump version to 0.1.1"
```

---

## Self-Review

**Spec coverage:**
- Feature 13 (Templates) → Task 1: TEMPLATES array, `<select id="f-template">`, `populateTemplateSelector()`, resets. ✓
- Feature 14 (Require Confirmation) → Task 2: dataclass field, `REQUIRE_CONFIRMATION_PROMPT`, `chat()` param + injection, `_run_agent()`, `handlers_chat.py`, tests. Task 3: checkbox UI. ✓
- Feature 15 (Execution log) → Task 4: dataclass field, `_append_execution_log()`, 20-cap, token delta, error path, serialization, tests. Task 5: collapsible UI, `renderExecutionLog()`. ✓
- Version bump → Task 6. ✓

**Placeholder scan:** All code blocks are complete. Template texts use `[modifica qui]` and `[es. 21°C]` as literal UI strings visible to the end user, not plan placeholders.

**Type consistency:**
- `require_confirmation` (bool) used identically in: Agent dataclass, UPDATABLE_FIELDS, `create_agent()`, `_load()`, `_run_agent()`, `chat()`, `handlers_chat.py`, all tests, and JS `buildPayload()`.
- `execution_log` (list[dict]) used identically in: Agent dataclass, `_load()`, `_append_execution_log()`, all tests, and JS `renderExecutionLog()`.
- `REQUIRE_CONFIRMATION_PROMPT` constant name used identically in `claude_runner.py` definition and all test imports.
- JS ids `f-template`, `f-require-confirmation`, `log-body` used consistently between HTML markup and JS.
- `renderExecutionLog` used in definition, `openAgent(a)`, and `new-btn onclick`.
