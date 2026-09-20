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
/* Dal 20/09/2026 i gruppi non sono piu' `<details>`: sono elenchi lunghi
   (spec §6) -- una riga di riassunto, un bottone alto 44 px, e le righe
   costruite al clic. Questi due aiuti tengono le prove che c'erano gia',
   dicendo la stessa cosa nella forma nuova. */
function gruppo(corpo, testoRiassunto) {
  /* Un «gruppo» nella forma nuova e' tutto cio' che sta fra la sua riga di
     riassunto e quella del gruppo dopo: un bottone (che si apre), l'elenco
     costruito al clic, oppure -- se le righe sono poche -- le righe stesse,
     che sotto la soglia non si chiudono. Si raccoglie tutto in un nodo solo,
     cosi' le prove che c'erano continuano a leggere `textContent`. */
  const riassunti = Array.from(corpo.querySelectorAll('p.sc-desc'));
  const riassunto = riassunti.find((d) => d.textContent.trim().indexOf(testoRiassunto) === 0);
  if (!riassunto) return undefined;
  const raccolta = corpo.ownerDocument.createElement('div');
  let nodo = riassunto.nextElementSibling;
  while (nodo && nodo.tagName !== 'P') {
    if (nodo.tagName === 'BUTTON' && /^(Vedi|Altre)/.test(nodo.textContent)) nodo.click();
    else raccolta.appendChild(nodo.cloneNode(true));
    nodo = nodo.nextElementSibling;
  }
  return raccolta;
}

