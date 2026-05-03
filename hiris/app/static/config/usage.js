/* HIRIS · Designer · per-agent usage panel
   Reads/displays per-agent usage; lets user reset, set budget, block/unblock. */

async function loadAgentUsage(agentId) {
  if (!agentId) return;
  try {
    var r = await fetch('api/agents/' + agentId + '/usage');
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
    btn.textContent = '⊘ Blocca agente';
    btn.className = 'btn-usage-block';
  } else {
    btn.textContent = '✓ Riabilita agente';
    btn.className = 'btn-usage-enable';
  }
}

document.getElementById('u-ag-reset-btn').onclick = async function() {
  if (!currentId || !confirm('Azzerare i contatori di consumo per questo agente?')) return;
  try {
    await fetch('api/agents/' + currentId + '/usage/reset', { method: 'POST' });
    await loadAgentUsage(currentId);
  } catch(e) {}
};

document.getElementById('u-ag-toggle-btn').onclick = async function() {
  if (!currentId) return;
  var agent = agents.find(function(a) { return a.id === currentId; });
  if (!agent) return;
  var newEnabled = !agent.enabled;
  var confirmMsg = newEnabled
    ? 'Riabilitare questo agente?'
    : 'Bloccare questo agente? Non verrà più eseguito automaticamente.';
  if (!confirm(confirmMsg)) return;
  try {
    var r = await fetch('api/agents/' + currentId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newEnabled }),
    });
    await r.json();
    await loadAgents();
    var fresh = agents.find(function(a) { return a.id === currentId; });
    if (fresh) openAgent(fresh);
  } catch(e) {}
};

document.getElementById('u-ag-budget-save-btn').onclick = async function() {
  if (!currentId) return;
  var budget = parseFloat(document.getElementById('u-ag-budget').value) || 0;
  try {
    await fetch('api/agents/' + currentId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget_eur_limit: budget }),
    });
    alert(budget > 0 ? 'Soglia di budget salvata: €' + budget.toFixed(2) : 'Nessun limite di budget impostato.');
  } catch(e) {}
};

document.getElementById('usage-reset-btn').onclick = async function() {
  if (!confirm('Azzerare i contatori di utilizzo API?')) return;
  try {
    var r = await fetch('api/usage/reset', {method: 'POST'});
    if (r.ok) await loadUsage();
  } catch(e) {}
};
