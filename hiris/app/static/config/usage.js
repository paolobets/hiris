/* HIRIS · Designer · per-agent usage panel
   Reads/displays per-agent usage; lets user reset counters, block/unblock.
   Task 4 (Slice 5): rimosso il set-budget control (vedi nota più sotto). */

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
  if (!agent) return;
  if (agent.enabled) {
    btn.textContent = '⊘ Blocca Chatbot';
    btn.className = 'btn-usage-block';
  } else {
    btn.textContent = '✓ Riabilita Chatbot';
    btn.className = 'btn-usage-enable';
  }
}

document.getElementById('u-ag-reset-btn').onclick = async function() {
  if (!currentId || !confirm('Azzerare i contatori di consumo per questo Chatbot?')) return;
  try {
    await fetch('api/chatbots/' + currentId + '/usage/reset', { method: 'POST', headers: {'X-Requested-With': 'fetch'} });
    await loadAgentUsage(currentId);
  } catch(e) {}
};

document.getElementById('u-ag-toggle-btn').onclick = async function() {
  if (!currentId) return;
  var agent = chatbots.find(function(a) { return a.id === currentId; });
  if (!agent) return;
  var newEnabled = !agent.enabled;
  var confirmMsg = newEnabled
    ? 'Riabilitare questo Chatbot?'
    : 'Bloccare questo Chatbot? Non verrà più eseguito automaticamente.';
  if (!confirm(confirmMsg)) return;
  try {
    var r = await fetch('api/chatbots/' + currentId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ enabled: newEnabled }),
    });
    await r.json();
    await loadChatbots();
    var fresh = chatbots.find(function(a) { return a.id === currentId; });
    if (fresh) openAgent(fresh);
  } catch(e) {}
};

/* Task 4 (Slice 5) review fix: rimosso il binding di u-ag-budget-save-btn
   (PUT budget_eur_limit) — il campo e il pulsante non esistono più nel
   markup (rimossi da populateConsumi in chatbot-editor.js) e il backend
   scarta comunque quella chiave. Lasciarlo qui avrebbe fatto sì che
   getElementById('u-ag-budget-save-btn') restituisse null e il successivo
   .onclick lanciasse un TypeError non gestito al primo mount dell'editor. */

document.getElementById('usage-reset-btn').onclick = async function() {
  if (!confirm('Azzerare i contatori di utilizzo API?')) return;
  try {
    var r = await fetch('api/usage/reset', {method: 'POST', headers: {'X-Requested-With': 'fetch'}});
    if (r.ok) await loadUsage();
  } catch(e) {}
};
