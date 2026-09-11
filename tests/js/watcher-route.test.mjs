import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { JSDOM } from 'jsdom';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Giro di correzioni sulla pagina «L'osservatore» (config/watcher-route.js),
   guida-ux-osservatore in .superpowers/sdd/2026-08-26-l-osservatore/pagina-brief.md.

   E' anche il primo file di test di questa pagina: fino a qui `_rendiOsservate`
   e `_rendiOggetti` erano una seam PROMESSA da un commento ("seam di test: la
   resa va pinnata senza passare da fetch") e mai usata da nessun test -- oltre
   quattrocento righe di resa senza nessuna rete. Le sezioni "seam:" qui sotto
   chiudono quel buco usando esattamente quelle due funzioni.

   Dal 11/09/2026 (fetta «i tre attori») `_rendiOsservate(corpo, elenco)` e'
   diventata `_rendiScope(corpo, payload)`: la sezione 01 non rende piu' un
   elenco di voci per gamba, rende le cinque parti di `GET /api/mind/watching`
   (obiettivo, cosa si guarda, lasciato fuori, riconsiderazione, volume). */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'config');
const SORGENTE = readFileSync(join(CONFIG_DIR, 'watcher-route.js'), 'utf8');

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/watcher-route.js'];

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

/* Il finto server: distingue le due rotte per prefisso, come fa la pagina
   vera (`api/mind/watching`, `api/mind/facts[?day=...]`). */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url) => {
    const u = String(url);
    chiamate.push(u);
    if (u.indexOf('api/mind/watching') === 0) {
      if (opts.osservateRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.watching !== undefined ? opts.watching : paginaScope(),
        opts.osservateStatus);
    }
    if (u.indexOf('api/mind/facts') === 0) {
      if (opts.oggettiRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.facts !== undefined ? opts.facts : { facts: [] },
        opts.oggettiStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
}

// Rilievo 2 del brief «css-morto»: il messaggio "nessun episodio" (sezione
// 02, «Cosa è successo») va letto sul SUO nodo, non su tutto il contenitore
// -- la descrizione statica della sezione 02 contiene ANCH'ESSA "00:20"
// ("scritti alle 00:20, sul fuso della CASA"), quindi cercare `/00:20/` su
// tutto `#route-outlet` resta sempre soddisfatta, a prescindere dal testo
// del messaggio vero e proprio (mutazione provata: cambiando il messaggio in
// "prima o poi" i vecchi test restavano verdi). Il messaggio è l'unico
// `.sc-desc` dentro il `.sc-body` della seconda `.section-card`.
function testoMessaggioOggetti(document) {
  const card2 = document.querySelectorAll('.section-card')[1];
  const msg = card2 && card2.querySelector('.sc-body .sc-desc');
  assert.ok(msg, 'non trovo il nodo del messaggio dentro la sezione 02 (struttura pagina cambiata?)');
  return msg.textContent;
}

// -- date locali, calcolate come le calcola la pagina (fuso del browser di
//    chi fa girare il test), MAI hardcoded: una data fissa scritta nel test
//    diventerebbe falsa il giorno dopo. --
function pad2(n) { return n < 10 ? '0' + n : String(n); }
function isoLocale(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
function giornoFa(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoLocale(d);
}
function ggmmaaaa(iso) {
  const [y, m, g] = iso.split('-');
  return g + '/' + m + '/' + y;
}

const OGGI = giornoFa(0);
const IERI = giornoFa(1);
const VECCHIO = giornoFa(40); // sicuramente né oggi né ieri, qualunque sia la data di corsa

// ---------------------------------------------------------------------------
// Ortografia: «è» non «e’»/«E’» (rilievo 2, e rilievo 3 del brief «css-morto»)
// — sulle stringhe VISIBILI
// ---------------------------------------------------------------------------

// Rileva il refuso "e’ "/"E’ " al posto di "è "/"È ", ovunque compaia.
// Rilievo 3 del brief «css-morto»: la vecchia guardia escludeva i casi
// "preceduti da una lettera" per difendersi da una parola tipo "che’ " che
// NON esiste in italiano -- e con quella difesa saltava esattamente
// "perche’ " e "cioe’ ", che sono la forma in cui il refuso compare più
// spesso, e non copriva affatto la maiuscola "E’ ". Nessuna esclusione:
// verificato (grep) che oggi nessun modulo di config/ contiene "e’ "
// preceduto da una lettera, quindi togliere il filtro non introduce falsi
// positivi sul codice reale.
function trovaRefusiApostrofo(testo) {
  const trovati = [];
  for (const m of testo.matchAll(/[eE]’ /g)) trovati.push(m.index);
  return trovati;
}

test('nessun modulo di config/ contiene il refuso "e’ "/"E’ " al posto di "è "/"È " (rilievo 2)', () => {
  // Guardia a livello di prodotto, non solo di questa pagina: scansiona TUTTI
  // i moduli di config/, cosi' il refuso non puo' tornare silenzioso da
  // nessun'altra parte della SPA di configurazione -- il brief lo chiede
  // esplicitamente ("e' un refuso che tornera'").
  const file = readdirSync(CONFIG_DIR).filter((f) => f.endsWith('.js'));
  assert.ok(file.length > 5, 'la cartella config/ deve contenere piu\' di 5 script (verifica del percorso)');
  const trovati = [];
  for (const f of file) {
    const testo = readFileSync(join(CONFIG_DIR, f), 'utf8');
    for (const start of trovaRefusiApostrofo(testo)) {
      const riga = testo.slice(0, start).split('\n').length;
      trovati.push(f + ':' + riga);
    }
  }
  assert.deepEqual(trovati, [], 'refuso "e’ "/"E’ " (invece di "è "/"È ") trovato in: ' + trovati.join(', '));
});

test('rilievo 3: la guardia del refuso cattura "perche’ " e "cioe’ ", non solo le forme isolate', () => {
  // Provato iniettando entrambe le varianti (nella stringa del test, non in
  // un file vero): con la vecchia esclusione "preceduto da una lettera"
  // questo assert falliva (0 trovati, non 1) per entrambe.
  assert.equal(trovaRefusiApostrofo('lo dico perche’ serve davvero').length, 1,
    '"perche’ " deve essere rilevato');
  assert.equal(trovaRefusiApostrofo('cioe’ questo è il punto').length, 1,
    '"cioe’ " deve essere rilevato');
});

test('rilievo 3: la guardia del refuso cattura anche la maiuscola "E’ "', () => {
  assert.equal(trovaRefusiApostrofo('E’ vero, non funzionava.').length, 1);
});

test('mount: "Non sto guardando ancora niente" usa è, non e’', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /HIRIS è appena partito/);
  assert.match(testo, /è normale/);
});

test('mount: il sottotitolo usa è, non e’, e chiama il materiale "episodi"', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const sottotitolo = document.querySelector('.page-subtitle').textContent;
  assert.match(sottotitolo, /è il materiale/);
  assert.match(sottotitolo, /ricava episodi/);
});

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
  window.HirisWatcherRoute._rendiScope(corpo, payload);
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
  // Mutazione: `volume.sort(...)` o `.reverse()` prima del ciclo in
  // `renderVolume` (l'ordine dei giorni cambia); `pct` calcolato su una
  // costante invece che su `max` (le larghezze non tornano); `fmtCount`
  // sostituito da `String(n)` («4951» invece di «4.951»); `if (r.righe)
  // return` per saltare i giorni a zero (la settima riga sparisce).
  const { corpo } = rendiScope(paginaScope({
    volume: [
      { giorno: '2026-09-04', righe: 29227 },
      { giorno: '2026-09-05', righe: 4951 },
      { giorno: '2026-09-06', righe: 0 },
    ],
  }));
  const righe = Array.from(corpo.querySelectorAll('ul > li'));
  assert.equal(righe.length, 3);
  assert.deepEqual(righe.map((li) => li.querySelector('.field-hint').textContent),
    ['04/09/2026', '05/09/2026', '06/09/2026'], 'dal più vecchio: una tendenza si legge in avanti');
  assert.deepEqual(righe.map((li) => li.querySelector('.text-mono').textContent),
    ['29.227 righe', '4.951 righe', '0 righe']);
  // Il CSSOM RISERIALIZZA il valore letto («100.0%» -> «100%», «0.0%» ->
  // «0%»; stesso comportamento gia' misurato per `display:flex` piu' sopra):
  // si confronta il numero, non la stringa scritta dalla pagina.
  const larghezze = righe.map((li) => parseFloat(li.querySelector('[aria-hidden="true"] > div').style.width));
  assert.equal(larghezze[0], 100, 'il giorno piu\' alto e\' il metro: barra piena');
  assert.equal(larghezze[1], Number((4951 / 29227 * 100).toFixed(1)));
  assert.equal(larghezze[2], 0, 'un giorno a zero resta una barra vuota, non sparisce');
  assert.equal(corpo.querySelectorAll('canvas, svg').length, 0, 'barre CSS, niente canvas/SVG per sette numeri');
});

// -- Le cinque parti, in quest'ordine, e niente pavimento ---------------------------

