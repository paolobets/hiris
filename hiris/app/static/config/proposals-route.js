/* HIRIS · Designer · proposals route mount (Phase 9) */
(function() {
  function mount() {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML =
      '<div class="page-title">Proposte automazione</div>' +
      '<p class="page-subtitle">Una proposta attivata genera una <strong>automation HA nativa</strong>. Le proposte sono generate dagli agenti HIRIS sulla base dei loro pattern di osservazione.</p>' +
      '<div class="proposals-tabs" style="display:flex;gap:8px;margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:8px">' +
        '<button class="proposals-tab active" id="prop-tab-pending" data-tab="pending">In attesa <span class="fc-count" id="prop-count-pending">—</span></button>' +
        '<button class="proposals-tab" id="prop-tab-archived" data-tab="archived">Archivio <span class="fc-count" id="prop-count-archived">—</span></button>' +
      '</div>' +
      '<div id="proposals-list">' +
        '<div class="proposals-empty">Caricamento…</div>' +
      '</div>';

    /* Counts: parallel fetch of both tabs to populate badges */
    function updateCounts() {
      Promise.all([
        fetch('api/proposals?status=pending').then(function(r){ return r.ok ? r.json() : {proposals:[]}; }).catch(function(){ return {proposals:[]}; }),
        fetch('api/proposals?status=archived').then(function(r){ return r.ok ? r.json() : {proposals:[]}; }).catch(function(){ return {proposals:[]}; })
      ]).then(function(results) {
        var p = (results[0].proposals || []).length;
        var a = (results[1].proposals || []).length;
        var elP = document.getElementById('prop-count-pending');
        var elA = document.getElementById('prop-count-archived');
        if (elP) elP.textContent = p;
        if (elA) elA.textContent = a;
      });
    }

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

    /* Initial load + counts */
    activate('pending');
    updateCounts();
  }

  window.HirisProposalsRoute = { mount: mount };
})();
