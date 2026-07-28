/* HIRIS · Designer · per-agent usage panel
   Reads/displays per-agent usage; lets user reset counters, block/unblock.
   Task 4 (Slice 5): rimosso il set-budget control (vedi nota più sotto).

   SP-4 Fase B Task 2: #u-ag-reset-btn/#u-ag-toggle-btn vivono dentro
   #route-outlet, ricreati a ogni mount dell'editor Chatbot (populateConsumi
   in chatbot-editor.js). Con lo script ora caricato in modo statico (non più
   iniettato dopo il mount), un binding IIFE-time via getElementById(...)
   .onclick lancerebbe un TypeError al primo load (i bottoni non esistono
   ancora) e comunque smetterebbe di funzionare dopo un remount (nodo
   sostituito). Delegation su #route-outlet (contenitore stabile, mai
   ricreato — solo il suo innerHTML cambia) risolve entrambi i problemi in
   un colpo solo: nessun rebind manuale necessario.

   Vincitori (grounding SP-4 Fase B, A1):
   - reset consumi (#u-ag-reset-btn): versione editor — usa
     HirisState.get('activeChatbotId'), non il global currentId.
   - toggle abilitato (#u-ag-toggle-btn): versione usage.js — ha il
     confirm() e ricarica la lista + riapre l'agente (l'editor non lo
     faceva: miglioramento reale, non solo parità). */

async function loadAgentUsage(agentId) {
  if (!agentId) return;
  try {
    var r = await fetch('api/chatbots/' + agentId + '/usage');
    if (!r.ok) return;
    var d = await r.json();
    document.getElementById('u-ag-requests').textContent = d.requests != null ? d.requests : '—';
    document.getElementById('u-ag-input').textContent = fmtNum(d.input_tokens);
    document.getElementById('u-ag-output').textContent = fmtNum(d.output_tokens);
    document.getElementById('u-ag-cost').textContent = d.cost_eur != null ? '€' + d.cost_eur.toFixed(4) : '—';
    var lr = d.last_run ? new Date(d.last_run).toLocaleString('it-IT') : 'mai';
    document.getElementById('u-ag-last-run').textContent = lr;
  } catch(e) {}
}

function updateAgentUsageToggleBtn(agent) {
  var btn = document.getElementById('u-ag-toggle-btn');
  if (!agent || !btn) return;
  if (agent.enabled) {
    btn.textContent = '⊘ Blocca Chatbot';
    btn.className = 'btn-usage-block';
  } else {
    btn.textContent = '✓ Riabilita Chatbot';
    btn.className = 'btn-usage-enable';
  }
}

async function _resetAgentUsage() {
  var aid = window.HirisState && HirisState.get('activeChatbotId');
  if (!aid || !confirm('Azzerare i contatori di consumo per questo Chatbot?')) return;
  try {
    await fetch('api/chatbots/' + encodeURIComponent(aid) + '/usage/reset', { method: 'POST', headers: {'X-Requested-With': 'fetch'} });
    await loadAgentUsage(aid);
  } catch(e) {}
}

async function _toggleAgentUsage() {
  if (!currentId) return;
  var agent = chatbots.find(function(a) { return a.id === currentId; });
  if (!agent) return;
  var newEnabled = !agent.enabled;
  var confirmMsg = newEnabled
    ? 'Riabilitare questo Chatbot?'
    : 'Bloccare questo Chatbot? Non verrà più eseguito automaticamente.';
  if (!confirm(confirmMsg)) return;
  try {
    var r = await fetch('api/chatbots/' + encodeURIComponent(currentId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ enabled: newEnabled }),
    });
    await r.json();
    await loadChatbots();
    var fresh = chatbots.find(function(a) { return a.id === currentId; });
    if (fresh && typeof openAgent === 'function') openAgent(fresh);
  } catch(e) {}
}

(function() {
  var outlet = document.getElementById('route-outlet');
  var target = outlet || document;
  target.addEventListener('click', function(e) {
    if (e.target.closest('#u-ag-reset-btn')) { _resetAgentUsage(); return; }
    if (e.target.closest('#u-ag-toggle-btn')) { _toggleAgentUsage(); return; }
  });
})();
