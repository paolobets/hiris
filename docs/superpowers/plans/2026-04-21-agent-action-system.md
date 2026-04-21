# Agent Action System — Plan B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class Action System to HIRIS agents: agents declare what actions they can take, Claude's response is forced into a structured `VALUTAZIONE/AZIONE` format, and the execution log shows structured evaluation status + action taken (not a raw Claude dump).

**Architecture:** Four-layer change: (1) Agent dataclass gets `actions: list[dict]` field, (2) ClaudeRunner injects action instructions into system prompt and parses structured response lines, (3) AgentEngine stores `eval_status` + `action_taken` in execution log, (4) config.html gets an Action Builder fieldset and structured log display.

**Tech Stack:** Python 3.11 + aiohttp (backend), vanilla JS (frontend), existing `config.html` dark-theme CSS variables.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `hiris/app/agent_engine.py` | Modify | Add `actions` field to Agent, update UPDATABLE_FIELDS, store eval_status/action_taken in log |
| `hiris/app/claude_runner.py` | Modify | Inject action instructions into system prompt, parse VALUTAZIONE/AZIONE from response |
| `hiris/app/static/config.html` | Modify | Action builder UI fieldset, structured log display |
| `hiris/app/server.py` | Modify | Version bump 0.1.4 → 0.1.5 |
| `config.yaml` | Modify | Version bump 0.1.4 → 0.1.5 |
| `tests/test_api.py` | Modify | Version bump 0.1.4 → 0.1.5 |
| `tests/test_agent_engine.py` | Modify | Tests for actions field persistence |
| `tests/test_claude_runner.py` | Modify | Tests for action instruction injection and response parsing |

---

### Task 5: Agent dataclass — `actions` field + UPDATABLE_FIELDS

**Files:**
- Modify: `hiris/app/agent_engine.py`
- Modify: `tests/test_agent_engine.py`

An **action** is a dict with this shape:

```python
{
    "type": "notify" | "call_service",
    "label": str,                # human-readable description shown in UI
    # for type == "notify":
    "channel": str,              # e.g. "ha" | "telegram"
    # for type == "call_service":
    "domain": str,               # e.g. "light"
    "service": str,              # e.g. "turn_off"
    "entity_pattern": str,       # e.g. "light.*" (optional)
}
```

- [ ] **Step 1: Write failing tests for actions field**

Add to `tests/test_agent_engine.py`:

```python
def test_create_agent_with_actions(tmp_path):
    from unittest.mock import MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))

    actions = [
        {"type": "notify", "label": "Avvisa via Telegram", "channel": "telegram"},
        {"type": "call_service", "label": "Spegni luci", "domain": "light", "service": "turn_off", "entity_pattern": "light.*"},
    ]
    agent = engine.create_agent({
        "name": "Action Test",
        "type": "monitor",
        "trigger": {"type": "manual"},
        "actions": actions,
    })
    assert agent.actions == actions


def test_update_agent_actions(tmp_path):
    from unittest.mock import MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    agent = engine.create_agent({
        "name": "Action Update Test", "type": "monitor",
        "trigger": {"type": "manual"},
    })
    assert agent.actions == []

    new_actions = [{"type": "notify", "label": "Test", "channel": "ha"}]
    updated = engine.update_agent(agent.id, {"actions": new_actions})
    assert updated.actions == new_actions


def test_agent_actions_persist_to_disk(tmp_path):
    from unittest.mock import MagicMock
    from hiris.app.agent_engine import AgentEngine

    mock_ha = MagicMock()
    mock_ha.add_state_listener = MagicMock()

    data_path = str(tmp_path / "agents.json")
    engine = AgentEngine(ha_client=mock_ha, data_path=data_path)

    actions = [{"type": "notify", "label": "Disk test", "channel": "telegram"}]
    agent = engine.create_agent({
        "name": "Persist Test", "type": "monitor",
        "trigger": {"type": "manual"},
        "actions": actions,
    })

    # Reload from disk
    engine2 = AgentEngine(ha_client=mock_ha, data_path=data_path)
    engine2._load()
    reloaded = engine2.get_agent(agent.id)
    assert reloaded.actions == actions
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_agent_engine.py::test_create_agent_with_actions tests/test_agent_engine.py::test_update_agent_actions tests/test_agent_engine.py::test_agent_actions_persist_to_disk -v
```

Expected: FAIL — `actions` not a valid field yet, or ignored on create.

- [ ] **Step 3: Add `actions` to Agent dataclass**

