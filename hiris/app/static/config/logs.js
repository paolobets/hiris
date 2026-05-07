/* HIRIS · Designer · execution log + token counter + context preview */

function renderExecutionLog(a) {
  var body = document.getElementById('log-body');
  if (!body) return;
  if (window.HirisLogRow) {
    HirisLogRow.render(body, a);
  } else {
    /* Fallback shouldn't happen if log-row.js is loaded; keep minimal no-op */
    body.innerHTML = '<div class="log-empty">log-row.js non caricato</div>';
  }
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
