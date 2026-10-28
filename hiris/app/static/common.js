/* HIRIS - le utilita' del frontend, scritte UNA volta per le due pagine
   (chat e configurazione). Carica per prima, nell'<head> di entrambe: definisce
   globali bare, non un modulo, e al caricamento non tocca la pagina.

   Era `config/api.js`, che gia' faceva da file condiviso ma con un nome che
   non lo diceva; intanto ogni pagina della configurazione si riscriveva
   `el`, `clearEl`, `byId`, `api`, `pad2` -- nove copie di `el`, sei di `api`
   (registro C-20, C-22). Il cancello che impedisce il ritorno delle copie
   chiede i nomi a QUESTO file: tests/js/common.test.mjs. */

/* ------------------------------------------------------------- l'attesa */

/* Le durate e le frasi dell'attesa di un turno, scritte UNA volta per le due
   porte che lo aspettano: la chat (chat/messages.js) e il «Rifalla» della
   pagina Proposte (config/constructions-route.js; attori, Task 4.4). Fino al
   06/10/2026 vivevano solo nella chat: la seconda porta le avrebbe ricopiate,
   e le due attese avrebbero cominciato a dire cose diverse.

   Le prime tre -- quelle che l'utente vive come attesa -- sono calibrate
   sulla letteratura (i 10 secondi oltre i quali l'attenzione si stacca) e NON
   su tempi di risposta misurati su questo prodotto: nessuno li ha ancora
   raccolti. Le altre hanno una provenienza diversa, dichiarata accanto. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle due pagine
var SOGLIE_ATTESA = {
  /* ogni quanto la pagina richiede notizie di un turno del ponte */
  rilettura: 3500,
  /* compare il cronometro */
  timer: 10000,
  /* l'etichetta ammette che ci sta mettendo troppo */
  lenta: 30000,
  /* compare la riga che dice che fine fa il turno */
  servizio: 120000,
  /* Quanto PRIMA della scadenza avvisare che sta per arrendersi. La scadenza
     non e' scritta qui: la porta chi ce l'ha davvero (la chat dal suo poll,
     il «Rifalla» dalla coda del server). */
  margineResa: 30000,
  /* E quando dirlo dove una scadenza non esiste proprio. Questo numero e'
     arbitrario e lo dichiara: non c'e' niente da cui derivarlo. */
  senzaScadenza: 270000,
  /* Quanto la bolla della chat resta una regione live DOPO che ci e' stata
     scritta dentro la risposta (chat/messages.js, updateBubble): l'ultimo
     atto della stessa vita, l'indicatore che diventa risposta. */
  uscitaRegioneLive: 1200
};

/* Le frasi che non dipendono da COSA si aspetta. Quelle che lo nominano --
   «questa risposta», «questo rifacimento» -- stanno con la loro porta. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle due pagine
var FRASI_ATTESA = {
  lenta: 'Ci sto mettendo più del solito',
  quasiResa: 'Ancora niente: fra poco smetto di aspettare',
  senzaScadenza: 'Ancora niente. Continuo ad aspettare: su questo turno non ho un tempo massimo.'
};

/* Il cronometro dell'attesa, `m:ss`. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle due pagine
function stopwatchText(ms) {
  var s = Math.floor(Math.max(0, ms) / 1000);
  var ss = s % 60;
  return Math.floor(s / 60) + ':' + (ss < 10 ? '0' + ss : ss);
}

/* --------------------------------------------------------------- il DOM */

/* Un elemento con classe e testo. Il testo passa SEMPRE da `textContent`:
   cio' che arriva dal server non diventa mai markup. */
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/* La frase di uno stato messa in testa a un'etichetta: la prima lettera
   maiuscola, il resto com'e'. La frase arriva dalla rotta
   (`stato_leggibile`, dal vocabolario `hiris/app/states.py`, C-10 della
   Tappa 8), minuscola perche' il server la mette anche in mezzo a una
   frase; le pagine non tengono una tabella loro delle parole. Se la frase
   manca e arriva la parola grezza dell'archivio, il trattino basso diventa
   uno spazio: «In corso», non «In_corso» (ux-ui-specialist, 08/10/2026). */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/agenda-route.js e config/constructions-route.js