In `hiris/app/agent_engine.py`, find the Agent dataclass. After the `execution_log` field (currently the last field), add:

```python
    actions: list[dict] = field(default_factory=list)
```

Full Agent dataclass after change:
```python
@dataclass
class Agent:
    id: str
    name: str
    type: str
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
    require_confirmation: bool = False
    execution_log: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Add `"actions"` to UPDATABLE_FIELDS**

Find `UPDATABLE_FIELDS` in `agent_engine.py`. It should look like:

```python
UPDATABLE_FIELDS = {
    "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
    "strategic_context", "allowed_entities", "allowed_services",
    "model", "max_tokens", "restrict_to_home", "require_confirmation",
}
```

Add `"actions"` to the set:

```python
UPDATABLE_FIELDS = {
    "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
    "strategic_context", "allowed_entities", "allowed_services",
    "model", "max_tokens", "restrict_to_home", "require_confirmation",
    "actions",
}
```

- [ ] **Step 5: Run tests — verify they pass**

```
pytest tests/test_agent_engine.py::test_create_agent_with_actions tests/test_agent_engine.py::test_update_agent_actions tests/test_agent_engine.py::test_agent_actions_persist_to_disk -v
```

Expected: all PASS.

- [ ] **Step 6: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add hiris/app/agent_engine.py tests/test_agent_engine.py
git commit -m "$(cat <<'EOF'
feat: add actions field to Agent dataclass

Agents now declare allowed actions as a list of typed dicts
(notify or call_service). Persists to disk, updatable via PUT.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: ClaudeRunner — inject action instructions + parse structured response

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_claude_runner.py`

For non-chat agents that have `actions` defined, the system prompt gets appended with:

```
---
ISTRUZIONI DI RISPOSTA:
Termina SEMPRE la tua risposta con queste due righe esatte:
VALUTAZIONE: [OK | ATTENZIONE | ANOMALIA]
AZIONE: [breve descrizione dell'azione intrapresa, oppure "nessuna azione necessaria"]

Azioni disponibili per questo agente:
- Notifica via Telegram: invia un messaggio di allerta
- Spegni luci (light.turn_off su light.*): esegui se anomalia rilevata
```

After the API call, the runner parses out `VALUTAZIONE:` and `AZIONE:` lines from the response text, strips them from the visible result, and returns them as metadata.

The `run_agent` method in `agent_engine.py` will receive a tuple `(result_text, eval_status, action_taken)` from the runner when actions are present, or a plain string for backward compatibility.

**Design decision for backward compatibility:** `ClaudeRunner.chat()` always returns a plain string (unchanged). Add a new method `run_with_actions(agent, messages)` that returns `(text, eval_status, action_taken)`. `AgentEngine.run_agent` calls `run_with_actions` if the agent has actions, else `chat`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_claude_runner.py`:

```python
def test_build_action_instructions_notify():
    from hiris.app.claude_runner import _build_action_instructions
    actions = [{"type": "notify", "label": "Avvisa via Telegram", "channel": "telegram"}]
    instructions = _build_action_instructions(actions)
    assert "VALUTAZIONE:" in instructions
    assert "AZIONE:" in instructions
    assert "Avvisa via Telegram" in instructions


def test_build_action_instructions_call_service():
    from hiris.app.claude_runner import _build_action_instructions
    actions = [
        {"type": "call_service", "label": "Spegni luci",
         "domain": "light", "service": "turn_off", "entity_pattern": "light.*"},
    ]
    instructions = _build_action_instructions(actions)
    assert "Spegni luci" in instructions
    assert "light.turn_off" in instructions


def test_build_action_instructions_empty():
    from hiris.app.claude_runner import _build_action_instructions
    assert _build_action_instructions([]) == ""


def test_parse_structured_response_extracts_fields():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Il sistema è normale.\n\nVALUTAZIONE: OK\nAZIONE: nessuna azione necessaria"
    text, status, action = _parse_structured_response(raw)
    assert status == "OK"
    assert action == "nessuna azione necessaria"
    assert "VALUTAZIONE:" not in text
    assert "AZIONE:" not in text
    assert "Il sistema è normale." in text


def test_parse_structured_response_attenzione():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Anomalia rilevata.\nVALUTAZIONE: ANOMALIA\nAZIONE: Notifica inviata via Telegram"
    text, status, action = _parse_structured_response(raw)
    assert status == "ANOMALIA"
    assert action == "Notifica inviata via Telegram"


