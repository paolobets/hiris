import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La scheda «L'osservatore» (config/watcher-lavoro.js): cosa si guarda, da
   quando, perche' -- e l'obiettivo, che si scrive da qui.

   Queste prove erano in `watcher-route.test.mjs` fino al taglio del
   18/09/2026, quando la pagina e' diventata quattro schede e sei file (spec
   `docs/design/2026-09-18-la-pagina-dell-osservatore.md`). Sono le stesse,
   riga per riga: cambia il namespace della seam
   (`HirisWatcherLavoro._rendiScope` invece di `HirisWatcherLavoro._rendiScope`),
   la lista `SCRIPTS`, e il fatto che `mount` voglia il nome della scheda -- il
   carico e' pigro, e senza quel nome questa scheda non verrebbe mai letta. */

const SCRIPTS = ['config/watcher-shared.js', 'config/watcher-giorno.js',
  'config/watcher-cosa-fare.js', 'config/watcher-sapere.js',
  'config/watcher-lavoro.js', 'config/state.js', 'config/router.js',
  'config/watcher-route.js'];

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* Il payload nuovo di `GET /api/mind/watching` (fetta «i tre attori»,
   11/09/2026): cinque parti in una risposta sola. `paginaScope()` è la
   forma «archivio collegato, niente ancora deciso»; ogni prova sovrascrive
   la parte che le serve. Le date sono epoch in secondi (float), come
   `da_quando_ts`/`deciso_ts`/`scritto_ts`/`quando_ts` sul filo -- MAI
   confrontate con una stringa fissa nei test: la resa è nel fuso del
   browser di chi fa girare la suite. */
const OBIETTIVO_DI_PROVA = { testo: 'ottimizzare la casa e renderla confortevole', scritto_ts: 1787000000 };
const RICONSIDERAZIONE_DI_PROVA = { quando_ts: 1787000000, finestra_s: 604800, cadenza_s: 302400 };

function paginaScope(extra) {
  return Object.assign({
    watching: [], fuori: [], obiettivo: OBIETTIVO_DI_PROVA,
    riconsiderazione: RICONSIDERAZIONE_DI_PROVA, volume: [],
  }, extra || {});
}

// Una voce decisa dallo scope (un'entità), e una condizione di sistema --
// che `Watcher.watching` (watcher.py) manda con `autore: null` e
// `da_quando_ts: null`, per costruzione.
function voce(soggetto, extra) {
  return Object.assign({ soggetto, motivo: 'scalda la casa', autore: 'observer', da_quando_ts: 1787000000 }, extra || {});
}

function condizione(soggetto) {
  return { soggetto, motivo: 'una condizione di sistema aperta si guarda finche\' dura', autore: null, da_quando_ts: null };
}