test('seam _rendiScope: le cinque parti sono titoli veri (h3), nell\'ordine della spec, e il pavimento non affiora più', () => {
  // Mutazione: scambiare due chiamate in `renderScope` (l'ordine cambia);
  // `el('p', ...)` al posto di `el('h3', ...)` in `subheading` (un lettore
  // di schermo non salta più di parte in parte).
  const { corpo } = rendiScope(paginaScope({ watching: [voce('climate.camera_t')] }));
  assert.deepEqual(titoli(corpo), ['L’obiettivo', 'Cosa guardo', 'Lasciato fuori', 'La riconsiderazione', 'Quanto scrive al giorno']);
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
// Il campo Giorno: dentro il tema, con l'etichetta associata (rilievo 3)
// ---------------------------------------------------------------------------

test('mount: il campo Giorno entra nei selettori del tema (input[type=date] condiviso)', () => {
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');
  const blocchi = Array.from(css.matchAll(/input\[type=text\][^\n]*\{/g)).map((m) => m[0]);
  assert.equal(blocchi.length, 2,
    'attesi i due blocchi di stile condiviso per gli input (legacy + v5 moderno)');
  for (const blocco of blocchi) {
    assert.match(blocco, /input\[type=date\]/,
      'il selettore condiviso deve includere anche il campo Giorno: ' + blocco);
  }
});

test('mount: l\'etichetta «Giorno» è associata al campo data (for/id)', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const input = document.querySelector('input[type=date]');
  assert.ok(input, 'deve esserci un campo data');
  assert.ok(input.id, 'il campo data deve avere un id per essere raggiungibile da un\'etichetta');
  const label = Array.from(document.querySelectorAll('label')).find((l) => l.textContent === 'Giorno');
  assert.ok(label, 'deve esserci un\'etichetta «Giorno»');
  assert.equal(label.getAttribute('for'), input.id,
    'l\'etichetta deve puntare al campo con for/id, altrimenti per un lettore di schermo è anonimo');
});

test('mount: il campo Giorno entra ANCHE nel terzo blocco di stile (hiris-config-override.css, rilievo 4)', () => {
  // hiris-config.css porta due blocchi condiviso legacy+v5 (verificati sopra),
  // ma esiste un TERZO blocco -- con `!important`, quindi vince sempre --
  // in hiris-config-override.css: senza `input[type=date]` anche lì, il tema
  // scuro è a posto ma il campo Giorno resta con misure/spaziature diverse
  // da ogni altro campo del prodotto. Verificato col grep che non ce n'è un
  // quarto (`hiris-theme.css`/`hiris-chat.css` non definiscono liste di
  // `input[type=...]`): sono tre in tutto `static/`.
  const overrideCss = readFileSync(join(CONFIG_DIR, '..', 'hiris-config-override.css'), 'utf8');
  const blocco = overrideCss.match(/input\[type=text\][^\n]*\{/);
  assert.ok(blocco, 'il blocco condiviso di stile degli input in hiris-config-override.css non è più nella forma attesa');
  assert.match(blocco[0], /input\[type=date\]/,
    'il selettore condiviso in hiris-config-override.css deve includere anche il campo Giorno: ' + blocco[0]);
});

// ---------------------------------------------------------------------------
// Lo span dentro una riga flex si restringe davvero (rilievo 1 del brief
// «css-morto»): il selettore che azzera `min-width` deve corrispondere a uno
// span costruito ESATTAMENTE come lo costruisce la SPA, cioè figlio di un
// elemento il cui stile nasce da `style.cssText = 'display:flex;...'`, SENZA
// spazio dopo i due punti (letterale nel sorgente, vedi rigaOggetto() sotto).
// Il browser però RISERIALIZZA l'attributo `style` quando lo si legge,
// aggiungendo lo spazio ("display: flex;") — verificato qui con lo stesso
// comportamento di jsdom (nwsapi) e dal vivo in Chromium. Il selettore va
// estratto dal file vero, non riscritto qui: così la mutazione richiesta dal
// brief (rimettere `.section-card [style*="display:flex"] > span`, la forma
// morta) arrossisce questo test senza dover toccare altro.
// ---------------------------------------------------------------------------

test('CSS: il selettore che azzera min-width sugli span corrisponde a uno span costruito come lo costruisce la SPA (rilievo 1)', () => {
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');
  const ancora = css.indexOf('Terza recidiva');
  assert.ok(ancora > -1,
    'il commento «Terza recidiva» (che documenta il difetto) non è più nel CSS: aggiorna l\'ancora di questo test');
  const dopo = css.slice(ancora);
  const regola = dopo.match(/\*\/\s*\n([^\n{]+)\{\s*\n\s*min-width:\s*0;/);
  assert.ok(regola, 'nessuna regola `min-width: 0` subito dopo il commento «Terza recidiva»');
  const selettore = regola[1].trim();

  // Stessa struttura di rigaOggetto() in watcher-route.js: uno span
  // figlio diretto di una riga il cui style nasce da `style.cssText =
  // 'display:flex;...'`, dentro una `.section-card`.
  const dom = new JSDOM('<!doctype html><body><section class="section-card"><div class="sc-body"></div></section></body>');
  const { document } = dom.window;
  const corpo = document.querySelector('.sc-body');
  const testa = document.createElement('div');
  testa.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
  const span = document.createElement('span');
  span.className = 'text-mono field-hint';
  testa.appendChild(span);
  corpo.appendChild(testa);

  assert.equal(testa.getAttribute('style'), 'display: flex; align-items: center; gap: 8px; flex-wrap: wrap;',
    'il browser riserializza l\'attributo style CON lo spazio dopo i due punti (precondizione del difetto)');
  assert.ok(span.matches(selettore),
    'il selettore «' + selettore + '» estratto da hiris-config.css non corrisponde a uno span costruito come lo costruisce la SPA');
});

// ---------------------------------------------------------------------------
// «Riprova»: unica pagina di lettura che ne era priva (rilievo 4)
// ---------------------------------------------------------------------------

test('un errore nel leggere "cosa sto guardando" (503) offre Riprova, e il testo del messaggio non cambia', async () => {
  const { window, document } = montaConServer({ osservateStatus: 503, watching: {} });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è una lista vuota — è l’osservatore stesso ad essere fermo/,
    'il testo d\'errore a tre stati non si tocca (è dichiarato il migliore del pannello)');
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare, come nelle pagine sorelle');
});

test('un guasto di rete su "cosa sto guardando" offre Riprova, e il bottone rilancia la richiesta', async () => {
  const { window, document, chiamate } = montaConServer({ osservateRotto: true });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const primaDelClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  const retry = bottone(document, 'Riprova');
  assert.ok(retry, 'deve esserci un modo di riprovare');
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const dopoIlClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  assert.equal(dopoIlClick, primaDelClick + 1, 'il bottone deve rilanciare la stessa richiesta');
});

test('un errore nel leggere "cosa è successo" (503) offre Riprova', async () => {
  const { window, document } = montaConServer({ oggettiStatus: 503, facts: {} });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è una lista vuota — è l’archivio stesso ad essere fermo/);
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare anche per gli episodi');
});

test('un guasto di rete su "cosa è successo" offre Riprova, e il bottone rilancia la richiesta con lo stesso giorno', async () => {
  const { window, document, chiamate } = montaConServer({ oggettiRotto: true });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const chiamateOggettiPrima = chiamate.filter((u) => u.indexOf('facts') !== -1);
  const retry = bottone(document, 'Riprova');
  assert.ok(retry);
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const chiamateOggettiDopo = chiamate.filter((u) => u.indexOf('facts') !== -1);
  assert.equal(chiamateOggettiDopo.length, chiamateOggettiPrima.length + 1);
  assert.equal(chiamateOggettiDopo[chiamateOggettiDopo.length - 1], chiamateOggettiPrima[0],
    'il retry deve rilanciare la stessa richiesta (stesso giorno), non perdere il filtro');
});

// ---------------------------------------------------------------------------
// Il primo giorno: quando comparirà qualcosa (rilievo 5) — «episodi» (6a)
// ---------------------------------------------------------------------------

test('nessun episodio per IERI: dice quando tornare (00:20), niente data ISO, niente ipotesi debole', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisWatcherRoute.mount();
  await tick(20); // il campo nasce su "ieri" di default

  const messaggio = testoMessaggioOggetti(document);
  assert.match(messaggio, /episodio/, 'parola utente: episodio, non oggetto');
  assert.match(messaggio, /00:20/, 'deve dire quando tornare (nel messaggio, non altrove nella pagina)');
  assert.match(messaggio, new RegExp(ggmmaaaa(IERI).replace(/\//g, '\\/')), 'la data va in gg/mm/aaaa');
  assert.doesNotMatch(messaggio, /\d{4}-\d{2}-\d{2}/, 'nessuna data in formato ISO nel testo');
  assert.doesNotMatch(messaggio, /potrebbe non aver fatto niente di osservabile/,
    'il primo giorno non deve seminare il dubbio che la casa non abbia fatto niente: è quasi impossibile');
});

test('nessun episodio per OGGI: stesso trattamento del primo giorno (ieri/oggi sono lo stesso caso)', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const input = document.querySelector('input[type=date]');
  input.value = OGGI;
  input.dispatchEvent(new window.Event('change'));
  await tick(20);

  const messaggio = testoMessaggioOggetti(document);
  assert.match(messaggio, /00:20/, 'deve dire quando tornare (nel messaggio, non altrove nella pagina)');
  assert.doesNotMatch(messaggio, /potrebbe non aver fatto niente di osservabile/);
});

test('nessun episodio per un giorno VECCHIO: l\'ipotesi doppia resta, ma la data è in gg/mm/aaaa', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const input = document.querySelector('input[type=date]');
  input.value = VECCHIO;
  input.dispatchEvent(new window.Event('change'));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /potrebbe non aver fatto niente di osservabile/,
    'per un giorno vecchio l\'ipotesi doppia attuale va bene, il brief lo dice esplicitamente');
  assert.match(testo, new RegExp(ggmmaaaa(VECCHIO).replace(/\//g, '\\/')));
  assert.doesNotMatch(testo, /\d{4}-\d{2}-\d{2}/);
});

test('nessun episodio SENZA filtro (bottone "più recenti"): parla di episodi', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const btnRecenti = bottone(document, 'Vedi i più recenti, senza filtro');
  btnRecenti.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /episodio/);
  assert.doesNotMatch(testo, /\boggetto\b/);
});

// ---------------------------------------------------------------------------
// Il fuso senza numero inventato (rilievo 12)
// ---------------------------------------------------------------------------

test('mount: la sezione 02 non dichiara una differenza di fuso in ore', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const descrizioni = Array.from(document.querySelectorAll('.sc-desc')).map((p) => p.textContent);
  const desc02 = descrizioni.find((d) => /fuso della CASA/.test(d) || /fuso di/.test(d));
  assert.ok(desc02, 'deve esserci la descrizione della sezione 02');
  assert.doesNotMatch(desc02, /un'ora|un’ora/, 'la cifra "un\'ora" non è misurata: il caso reale (stesso fuso) ha errore zero');
});

// ---------------------------------------------------------------------------
// La gerarchia della riga: il fatto prima dell'identificatore (rilievo 7)
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: l\'identificatore è in monospazio attenuato, il contenuto è il testo prominente', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'climate.riscaldamento_camera',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { stato: 'acceso' },
  }], null);

  const identificatore = corpo.querySelector('.text-mono');
  assert.ok(identificatore, 'l\'identificatore deve portare la classe text-mono (rottura + tipografia attenuata)');
  assert.equal(identificatore.textContent, 'climate.riscaldamento_camera');
  assert.doesNotMatch(identificatore.className, /\bagent-badge\b/,
    'l\'identificatore non è il badge del genere: sono due elementi distinti nella stessa riga');

  // Il paragrafo col fatto (orario + stato) non deve più essere una nota a
  // margine (`field-hint`): deve leggersi come contenuto.
  const paragrafi = Array.from(corpo.querySelectorAll('p'));
  const rigaFatto = paragrafi.find((p) => /acceso/.test(p.textContent) && /→/.test(p.textContent));
  assert.ok(rigaFatto, 'deve esserci un paragrafo col periodo e lo stato');
  assert.doesNotMatch(rigaFatto.className, /\bfield-hint\b/,
    'il fatto non deve avere la classe attenuata riservata prima a lui: ora è il contenuto principale');
});

