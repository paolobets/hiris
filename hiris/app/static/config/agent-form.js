/* HIRIS · Designer · agent form (CRUD + run)
   Glues the tabs, list, save/delete/run. Calls into permessi.js, triggers.js,
   action-editor.js, logs.js, usage.js. */

var agents = [];
var currentId = null;

async function loadAgents() {
  try {
    var r = await fetch('api/agents');
    agents = await r.json();
    renderList();
  } catch(e) {}
}

function renderList() {
  var el = document.getElementById('agent-list');
  el.innerHTML = '';
  agents.forEach(function(a) {
    var row = document.createElement('div');
    row.className = 'agent-row' + (a.id === currentId ? ' active' : '');
    var typeLabel = (a.type === 'chat') ? 'Chat' : 'Agent';
    row.innerHTML = '<span>' + esc(a.name) + ' <small style="color:var(--text-muted);font-size:0.7rem">' + typeLabel + '</small></span><span class="badge ' + (a.enabled ? '' : 'off') + '">' + (a.enabled ? 'ON' : 'OFF') + '</span>';
    row.addEventListener('click', function() { openAgent(a); });
    el.appendChild(row);
  });
}

function showAgentMode(type) {
  var isAgent = type === 'agent';
  document.getElementById('agent-triggers-section').style.display = isAgent ? '' : 'none';
  var maxTurnsRow = document.getElementById('max-turns-row');
  if (maxTurnsRow) maxTurnsRow.style.display = type === 'chat' ? '' : 'none';
  var actionsTabBtn = document.querySelector('#agent-tabs .tab-btn[data-tab="tab-azioni"]');
  if (actionsTabBtn) {
    actionsTabBtn.style.display = isAgent ? '' : 'none';
    if (!isAgent && document.getElementById('tab-azioni') && document.getElementById('tab-azioni').classList.contains('tab-active')) {
      switchTab('tab-identity');
    }
  }
}

function showActionMode(mode) {
  document.getElementById('configured-actions-section').style.display = mode === 'configured' ? '' : 'none';
}

function _defaultStates() {
  var raw = (document.getElementById('f-states').value || '');
  var parts = raw.split(',').map(function(s) { return s.trim().toUpperCase(); }).filter(function(s) { return s.length > 0; });
  return parts.length > 0 ? parts : ['OK', 'ATTENZIONE', 'ANOMALIA'];
}

function _buildTriggerOnChecks(states, selectedValues) {
  var container = document.getElementById('trigger-on-checks');
  container.innerHTML = '';
  (states || _defaultStates()).forEach(function(s) {
    var lbl = document.createElement('label');
    lbl.style.cssText = 'display:flex;align-items:center;gap:5px;font-size:0.8rem;color:var(--text);margin:0;cursor:pointer';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.name = 'trigger_on';
    chk.value = s;
    chk.checked = (selectedValues || []).indexOf(s) >= 0;
    lbl.appendChild(chk);
    lbl.appendChild(document.createTextNode(' ' + s));
    container.appendChild(lbl);
  });
}

function _triggerOnValue() {
  return Array.from(document.querySelectorAll('#trigger-on-checks input[name="trigger_on"]:checked'))
    .map(function(i) { return i.value; });
}

document.getElementById('f-type').addEventListener('change', function(e) {
  showAgentMode(e.target.value);
  updateConfirmFreeVisibility();
});
document.getElementById('f-action-mode').addEventListener('change', function(e) { showActionMode(e.target.value); });
document.getElementById('f-model').addEventListener('change', updateConfirmFreeVisibility);

/* Show the "accept :free risks" checkbox only for autonomous agents on a
   :free OpenRouter model. The server enforces the same rule with HTTP 400
   (handlers_agents._validate_free_model_for_agent_type); the UI mirrors it
   so the user gets the warning before clicking save. When the field is
   hidden the checkbox stays unchecked and is omitted from the save payload. */
function updateConfirmFreeVisibility() {
  var row = document.getElementById('confirm-free-row');
  if (!row) return;
  var type = document.getElementById('f-type').value;
  var model = document.getElementById('f-model').value || '';
  var shouldShow = (type === 'agent') && /:free$/.test(model);
  row.style.display = shouldShow ? '' : 'none';
}

