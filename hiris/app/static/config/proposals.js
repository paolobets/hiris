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
    var TYPE_LABELS = {
      ha_automation: '→ automazione HA', hiris_agent: '→ Agentbot',
      ha_dashboard: '→ dashboard', ha_script: '→ script', ha_scene: '→ scena'
    };
    var typeLabel = TYPE_LABELS[p.type] || ('→ ' + (p.type || 'config'));
    var configPreview = '';
    if (p.type === 'ha_dashboard' || p.type === 'ha_script' || p.type === 'ha_scene') {
      try {
        configPreview = '<pre class="proposal-config" style="max-height:180px;overflow:auto;'
          + 'background:var(--surface-sunken,#00000010);padding:8px;border-radius:6px;'
          + 'font-family:var(--font-mono);font-size:11px;margin-top:6px">'
          + escHtml(JSON.stringify((p.config && p.config.ha_config) || p.config, null, 2))
          + '</pre>';
      } catch(e) { configPreview = ''; }
    }
    /* Una proposta di plancia con mode=replace non aggiunge: sovrascrive.
       L'avviso lo dice prima dell'Attiva. (L'azione Annulla vive solo nel
       pannello Proposte della chat: è la superficie d'azione scelta.) */
    var pcfg = p.config || {};
    var warn = (p.type === 'ha_dashboard' && pcfg.mode === 'replace')
      ? '<div class="pp-warn">Sostituisce interamente la plancia "' + escHtml(String(pcfg.slug || '')) + '".</div>'
      : '';
    var date = p.created_at ? p.created_at.substring(0, 10) : '';
    var safeId = escHtml(p.id);
    var actions = status === 'pending'
      ? '<button class="btn-apply" data-pid="' + safeId + '">Attiva</button>'
      + '<button class="btn-reject" data-pid="' + safeId + '">Rifiuta</button>'
      : '';
    return '<div class="proposal-row" id="pr-' + safeId + '">'
      + '<div class="proposal-info">'
      + '<div class="proposal-name"><span class="type-badge" style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;background:var(--accent-tint);color:var(--accent-ink);padding:1px 6px;border-radius:4px;font-family:var(--font-mono);margin-right:6px;vertical-align:middle">' + escHtml(typeLabel) + '</span>' + escHtml(p.name) + '</div>'
      + '<div class="proposal-meta">' + date + '</div>'
      + '<div class="proposal-desc">' + escHtml(p.description || '') + '</div>'
      + warn
      + '<div class="proposal-reason"><strong>Motivo:</strong> ' + escHtml(p.routing_reason || '') + '</div>'
      + configPreview
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
    var res = await HirisProposalsCore.apply(id);
    // I-5 (fratello): mai la stringa tecnica del backend, messaggio derivato
    // dallo stato -- stesso HirisProposalsCore.errorMessage di chat/proposals.js.
    if (!res.ok) {
      console.error('applyProposal failed', res.status, res.error);
      alert(HirisProposalsCore.errorMessage(res));
      return;
    }
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
    var res = await HirisProposalsCore.reject(id);
    // I-5 (fratello): idem sopra in applyProposal().
    if (!res.ok) {
      console.error('rejectProposal failed', res.status, res.error);
      alert(HirisProposalsCore.errorMessage(res));
      return;
    }
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
  if (!list) return;   /* difesa: questa funzione vive sulla pagina Proposte; se
                          invocata altrove (DOM senza #proposals-list) non deve lanciare */
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
