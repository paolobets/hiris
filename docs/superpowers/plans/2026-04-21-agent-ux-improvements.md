# Agent Designer UX Improvements — Plan A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the HIRIS Agent Designer UI with a proper entity selector (multi-select with domain pills + search), polished test-run UX (spinner, scroll, empty state), and expandable execution log rows.

**Architecture:** Three independent UX improvements in `config.html` (frontend only), plus one new backend endpoint `GET /api/entities` to power the entity selector. No changes to Agent data model or agent_engine.py.

**Tech Stack:** Python 3.11 + aiohttp (backend), vanilla JS + CSS (frontend, no framework), existing dark-theme CSS variables in config.html.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `hiris/app/api/handlers_agents.py` | Modify | Add `handle_list_entities` handler |
| `hiris/app/server.py` | Modify | Register `GET /api/entities` route |
| `hiris/app/static/config.html` | Modify | Entity selector, test-run UX, log improvements |
| `tests/test_handlers_agents.py` | Create | Tests for `handle_list_entities` |

---

### Task 1: `GET /api/entities` backend endpoint

**Files:**
- Modify: `hiris/app/api/handlers_agents.py`
- Modify: `hiris/app/server.py`
- Create: `tests/test_handlers_agents.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_handlers_agents.py`:

```python
import pytest
from unittest.mock import MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_agents import handle_list_entities


@pytest.mark.asyncio
async def test_list_entities_returns_sorted_entities():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "switch.relay", "state": "off",  "name": "Relay",   "unit": ""},
        {"id": "light.salon",  "state": "on",   "name": "Salon",   "unit": ""},
        {"id": "sensor.temp",  "state": "21.5", "name": "Temp",    "unit": "°C"},
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities", app=app)

    resp = await handle_list_entities(request)
    data = resp.body
    import json
    entities = json.loads(data)

    assert len(entities) == 3
    ids = [e["id"] for e in entities]
    assert ids == sorted(ids)
    assert entities[0]["domain"] == entities[0]["id"].split(".")[0]


@pytest.mark.asyncio
async def test_list_entities_search_filter():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "light.salon",   "state": "on",  "name": "Salon Light", "unit": ""},
        {"id": "sensor.temp",   "state": "21",  "name": "Temperature", "unit": "°C"},
        {"id": "light.kitchen", "state": "off", "name": "Kitchen",     "unit": ""},
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request(
        "GET", "/api/entities?q=light",
        match_info={},
        app=app,
    )
    # Override query string
    request = make_mocked_request("GET", "/api/entities", app=app)
    request.rel_url = MagicMock()
    request.rel_url.query = {"q": "light"}

    resp = await handle_list_entities(request)
    import json
    entities = json.loads(resp.body)
    assert all("light" in e["id"] or "light" in e["name"].lower() for e in entities)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd C:\Work\Sviluppo\hiris
pytest tests/test_handlers_agents.py -v
```

Expected: `ImportError` or `AttributeError` — `handle_list_entities` does not exist yet.

- [ ] **Step 3: Implement `handle_list_entities` in `handlers_agents.py`**

Add at the end of `hiris/app/api/handlers_agents.py`:

```python
async def handle_list_entities(request: web.Request) -> web.Response:
    cache = request.app["entity_cache"]
    q = request.rel_url.query.get("q", "").lower().strip()
    entities = []
    for e in cache.get_all():
        domain = e["id"].split(".")[0]
        entities.append({
            "id": e["id"],
            "name": e.get("name", ""),
            "state": e.get("state", ""),
            "domain": domain,
        })
    if q:
        entities = [
            e for e in entities
            if q in e["id"].lower() or q in e["name"].lower() or q in e["domain"].lower()
        ]
    entities.sort(key=lambda e: e["id"])
    return web.json_response(entities)
```

- [ ] **Step 4: Register the route in `server.py`**

In `hiris/app/server.py`, add the import and route.