function stateLabel(phrase) {
  var text = phrase == null ? '' : String(phrase).replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/* Lo stato di un'entita' da scrivere accanto al nome (una riga `corta` di
   `render_entity`, la stessa forma da ogni porta). Fino al 28/10/2026 viveva
   in config/tree-route.js; dalla Fase B lo legge anche la riga «Adesso» del
   Brain, quindi sta qui, una volta sola: le parole di Home Assistant
   (`stato_leggibile`) quando ci sono, altrimenti il valore grezzo con la
   sua unita'. Le parole di `unavailable`/`unknown` non arrivano dal comando
   che HIRIS legge (`frontend/get_translations`, vedi
   `proxy/state_translations.state_translation`): Home Assistant le tiene
   nel pacchetto di traduzioni del suo frontend (misurato dallo Sprint
   l'11/10/2026). Restano grezze, come nella chat. Senza stato non si
   scrive niente. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/tree-route.js e config/watcher-cosa-fare.js
function entityStateText(e) {
  if (e.stato_leggibile) return e.stato_leggibile;
  if (e.stato == null) return '';
  return e.unita ? e.stato + ' ' + e.unita : String(e.stato);
}

/* Una frase chiusa da un punto, **senza raddoppiarlo**: un testo che arriva
   dalla rotta (scritto dal modello) puo' finire gia' col suo punto, e
   aggiungerne un altro scriveva «..» sulla pagina del Brain (fotografia della
   Fase L, 22/10/2026). Un testo vuoto resta vuoto. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/watcher-cosa-fare.js
function closeSentence(text) {
  var t = text == null ? '' : String(text).trim();
  if (!t) return '';
  return /[.!?…]$/.test(t) ? t : t + '.';
}

/* Il colore del badge di uno stato, uno per tutte le code (promesse,
   costruzioni): le parole sono del vocabolario unico (`hiris/app/states.py`),
   e lo stesso stato ha la stessa faccia in ogni pagina. Fino all'08/10/2026
   ogni pagina ne teneva una mappa sua (ux-ui-specialist, 08/10/2026).
   in_attesa e disdetta neutri (il «no» di una persona non e' un guasto);
   in_corso, mantenuta e applicata accesi; fallita rosso; saltata, scaduta e
   incerta ambra (tempo passato o esito non saputo, non un fallimento). Uno
   stato che la mappa non conosce e' neutro. */
var STATE_BADGE = {
  in_attesa: 'badge-off',
  in_corso: 'badge-on',
  mantenuta: 'badge-on',
  applicata: 'badge-on',
  disdetta: 'badge-off',
  fallita: 'badge-err',
  saltata: 'badge-warn',
  scaduta: 'badge-warn',
  incerta: 'badge-warn'
};

// eslint-disable-next-line no-unused-vars -- global bare, letta da config/agenda-route.js e config/constructions-route.js
function stateBadge(state) {
  return STATE_BADGE[state] || 'badge-off';
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

/* I mattoni delle pagine che leggono e mostrano (la home, l'albero, le schede
   dell'osservatore). Ne avevano una copia ciascuna (C-20).

   I toni sono quelli del TESTO, non dei pallini: le tinte `*-ink`, perche'
   `--warn`/`--err` sul tema chiaro stanno a 2.04:1 e 4.05:1, e qui colorano
   la frase con cui HIRIS dice «questo non l'ho letto», cioe' la frase per cui
   queste pagine esistono. Tre stati e non due: «non si puo' sapere» non e' ne'
   un'assenza vera (calmo) ne' un guasto (problema), come un `null` non e' un
   `[]`. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
var TONE_UNKNOWN = 'color:var(--warn-ink)';
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
var TONE_PROBLEM = 'color:var(--err-ink)';
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
var TONE_CALM = 'color:var(--text-3)';

// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine della configurazione
function pageLine(parent, text, style) {
  var p = el('p', 'sc-desc', text);
  if (style) p.style.cssText = style;
  parent.appendChild(p);
  return p;
}

// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function pageList(parent, voci) {
  var ul = el('ul');
  ul.style.cssText = 'margin:4px 0 0;padding-left:20px;color:var(--text-2);font-size:var(--fs-13)';
  voci.forEach(function (v) { ul.appendChild(el('li', null, v)); });
  parent.appendChild(ul);
  return ul;
}

/* Una sezione con titolo e sottotitolo; restituisce il corpo. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function pageSection(outlet, title, subtitle) {
  var card = el('section', 'section-card');
  var head = el('div', 'sc-header');
  head.appendChild(el('h2', 'sc-title', title));
  if (subtitle) head.appendChild(el('div', 'sc-desc', subtitle));
  card.appendChild(head);
  var body = el('div', 'sc-body');
  card.appendChild(body);
  outlet.appendChild(card);
  return body;
}

/* La lettura che si rompe su una risposta non riuscita: chi chiama la prende
   nel `catch` e dice cosa non ha potuto leggere. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function readJson(path) {
  return fetch(path).then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}

/* Un errore di rete NON degrada in una pagina vuota: la sezione dice che non
   ha potuto leggere, e la console porta il dettaglio tecnico. Una pagina che
   tace su una fetch caduta e' indistinguibile da una casa senza niente dentro.
   Diversa da `renderError` di proposito: qui non c'e' un «Riprova» dentro
   un nodo che c'e' gia', c'e' una sezione intera al posto di quella che non
   e' arrivata. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function renderSectionError(outlet, title, text, err) {
  console.error('[' + title + '] lettura fallita', err);
  var body = pageSection(outlet, title, null);
  pageLine(body, text, TONE_PROBLEM);
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
   Le parole dei registri le manda il server (`nomi_registri` di
   `GET /api/home-space`, C-10): qui non se ne tiene una copia, e un registro
   che la mappa non conosce si legge col suo nome grezzo. La leggono la home
   e l'albero della casa. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da config/dashboard.js e config/tree-route.js
function nomiRegistriInItaliano(voci, nomi) {
  return voci.map(function (entry) {
    var pezzi = String(entry).split(':');
    var name = (nomi && nomi[pezzi[0]]) || pezzi[0];
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

/* ------------------------------------------------------ l'ora della casa */

/* C-17 (Tappa 4, Task 4, passi 4-6). Il server manda ogni istante in ISO con
   l'offset della CASA (`historian.instant_out`, decisione D3 del 05/10/2026),
   e la pagina **non converte**: mostra le cifre della stringa. Fino al
   14/10/2026 ogni pagina passava da `new Date(...)`, cioe' dal fuso del
   BROWSER: Paolo in viaggio a New York leggeva le 08:30 di un'automazione
   partita alle 14:30 a casa sua, e le pagine avevano sei funzioni di formato
   diverse (`fmtDateTime` qui, `fmtTime`/`fmtWhenFull`/`fmtDateOnly`/
   `fmtDayMonth` dell'osservatore, `fmtAbsolute` degli Impegni, `fmtData`
   delle Costruzioni, `fmtWhen` dei Ricordi, i due orari della chat). Ne resta
   una famiglia, qui.

   La forma (parere di `ux-ui-specialist`, 14/10/2026,
   `chiusura/c17-ux.md`): 24 ore, senza secondi; «oggi alle 14:30» e «ieri
   alle 14:30» quando «oggi» lo dice il server; altrimenti «12/10, 14:30», con
   l'anno solo se diverso da quello DELLA CASA («12/10/2025, 14:30").

   `clock` e' `orologio` della risposta (`historian.house_clock`):
   `{fuso, adesso}`, e le cifre di `adesso` sono «oggi» nel fuso della casa.
   Una risposta senza orologio non sa che giorno e' oggi: l'istante esce
   intero, con l'anno, e non mente. */
var INSTANT_DIGITS = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;

/* Le cifre di un istante, senza convertirle. `null` per tutto cio' che non e'
   un ISO con l'offset: un epoch, un testo senza fuso, un `null`. */
function instantDigits(iso) {
  var m = INSTANT_DIGITS.exec(typeof iso === 'string' ? iso : '');
  if (!m) return null;
  return { year: m[1], month: m[2], day: m[3], hour: m[4] + ':' + m[5],
           date: m[1] + '-' + m[2] + '-' + m[3], offset: m[6] };
}

/* Il giorno prima di un giorno `AAAA-MM-GG`: calendario puro, in UTC per non
   incontrare il cambio d'ora del browser. Nessun fuso entra nel conto. */
function dayBefore(date) {
  var p = date.split('-');
  return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] - 1)).toISOString().slice(0, 10);
}