/* Il finto server della SOLA scheda «L'osservatore»: la sua lettura
   (`api/mind/watching`) e la sua scrittura (`api/mind/objective`). Un altro
   indirizzo solleva -- se un giorno questa scheda si mettesse a chiedere il
   resoconto o il sapere, il carico pigro sarebbe rotto e si vedrebbe qui. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  const corpiInviati = [];
  ctx.window.fetch = async (url, init) => {
    const u = String(url);
    chiamate.push(u);
    if (init && init.body) corpiInviati.push(String(init.body));
    if (u.indexOf('api/mind/objective') === 0) {
      if (opts.obiettivoRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.obiettivo !== undefined ? opts.obiettivo
          : { obiettivo: OBIETTIVO_DI_PROVA, scritto: true },
        opts.obiettivoStatus);
    }
    if (u.indexOf('api/mind/watching') === 0) {
      if (opts.osservateRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.watching !== undefined ? opts.watching : paginaScope(),
        opts.osservateStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate, corpiInviati });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
}

// ---------------------------------------------------------------------------
// Fetta «i tre attori» (11/09/2026, spec §5.1 e §11): il pavimento non
// esiste più. `GET /api/mind/watching` porta cinque parti in una risposta
// sola -- obiettivo, cosa si guarda (motivo + autore), lasciato fuori,
// riconsiderazione, volume -- e la seam è `_rendiScope(corpo, payload)`,
// non più `_rendiOsservate(corpo, elenco)`. Ogni prova qui sotto dichiara
// quale mutazione della produzione la farebbe arrossire.
// ---------------------------------------------------------------------------

function rendiScope(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherLavoro._rendiScope(corpo, payload);
  return { window, document, corpo };
}

// Un `details` per gruppo: si cerca per il testo del suo `summary`.
function gruppo(corpo, testoSommario) {
  return Array.from(corpo.querySelectorAll('details')).find((d) =>
    d.querySelector('summary') && d.querySelector('summary').textContent.indexOf(testoSommario) === 0);
}

function sommari(corpo) {
  return Array.from(corpo.querySelectorAll('details > summary')).map((s) => s.textContent);
}

function titoli(corpo) {
  return Array.from(corpo.querySelectorAll('h3')).map((h) => h.textContent);
}

const DATA_ORA = /\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/;

// -- 1. L'obiettivo ---------------------------------------------------------

test('seam _rendiScope: l\'obiettivo è la prima cosa, col suo testo e quando è stato scritto', () => {
  // Mutazione che la uccide: togliere `renderObjective(body, p.obiettivo)`
  // da `renderScope` (il testo dell'obiettivo sparisce), oppure spostarla
  // dopo `renderWatched` (il primo h3 non è più «L’obiettivo»).
  const { corpo } = rendiScope(paginaScope({ obiettivo: { testo: 'tenere la casa calda e spendere poco', scritto_ts: 1787000000 } }));
  assert.equal(titoli(corpo)[0], 'L’obiettivo', 'senza la domanda le scelte sono illeggibili: viene prima');
  const citazione = corpo.querySelector('blockquote');
  assert.ok(citazione, 'il testo dell\'obiettivo è una citazione del proprietario, non un paragrafo qualunque');
  assert.equal(citazione.textContent, 'tenere la casa calda e spendere poco');
  assert.match(corpo.textContent, /Scritto il \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/,
    'è datato, e la sua storia conta (spec §11): la data porta l\'anno');
});

test('seam _rendiScope: un obiettivo mai scritto (scritto_ts null) si dice «di fabbrica», non si spaccia per scritto', () => {
  // Mutazione: sostituire `objective.scritto_ts == null ? ... : ...` col solo
  // ramo «Scritto il»: `fmtWhenFull(null)` torna null e la pagina direbbe
  // «Scritto il null.» -- questo assert lo vede.
  const { corpo } = rendiScope(paginaScope({ obiettivo: { testo: 'ottimizzare la casa e renderla confortevole', scritto_ts: null } }));
  assert.match(corpo.textContent, /Obiettivo di fabbrica: nessuno l’ha ancora scritto/);
  assert.doesNotMatch(corpo.textContent, /Scritto il/);
});

// -- I tre stati: archivio scollegato ≠ vuoto ≠ pieno --------------------------

test('seam _rendiScope: con l\'archivio scollegato (obiettivo null) niente è inventato: né il default, né «niente escluso», né «mai riconsiderato»', () => {
  // È il ramo `store is None` di `handle_watching` (handlers_mind.py):
  // `obiettivo: null`, `fuori: []`, `riconsiderazione: null`, `volume: []`.
  // Mutazione: `var archiveMissing = false;` in `renderScope` -- la pagina
  // direbbe «Niente è stato lasciato fuori» e «Non è mai stata fatta», due
  // affermazioni che nessuno ha verificato, e i tre `doesNotMatch` sotto
  // arrossiscono.
  const { corpo } = rendiScope({
    watching: [voce('climate.camera_t')], fuori: [], obiettivo: null, riconsiderazione: null, volume: [],
  });
  const testo = corpo.textContent;
  assert.match(testo, /L’obiettivo non si può leggere/);
  assert.doesNotMatch(testo, /ottimizzare la casa/, 'il default di fabbrica NON si mostra: non si sa quale sia');
  assert.match(testo, /Non si può sapere cosa è stato lasciato fuori/);
  assert.doesNotMatch(testo, /Niente è stato lasciato fuori/);
  assert.match(testo, /Non si può sapere quando la casa è stata riconsiderata/);
  assert.doesNotMatch(testo, /mai stata fatta/);
  assert.match(testo, /Non si può contare/);
  assert.doesNotMatch(testo, /Nessun conteggio disponibile/);
  // Ciò che si guarda, invece, c'è (l'osservatore risponde anche senza archivio).
  assert.match(testo, /climate\.camera_t/);
});

// -- 2. Cosa si guarda: motivo e chi ha deciso ---------------------------------

test('seam _rendiScope: le voci si raggruppano per chi ha deciso, nell\'ordine tu / analista / osservatore, e ogni riga porta il suo motivo', () => {
  // Mutazione: invertire `AUTHOR_ORDER` (l'ordine dei sommari cambia), o
  // togliere `AUTHOR_LABEL[autore] ||` da `authorPhrase` (i sommari
  // diventano «Deciso da «owner»»), o `sayReason` forzato a false in
  // `decisionRow` (i motivi spariscono dalle righe).
  const { corpo } = rendiScope(paginaScope({
    watching: [
      voce('climate.camera_t', { motivo: 'scalda la casa, e il riscaldamento è la voce più pesante', autore: 'observer' }),
      voce('light.cucina', { motivo: 'me l’hai chiesto tu', autore: 'owner' }),
      voce('sensor.co2_soggiorno', { motivo: 'serve al resoconto sull’aria', autore: 'analyst' }),
    ],
  }));
  assert.deepEqual(sommari(corpo), [
    'Deciso da te — 1 voce',
    'Deciso dall’analista — 1 voce',
    'Deciso dall’osservatore — 1 voce',
  ]);
  const tuo = gruppo(corpo, 'Deciso da te');
  assert.match(tuo.textContent, /light\.cucina/);
  assert.match(tuo.textContent, /me l’hai chiesto tu/, 'il motivo sta accanto alla voce: è da lì che si toglie');
  assert.match(tuo.textContent, /dal \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/, '«da quando» si dice, con l\'anno');
  const osservatore = gruppo(corpo, 'Deciso dall’osservatore');
  assert.match(osservatore.textContent, /il riscaldamento è la voce più pesante/);
});

test('seam _rendiScope: una condizione di sistema (autore null) non è attribuita a nessuno e non porta un «dal»', () => {
  // `Watcher.watching` (watcher.py): le condizioni di sistema non passano
  // dallo scope, nessuno le ha decise, `autore: None`, `da_quando_ts: None`.
  // Mutazione: `var k = v.autore == null ? '' : ...` -> `var k = v.autore ||
  // 'observer'` in `groupByAuthor`: la condizione finirebbe sotto «Deciso
  // dall’osservatore», e il primo assert la vede. Mutazione sul «dal»:
  // `ts != null ? ... : null` -> sempre `opts.whenPrefix + ' ' +
  // fmtWhenFull(ts)`: comparirebbe «dal null».
  const { corpo } = rendiScope(paginaScope({
    watching: [
      condizione('problema:sonos.subscriptions_failed'),
      voce('climate.camera_t', { autore: 'observer' }),
    ],
  }));
  assert.deepEqual(sommari(corpo), [
    'Deciso dall’osservatore — 1 voce',
    'Condizioni di sistema aperte — 1 voce',
  ], 'le condizioni di sistema chiudono, in un gruppo proprio, senza autore');
  const sistema = gruppo(corpo, 'Condizioni di sistema aperte');
  assert.match(sistema.textContent, /Nessuno le ha decise/);
  assert.match(sistema.textContent, /Problema Home Assistant: sonos\.subscriptions_failed/,
    'il prefisso tecnico passa da describeWatchedSubject, come prima');
  assert.doesNotMatch(sistema.textContent, /\bdal\b/, 'da_quando_ts è null per costruzione: nessuna data inventata');
  assert.doesNotMatch(sistema.textContent, /null/);
  const osservatore = gruppo(corpo, 'Deciso dall’osservatore');
  assert.doesNotMatch(osservatore.textContent, /sonos/, 'la condizione non finisce sotto l\'osservatore');
});

test('seam _rendiScope: un autore che la pagina non conosce non sparisce: ha il suo gruppo, col valore grezzo', () => {
  // Stessa regola di `GENRE_LABEL`. Mutazione: in `groupByAuthor` togliere
  // il ciclo `seen.forEach(...)` che accoda gli autori fuori da
  // `AUTHOR_ORDER` -- la voce sparirebbe dalla pagina.
  const { corpo } = rendiScope(paginaScope({
    watching: [voce('switch.pompa', { autore: 'gardener' })],
  }));
  assert.deepEqual(sommari(corpo), ['Deciso da «gardener» — 1 voce']);
  assert.match(gruppo(corpo, 'Deciso da «gardener»').textContent, /switch\.pompa/);
});

test('seam _rendiScope: un motivo identico su ogni riga del gruppo si dice una volta, non trenta', () => {
  // Le ~30 condizioni di sistema portano tutte `_SYSTEM_REASON`
  // (watcher.py). Mutazione: `var sharedReason = false;` in
  // `renderDecisionGroup` -- il motivo torna su ogni riga e il conteggio
  // sale a 3. Mutazione opposta (dire sempre «per tutte» anche con motivi
  // diversi): il secondo gruppo qui sotto perderebbe uno dei due motivi.
  const MOTIVO = 'una condizione di sistema aperta si guarda finche\' dura';
  const { corpo } = rendiScope(paginaScope({
    watching: [
      condizione('problema:sonos.subscriptions_failed'),
      condizione('integrazione:01K2CK4GG287VKK18M5J788MRQ'),
      condizione('automazione:automation.spegni_luci_notte'),
      voce('climate.camera_t', { motivo: 'scalda la casa' }),
      voce('light.cucina', { motivo: 'la luce che accendi di più' }),
    ],
  }));
  const sistema = gruppo(corpo, 'Condizioni di sistema aperte');
  const occorrenze = sistema.textContent.split(MOTIVO).length - 1;
  assert.equal(occorrenze, 1, 'il motivo condiviso compare una volta sola nel gruppo');
  assert.match(sistema.textContent, /Motivo, per tutte: /);
  const osservatore = gruppo(corpo, 'Deciso dall’osservatore');
  assert.match(osservatore.textContent, /scalda la casa/);
  assert.match(osservatore.textContent, /la luce che accendi di più/);
  assert.doesNotMatch(osservatore.textContent, /Motivo, per tutte/, 'motivi diversi: ognuna porta il suo');
});

// -- 3. Lasciato fuori ----------------------------------------------------------

test('seam _rendiScope: ciò che è stato lasciato fuori ha la sua parte, con motivo, autore e quando; e la frase su chi non è stato considerato', () => {
  // Mutazione: togliere il ciclo `groupByAuthor(leftOut).forEach(...)` da
  // `renderLeftOut` -- `sensor.uptime` e il suo motivo spariscono. Mutazione
  // sulla frase: toglierla lascia leggere «lasciato fuori» come «tutto il
  // resto della casa».
  const { corpo } = rendiScope(paginaScope({
    fuori: [{ soggetto: 'sensor.uptime', motivo: 'di servizio, non dice niente sulla casa', autore: 'observer', deciso_ts: 1787000001 }],
  }));
  assert.ok(titoli(corpo).indexOf('Lasciato fuori') > titoli(corpo).indexOf('Cosa guardo'),
    'l\'altra metà della trasparenza viene DOPO cosa si guarda');
  const fuori = gruppo(corpo, 'Lasciato fuori dall’osservatore');
  assert.ok(fuori, 'sommari trovati: ' + sommari(corpo).join(' | '));
  assert.match(fuori.querySelector('summary').textContent, /— 1 voce$/);
  assert.match(fuori.textContent, /sensor\.uptime/);
  assert.match(fuori.textContent, /di servizio, non dice niente sulla casa/);
  // Si legge lo span del «quando», non `textContent` (che incolla gli span
  // senza spazi -- «sensor.uptimeil 17/08/2026» -- e un `\b` non ci starebbe).
  const quando = Array.from(fuori.querySelectorAll('.field-hint')).map((s) => s.textContent)
    .find((s) => /^(il|dal) /.test(s));
  assert.ok(quando, 'deciso_ts deve comparire come «quando» accanto alla voce');
  assert.match(quando, /^il \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/, 'deciso_ts si mostra come «il ...», non «dal ...»');
  assert.match(corpo.textContent, /non è stato escluso — non è stato considerato/);
});

test('seam _rendiScope: con l\'archivio collegato e nessuna esclusione si dice «niente lasciato fuori» (non «non si può sapere»)', () => {
  // Mutazione: `if (archiveMissing)` -> `if (archiveMissing || !leftOut.length)`
  // in `renderLeftOut`: un'assenza vera verrebbe raccontata come un buco di
  // lettura.
  const { corpo } = rendiScope(paginaScope({ fuori: [] }));
  assert.match(corpo.textContent, /Niente è stato lasciato fuori con una ragione scritta/);
  assert.doesNotMatch(corpo.textContent, /Non si può sapere cosa è stato lasciato fuori/);
});

// -- 4. La riconsiderazione: tutti e tre i numeri ----------------------------

test('seam _rendiScope: la riconsiderazione mostra quando, la memoria misurata in giorni e la cadenza in ore — tutti e tre', () => {
  // Mutazione: togliere la tessera «Memoria di Home Assistant, misurata» da
  // `tiles` in `renderReconsideration` -- «ogni 84 ore» resterebbe da
  // credere sulla parola, e `/7 giorni/` arrossisce. Mutazione su
  // `fmtHours`: dividere per 86400 invece di 3600 darebbe «3,5 ore».
  const { corpo } = rendiScope(paginaScope({ riconsiderazione: { quando_ts: 1787000000, finestra_s: 604800, cadenza_s: 302400 } }));
  const tessere = Array.from(corpo.querySelectorAll('.stat-tile')).map((t) =>
    [t.querySelector('.st-label').textContent, t.querySelector('.st-value').textContent]);
  assert.equal(tessere.length, 3);
  assert.equal(tessere[0][0], 'Ultima volta');
  assert.match(tessere[0][1], DATA_ORA);
  assert.deepEqual(tessere[1], ['Memoria di Home Assistant, misurata', '7 giorni']);
  assert.deepEqual(tessere[2], ['Cadenza', 'ogni 84 ore']);
  assert.match(corpo.textContent, /La cadenza è la metà della memoria misurata/,
    'il legame fra i due numeri (mind/cadence.py::cadence_from) si dice');
});

test('seam _rendiScope: riconsiderazione mai fatta (null, archivio collegato) si dice tale, senza tessere', () => {
  // Mutazione: `if (!r)` tolto in `renderReconsideration` -- `r.quando_ts`
  // lancerebbe su null, oppure (con `r || {}`) comparirebbero tre tessere
  // «data non disponibile / non misurata / nessuna» per una riconsiderazione
  // che non è mai avvenuta.
  const { corpo } = rendiScope(paginaScope({ riconsiderazione: null }));
  assert.match(corpo.textContent, /Non è mai stata fatta/);
  assert.equal(corpo.querySelectorAll('.stat-tile').length, 0);
});

test('seam _rendiScope: finestra non misurata dentro una riconsiderazione avvenuta: «non misurata», «nessuna», e la conseguenza detta', () => {
  // `record_reconsideration` (mind/store.py) accetta `window_s=None`, e
  // `cadence_from(None)` (mind/cadence.py) dà None; `due()` senza cadenza
  // risponde di no. Mutazione: togliere il ramo `if (r.finestra_s == null ||
  // r.cadenza_s == null)` -- la pagina direbbe «la cadenza è la metà della
  // memoria misurata» sotto a una tessera «non misurata».
  const { corpo } = rendiScope(paginaScope({ riconsiderazione: { quando_ts: 1787000000, finestra_s: null, cadenza_s: null } }));
  const valori = Array.from(corpo.querySelectorAll('.stat-tile .st-value')).map((v) => v.textContent);
  assert.equal(valori[1], 'non misurata');
  assert.equal(valori[2], 'nessuna');
  assert.match(corpo.textContent, /non riconsidera la casa da solo finché non riesce a misurarla/);
  assert.doesNotMatch(corpo.textContent, /La cadenza è la metà/);
});

// -- 5. Quanto scrive al giorno ---------------------------------------------------

test('seam _rendiScope: il volume è una barra per giorno, nell\'ordine del payload, larga in proporzione al giorno più alto, col numero scritto', () => {
  // Mutazione: `.reverse()` prima del ciclo in `renderVolume` (l'ordine dei
  // giorni cambia); `pct` calcolato su una costante invece che su `max` (le
  // larghezze non tornano); `fmtCount` sostituito da `String(n)` («4951»
  // invece di «4.951»); `if (r.righe) return` per saltare i giorni a zero (la
  // riga a zero sparisce).
  //
  // **I giorni arrivano NON ordinati, ed è voluto** (15/09/2026): col payload
  // già crescente un `volume.sort(...)` era un no-op e la mutazione restava
  // verde — la prova dimostrava «crescente», non «nell'ordine del payload»
  // come dice il titolo. L'ha detto una mutazione eseguita dalla revisione
  // indipendente.
  const { corpo } = rendiScope(paginaScope({
    volume: [
      { giorno: '2026-09-05', righe: 4951 },
      { giorno: '2026-09-04', righe: 29227 },
      { giorno: '2026-09-06', righe: 0 },
    ],
  }));
  const righe = Array.from(corpo.querySelectorAll('ul > li'));
  assert.equal(righe.length, 3);
  assert.deepEqual(righe.map((li) => li.querySelector('.field-hint').textContent),
    ['05/09/2026', '04/09/2026', '06/09/2026'],
    "nell'ordine in cui il server li manda: chi ordina e' `_volume`, non la pagina");
  assert.deepEqual(righe.map((li) => li.querySelector('.text-mono').textContent),
    ['4.951 righe', '29.227 righe', '0 righe']);
  // Il CSSOM RISERIALIZZA il valore letto («100.0%» -> «100%», «0.0%» ->
  // «0%»; stesso comportamento gia' misurato per `display:flex` piu' sopra):
  // si confronta il numero, non la stringa scritta dalla pagina.
  const larghezze = righe.map((li) => parseFloat(li.querySelector('[aria-hidden="true"] > div').style.width));
  assert.equal(larghezze[1], 100, 'il giorno piu\' alto e\' il metro: barra piena');
  assert.equal(larghezze[0], Number((4951 / 29227 * 100).toFixed(1)));
  assert.equal(larghezze[2], 0, 'un giorno a zero resta una barra vuota, non sparisce');
  assert.equal(corpo.querySelectorAll('canvas, svg').length, 0, 'barre CSS, niente canvas/SVG per sette numeri');
});

// -- Le sei parti, in quest'ordine, e niente pavimento ------------------------------
//
// Erano cinque fino all'11/09/2026. La sesta, «I tentativi», e' entrata perche'
// le altre cinque, tutte insieme, non sapevano dire che l'osservatore stava
// fallendo da quaranta minuti mentre la casa non veniva piu' registrata.

test('seam _rendiScope: le sei parti sono titoli veri (h3), nell\'ordine della spec, e il pavimento non affiora più', () => {
  // Mutazione: scambiare due chiamate in `renderScope` (l'ordine cambia);
  // `el('p', ...)` al posto di `el('h3', ...)` in `subheading` (un lettore
  // di schermo non salta più di parte in parte).
  const { corpo } = rendiScope(paginaScope({ watching: [voce('climate.camera_t')] }));
  assert.deepEqual(titoli(corpo), ['L’obiettivo', 'Cosa guardo', 'Lasciato fuori', 'La riconsiderazione', 'I tentativi', 'Quanto scrive al giorno']);
  assert.doesNotMatch(corpo.textContent, /pavimento|Di serie|gamba/i,
    'le parole del vecchio filtro non devono comparire nel testo utente');
  assert.equal(corpo.querySelectorAll('.agent-badge').length, 0,
    'nessun badge di provenienza per riga: chi ha deciso sta sul gruppo');
});

// ---------------------------------------------------------------------------
// Cancello del collaudo E2 (07/09/2026, BACKLOG.md «"Cosa sto guardando"
// stampa i soggetti grezzi, gli episodi no»): la vecchia resa scriveva
// `v.soggetto` tale e quale, mentre gli episodi (renderFacts, la sezione
// gemella della stessa pagina) passavano gia' da `protagonistName`. Col
// gruppo passato da due a diciannove voci, diciassette delle quali percorsi
// di file, il difetto -- gia' presente prima -- e' diventato visibile.
// Portato sul payload nuovo (11/09/2026): le condizioni di sistema arrivano
// con `autore: null`, e la resa passa da `decisionRow`.
// ---------------------------------------------------------------------------

test('seam _rendiScope: un prefisso tecnico grezzo (log:/integrazione:/problema:/automazione:) non resta mai a schermo (collaudo E2, 07/09/2026)', () => {
  // Mutazione dichiarata: in `decisionRow` sostituire
  // `el('span', 'text-mono', described.primary)` con
  // `el('span', 'text-mono', v.soggetto)` fa arrossire `assert.doesNotMatch`
  // qui sotto, sulle voci `log:` e `integrazione:` -- il soggetto grezzo
  // torna a comparire tale e quale.
  const { corpo } = rendiScope(paginaScope({
    watching: [
      condizione('integrazione:01K2CK4GG287VKK18M5J788MRQ'),
      condizione('log:aioamazondevices@components/alexa_devices/coordinator.py:192'),
      condizione('log:homeassistant.components.hydrawise@helpers/update_coordinator.py:481'),
      condizione('log:custom_components.zcsazzurro.api@custom_components/zcsazzurro/api.py:202'),
      condizione('problema:light.termostato_soggiorno'),
      condizione('automazione:automation.spegni_luci_notte'),
    ],
  }));

  // Il nome leggibile e' sempre il PRIMO `.text-mono` di ogni riga (la resa
  // scrive prima `primary`, poi -- solo se c'e' -- `secondary`).
  const righe = Array.from(corpo.querySelectorAll('ul > li'));
  const primary = righe.map((li) => li.querySelector('.text-mono').textContent);
  assert.equal(primary.length, 6, 'una riga per soggetto, come le sei voci passate');

  primary.forEach((text, i) => {
    assert.doesNotMatch(text, /^(log|integrazione|problema|automazione):/,
      `riga ${i}: un prefisso tecnico e' rimasto a schermo tale e quale: "${text}"`);
  });

  assert.match(primary[0], /integrazione non caricata/i,
    'senza titolo, un id opaco (ULID) non e\' risolvibile: si dice cosa e\', non l\'id da solo');
  assert.match(primary[1], /Registro: aioamazondevices/,
    'il logger e\' il nome utile del soggetto "log:", e resta leggibile');
  assert.match(primary[2], /Registro: homeassistant\.components\.hydrawise/);
  assert.match(primary[3], /Registro: custom_components\.zcsazzurro\.api/);

  // Il percorso del file NON si butta (distingue due errori dello stesso
  // logger): resta a schermo, ma in secondo piano (`.text-mono.field-hint`),
  // mai come primo testo della riga.
  const secondaria = righe[1].querySelector('.text-mono.field-hint');
  assert.ok(secondaria, 'il riferimento tecnico del "log:" non deve sparire, solo passare in secondo piano');
  assert.match(secondaria.textContent, /coordinator\.py:192/);
  assert.doesNotMatch(primary[1], /coordinator\.py/, 'il percorso del file non deve stare nel nome PRIMARIO della riga');

  // Lo stesso vincolo per `integrazione:` (rilievo del revisore,
  // 07/09/2026): mutazione ESEGUITA allora -- rimettere `secondary: ''` al
  // posto di `secondary: p.rest` per il caso `integrazione` in
  // `describeWatchedSubject` fa arrossire `assert.ok` qui sotto.
  const secondariaIntegrazione = righe[0].querySelector('.text-mono.field-hint');
  assert.ok(secondariaIntegrazione,
    'l\'id dell\'integrazione non deve sparire, solo passare in secondo piano (come il percorso del "log:")');
  assert.match(secondariaIntegrazione.textContent, /01K2CK4GG287VKK18M5J788MRQ/);
  assert.doesNotMatch(primary[0], /01K2CK4GG287VKK18M5J788MRQ/,
    'l\'id non deve stare nel nome PRIMARIO della riga (è opaco, non un nome)');
});

// ---------------------------------------------------------------------------
// «Riprova»: unica pagina di lettura che ne era priva (rilievo 4)
// ---------------------------------------------------------------------------

test('un errore nel leggere "cosa sto guardando" (503) offre Riprova, e il testo del messaggio non cambia', async () => {
  const { window, document } = montaConServer({ osservateStatus: 503, watching: {} });
  window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è una lista vuota — è l’osservatore stesso ad essere fermo/,
    'il testo d\'errore a tre stati non si tocca (è dichiarato il migliore del pannello)');
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare, come nelle pagine sorelle');
});

test('un guasto di rete su "cosa sto guardando" offre Riprova, e il bottone rilancia la richiesta', async () => {
  const { window, document, chiamate } = montaConServer({ osservateRotto: true });
  window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  const primaDelClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  const retry = bottone(document, 'Riprova');
  assert.ok(retry, 'deve esserci un modo di riprovare');
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const dopoIlClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  assert.equal(dopoIlClick, primaDelClick + 1, 'il bottone deve rilanciare la stessa richiesta');
});

// ---------------------------------------------------------------------------
// Fetta «il nome» (07/09/2026): il nome amichevole SALVATO al momento del
// cambio (`corpo.nome`, colonna `friendly_name`) arriva alla riga; e quando
// non c'è, la riga mostra l'identificatore DICENDO che è un identificatore —
// mai un nome dedotto dall'`entity_id`, mai una riga muta.
// ---------------------------------------------------------------------------




test('seam _rendiScope: un entity_id nudo viene dichiarato per quello che è (l\'endpoint non porta nomi)', () => {
  // R4 (revisione del tratto v3.22.2..HEAD): quando OGNI voce del gruppo è
  // tecnica (qui l'unica voce dell'osservatore) la dichiarazione vive una
  // volta per il GRUPPO, non sulla riga -- la riga da sola, ripetuta su un
  // elenco di ~380 entità, era il rumore che il rilievo segnala. Mutazione
  // dichiarata: togliere il blocco `if (allTechnical) { ... }` da
  // `renderDecisionGroup` fa arrossire `assert.match(dettaglio.textContent,
  // /identificatori tecnici/i)`.
  const { corpo } = rendiScope(paginaScope({
    watching: [voce('binary_sensor.movimento_cucina')],
  }));
  const dettaglio = corpo.querySelector('details');
  assert.match(dettaglio.textContent, /identificatori tecnici/i,
    '`/api/mind/watching` non porta nomi: il gruppo deve dirlo (una volta), non tacerlo');
  const riga = corpo.querySelector('ul > li');
  assert.match(riga.textContent, /binary_sensor\.movimento_cucina/,
    'l\'id non si butta e non si tace: resta a schermo');
  assert.doesNotMatch(riga.textContent, /identificatore/i,
    'sul gruppo tutto tecnico la riga non ripete piu\' la dichiarazione: l\'ha già detta il gruppo');
  assert.doesNotMatch(riga.textContent, /Movimento Cucina/,
    'nessun nome dedotto dall\'id');
});

test('seam _rendiScope: un gruppo misto (entità + condizioni già nominate) porta la dichiarazione SOLO sulla riga tecnica', () => {
  // Col payload nuovo un gruppo misto non nasce dal filo (`Watcher.watching`
  // mette le condizioni di sistema sotto `autore: null`, le entità sotto un
  // autore), ma `renderDecisionGroup` non deve dipendere da quella
  // garanzia per essere corretta: un `problema:` con un autore -- domani,
  // se l'analista chiedesse di guardarne uno -- cadrebbe qui. Mutazione
  // dichiarata: sostituire `!allTechnical` con `false` nella chiamata a
  // `decisionRow` fa arrossire il primo assert (la dichiarazione sparisce
  // anche dove distingue).
  const { corpo } = rendiScope(paginaScope({
    watching: [
      voce('lock.porta_garage', { autore: 'analyst' }),
      voce('problema:light.termostato_soggiorno', { autore: 'analyst' }),
    ],
  }));
  const righe = Array.from(corpo.querySelectorAll('ul > li'));
  assert.equal(righe.length, 2);
  assert.match(righe[0].textContent, /identificatore/i,
    'la voce tecnica del gruppo misto porta ancora la dichiarazione per-riga: qui distingue');
  assert.doesNotMatch(righe[1].textContent, /identificatore/i,
    'la voce già nominata (il "problema:") non è un identificatore nudo');
  // Il gruppo è misto, non uniforme: la dichiarazione UNA-volta-per-gruppo
  // (pensata per i gruppi tutti tecnici) non deve comparire qui, o la stessa
  // informazione si direbbe due volte in due forme diverse.
  const dettaglio = corpo.querySelector('details');
  assert.doesNotMatch(dettaglio.textContent, /identificatori tecnici/i,
    'un gruppo misto non porta anche l\'annuncio collettivo: solo la dichiarazione per-riga, dove distingue');
});








// -- 6. I tentativi ---------------------------------------------------------
//
// Il difetto misurato sulla casa vera l'11/09/2026: l'osservatore ha provato
// e fallito quattro volte in quaranta minuti, HIRIS ha smesso di registrare
// qualunque cosa (il cancello di cio' che si registra E' lo scope), e questa
// pagina diceva soltanto «Non e' mai stata fatta». Vero alla lettera, falso
// come racconto. La regola che il prodotto si e' dato -- e che questa pagina
// violava -- e' che **un guasto non si appiattisce su un'assenza**.

function tentativo(esito, quandoFa, dettaglio) {
  return { quando_ts: Math.floor(Date.now() / 1000) - quandoFa, esito: esito,
           dettaglio: dettaglio };
}

test('seam _rendiScope: senza nessun tentativo lo dice, e non tace', () => {
  // Mutazione che la uccide: saltare la sezione quando l'elenco e' vuoto --
  // e' proprio il silenzio da cui questa fetta nasce.
  const { corpo } = rendiScope(paginaScope({ tentativi: [] }));
  assert.ok(titoli(corpo).includes('I tentativi'),
    'la sezione esiste anche quando non c\'e' + '’' + ' niente da mostrare');
  assert.match(corpo.textContent, /Nessuno ha ancora provato a ripensare la casa/);
});

test('seam _rendiScope: un turno in attesa NON si confonde con un guasto', () => {
  // Dieci minuti di attesa legittima e quaranta di guasto avevano la stessa
  // faccia: nessuna. Mutazione che la uccide: rendere «accodata» con lo
  // stesso tono del fallimento.
  const { corpo } = rendiScope(paginaScope({
    tentativi: [tentativo('accodata', 180, 'chiesto al piano: non è mai stata fatta')] }));
  assert.match(corpo.textContent, /In corso da 3 minuti/);
  assert.equal(corpo.innerHTML.indexOf('--err-ink'), -1,
    'aspettare non è un guasto: nessun rosso');
});

test("seam _rendiScope: un giro riuscito dice quanto ha deciso NELLA FRASE, non solo nell'elenco", () => {
  // **Questa prova e' nata verde e non poteva fallire.** La prima stesura
  // asseriva `/31 decisioni su 381/` su tutto il testo della sezione -- e
  // quel dettaglio compare ANCHE dentro l'elenco richiudibile, quindi
  // toglierlo dalla frase a colpo d'occhio la lasciava verde. Mutazione
  // ESEGUITA l'11/09/2026 (`line(...)` senza `last.dettaglio`): verde.
  // Riscritta per legare le due meta' in UNA frase, la stessa mutazione la
  // fa arrossire. E' il difetto n.1 di questo progetto, trovato su se stesso.
  const { corpo } = rendiScope(paginaScope({
    tentativi: [tentativo('riuscito', 7200, "31 decisioni su 381 entita' guardate")] }));
  assert.match(corpo.textContent, /L’ultimo tentativo è riuscito, 2 ore fa: 31 decisioni su 381/,
    "a colpo d'occhio si deve leggere quanto ha deciso, senza aprire niente");
});

test('seam _rendiScope: una serie di fallimenti si vede, e dice DA QUANTO', () => {
  // **Questa e' la prova del difetto dell'11/09/2026.** Quattro fallimenti di
  // fila in quaranta minuti erano indistinguibili da un avvio appena fatto.
  // Mutazione che la uccide: mostrare solo l'ultimo tentativo invece della
  // serie -- il testo perde «4 tentativi di fila» e il «da 40 minuti».
  // Il giro riuscito in fondo e' cio' che rende la durata SAPUTA: la serie
  // finisce li', e non c'e' niente da dire con «almeno».
  const { corpo } = rendiScope(paginaScope({
    tentativi: [
      tentativo('non_riuscito', 120, 'il modello non ha risposto: RuntimeError'),
      tentativo('non_riuscito', 720, 'il modello non ha risposto: RuntimeError'),
      tentativo('non_riuscito', 1320, 'il modello non ha risposto: RuntimeError'),
      tentativo('non_riuscito', 2400, 'il modello non ha risposto: RuntimeError'),
      tentativo('riuscito', 3000, "31 decisioni su 381 entita' guardate"),
    ] }));
  assert.match(corpo.textContent, /Sta fallendo da 40 minuti/);
  assert.match(corpo.textContent, /4 tentativi di fila/);
  assert.ok(corpo.innerHTML.indexOf('--err-ink') !== -1,
    'un guasto in corso costa dati veri, per sempre: si vede');
});

test('seam _rendiScope: con l\'elenco pieno di fallimenti si dice «almeno», non un numero preciso', () => {
  // L'elenco arriva a dieci: se sono dieci fallimenti, da quanto duri non si
  // SA. Un numero preciso su un fatto troncato e' un dato dedotto spacciato
  // per uno letto -- il difetto n.4 di questo progetto.
  // Mutazione che la uccide: togliere il ramo «almeno».
  const tentativi = [];
  for (let n = 0; n < 10; n++) tentativi.push(tentativo('non_riuscito', 120 + n * 600, 'niente da fare'));
  const { corpo } = rendiScope(paginaScope({ tentativi: tentativi }));
  assert.match(corpo.textContent, /almeno 10 tentativi di fila/);
  assert.match(corpo.textContent, /più indietro di così non si vede/,
    "la pagina non nomina «dieci»: il tetto vive nell'archivio, e ricopiarlo "
    + 'qui sarebbe un doppione destinato a mentire quando cambia');
});

test('seam _rendiScope: quando sta fallendo la storia è già APERTA, altrimenti no', () => {
  // Le altre rivelazioni di questa pagina nascono chiuse perche' sono un
  // DETTAGLIO -- «i dati sono gia' nel payload, chi vuole apre»; questa nasce
  // aperta per URGENZA, che e' un'altra ragione e vale solo nel caso brutto.
  // (La prima stesura citava «un'area con 1.224 entita'»: quel numero vive in
  // `tree-route.js:348`, parla di una CASA e riguarda un'altra pagina --
  // motivazione falsa, trovata dalla review indipendente dell'11/09/2026.)
  // Mutazione che la uccide: passare sempre `false` a `openByDefault`.
  const rotto = rendiScope(paginaScope({
    tentativi: [tentativo('non_riuscito', 120, 'x'), tentativo('non_riuscito', 720, 'x')] }));
  const sano = rendiScope(paginaScope({
    tentativi: [tentativo('riuscito', 120, '3 decisioni su 4 entita\' guardate')] }));

  const apertoRotto = Array.from(rotto.corpo.querySelectorAll('button[aria-expanded]'))
    .some((b) => b.getAttribute('aria-expanded') === 'true');
  const apertoSano = Array.from(sano.corpo.querySelectorAll('button[aria-expanded]'))
    .some((b) => b.getAttribute('aria-expanded') === 'true');

  assert.ok(apertoRotto, 'un guasto in corso non si va a cercare: si trova aperto');
  assert.ok(!apertoSano, 'quando va tutto bene la storia è rumore: resta chiusa');
});

test('seam _rendiScope: un turno in attesa DOPO una serie di fallimenti non nasconde la serie', () => {
  // **Il difetto che la review ha trovato, ed e' quello da cui nasce la
  // fetta, ricostruito dalla pagina nuova.** Dopo un fallimento il giro
  // riaccoda, quindi la sequenza VERA che l'archivio produce ha «accodata» in
  // cima e i fallimenti sotto: contando la serie dall'indice 0 il conto
  // finiva a zero, e quaranta minuti di guasto tornavano ad avere la faccia
  // di un'attesa di un minuto -- calma, elenco chiuso.
  // Mutazione che la uccide: contare i fallimenti dall'indice 0 invece che
  // dalla prima voce che non sia «accodata».
  const { corpo } = rendiScope(paginaScope({
    tentativi: [
      tentativo('accodata', 30, 'chiesto al piano'),
      tentativo('non_riuscito', 600, 'il modello non ha risposto: RuntimeError'),
      tentativo('non_riuscito', 1200, 'il modello non ha risposto: RuntimeError'),
      tentativo('non_riuscito', 1800, 'il modello non ha risposto: RuntimeError'),
      tentativo('riuscito', 2400, '31 decisioni su 381 entita\' guardate'),
    ] }));
  assert.match(corpo.textContent, /3 tentativi di fila non sono riusciti/);
  assert.ok(corpo.innerHTML.indexOf('--err-ink') !== -1,
    'sta ancora fallendo: l\'attesa in corso non cancella la serie sotto');
});

test('seam _rendiScope: un esito che la pagina non conosce non la fa esplodere', () => {
  // **Questa prova e' nata verde per la ragione sbagliata.** La prima stesura
  // usava «scaduta», che pero' e' un esito CONOSCIUTO e conta fra i guasti: il
  // ramo della serie lo copriva e la guardia non veniva mai toccata. Mutazione
  // ESEGUITA l'11/09/2026 (`run > 1` -> `run >= 0`, che toglie la guardia):
  // verde. Riscritta con un esito che la pagina non conosce davvero.
  //
  // Senza guardia, `tentativi[inizio + run - 1]` con `run === 0` legge
  // `tentativi[-1]` -- `undefined` -- e l'eccezione porta via TUTTE E SEI le
  // parti della sezione: la pagina che deve dire «sta funzionando?» muore.
  const { corpo } = rendiScope(paginaScope({
    tentativi: [tentativo('boh', 120, 'un esito che questa pagina non conosce'),
                tentativo('non_riuscito', 720, 'x')] }));
  assert.ok(titoli(corpo).includes('Quanto scrive al giorno'),
    "la sezione dopo esiste ancora: niente e' esploso");
  assert.match(corpo.textContent, /un esito che questa pagina non conosce/);
});

test('seam _rendiScope: un tentativo di un mese fa si dice in giorni, non in 840 ore', () => {
  // Su una casa SANA i tentativi avvengono alla cadenza -- 84 ore su questa
  // casa -- quindi dieci righe sono piu' di un mese. Il commento diceva «per
  // costruzione sono recenti»: falso.
  // Mutazione che la uccide: togliere la soglia dei giorni da `fmtDuration`.
  const { corpo } = rendiScope(paginaScope({
    tentativi: [tentativo('riuscito', 35 * 86400, '31 decisioni su 381 entita\' guardate')] }));
  assert.doesNotMatch(corpo.textContent, /\d{3,} ore/);
  assert.match(corpo.textContent, /giorni fa/);
});

/* ------------------------------------------- l'obiettivo si SCRIVE (§11)

   Misurato sulla casa vera il 14/09/2026: l'obiettivo era ancora quello di
   fabbrica, `scritto_ts: null`, perché `set_objective` non aveva NESSUN
   chiamante — né rotta, né campo, né strumento in chat. L'osservatore
   decideva cosa guardare contro una frase generica, e la spec lo chiama
   «obiettivo = prompt». */

