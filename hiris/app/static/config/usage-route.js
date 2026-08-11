/* HIRIS · Designer · usage route mount (Phase 9) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatTokens(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'k';
    return String(n);
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML =
      '<div class="page-title">Consumi globali</div>' +
      '<p class="page-subtitle">Token e costi complessivi, aggregati dall\'avvio o dall\'ultimo reset. ' +
        'Il dettaglio per Chatbot non è misurato in questa versione — HIRIS gira su un\'unica chat, senza id.</p>' +
      '<div class="stat-grid" id="usage-global-grid">' +
        '<div class="stat-tile"><div class="st-label">Richieste</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token IN</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token OUT</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Costo</div><div class="st-value">—</div></div>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:8px">' +
        '<button class="btn btn-danger" id="usage-reset-global">↺ Azzera contatori globali</button>' +
      '</div>';

    /* Global usage */
    fetch('api/usage').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(u) {
      var grid = document.getElementById('usage-global-grid');
      if (!grid) return;
      var tin = u.total_input_tokens || u.input_tokens || 0;
      var tout = u.total_output_tokens || u.output_tokens || 0;
      var cost = u.total_cost_eur || u.cost_eur || 0;
      var req = u.total_requests || u.requests || 0;
      var lastReset = u.last_reset || u.reset_at || '';
      grid.innerHTML =
        '<div class="stat-tile"><div class="st-label">Richieste</div><div class="st-value">' + req + '</div><div class="st-delta">' + (lastReset ? 'da ' + escHtml(String(lastReset).slice(0,10)) : '') + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token IN</div><div class="st-value">' + formatTokens(tin) + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token OUT</div><div class="st-value">' + formatTokens(tout) + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Costo</div><div class="st-value">€ ' + Number(cost).toFixed(2) + '</div></div>';
    }).catch(function(err) {
      console.error('usage global fetch failed', err);
      var grid = document.getElementById('usage-global-grid');
      if (grid) grid.innerHTML = '<div class="proposals-error" style="grid-column:1/-1">Errore caricamento consumi.</div>';
    });

    /* fetta E5 Task 7 ("Consumi e Modelli smettono di mentire"): la tabella
       "Per Chatbot" esce -- non era una rotta morta (GET api/chatbots
       risponde), ma mentiva per omissione: i campi usage/budget_limit_eur/
       _rate_limit_paused che leggeva non esistono piu' nel payload
       (handlers_chatbots.handle_list_chatbots, dalla E4 Task 4 "un bot
       solo") e degradavano tutti a zero -- sembrava un consumo azzerato, era
       un consumo mai misurato per-entita'. Il sottotitolo qui sopra lo
       dichiara invece di lasciarlo sparire in silenzio. */

    /* Reset button */
    var resetBtn = document.getElementById('usage-reset-global');
    if (resetBtn) {
      resetBtn.addEventListener('click', function() {
        if (!confirm('Azzerare tutti i contatori globali? L\'operazione è irreversibile.')) return;
        fetch('api/usage/reset', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
          .then(function(r) { if (r.ok) mount(); else alert('Errore reset'); })
          .catch(function() { alert('Errore di rete'); });
      });
    }
  }

  window.HirisUsageRoute = { mount: mount };
})();
