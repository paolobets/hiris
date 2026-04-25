# Agent Security Context & Topic Restriction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere per ogni agente una whitelist di servizi HA invocabili e un filtro sulle entità accessibili; aggiungere un'opzione globale configurabile che limita la chat NL ai soli argomenti di domotica.

**Architecture:** Le restrizioni vivono nel dataclass `Agent` (allowed_services, allowed_entities) e vengono enforce in `ClaudeRunner._dispatch_tool()` tramite pattern fnmatch. La topic restriction è un'opzione add-on (`restrict_chat_to_home`) che viene iniettata nel system prompt della chat NL. La UI dell'Agent Designer viene estesa con i nuovi campi.

**Tech Stack:** Python 3.11, aiohttp, fnmatch (stdlib), APScheduler — nessuna nuova dipendenza.

---

## File modificati

| File | Modifica |
|------|----------|
| `hiris/app/agent_engine.py` | Aggiunge `allowed_services`, `allowed_entities` ad `Agent`; aggiorna `UPDATABLE_FIELDS` e `_run_agent` |
| `hiris/app/claude_runner.py` | Aggiunge parametri a `chat()`, enforce whitelist in `_dispatch_tool()`, topic restriction nel system prompt |
| `hiris/app/api/handlers_chat.py` | Passa il flag `restrict_to_home` al runner |
| `hiris/app/server.py` | Legge `RESTRICT_CHAT_TO_HOME` env, passa a `ClaudeRunner` |
| `hiris/config.yaml` | Aggiunge opzione `restrict_chat_to_home: bool` |
| `hiris/run.sh` | Esporta `RESTRICT_CHAT_TO_HOME` |
| `hiris/app/static/config.html` | Aggiunge campi "Servizi permessi" e "Entità accessibili" |
| `tests/test_agent_engine.py` | Test per nuovi campi Agent |
| `tests/test_claude_runner.py` | Test per enforcement whitelist + topic restriction |

---

## Task 1 — Agent dataclass: allowed_services + allowed_entities

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Modify: `tests/test_agent_engine.py`

- [ ] **Step 1: Scrivi il test che fallisce**

In `tests/test_agent_engine.py`, aggiungi dopo i test esistenti:

```python
def test_agent_has_security_fields():
    from hiris.app.agent_engine import AgentEngine
    from unittest.mock import AsyncMock
    ha = AsyncMock()
    engine = AgentEngine(ha_client=ha)
    agent = engine.create_agent({
        "name": "Secure Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Test",
        "allowed_tools": ["call_ha_service"],
        "allowed_services": ["light.*", "switch.turn_on"],
        "allowed_entities": ["light.*"],
        "enabled": True,
    })
    assert agent.allowed_services == ["light.*", "switch.turn_on"]
    assert agent.allowed_entities == ["light.*"]


def test_agent_defaults_empty_security_fields():
    from hiris.app.agent_engine import AgentEngine
    from unittest.mock import AsyncMock
    ha = AsyncMock()
    engine = AgentEngine(ha_client=ha)
    agent = engine.create_agent({
        "name": "Basic Agent",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Test",
        "enabled": True,
    })
    assert agent.allowed_services == []
    assert agent.allowed_entities == []


def test_update_agent_security_fields():
    from hiris.app.agent_engine import AgentEngine
    from unittest.mock import AsyncMock
    ha = AsyncMock()
    engine = AgentEngine(ha_client=ha)
    agent = engine.create_agent({
        "name": "A",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "",
        "enabled": False,
    })
    updated = engine.update_agent(agent.id, {
        "allowed_services": ["climate.*"],
        "allowed_entities": ["climate.*", "sensor.*"],
    })
    assert updated.allowed_services == ["climate.*"]
    assert updated.allowed_entities == ["climate.*", "sensor.*"]
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

```
py -m pytest tests/test_agent_engine.py::test_agent_has_security_fields -v
```
Atteso: `FAILED` — `TypeError: Agent.__init__() got an unexpected keyword argument 'allowed_services'`

- [ ] **Step 3: Modifica `hiris/app/agent_engine.py`**

Sostituisci l'intero blocco `@dataclass class Agent` e aggiorna `create_agent`, `UPDATABLE_FIELDS`, `_run_agent`:

```python
@dataclass
class Agent:
    id: str
    name: str
    type: str  # monitor | reactive | preventive | chat
    trigger: dict
    system_prompt: str
    allowed_tools: list[str]
    allowed_services: list[str]   # fnmatch patterns, es. ["light.*", "switch.turn_on"]; [] = nessuna restrizione
    allowed_entities: list[str]   # fnmatch patterns, es. ["light.*"]; [] = nessuna restrizione
    enabled: bool
    last_run: Optional[str] = None
    last_result: Optional[str] = None