Add `handle_list_entities` to the import line (line 7):

```python
from .api.handlers_agents import handle_list_agents, handle_create_agent, handle_get_agent, handle_update_agent, handle_delete_agent, handle_run_agent, handle_list_entities
```

Add route after `handle_run_agent` route (after line 105):

```python
    app.router.add_get("/api/entities", handle_list_entities)
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_handlers_agents.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```
pytest --tb=short -q
```

Expected: all pass (currently 169 tests).

- [ ] **Step 7: Commit**

```bash
git add hiris/app/api/handlers_agents.py hiris/app/server.py tests/test_handlers_agents.py
git commit -m "$(cat <<'EOF'
feat: add GET /api/entities endpoint for entity selector

Returns all cached entities with id/name/state/domain,
supports ?q= search filter, sorted by entity id.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Entity Selector — replace textarea with multi-select chips

**Files:**
- Modify: `hiris/app/static/config.html`

This task replaces the plain `<textarea id="f-entities">` (lines 465-467) with a multi-select component that has:
- Domain-pill quick-add buttons (light, sensor, switch, climate, cover, binary_sensor, person)
- A search input that queries `GET /api/entities?q=...` after 300ms debounce
- Chips display for selected patterns/entities
- Hidden `<input type="hidden" id="f-entities-hidden">` whose value is a JSON array stringified (to replace the old textarea value)

The existing code reads `f-entities.value` (a textarea) and splits by newline/comma to get entity patterns. After this task it will read from the hidden input.

- [ ] **Step 1: Identify the exact textarea block in config.html**

The entity section is around lines 460-475 in `config.html`. It looks like:

```html
<div class="form-group" id="entities-group">
  <label>Entità permesse <span class="hint">(fnmatch: light.*, sensor.temp)</span></label>
  <textarea id="f-entities" rows="3" placeholder="light.*&#10;sensor.temp&#10;switch.*"></textarea>
</div>
```

- [ ] **Step 2: Replace the textarea with the new entity selector HTML**

Find the exact textarea block and replace with:

```html
<div class="form-group" id="entities-group">
  <label>Entità permesse</label>
  <div class="entity-selector">
    <div class="entity-domain-pills" id="entity-domain-pills">
      <span class="domain-pill" data-pattern="light.*">💡 luci</span>
      <span class="domain-pill" data-pattern="switch.*">🔌 switch</span>
      <span class="domain-pill" data-pattern="sensor.*">📊 sensori</span>
      <span class="domain-pill" data-pattern="climate.*">🌡️ clima</span>
      <span class="domain-pill" data-pattern="cover.*">🪟 tapparelle</span>
      <span class="domain-pill" data-pattern="binary_sensor.*">⚡ binari</span>
      <span class="domain-pill" data-pattern="person.*">🧑 persone</span>
    </div>
    <div class="entity-search-row">
      <input type="text" id="entity-search" placeholder="Cerca entità…" autocomplete="off">
      <div id="entity-suggestions" class="entity-suggestions" style="display:none"></div>
    </div>
    <div id="entity-chips" class="entity-chips"></div>
    <input type="hidden" id="f-entities">
  </div>
</div>
```

- [ ] **Step 3: Add CSS for entity selector**

In the `<style>` block, add before the closing `</style>`:

```css
/* Entity selector */
.entity-selector { display: flex; flex-direction: column; gap: 8px; }
.entity-domain-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.domain-pill {
  padding: 4px 10px; border-radius: 12px; font-size: 12px; cursor: pointer;
  background: var(--surface-4); color: var(--text-muted); border: 1px solid var(--border);
  user-select: none; transition: background 0.15s, color 0.15s;
}
.domain-pill:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.entity-search-row { position: relative; }
#entity-search {
  width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--input-bg); color: var(--text); font-size: 13px; box-sizing: border-box;
}
#entity-search:focus { outline: none; border-color: var(--accent); }
.entity-suggestions {
  position: absolute; top: calc(100% + 2px); left: 0; right: 0; z-index: 100;
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  max-height: 180px; overflow-y: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.suggestion-item {
  padding: 7px 12px; cursor: pointer; font-size: 13px; display: flex;
  justify-content: space-between; align-items: center;
}
.suggestion-item:hover { background: var(--surface-hover); }
.suggestion-item .s-name { color: var(--text-muted); font-size: 11px; }
.entity-chips { display: flex; flex-wrap: wrap; gap: 6px; min-height: 10px; }
.entity-chip {
  display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px;
  border-radius: 12px; background: var(--surface-4); border: 1px solid var(--border-accent);
  font-size: 12px; color: var(--text);
}
.entity-chip .chip-remove {
  cursor: pointer; color: var(--text-muted); font-size: 14px; line-height: 1;
  padding: 0 1px;
}
.entity-chip .chip-remove:hover { color: var(--danger); }
```

- [ ] **Step 4: Add JS for entity selector**

Find the script block (before `</script>`) in `config.html` and add the entity selector logic. Add before the closing `</script>` tag:

```javascript
// ── Entity Selector ─────────────────────────────────────────────────────────
let _entitySelectionSet = new Set();

function _entitySelectorRender() {
  const chips = document.getElementById('entity-chips');
  chips.innerHTML = '';
  for (const pattern of _entitySelectionSet) {
    const chip = document.createElement('span');
    chip.className = 'entity-chip';
    chip.innerHTML = `<span>${pattern}</span><span class="chip-remove" data-p="${pattern}">×</span>`;
    chip.querySelector('.chip-remove').addEventListener('click', () => {
      _entitySelectionSet.delete(pattern);
      _entitySelectorRender();
    });
    chips.appendChild(chip);
  }
  document.getElementById('f-entities').value = JSON.stringify([..._entitySelectionSet]);
}

function _entitySelectorAdd(pattern) {
  if (pattern && !_entitySelectionSet.has(pattern)) {
    _entitySelectionSet.add(pattern);
    _entitySelectorRender();
  }
}

function _entitySelectorLoad(patterns) {
  _entitySelectionSet = new Set(Array.isArray(patterns) ? patterns : []);
  _entitySelectorRender();
}

// Domain pills
document.querySelectorAll('.domain-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    _entitySelectorAdd(pill.dataset.pattern);
    document.getElementById('entity-search').value = '';
  });
});

// Search with debounce
let _entitySearchTimer = null;
const _entitySearchInput = document.getElementById('entity-search');
const _entitySuggestions = document.getElementById('entity-suggestions');

_entitySearchInput.addEventListener('input', () => {
  clearTimeout(_entitySearchTimer);
  const q = _entitySearchInput.value.trim();
  if (!q) { _entitySuggestions.style.display = 'none'; return; }
  _entitySearchTimer = setTimeout(async () => {
    try {
      const resp = await fetch(`/api/entities?q=${encodeURIComponent(q)}`);
      const items = await resp.json();
      _entitySuggestions.innerHTML = '';
      if (!items.length) {
        _entitySuggestions.style.display = 'none';
        return;
      }
      items.slice(0, 20).forEach(e => {
        const div = document.createElement('div');
        div.className = 'suggestion-item';
        div.innerHTML = `<span>${e.id}</span><span class="s-name">${e.name || ''}</span>`;
        div.addEventListener('click', () => {
          _entitySelectorAdd(e.id);
          _entitySearchInput.value = '';
          _entitySuggestions.style.display = 'none';
        });
        _entitySuggestions.appendChild(div);
      });
      _entitySuggestions.style.display = 'block';
    } catch (_) { /* ignore */ }
  }, 300);
});

// Allow typing a pattern directly and pressing Enter
_entitySearchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const q = _entitySearchInput.value.trim();
    if (q) {
      _entitySelectorAdd(q);
      _entitySearchInput.value = '';
      _entitySuggestions.style.display = 'none';
    }
  }
  if (e.key === 'Escape') {
    _entitySuggestions.style.display = 'none';
  }
});

document.addEventListener('click', (e) => {
  if (!_entitySearchInput.contains(e.target) && !_entitySuggestions.contains(e.target)) {
    _entitySuggestions.style.display = 'none';
  }
});
```