test('seam _rendiScope: l’obiettivo si può scrivere, e il campo parte da quello di adesso', () => {
  // Mutazione che la uccide: rendere l'obiettivo di sola lettura.
  const { corpo } = rendiScope(paginaScope());
  const campo = corpo.querySelector('textarea');
  assert.ok(campo, 'ci deve essere un campo per scriverlo');
  assert.equal(campo.value, OBIETTIVO_DI_PROVA.testo,
    'parte da quello di adesso: si corregge, non si riscrive da zero');
  assert.ok(bottone(corpo, 'Salva l’obiettivo'), 'e un bottone per salvarlo');
});

test('mount: salvare l’obiettivo lo manda alla rotta, col testo scritto', async () => {
  // Mutazione che la uccide: mandare il testo vecchio invece di quello nel campo.
  const ctx = montaConServer();
  ctx.window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  const campo = ctx.document.querySelector('textarea');
  campo.value = 'spendere meno di sera';
  bottone(ctx.document, 'Salva l’obiettivo').click();
  await tick(20);

  const scritte = ctx.chiamate.filter((u) => u.indexOf('api/mind/objective') === 0);
  assert.equal(scritte.length, 1, JSON.stringify(ctx.chiamate));
  assert.equal(ctx.corpiInviati[0], JSON.stringify({ testo: 'spendere meno di sera' }));
});

