/* HIRIS · Designer · proposals workflow
   Pending / archived proposals from agents. Apply / Reject. */

var _currentProposalTab = 'pending';

async function loadProposals(status) {
  var list = document.getElementById('proposals-list');
  list.innerHTML = '<div class="proposals-empty">Caricamento…</div>';
  try {
    var url = 'api/proposals' + (status ? '?status=' + status : '');
    var r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var data = await r.json();
    renderProposals(data.proposals || [], status);
  } catch(e) {
    list.innerHTML = '<div class="proposals-error">Errore caricamento proposte.</div>';
  }
}

function renderProposals(proposals, status) {
  var list = document.getElementById('proposals-list');
  if (!proposals.length) {
    list.innerHTML = '<div class="proposals-empty">Nessuna proposta ' + (status === 'pending' ? 'in attesa' : 'archiviata') + '.</div>';
    return;
  }
  list.innerHTML = proposals.map(function(p) {
    var typeLabel = p.type === 'ha_automation' ? 'HA Nativa' : 'Agente HIRIS';
    var date = p.created_at ? p.created_at.substring(0, 10) : '';
    var safeId = escHtml(p.id);
    var actions = status === 'pending'
      ? '<button class="btn-apply" data-pid="' + safeId + '">Attiva</button>'
      + '<button class="btn-reject" data-pid="' + safeId + '">Rifiuta</button>'
      : '';
    return '<div class="proposal-row" id="pr-' + safeId + '">'
      + '<div class="proposal-info">'
      + '<div class="proposal-name"><span class="type-badge">' + typeLabel + '</span>' + escHtml(p.name) + '</div>'
      + '<div class="proposal-meta">' + date + '</div>'
      + '<div class="proposal-desc">' + escHtml(p.description || '') + '</div>'
      + '<div class="proposal-reason"><strong>Motivo:</strong> ' + escHtml(p.routing_reason || '') + '</div>'
      + '</div>'
      + (actions ? '<div class="proposal-actions">' + actions + '</div>' : '')
      + '</div>';
  }).join('');
  list.querySelectorAll('.btn-apply').forEach(function(btn) {
    btn.addEventListener('click', function() { applyProposal(this.dataset.pid); });
  });
  list.querySelectorAll('.btn-reject').forEach(function(btn) {
    btn.addEventListener('click', function() { rejectProposal(this.dataset.pid); });
  });
}

async function applyProposal(id) {
  if (!confirm('Attivare questa proposta?')) return;
  var row = document.getElementById('pr-' + id);
  try {
    var r = await fetch('api/proposals/' + id + '/apply', {method: 'POST', headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!r.ok) { var d = await r.json(); alert(d.error || 'Errore'); return; }
    if (row) {
      row.style.opacity = '0.5';
      row.querySelector('.proposal-name').innerHTML = '<span style="color:var(--success)">✓ Proposta attivata</span>';
      row.querySelector('.proposal-actions').remove();
      setTimeout(function() { row.remove(); checkEmptyList(); }, 1200);
    } else {
      checkEmptyList();
    }
  } catch(e) { alert('Errore di rete'); }
}

async function rejectProposal(id) {
  if (!confirm('Rifiutare questa proposta?')) return;
  var row = document.getElementById('pr-' + id);
  try {
    var r = await fetch('api/proposals/' + id + '/reject', {method: 'POST', headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!r.ok) { var d = await r.json(); alert(d.error || 'Errore'); return; }
    if (row) {
      row.style.opacity = '0.5';
      row.querySelector('.proposal-name').innerHTML = '<span style="color:var(--text-muted)">Proposta rifiutata</span>';
      row.querySelector('.proposal-actions').remove();
      setTimeout(function() { row.remove(); checkEmptyList(); }, 1200);
    } else {
      checkEmptyList();
    }
  } catch(e) { alert('Errore di rete'); }
}

function checkEmptyList() {
  var list = document.getElementById('proposals-list');
  if (!list.querySelector('.proposal-row')) {
    var label = _currentProposalTab === 'archived' ? 'archiviata' : 'in attesa';
    list.innerHTML = '<div class="proposals-empty">Nessuna proposta ' + label + '.</div>';
  }
}

function switchProposalsTab(status) {
  _currentProposalTab = status;
  document.getElementById('tab-pending').className = 'proposals-tab' + (status === 'pending' ? ' active' : '');
  document.getElementById('tab-archived').className = 'proposals-tab' + (status === 'archived' ? ' active' : '');
  loadProposals(status);
}