```

In `create_agent`, sostituisci il corpo:

```python
def create_agent(self, data: dict) -> Agent:
    agent = Agent(
        id=str(uuid.uuid4()),
        name=data["name"],
        type=data["type"],
        trigger=data["trigger"],
        system_prompt=data.get("system_prompt", ""),
        allowed_tools=data.get("allowed_tools", []),
        allowed_services=data.get("allowed_services", []),
        allowed_entities=data.get("allowed_entities", []),
        enabled=data.get("enabled", True),
    )
    self._agents[agent.id] = agent
    if agent.enabled:
        self._schedule_agent(agent)
    return agent
```

Sostituisci `UPDATABLE_FIELDS`:

```python
UPDATABLE_FIELDS = {"name", "type", "trigger", "system_prompt", "allowed_tools", "allowed_services", "allowed_entities", "enabled"}
```

In `_run_agent`, sostituisci la chiamata a `self._claude_runner.chat(...)`:

```python
result = await self._claude_runner.chat(
    user_message=f"[Agent trigger: {agent.trigger.get('type')}]",
    system_prompt=prompt,
    allowed_tools=agent.allowed_tools or None,
    allowed_services=agent.allowed_services or None,
    allowed_entities=agent.allowed_entities or None,
)
```

- [ ] **Step 4: Esegui i test e verifica che passino**

```
py -m pytest tests/test_agent_engine.py -v
```
Atteso: tutti i test PASS (i vecchi + i 3 nuovi)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "feat: add allowed_services and allowed_entities to Agent dataclass"
```

---

## Task 2 — ClaudeRunner: enforcement whitelist servizi ed entità

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_claude_runner.py`, aggiungi dopo i test esistenti:

```python
@pytest.mark.asyncio
async def test_service_whitelist_blocks_disallowed_service():
    from hiris.app.claude_runner import ClaudeRunner
    from unittest.mock import AsyncMock, MagicMock, patch
    ha = AsyncMock()
    runner = ClaudeRunner(api_key="test", ha_client=ha, notify_config={})

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "call_ha_service"
    tool_block.id = "1"
    tool_block.input = {"domain": "climate", "service": "set_temperature", "data": {}}

    end_block = MagicMock()
    end_block.type = "text"
    end_block.text = "done"

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    resp_end = MagicMock()
    resp_end.stop_reason = "end_turn"
    resp_end.content = [end_block]

    runner._client = AsyncMock()
    runner._client.messages.create = AsyncMock(side_effect=[resp_tool, resp_end])

    result = await runner.chat(
        user_message="set temp",
        allowed_services=["light.*"],  # climate non permesso
    )
    # Il tool result deve contenere l'errore di whitelist
    call_args = runner._client.messages.create.call_args_list[1]
    messages = call_args[1]["messages"]
    tool_result_msg = messages[-1]["content"][0]
    assert "not in allowed_services" in tool_result_msg["content"]


@pytest.mark.asyncio
async def test_entity_filter_removes_disallowed_entity():
    from hiris.app.claude_runner import ClaudeRunner
    from unittest.mock import AsyncMock, MagicMock
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[
        {"entity_id": "light.living", "state": "on", "attributes": {}},
    ])
    runner = ClaudeRunner(api_key="test", ha_client=ha, notify_config={})

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "get_entity_states"
    tool_block.id = "2"
    tool_block.input = {"ids": ["light.living", "climate.bedroom"]}

    end_block = MagicMock()
    end_block.type = "text"
    end_block.text = "ok"

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_block]

    resp_end = MagicMock()
    resp_end.stop_reason = "end_turn"
    resp_end.content = [end_block]

    runner._client = AsyncMock()
    runner._client.messages.create = AsyncMock(side_effect=[resp_tool, resp_end])

    await runner.chat(
        user_message="show lights",
        allowed_entities=["light.*"],
    )
    # ha.get_states deve essere chiamata solo con light.living (climate filtrato)
    ha.get_states.assert_awaited_once_with(["light.living"])
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

```
py -m pytest tests/test_claude_runner.py::test_service_whitelist_blocks_disallowed_service tests/test_claude_runner.py::test_entity_filter_removes_disallowed_entity -v
```
Atteso: `FAILED` — i parametri `allowed_services`/`allowed_entities` non esistono ancora

- [ ] **Step 3: Modifica `hiris/app/claude_runner.py`**

