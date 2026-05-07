/* HIRIS · Designer · execution log + token counter + context preview
   v0.10.5 cleanup: rimossi toggleLogRow + click delegate su #log-body
   (gestiti markup legacy .log-preview/.log-full/.log-expand-btn che non
   esistono in v6 — HirisLogRow.render in log-row.js produce il markup
   v6 .log-row/.lr-collapsed/.lr-detail con il proprio click handler).
   IIFE listeners su #f-strategic/#f-prompt rimossi: ora gestiti da
   rewireLegacyAfterMount in agent-editor.js (rebind ad ogni mount). */

function renderExecutionLog(a) {
  var body = document.getElementById('log-body');
  if (!body) return;
  if (window.HirisLogRow) {
    HirisLogRow.render(body, a);
  } else {
    body.innerHTML = '<div class="log-empty">log-row.js non caricato</div>';
  }
}

/* ── Token counter ─────────────────────────── */
var BASE_TOK = 1800; /* rough estimate of BASE_SYSTEM_PROMPT size in tokens */

function updateTokenCounter() {
  var strategic = document.getElementById('f-strategic');
  var prompt    = document.getElementById('f-prompt');
  if (!strategic || !prompt) return;
  var tStrat  = estimateTok(strategic.value);
  var tPrompt = estimateTok(prompt.value);
  var tTotal  = BASE_TOK + tStrat + tPrompt;
  var tcStrat = document.getElementById('tc-strategic');
  var tcPrompt = document.getElementById('tc-prompt');
  if (tcStrat) tcStrat.textContent = fmtTok(tStrat);
  if (tcPrompt) tcPrompt.textContent = fmtTok(tPrompt);
  var totalEl = document.getElementById('tc-total');
  if (totalEl) {
    totalEl.textContent = '~' + fmtTok(tTotal);
    totalEl.className = 'token-val' + (tTotal > 6000 ? ' warn' : '');
  }
}

async function loadContextPreview(agentId) {
  var ctxEl = document.getElementById('tc-context');
  var wrap  = document.getElementById('context-preview-wrap');
  var pre   = document.getElementById('context-preview-content');
  if (!agentId) { if (ctxEl) ctxEl.textContent = '—'; return; }
  try {
    var r = await fetch('api/agents/' + agentId + '/context-preview');
    if (!r.ok) throw new Error();
    var d = await r.json();
    if (ctxEl) ctxEl.textContent = d.token_estimate > 0 ? '~' + fmtTok(d.token_estimate) : '—';
    if (d.context_str && wrap && pre) {
      pre.textContent = d.context_str;
      wrap.style.display = '';
    } else if (wrap) {
      wrap.style.display = 'none';
    }
  } catch(e) {
    if (ctxEl) ctxEl.textContent = '—';
    if (wrap) wrap.style.display = 'none';
  }
}
