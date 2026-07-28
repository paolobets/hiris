/* HIRIS · Designer · api + helpers
   Tiny utilities + fetch wrappers used across modules. Loads first. */

function esc(t) {
  return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtNum(n) {
  if (n == null) return '—';
  return n >= 1000000 ? (n/1000000).toFixed(2) + 'M'
       : n >= 1000    ? (n/1000).toFixed(1) + 'k'
       : String(n);
}

function estimateTok(text) { return Math.ceil((text || '').length / 4); }

function fmtTok(n) {
  if (n === 0) return '—';
  return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
}

/* Theme: localStorage > server config > system. */
async function applyTheme() {
  var local = null;
  try { local = localStorage.getItem('hiris-theme'); } catch(e) {}
  if (local === 'light' || local === 'dark') {
    document.documentElement.setAttribute('data-theme', local);
    return;
  }
  try {
    var r = await fetch('api/config');
    var cfg = await r.json();
    var theme = cfg.theme || 'auto';
    if (theme === 'light' || theme === 'dark') {
      document.documentElement.setAttribute('data-theme', theme);
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  } catch(e) {}
}

/* loadModels()/_setModelValue() spostate in config/editor-kit.js
   (HirisEditorKit.modelSelect / HirisEditorKit.setModelValue) — SP-4 Fase B
   Task 3: erano codice editor (popolano #f-model) dentro un file di utility
   pure, e ogni chiamante (agentbot-route.js) ne rifaceva una fetch propria
   per riga invece di condividerla. Vedi editor-kit.js per la cache
   condivisa. */

async function loadUsage() {
  try {
    var r = await fetch('api/usage');
    if (!r.ok) return;
    var d = await r.json();
    document.getElementById('u-requests').textContent = d.total_requests != null ? d.total_requests : '—';
    document.getElementById('u-input').textContent = fmtNum(d.input_tokens);
    document.getElementById('u-output').textContent = fmtNum(d.output_tokens);
    document.getElementById('u-cost').textContent = d.cost_eur != null ? '€' + d.cost_eur.toFixed(4) : '—';
    if (d.last_reset) {
      var dt = new Date(d.last_reset);
      document.getElementById('usage-last-reset').textContent = 'Azzerato il ' + dt.toLocaleString('it-IT');
    }
  } catch(e) {}
}
