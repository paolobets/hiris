/* HIRIS · Designer · tasks route mount (v0.10.7) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      return d.toLocaleString('it-IT', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    } catch(e) { return iso; }
  }

  function describeTrigger(t) {
    if (!t || typeof t !== 'object') return '—';
    if (t.type === 'delay') return 'tra ' + (t.minutes || 0) + ' min';
    if (t.type === 'cron') return 'cron: ' + (t.cron || '');
    if (t.type === 'state_changed') return 'state: ' + (t.entity_id || '');
    if (t.type === 'absolute_time') return 'alle ' + (t.iso || '');
    return t.type || JSON.stringify(t);
  }

  var STATUS_LABELS = {
    pending: 'In attesa',
    executed: 'Eseguito',
    cancelled: 'Cancellato',
    failed: 'Fallito',
  };

  var STATUS_CLS = {
    pending: 'warn',
    executed: 'ok',
    cancelled: '',
    failed: 'err',
  };

  function fetchTasks(filterStatus) {
    var url = 'api/tasks';
    if (filterStatus && filterStatus !== 'all') url += '?status=' + encodeURIComponent(filterStatus);
    return fetch(url).then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; });
  }

  function cancelTask(id) {
    return fetch('api/tasks/' + encodeURIComponent(id), {
      method: 'DELETE',
      headers: { 'X-Requested-With': 'fetch' },
    });
  }

  function buildRow(t, agentNamesById) {
    var agentName = agentNamesById[t.agent_id] || t.agent_id || '—';
    var statusCls = STATUS_CLS[t.status] || '';
    var statusLabel = STATUS_LABELS[t.status] || t.status || '—';
    var actionsCount = (t.actions && t.actions.length) || 0;
    var actionsLabel = actionsCount + ' azion' + (actionsCount === 1 ? 'e' : 'i');
    var triggerDesc = describeTrigger(t.trigger);

    var detailMeta = [];
    detailMeta.push('<span class="meta-chip">📋 trigger: ' + escHtml(triggerDesc) + '</span>');
    detailMeta.push('<span class="meta-chip">⚙ ' + actionsLabel + '</span>');
    if (t.executed_at) detailMeta.push('<span class="meta-chip">✓ ' + escHtml(fmtDate(t.executed_at)) + '</span>');
    if (t.error) detailMeta.push('<span class="meta-chip" style="color:var(--err);background:var(--err-tint);border-color:transparent">⚠ ' + escHtml(t.error) + '</span>');
    if (t.parent_task_id) detailMeta.push('<span class="meta-chip">↳ parent: ' + escHtml(t.parent_task_id.slice(0, 8)) + '…</span>');

    var actionsHtml = '<button class="btn btn-sm btn-ghost" data-act="copy-raw" data-tid="' + escHtml(t.id) + '">{} copia raw JSON</button>';
    if (t.status === 'pending') {
      actionsHtml = '<button class="btn btn-sm btn-danger" data-act="cancel" data-tid="' + escHtml(t.id) + '">⊘ Cancella</button>' + actionsHtml;
    }

    var resultBlock = '';
    if (t.result) {
      resultBlock = '<pre style="background:var(--surface-2);padding:8px 10px;border-radius:4px;font-size:12px;color:var(--text-2);white-space:pre-wrap;max-height:200px;overflow-y:auto">' + escHtml(t.result) + '</pre>';
    }

    return '<li class="log-row" data-tid="' + escHtml(t.id) + '" data-raw=\'' + escHtml(JSON.stringify(t)) + '\'>' +
      '<div class="lr-collapsed">' +
        '<span class="lr-time">' + escHtml(fmtDate(t.created_at)) + '</span>' +
        '<span class="lr-status ' + statusCls + '">' + escHtml(statusLabel) + '</span>' +
        '<span class="lr-summary"><strong>' + escHtml(agentName) + '</strong>' + (t.label && t.label !== agentName ? ' · ' + escHtml(t.label) : '') + '</span>' +
        '<span class="lr-tokens">' + escHtml(triggerDesc) + '</span>' +
        '<span class="lr-chev">▼</span>' +
      '</div>' +
      '<div class="lr-detail">' +
        '<p class="lrd-summary"><strong>' + escHtml(t.label || '(senza etichetta)') + '</strong></p>' +
        '<div class="lrd-meta">' + detailMeta.join('') + '</div>' +
        resultBlock +
        '<div class="lrd-actions">' + actionsHtml + '</div>' +
      '</div>' +
    '</li>';
  }

  function renderTasks(filterStatus) {
    var listBody = document.getElementById('tasks-list-body');
    if (!listBody) return;
    listBody.innerHTML = '<div style="padding:24px;color:var(--text-3)">Caricamento…</div>';

    /* Fetch tasks + agents in parallel for name resolution */
    Promise.all([
      fetchTasks(filterStatus),
      fetch('api/agents').then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; }),
    ]).then(function(results) {
      var tasks = results[0] || [];
      var agents = Array.isArray(results[1]) ? results[1] : (results[1].agents || []);
      var byId = {};
      agents.forEach(function(a) { byId[a.id] = a.name; });

      /* Update tab counters via separate fetch (always all statuses) */
      fetchTasks('all').then(function(allTasks) {
        var counts = { all: allTasks.length, pending: 0, executed: 0, cancelled: 0, failed: 0 };
        allTasks.forEach(function(t) {
          if (counts[t.status] !== undefined) counts[t.status]++;
        });
        ['all', 'pending', 'executed', 'cancelled', 'failed'].forEach(function(k) {
          var el = document.getElementById('tasks-count-' + k);
          if (el) el.textContent = counts[k];
        });
        /* Sync sidenav badge with pending count (hide when 0) */
        var navBadge = document.getElementById('nav-tasks-count');
        if (navBadge) {
          navBadge.textContent = counts.pending;
          navBadge.classList.toggle('is-empty', counts.pending === 0);
        }
      });

      if (!tasks.length) {
        listBody.innerHTML = '<div style="padding:24px;color:var(--text-3);text-align:center"><div style="font-size:32px;opacity:0.3;margin-bottom:8px">∅</div>Nessun task ' + (filterStatus !== 'all' ? STATUS_LABELS[filterStatus] || filterStatus : '') + '.</div>';
        return;
      }

      /* Sort: pending+failed first, then by created_at desc */
      tasks.sort(function(a, b) {
        var sa = (a.status === 'pending' || a.status === 'failed') ? 0 : 1;
        var sb = (b.status === 'pending' || b.status === 'failed') ? 0 : 1;
        if (sa !== sb) return sa - sb;
        return (b.created_at || '').localeCompare(a.created_at || '');
      });

      listBody.innerHTML = '<ul class="log-list-v2" style="list-style:none;padding:0;margin:0">' +
        tasks.map(function(t) { return buildRow(t, byId); }).join('') +
      '</ul>';
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML =
      '<div class="page-title">Task pianificati</div>' +
      '<p class="page-subtitle">Task asincrone schedulate dagli agenti (es. <code class="code-inline">create_task()</code> in irrigazione, scenari rientro, ecc).</p>' +
      '<div class="log-toolbar">' +
        '<span class="filter-chip active" data-filter="all">tutti<span class="fc-count" id="tasks-count-all">—</span></span>' +
        '<span class="filter-chip" data-filter="pending">⏱ in attesa<span class="fc-count" id="tasks-count-pending">—</span></span>' +
        '<span class="filter-chip" data-filter="executed">✓ eseguiti<span class="fc-count" id="tasks-count-executed">—</span></span>' +
        '<span class="filter-chip" data-filter="failed">✗ falliti<span class="fc-count" id="tasks-count-failed">—</span></span>' +
        '<span class="filter-chip" data-filter="cancelled">⊘ cancellati<span class="fc-count" id="tasks-count-cancelled">—</span></span>' +
        '<span class="lt-spacer"></span>' +
        '<button class="btn btn-sm btn-ghost" id="tasks-refresh">↻ aggiorna</button>' +
      '</div>' +
      '<div id="tasks-list-body"></div>';

    var currentFilter = 'all';

    /* Wire filter chips */
    document.querySelectorAll('#route-outlet .filter-chip').forEach(function(chip) {
      chip.addEventListener('click', function() {
        document.querySelectorAll('#route-outlet .filter-chip').forEach(function(c) { c.classList.remove('active'); });
        chip.classList.add('active');
        currentFilter = chip.dataset.filter;
        renderTasks(currentFilter);
      });
    });

    /* Wire refresh */
    document.getElementById('tasks-refresh').addEventListener('click', function() {
      renderTasks(currentFilter);
    });

    /* Click row → toggle expanded (same pattern as log-row v6).
       CSS uses .log-row.expanded .lr-detail { display: flex !important },
       so we toggle the class only — no inline display manipulation. */
    document.getElementById('tasks-list-body').addEventListener('click', function(e) {
      if (e.target.closest('button')) return;
      var li = e.target.closest('.log-row');
      if (!li) return;
      var wasExpanded = li.classList.contains('expanded');
      document.querySelectorAll('#tasks-list-body .log-row.expanded').forEach(function(other) {
        other.classList.remove('expanded');
      });
      if (!wasExpanded) li.classList.add('expanded');
    });

    /* Delegated cancel + copy-raw */
    document.getElementById('tasks-list-body').addEventListener('click', function(e) {
      var btn = e.target.closest('[data-act]');
      if (!btn) return;
      e.stopPropagation();
      var act = btn.dataset.act;
      var tid = btn.dataset.tid;
      if (act === 'cancel') {
        if (!confirm('Cancellare questo task?')) return;
        cancelTask(tid).then(function(r) {
          if (r.ok || r.status === 204) renderTasks(currentFilter);
          else alert('Errore cancellazione (HTTP ' + r.status + ')');
        }).catch(function() { alert('Errore di rete'); });
      } else if (act === 'copy-raw') {
        var li = btn.closest('.log-row');
        var raw = li && li.dataset.raw;
        if (raw) {
          try { navigator.clipboard.writeText(raw); } catch(e) {}
        }
      }
    });

    renderTasks(currentFilter);
  }

  window.HirisTasksRoute = { mount: mount };
})();