// ---------------------------------------------------------------------------
// Seam _rendiOggetti: i sei generi, i comprimari, le misure — senza rete
// (rilievo 9: la resa era priva di qualunque test)
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: un oggetto di energia mostra da/a e la differenza col segno', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_forno',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { valore_iniziale: 12.5, valore_finale: 15.0, differenza: 2.5 },
  }], null);
  assert.match(corpo.textContent, /da 12\.5 a 15/);
  assert.match(corpo.textContent, /\+2\.5/);
});

test('seam _rendiOggetti: un oggetto di energia con differenza non calcolabile lo dichiara, mai un NaN silenzioso', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.contatore',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 5, valore_finale: 'unavailable', differenza: null },
  }], null);
  assert.match(corpo.textContent, /non calcolabile/);
  assert.doesNotMatch(corpo.textContent, /NaN/);
});

test('seam _rendiOggetti: un episodio di energia con direzione DICHIARATA la mostra in italiano e distingue la provenienza', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_prodotta',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { valore_iniziale: 10, valore_finale: 25, differenza: 15,
            direzione: 'produzione', provenienza: 'dichiarata' },
  }], null);
  assert.match(corpo.textContent, /[Pp]roduzione/,
    'la direzione va mostrata in italiano leggibile, non il valore grezzo');
  assert.match(corpo.textContent, /[Dd]ichiarat/,
    'la provenienza "dichiarata" deve comparire nel testo');
});

test('seam _rendiOggetti: un episodio di energia con direzione DEDOTTA si distingue visibilmente dalla dichiarata', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const dichiarato = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(dichiarato, [{
    id: 1, genere: 'energia', protagonista: 'sensor.a',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1,
            direzione: 'prelievo', provenienza: 'dichiarata' },
  }], null);
  const dedotto = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(dedotto, [{
    id: 2, genere: 'energia', protagonista: 'sensor.b',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1,
            direzione: 'prelievo', provenienza: 'dedotta' },
  }], null);
  assert.match(dedotto.textContent, /[Dd]edott/);
  // Le due provenienze non devono rendersi con lo stesso badge: e' il
  // requisito del mandato, «distingue visibilmente le due provenienze».
  const badgeDichiarato = Array.from(dichiarato.querySelectorAll('.agent-badge')).pop();
  const badgeDedotto = Array.from(dedotto.querySelectorAll('.agent-badge')).pop();
  assert.ok(badgeDichiarato && badgeDedotto, 'entrambi gli episodi devono avere un badge di provenienza');
  assert.notEqual(badgeDichiarato.className, badgeDedotto.className,
    'la classe del badge deve differire fra dichiarata e dedotta');
});

test('seam _rendiOggetti: un episodio di energia SENZA direzione nota non mostra nessun badge di provenienza in piu', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_ignota',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1 },
  }], null);
  // Un solo badge: quello del genere ("Energia"). Nessun secondo badge di
  // provenienza quando il campo `direzione` non c'e' affatto -- il mandato
  // vieta esplicitamente una "sconosciuta" travestita da dato.
  assert.equal(corpo.querySelectorAll('.agent-badge').length, 1);
});

test('seam _rendiOggetti: un guasto ancora aperto lo dice esplicitamente', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'problema:hue.bridge_offline',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'aperto' },
  }], null);
  assert.match(corpo.textContent, /ancora aperto/);
  assert.match(corpo.textContent, /in corso a fine giornata/,
    'un fine_ts nullo si dichiara come "in corso a fine giornata", non "ancora in corso" ' +
    '(cancello-rilascio-brief.md, punto 2): l\'aggregazione e\' per giornata, e non puo\' ' +
    'promettere una continuita\' che non tiene oltre la mezzanotte');
  assert.match(corpo.textContent, /Problema Home Assistant: hue\.bridge_offline/,
    'un protagonista "problema:" diventa un nome leggibile, come in tree-route.js');
});

// Giro di correzioni sul Task 7: `protagonistName` traduceva solo
// `problema:`/`integrazione:` -- un `log:` o un `automazione:` SENZA
// `corpo.titolo` (l'evento non porta un nome, o `message[0]` manca)
// ricadeva sul `return s` finale, mostrando l'identificatore opaco sulla
// pagina che una persona legge. Mutazione ESEGUITA per provarlo: togliere
// i due `if` aggiunti da `protagonistName` -- entrambi i test qui sotto
// tornano rossi sul rispettivo `assert.match` (il testo mostrerebbe
// l'identificatore grezzo invece del nome leggibile).
test('seam _rendiOggetti: un `log:` senza titolo diventa un nome leggibile, non l\'identificatore grezzo', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'log:homeassistant.components.lifx@lifx/light.py:120',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'ERROR' },
  }], null);
  assert.match(corpo.textContent,
    /Voce del registro di Home Assistant: homeassistant\.components\.lifx@lifx\/light\.py:120/,
    'un protagonista "log:" senza titolo deve diventare un nome leggibile, non restare grezzo');
});

test('seam _rendiOggetti: un `automazione:` senza titolo diventa un nome leggibile, non l\'identificatore grezzo', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'automazione:automation.rotta',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'error' },
  }], null);
  assert.match(corpo.textContent, /Automazione: automation\.rotta/,
    'un protagonista "automazione:" senza titolo deve diventare un nome leggibile, non restare grezzo');
});

// Nit del revisore sul cancello E2 (07/09/2026): `watcher.py` scrive sempre
// `<logger>@<file>:<riga>` per un `log:`, quindi un soggetto senza `@` non
// capita OGGI -- ma la resa non deve dipendere da quella garanzia per essere
// corretta. Mutazione ESEGUITA per provarlo: ripristinare
// `p.logger + '@' + p.location` (senza il controllo `p.location ? ... : ''`)
// fa tornare rosso l'`assert.doesNotMatch` qui sotto (il testo mostrerebbe
// "loggersenzachiocciola@", con la "@" appesa e nulla dopo).
test('seam _rendiOggetti: un `log:` senza `@` (nessun percorso) non lascia una "@" appesa al nome', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'log:loggersenzachiocciola',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'ERROR' },
  }], null);
  assert.match(corpo.textContent, /Voce del registro di Home Assistant: loggersenzachiocciola/);
  assert.doesNotMatch(corpo.textContent, /loggersenzachiocciola@/,
    'senza un percorso dopo la "@", la "@" non deve comparire da sola');
});

