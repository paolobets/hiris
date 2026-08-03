/* HIRIS · Chat page · Chatbot list, switching, turn limit (SP-4 Fase B Task 8) */
(function() {
  var state = window.HirisChatState;

  function updateTurnCounter() {
    var counter = document.getElementById('turn-counter');
    var max = state.agentMaxTurns[state.activeAgentId] || 0;
    if (!state.activeAgentId || max === 0) { counter.style.display = 'none'; return; }
    var current = state.agentTurnCounts[state.activeAgentId] || 0;
    counter.style.display = '';
    counter.textContent = current + ' / ' + max + ' messaggi';
    counter.style.color = current >= max ? 'var(--err)' : 'var(--text-3)';
  }

  function checkTurnLimit() {
    var max = state.agentMaxTurns[state.activeAgentId] || 0;
    var sessionMsg = document.getElementById('session-ended-msg');
    if (max === 0) {
      state.els.input.disabled = false;
      state.els.sendBtn.disabled = false;
      if (sessionMsg) sessionMsg.style.display = 'none';
      return;
    }
    var current = state.agentTurnCounts[state.activeAgentId] || 0;
    var reached = current >= max;
    state.els.input.disabled = reached;
    state.els.sendBtn.disabled = reached;
    if (sessionMsg) sessionMsg.style.display = reached ? '' : 'none';
  }

  async function clearConversation() {
    if (!state.activeAgentId) return;
    /* Irreversibile: la card Lovelace (hiris-chat-card.js) chiede conferma
       per la stessa identica azione con lo stesso testo -- qui mancava. */
    if (!window.confirm('Cancellare la cronologia di questa conversazione?')) return;
    try {
      var r = await fetch('api/chatbots/' + state.activeAgentId + '/chat-history', { method: 'DELETE', headers: { 'X-Requested-With': 'fetch' } });
      if (!r.ok) {
        /* Se il server non ha cancellato, la UI non deve fingere che l'abbia
           fatto: altrove in questo file un catch vuoto ha nascosto per mesi
           un guasto identico (vedi A9/api.js). */
        console.error('clearConversation failed', r.status);
        window.alert('Non è stato possibile cancellare la cronologia. Riprova più tardi.');
        return;
      }
    } catch (e) {
      console.error('clearConversation failed', e);
      window.alert('Non è stato possibile cancellare la cronologia. Riprova più tardi.');
      return;
    }
    state.els.messages.innerHTML = '';
    state.els.messages.appendChild(state.els.welcome);
    state.els.welcome.style.display = '';
    state.hasMessages = false;
    state.agentTurnCounts[state.activeAgentId] = 0;
    updateTurnCounter();
    checkTurnLimit();
  }

  function updateAgentPill(agentName) {
    var pill = document.getElementById('agent-pill');
    if (!pill) return;
    var avatar = document.getElementById('ap-avatar');
    var name = document.getElementById('ap-name');
    var letter = (agentName || 'I').trim().charAt(0).toUpperCase();
    if (avatar) avatar.textContent = letter;
    if (name) name.textContent = agentName || 'Iris';
  }

  function updateGreeting() {
    var hello = document.getElementById('welcome-hello');
    if (!hello) return;
    var h = new Date().getHours();
    var word = (h < 5 || h >= 22) ? 'Buonanotte'
             : (h < 12) ? 'Buongiorno'
             : (h < 18) ? 'Buon pomeriggio'
             : 'Buonasera';
    hello.textContent = word;
  }

  async function load() {
    try {
      var r = await fetch('api/chatbots');
      if (!r.ok) throw new Error();
      var agents = await r.json();
      state.els.connDot.classList.remove('offline');
      state.els.connDot.textContent = 'connesso';
      state.els.agentList.innerHTML = '';
      agents.forEach(function(a) {
        state.agentMaxTurns[a.id] = a.max_chat_turns || 0;
        var div = document.createElement('div');
        div.className = 'agent-item' + (a.id === state.activeAgentId ? ' agent-active' : '');
        div.innerHTML =
          '<div class="dot ' + (a.enabled ? 'on' : 'off') + '"></div>' +
          '<span>' + esc(a.name) + '</span>' +
          (a.is_default ? '<span class="meta">default</span>' : '');
        div.addEventListener('click', function() { setActive(a.id, a.name); });
        state.els.agentList.appendChild(div);
      });
      /* keep pill in sync with active agent */
      var current = agents.find(function(a) { return a.id === state.activeAgentId; }) || agents[0];
      if (current) updateAgentPill(current.name);
    } catch (e) {
      state.els.connDot.classList.add('offline');
      state.els.connDot.textContent = 'offline';
    }
  }

  /* Carica e mostra la history salvata di `agentId`. Il guard sul confronto con
     l'agente attivo evita che una risposta stale (l'utente cambia agente prima
     che la fetch torni) riscriva la chat del nuovo agente. Estratta da setActive
     per essere riusata al boot (restore). */
  async function applyHistory(agentId) {
    var localId = agentId;
    try {
      var r = await fetch('api/chatbots/' + agentId + '/chat-history');
      if (localId !== state.activeAgentId) return;
      if (!r.ok) {
        /* Fratello dello stesso difetto: prima ne' il ramo r.ok=false ne' il
           catch sotto lasciavano traccia -- la cronologia restava vuota senza
           che nulla lo dicesse nemmeno in console. */
        console.error('applyHistory failed', r.status);
        return;
      }
      var data = await r.json();
      if (localId !== state.activeAgentId) return;
      var msgs = data.messages || [];
      msgs.forEach(function(m) {
        window.HirisChatMessages.appendMsg(m.role === 'user' ? 'user' : 'assistant', m.content);
      });
      state.agentTurnCounts[agentId] = msgs.filter(function(m) { return m.role === 'user'; }).length;
      updateTurnCounter();
      checkTurnLimit();
    } catch (e) {
      console.error('applyHistory failed', e);
    }
  }

  async function setActive(agentId, agentName) {
    if (agentId === state.activeAgentId) return;
    state.activeAgentId = agentId;
    /* Ricorda l'agente attivo: la pagina chat e' separata da config, quindi
       tornarci = reload pieno; senza questo activeAgentId ripartiva sempre da
       'hiris-default' e si perdeva la conversazione dell'agente in uso. */
    try { window.localStorage.setItem('hiris_active_agent', agentId); } catch (e) {}
    state.els.messages.innerHTML = '';
    state.els.messages.appendChild(state.els.welcome);
    state.els.welcome.style.display = '';
    state.hasMessages = false;
    var titleEl = document.getElementById('header-title');
    if (titleEl && titleEl.firstChild) titleEl.firstChild.nodeValue = agentName + ' ';
    updateAgentPill(agentName);
    state.agentTurnCounts[agentId] = 0;
    updateTurnCounter();
    checkTurnLimit();
    await applyHistory(agentId);
    load();
  }

  /* Boot: setActive carica la history SOLO al cambio agente (guard su id), quindi
     al primo mount la conversazione dell'agente attivo non veniva mai ricaricata
     -> tornando alla chat da config si vedeva una chat vuota pur essendo salvata
     lato server (per chatbot_id). restore() ricarica la history dell'agente
     attivo (ripristinato da localStorage in state.js), senza il guard di cambio. */
  async function restore() {
    await applyHistory(state.activeAgentId);
  }

  window.HirisChatAgents = {
    updateTurnCounter: updateTurnCounter,
    checkTurnLimit: checkTurnLimit,
    clearConversation: clearConversation,
    updateAgentPill: updateAgentPill,
    updateGreeting: updateGreeting,
    load: load,
    setActive: setActive,
    restore: restore,
  };
})();