document.getElementById('f-states').addEventListener('blur', function() {
  var current = _triggerOnValue();
  _buildTriggerOnChecks(_defaultStates(), current);
});

function openAgent(a) {
  currentId = a.id;
  /* v0.10.2 defensive guards: tutti i getElementById(...).style/.textContent
     che toccavano ID legacy ora protetti per evitare TypeError se la pagina
     v6 è caricata da cache stale senza shim. */
  var _ftpl = document.getElementById('f-template'); if (_ftpl) _ftpl.value = '';
  var _ns = document.getElementById('no-selection'); if (_ns) _ns.style.display = 'none';
  var _fm = document.getElementById('form'); if (_fm) _fm.style.display = '';
  if (typeof resetToFirstTab === 'function') resetToFirstTab();
  var _ft = document.getElementById('form-title'); if (_ft) _ft.textContent = a.name;
  var _fn = document.getElementById('f-name'); if (_fn) _fn.value = a.name;
  /* Normalize legacy types (monitor/reactive/preventive → agent) */
  var agentType = (a.type === 'chat') ? 'chat' : 'agent';
  document.getElementById('f-type').value = agentType;
  /* Load triggers (new format) or migrate from legacy single trigger */
  var triggers = a.triggers && a.triggers.length ? a.triggers :
    (a.trigger ? [a.trigger] : []);
  _triggersLoad(triggers);
  document.getElementById('f-prompt').value = a.system_prompt || '';
  document.getElementById('f-strategic').value = a.strategic_context || '';
  _entitySelectorLoad(a.allowed_entities || []);
  document.getElementById('f-enabled').checked = a.enabled;
  _setModelValue(a.model || 'auto');
  /* Pre-check confirm-free if existing agent is already saved on a :free
     model — that means the user already accepted the warning at some point
     (otherwise the server would have rejected the save). */
  document.getElementById('f-confirm-free').checked = /:free$/.test(a.model || '');
  updateConfirmFreeVisibility();
  document.getElementById('f-max-tokens').value = a.max_tokens || 4096;
  document.getElementById('f-restrict').checked = !!a.restrict_to_home;
  document.getElementById('f-require-confirmation').checked = !!a.require_confirmation;
  document.getElementById('f-max-chat-turns').value = a.max_chat_turns || 0;
  document.getElementById('f-response-mode').value = a.response_mode || 'auto';
  document.getElementById('f-thinking-budget').value = String(a.thinking_budget || 0);
  buildActionChecks(a.allowed_services || []);
  /* Load actions from first rule (configured mode) or legacy actions field */
  var firstRule = a.rules && a.rules.length ? a.rules[0] : null;
  _actionsLoad(firstRule ? (firstRule.actions || []) : (a.actions || []));
  /* action_mode */
  var actionMode = a.action_mode || 'automatic';
  document.getElementById('f-action-mode').value = actionMode;
  showActionMode(actionMode);
  var _db = document.getElementById('delete-btn');
  if (_db) _db.style.display = a.is_default ? 'none' : '';
  var ro = document.getElementById('run-output');
  if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }
  /* buildToolChecks must run after buildActionChecks — it owns the final updateServicesVisibility() call */
  buildToolChecks(a.allowed_tools || []);
  showAgentMode(agentType);
  renderList();
  renderExecutionLog(a);
  loadAgentUsage(a.id);
  updateAgentUsageToggleBtn(a);
  updateTokenCounter();
  loadContextPreview(a.id);
  document.getElementById('u-ag-budget').value = a.budget_eur_limit || 0;
  var agentStates = (a.states && a.states.length) ? a.states : ['OK', 'ATTENZIONE', 'ANOMALIA'];
  document.getElementById('f-states').value = agentStates.join(', ');
  var ruleStates = firstRule ? (firstRule.states || ['ANOMALIA']) : (a.trigger_on || ['ANOMALIA']);
  _buildTriggerOnChecks(agentStates, ruleStates);
}

/* v0.10.2: questo handler è inerte in v6 (new-btn è solo uno shim div).
   Il path "Nuovo agente" v6 passa per HirisAgentEditor.initNewAgent() in
   agent-editor.js. Lasciato per backward compat nel caso il vecchio markup
   venga ripristinato. Tutti i .style protetti con guard for safety. */