function sommari(corpo) {
  return Array.from(corpo.querySelectorAll('p.sc-desc'))
    .filter((d) => /— \d+ voc/.test(d.textContent))
    .map((d) => d.textContent);
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
  /* **Dal 20/09 le condizioni di sistema hanno una parte loro** (spec §4D):
     non stanno piu' in un gruppo «senza autore» in mezzo alle cose della
     casa, ma sotto «Integrazioni e log». La proprieta' che questa prova
     custodisce non cambia: nessun autore, nessun «dal» inventato, e la
     condizione non finisce sotto l'osservatore. */
  const testo = corpo.textContent;
  assert.deepEqual(sommari(corpo), ['Deciso dall’osservatore — 1 voce']);
  assert.match(testo, /Integrazioni e log \(1, in 1 integrazione\)/);
  assert.match(testo, /Nessuno le ha decise/);
  assert.doesNotMatch(testo, /dal/, 'da_quando_ts è null per costruzione: nessuna data inventata');
  assert.doesNotMatch(testo, /null/);
  const osservatore = gruppo(corpo, 'Deciso dall’osservatore');
  assert.doesNotMatch(osservatore.textContent, /sonos/,
    "la condizione non finisce sotto l'osservatore");
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
  /* Le ~30 condizioni di sistema portano tutte la stessa frase (watcher.py),
     e ripeterla trenta volte e' rumore. **Dal 20/09 il motivo condiviso si
     dice nella riga di riassunto del gruppo**, che e' anche il posto in cui
     si legge senza aprire niente.

     Mutazione che la uccide: `motivoComune` che torna sempre `''` -- il
     motivo torna su ogni riga; oppure che lo dice anche con motivi diversi
     -- il gruppo qui sotto perderebbe uno dei due. */
  const { corpo } = rendiScope(paginaScope({
    watching: [
      voce('climate.camera_t', { motivo: 'sta nell’obiettivo', autore: 'observer' }),
      voce('light.salotto', { motivo: 'sta nell’obiettivo', autore: 'observer' }),
      voce('sensor.co2', { motivo: 'sta nell’obiettivo', autore: 'observer' }),
      voce('light.cucina', { motivo: 'me l’hai chiesto tu', autore: 'owner' }),
    ],
  }));

  const osservatore = gruppo(corpo, 'Deciso dall’osservatore');
  const riassunto = sommari(corpo).filter((t) => t.indexOf('osservatore') >= 0)[0];
  assert.match(riassunto, /sta nell’obiettivo/, 'il motivo condiviso si dice nel riassunto');
  const occorrenze = osservatore.textContent.split('sta nell’obiettivo').length - 1;
  assert.equal(occorrenze, 0, 'il motivo condiviso non si ripete su ogni riga');
  const tuo = sommari(corpo).filter((t) => t.indexOf('da te') >= 0)[0];
  assert.doesNotMatch(tuo, /me l’hai chiesto tu/,
    'un gruppo di una voce sola non ha un motivo «condiviso»: sta sulla riga');
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
  /* **Dal 20/09 si raggruppa per TIPO di cosa** (spec §4D): i 280 lasciati
     fuori della casa vera portano 128 motivi distinti scritti in prosa, e per
     motivo non si raggruppano. Il motivo si legge aprendo il tipo, ed e' li'
     che ci si accorge se il modello ha scartato qualcosa che contava. */
  assert.match(corpo.textContent, /sensor — 1 soggetto/);
  const fuori = gruppo(corpo, '1 soggetti, in 1 tipo di cosa');
  assert.ok(fuori, 'riassunti trovati: ' + sommari(corpo).join(' | '));
  const vedi = Array.from(fuori.querySelectorAll('button')).filter((b) => b.textContent.startsWith('Vedi'))[0];
  if (vedi) vedi.click();
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
  /* **L'ordine e' cambiato il 20/09** (spec §4D): l'obiettivo, i tre numeri,
     la riconsiderazione -- poi gli elenchi, che sono lunghi. Prima la
     riconsiderazione era quarta, dopo due elenchi da centocinquanta righe. */
  assert.deepEqual(titoli(corpo), ['L’obiettivo', 'La riconsiderazione', 'Cosa guardo', 'Lasciato fuori', 'I tentativi', 'Quanto scrive al giorno']);
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
  /* Il cancello del collaudo E2: la resa vecchia scriveva `v.soggetto` tale e
     quale. **Nella forma nuova** i soggetti tecnici stanno sotto
     «Integrazioni e log», e si vedono aprendo il loro gruppo -- il cancello
     vale li' dentro, dove le righe vivono adesso.

     Mutazione dichiarata: in `rigaDecisione` sostituire `d.primary` con
     `v.soggetto` fa arrossire l'assert qui sotto. */
  const { corpo, document } = rendiScope(paginaScope({
    watching: [
      condizione('integrazione:01K2CK4GG287VKK18M5J788MRQ'),
      condizione('log:aioamazondevices@components/alexa_devices/coordinator.py:192'),
      condizione('log:homeassistant.components.hydrawise@helpers/update_coordinator.py:481'),
      condizione('log:custom_components.zcsazzurro.api@custom_components/zcsazzurro/api.py:202'),
      condizione('problema:light.termostato_soggiorno'),
      condizione('automazione:automation.spegni_luci_notte'),
    ],
  }));

  // Si aprono TUTTI gli elenchi, anche quelli dentro le righe: il cancello
  // guarda ogni riga che un umano puo' arrivare a vedere.
  for (let giro = 0; giro < 4; giro++) {
    Array.from(corpo.querySelectorAll('button'))
      .filter((b) => (b.textContent.startsWith('Vedi') || b.textContent.startsWith('Altre')) && b.getAttribute('aria-expanded') !== 'true')
      .forEach((b) => b.click());
  }
  const righe = Array.from(corpo.querySelectorAll('.sc-row'));
  assert.ok(righe.length >= 6, 'le righe dei soggetti tecnici non si sono aperte: ' + righe.length);
  righe.forEach((riga, i) => {
    const primo = riga.querySelector('.text-mono');
    if (!primo) return;
    assert.doesNotMatch(primo.textContent, /^(log|integrazione|problema|automazione):/,
      `riga ${i}: un prefisso tecnico e' rimasto a schermo tale e quale: "${primo.textContent}"`);
  });
  assert.doesNotMatch(document.body.textContent, /components\/hassio\/handler\.py/,
    'il percorso del sorgente non sta sulla riga');
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




test("seam _rendiScope: un entity_id nudo viene dichiarato per quello che è (l'endpoint non porta nomi)", () => {
  /* `GET /api/mind/watching` manda gli entity_id, non i nomi: la pagina non
     spaccia un identificativo per un nome, lo DICHIARA.

     Mutazione che la uccide: togliere la dichiarazione da `rigaDecisione`. */
  const { corpo } = rendiScope(paginaScope({ watching: [voce('climate.camera_t')] }));
  Array.from(corpo.querySelectorAll('button'))
    .filter((b) => b.textContent.startsWith('Vedi')).forEach((b) => b.click());

  const riga = corpo.querySelector('.sc-row');
  assert.ok(riga, 'nessuna riga disegnata');
  assert.match(riga.textContent, /identificatore/i);
  assert.match(riga.textContent, /climate\.camera_t/);
});

test("seam _rendiScope: la dichiarazione «identificatore» sta sulle righe senza nome, non su quelle che un nome ce l'hanno", () => {
  /* **La premessa della prova vecchia non esiste piu'**: dal 20/09 i soggetti
     tecnici non stanno in un gruppo per autore insieme alle entita' -- si
     separano per FORMA del soggetto (spec §4D), quindi un gruppo misto non
     nasce. La proprieta' che resta, e che conta, e' un'altra: la
     dichiarazione si mette dove distingue.

     Mutazione che la uccide: dichiararle tutte, o nessuna. */
  const { corpo } = rendiScope(paginaScope({
    watching: [
      voce('lock.porta_garage', { autore: 'analyst' }),
      Object.assign(condizione('log:homeassistant.components.hydrawise@x.py:1'),
        { integrazione: 'hydrawise', nome: 'Hydrawise' }),
    ],
  }));
  for (let giro = 0; giro < 3; giro++) {
    Array.from(corpo.querySelectorAll('button'))
      .filter((b) => b.textContent.startsWith('Vedi') && b.getAttribute('aria-expanded') !== 'true')
      .forEach((b) => b.click());
  }
  const righe = Array.from(corpo.querySelectorAll('.sc-row'));
  const senzaNome = righe.filter((r) => /lock\.porta_garage/.test(r.textContent))[0];
  const conNome = righe.filter((r) => /Registro|Hydrawise/.test(r.textContent))[0];
  assert.match(senzaNome.textContent, /identificatore/i,
    'un entity_id nudo va dichiarato: nessuno gli ha dato un nome');
  assert.ok(conNome, 'la riga dell’integrazione non è stata disegnata');
  assert.doesNotMatch(conNome.textContent, /identificatore/i,
    'una voce già nominata non è un identificatore nudo');
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


/* -------------------------------------------------------------------------
   La forma della scheda (spec §4D), riscritta il 20/09/2026.

   Misurato sulla casa il 18/09: 153 soggetti guardati (114 cose della casa e
   39 tecnici, da 23 integrazioni), 280 lasciati fuori con 128 motivi distinti
   scritti in prosa. La scheda li elencava uno per uno dentro dei `<details>`
   -- 50 KB di testo, e i `summary` alti 21-23 px che la spec §6 vieta.
   ------------------------------------------------------------------------- */

function apriIn(corpo, etichetta) {
  const b = [...corpo.querySelectorAll('button')]
    .filter((x) => x.textContent.indexOf(etichetta) >= 0)[0];
  if (b) b.click();
  return b;
}

function moltiSoggetti(quanti, dominio) {
  const voci = [];
  for (let i = 0; i < quanti; i++) voci.push(voce(dominio + '.cosa_' + i));
  return voci;
}

test('seam _rendiScope: in testa i TRE numeri, e la riconsiderazione prima di cosa guardo', () => {
  /* Spec §4D: «L'obiettivo per primo (è la voce del proprietario), poi tre
     numeri -- guardati, lasciati fuori, righe al giorno -- e la
     riconsiderazione». Oggi la riconsiderazione era quarta, dopo due elenchi
     da centocinquanta righe.

     Mutazione che la uccide: rimettere la riconsiderazione dopo «Lasciato
     fuori». */
  const { corpo } = rendiScope(paginaScope({
    watching: moltiSoggetti(4, 'light'),
    fuori: [{ soggetto: 'sensor.x', motivo: 'non riguarda l’obiettivo', autore: 'observer', deciso_ts: 1787000000 }],
    volume: [{ giorno: '2026-09-19', righe: 13945 }],
  }));

  const testo = corpo.textContent;
  assert.match(testo, /4 guardati/);
  assert.match(testo, /1 lasciato fuori/);
  assert.match(testo, /13\.945 righe/);
  assert.ok(testo.indexOf('La riconsiderazione') < testo.indexOf('Cosa guardo'),
    'la riconsiderazione sta ancora dopo gli elenchi');
});

test('seam _rendiScope: «Cosa guardo» separa le cose della casa dalle integrazioni', () => {
  /* Misurato: 114 cose della casa e 39 soggetti tecnici in un elenco solo.
     Sono due domande diverse -- «cosa guardo della casa» e «quali
     integrazioni mi stanno dando problemi» -- e stavano in una colonna.

     Mutazione che la uccide: un gruppo solo per autore, come prima. */
  const { corpo } = rendiScope(paginaScope({
    watching: moltiSoggetti(4, 'light').concat([
      Object.assign(condizione('log:homeassistant.components.hassio.handler@x.py:1'),
        { integrazione: 'hassio', nome: 'Hassio' }),
      Object.assign(condizione('log:homeassistant.components.hassio.http@y.py:2'),
        { integrazione: 'hassio', nome: 'Hassio' }),
      Object.assign(condizione('log:aioamazondevices@z.py:3'),
        { integrazione: 'aioamazondevices', nome: 'Aioamazondevices' }),
    ]),
  }));

  const testo = corpo.textContent;
  assert.match(testo, /Le cose della casa \(4\)/);
  assert.match(testo, /Integrazioni e log \(3, in 2 integrazioni\)/,
    'i tre logger del Supervisor sono UNA integrazione');
  assert.match(testo, /Hassio/);
  assert.doesNotMatch(testo, /hassio\.handler@/,
    'il percorso del sorgente sta nel dettaglio, non sulla riga');
});

test('seam _rendiScope: «Lasciato fuori» si raggruppa per TIPO di cosa, non per motivo', () => {
  /* Misurato il 18/09: 280 soggetti e **128 motivi distinti** scritti in
     prosa dal modello. Per motivo non si raggruppano; per tipo sì -- i primi
     otto tipi coprono 226 dei 280.

     Mutazione che la uccide: tornare a raggruppare per autore. */
  const fuori = [];
  for (let i = 0; i < 12; i++) {
    fuori.push({ soggetto: 'sensor.s' + i, motivo: 'motivo numero ' + i,
      autore: 'observer', deciso_ts: 1787000000 });
  }
  for (let i = 0; i < 3; i++) {
    fuori.push({ soggetto: 'button.b' + i, motivo: 'un comando, non una misura',
      autore: 'observer', deciso_ts: 1787000000 });
  }
  const { corpo } = rendiScope(paginaScope({ fuori }));

  const testo = corpo.textContent;
  assert.match(testo, /15 lasciati fuori/);
  assert.match(testo, /sensor — 12/, 'il tipo con più soggetti non è in testa');
  assert.match(testo, /button — 3/);
});

test('seam _rendiScope: il motivo di una singola esclusione si legge, aperto il suo tipo', () => {
  /* «Il motivo scritto dal modello si legge sulla riga, aperto il gruppo: è
     lì che ci si accorge se ha scartato qualcosa che contava» (spec §4D).

     Mutazione che la uccide: mostrare solo i conteggi per tipo. */
  const fuori = [];
  for (let i = 0; i < 6; i++) {
    fuori.push({ soggetto: 'camera.c' + i, motivo: 'Comando PTZ di una telecamera, non riguarda energia',
      autore: 'observer', deciso_ts: 1787000000 });
  }
  const { corpo } = rendiScope(paginaScope({ fuori }));
  apriIn(corpo, 'Vedi');

  assert.match(corpo.textContent, /Comando PTZ di una telecamera/);
});

test('seam _rendiScope: nessun «summary» negli elenchi di questa scheda (spec §6)', () => {
  /* Il cancello della forma: i `summary` sono alti 21-23 px, sotto la soglia
     del tocco, ed è la misura per cui la spec vieta di usarli per aprire un
     elenco. Erano il modo in cui questa scheda apriva ogni gruppo.

     Mutazione che la uccide: rimettere `renderDecisionGroup` coi `<details>`. */
  const { corpo } = rendiScope(paginaScope({
    watching: moltiSoggetti(6, 'light'),
    fuori: [{ soggetto: 'sensor.x', motivo: 'no', autore: 'observer', deciso_ts: 1787000000 }],
  }));

  assert.equal(corpo.querySelectorAll('summary').length, 0);
});