Aggiungi l'import in cima:

```python
import fnmatch
```

Aggiungi queste due funzioni helper appena sotto le costanti (prima di `class ClaudeRunner`):

```python
def _service_allowed(domain: str, service: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    call = f"{domain}.{service}"
    return any(fnmatch.fnmatch(call, p) for p in allowed)


def _entity_allowed(entity_id: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    return any(fnmatch.fnmatch(entity_id, p) for p in allowed)
```

Sostituisci la firma di `chat()`:

```python
async def chat(
    self,
    user_message: str,
    system_prompt: str = "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
    allowed_tools: Optional[list[str]] = None,
    allowed_services: Optional[list[str]] = None,
    allowed_entities: Optional[list[str]] = None,
    conversation_history: Optional[list[dict]] = None,
) -> str:
```

Nel corpo di `chat()`, sostituisci la chiamata a `self._dispatch_tool`:

```python
result = await self._dispatch_tool(
    block.name, block.input,
    allowed_services=allowed_services or [],
    allowed_entities=allowed_entities or [],
)
```

Sostituisci l'intera firma e corpo di `_dispatch_tool`:

```python
async def _dispatch_tool(
    self,
    name: str,
    inputs: dict,
    allowed_services: list[str] = [],
    allowed_entities: list[str] = [],
) -> Any:
    logger.info("Tool call: %s(%s)", name, inputs)
    try:
        if name == "get_entity_states":
            ids = inputs["ids"]
            if allowed_entities:
                ids = [i for i in ids if _entity_allowed(i, allowed_entities)]
            return await get_entity_states(self._ha, ids)
        if name == "get_energy_history":
            return await get_energy_history(self._ha, inputs["days"])
        if name == "get_weather_forecast":
            return await get_weather_forecast(inputs["hours"])
        if name == "send_notification":
            return await send_notification(self._ha, inputs["message"], inputs["channel"], self._notify_config)
        if name == "get_ha_automations":
            return await get_ha_automations(self._ha)
        if name == "trigger_automation":
            return await trigger_automation(self._ha, inputs["automation_id"])
        if name == "toggle_automation":
            return await toggle_automation(self._ha, inputs["automation_id"], inputs["enabled"])
        if name == "call_ha_service":
            domain = inputs["domain"]
            service = inputs["service"]
            data = inputs.get("data", {})
            if not _service_allowed(domain, service, allowed_services):
                return {"error": f"Service {domain}.{service} not in allowed_services for this agent"}
            entity_id = data.get("entity_id", "")
            if entity_id and not _entity_allowed(entity_id, allowed_entities):
                return {"error": f"Entity {entity_id} not in allowed_entities for this agent"}
            return await self._ha.call_service(domain, service, data)
        logger.warning("Unknown tool: %s", name)
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        return {"error": str(exc)}
```

- [ ] **Step 4: Esegui tutti i test**

```
py -m pytest tests/ -v
```
Atteso: tutti PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/claude_runner.py tests/test_claude_runner.py
git commit -m "feat: enforce allowed_services and allowed_entities in tool dispatch"
```

---

## Task 3 — Topic restriction (opzione globale)

**Files:**
- Modify: `hiris/config.yaml`
- Modify: `hiris/run.sh`
- Modify: `hiris/app/server.py`
- Modify: `hiris/app/claude_runner.py`
- Modify: `hiris/app/api/handlers_chat.py`
- Modify: `tests/test_claude_runner.py`

- [ ] **Step 1: Scrivi il test che fallisce**

In `tests/test_claude_runner.py`, aggiungi:

```python
@pytest.mark.asyncio
async def test_topic_restriction_injected_in_system_prompt():
    from hiris.app.claude_runner import ClaudeRunner
    from unittest.mock import AsyncMock, MagicMock

    ha = AsyncMock()
    runner = ClaudeRunner(api_key="test", ha_client=ha, notify_config={}, restrict_to_home=True)

    captured_system = {}

    async def fake_create(**kwargs):
        captured_system["value"] = kwargs.get("system", "")
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = [MagicMock(type="text", text="risposta")]
        return resp

    runner._client = AsyncMock()
    runner._client.messages.create = fake_create

    await runner.chat(user_message="chi ha vinto il campionato?")
    assert "domotica" in captured_system["value"].lower() or "casa" in captured_system["value"].lower()