var _nb = document.getElementById('new-btn');
if (_nb) _nb.addEventListener('click', function() {
  currentId = null;
  var _e1 = document.getElementById('f-template'); if (_e1) _e1.value = '';
  var _e2 = document.getElementById('no-selection'); if (_e2) _e2.style.display = 'none';
  var _e3 = document.getElementById('form'); if (_e3) _e3.style.display = '';
  if (typeof resetToFirstTab === 'function') resetToFirstTab();
  var _e4 = document.getElementById('form-title'); if (_e4) _e4.textContent = 'Nuovo agente';
  var _e5 = document.getElementById('f-name'); if (_e5) _e5.value = '';
  document.getElementById('f-type').value = 'agent';
  _triggersLoad([]);
  document.getElementById('f-prompt').value = '';
  document.getElementById('f-strategic').value = '';
  _entitySelectorLoad([]);
  document.getElementById('f-enabled').checked = true;
  _setModelValue('auto');
  document.getElementById('f-confirm-free').checked = false;
  updateConfirmFreeVisibility();
  document.getElementById('f-max-tokens').value = 4096;
  document.getElementById('f-restrict').checked = false;
  document.getElementById('f-require-confirmation').checked = false;
  document.getElementById('f-max-chat-turns').value = 0;
  document.getElementById('f-response-mode').value = 'auto';
  document.getElementById('f-thinking-budget').value = '0';
  buildActionChecks([]);
  _actionsLoad([]);
  document.getElementById('f-action-mode').value = 'automatic';
  showActionMode('automatic');
  var _db2 = document.getElementById('delete-btn');
  if (_db2) _db2.style.display = 'none';
  var ro = document.getElementById('run-output');
  if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }
  buildToolChecks([]);
  showAgentMode('agent');
  renderExecutionLog(null);
  document.getElementById('u-ag-budget').value = 0;
  document.getElementById('f-states').value = 'OK, ATTENZIONE, ANOMALIA';
  _buildTriggerOnChecks(['OK', 'ATTENZIONE', 'ANOMALIA'], ['ANOMALIA']);
  updateTokenCounter();
  var _tc = document.getElementById('tc-context'); if (_tc) _tc.textContent = '—';
  var _cw = document.getElementById('context-preview-wrap'); if (_cw) _cw.style.display = 'none';
});

function buildPayload() {
  var type = document.getElementById('f-type').value;
  var actionMode = document.getElementById('f-action-mode').value;
  var rules = [];
  if (actionMode === 'configured') {
    rules = [{states: _triggerOnValue(), actions: _actionsValue()}];
  }
  var payload = {
    name: document.getElementById('f-name').value,
    type: type,
    triggers: _triggersValue(),
    action_mode: actionMode,
    rules: rules,
    system_prompt: document.getElementById('f-prompt').value,
    strategic_context: document.getElementById('f-strategic').value,
    allowed_tools: getSelectedTools(),
    allowed_entities: (function() { try { return JSON.parse(document.getElementById('f-entities').value || '[]'); } catch(e) { return []; } })(),
    allowed_services: getSelectedActions(),
    model: document.getElementById('f-model').value,
    max_tokens: parseInt(document.getElementById('f-max-tokens').value) || 4096,
    restrict_to_home: document.getElementById('f-restrict').checked,
    require_confirmation: document.getElementById('f-require-confirmation').checked,
    enabled: document.getElementById('f-enabled').checked,
    states: _defaultStates(),
    budget_eur_limit: parseFloat(document.getElementById('u-ag-budget').value) || 0,
    max_chat_turns: parseInt(document.getElementById('f-max-chat-turns').value) || 0,
    response_mode: document.getElementById('f-response-mode').value,
    thinking_budget: parseInt(document.getElementById('f-thinking-budget').value) || 0,
  };
  /* Only include the bypass flag when the user has explicitly checked it
     AND the row is visible (autonomous agent on a :free model). The server
     ignores it for other combinations, but keeping the payload clean makes
     intent obvious in the request log. */
  var confirmRow = document.getElementById('confirm-free-row');
  if (confirmRow && confirmRow.style.display !== 'none' &&
      document.getElementById('f-confirm-free').checked) {
    payload.confirm_free_for_agent = true;
  }
  return payload;
}