- [ ] **Step 5: Update `openAgent` to load entity selector**

Find the `openAgent` function in the JS (around line 700-740). It currently sets `document.getElementById('f-entities').value = (agent.allowed_entities || []).join('\n')`.

Replace that line with:

```javascript
_entitySelectorLoad(agent.allowed_entities || []);
```

- [ ] **Step 6: Update `saveAgent` to read entity selector**

Find the `saveAgent` function. It currently reads `f-entities` as a textarea and splits by newline:

```javascript
allowed_entities: document.getElementById('f-entities').value.split('\n').map(s=>s.trim()).filter(Boolean),
```

Replace with:

```javascript
allowed_entities: JSON.parse(document.getElementById('f-entities').value || '[]'),
```

- [ ] **Step 7: Update `newAgent` / reset logic to clear entity selector**

Find where a new agent form is initialized (the `newAgent()` function or equivalent reset). Add:

```javascript
_entitySelectorLoad([]);
```

alongside the other field resets.

- [ ] **Step 8: Manual smoke test**

1. Open `http://localhost:8099/config`
2. Open or create an agent
3. Click a domain pill (e.g., "💡 luci") → chip `light.*` appears
4. Type "sensor" in search → dropdown shows matching entities
5. Click a suggestion → chip appears
6. Click × on a chip → chip disappears
7. Save agent → reload → chips re-populate correctly

- [ ] **Step 9: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "$(cat <<'EOF'
feat: replace entity textarea with multi-select chip selector

Domain-pill quick-add, live entity search via /api/entities,
chips display with remove button, Enter to add patterns directly.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Test-run UX — spinner, scroll, empty state, timeout feedback

**Files:**
- Modify: `hiris/app/static/config.html`

Current behavior: clicking "Test Run" calls `/api/agents/{id}/run`, then shows the result in `#run-output`. No loading indicator, output div hidden on `openAgent()` (so it disappears when re-opening), no scroll to output, no feedback if result is empty.

- [ ] **Step 1: Identify the run button and output block**

In `config.html`, around lines 820-840:

```html
<button class="btn-run" id="btn-run-agent">▶ Test Run</button>
...
<div id="run-output" style="display:none">
  <div class="run-label">Risultato</div>
  <pre id="run-result"></pre>
</div>
```

And the handler (around lines 820-833):

```javascript
document.getElementById('btn-run-agent').addEventListener('click', async () => {
  const id = document.getElementById('f-id').value;
  if (!id) return;
  const resp = await fetch(`/api/agents/${id}/run`, { method: 'POST' });
  const data = await resp.json();
  document.getElementById('run-result').textContent = data.result || '(nessun risultato)';
  document.getElementById('run-output').style.display = 'block';
});
```

- [ ] **Step 2: Add spinner CSS**

In the `<style>` block, add:

```css
/* Run button states */
.btn-run { position: relative; }
.btn-run.running { opacity: 0.7; cursor: not-allowed; }
.btn-run .spinner {
  display: none; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite;
  vertical-align: middle; margin-right: 6px;
}
.btn-run.running .spinner { display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Run output panel */
#run-output { margin-top: 12px; }
.run-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--text-muted); margin-bottom: 6px; }
#run-result {
  background: var(--terminal-bg); color: var(--terminal-text);
  border: 1px solid var(--terminal-border); border-radius: 6px;
  padding: 12px 14px; font-size: 12px; white-space: pre-wrap; word-break: break-word;
  max-height: 300px; overflow-y: auto; line-height: 1.5;
}
.run-empty { color: var(--text-muted); font-style: italic; }
.run-error { color: var(--danger); }
```