test('mount: un obiettivo rifiutato DICE perché, e non svuota il campo', async () => {
  // Il proprietario ha appena scritto una frase: perderla sarebbe il danno
  // peggiore dei due.
  // Mutazione che la uccide: ricaricare la sezione anche quando la rotta rifiuta.
  const ctx = montaConServer({
    obiettivoStatus: 400,
    obiettivo: { errore: 'un obiettivo vuoto non si scrive: è la sola manopola' },
  });
  ctx.window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  const campo = ctx.document.querySelector('textarea');
  campo.value = '   ';
  bottone(ctx.document, 'Salva l’obiettivo').click();
  await tick(20);

  assert.match(ctx.document.getElementById('route-outlet').textContent,
    /sola manopola/);
  assert.equal(ctx.document.querySelector('textarea').value, '   ',
    'il campo resta com’era: la frase appena scritta non si butta');
});

test('mount: riscrivere lo STESSO obiettivo non è un errore, e lo dice', async () => {
  // `scritto: false` vuol dire «c'era già», non «non ha funzionato»: dirlo
  // come un guasto insegnerebbe a diffidare dei guasti veri.
  // Mutazione che la uccide: trattare `scritto: false` come un errore.
  const ctx = montaConServer({
    obiettivo: { obiettivo: OBIETTIVO_DI_PROVA, scritto: false },
  });
  ctx.window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  bottone(ctx.document, 'Salva l’obiettivo').click();
  await tick(20);

  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.match(testo, /era già questo/);
  assert.doesNotMatch(testo, /non è stato possibile/i);
});