// Onda finale, rilievo 1 (revisione di ramo): dal Task 2 `corpo.stato` porta
// la condizione VERA (`setup_retry`, `setup_error`, ...), mai la costante
// "aperto" -- ma un'integrazione con quella condizione e' comunque APERTA
// (`fine_ts: null`). Il codice di prima decideva "ancora aperto" da
// `c.stato === 'aperto'`: per questo episodio sarebbe rimasto rosso muto,
// mostrando solo "stato: setup_retry" senza mai dire che e' ancora aperto.
// Mutazione ESEGUITA per provarlo: ripristinare
// `c.stato === 'aperto' ? 'ancora aperto' : 'stato: ' + (c.stato || '?')`
// in `mainPhrase` -- il test torna rosso su
// `assert.match(corpo.textContent, /ancora aperto/)` (il testo diventa
// "stato: setup_retry", senza "ancora aperto").
test('seam _rendiOggetti: un\'integrazione con una condizione vera (non "aperto") e fine_ts nullo e\' comunque "ancora aperto"', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'integrazione:01ABC',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'setup_retry', dominio: 'lifx', titolo: 'Abat-jour' },
  }], null);
  assert.match(corpo.textContent, /ancora aperto/,
    '"in corso" si decide da fine_ts, non da uno stato che dal Task 2 non vale mai "aperto"');
  assert.match(corpo.textContent, /stato: setup_retry/,
    'la condizione vera resta mostrata, come informazione nuova');
  assert.match(corpo.textContent, /Abat-jour/,
    'il nome leggibile (corpo.titolo) sostituisce l\'identificativo opaco quando c\'e\'');
  assert.doesNotMatch(corpo.textContent, /01ABC/,
    'con titolo/dominio presenti l\'identificativo opaco non deve piu\' comparire');
});

// Onda finale, rilievo 1 (revisione di ramo): per un `problema:` `stato`
// resta "aperto" anche a episodio CHIUSO (spec §2.3) -- il difetto misurato
// e rimasto sullo schermo perche' il codice di prima leggeva "ancora
// aperto" da `c.stato`, non da `fine_ts`. Mutazione ESEGUITA per provarlo:
// stessa mutazione di sopra (ripristinare la vecchia `mainPhrase` per
// "guasto") -- il test torna rosso su
// `assert.doesNotMatch(corpo.textContent, /ancora aperto/)` (l'episodio
// chiuso mostrerebbe di nuovo "ancora aperto").
//
// Collaudo usabilita' 3.22, rilievo 2 (07/09/2026): finche' `mainPhrase`
// scriveva SEMPRE "· stato: X" quando `c.stato != null`, questo stesso test
// affermava «stato: aperto» accanto a «chiuso» -- «06/09 08:54 → 06/09
// 19:04 · chiuso · stato: aperto», due parole opposte a tre centimetri di
// distanza, misurato dal vivo. `c.stato === 'aperto'` e' la STESSA parola
// che "chiuso"/"ancora aperto" ha appena scritto sotto un'altra forma: si
// toglie SOLO in questo caso, non per gli altri valori (vedi il test subito
// sotto, che li tiene). Mutazione ESEGUITA per provarlo: togliere
// `if (c.stato === 'aperto') return aperto;` da `mainPhrase` -- il test
// torna rosso sull'ultimo `assert.doesNotMatch` (il testo mostrerebbe di
// nuovo "stato: aperto").
test('seam _rendiOggetti: un `problema:` con stato ancora "aperto" ma fine_ts valorizzato non dice "ancora aperto", ne\' "stato: aperto"', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'problema:hue.bridge_offline',
    inizio_ts: 1, fine_ts: 2,
    corpo: { stato: 'aperto' },
  }], null);
  assert.doesNotMatch(corpo.textContent, /ancora aperto/,
    'un episodio chiuso (fine_ts valorizzato) non deve mai dire "ancora aperto", ' +
    'anche se `corpo.stato` resta "aperto" per costruzione (spec §2.3)');
  assert.match(corpo.textContent, /chiuso/);
  assert.doesNotMatch(corpo.textContent, /stato: aperto/,
    '«chiuso · stato: aperto» e\' la contraddizione misurata dal collaudo: la parola "aperto" ' +
    'non deve ripetersi accanto a "chiuso"');
});

// Stesso principio, ma sul caso in cui l'episodio e' ANCORA aperto: "ancora
// aperto · stato: aperto" non e' una contraddizione (le due parole
// concordano), ma e' comunque una ripetizione letterale che non aggiunge
// niente -- il rilievo del collaudo non distingue i due casi, distingue
// SOLO se `stato` vale letteralmente "aperto". Mutazione ESEGUITA per
// provarlo: stessa di sopra -- il test torna rosso sull'`assert.doesNotMatch`
// (il testo mostrerebbe "ancora aperto · stato: aperto").
test('seam _rendiOggetti: un `problema:` ancora aperto con stato "aperto" non ripete la parola in "stato: aperto"', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'problema:hue.bridge_offline',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'aperto' },
  }], null);
  assert.match(corpo.textContent, /ancora aperto/);
  assert.doesNotMatch(corpo.textContent, /stato: aperto/,
    'la parola "aperto" non deve ripetersi come "stato:" -- non aggiunge un\'informazione nuova');
});

test('seam _rendiOggetti: comprimari e misure stanno dietro un rivelatore sincrono, chiuso di default', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  document.body.appendChild(corpo);

  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'light.lampadario',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: {
      stato: 'acceso',
      comprimari: ['light.lampadario_gruppo', 'switch.lampadario_interruttore'],
      misure: { 'sensor.temp_soggiorno': { da: 18.2, a: 21.0 } },
    },
  }], null);

  const btn = Array.from(corpo.querySelectorAll('button'))
    .find((b) => /c’era intorno/.test(b.textContent));
  assert.ok(btn, 'il rivelatore deve esserci quando ci sono comprimari o misure');
  const pannello = btn.nextElementSibling;
  assert.ok(pannello, 'deve esserci il pannello dei dettagli');
  assert.equal(pannello.hidden, true, 'il pannello nasce chiuso (`hidden`, non solo un CSS display)');

  btn.dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(pannello.hidden, false, 'il click deve aprire il pannello, e i dati sono già nel payload');
  assert.match(corpo.textContent, /light\.lampadario_gruppo/);
  assert.match(corpo.textContent, /switch\.lampadario_interruttore/);
  assert.match(corpo.textContent, /sensor\.temp_soggiorno.*da 18\.2 a 21/s);

  // rilievo 8c: «Nascondi» da solo perde il referente con più righe aperte.
  assert.notEqual(btn.textContent, 'Nascondi', 'il testo del rivelatore aperto deve avere un referente');
  assert.match(btn.textContent, /c’era intorno/);
});

test('seam _rendiOggetti: senza comprimari e senza misure non c\'è nessun rivelatore', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'presenza', protagonista: 'person.paolo',
    inizio_ts: 1, fine_ts: 2, corpo: { stato: 'a casa' },
  }], null);
  assert.equal(corpo.querySelectorAll('button').length, 0);
});

// ---------------------------------------------------------------------------
// Il bilancio dell'energia (mandato «il bilancio dell'energia», 27/08/2026):
// un oggetto al giorno per dispositivo, una QUANTITA' CON UNA FORMA, non un
// episodio. La forma reale del corpo è quella di `build_balance_body`
// (hiris/app/mind/facts.py): {totali:{dimensione:{valore,provenienza}},
// forma:{dimensione:[{ora,valore}...]}, momenti:{...}}, più `dispositivo`/`entita`
// aggiunti da `aggregate_day`. Prima di questa fetta il genere "bilancio"
// cadeva nel ramo di default di `mainPhrase` e mostrava «(nessun
// dettaglio)» — questi test bloccano quella regressione E vietano lo stampo
// dell'episodio («da X a Y», la freccia di `period()`).
// ---------------------------------------------------------------------------

// `forma[dimensione]` porta l'ORA VERA di ogni punto dal 27/08/2026 (mandato
// «la pagina del bilancio -- le correzioni», punto 6): non piu' una lista
// posizionale nuda, ma `[{"ora","valore"}, ...]` -- vedi `costruisci_corpo_
// bilancio` in `hiris/app/mind/facts.py`. Questo helper costruisce un
// ISO alla stessa ora LOCALE di questa macchina (stesso principio TZ-agnostico
// di `giornoFa` sopra): `new Date(iso).getHours()`, nel codice sotto test,
// torna esattamente `h`, qualunque sia il fuso di chi fa girare il test.
function oraIsoLocale(h, m) {
  var d = new Date();
  d.setHours(h, m || 0, 0, 0);
  return d.toISOString();
}