@pytest.mark.asyncio
async def test_topic_restriction_not_injected_when_disabled():
    from hiris.app.claude_runner import ClaudeRunner
    from unittest.mock import AsyncMock, MagicMock

    ha = AsyncMock()
    runner = ClaudeRunner(api_key="test", ha_client=ha, notify_config={}, restrict_to_home=False)
    default_prompt = "You are HIRIS"
    captured_system = {}

    async def fake_create(**kwargs):
        captured_system["value"] = kwargs.get("system", "")
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content = [MagicMock(type="text", text="ok")]
        return resp

    runner._client = AsyncMock()
    runner._client.messages.create = fake_create

    await runner.chat(user_message="ciao")
    assert captured_system["value"] == default_prompt
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

```
py -m pytest tests/test_claude_runner.py::test_topic_restriction_injected_in_system_prompt tests/test_claude_runner.py::test_topic_restriction_not_injected_when_disabled -v
```
Atteso: `FAILED` — `ClaudeRunner.__init__()` non accetta `restrict_to_home`

- [ ] **Step 3: Modifica `hiris/app/claude_runner.py`**

Aggiungi la costante del prompt di restrizione dopo `MAX_TOOL_ITERATIONS`:

```python
TOPIC_RESTRICTION_PROMPT = (
    "IMPORTANTE: Sei un assistente esclusivamente per la gestione della casa e della domotica. "
    "Rispondi SOLO a domande relative a: dispositivi smart home, automazioni, energia, meteo locale, "
    "entità di Home Assistant. Se l'utente chiede argomenti non correlati alla gestione domestica "
    "(sport, politica, storia, etc.), declinare educatamente e reindirizzare alla domotica."
)
```

Modifica `ClaudeRunner.__init__`:

```python
def __init__(self, api_key: str, ha_client: HAClient, notify_config: dict, restrict_to_home: bool = False) -> None:
    self._client = anthropic.AsyncAnthropic(api_key=api_key)
    self._ha = ha_client
    self._notify_config = notify_config
    self._restrict_to_home = restrict_to_home
```

All'inizio di `chat()`, aggiungi prima di `tools = ...`:

```python
if self._restrict_to_home:
    system_prompt = TOPIC_RESTRICTION_PROMPT + "\n\n" + system_prompt
```

- [ ] **Step 4: Modifica `hiris/config.yaml`**

Aggiungi nelle `options` e `schema`:

```yaml
options:
  claude_api_key: ""
  log_level: "info"
  restrict_chat_to_home: false
schema:
  claude_api_key: password
  log_level: "list(debug|info|warning|error)"
  restrict_chat_to_home: bool
```

- [ ] **Step 5: Modifica `hiris/run.sh`**

Aggiungi dopo `export CLAUDE_API_KEY=...`:

```bash
export RESTRICT_CHAT_TO_HOME=$(bashio::config 'restrict_chat_to_home' 'false')
```

- [ ] **Step 6: Modifica `hiris/app/server.py`**

In `_on_startup`, dopo la riga che legge `api_key`:

```python
restrict_to_home = os.environ.get("RESTRICT_CHAT_TO_HOME", "false").lower() == "true"
```

Aggiorna la costruzione di `ClaudeRunner`:

```python
runner = ClaudeRunner(
    api_key=api_key,
    ha_client=ha_client,
    notify_config=notify_config,
    restrict_to_home=restrict_to_home,
)
```

- [ ] **Step 7: Esegui tutti i test**

```
py -m pytest tests/ -v
```
Atteso: tutti PASS

- [ ] **Step 8: Commit**

```bash
git add hiris/app/claude_runner.py hiris/app/server.py hiris/config.yaml hiris/run.sh tests/test_claude_runner.py
git commit -m "feat: add restrict_chat_to_home global option — blocks off-topic chat"
```

---

## Task 4 — Agent Designer UI: nuovi campi

**Files:**
- Modify: `hiris/app/static/config.html`

I nuovi campi sono:
- **Entità accessibili** — textarea, una pattern per riga (es. `light.*`). Vuota = nessuna restrizione. Visibile sempre.
- **Servizi permessi** — textarea, una pattern per riga (es. `light.turn_on`). Vuota = nessuna restrizione. Visibile solo se `call_ha_service` è tra i tool selezionati.

- [ ] **Step 1: Aggiungi i campi HTML**

In `hiris/app/static/config.html`, dopo il blocco `<div class="tool-checkboxes" id="tool-checks"></div>`, aggiungi:

```html
<div id="entity-filter-section">
  <label>Entità accessibili <span style="color:#64748b;font-weight:normal">(una pattern per riga, es. <code>light.*</code> — vuoto = tutto)</span></label>
  <textarea id="f-entities" placeholder="light.*&#10;sensor.*&#10;switch.garage" rows="3"></textarea>
</div>
<div id="service-filter-section" style="display:none">
  <label>Servizi permessi <span style="color:#64748b;font-weight:normal">(una pattern per riga, es. <code>light.*</code> — vuoto = tutto)</span></label>
  <textarea id="f-services" placeholder="light.*&#10;switch.turn_on" rows="3"></textarea>
</div>
```

- [ ] **Step 2: Aggiorna la funzione `buildToolChecks` per mostrare/nascondere il campo servizi**

Sostituisci la funzione `buildToolChecks` in `config.html`:

```javascript
function buildToolChecks(selected) {
  const el = document.getElementById('tool-checks');
  el.innerHTML = '';
  TOOLS.forEach(t => {
    const lbl = document.createElement('label');
    lbl.innerHTML = `<input type="checkbox" value="${t}" ${selected.includes(t) ? 'checked' : ''}> ${t}`;
    el.appendChild(lbl);
  });
  updateServiceFilterVisibility();
}

function updateServiceFilterVisibility() {
  const hasCallService = [...document.querySelectorAll('#tool-checks input:checked')]
    .some(i => i.value === 'call_ha_service');
  document.getElementById('service-filter-section').style.display = hasCallService ? '' : 'none';
}

document.getElementById('tool-checks').addEventListener('change', updateServiceFilterVisibility);
```

- [ ] **Step 3: Aggiorna `openAgent` per popolare i nuovi campi**

In `openAgent(a)`, aggiungi dopo `buildToolChecks(a.allowed_tools || [])`:

```javascript
document.getElementById('f-entities').value = (a.allowed_entities || []).join('\n');
document.getElementById('f-services').value = (a.allowed_services || []).join('\n');
```

- [ ] **Step 4: Aggiorna il form "Nuovo agente" per azzerare i campi**

Nel handler `document.getElementById('new-btn').onclick`, aggiungi dopo `buildToolChecks([])`:

```javascript
document.getElementById('f-entities').value = '';
document.getElementById('f-services').value = '';
updateServiceFilterVisibility();
```

- [ ] **Step 5: Aggiorna `buildPayload` per includere i nuovi campi**

Sostituisci la funzione `buildPayload`:

```javascript
function buildPayload() {
  const type = document.getElementById('f-type').value;
  let trigger = {type: TRIGGER_TYPE_MAP[type]};
  if (type === 'monitor') trigger.interval_minutes = parseInt(document.getElementById('f-interval').value) || 5;
  if (type === 'reactive') trigger.entity_id = document.getElementById('f-entity').value;
  if (type === 'preventive') trigger.cron = document.getElementById('f-cron').value;

  const parseLines = id => document.getElementById(id).value
    .split('\n').map(s => s.trim()).filter(Boolean);

  return {
    name: document.getElementById('f-name').value,
    type,
    trigger,
    system_prompt: document.getElementById('f-prompt').value,
    allowed_tools: getSelectedTools(),
    allowed_entities: parseLines('f-entities'),
    allowed_services: parseLines('f-services'),
    enabled: document.getElementById('f-enabled').checked,
  };
}
```

- [ ] **Step 6: Esegui i test automatici (la UI va testata manualmente)**

```
py -m pytest tests/ -v
```
Atteso: tutti PASS (nessun test nuovo, i test esistenti non devono regredire)

- [ ] **Step 7: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "feat: Agent Designer UI — add allowed_entities and allowed_services fields"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Servizi invocabili per agente → Task 1 + 2 (`allowed_services`, fnmatch enforcement in `call_ha_service`)
- ✅ Proprietà/entità accessibili per agente → Task 1 + 2 (`allowed_entities`, filtro in `get_entity_states` e `call_ha_service`)
- ✅ Topic restriction configurabile → Task 3 (`restrict_chat_to_home` in config.yaml + system prompt injection)
- ✅ UI per i nuovi campi → Task 4

**2. Placeholder scan:** nessuno trovato. Tutti i step hanno codice completo.

**3. Type consistency:**
- `allowed_services: list[str]` — usato in Agent (Task 1), `chat()` params, `_dispatch_tool` (Task 2), `buildPayload` JS (Task 4) ✅
- `allowed_entities: list[str]` — stesso pattern ✅
- `_service_allowed(domain, service, allowed)` — definita in Task 2, usata in Task 2 ✅
- `_entity_allowed(entity_id, allowed)` — definita in Task 2, usata in Task 2 ✅
- `restrict_to_home: bool` — `ClaudeRunner.__init__` (Task 3), `server.py` (Task 3) ✅