/* «14:30». */
// eslint-disable-next-line no-unused-vars -- global bare, letta dalle pagine dell'osservatore e dalla chat
function fmtHour(iso) {
  var d = instantDigits(iso);
  return d ? d.hour : '';
}

/* Solo la data: «12/10/2026» con `withYear`, «12/10» senza. Le due forme
   approvate dell'osservatore (punto 4: «Corretto da Paolo il gg/mm/aaaa»,
   «Modificata a mano il gg/mm») e la data delle Costruzioni. */
// eslint-disable-next-line no-unused-vars -- global bare, letta dall'osservatore e dalle Costruzioni
function fmtDay(iso, withYear) {
  var d = instantDigits(iso);
  if (!d) return '';
  return d.day + '/' + d.month + (withYear ? '/' + d.year : '');
}

/* L'istante intero. `article` accorda la frase che lo precede, e davanti a
   «oggi» e «ieri» l'articolo cade: `'il'` («Letta il 12/10, 14:30» / «Letta
   oggi alle 14:30»), `'del'` («la copia del 12/10, 14:30» / «la copia di oggi
   alle 14:30»), `'dal'` («Conta dal 12/10, 14:30» / «Conta da ieri alle
   14:30»); nessuno per l'istante nudo. Stringa vuota su un valore assente o
   illeggibile: chi chiama decide se scrivere un trattino o niente, e non
   compare mai `Invalid Date`. */
var ARTICLE_BEFORE_TODAY = { il: '', del: 'di ', dal: 'da ' };