def test_parse_structured_response_missing_lines():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Risposta senza struttura"
    text, status, action = _parse_structured_response(raw)
    assert text == raw
    assert status is None
    assert action is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_claude_runner.py::test_build_action_instructions_notify tests/test_claude_runner.py::test_parse_structured_response_extracts_fields -v
```

Expected: `ImportError` — `_build_action_instructions` and `_parse_structured_response` do not exist yet.

- [ ] **Step 3: Implement the two helper functions in claude_runner.py**

Add to `hiris/app/claude_runner.py` (as module-level functions, before the `ClaudeRunner` class):

```python
def _build_action_instructions(actions: list[dict]) -> str:
    """Return the structured-response instruction block for a list of actions.
    Returns empty string if no actions defined."""
    if not actions:
        return ""
    lines = [
        "---",
        "ISTRUZIONI DI RISPOSTA:",
        "Termina SEMPRE la tua risposta con queste due righe esatte:",
        "VALUTAZIONE: [OK | ATTENZIONE | ANOMALIA]",
        "AZIONE: [breve descrizione dell'azione intrapresa, oppure \"nessuna azione necessaria\"]",
        "",
        "Azioni disponibili per questo agente:",
    ]
    for a in actions:
        if a.get("type") == "notify":
            lines.append(f"- {a.get('label', 'Notifica')} (canale: {a.get('channel', 'ha')})")
        elif a.get("type") == "call_service":
            svc = f"{a.get('domain', '')}.{a.get('service', '')}"
            pattern = a.get("entity_pattern", "")
            suffix = f" su {pattern}" if pattern else ""
            lines.append(f"- {a.get('label', 'Servizio')} ({svc}{suffix})")
    return "\n".join(lines)


def _parse_structured_response(text: str) -> tuple[str, str | None, str | None]:
    """Parse VALUTAZIONE and AZIONE lines from Claude response.
    Returns (cleaned_text, eval_status, action_taken).
    eval_status and action_taken are None if not found."""
    eval_status: str | None = None
    action_taken: str | None = None
    clean_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("VALUTAZIONE:"):
            eval_status = stripped[len("VALUTAZIONE:"):].strip()
        elif stripped.startswith("AZIONE:"):
            action_taken = stripped[len("AZIONE:"):].strip()
        else:
            clean_lines.append(line)
    # Remove trailing blank lines after stripping structured lines
    clean_text = "\n".join(clean_lines).rstrip()
    return clean_text, eval_status, action_taken
```

- [ ] **Step 4: Add `run_with_actions` method to ClaudeRunner**

In the `ClaudeRunner` class, add after the existing `chat` method:

```python
async def run_with_actions(
    self,
    agent: Any,
    messages: list[dict],
) -> tuple[str, str | None, str | None]:
    """Like chat() but injects action instructions and parses structured response.
    Returns (cleaned_text, eval_status, action_taken)."""
    action_instructions = _build_action_instructions(getattr(agent, "actions", []))
    # Build effective system prompt with action instructions appended
    base_system = await self._build_system_prompt(agent)  # existing method or inline
    if action_instructions:
        effective_system = f"{base_system}\n\n{action_instructions}"
    else:
        effective_system = base_system

    raw_result = await self.chat(
        messages=messages,
        system_override=effective_system,
        agent=agent,
    )
    return _parse_structured_response(raw_result)
```

**Note:** Check the existing `chat()` signature in `claude_runner.py` to ensure `system_override` is an accepted parameter. If it isn't, add it as an optional kwarg that, when provided, replaces the auto-built system prompt. See Step 5.

- [ ] **Step 5: Add `system_override` parameter to `chat()` if not present**

In `claude_runner.py`, find the `chat` method signature. If it does NOT have a `system_override` parameter, add it:

```python
async def chat(
    self,
    messages: list[dict],
    agent: Any = None,
    system_override: str | None = None,
) -> str:
```

Inside `chat()`, where the effective system prompt is built, add:

```python
if system_override is not None:
    effective_system = system_override
```

Make this override happen AFTER the normal system prompt is built but BEFORE it's sent to the API.

- [ ] **Step 6: Update AgentEngine.run_agent to call run_with_actions when applicable**

In `hiris/app/agent_engine.py`, find `run_agent`. It currently calls something like:

```python
result = await self._claude_runner.chat(messages=[...], agent=agent)
```

Change it to:

```python
if getattr(agent, 'actions', []):
    result_text, eval_status, action_taken = await self._claude_runner.run_with_actions(
        agent=agent, messages=[{"role": "user", "content": trigger_content}]
    )