- [ ] **Step 3: Update the run button HTML to include spinner element**

Replace:

```html
<button class="btn-run" id="btn-run-agent">▶ Test Run</button>
```

With:

```html
<button class="btn-run" id="btn-run-agent"><span class="spinner"></span>▶ Test Run</button>
```

- [ ] **Step 4: Replace the run click handler**

Find and replace the existing click handler with:

```javascript
document.getElementById('btn-run-agent').addEventListener('click', async () => {
  const id = document.getElementById('f-id').value;
  if (!id) return;
  const btn = document.getElementById('btn-run-agent');
  const output = document.getElementById('run-output');
  const pre = document.getElementById('run-result');

  btn.classList.add('running');
  btn.disabled = true;
  output.style.display = 'block';
  pre.className = '';
  pre.textContent = 'Avvio esecuzione…';

  const timeout = 90_000; // 90s
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);

  try {
    const resp = await fetch(`/api/agents/${id}/run`, {
      method: 'POST',
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    const data = await resp.json();
    const result = data.result || '';
    if (!result.trim()) {
      pre.className = 'run-empty';
      pre.textContent = '(nessun risultato restituito dall\'agente)';
    } else {
      pre.className = '';
      pre.textContent = result;
    }
  } catch (err) {
    clearTimeout(timer);
    pre.className = 'run-error';
    if (err.name === 'AbortError') {
      pre.textContent = '⏱ Timeout: l\'agente non ha risposto entro 90 secondi.';
    } else {
      pre.textContent = `Errore: ${err.message}`;
    }
  } finally {
    btn.classList.remove('running');
    btn.disabled = false;
    output.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
});
```

- [ ] **Step 5: Keep output visible when re-opening agent (remove hide on openAgent)**

In the `openAgent` function, find:

```javascript
document.getElementById('run-output').style.display = 'none';
```

Replace with nothing (delete this line) OR change it to only reset content but keep visible if there was a previous result:

```javascript
// Clear previous run output when opening a new agent
document.getElementById('run-result').textContent = '';
document.getElementById('run-output').style.display = 'none';
```

Keep the `display = 'none'` when switching agents (to avoid showing a stale previous result), but ensure that after a fresh run completes the panel stays visible.

- [ ] **Step 6: Manual smoke test**

1. Open agent designer, select an agent with Claude runner configured
2. Click "Test Run" → spinner appears, button disabled
3. Result appears after completion → panel visible, scrolled into view
4. Open a different agent → run output hidden (clean state)
5. Click "Test Run" on an agent with no claude_runner → error message appears in red

- [ ] **Step 7: Commit**

```bash
git add hiris/app/static/config.html
git commit -m "$(cat <<'EOF'
feat: polish test-run UX with spinner, scroll-to, and empty-state handling

Adds loading spinner, 90s timeout, proper error display,
empty-result message, and auto-scroll to output panel.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Execution Log — expand rows + increase summary length

**Files:**
- Modify: `hiris/app/agent_engine.py` (increase truncation from 200 to 1000 chars)
- Modify: `hiris/app/static/config.html` (expandable log rows)

- [ ] **Step 1: Fix truncation in agent_engine.py**

Find line 373 in `hiris/app/agent_engine.py`:

```python
"result_summary": (result or "")[:200],
```

Replace with:

```python
"result_summary": (result or "")[:1000],
```

- [ ] **Step 2: Write test for new truncation length**

In `tests/test_agent_engine.py`, add a test that verifies 1000-char truncation:

```python
@pytest.mark.asyncio
async def test_execution_log_result_summary_truncated_at_1000(tmp_path):
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
        "name": "Log Test", "type": "monitor",
        "trigger": {"type": "manual"},
    })

    long_result = "x" * 1500
    mock_runner = MagicMock()
    mock_runner.chat = AsyncMock(return_value=long_result)
    engine.set_claude_runner(mock_runner)

    await engine.run_agent(agent)
    assert len(agent.execution_log[0]["result_summary"]) == 1000

    await engine.stop()
