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

function _setModelValue(val) {
  var sel = document.getElementById('f-model');
  sel.value = val;
  if (sel.value !== val) {
    /* Model not in list (provider not configured) — add as orphan option */
    var opt = document.createElement('option');
    opt.value = val;
    opt.textContent = val + ' (provider non configurato)';
    sel.insertBefore(opt, sel.firstChild);
    sel.value = val;
  }
}

async function loadModels() {
  var sel = document.getElementById('f-model');
  try {
    var r = await fetch('api/models');
    if (!r.ok) return;
    var d = await r.json();
    var providers = d.providers || [];
    var current = sel.value;
    sel.innerHTML = '';
    providers.forEach(function(p) {
      var grp = document.createElement('optgroup');
      grp.label = p.label;
      p.models.forEach(function(m) {
        var opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m === 'auto' ? 'auto — segue tipo agente' : m;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    });
    if (providers.length === 0) {
      var opt = document.createElement('option');
      opt.value = 'auto';
      opt.textContent = 'auto — nessun provider configurato';
      sel.appendChild(opt);
    }
    _setModelValue(current || 'auto');
    var hint = document.getElementById('model-hint');
    if (hint && providers.length > 0) {
      hint.textContent = 'Seleziona il modello AI. Sono disponibili '
        + providers.map(function(p){return p.label;}).join(', ')
        + '. «auto» sceglie in base al tipo agente.';
    }
  } catch(e) {
    console.warn('loadModels failed:', e);
  }
}

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