else:
    result_text = await self._claude_runner.chat(
        messages=[{"role": "user", "content": trigger_content}], agent=agent
    )
    eval_status = None
    action_taken = None
```

Then store the structured fields in the execution log entry. Find where the log entry dict is built and add:

```python
log_entry = {
    "ts": datetime.now(timezone.utc).isoformat(),
    "result_summary": (result_text or "")[:1000],
    "eval_status": eval_status,       # "OK" | "ATTENZIONE" | "ANOMALIA" | None
    "action_taken": action_taken,     # str | None
}
```

- [ ] **Step 7: Run all tests**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add hiris/app/claude_runner.py hiris/app/agent_engine.py tests/test_claude_runner.py
git commit -m "$(cat <<'EOF'
feat: structured agent evaluation with VALUTAZIONE/AZIONE parsing

ClaudeRunner injects action instructions when agent has actions defined.
Response is parsed for VALUTAZIONE (OK/ATTENZIONE/ANOMALIA) and AZIONE
fields, stored in execution log alongside result_summary.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Action Builder UI + structured log display in config.html

**Files:**
- Modify: `hiris/app/static/config.html`

This task adds:
1. An "Azioni" fieldset in the agent form with an "Add action" flow (type selector → channel or domain/service/pattern → label)
2. Structured status badge in the execution log rows (shows `eval_status` badge + `action_taken` line)

- [ ] **Step 1: Add Azioni fieldset HTML**

Find the existing `allowed_services` / `call_ha_service` section in config.html (around line 468-472, the domain checkboxes). After that block, add a new fieldset:

```html
<fieldset class="form-section" id="actions-fieldset">
  <legend>Azioni configurate</legend>
  <div id="actions-list" class="actions-list"></div>
  <button type="button" class="btn-add-action" id="btn-add-action">+ Aggiungi azione</button>

  <!-- Inline action editor (hidden until "add" clicked) -->
  <div id="action-editor" class="action-editor" style="display:none">
    <div class="ae-row">
      <label>Tipo</label>
      <select id="ae-type">
        <option value="notify">Notifica</option>
        <option value="call_service">Chiama servizio HA</option>
      </select>
    </div>
    <div class="ae-row">
      <label>Etichetta</label>
      <input type="text" id="ae-label" placeholder="es. Avvisa via Telegram">
    </div>
    <div id="ae-notify-fields" class="ae-conditional">
      <div class="ae-row">
        <label>Canale</label>
        <select id="ae-channel">
          <option value="ha">Home Assistant push</option>
          <option value="telegram">Telegram</option>
          <option value="retropanel">Retro Panel toast</option>
        </select>
      </div>
    </div>
    <div id="ae-service-fields" class="ae-conditional" style="display:none">
      <div class="ae-row">
        <label>Dominio</label>
        <input type="text" id="ae-domain" placeholder="light">
      </div>
      <div class="ae-row">
        <label>Servizio</label>
        <input type="text" id="ae-service" placeholder="turn_off">
      </div>
      <div class="ae-row">
        <label>Pattern entità</label>
        <input type="text" id="ae-entity-pattern" placeholder="light.* (opzionale)">
      </div>
    </div>
    <div class="ae-buttons">
      <button type="button" id="ae-confirm">✓ Aggiungi</button>
      <button type="button" id="ae-cancel">Annulla</button>
    </div>
  </div>