/* v0.10.2: save-btn/delete-btn/run-btn id legacy. In v6 i pulsanti reali sono
   #btn-save/#btn-delete/#btn-test-run e i loro handler sono installati da
   agent-editor.js setupStickyActions() che chiama window.saveAgent/deleteAgent/
   runAgent (definiti in agent-editor.js, riusano buildPayload da qui).
   I binding sotto sono inerti ma protetti da null guard per safety. */
var _sb = document.getElementById('save-btn');
if (_sb) _sb.addEventListener('click', async function() {
  var payload = buildPayload();
  var method = currentId ? 'PUT' : 'POST';
  var url = currentId ? ('api/agents/' + currentId) : 'api/agents';
  try {
    var r = await fetch(url, {method: method, headers: {'Content-Type':'application/json', 'X-Requested-With': 'fetch'}, body: JSON.stringify(payload)});
    if (!r.ok) {
      var msg = 'Errore salvataggio agente (HTTP ' + r.status + ')';
      try { var d = await r.json(); if (d.error) msg = d.error; } catch (e) {}
      alert(msg);
      return;
    }
    var a = await r.json();
    await loadAgents();
    openAgent(a);
  } catch (e) {
    alert('Errore di rete durante il salvataggio: ' + (e && e.message ? e.message : e));
  }
});

var _delb = document.getElementById('delete-btn');
if (_delb) _delb.addEventListener('click', async function() {
  if (!currentId || !confirm('Eliminare questo agente?')) return;
  try {
    var r = await fetch('api/agents/' + currentId, {method: 'DELETE', headers: {'X-Requested-With': 'fetch'}});
    if (!r.ok && r.status !== 204) {
      var msg = 'Errore eliminazione agente (HTTP ' + r.status + ')';
      try { var d = await r.json(); if (d.error) msg = d.error; } catch (e) {}
      alert(msg);
      return;
    }
    currentId = null;
    var _f3 = document.getElementById('form'); if (_f3) _f3.style.display = 'none';
    var _ns3 = document.getElementById('no-selection'); if (_ns3) _ns3.style.display = '';
    await loadAgents();
  } catch (e) {
    alert('Errore di rete durante l eliminazione: ' + (e && e.message ? e.message : e));
  }
});

function highlightOutput(text) {
  return text
    .replace(/("error")/g, '<span style="color:#ff7b72">$1</span>')
    .replace(/("[\w_]+")\s*:/g, '<span style="color:#79c0ff">$1</span>:')
    .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span style="color:#a5d6a7">$1</span>');
}

var _rb = document.getElementById('run-btn');
if (_rb) _rb.addEventListener('click', async function() {
  if (!currentId) return;
  var btn = document.getElementById('run-btn');
  var out = document.getElementById('run-output');
  if (!btn || !out) return;

  btn.classList.add('running');
  btn.disabled = true;
  out.style.display = '';
  out.className = '';
  out.textContent = 'Avvio esecuzione…';

  var timeout = 90000;
  var ctrl = new AbortController();
  var timer = setTimeout(function() { ctrl.abort(); }, timeout);

  try {
    var r = await fetch('api/agents/' + currentId + '/run', {
      method: 'POST',
      headers: {'X-Requested-With': 'fetch'},
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    var data = await r.json();
    var raw = (data.result || data.error || '').trim();
    if (!raw) {
      out.className = 'run-empty';
      out.textContent = '(nessun risultato restituito dall\'agente)';
    } else {
      out.className = '';
      out.innerHTML = highlightOutput(esc(raw));
    }
  } catch(e) {
    clearTimeout(timer);
    out.className = 'run-error-text';
    if (e.name === 'AbortError') {
      out.textContent = '⏱ Timeout: l\'agente non ha risposto entro 90 secondi.';
    } else {
      out.textContent = 'Errore: ' + e.message;
    }
  } finally {
    btn.classList.remove('running');
    btn.disabled = false;
    out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
});
