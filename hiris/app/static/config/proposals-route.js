/* HIRIS · Designer · proposals route mount (Phase 9) */
(function() {
  function mount() {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML =
      '<div class="page-title">Proposte automazione</div>' +
      '<p class="page-subtitle">Una proposta attivata genera una <strong>automation HA nativa</strong>. Le proposte sono generate dagli agenti HIRIS sulla base dei loro pattern di osservazione.</p>' +
      '<div class="proposals-tabs" style="display:flex;gap:8px;margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:8px">' +
        '<button class="proposals-tab active" id="prop-tab-pending" data-tab="pending">In attesa</button>' +
        '<button class="proposals-tab" id="prop-tab-archived" data-tab="archived">Archivio</button>' +
      '</div>' +
      '<div id="proposals-list">' +
        '<div class="proposals-empty">Caricamento…</div>' +
      '</div>';

    /* Wire tab clicks */
    var pending = document.getElementById('prop-tab-pending');
    var archived = document.getElementById('prop-tab-archived');
    function activate(tab) {
      pending.classList.toggle('active', tab === 'pending');
      archived.classList.toggle('active', tab === 'archived');
      if (typeof loadProposals === 'function') {
        loadProposals(tab);
      } else {
        document.getElementById('proposals-list').innerHTML = '<div class="proposals-empty">proposals.js non caricato — apri prima un agente per inizializzare i moduli legacy.</div>';
      }
      if (typeof window !== 'undefined') window._currentProposalTab = tab;
    }
    pending.addEventListener('click', function() { activate('pending'); });
    archived.addEventListener('click', function() { activate('archived'); });

    /* Initial load */
    activate('pending');
  }

  window.HirisProposalsRoute = { mount: mount };
})();
