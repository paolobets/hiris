/* HIRIS · Designer · execution log + token counter + context preview */

function renderExecutionLog(a) {
  var body = document.getElementById('log-body');
  if (!body) return;
  var log = (a && a.execution_log) || [];
  if (log.length === 0) {
    body.innerHTML = '<div class="log-empty">Nessuna esecuzione registrata.</div>';
    return;
  }
  var rows = log.slice().reverse().map(function(r) {
    var t = r.timestamp ? new Date(r.timestamp) : null;
    var timeStr = t ? t.toLocaleString('it-IT', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '—';
    var statusCls = r.success ? 'log-success' : 'log-error';
    var statusTxt = r.success ? '✓ ok' : '✗ err';
    var tools = (r.tool_calls || []).join(', ');
    var summary = r.result_summary || '';
    var titleAttr = esc(summary) + (tools ? (' — tools: ' + esc(tools)) : '');
    var tokens = (r.input_tokens || 0) + '↓ / ' + (r.output_tokens || 0) + '↑';
    var rowId = 'lr-' + Math.random().toString(36).slice(2, 9);
    var isLong = summary.length > 120;
    var preview = isLong ? summary.slice(0, 120) + '…' : summary;
    var EVAL_CLASS = { 'OK': 'eval-ok', 'ATTENZIONE': 'eval-warn', 'ANOMALIA': 'eval-alert' };
    var evalStatus = r.eval_status || null;
    var evalBadge = evalStatus
      ? '<span class="eval-badge ' + (EVAL_CLASS[evalStatus] || '') + '">' + esc(evalStatus) + '</span>'
      : '';
    var actionLine = r.action_taken
      ? '<div class="log-action-taken">↳ ' + esc(r.action_taken) + '</div>'
      : '';
    var thinkingBlocks = (r.thinking_blocks && r.thinking_blocks.length) ? r.thinking_blocks : null;
    var thinkingBtn = thinkingBlocks
      ? '<button class="log-thinking-btn" data-row-id="' + esc(rowId) + '" title="Mostra/nasconde il chain-of-thought">💭 thinking</button>'
      : '';
    var thinkingPanel = thinkingBlocks
      ? '<pre class="log-thinking-panel" style="display:none">' +
          thinkingBlocks.map(function(tb, i) {
            return '— step ' + (i + 1) + ' —\n' + esc(tb);
          }).join('\n\n') +
        '</pre>'
      : '';
    var summaryHtml = evalBadge +
      '<span class="log-preview">' + esc(preview || tools || '—') + '</span>' +
      (isLong ? '<span class="log-full" style="display:none">' + esc(summary) + '</span>' +
        '<button class="log-expand-btn" data-row-id="' + esc(rowId) + '">▼ espandi</button>' : '') +
      thinkingBtn +
      actionLine +
      thinkingPanel;
    return '<li id="' + rowId + '">' +
      '<span class="log-time">' + esc(timeStr) + '</span>' +
      '<span class="' + statusCls + '">' + statusTxt + '</span>' +
      '<span class="log-summary" title="' + titleAttr + '">' + summaryHtml + '</span>' +
      '<span class="log-tokens">' + esc(tokens) + '</span>' +
    '</li>';
  }).join('');
  body.innerHTML = '<ul class="log-list">' + rows + '</ul>';
}

function toggleLogRow(rowId) {
  var row = document.getElementById(rowId);
  if (!row) return;
  var preview = row.querySelector('.log-preview');
  var full = row.querySelector('.log-full');
  var btn = row.querySelector('.log-expand-btn');
  var expanded = full && full.style.display !== 'none';
  if (preview) preview.style.display = expanded ? '' : 'none';
  if (full) full.style.display = expanded ? 'none' : 'block';
  if (btn) btn.textContent = expanded ? '▼ espandi' : '▲ comprimi';
  row.classList.toggle('expanded', !expanded);
}

document.getElementById('log-body').addEventListener('click', function(e) {
  var btn = e.target.closest('.log-expand-btn');
  if (btn) {
    var rowId = btn.dataset.rowId;
    if (rowId) toggleLogRow(rowId);
    return;
  }
  var thBtn = e.target.closest('.log-thinking-btn');
  if (thBtn) {
    var thRow = document.getElementById(thBtn.dataset.rowId);
    if (!thRow) return;
    var panel = thRow.querySelector('.log-thinking-panel');
    if (!panel) return;
    var open = panel.style.display !== 'none';
    panel.style.display = open ? 'none' : 'block';
    thBtn.classList.toggle('open', !open);
  }
});

/* ── Token counter ─────────────────────────── */
var BASE_TOK = 1800; /* rough estimate of BASE_SYSTEM_PROMPT size in tokens */

function updateTokenCounter() {
  var strategic = document.getElementById('f-strategic').value;
  var prompt    = document.getElementById('f-prompt').value;
  var tStrat  = estimateTok(strategic);
  var tPrompt = estimateTok(prompt);
  var tTotal  = BASE_TOK + tStrat + tPrompt;
  document.getElementById('tc-strategic').textContent = fmtTok(tStrat);
  document.getElementById('tc-prompt').textContent    = fmtTok(tPrompt);
  var totalEl = document.getElementById('tc-total');
  totalEl.textContent = '~' + fmtTok(tTotal);
  totalEl.className = 'token-val' + (tTotal > 6000 ? ' warn' : '');
}

var _ctxPreviewTimer = null;
async function loadContextPreview(agentId) {
  if (!agentId) { document.getElementById('tc-context').textContent = '—'; return; }
  try {
    var r = await fetch('api/agents/' + agentId + '/context-preview');
    if (!r.ok) throw new Error();
    var d = await r.json();
    var ctxEl = document.getElementById('tc-context');
    ctxEl.textContent = d.token_estimate > 0 ? '~' + fmtTok(d.token_estimate) : '—';
    var wrap = document.getElementById('context-preview-wrap');
    var pre  = document.getElementById('context-preview-content');
    if (d.context_str) {
      pre.textContent = d.context_str;
      wrap.style.display = '';
    } else {
      wrap.style.display = 'none';
    }
  } catch(e) {
    document.getElementById('tc-context').textContent = '—';
    document.getElementById('context-preview-wrap').style.display = 'none';
  }
}

document.getElementById('f-strategic').addEventListener('input', updateTokenCounter);
document.getElementById('f-prompt').addEventListener('input', updateTokenCounter);
