/* HIRIS - utilita' condivise dalle due pagine (chat e configurazione).
   Carica per prima: definisce globali bare, non un modulo. */

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

/* Scrive il testo in `id` solo se l'elemento esiste in questa pagina.
   Correzione (I-3, review indipendente): il commento precedente diceva che
   l'id mancante (usage-last-reset, mai aggiunto a index.html) impediva ai
   QUATTRO contatori di popolarsi -- falso, verificato sul codice prima di
   questa correzione: usage-last-reset era l'ULTIMO dei cinque assegnamenti
   in loadUsage(), quindi i quattro contatori (u-requests/u-input/u-output/
   u-cost) giravano gia' regolarmente; solo il quinto (la data di azzeramento)
   sollevava, e il catch(e) vuoto lo inghiottiva in silenzio, senza mai
   loggare. _setUsageText() resta comunque un irrobustimento genuino: rende
   ogni assegnamento indipendente dagli altri (non solo dall'ultimo) per
   qualunque futuro id mancante, e il catch finale ora logga (vedi sotto). */
function _setUsageText(id, text) {
  var el = document.getElementById(id);
  if (el) el.textContent = text;
}

async function loadUsage() {
  try {
    var r = await fetch('api/usage');
    if (!r.ok) { console.error('loadUsage failed', r.status); return; }
    var d = await r.json();
    _setUsageText('u-requests', d.total_requests != null ? d.total_requests : '—');
    _setUsageText('u-input', fmtNum(d.input_tokens));
    _setUsageText('u-output', fmtNum(d.output_tokens));
    _setUsageText('u-cost', d.cost_eur != null ? '€' + d.cost_eur.toFixed(4) : '—');
    if (d.last_reset) {
      var dt = new Date(d.last_reset);
      _setUsageText('usage-last-reset', 'Azzerato il ' + dt.toLocaleString('it-IT'));
    }
  } catch(e) {
    console.error('loadUsage failed', e);
  }
}
