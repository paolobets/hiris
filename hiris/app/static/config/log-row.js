/* HIRIS · Designer · log row v6 (Phase 5)
   Mid-truncation, click-anywhere expand, accordion, filter chips. */
(function() {
  var EVAL_CLASS = { 'OK': 'ok', 'ATTENZIONE': 'warn', 'ANOMALIA': 'err' };

  function midTruncate(s, maxLen) {
    if (!s || s.length <= maxLen) return s;
    var head = Math.ceil((maxLen - 1) / 2);
    var tail = Math.floor((maxLen - 1) / 2);
    return s.slice(0, head) + '…' + s.slice(-tail);
  }

  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function render(container, agent) {
    var log = (agent && agent.execution_log) || [];
    container.innerHTML = '';
    if (log.length === 0) {
      container.innerHTML = '<div class="log-empty" style="padding:24px;text-align:center;color:var(--text-3);border:1px dashed var(--border);border-radius:6px"><div style="font-size:32px;opacity:0.3;margin-bottom:8px">∅</div>Nessuna esecuzione registrata.<br><span style="font-size:12px">Lancia un Test Run o attendi il prossimo trigger.</span></div>';
      return;
    }

    var toolbar = document.createElement('div');
    toolbar.className = 'log-toolbar';
    var counts = countFilters(log);
    toolbar.innerHTML =
      '<span class="filter-chip active" data-filter="all">tutti<span class="fc-count">' + counts.all + '</span></span>' +
      '<span class="filter-chip" data-filter="ok">✓ ok<span class="fc-count">' + counts.ok + '</span></span>' +
      '<span class="filter-chip" data-filter="err">✗ err<span class="fc-count">' + counts.err + '</span></span>' +
      (counts.thinking > 0 ? '<span class="filter-chip" data-filter="thinking">💭 thinking<span class="fc-count">' + counts.thinking + '</span></span>' : '') +
      '<span class="lt-spacer"></span>' +
      '<button class="btn btn-sm btn-ghost" data-act="refresh">↻ aggiorna</button>';
    container.appendChild(toolbar);

    var ul = document.createElement('ul');
    ul.className = 'log-list-v2';
    container.appendChild(ul);

    var maxLen = computeMaxLen(container);

    log.slice().reverse().forEach(function(r) {
      ul.appendChild(buildRow(r, maxLen));
    });

    toolbar.querySelectorAll('.filter-chip').forEach(function(chip) {
      chip.addEventListener('click', function() {
        toolbar.querySelectorAll('.filter-chip').forEach(function(c) { c.classList.remove('active'); });
        chip.classList.add('active');
        applyFilter(ul, chip.dataset.filter);
      });
    });

    var refreshBtn = toolbar.querySelector('[data-act="refresh"]');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function() {
        if (typeof loadAgent === 'function' && agent && agent.id) {
          loadAgent(agent.id).then(function(a) { render(container, a); });
        } else if (typeof openAgent === 'function' && agent && agent.id) {
          openAgent(agent.id);
        }
      });
    }
  }

  function countFilters(log) {
    var c = { all: log.length, ok: 0, err: 0, thinking: 0 };
    log.forEach(function(r) {
      if (r.success) c.ok++; else c.err++;
      if (r.thinking_blocks && r.thinking_blocks.length) c.thinking++;
    });
    return c;
  }

  function applyFilter(ul, filter) {
    ul.querySelectorAll('.log-row').forEach(function(row) {
      var match = filter === 'all'
        || (filter === 'ok' && row.dataset.success === 'true')
        || (filter === 'err' && row.dataset.success === 'false')
        || (filter === 'thinking' && row.dataset.thinking === 'true');
      row.style.display = match ? '' : 'none';
    });
  }

  function computeMaxLen(container) {
    var w = (container.getBoundingClientRect().width) || 800;
    var summaryW = w - 96 - 56 - 90 - 32;
    return Math.max(40, Math.floor(summaryW / 7));
  }

  function buildRow(r, maxLen) {
    var t = r.timestamp ? new Date(r.timestamp) : null;
    var timeStr = t ? t.toLocaleString('it-IT', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
    var statusCls = r.success ? 'ok' : 'err';
    var statusTxt = r.success ? '✓ ok' : '✗ err';
    var summary = r.result_summary || (r.tool_calls || []).join(', ') || '—';
    var preview = midTruncate(summary, maxLen);
    var evalCls = EVAL_CLASS[r.eval_status] || '';
    var evalBadge = r.eval_status ? '<span class="eval-badge ' + evalCls + '">' + escHtml(r.eval_status) + '</span> ' : '';
    var tokens = (r.input_tokens || 0) + '↓ ' + (r.output_tokens || 0) + '↑';

    var li = document.createElement('li');
    li.className = 'log-row';
    li.dataset.success = r.success ? 'true' : 'false';
    li.dataset.thinking = (r.thinking_blocks && r.thinking_blocks.length) ? 'true' : 'false';
    li.innerHTML =
      '<div class="lr-collapsed">' +
        '<span class="lr-time">' + escHtml(timeStr) + '</span>' +
        '<span class="lr-status ' + statusCls + '">' + statusTxt + '</span>' +
        '<span class="lr-summary">' + evalBadge + escHtml(preview) + '</span>' +
        '<span class="lr-tokens">' + tokens + '</span>' +
        '<span class="lr-chev">▼</span>' +
      '</div>' +
      buildDetail(r, evalBadge, summary);

    li.addEventListener('click', function(e) {
      if (e.target.closest('button, a')) return;
      var wasExpanded = li.classList.contains('expanded');
      var ul = li.parentElement;
      ul.querySelectorAll('.log-row.expanded').forEach(function(other) { other.classList.remove('expanded'); });
      if (!wasExpanded) li.classList.add('expanded');
    });

    return li;
  }

  function buildDetail(r, evalBadge, summary) {
    var meta = [];
    if (r.tool_calls && r.tool_calls.length) meta.push('<span class="meta-chip">🛠 ' + r.tool_calls.map(escHtml).join(' · ') + '</span>');
    if (r.action_taken) meta.push('<span class="meta-chip action">↳ ' + escHtml(r.action_taken) + '</span>');
    meta.push('<span class="meta-chip">📊 ' + (r.input_tokens || 0) + '↓ / ' + (r.output_tokens || 0) + '↑</span>');
    if (r.cost_eur != null) meta.push('<span class="meta-chip">€ ' + Number(r.cost_eur).toFixed(4) + '</span>');

    var actions = '<button class="btn btn-sm btn-ghost" data-act="copy-summary">📋 copia summary</button>' +
      '<button class="btn btn-sm btn-ghost" data-act="copy-raw">{} copia raw JSON</button>';

    var thinking = '';
    if (r.thinking_blocks && r.thinking_blocks.length) {
      actions = '<button class="btn btn-sm" data-act="toggle-thinking">💭 mostra thinking (' + r.thinking_blocks.length + ')</button>' + actions;
      thinking = '<pre class="thinking-block">' +
        r.thinking_blocks.map(function(tb, i) {
          return '— step ' + (i + 1) + ' —\n' + escHtml(tb);
        }).join('\n\n') +
        '</pre>';
    }

    /* style="display:none" inline come belt-and-suspenders contro cache stale CSS;
       il rule .log-row.expanded .lr-detail { display: flex !important } in
       hiris-config.css lo override quando il row ha la classe .expanded. */
    return '<div class="lr-detail" style="display:none">' +
      '<p class="lrd-summary">' + evalBadge + escHtml(summary) + '</p>' +
      '<div class="lrd-meta">' + meta.join('') + '</div>' +
      '<div class="lrd-actions" data-raw=\'' + escHtml(JSON.stringify(r)) + '\'>' + actions + '</div>' +
      thinking +
      '</div>';
  }

  /* Delegated handlers per copia + thinking toggle (one global listener) */
  document.addEventListener('click', function(e) {
    var b = e.target.closest('.lr-detail [data-act]');
    if (!b) return;
    e.stopPropagation();
    var detail = b.closest('.lr-detail');
    var actions = detail.querySelector('.lrd-actions');
    if (b.dataset.act === 'copy-summary') {
      try { navigator.clipboard.writeText(detail.querySelector('.lrd-summary').textContent.trim()); } catch(e) {}
    } else if (b.dataset.act === 'copy-raw') {
      try { navigator.clipboard.writeText(actions.dataset.raw); } catch(e) {}
    } else if (b.dataset.act === 'toggle-thinking') {
      detail.classList.toggle('show-thinking');
      var pre = detail.querySelector('.thinking-block');
      if (pre) pre.style.display = detail.classList.contains('show-thinking') ? 'block' : 'none';
      b.textContent = detail.classList.contains('show-thinking')
        ? b.textContent.replace('mostra', 'nascondi')
        : b.textContent.replace('nascondi', 'mostra');
    }
  });

  /* Global ESC closes any expanded row */
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.log-row.expanded').forEach(function(row) { row.classList.remove('expanded'); });
    }
  });

  window.HirisLogRow = { render: render, midTruncate: midTruncate };
})();
