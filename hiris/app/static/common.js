/* HIRIS - le utilita' del frontend, scritte UNA volta per le due pagine
   (chat e configurazione). Carica per prima, nell'<head> di entrambe: definisce
   globali bare, non un modulo, e al caricamento non tocca la pagina.

   Era `config/api.js`, che gia' faceva da file condiviso ma con un nome che
   non lo diceva; intanto ogni pagina della configurazione si riscriveva
   `el`, `clearEl`, `byId`, `api`, `pad2` -- nove copie di `el`, sei di `api`
   (registro C-20, C-22). Il cancello che impedisce il ritorno delle copie
   chiede i nomi a QUESTO file: tests/js/common.test.mjs. */

/* --------------------------------------------------------------- il DOM */

/* Un elemento con classe e testo. Il testo passa SEMPRE da `textContent`:
   cio' che arriva dal server non diventa mai markup. */
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/* Svuota un nodo e lo restituisce; un nodo assente resta assente. */
function clearEl(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
function byId(id) { return document.getElementById(id); }

/* L'errore di una lettura, nella forma che le pagine usano gia': la frase
   (in `.proposals-error`) e un «Riprova» che rilancia `reload`. Svuota il
   nodo prima di scrivere. La frase la porta chi chiama: dice COSA non si e'
   potuto leggere, ed e' sua. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
function renderError(node, text, reload) {
  clearEl(node);
  node.appendChild(el('p', 'proposals-error', text));
  var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
  retry.type = 'button';
  retry.addEventListener('click', reload);
  node.appendChild(retry);
  return node;
}

/* Lo stato di un rivelatore scritto in un posto solo: `hidden` sul
   pannello e `aria-expanded` sul bottone che lo governa non possono
   divergere se nessuno li assegna separatamente -- ed e' proprio la
   divergenza (il pannello aperto e lo screen reader che lo annuncia chiuso)
   il difetto che questa riga rende impossibile. La usano gli Impegni
   (lo «Storico», «Cosa è cambiato») e le Proposte (lo «Storico», i
   «Dettagli tecnici»): prima ne avevano una copia ciascuno, tenuta fuori di
   qui solo perche' le prove caricavano ogni pagina senza il file comune. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/agenda-route.js e config/constructions-route.js
function setDisclosure(btn, panel, open) {
  panel.hidden = !open;
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

/* ---------------------------------------------------------- il server */

/* L'intestazione anti-CSRF, una sola (registro C-19). `csrf_middleware`
   (api/middleware_csrf.py) risponde 403 a ogni POST/PUT/PATCH/DELETE su /api/
   che non la porta, e accetta qualunque valore non vuoto: prima una pagina
   mandava 'XMLHttpRequest' e le altre 'fetch', due forme dello stesso gesto. */
var CSRF_HEADER = 'X-Requested-With';
var CSRF_VALUE = 'fetch';

/* Ogni chiamata delle pagine che scrive passa da qui: dimenticare
   l'intestazione su una chiamata sola e' il modo esatto in cui una pagina
   smette di salvare senza dire niente. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione e dalla chat
function api(path, opts) {
  opts = opts || {};
  var headers = { 'Content-Type': 'application/json' };
  headers[CSRF_HEADER] = CSRF_VALUE;
  opts.headers = Object.assign(headers, opts.headers || {});
  return fetch(path, opts);
}

/* ------------------------------------------------------------ i formati */

// eslint-disable-next-line no-unused-vars -- global bare, letta dalle due pagine
function pad2(n) { return n < 10 ? '0' + n : String(n); }

/* I registri caduti, in italiano. `non_disponibili` porta il nome grezzo
   della tabella e, per le categorie, l'ambito che ha fallito
   (`categorie:script` -- vedi `ha_client.read_registries`): l'ambito NON si
   butta, e' il dettaglio che dice quale delle quattro chiamate e' caduta.
   La leggono la home e l'albero della casa: prima ne avevano una copia
   ciascuno, «duplicata di proposito». */
var NOMI_REGISTRI = {
  piani: 'Piani', aree: 'Aree', dispositivi: 'Dispositivi', entita: 'Entità',
  etichette: 'Etichette', categorie: 'Categorie', integrazioni: 'Integrazioni'
};

// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function nomiRegistriInItaliano(voci) {
  return voci.map(function (entry) {
    var pezzi = String(entry).split(':');
    var name = NOMI_REGISTRI[pezzi[0]] || pezzi[0];
    var scope = pezzi.slice(1).join(':');
    return scope ? name + ' (ambito «' + scope + '»)' : name;
  });
}

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

