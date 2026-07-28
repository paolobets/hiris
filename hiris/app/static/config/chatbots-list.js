/* HIRIS · Designer · agents list route mount (Phase 9 / 4.0) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fetchAgents() {
    return fetch('api/chatbots').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) { return Array.isArray(d) ? d : (d.agents || []); });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px">' +
        '<div class="page-title">Chatbot</div>' +
        '<a class="btn btn-primary" href="#/nuovo">+ Nuovo Chatbot</a>' +
      '</div>' +
      '<p class="page-subtitle">Click su un Chatbot per aprire l\'editor.</p>' +
      '<div class="dash-list" id="agents-list-body"><div style="padding:24px;color:var(--text-3)">Caricamento…</div></div>';

    fetchAgents().then(function(agents) {
      HirisState.set('chatbots', agents);
      var body = document.getElementById('agents-list-body');
      if (!body) return;
      if (!agents.length) {
        body.innerHTML = '<div style="padding:24px;color:var(--text-3);text-align:center">Nessun Chatbot configurato. <a href="#/nuovo">Crea il primo</a>.</div>';
        return;
      }
      var sorted = agents.slice().sort(function(a, b) {
        var ea = a.enabled ? 1 : 0, eb = b.enabled ? 1 : 0;
        if (eb !== ea) return eb - ea;
        return (a.name || '').localeCompare(b.name || '');
      });
      var nActive = agents.filter(function(a){return a.enabled;}).length;
      var nDisabled = agents.length - nActive;
      var summary = '<div class="agents-summary">' +
        '<span class="chip chip-on">✓ attivi ' + nActive + '</span>' +
        '<span class="chip chip-off">⏸ disabilitati ' + nDisabled + '</span>' +
        '</div>';
      body.innerHTML = summary + sorted.map(function(a) {
        var paused = !!a._rate_limit_paused;
        var enabled = !!a.enabled;
        var dotCls = paused ? 'iris' : (enabled ? 'on' : 'off');
        var rowCls = 'dl-row agent-row' + (enabled ? '' : ' is-disabled') + (paused ? ' is-paused' : '');
        var badge = paused
          ? '<span class="agent-badge badge-paused">⏸ in pausa</span>'
          : (enabled
              ? '<span class="agent-badge badge-on">● Attivo</span>'
              : '<span class="agent-badge badge-off">○ Disabilitato</span>');
        /* Task 4 (Slice 5): rimossi typeLabel/triggerCount — il campo `type`
           e i trigger sono stati ritirati dal backend (Task 1-3), ogni
           agente è ormai una persona chat-only. */
        var modelLabel = a.model || 'auto';
        var lastLog = (a.execution_log || [])[a.execution_log ? a.execution_log.length - 1 : -1];
        var lastLogText = lastLog ? ('ultima esec ' + new Date(lastLog.timestamp).toLocaleTimeString('it-IT', {hour:'2-digit',minute:'2-digit'}) + (lastLog.success ? ' ✓' : ' ✗')) : 'mai eseguito';
        return '<a class="' + rowCls + '" href="#/chatbots/' + escHtml(a.id) + '">' +
          '<span class="dl-time"><span class="dot ' + dotCls + '"></span></span>' +
          '<span class="dl-content">' +
            '<span class="dl-agent">' + escHtml(a.name) + '</span>' +
            '<span class="dl-text">' + escHtml(modelLabel) + ' · ' + lastLogText + '</span>' +
          '</span>' +
          badge +
          '<span class="dl-arrow">→</span>' +
        '</a>';
      }).join('');
    }).catch(function(err) {
      console.error('agents fetch failed', err);
      var body = document.getElementById('agents-list-body');
      if (body) body.innerHTML = '<div class="proposals-error" style="text-align:center;padding:24px">Errore nel caricamento della lista Chatbot. Riprova.</div>';
    });
  }

  window.HirisChatbotsList = { mount: mount };
})();