function puntoOra(h, valore) { return { ora: oraIsoLocale(h), valore: valore }; }

function bilancioFixture(extra) {
  return Object.assign({
    id: 1, genere: 'bilancio', protagonista: 'a1b2c3d4e5f6',
    inizio_ts: 1755990000, fine_ts: 1756076400,
    corpo: {
      totali: {
        produzione: { valore: 24.5, provenienza: null },
        autoconsumo: { valore: 14.2, provenienza: null },
        immissione: { valore: 10.3, provenienza: 'dichiarata' },
        prelievo: { valore: 3.1, provenienza: 'dedotta' },
      },
      forma: {
        produzione: [4, 5, 6, 7, 8, 9, 10, 11].map((h, i) =>
          puntoOra(h, [0, 0, 1.2, 2.3, 4.8, 3.1, 0.4, 0][i])),
        prelievo: [4, 5, 6, 7, 8, 9, 10, 11].map((h, i) =>
          puntoOra(h, [0.5, 0.4, 0.2, 0.1, 0, 0, 0.3, 0.6][i])),
      },
      momenti: {
        prima_ora_produzione: '2026-08-23T04:00:00+00:00',
        ultima_ora_produzione: '2026-08-23T18:00:00+00:00',
        picco_produzione: { valore: 4.8, ora: '2026-08-23T11:00:00+00:00' },
        quota_autoconsumo: 0.712,
      },
      dispositivo: 'Inverter con accumulo',
      entita: ['sensor.energia_prodotta_oggi', 'sensor.energia_immessa_oggi'],
    },
  }, extra || {});
}

test('seam _rendiOggetti: un bilancio mostra i totali in kWh, non «(nessun dettaglio)»', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /nessun dettaglio/);
  assert.match(corpo.textContent, /24,5\s*kWh/, 'il totale di produzione deve leggersi in kWh, virgola italiana');
  assert.match(corpo.textContent, /Inverter con accumulo/, 'il nome leggibile del dispositivo deve comparire');
  const badgeGenere = corpo.querySelector('.agent-badge');
  assert.equal(badgeGenere.textContent, 'Bilancio');
});

test('seam _rendiOggetti: un bilancio NON si legge come un episodio (niente "da X a Y", niente freccia di periodo)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /→/,
    'un bilancio è una quantità con una forma, non un "da → a": niente freccia di periodo()');
  assert.doesNotMatch(corpo.textContent, /\bda 24[,.]5\b/,
    'il totale non deve essere presentato come "da X a Y" (lo stampo dell\'episodio)');
});

test('seam _rendiOggetti: la provenienza di un totale riusa lo stesso badge dichiarata/dedotta degli episodi di energia', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.match(corpo.textContent, /[Dd]ichiarat/, 'la provenienza "dichiarata" (immissione) deve comparire');
  assert.match(corpo.textContent, /[Dd]edott/, 'la provenienza "dedotta" (prelievo) deve comparire');

  const badgeDichiarato = Array.from(corpo.querySelectorAll('.agent-badge'))
    .find((b) => /[Dd]ichiarat/.test(b.textContent));
  const badgeDedotto = Array.from(corpo.querySelectorAll('.agent-badge'))
    .find((b) => /[Dd]edott/.test(b.textContent));
  assert.ok(badgeDichiarato && badgeDedotto, 'entrambi i badge di provenienza devono esserci');
  assert.notEqual(badgeDichiarato.className, badgeDedotto.className,
    'le due provenienze devono distinguersi visibilmente, come per gli episodi di energia');
});

test('seam _rendiOggetti: un totale senza provenienza nota (produzione) non porta un badge di provenienza in più', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  // Un solo badge non porta ne' "dichiarat" ne' "dedott": e' il genere ("Bilancio").
  const badgeGenerici = Array.from(corpo.querySelectorAll('.agent-badge'))
    .filter((b) => !/[Dd]ichiarat|[Dd]edott/.test(b.textContent));
  assert.equal(badgeGenerici.length, 1, 'un solo badge senza provenienza: quello del genere');
});

test('seam _rendiOggetti: una dimensione assente (es. batteria) non compare come totale a zero', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /[Cc]arica della batteria/,
    'nessuna entità batteria in questa fixture: "carica" non deve comparire');
  assert.doesNotMatch(corpo.textContent, /[Ss]carica della batteria/);
  assert.doesNotMatch(corpo.textContent, /\b0\s*kWh\b/,
    'mai uno zero inventato per una dimensione senza dati (mandato, "cosa NON si salva")');
});

test('seam _rendiOggetti: la curva mostra produzione e prelievo sovrapposti, come barre SVG', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci un grafico SVG per la forma della giornata');
  const rects = svg.querySelectorAll('rect');
  assert.ok(rects.length > 0, 'il grafico deve avere almeno una barra');
  const riempimenti = new Set(Array.from(rects).map((r) => r.getAttribute('fill')));
  assert.ok(riempimenti.size >= 2, 'produzione e prelievo devono avere un colore diverso l\'una dall\'altra');
});

test('seam _rendiOggetti: senza `forma` non compare nessun grafico', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.forma;
  window.HirisWatcherRoute._rendiOggetti(corpo, [fx], null);

  assert.equal(corpo.querySelectorAll('svg').length, 0,
    'senza la forma della giornata non c\'è niente da disegnare');
});

// ---------------------------------------------------------------------------
// Punto 1 (ALTO) del brief-correzioni, riaperto e reso PIÙ severo dal punto 6:
// «la pagina non deve mai affermare un'ora falsa». Prima della correzione del
// 27/08 (mandato punto 6) la forma era un segnaposto posizionale ("punto N"),
// e il vecchio test si limitava a VIETARE qualunque HH:MM nell'SVG. Ora che
// il Python porta l'ora vera per ogni punto (`forma[dimensione] = [{"ora",
// "valore"}, ...]`), vietare non basta più: il test deve PRETENDERE l'ora
// giusta, e arrossire se la resa tornasse a leggere la POSIZIONE nell'array
// al posto della chiave `ora` (la mutazione che il mandato chiede di
// eseguire, non dedurre).
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: la curva del bilancio porta l\'ORA VERA di ogni barra, non la posizione nell\'array', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      // Le due ore sono deliberatamente NON in posizione 0/1 e distanti fra
      // loro: una resa che leggesse la posizione nell'array (0, 1, ...)
      // invece della chiave `ora` produrrebbe un'etichetta diversa dalla
      // vera per ENTRAMBI i punti, e questo test la coglierebbe.
      forma: { produzione: [puntoOra(7, 1.2), puntoOra(13, 4.8)] },
    }),
  })], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci il grafico');
  const titoliBarre = Array.from(svg.querySelectorAll('rect > title')).map((t) => t.textContent);

  assert.ok(titoliBarre.some((t) => /\b07:00\b/.test(t)),
    'la barra da 1,2 kWh deve portare la SUA ora vera (07:00): ' + titoliBarre.join(' | '));
  assert.ok(titoliBarre.some((t) => /\b13:00\b/.test(t)),
    'la barra da 4,8 kWh deve portare la SUA ora vera (13:00): ' + titoliBarre.join(' | '));
  assert.ok(!titoliBarre.some((t) => /\bpunto\s*\d/.test(t)),
    'nessun segnaposto posizionale ("punto N") deve restare nel testo delle barre: ' + titoliBarre.join(' | '));
});

test('seam _rendiOggetti: due punti lontani nel tempo restano distanti nel grafico -- i buchi si vedono', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [puntoOra(4, 1), puntoOra(5, 1), puntoOra(18, 1)] },
    }),
  })], null);

  const rects = Array.from(corpo.querySelectorAll('svg rect'));
  assert.equal(rects.length, 3);
  const xs = rects.map((r) => parseFloat(r.getAttribute('x'))).sort((a, b) => a - b);
  const scartoRavvicinato = xs[1] - xs[0]; // 4:00 -> 5:00, un'ora
  const scartoLontano = xs[2] - xs[1]; // 5:00 -> 18:00, tredici ore
  assert.ok(scartoLontano > scartoRavvicinato * 5,
    'un buco di 13 ore deve restare visibilmente più largo di uno di 1 ora: ' +
    scartoRavvicinato + ' vs ' + scartoLontano);
});

test('seam _rendiOggetti: l\'ora mostrata è quella LOCALE (convertita con Date), mai le cifre grezze della stringa ISO', () => {
  // `ora` arriva in UTC (`HAClient._instant_from_ha`): mostrare le prime
  // cifre della stringa ("13" da "...T13:00:00Z") sarebbe il difetto in
  // forma peggiore -- non più "non so l'ora", ma "affermo l'ora sbagliata"
  // (fino a due ore, con l'ora legale). Un fuso ESPLICITO e lontano da UTC
  // rende la prova indipendente dal fuso di chi fa girare il test: se la
  // resa leggesse le cifre grezze mostrerebbe "13:00" anche qui; la resa
  // corretta converte con `new Date(iso)`, come fa già `fmtIsoHour` per i
  // momenti -- la STESSA strada, non una nuova.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const isoConFusoEsplicito = '2026-08-23T13:00:00+05:00';
  const d = new Date(isoConFusoEsplicito);
  const pad2 = (n) => (n < 10 ? '0' + n : String(n));
  const oraLocaleAttesa = pad2(d.getHours()) + ':' + pad2(d.getMinutes());

  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [{ ora: isoConFusoEsplicito, valore: 2.5 }] },
    }),
  })], null);

  const titoloBarra = corpo.querySelector('svg rect > title').textContent;
  assert.ok(titoloBarra.indexOf(oraLocaleAttesa) !== -1,
    'la barra deve mostrare l\'ora LOCALE vera (' + oraLocaleAttesa + ', convertita con Date): ' + titoloBarra);
  if (oraLocaleAttesa !== '13:00') {
    assert.ok(titoloBarra.indexOf('13:00') === -1,
      'non deve mostrare la cifra GREZZA "13:00" letta dalla stringa ISO quando l\'ora locale vera è diversa: ' + titoloBarra);
  }
});