/* Collaudo 3.22 (C5): «Richieste 99 · Token input 7.20M · Costo € 0,00»
   senza altra spiegazione -- misurato quando l'UNICO uso e' l'abbonamento
   (`ponte`), che non ha un costo di turno da sommare (vedi
   hiris/app/usage/vocabulary.py::cost_state_and_value, stato "compreso").
   Il totale che il server manda (`cost_eur`) e' 0.0 per costruzione: nessun
   altro addendo. Uno zero misurato e uno zero "non c'e' niente da misurare"
   sono lo stesso zero a schermo, ed e' la stessa confusione a tre stati che
   l'archivio della casa combatte ovunque -- rimessa dentro dalla porta del
   riquadro Utilizzo.

   Niente di nuovo da inventare: `sections[].provider` arriva gia' in ogni
   risposta di `/api/usage` (handlers_usage.py), e la sezione dell'abbonamento
   ha gia' il proprio nome, "ponte". Condivisa fra il riquadro della chat e
   la pagina Consumi -- le DUE superfici che leggono lo stesso `cost_eur`,
   per la stessa ragione per cui fmtEuro/fmtNum vivono qui e non in due
   copie (vedi il commento sopra fmtNum). */
function isSubscriptionOnly(sections) {
  return !!(sections && sections.length
    && sections.every(function(s) { return s.provider === 'ponte'; }));
}

/* La parola che sostituisce «€ 0,00» quando `isSubscriptionOnly()` e' vera.
   NON un trattino: la pagina Consumi ha una regola esplicita contro di esso
   proprio per il costo ("MAI UN TRATTINO PER UN COSTO", config/usage-route.js)
   -- su quella pagina il trattino significa gia' "sto caricando", e uno
   stesso simbolo per due fatti diversi sarebbe l'errore che questa fetta
   toglie, spostato di un carattere. */
var SUBSCRIPTION_ONLY_COST_LABEL = 'In abbonamento';

/* Chi guarda configura? Una regola sola, chiusa nel dubbio (spec
   2026-09-27 §4): decide `HirisPendingBadge.configures()` -- il `true` del
   server o del ricordo -- e senza il pallino (script non caricato) no. Qui
   e non in ogni pagina: prima il guscio (config/main.js) e la Memoria
   (config/memory-route.js) ne avevano una copia ciascuno, e una regola di
   riservatezza scritta due volte e' un doppione che puo' divergere. */
// eslint-disable-next-line no-unused-vars -- letta da config/main.js e config/memory-route.js
function configures() {
  return !!(window.HirisPendingBadge && window.HirisPendingBadge.configures());
}

/* ------------------------------------------------------------- il tema

   Letto e scritto QUI, per tutte e due le pagine (registro C-16). La regola:
   la scelta di chi guarda (il bottone, ricordato nel browser) > il tema del
   server (opzione `theme` dell'add-on) > quello del sistema.

   Prima la chiave stava scritta in cinque posti, e la configurazione non
   chiedeva mai il tema al server: l'opzione dell'add-on valeva per la chat
   sola. In piu' la configurazione salvava nel browser il tema che trovava
   all'avvio -- quindi bastava aprirla una volta perche' da li' in poi
   nemmeno la chat guardasse piu' il server. Adesso nel browser si scrive
   solo al clic del bottone. */
var THEME_KEY = 'hiris-theme';

/* Il tema che chi guarda ha scelto col bottone, o `null`. */
function savedTheme() {
  try {
    var t = localStorage.getItem(THEME_KEY);
    return (t === 'light' || t === 'dark') ? t : null;
  } catch { return null; }
}

/* Il bootstrap in linea dell'<head> delle due pagine: solo la scelta
   salvata, prima del primo disegno, perche' e' l'unica che non chiede la
   rete. Il resto lo fa `applyTheme()` quando la pagina parte. */
// eslint-disable-next-line no-unused-vars -- chiamata dal <script> in linea di index.html e config.html
function paintSavedTheme() {
  var t = savedTheme();
  if (t) document.documentElement.setAttribute('data-theme', t);
}

// global bare (nessun modulo): chiamata da chat/theme.js::init() e da
// config/main.js::mountChrome(), non da questo file.
// eslint-disable-next-line no-unused-vars -- vedi commento sopra
async function applyTheme() {
  var local = savedTheme();
  if (local) {
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

/* Il tema che la pagina mostra adesso: quello dichiarato, o quello del
   sistema quando nessuno l'ha dichiarato. */
function currentTheme() {
  var t = document.documentElement.getAttribute('data-theme');
  if (t === 'light' || t === 'dark') return t;
  return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
    ? 'dark' : 'light';
}

/* Il clic sul bottone del tema: l'opposto di quello mostrato, ricordato nel
   browser. Restituisce il tema nuovo; disegnare l'icona resta alla pagina,
   perche' le due pagine hanno icone fatte in modo diverso. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da chat/theme.js e config/main.js
function toggleTheme() {
  var next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(THEME_KEY, next); } catch {}
  return next;
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
    _setUsageText('u-cost', isSubscriptionOnly(d.sections) ? SUBSCRIPTION_ONLY_COST_LABEL : fmtEuro(d.cost_eur));
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
