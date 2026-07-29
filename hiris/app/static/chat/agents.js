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
    try {
      await fetch('api/chatbots/' + state.activeAgentId + '/chat-history', { method: 'DELETE', headers: { 'X-Requested-With': 'fetch' } });
    } catch (e) {}
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

  async function setActive(agentId, agentName) {
    if (agentId === state.activeAgentId) return;
    state.activeAgentId = agentId;
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
    // Capture local id: if the user clicks another agent before history loads,
    // a stale response would otherwise rewrite the new agent's empty chat.
    var localId = agentId;
    try {
      var r = await fetch('api/chatbots/' + agentId + '/chat-history');
      if (localId !== state.activeAgentId) return;
      if (r.ok) {
        var data = await r.json();
        if (localId !== state.activeAgentId) return;
        var msgs = data.messages || [];
        msgs.forEach(function(m) {
          window.HirisChatMessages.appendMsg(m.role === 'user' ? 'user' : 'assistant', m.content);
        });
        state.agentTurnCounts[agentId] = msgs.filter(function(m) { return m.role === 'user'; }).length;
        updateTurnCounter();
        checkTurnLimit();
      }
    } catch (e) {}
    load();
  }

  window.HirisChatAgents = {
    updateTurnCounter: updateTurnCounter,
    checkTurnLimit: checkTurnLimit,
    clearConversation: clearConversation,
    updateAgentPill: updateAgentPill,
    updateGreeting: updateGreeting,
    load: load,
    setActive: setActive,
  };
})();
