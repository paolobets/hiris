/* HIRIS · Designer · dashboard adaptive route (Phase 8) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function midTruncate(s, n) {
    if (!s || s.length <= n) return s || '';
    return s.slice(0, Math.ceil((n-1)/2)) + '…' + s.slice(-Math.floor((n-1)/2));
  }

  function formatTokens(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'k';
    return String(n);
  }

  function greeting() {
    var h = new Date().getHours();
    if (h < 6) return 'Buonanotte';
    if (h < 12) return 'Buongiorno';
    if (h < 18) return 'Buon pomeriggio';
    return 'Buonasera';
  }

  /* Fallback fetch: loadAgents() in agent-form.js mutates module state and
     touches DOM (#agent-list); not safe to call before that DOM exists. */
  function fetchAgentsDirect() {
    return fetch('api/agents').then(function(r) {
      return r.ok ? r.json() : { agents: [] };
    }).then(function(d) {
      /* api/agents returns either an array or {agents: [...]} */
      if (Array.isArray(d)) return d;
      return d.agents || [];
    }).catch(function() { return []; });
  }

  function renderEmpty(outlet) {
    outlet.innerHTML =
      '<div class="page-title">Benvenuto in HIRIS</div>' +
      '<p class="page-subtitle">Configura il tuo primo agente AI per Home Assistant. Scegli un template per iniziare velocemente, oppure parti da zero.</p>' +
      '<div class="stat-grid" style="grid-template-columns:repeat(3, 1fr)">' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">⚡ Energia</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Monitor consumi</div>' +
          '<div class="st-delta">Rileva anomalie e suggerisce azioni</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">🏠 Rientro</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Scenario casa</div>' +
          '<div class="st-delta">Attiva luci/clima al rientro</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">⏰ Promemoria</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Notifiche schedulate</div>' +
          '<div class="st-delta">Reminder ricorrenti</div>' +
        '</a>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:12px">' +
        '<a class="btn btn-primary" href="#/agents/new">+ Crea agente vuoto</a>' +
        '<a class="btn btn-ghost" href="docs/" target="_blank">Cosa è HIRIS?</a>' +
      '</div>';
  }

  function renderPopulated(outlet, agents) {
    var enabled = agents.filter(function(a) { return a.enabled; }).length;
    var paused = agents.filter(function(a) { return a._rate_limit_paused; }).length;
    var disabled = agents.length - enabled - paused;

    outlet.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:24px">' +
        '<div>' +
          '<h1 style="font-size:var(--fs-24);font-weight:600;letter-spacing:-0.02em">' + greeting() + '</h1>' +
          '<p style="font-size:var(--fs-13);color:var(--text-3);margin-top:4px">' +
            agents.length + ' agenti configurati · ' + enabled + ' abilitati' +
            (paused ? ' · ' + paused + ' in pausa rate-limit' : '') +
          '</p>' +
        '</div>' +
        '<div style="display:flex;gap:8px">' +
          '<a class="btn btn-primary" href="#/agents/new">+ Nuovo agente</a>' +
          '<a class="btn btn-ghost" href="./">Vai alla chat</a>' +
        '</div>' +
      '</div>' +

      '<div class="stat-grid">' +
        '<div class="stat-tile">' +
          '<div class="st-label">Agenti attivi</div>' +
          '<div class="st-value">' + enabled + '<span class="text-muted" style="font-weight:400;font-size:var(--fs-15)"> / ' + agents.length + '</span></div>' +
          '<div class="st-delta">' + paused + ' in pausa, ' + disabled + ' disabilitato' + (disabled !== 1 ? 'i' : '') + '</div>' +
        '</div>' +
        '<div class="stat-tile">' +
          '<div class="st-label">Esecuzioni 24h</div>' +
          '<div class="st-value" id="dash-exec24h">—</div>' +
          '<div class="st-delta" id="dash-exec24h-delta"></div>' +
        '</div>' +
        '<div class="stat-tile">' +
          '<div class="st-label">Token oggi</div>' +
          '<div class="st-value" id="dash-tokens">—</div>' +
          '<div class="st-delta" id="dash-tokens-delta"></div>' +
        '</div>' +
        '<div class="stat-tile">' +
          '<div class="st-label">Costo mese</div>' +
          '<div class="st-value" id="dash-cost">—</div>' +
          '<div class="st-delta" id="dash-cost-delta"></div>' +
        '</div>' +
      '</div>' +

      '<div class="dash-cols">' +
        '<div>' +
          '<div class="dash-list">' +
            '<h3>Ultimi log <span class="right" id="dash-logs-count">cross-agent</span></h3>' +
            '<div id="dash-last-logs-body"><div style="padding:24px;color:var(--text-3)">Caricamento…</div></div>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:20px">' +
          '<div class="dash-list">' +
            '<h3>Proposte pending <span class="right" id="dash-prop-count">—</span></h3>' +
            '<div id="dash-proposals-body"><div style="padding:16px;color:var(--text-3)">Caricamento…</div></div>' +
          '</div>' +
          '<div class="dash-list">' +
            '<h3>Prossimi trigger <span class="right">P2</span></h3>' +
            '<div style="padding:16px;color:var(--text-3);font-size:var(--fs-12)">Coming soon — implementazione next triggers richiede endpoint backend (P2).</div>' +
          '</div>' +
        '</div>' +
      '</div>';

    /* Async loaders */
    fetch('api/usage').then(function(r) { return r.ok ? r.json() : {}; }).then(function(u) {
      var execEl = document.getElementById('dash-exec24h');
      var tokEl = document.getElementById('dash-tokens');
      var tokDeltaEl = document.getElementById('dash-tokens-delta');
      var costEl = document.getElementById('dash-cost');
      var costDeltaEl = document.getElementById('dash-cost-delta');
      if (execEl) execEl.textContent = u.executions_24h != null ? u.executions_24h : (u.total_requests || 0);
      var tin = u.total_input_tokens || u.input_tokens || 0;
      var tout = u.total_output_tokens || u.output_tokens || 0;
      if (tokEl) tokEl.textContent = formatTokens(tin + tout);
      if (tokDeltaEl) tokDeltaEl.textContent = formatTokens(tin) + ' in · ' + formatTokens(tout) + ' out';
      var cost = u.total_cost_eur || u.cost_eur || 0;
      if (costEl) costEl.textContent = '€ ' + Number(cost).toFixed(2);
      if (costDeltaEl) costDeltaEl.textContent = u.budget_eur ? ('budget €' + Number(u.budget_eur).toFixed(2)) : '';
    }).catch(function() { /* silent */ });

    /* Cross-agent last logs (limit to first 6 agents to avoid N+1 explosion) */
    var subset = agents.slice(0, 6);
    Promise.all(subset.map(function(a) {
      return fetch('api/agents/' + encodeURIComponent(a.id)).then(function(r) { return r.ok ? r.json() : null; }).then(function(d) {
        if (!d) return [];
        var ag = d.agent || d;
        return (ag.execution_log || []).slice(-3).map(function(l) {
          return { agent_id: a.id, agent_name: a.name, timestamp: l.timestamp, success: l.success, summary: l.result_summary || '' };
        });
      }).catch(function() { return []; });
    })).then(function(arr) {
      var flat = [].concat.apply([], arr).sort(function(a, b) {
        return new Date(b.timestamp) - new Date(a.timestamp);
      }).slice(0, 8);
      var body = document.getElementById('dash-last-logs-body');
      if (!body) return;
      if (!flat.length) {
        body.innerHTML = '<div style="padding:24px;color:var(--text-3)">Nessun log recente.</div>';
        return;
      }
      body.innerHTML = flat.map(function(item) {
        var t = new Date(item.timestamp);
        var timeStr = t.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
        return '<a class="dl-row" href="#/agents/' + escHtml(item.agent_id) + '">' +
          '<span class="dl-time">' + escHtml(timeStr) + '</span>' +
          '<span class="dl-content">' +
            '<span class="dl-agent">' + escHtml(item.agent_name) + '</span>' +
            '<span class="dl-text">' + escHtml(midTruncate(item.summary, 70)) + '</span>' +
          '</span>' +
          '<span class="dl-status" style="color:var(--' + (item.success ? 'ok' : 'err') + ')">' + (item.success ? '✓' : '✗') + '</span>' +
        '</a>';
      }).join('');
    });

    /* Proposals peek */
    fetch('api/proposals?status=pending').then(function(r) { return r.ok ? r.json() : { proposals: [] }; }).then(function(d) {
      var props = (d.proposals || []).slice(0, 3);
      var body = document.getElementById('dash-proposals-body');
      var countEl = document.getElementById('dash-prop-count');
      if (countEl) countEl.textContent = (d.proposals || []).length + ' nuove';
      if (!body) return;
      if (!props.length) {
        body.innerHTML = '<div style="padding:16px;color:var(--text-3)">Nessuna proposta pending.</div>';
        return;
      }
      body.innerHTML = props.map(function(p) {
        return '<div class="prop-card">' +
          '<div class="prop-title">' +
            '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;background:var(--accent-tint);color:var(--accent-ink);padding:1px 6px;border-radius:4px;font-family:var(--font-mono);margin-right:6px;vertical-align:middle">→ automazione HA</span>' +
            escHtml(p.name) +
          '</div>' +
          '<div class="prop-desc">' + escHtml(p.description || '') + '</div>' +
          '<div class="prop-actions">' +
            '<button class="btn btn-sm btn-primary" data-act="apply" data-pid="' + escHtml(p.id) + '">Attiva</button>' +
            '<button class="btn btn-sm" data-act="reject" data-pid="' + escHtml(p.id) + '">Rifiuta</button>' +
          '</div>' +
        '</div>';
      }).join('');

      /* Wire apply/reject buttons (delegate to existing logic in proposals.js if loaded) */
      body.querySelectorAll('[data-act="apply"]').forEach(function(b) {
        b.addEventListener('click', function() {
          if (typeof applyProposal === 'function') applyProposal(b.dataset.pid);
        });
      });
      body.querySelectorAll('[data-act="reject"]').forEach(function(b) {
        b.addEventListener('click', function() {
          if (typeof rejectProposal === 'function') rejectProposal(b.dataset.pid);
        });
      });
    }).catch(function() { /* silent */ });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    var agents = HirisState.get('agents') || [];

    if (agents.length === 0) {
      /* Fetch agents directly (avoids depending on agent-form.js loadAgents) */
      fetchAgentsDirect().then(function(loaded) {
        HirisState.set('agents', loaded);
        if (loaded.length === 0) renderEmpty(outlet);
        else renderPopulated(outlet, loaded);
      });
    } else {
      renderPopulated(outlet, agents);
    }
  }

  window.HirisDashboard = { mount: mount };
})();
