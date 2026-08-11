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

/* Mostra/nasconde le quattro righe di numeri del riquadro "Utilizzo".
   Quando la misura non esiste, quattro trattini accanto a "Richieste" e
   "Costo" si leggono come "sto caricando": le righe escono di scena e resta
   la frase che dice perche'. Guardata sull'esistenza: la pagina di
   configurazione non ha questo riquadro. */
function _mostraRigheConsumi(visibili) {
  var widget = document.getElementById('usage-widget');
  if (!widget) return;
  var righe = widget.querySelectorAll('.usage-row');
  for (var i = 0; i < righe.length; i++) {
    righe[i].style.display = visibili ? '' : 'none';
  }
}

/* Restituisce `false` quando il server ha DICHIARATO che su questa
   configurazione i consumi non si misurano (GET api/usage -> 200 con
   `misurata: false`, vedi api/handlers_usage.py): e' un fatto della
   configurazione, non un guasto passeggero, e non cambia senza un riavvio
   dell'add-on. Chi chiama a intervalli usa questo `false` per SMETTERE di
   chiamare -- prima il riquadro della chat ripeteva la stessa domanda ogni
   30 secondi e ogni volta si prendeva un 503 e un console.error, senza mai
   dire niente all'utente. In ogni altro caso (numeri veri, errore HTTP,
   rete caduta) restituisce `true`: quelli si' che possono cambiare al giro
   dopo. */
async function loadUsage() {
  try {
    var r = await fetch('api/usage');
    if (!r.ok) { console.error('loadUsage failed', r.status); return true; }
    var d = await r.json();
    if (d.misurata === false) {
      _mostraRigheConsumi(false);
      _setUsageText('usage-last-reset', d.messaggio || 'I consumi non si misurano su questa configurazione.');
      return false;
    }
    _mostraRigheConsumi(true);
    _setUsageText('u-requests', d.total_requests != null ? d.total_requests : '—');
    _setUsageText('u-input', fmtNum(d.input_tokens));
    _setUsageText('u-output', fmtNum(d.output_tokens));
    _setUsageText('u-cost', d.cost_eur != null ? '€' + d.cost_eur.toFixed(4) : '—');
    if (d.last_reset) {
      var dt = new Date(d.last_reset);
      _setUsageText('usage-last-reset', 'Azzerato il ' + dt.toLocaleString('it-IT'));
    }
    return true;
  } catch(e) {
    console.error('loadUsage failed', e);
    return true;
  }
}
