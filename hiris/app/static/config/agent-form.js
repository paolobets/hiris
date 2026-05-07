/* HIRIS · Designer · agent form (CRUD + run)
   v0.10.5 cleanup: rimossi renderList (target #agent-list shim invisibile in v6 —
   la lista è gestita da agents-list.js), querySelector #agent-tabs/.tab-btn
   (markup tab orizzontale rimosso in v6), e gli IIFE handler di
   #new-btn/#save-btn/#delete-btn/#run-btn (shimmati a div invisibili,
   sostituiti da window.saveAgent/runAgent/deleteAgent in agent-editor.js
   + initNewAgent path). Restano: openAgent, buildPayload, showAgentMode
   (essenziali per il form long-form v6).
   Calls into permessi.js, triggers.js, action-editor.js, logs.js, usage.js. */

var agents = [];
var currentId = null;

async function loadAgents() {
  try {
    var r = await fetch('api/agents');
    agents = await r.json();
    /* v0.10.5: niente renderList — la lista agenti è renderizzata da
       agents-list.js sulla route #/agents. agents global resta popolata
       per le chiamate downstream (openAgent, ecc.). */
  } catch(e) {}
}

function showAgentMode(type) {
  var isAgent = type === 'agent';
  var triggersSec = document.getElementById('agent-triggers-section');
  if (triggersSec) triggersSec.style.display = isAgent ? '' : 'none';
  var maxTurnsRow = document.getElementById('max-turns-row');
  if (maxTurnsRow) maxTurnsRow.style.display = type === 'chat' ? '' : 'none';
  /* Sezione Azioni: nascosta per chat agents. Target la section-card v6. */
  var azioniSection = document.getElementById('sec-azioni');
  if (azioniSection) azioniSection.style.display = isAgent ? '' : 'none';
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

/* v0.10.5 cleanup: rimosso handler #new-btn (era IIFE su shim div invisibile).
   Il path "Nuovo agente" v6 è gestito da HirisAgentEditor.initNewAgent() in
   agent-editor.js (chiamato dal route #/agents/new). */

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

/* v0.10.5 cleanup: rimossi handler IIFE per #save-btn, #delete-btn, #run-btn.
   Erano inerti su shim div invisibili. La logica equivalente è in
   window.saveAgent / window.deleteAgent / window.runAgent definite in
   agent-editor.js (chiamate da setupStickyActions sui veri pulsanti
   #btn-save / #btn-delete / #btn-test-run del template v6). */

function highlightOutput(text) {
  return text
    .replace(/("error")/g, '<span style="color:#ff7b72">$1</span>')
    .replace(/("[\w_]+")\s*:/g, '<span style="color:#79c0ff">$1</span>:')
    .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span style="color:#a5d6a7">$1</span>');
}
