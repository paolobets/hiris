/* HIRIS · Chat page · first-run onboarding (SP-4 Fase B Task 8)
   Rebuilt to 2 steps (Benvenuto -> Nome+Istruzioni), dropping the old
   step "che tipo di assistente?" (Monitor/Chat/Reattivo): since the SP-4
   Fase B rename, `POST api/chatbots` has no `type` or `triggers` field at
   all (Chatbot and Agentbot are separate entities -- see
   handlers_chatbots.py::_validate_chatbot_payload and
   config/create-wizard.js). The old picker sent those fields regardless of
   which of the 3 options was chosen, so every choice silently created the
   same plain Chatbot -- dead UI offering a distinction the backend no
   longer has a vocabulary for. This page only ever creates a Chatbot (no
   trigger/action fields here); creating an Agentbot goes through the full
   goal-first wizard at "Configurazione" (config/create-wizard.js). */
(function() {
  async function check() {
    if (localStorage.getItem('hiris_onboarding_v1')) return;
    try {
      var r = await fetch('api/chatbots');
      if (!r.ok) return;
      var agents = await r.json();
      var nonDefault = agents.filter(function(a) { return !a.is_default; });
      if (nonDefault.length > 0) { localStorage.setItem('hiris_onboarding_v1', '1'); return; }
    } catch (e) { return; }
    document.getElementById('onboarding').style.display = 'flex';
  }

  function dismiss() {
    localStorage.setItem('hiris_onboarding_v1', '1');
    document.getElementById('onboarding').style.display = 'none';
  }

  function go(step) {
    for (var i = 0; i < 2; i++) {
      document.getElementById('ob-step-' + i).classList.toggle('active', i === step);
      document.getElementById('ob-dot-' + i).classList.toggle('active', i === step);
    }
  }

  async function create() {
    var name = (document.getElementById('ob-name').value || '').trim();
    if (!name) { document.getElementById('ob-name').focus(); return; }
    var prompt = (document.getElementById('ob-prompt').value || '').trim();
    var payload = { name: name };
    if (prompt) payload.system_prompt = prompt;
    var btn = document.getElementById('ob-create-btn');
    btn.disabled = true;
    try {
      var r = await fetch('api/chatbots', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' }, body: JSON.stringify(payload) });
      if (!r.ok) { btn.disabled = false; alert('Errore nella creazione assistente. Riprova.'); return; }
      var agent = await r.json();
      await window.HirisChatAgents.load();
      if (agent.id) window.HirisChatAgents.setActive(agent.id, agent.name || agent.id);
      dismiss();
    } catch (e) { btn.disabled = false; alert('Errore di rete. Riprova.'); }
  }

  function wire() {
    var skipBtn = document.getElementById('ob-btn-skip-0');
    if (skipBtn) skipBtn.addEventListener('click', dismiss);
    var startBtn = document.getElementById('ob-btn-start');
    if (startBtn) startBtn.addEventListener('click', function() { go(1); });
    var backBtn = document.getElementById('ob-btn-back-1');
    if (backBtn) backBtn.addEventListener('click', function() { go(0); });
    var createBtn = document.getElementById('ob-create-btn');
    if (createBtn) createBtn.addEventListener('click', create);
  }

  function init() {
    wire();
    check();
  }

  window.HirisChatOnboarding = { init: init, dismiss: dismiss, go: go, create: create, check: check };
})();