```

- [ ] **Step 3: Run the new test — verify it fails first**

```
pytest tests/test_agent_engine.py::test_execution_log_result_summary_truncated_at_1000 -v
```

Expected: FAIL (still truncates at 200 before the fix is applied, or AssertionError 200 != 1000).

- [ ] **Step 4: Apply the truncation fix**

Edit `hiris/app/agent_engine.py` line 373 as described in Step 1.

- [ ] **Step 5: Run test — verify it passes**

```
pytest tests/test_agent_engine.py::test_execution_log_result_summary_truncated_at_1000 -v
```

Expected: PASS.

- [ ] **Step 6: Make log rows expandable in config.html**

Find the log rendering code in `config.html` (around lines 614-638). It renders a table/list with `result_summary` shown as a single truncated line.

The current log row renders something like:

```javascript
`<tr>
  <td>${ts}</td>
  <td class="log-summary">${row.result_summary || ''}</td>
</tr>`
```

Replace the log row template with an expandable version:

```javascript
const rowId = `log-row-${Math.random().toString(36).slice(2)}`;
const summary = row.result_summary || '';
const isLong = summary.length > 120;
const preview = isLong ? summary.slice(0, 120) + '…' : summary;

`<tr class="log-row" id="${rowId}">
  <td class="log-ts">${ts}</td>
  <td class="log-summary">
    <span class="log-preview">${preview}</span>
    ${isLong ? `<span class="log-full" style="display:none">${summary}</span>
    <button class="log-expand-btn" onclick="toggleLogRow('${rowId}')">▼ espandi</button>` : ''}
  </td>
</tr>`
```

Add the JS function:

```javascript
function toggleLogRow(rowId) {
  const row = document.getElementById(rowId);
  const preview = row.querySelector('.log-preview');
  const full = row.querySelector('.log-full');
  const btn = row.querySelector('.log-expand-btn');
  const expanded = full.style.display !== 'none';
  preview.style.display = expanded ? '' : 'none';
  full.style.display = expanded ? 'none' : '';
  btn.textContent = expanded ? '▼ espandi' : '▲ comprimi';
}
```

Add CSS:

```css
.log-expand-btn {
  background: none; border: none; color: var(--accent); font-size: 11px;
  cursor: pointer; padding: 0; margin-left: 6px;
}
.log-expand-btn:hover { text-decoration: underline; }
.log-full { display: block; white-space: pre-wrap; margin-top: 4px; }
.log-preview { display: inline; }
```

- [ ] **Step 7: Run full test suite**

```
pytest --tb=short -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add hiris/app/agent_engine.py hiris/app/static/config.html tests/test_agent_engine.py
git commit -m "$(cat <<'EOF'
feat: improve execution log — 1000-char summary and expandable rows

Increase result_summary truncation from 200 to 1000 chars.
Log rows with >120 chars show preview + expand/collapse button.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| Entity selector: replace textarea with multi-select | Task 2 |
| Entity selector: domain pattern pills | Task 2 |
| Entity selector: search individual entities | Tasks 1 + 2 |
| Test run: spinner during execution | Task 3 |
| Test run: scroll to output | Task 3 |
| Test run: empty state message | Task 3 |
| Test run: timeout handling | Task 3 |
| Log: increase truncation (200→1000) | Task 4 |
| Log: expandable rows | Task 4 |

### No Placeholders

All steps include actual code. No "TBD" or "implement later" patterns.

### Type Consistency

- `f-entities` is now `<input type="hidden">` throughout — Task 2 Step 2 replaces textarea, Steps 5-7 update all JS references.
- `handle_list_entities` returns `list[dict]` with keys: `id`, `name`, `state`, `domain`.
- `_entitySelectorLoad` / `_entitySelectorAdd` / `_entitySelectorRender` — consistent naming throughout Task 2.