test('seam _rendiOggetti: un punto senza `ora` valida non si disegna (mai un\'ora inventata)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [{ ora: null, valore: 9.9 }] },
    }),
  })], null);

  const rects = corpo.querySelectorAll('svg rect');
  assert.equal(rects.length, 0, 'un punto senza ora non deve produrre una barra posizionata a caso');
});

// La dodicesima (brief-dodicesima.md, punto 1 -- MEDIO, "il cuore"): nessun
// test qui sopra lega la POSIZIONE della barra all'ora che dichiara. Un test
// guarda le distanze RELATIVE fra le barre ("i buchi si vedono", sopra), un
// altro guarda l'ETICHETTA (il titolo del `<title>`, sopra) -- nessuno lega
// le due cose. Mutazione ESEGUITA dal revisore per provarlo: spostare OGNI
// barra di un'ora nel solo piazzamento (x), lasciando l'etichetta corretta
// -> i 56 test allora esistenti restavano tutti verdi. Il riquadro al
// passaggio del mouse direbbe «le 13», e la barra starebbe alle 14 -- e la
// POSIZIONE e' cio' che si guarda per decidere, non l'etichetta.
// Serve un ancoraggio ASSOLUTO: la coordinata x attesa, calcolata dalla SUA
// ora con lo stesso contratto geometrico di `renderBalanceCurve`
// (watcher-route.js: viewBox 640x140, margine sinistro 4, 24 ore fisse
// -- `L`/`sinistra`/`ORE_DEL_GIORNO` nel sorgente, non ricopiati per caso:
// e' lo stesso disegno che la pagina dichiara nel suo `viewBox`, verificato
// sotto). Una sola serie (produzione) rende l'indice di serie ininfluente
// (`si * barWidth` = 0), cosi' la formula attesa non dipende da un
// dettaglio che non e' oggetto di questo test.
test('seam _rendiOggetti: la barra sta alla coordinata ASSOLUTA della sua ora, non solo in un ordine relativo alle altre (mutazione: un piazzamento spostato di un\'ora resta verde per tutti gli altri test)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [puntoOra(13, 4.8)] },
    }),
  })], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci il grafico');
  // Precondizione: il viewBox deve davvero essere 640x140 (altrimenti la
  // formula sotto misurerebbe il contratto sbagliato).
  assert.equal(svg.getAttribute('viewBox'), '0 0 640 140',
    'il viewBox del grafico non è più 640x140: aggiorna la costante di questo test insieme al sorgente');

  const rect = svg.querySelector('rect');
  assert.ok(rect, 'deve esserci la barra delle 13');

  const L = 640, sinistra = 4, ORE_DEL_GIORNO = 24;
  const passo = (L - sinistra * 2) / ORE_DEL_GIORNO;
  const xAttesa = sinistra + 13 * passo; // ora=13, una sola serie -> nessuno scarto di serie
  const xReale = parseFloat(rect.getAttribute('x'));
  assert.ok(Math.abs(xReale - xAttesa) < 0.15,
    'la barra delle 13 deve stare alla coordinata assoluta x=' + xAttesa.toFixed(1) +
    ' (sinistra + ora*passo), non a x=' + xReale +
    ' -- una traslazione uniforme del solo piazzamento (la mutazione del brief) sposta questo numero');
});

// ---------------------------------------------------------------------------
// Punto 3 (MEDIO): la descrizione dell'SVG non deve affermare «gli stessi
// numeri» -- falso nel caso generale (i momenti portano orari e percentuali,
// non gli stessi kWh della curva) -- e deve sparire quando i momenti mancano.
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: la descrizione dell\'SVG non dichiara "gli stessi numeri" dei momenti', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const desc = corpo.querySelector('svg desc').textContent;
  assert.doesNotMatch(desc, /stessi numeri/i,
    'i momenti non ripetono "gli stessi numeri" della curva (percentuali, orari): falso nel caso generale');
});

test('seam _rendiOggetti: senza `momenti`, la descrizione dell\'SVG non rimanda a una sezione che non c\'è', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.momenti;
  window.HirisWatcherRoute._rendiOggetti(corpo, [fx], null);

  const desc = corpo.querySelector('svg desc').textContent;
  assert.doesNotMatch(desc, /momenti/, 'orfana se i momenti mancano: la frase non deve più nominarli');
});

test('seam _rendiOggetti: i momenti si leggono come dati secchi (orario HH:MM, percentuale con la virgola)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  // Sul NODO giusto (rilievo 2 del brief «css-morto»: un assert sul testo di
  // TUTTA la pagina/riga può essere soddisfatto da un'altra sezione).
  // `<dt>`/`<dd>` non hanno separatore visivo nel textContent concatenato,
  // quindi si legge la coppia esatta, non l'intera riga.
  const momenti = corpo.querySelector('.bil-moments');
  assert.ok(momenti, 'deve esserci la sezione dei momenti derivati');
  const etichette = Array.from(momenti.querySelectorAll('dt')).map((n) => n.textContent);
  const valori = Array.from(momenti.querySelectorAll('dd')).map((n) => n.textContent);
  assert.ok(etichette.includes('Prima ora di produzione'));

  const primaOra = valori[etichette.indexOf('Prima ora di produzione')];
  assert.match(primaOra, /^\d{2}:\d{2}$/, 'l\'orario si legge HH:MM, non un timestamp ISO grezzo: ' + primaOra);
  assert.doesNotMatch(corpo.textContent, /2026-08-23T/, 'nessun ISO grezzo in pagina');

  const quota = valori[etichette.indexOf('Quota di autoconsumo')];
  assert.match(quota, /^71,2\s*%$/, 'la quota di autoconsumo è una percentuale con la virgola italiana: ' + quota);

  const picco = valori[etichette.indexOf('Picco di produzione')];
  assert.match(picco, /4,8\s*kWh/, 'il picco di produzione porta il suo valore in kWh: ' + picco);
  assert.match(picco, /\d{2}:\d{2}/, 'il picco di produzione porta anche l\'ora: ' + picco);
});

test('seam _rendiOggetti: senza `momenti` non compare la sezione dei momenti derivati', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.momenti;
  window.HirisWatcherRoute._rendiOggetti(corpo, [fx], null);

  assert.doesNotMatch(corpo.textContent, /Prima ora di produzione/);
  assert.doesNotMatch(corpo.textContent, /Quota di autoconsumo/);
});

// ---------------------------------------------------------------------------
// Punto 2 (MEDIO): a 1200px `.bil-moments` (auto-fit) può calcolare un numero
// DISPARI di colonne -- dt e dd, celle indipendenti della griglia, si
// spezzano a fine riga (misurato dal revisore: «Picco di produzione» chiude
// una riga, il suo valore ne apre un'altra accanto a un'altra etichetta).
// jsdom non fa layout, quindi non può riprodurre lo sfondamento a 1200px --
// ma può verificare la precondizione strutturale della correzione: ogni
// dt/dd deve condividere un contenitore proprio (`.bil-moment`), MAI essere
// figlio diretto di `.bil-moments`, perché solo così un motore vero non può
// più spezzare la coppia a nessuna larghezza (verificato dal vivo, vedi il
// rapporto).
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: ogni momento (dt+dd) è una coppia atomica, mai due celle indipendenti della griglia', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const momenti = corpo.querySelector('.bil-moments');
  const dts = Array.from(momenti.querySelectorAll('dt'));
  assert.ok(dts.length > 1, 'servono almeno due momenti per verificare che non si spezzino (fixture insufficiente?)');
  dts.forEach((dt) => {
    assert.notEqual(dt.parentElement, momenti,
      'dt non deve essere figlio diretto di `.bil-moments`: a certe larghezze un motore vero lo separa dal suo dd (rilievo 2)');
    const dd = dt.nextElementSibling;
    assert.ok(dd && dd.tagName === 'DD', 'ogni dt deve avere il suo dd come fratello immediato: ' + dt.textContent);
    assert.equal(dt.parentElement, dd.parentElement,
      'dt e dd devono condividere lo stesso contenitore (coppia atomica)');
  });
});

