/* HIRIS · Designer · agent form (CRUD + run)
   v0.10.5 cleanup: rimossi renderList (target #agent-list shim invisibile in v6 —
   la lista è gestita da chatbots-list.js), querySelector #agent-tabs/.tab-btn
   (markup tab orizzontale rimosso in v6), e gli IIFE handler di
   #new-btn/#save-btn/#delete-btn/#run-btn (shimmati a div invisibili,
   sostituiti da window.saveAgent/runAgent/deleteAgent in chatbot-editor.js
   + initNewAgent path). Restano: openAgent, buildPayload
   (essenziali per il form long-form v6).
   Task 4 (Slice 5): rimossi showAgentMode/showActionMode/_defaultStates/
   _buildTriggerOnChecks/_triggerOnValue/updateConfirmFreeVisibility — erano
   tutti legati al selettore Tipo (agent/chat), alla sezione Trigger e al tab
   Azioni, ritirati insieme alla macchina action/rules/states (Task 1-3). Il
   Designer ora edita solo Persona: prompt, tool scope, memory scope, chat
   policy, override modello.
   Calls into config/editor-kit.js (HirisEditorKit.setModelValue,
   window.HirisAgentToolChecks/HirisAgentActionChecks -- SP-4 Fase B Task 3,
   sostituiscono api.js._setModelValue e permessi.js buildToolChecks/
   buildActionChecks/getSelectedTools/getSelectedActions), logs.js, usage.js. */

var chatbots = [];
var currentId = null;

async function loadChatbots() {
  try {
    var r = await fetch('api/chatbots');
    chatbots = await r.json();
    /* v0.10.5: niente renderList — la lista agenti è renderizzata da
       chatbots-list.js sulla route #/chatbots. agents global resta popolata
       per le chiamate downstream (openAgent, ecc.). */
  } catch(e) {}
}

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
  document.getElementById('f-prompt').value = a.system_prompt || '';
  document.getElementById('f-strategic').value = a.strategic_context || '';
  if (window.HirisAgentEntityPicker) window.HirisAgentEntityPicker.setValue(a.allowed_entities || []);
  document.getElementById('f-enabled').checked = a.enabled;
  HirisEditorKit.setModelValue(document.getElementById('f-model'), a.model || 'auto');
  document.getElementById('f-max-tokens').value = a.max_tokens || 4096;
  document.getElementById('f-restrict').checked = !!a.restrict_to_home;
  document.getElementById('f-require-confirmation').checked = !!a.require_confirmation;
  document.getElementById('f-max-chat-turns').value = a.max_chat_turns || 0;
  document.getElementById('f-response-mode').value = a.response_mode || 'auto';
  document.getElementById('f-thinking-budget').value = String(a.thinking_budget || 0);
  if (window.HirisAgentActionChecks) window.HirisAgentActionChecks.setSelected(a.allowed_services || []);
  var _db = document.getElementById('delete-btn');
  if (_db) _db.style.display = a.is_default ? 'none' : '';
  var ro = document.getElementById('run-output');
  if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }
  /* setSelected sul gruppo tool deve girare dopo quello azioni: la sua
     wrapper (chatbot-editor.js populatePermessi) sincronizza la visibilità
     della sezione Azioni in base a call_ha_service — stesso ordine di
     dipendenza del vecchio buildToolChecks/buildActionChecks. */
  if (window.HirisAgentToolChecks) window.HirisAgentToolChecks.setSelected(a.allowed_tools || []);
  /* v0.10.5: niente renderList (rimosso in cleanup, lista agenti gestita
     da chatbots-list.js sulla route #/chatbots) */
  renderExecutionLog(a);
  loadAgentUsage(a.id);
  updateAgentUsageToggleBtn(a);
  updateTokenCounter();
  loadContextPreview(a.id);
}

/* v0.10.5 cleanup: rimosso handler #new-btn (era IIFE su shim div invisibile).
   Il path "Nuovo agente" v6 è gestito da HirisChatbotEditor.initNewAgent() in
   chatbot-editor.js (chiamato dal route #/chatbots/new). */

function buildPayload() {
  return {
    name: document.getElementById('f-name').value,
    system_prompt: document.getElementById('f-prompt').value,
    strategic_context: document.getElementById('f-strategic').value,
    allowed_tools: window.HirisAgentToolChecks ? window.HirisAgentToolChecks.getSelected() : [],
    allowed_entities: window.HirisAgentEntityPicker ? window.HirisAgentEntityPicker.getValue() : [],
    allowed_services: window.HirisAgentActionChecks ? window.HirisAgentActionChecks.getSelected() : [],
    model: document.getElementById('f-model').value,
    max_tokens: parseInt(document.getElementById('f-max-tokens').value) || 4096,
    restrict_to_home: document.getElementById('f-restrict').checked,
    require_confirmation: document.getElementById('f-require-confirmation').checked,
    enabled: document.getElementById('f-enabled').checked,
    max_chat_turns: parseInt(document.getElementById('f-max-chat-turns').value) || 0,
    response_mode: document.getElementById('f-response-mode').value,
    thinking_budget: parseInt(document.getElementById('f-thinking-budget').value) || 0,
  };
}

/* v0.10.5 cleanup: rimossi handler IIFE per #save-btn, #delete-btn, #run-btn.
   Erano inerti su shim div invisibili. La logica equivalente è in
   window.saveAgent / window.deleteAgent / window.runAgent definite in
   chatbot-editor.js (chiamate da setupStickyActions sui veri pulsanti
   #btn-save / #btn-delete / #btn-test-run del template v6). */

function highlightOutput(text) {
  return text
    .replace(/("error")/g, '<span style="color:#ff7b72">$1</span>')
    .replace(/("[\w_]+")\s*:/g, '<span style="color:#79c0ff">$1</span>:')
    .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span style="color:#a5d6a7">$1</span>');
}
