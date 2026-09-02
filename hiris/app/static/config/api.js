/* HIRIS - utilita' condivise dalle due pagine (chat e configurazione).
   Carica per prima: definisce globali bare, non un modulo. */

// global bare (nessun modulo): chiamata da chat/messages.js::formatContent(), non da
// questo file. Verificato con grep sull'intero repo (task-13); il contratto e' pinnato
// da tests/test_chat_page.py.
// eslint-disable-next-line no-unused-vars -- vedi commento sopra
function esc(t) {
  return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* Le tre funzioni qui sotto sono LA grammatica dei numeri di HIRIS, per tutte
   e due le superfici. Prima ce n'erano due copie divergenti: il riquadro
   «Utilizzo» della chat scriveva `1.28M` e `€3.2149`, la pagina «Consumi»
   scriveva gli stessi identici dati come `1.3M` e `€ 3.21`, e le date come
   `da 2026-08-01` mentre tutto il resto del prodotto scrive `11/08/2026`. Chi
   guardava le due schermate una dopo l'altra aveva ragione di credere che una
   delle due stesse sbagliando. Un solo posto, quattro decimali mai: un costo
   si legge a due. */
function fmtNum(n) {
  if (n == null) return '—';
  return n >= 1000000 ? (n/1000000).toFixed(2) + 'M'
       : n >= 1000    ? (n/1000).toFixed(1) + 'k'
       : String(n);
}

/* `decimali` e' il MASSIMO, non il fisso: due bastano a un totale, e una riga
   di modello ne vuole fino a quattro.

   Prima faceva `'€ ' + Number(n).toFixed(2)`, e sbagliava due volte.
   `toFixed(2)` scriveva «0.00» per un modello costato tre decimillesimi di
   euro: dopo aver tolto dai DATI lo zero che afferma (fetta «i consumi, per
   modello»), riaverlo a schermo sarebbe la stessa bugia con un'altra
   provenienza. E `toFixed` non conosce la lingua, quindi produceva il
   separatore col punto in una pagina dove la data accanto e' formattata
   `it-IT` -- difetto preesistente, trovato dall'audit di disegno.

   La funzione e' CONDIVISA col riquadro della chat: sistemarla la sistema in
   tutti e due i posti, che e' il punto di averla qui. */
function fmtEuro(n, decimals) {
  if (n == null) return '—';
  var max = decimals == null ? 2 : decimals;
  return '€ ' + Number(n).toLocaleString('it-IT',
    { minimumFractionDigits: 2, maximumFractionDigits: max });
}

/* Data e ora nel formato italiano, l'unico che il prodotto usa a schermo.
   Restituisce stringa vuota su un valore assente o illeggibile, cosi' chi
   chiama puo' decidere se scrivere un trattino o niente -- e non finisce mai
   con un `Invalid Date` stampato addosso all'utente. */
function fmtDateTime(v) {
  if (!v) return '';
  var d = new Date(v);
  return isNaN(d.getTime()) ? '' : d.toLocaleString('it-IT');
}

/* Theme: localStorage > server config > system. */
// global bare (nessun modulo): chiamata da chat/theme.js::init(), non da questo file.
// Verificato con grep sull'intero repo (task-13); il contratto e' pinnato da
// tests/test_chat_page.py.
// eslint-disable-next-line no-unused-vars -- vedi commento sopra
async function applyTheme() {
  var local = null;
  try { local = localStorage.getItem('hiris-theme'); } catch {}
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
  } catch {}
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
function _showUsageRows(visible) {
  var widget = document.getElementById('usage-widget');
  if (!widget) return;
  var rows = widget.querySelectorAll('.usage-row');
  for (var i = 0; i < rows.length; i++) {
    rows[i].style.display = visible ? '' : 'none';
  }
}

/* Restituisce `false` quando il server ha DICHIARATO che su questa
   configurazione i consumi non si misurano (GET api/usage -> 200 con
   `measured: false`, vedi api/handlers_usage.py): e' un fatto della
   configurazione, non un guasto passeggero, e non cambia senza un riavvio
   dell'add-on. Chi chiama a intervalli usa questo `false` per SMETTERE di
   chiamare -- prima il riquadro della chat ripeteva la stessa domanda ogni
   30 secondi e ogni volta si prendeva un 503 e un console.error, senza mai
   dire niente all'utente. In ogni altro caso (numeri veri, errore HTTP,
   rete caduta) restituisce `true`: quelli si' che possono cambiare al giro
   dopo. */
// global bare (nessun modulo): chiamata da chat/main.js::aggiornaConsumi(), non da
// questo file. Verificato con grep sull'intero repo (task-13); il contratto e' pinnato
// da tests/test_chat_page.py.
// eslint-disable-next-line no-unused-vars -- vedi commento sopra
async function loadUsage() {
  try {
    var r = await fetch('api/usage');
    if (!r.ok) { console.error('loadUsage failed', r.status); return true; }
    var d = await r.json();
    if (d.measured === false) {
      _showUsageRows(false);
      _setUsageText('usage-last-reset', d.message || 'I consumi non si misurano su questa configurazione.');
      return false;
    }
    _showUsageRows(true);
    _setUsageText('u-requests', d.total_requests != null ? d.total_requests : '—');
    _setUsageText('u-input', fmtNum(d.input_tokens));
    _setUsageText('u-output', fmtNum(d.output_tokens));
    _setUsageText('u-cost', fmtEuro(d.cost_eur));
    var when = fmtDateTime(d.last_reset);
    /* «Conta da», non «Azzerato il»: dalla fetta «i consumi, per modello»
       il pulsante sposta un'ancora e non cancella piu' niente, e `last_reset`
       porta l'istante di quell'ancora. Dire «azzerato» descriverebbe un gesto
       che il prodotto non compie piu'. */
    if (when) _setUsageText('usage-last-reset', 'Conta da ' + when);
    return true;
  } catch(e) {
    console.error('loadUsage failed', e);
    return true;
  }
}