// ---------------------------------------------------------------------------
// Il consumo, settima direzione del bilancio (LETTA, non dedotta -- vedi il
// commento sopra DIREZIONI_BILANCIO in mind/facts.py, mandato «il
// bilancio dell'energia», punto 1, 27/08/2026): la pagina deve poterlo
// mostrare come le altre sei, con la stessa etichetta già usata dagli
// episodi di energia.
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: il totale "consumo" (settima direzione) si mostra come le altre sei', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  fx.corpo.totali.consumo = { valore: 17.3, provenienza: null };
  window.HirisWatcherRoute._rendiOggetti(corpo, [fx], null);

  assert.match(corpo.textContent, /Consumo della casa/);
  assert.match(corpo.textContent, /17,3\s*kWh/);
});

test('seam _rendiOggetti: le entità del bilancio stanno dietro un rivelatore sincrono, chiuso di default', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  document.body.appendChild(corpo);
  window.HirisWatcherRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const btn = Array.from(corpo.querySelectorAll('button')).find((b) => /sensori/.test(b.textContent));
  assert.ok(btn, 'deve esserci un rivelatore per le entità del bilancio');
  const pannello = btn.nextElementSibling;
  // Chiuso via `hidden` (attributo DOM, non solo un display CSS), come il
  // rivelatore di comprimari/misure sopra: `textContent` include SEMPRE il
  // testo dei nodi `hidden` (in jsdom come in un motore vero), quindi non è
  // il segnale giusto per "non ancora visibile" -- lo è l'attributo.
  assert.equal(pannello.hidden, true, 'il pannello nasce chiuso');

  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(pannello.hidden, false, 'il click deve aprire il pannello');
  assert.match(pannello.textContent, /sensor\.energia_prodotta_oggi/);
  assert.match(pannello.textContent, /sensor\.energia_immessa_oggi/);
});

test('seam _rendiOggetti: un bilancio senza entità non mostra nessun rivelatore di entità', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture({ corpo: Object.assign({}, bilancioFixture().corpo, { entita: [] }) });
  window.HirisWatcherRoute._rendiOggetti(corpo, [fx], null);

  const btn = Array.from(corpo.querySelectorAll('button')).find((b) => /sensori/.test(b.textContent));
  assert.equal(btn, undefined);
});

test('mount: un bilancio nella lista di "cosa è successo" si legge, non resta "(nessun dettaglio)"', async () => {
  const { window, document } = montaConServer({ facts: { facts: [bilancioFixture()] } });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.doesNotMatch(testo, /nessun dettaglio/);
  assert.match(testo, /kWh/);
  assert.match(testo, /Inverter con accumulo/);
});

// ---------------------------------------------------------------------------
// Corsa sul cambio giorno (rilievo 8b): un contatore di generazione
// ---------------------------------------------------------------------------

test('due cambi rapidi di giorno: la risposta più lenta e superata non deve vincere su quella giusta', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const risposte = {};
  risposte[IERI] = { facts: [{ id: 1, genere: 'funzionamento', protagonista: 'light.vecchio_giorno', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };
  risposte[OGGI] = { facts: [{ id: 2, genere: 'funzionamento', protagonista: 'light.giorno_giusto', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };

  window.fetch = (url) => {
    const u = String(url);
    if (u.indexOf('api/mind/watching') === 0) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ watching: [] }) });
    }
    const m = u.match(/day=([\d-]+)/);
    const giorno = m ? decodeURIComponent(m[1]) : null;
    // La prima richiesta lanciata (IERI, poi superata da OGGI) è anche la
    // più lenta: senza guardia arriverebbe per ultima e vincerebbe.
    const ritardo = giorno === IERI ? 40 : 5;
    return new Promise((resolve) => setTimeout(() => resolve(
      { ok: true, status: 200, json: async () => risposte[giorno] }), ritardo));
  };

  const input = document.querySelector('input[type=date]');
  input.value = IERI;
  input.dispatchEvent(new window.Event('change'));
  await tick(1); // lascia partire la prima richiesta prima di cambiare di nuovo
  input.value = OGGI;
  input.dispatchEvent(new window.Event('change'));

  await tick(80); // entrambe le risposte sono arrivate ormai

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /light\.giorno_giusto/, 'deve mostrare il giorno richiesto per ultimo');
  assert.doesNotMatch(testo, /light\.vecchio_giorno/,
    'la risposta più lenta e superata non deve sovrascrivere quella giusta arrivata dopo, ma per prima');
});

// ---------------------------------------------------------------------------
// Pulizia: nessun `TONE_UNKNOWN` morto, nessun innerHTML (rilievo 8d + disciplina generale)
// ---------------------------------------------------------------------------

test('il sorgente non definisce TONO_IGNOTO se non lo usa (o si usa, o si toglie)', () => {
  const usiTonoIgnoto = (SORGENTE.match(/TONO_IGNOTO/g) || []).length;
  assert.ok(usiTonoIgnoto === 0 || usiTonoIgnoto >= 2,
    'TONO_IGNOTO non può essere definito e mai usato: o compare almeno una volta oltre alla definizione, o non c\'è più');
});

test('il sorgente non scrive mai innerHTML su dati del server', () => {
  // Cerca l'USO (`qualcosa.innerHTML =`), non la parola nel commento di
  // sicurezza in cima al file, che la nomina apposta per vietarla.
  assert.ok(!/\.innerHTML/.test(SORGENTE), 'trovato un uso di .innerHTML nel sorgente');
});

// ---------------------------------------------------------------------------
// README: il numero di rotte dichiarato combacia con quelle registrate in
// main.js (rilievo 10) — misurato, non ricopiato
// ---------------------------------------------------------------------------

test('README: il numero di rotte "live" dichiarato è quello davvero registrato in main.js', () => {
  const README = readFileSync(join(CONFIG_DIR, '..', '..', '..', '..', 'README.md'), 'utf8');
  const MAIN_JS = readFileSync(join(CONFIG_DIR, 'main.js'), 'utf8');
  const registrate = (MAIN_JS.match(/HirisRouter\.register\(/g) || []).length;
  assert.ok(registrate > 0, 'nessuna rotta trovata in main.js: il percorso è cambiato?');

  const NUMERI = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 };
  const m = README.match(/with (\w+) live routes/);
  assert.ok(m, 'la frase "with N live routes" non è più nel README: aggiorna questo test insieme al testo');
  const dichiarate = NUMERI[m[1].toLowerCase()];
  assert.ok(dichiarate, 'numero non riconosciuto nel README: ' + m[1]);
  assert.equal(dichiarate, registrate,
    'il README dichiara ' + m[1] + ' rotte live, ma main.js ne registra ' + registrate + ' (contate, non copiate)');
});

// ---------------------------------------------------------------------------
// Cancello del collaudo A3 (07/09/2026, BACKLOG.md «Il README documenta sei
// rotte che non esistono»): il numero di rotte combaciava anche col difetto
// -- sei erano il NOME sbagliato (`#/albero` invece di `#/tree`, e simili),
// e il test sopra (che conta soltanto) non poteva vederlo. Questo confronta
// l'IDENTITA' di ogni rotta, non solo la conta.
// ---------------------------------------------------------------------------

test('README: ogni rotta della tabella "Interface" è una di quelle davvero registrate in main.js, e viceversa', () => {
  const README = readFileSync(join(CONFIG_DIR, '..', '..', '..', '..', 'README.md'), 'utf8');
  const MAIN_JS = readFileSync(join(CONFIG_DIR, 'main.js'), 'utf8');

  // Ogni riga della tabella comincia con `| \`#/xxx\` |` -- l'ancora `^` in
  // modalità multilinea la distingue da una MENZIONE di un'altra rotta
  // dentro la colonna descrizione (es. "chosen per provider in `#/models`",
  // dentro la riga di `#/settings`), che non comincia mai la riga.
  const dalReadme = new Set();
  const reReadme = /^\| `#\/(\w*)` \|/gm;
  let m;
  while ((m = reReadme.exec(README))) dalReadme.add(m[1]);
  assert.ok(dalReadme.size > 0, 'nessuna riga di rotta trovata nella tabella "Interface" del README: il formato è cambiato?');

  // Stessa forma letterale del test sopra: `HirisRouter.register(/^#\/xxx\/?$/`
  // per una rotta con nome, `HirisRouter.register(/^#\/?$/` per la radice
  // (senza segmento -- gruppo di cattura opzionale).
  const daMainJs = new Set();
  const reMainJs = /HirisRouter\.register\(\/\^#(?:\\\/(\w+))?\\\/\?\$\//g;
  while ((m = reMainJs.exec(MAIN_JS))) daMainJs.add(m[1] || '');
  assert.ok(daMainJs.size > 0, 'nessuna rotta riconosciuta in main.js: la forma della regex è cambiata?');

  const soloNelReadme = [...dalReadme].filter((r) => !daMainJs.has(r));
  const soloInMainJs = [...daMainJs].filter((r) => !dalReadme.has(r));
  assert.deepEqual(soloNelReadme, [],
    'il README documenta ' + JSON.stringify(soloNelReadme) + ', rotte che main.js non registra');
  assert.deepEqual(soloInMainJs, [],
    'main.js registra ' + JSON.stringify(soloInMainJs) + ', rotte che il README non documenta');
});

// ---------------------------------------------------------------------------
// Fetta «il nome» (07/09/2026): il nome amichevole SALVATO al momento del
// cambio (`corpo.nome`, colonna `friendly_name`) arriva alla riga; e quando
// non c'è, la riga mostra l'identificatore DICENDO che è un identificatore —
// mai un nome dedotto dall'`entity_id`, mai una riga muta.
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: il nome amichevole è il contenuto, l\'identificatore resta il riferimento', () => {
  // Mutazione dichiarata, ESEGUITA (transcript nel rapporto): togliere il
  // blocco `if (c.nome && !c.titolo) { ... }` da `factLine`
  // (config/watcher-route.js) fa arrossire `assert.ok(rigaNome)` qui sotto —
  // il nome non compare da nessuna parte e la pagina torna a mostrare solo
  // l'entity_id.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'climate.bagno_1p_t_bagno_1p_t',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { stato: 'heat', nome: 'Termostato Bagno' },
  }], null);

  const paragrafi = Array.from(corpo.querySelectorAll('p'));
  const rigaNome = paragrafi.find((p) => p.textContent === 'Termostato Bagno');
  assert.ok(rigaNome, 'il nome amichevole deve leggersi come contenuto, non restare nel payload');
  assert.doesNotMatch(rigaNome.className || '', /\bfield-hint\b/,
    'il nome è il contenuto: non va nella classe attenuata riservata ai riferimenti');

  // L'identificatore NON si butta: distingue due entità che si chiamano
  // uguale, e resta nel monospazio attenuato.
  const identificatore = corpo.querySelector('.text-mono');
  assert.equal(identificatore.textContent, 'climate.bagno_1p_t_bagno_1p_t');

  // Con un nome vero non si dichiara niente: la parola «identificatore»
  // esiste per quando il nome MANCA, non come decorazione fissa.
  assert.doesNotMatch(corpo.textContent, /identificatore/i);
});