/* «oggi» o «ieri» della casa per un istante, o '' per ogni altro giorno e
   senza orologio: le cifre di `clock.adesso` SONO oggi (C-17). La sola
   regola del prodotto per dire «oggi» e «ieri» di un istante. */
function houseDayName(iso, clock) {
  var d = instantDigits(iso);
  var now = instantDigits(clock && clock.adesso);
  if (!d || !now) return '';
  if (d.date === now.date) return 'oggi';
  return d.date === dayBefore(now.date) ? 'ieri' : '';
}

function fmtInstant(iso, clock, article) {
  var d = instantDigits(iso);
  if (!d) return '';
  var name = houseDayName(iso, clock);
  if (name) return (article ? ARTICLE_BEFORE_TODAY[article] : '') + name + ' alle ' + d.hour;
  var now = instantDigits(clock && clock.adesso);
  var year = now && now.year === d.year ? '' : '/' + d.year;
  return (article ? article + ' ' : '') + d.day + '/' + d.month + year + ', ' + d.hour;
}

/* Il browser legge questo istante con un altro offset? Si confronta l'offset
   NELL'ISTANTE (parere UX, punto 2), non il nome del fuso: Lisbona e Londra
   hanno nomi diversi e lo stesso orologio, e due fusi che cambiano l'ora in
   settimane diverse sono uguali in un istante e diversi in un altro. */
function offsetDiffers(iso) {
  var d = instantDigits(iso);
  if (!d) return false;
  var house = d.offset === 'Z' ? 0
    : (d.offset[0] === '-' ? -1 : 1) * (+d.offset.slice(1, 3) * 60 + +d.offset.slice(4, 6));
  return -new Date(iso).getTimezoneOffset() !== house;
}

/* Una riga sola per pagina, in testo secondario sotto il titolo (parere UX,
   punto 2), e solo quando il browser sta in un altro fuso: «Gli orari sono
   quelli della casa (Europe/Rome), non del tuo dispositivo.». `title` e' il
   titolo della pagina, `instants` gli istanti che la pagina mostra (oltre ad
   `adesso`). Un id, non una classe: e' l'appiglio per non scriverla due volte
   quando la pagina ridisegna. */
// eslint-disable-next-line no-unused-vars -- global bare, letta da ogni pagina che mostra orari
function clockHint(title, clock, instants) {
  if (!title || !title.parentNode || !clock || !clock.fuso) return;
  if (title.parentNode.querySelector('#clock-hint')) return;
  var far = [clock.adesso].concat(instants || []).some(offsetDiffers);
  if (!far) return;
  var hint = el('p', 'field-hint',
    'Gli orari sono quelli della casa (' + clock.fuso + '), non del tuo dispositivo.');
  hint.id = 'clock-hint';
  title.parentNode.insertBefore(hint, title.nextSibling);
}

/* Collaudo 3.22 (C5): «Richieste 99 · Token input 7.20M · Costo € 0,00»
   senza altra spiegazione -- misurato quando l'UNICO uso e' l'abbonamento
   (`subscription`), che non ha un costo di turno da sommare (vedi
   hiris/app/usage/vocabulary.py::cost_state_and_value, stato "compreso").
   Il totale che il server manda (`cost_eur`) e' 0.0 per costruzione: nessun
   altro addendo. Uno zero misurato e uno zero "non c'e' niente da misurare"
   sono lo stesso zero a schermo, ed e' la stessa confusione a tre stati che
   l'archivio della casa combatte ovunque -- rimessa dentro dalla porta del
   riquadro Utilizzo.

   Niente di nuovo da inventare: ogni sezione di `/api/usage` dice da se' se
   il suo costo e' compreso nel piano (`cost_included`, dalla tabella dei
   provider). Fino alla Tappa 7 (Task 9) qui si riconosceva la sezione per
   nome, "ponte", che non era nemmeno il nome del provider. Condivisa fra il
   riquadro della chat e
   la pagina Consumi -- le DUE superfici che leggono lo stesso `cost_eur`,
   per la stessa ragione per cui fmtEuro/fmtNum vivono qui e non in due
   copie (vedi il commento sopra fmtNum). */
function isSubscriptionOnly(sections) {
  return !!(sections && sections.length
    && sections.every(function(s) { return !!s.cost_included; }));
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
    var when = fmtInstant(d.last_reset, d.orologio, 'il');
    /* «Conta da», non «Azzerato il»: dalla fetta «i consumi, per modello»
       il pulsante sposta un'ancora e non cancella piu' niente, e `last_reset`
       porta l'istante di quell'ancora. Dire «azzerato» descriverebbe un gesto
       che il prodotto non compie piu'. */
    if (when) _setUsageText('usage-last-reset', 'Conta dal ' + when);
    return true;
  } catch(e) {
    console.error('loadUsage failed', e);
    return true;
  }
}