</fieldset>
```

- [ ] **Step 2: Add CSS for action builder**

```css
/* Action builder */
.actions-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.action-item {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px;
  background: var(--surface-3); border: 1px solid var(--border); border-radius: 6px;
  font-size: 13px;
}
.action-item .ai-type {
  font-size: 11px; padding: 2px 6px; border-radius: 10px;
  background: var(--surface-4); color: var(--text-muted);
}
.action-item .ai-label { flex: 1; }
.action-item .ai-remove {
  cursor: pointer; color: var(--text-muted); font-size: 16px; line-height: 1;
}
.action-item .ai-remove:hover { color: var(--danger); }
.btn-add-action {
  background: var(--surface-4); border: 1px dashed var(--border-accent);
  color: var(--accent); font-size: 12px; padding: 5px 12px; border-radius: 6px;
  cursor: pointer;
}
.btn-add-action:hover { background: var(--surface-hover); }
.action-editor {
  margin-top: 10px; padding: 12px; background: var(--surface-3);
  border: 1px solid var(--border-accent); border-radius: 8px;
}
.ae-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ae-row label { width: 100px; font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.ae-row input, .ae-row select {
  flex: 1; padding: 5px 8px; background: var(--input-bg); border: 1px solid var(--border);
  color: var(--text); border-radius: 4px; font-size: 13px;
}
.ae-buttons { display: flex; gap: 8px; margin-top: 10px; }
.ae-buttons button {
  padding: 5px 14px; border-radius: 5px; border: 1px solid var(--border);
  cursor: pointer; font-size: 12px;
}
#ae-confirm { background: var(--accent); color: #fff; border-color: var(--accent); }
#ae-cancel { background: var(--surface-4); color: var(--text-muted); }

/* Execution log structured status */
.eval-badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
  font-weight: 600; margin-right: 6px;
}
.eval-ok    { background: #16532222; color: #34d399; border: 1px solid #16532266; }
.eval-warn  { background: #78350f22; color: #fbbf24; border: 1px solid #78350f66; }
.eval-alert { background: #7f1d1d22; color: #f87171; border: 1px solid #7f1d1d66; }
.log-action-taken { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
```

- [ ] **Step 3: Add JS for action builder**

Before the closing `</script>` tag, add:

```javascript
// ── Action Builder ───────────────────────────────────────────────────────────
let _agentActions = [];

function _actionsRender() {
  const list = document.getElementById('actions-list');
  list.innerHTML = '';
  _agentActions.forEach((a, i) => {
    const typeLabel = a.type === 'notify' ? 'Notifica' : 'Servizio';
    const detail = a.type === 'notify'
      ? `canale: ${a.channel || 'ha'}`
      : `${a.domain || ''}.${a.service || ''}${a.entity_pattern ? ' su ' + a.entity_pattern : ''}`;
    const div = document.createElement('div');
    div.className = 'action-item';
    div.innerHTML = `
      <span class="ai-type">${typeLabel}</span>
      <span class="ai-label">${a.label || '—'} <span style="color:var(--text-muted);font-size:11px">(${detail})</span></span>
      <span class="ai-remove" data-i="${i}">×</span>`;
    div.querySelector('.ai-remove').addEventListener('click', () => {
      _agentActions.splice(i, 1);
      _actionsRender();
    });
    list.appendChild(div);
  });
}

function _actionsLoad(actions) {
  _agentActions = Array.isArray(actions) ? JSON.parse(JSON.stringify(actions)) : [];
  _actionsRender();
}

function _actionsValue() {
  return JSON.parse(JSON.stringify(_agentActions));
}

// Show/hide editor
document.getElementById('btn-add-action').addEventListener('click', () => {
  document.getElementById('action-editor').style.display = 'block';
  document.getElementById('ae-label').value = '';
  document.getElementById('ae-domain').value = '';
  document.getElementById('ae-service').value = '';
  document.getElementById('ae-entity-pattern').value = '';
});

// Toggle notify vs service fields
document.getElementById('ae-type').addEventListener('change', function () {
  const isService = this.value === 'call_service';
  document.getElementById('ae-notify-fields').style.display = isService ? 'none' : '';
  document.getElementById('ae-service-fields').style.display = isService ? '' : 'none';
});

document.getElementById('ae-confirm').addEventListener('click', () => {
  const type = document.getElementById('ae-type').value;
  const label = document.getElementById('ae-label').value.trim();
  if (!label) { alert('Inserisci un\'etichetta per l\'azione.'); return; }
  const action = { type, label };
  if (type === 'notify') {
    action.channel = document.getElementById('ae-channel').value;
  } else {
    action.domain = document.getElementById('ae-domain').value.trim();
    action.service = document.getElementById('ae-service').value.trim();
    const ep = document.getElementById('ae-entity-pattern').value.trim();
    if (ep) action.entity_pattern = ep;
  }
  _agentActions.push(action);
  _actionsRender();
  document.getElementById('action-editor').style.display = 'none';
});

document.getElementById('ae-cancel').addEventListener('click', () => {
  document.getElementById('action-editor').style.display = 'none';
});
```

- [ ] **Step 4: Update `openAgent` to load actions**

In the `openAgent` function, add:

```javascript
_actionsLoad(agent.actions || []);
```

alongside the other field loads.

- [ ] **Step 5: Update `newAgent` to reset actions**

In the new-agent reset function, add:

```javascript
_actionsLoad([]);
```

- [ ] **Step 6: Update `saveAgent` to include actions**

In `saveAgent`, add to the body dict:

```javascript
actions: _actionsValue(),
```

- [ ] **Step 7: Update execution log rendering to show eval_status + action_taken**

Find the log row rendering code (around lines 614-638 after Task 4 changes). The log entry dict now has `eval_status` and `action_taken` fields. Update the row template to show them:

```javascript
const EVAL_CLASS = { OK: 'eval-ok', ATTENZIONE: 'eval-warn', ANOMALIA: 'eval-alert' };
const evalStatus = row.eval_status;
const evalBadge = evalStatus
  ? `<span class="eval-badge ${EVAL_CLASS[evalStatus] || ''}">${evalStatus}</span>`
  : '';
const actionLine = row.action_taken
  ? `<div class="log-action-taken">↳ ${row.action_taken}</div>`
  : '';
```

In the log row `<td class="log-summary">` cell, prepend `evalBadge` before the preview text, and append `actionLine` after the expand button.

Final log summary cell template:

```javascript
`<td class="log-summary">
  ${evalBadge}
  <span class="log-preview">${preview}</span>
  ${isLong ? `<span class="log-full" style="display:none">${summary}</span>
  <button class="log-expand-btn" onclick="toggleLogRow('${rowId}')">▼ espandi</button>` : ''}
  ${actionLine}
</td>`
```

- [ ] **Step 8: Manual smoke test**

1. Create an agent with type "monitor"
2. Add a "Notifica via Telegram" action and a "Spegni luci" call_service action
3. Save → reload → verify actions persist and show in list
4. Run the agent (requires Claude runner) → execution log shows `eval_status` badge
5. Verify `VALUTAZIONE:` and `AZIONE:` lines are NOT visible in the result text (stripped by parser)

- [ ] **Step 9: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "$(cat <<'EOF'
feat: action builder UI and structured evaluation display in log

Agents can define notify/call_service actions via inline editor.
Execution log shows VALUTAZIONE badge (OK/ATTENZIONE/ANOMALIA)
and action taken alongside result summary.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Version bump 0.1.4 → 0.1.5

**Files:**
- Modify: `hiris/app/server.py` (line 125: `"version": "0.1.4"`)
- Modify: `config.yaml` (version field)
- Modify: `tests/test_api.py` (version assertion)

- [ ] **Step 1: Bump version in server.py**

Find line 125 in `hiris/app/server.py`:

```python
    return web.json_response({"status": "ok", "version": "0.1.4"})
```

Change to:

```python
    return web.json_response({"status": "ok", "version": "0.1.5"})
```

- [ ] **Step 2: Bump version in config.yaml**

Find the `version:` field in `config.yaml` and change `"0.1.4"` to `"0.1.5"`.

- [ ] **Step 3: Bump version in tests/test_api.py**

Find the version assertion in `tests/test_api.py` (the health endpoint test) and update `"0.1.4"` to `"0.1.5"`.

- [ ] **Step 4: Run tests**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add hiris/app/server.py config.yaml tests/test_api.py
git commit -m "$(cat <<'EOF'
chore: bump version to 0.1.5

Agent action system and UX improvements complete.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Agents declare permitted/planned actions | Task 5 (Agent.actions field) |
| Actions configurable in designer UI | Task 7 (fieldset + action editor) |
| Notify and call_service action types | Tasks 5, 6, 7 |
| Claude receives action instructions | Task 6 (run_with_actions + _build_action_instructions) |
| Structured VALUTAZIONE/AZIONE response | Task 6 (_parse_structured_response) |
| eval_status/action_taken stored in log | Task 6 (log entry update) |
| Log shows evaluation badge | Task 7 (eval_badge CSS + render) |
| Log shows action taken | Task 7 (actionLine in row) |
| Version bump 0.1.4 → 0.1.5 | Task 8 |

### No Placeholders

All steps include actual code. No "TBD" or vague instructions.

### Type Consistency

- `actions` field: `list[dict]` throughout — Agent dataclass, `_actionsValue()`, `saveAgent` body, `run_with_actions` parameter.
- `_build_action_instructions(actions: list[dict]) -> str` — module-level function, called in `run_with_actions`.
- `_parse_structured_response(text: str) -> tuple[str, str | None, str | None]` — consistent `(text, eval_status, action_taken)` tuple throughout Tasks 6 and 6 log update.
- `EVAL_CLASS` dict in frontend matches backend values `"OK"`, `"ATTENZIONE"`, `"ANOMALIA"` — consistent with `_parse_structured_response` output.