test('seam _rendiOggetti: senza nome la riga mostra l\'id DICENDO che è un id, e non lo inventa', () => {
  // Mutazione dichiarata, ESEGUITA (transcript nel rapporto): togliere la
  // riga `if (d.technical) head.appendChild(el('span', 'field-hint',
  // SUBJECT_IS_ID));` da `factLine` fa arrossire `assert.match(testa, ...)`
  // qui sotto — l'entity_id torna a passare per un nome.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'climate.bagno_1p_t_bagno_1p_t',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { stato: 'heat' },
  }], null);

  const testa = corpo.textContent;
  assert.match(testa, /identificatore/i,
    'quando il nome manca, la riga deve DIRE che quello che mostra è un identificatore');
  assert.match(testa, /climate\.bagno_1p_t_bagno_1p_t/,
    'l\'identificatore si mostra: non si tace la riga');

  // Non si inventa un nome dall'id: nessuna capitalizzazione, nessuna
  // sostituzione degli underscore.
  assert.doesNotMatch(testa, /Bagno 1p/,
    'un nome dedotto dall\'entity_id sarebbe un\'invenzione, non un nome');

  // E la riga resta una riga: il fatto (periodo + stato) c'è comunque.
  const paragrafi = Array.from(corpo.querySelectorAll('p'));
  assert.ok(paragrafi.some((p) => /→/.test(p.textContent) && /heat/.test(p.textContent)),
    'senza nome il fatto si legge lo stesso: la riga non diventa muta');
});

test('seam _rendiOggetti: un guasto col suo titolo non viene dichiarato identificatore (ne ha già uno leggibile)', () => {
  // Mutazione dichiarata, ESEGUITA: far tornare `technical: true` anche per il
  // ramo `integrazione` di `describeWatchedSubject` fa arrossire
  // `assert.doesNotMatch` qui sotto — la parola comparirebbe accanto a un
  // nome che c'è già.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'integrazione:01K2CK4GG287VKK18M5J788MRQ',
    inizio_ts: 1755270600, fine_ts: null,
    corpo: { stato: 'setup_retry', dominio: 'lifx', titolo: 'Abat-jour' },
  }], null);
  assert.match(corpo.textContent, /Abat-jour/);
  assert.doesNotMatch(corpo.textContent, /identificatore/i);
});

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

// ---------------------------------------------------------------------------
// Fetta «lo stato» (07/09/2026): la resa arriva ACCANTO al grezzo, e i due
// silenzi (traduzioni non lette / stato senza traduzione) non si leggono
// uguali.
// ---------------------------------------------------------------------------

const TRADOTTE = { lette: true, lingua: 'it' };

function oggettoFunzionamento(corpo) {
  return {
    id: 1, genere: 'funzionamento', protagonista: 'climate.bagno_1p_t',
    inizio_ts: 1755270600, fine_ts: 1755277500, corpo,
  };
}

test('seam _rendiOggetti: lo stato reso è quello che si legge, non il grezzo inglese', () => {
  // Mutazione dichiarata, ESEGUITA: togliere la riga
  // `var shown = c.stato_reso != null ? c.stato_reso : c.stato;` da
  // `mainPhrase` (tornando a `c.stato`) fa arrossire l'`assert.match` su
  // /Riscaldamento/.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'heat', stato_reso: 'Riscaldamento', nome: 'Termostato Bagno' }),
  ], null, TRADOTTE);
  assert.match(corpo.textContent, /stato: Riscaldamento/,
    'la resa esiste: è quella che il proprietario deve leggere');
  assert.doesNotMatch(corpo.textContent, /stato: heat/,
    'il grezzo inglese non si mostra quando una resa c\'è: era il rilievo');
});

test('seam _rendiOggetti: senza resa la riga mostra il grezzo, e non lo tace né lo inventa', () => {
  // Mutazione dichiarata, ESEGUITA: scrivere `var shown = c.stato_reso;` in
  // `mainPhrase` fa arrossire l'`assert.match` su /digitalfirst/ — la riga
  // perderebbe lo stato invece di mostrarlo grezzo.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'digitalfirst', nome: 'Telecamera Ingresso' }),
  ], null, TRADOTTE);
  assert.match(corpo.textContent, /stato: digitalfirst/,
    'Home Assistant stesso mostra il grezzo quando non ha traduzione: la riga non mente');
  assert.doesNotMatch(corpo.textContent, /nessun dettaglio/);
});

test('seam _rendiOggetti: traduzioni NON LETTE lo dicono, col motivo', () => {
  // Mutazione dichiarata, ESEGUITA: togliere la chiamata
  // `translationsNote(body, translations);` da `renderFacts` fa arrossire
  // entrambi gli `assert.match` qui sotto.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'heat' }),
  ], null, { lette: false, motivo: 'Home Assistant non ha risposto' });
  assert.match(corpo.textContent, /non si sono potute leggere/,
    'gli stati restano in inglese per un GUASTO: va detto, non nascosto');
  assert.match(corpo.textContent, /Home Assistant non ha risposto/,
    'il motivo lo produce chi lo conosce e arriva fin qui');
});

test('seam _rendiOggetti: uno stato senza traduzione NON si annuncia come un guasto di lettura', () => {
  // I due silenzi non si leggono uguali: è l'invariante di questa fetta.
  // Mutazione dichiarata, ESEGUITA: far scrivere a `translationsNote` la
  // stessa frase anche per `lette: true` fa arrossire il `doesNotMatch`.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'digitalfirst' }),
  ], null, TRADOTTE);
  assert.match(corpo.textContent, /stato: digitalfirst/);
  assert.doesNotMatch(corpo.textContent, /non si sono potute leggere/,
    'le traduzioni SONO state lette: questo stato semplicemente non ne ha una');
});

test('seam _rendiOggetti: una casa in un\'altra lingua lo dichiara, invece di far sembrare la resa sbagliata', () => {
  // Mutazione dichiarata, ESEGUITA: togliere il ramo
  // `if (t.lette === true && t.lingua && t.lingua !== 'it')` da
  // `translationsNote` fa arrossire l'`assert.match` su /lingua della casa/.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'heat', stato_reso: 'Heating' }),
  ], null, { lette: true, lingua: 'en' });
  assert.match(corpo.textContent, /lingua della casa/,
    'la lingua è quella che il proprietario ha scelto in HA, non l\'italiano per definizione');
  assert.match(corpo.textContent, /stato: Heating/);
});

test('seam _rendiOggetti: una casa in italiano non si sente dire in che lingua legge', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [
    oggettoFunzionamento({ stato: 'heat', stato_reso: 'Riscaldamento' }),
  ], null, TRADOTTE);
  assert.doesNotMatch(corpo.textContent, /lingua della casa/,
    'l\'italiano è già la lingua della pagina: dirlo sarebbe rumore');
});

test('seam _rendiOggetti: un guasto continua a mostrare la sua condizione vera, senza resa', () => {
  // Un `integrazione:` non passa dal vocabolario degli stati (il confine sta
  // in `api/handlers_mind.py`): la riga non deve cambiare per questa fetta.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'integrazione:01K2CK4GG287VKK18M5J788MRQ',
    inizio_ts: 1755270600, fine_ts: null,
    corpo: { stato: 'setup_retry', dominio: 'lifx', titolo: 'Abat-jour' },
  }], null, TRADOTTE);
  assert.match(corpo.textContent, /stato: setup_retry/);
});
