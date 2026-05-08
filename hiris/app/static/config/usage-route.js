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
      '<p class="page-subtitle">Token, costi e budget per agente. Stat aggregate dall\'avvio o dall\'ultimo reset.</p>' +
      '<div class="stat-grid" id="usage-global-grid">' +
        '<div class="stat-tile"><div class="st-label">Richieste</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token IN</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token OUT</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Costo</div><div class="st-value">—</div></div>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:8px">' +
        '<button class="btn btn-danger" id="usage-reset-global">↺ Azzera contatori globali</button>' +
      '</div>' +
      '<div class="dash-list" style="margin-top:24px">' +
        '<h3>Per agente <span class="right" id="usage-per-agent-count">—</span></h3>' +
        '<div id="usage-per-agent-body"><div style="padding:24px;color:var(--text-3)">Caricamento…</div></div>' +
      '</div>';

    /* Global usage */
    fetch('api/usage').then(function(r) { return r.ok ? r.json() : {}; }).then(function(u) {
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
    });

    /* Per-agent table */
    fetch('api/agents').then(function(r) { return r.ok ? r.json() : []; }).then(function(d) {
      var list = Array.isArray(d) ? d : (d.agents || []);
      var body = document.getElementById('usage-per-agent-body');
      var countEl = document.getElementById('usage-per-agent-count');
      if (countEl) countEl.textContent = list.length + ' totali';
      if (!body) return;
      if (!list.length) {
        body.innerHTML = '<div style="padding:24px;color:var(--text-3)">Nessun agente configurato.</div>';
        return;
      }
      var sorted = list.slice().sort(function(a, b) {
        var ea = a.enabled ? 1 : 0, eb = b.enabled ? 1 : 0;
        if (eb !== ea) return eb - ea;
        return (a.name || '').localeCompare(b.name || '');
      });
      body.innerHTML = sorted.map(function(a) {
        var u = a.usage || {};
        var tin = u.input_tokens || 0;
        var tout = u.output_tokens || 0;
        var cost = u.cost_eur || 0;
        var reqs = u.requests || 0;
        var budget = a.budget_limit_eur || a.usage_budget_eur || 0;
        var pct = budget > 0 ? Math.round((cost / budget) * 100) : 0;
        var paused = !!a._rate_limit_paused;
        var enabled = !!a.enabled;
        var rowCls = 'dl-row agent-row' + (enabled ? '' : ' is-disabled') + (paused ? ' is-paused' : '');
        var badge = paused
          ? '<span class="agent-badge badge-paused">⏸ in pausa</span>'
          : (enabled
              ? '<span class="agent-badge badge-on">● Attivo</span>'
              : '<span class="agent-badge badge-off">○ Disabilitato</span>');
        return '<a class="' + rowCls + '" href="#/agents/' + escHtml(a.id) + '">' +
          '<span class="dl-time"><span class="dot ' + (paused ? 'iris' : (enabled ? 'on' : 'off')) + '"></span></span>' +
          '<span class="dl-content">' +
            '<span class="dl-agent">' + escHtml(a.name) + '</span>' +
            '<span class="dl-text">' + reqs + ' run · ' + formatTokens(tin + tout) + ' tok · €' + Number(cost).toFixed(3) + (budget > 0 ? ' / €' + budget + ' (' + pct + '%)' : '') + '</span>' +
          '</span>' +
          badge +
          '<span class="dl-arrow">→</span>' +
        '</a>';
      }).join('');
    });

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
