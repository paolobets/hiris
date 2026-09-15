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
    if (u.indexOf('api/mind/facts') === 0) {
      if (opts.oggettiRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.facts !== undefined ? opts.facts : { facts: [] },
        opts.oggettiStatus);
    }
    /* La terza rotta, dal 14/09/2026 (sezione 03). Prima di questa correzione
       `montaConServer` SOLLEVAVA su `api/mind/report` -- e la pagina lo
       inghiottiva nel ramo d'errore di `loadReport`, quindi tutte le prove di
       mount restavano verdi con la sezione 03 muta. La chiave `resoconto` è
       quella vera di `handlers_mind.handle_report`, ed è PINNATA qui: se una
       delle due parti la rinomina, questa prova cade. */
    if (u.indexOf('api/mind/knowledge') === 0) {
      if (opts.sapereRotto) throw new Error('rete interrotta');
      return jsonResponse(
        opts.sapere !== undefined ? opts.sapere
          : { conteggi: { totale: 0, righe: [] }, non_capito: [] },
        opts.sapereStatus);
    }
    if (u.indexOf('api/mind/analysis') === 0) {
      if (opts.analisiRotta) throw new Error('rete interrotta');
      return jsonResponse(
        opts.analisi !== undefined ? opts.analisi : { analisi: { osservazioni: [] } },
        opts.analisiStatus);
    }
    if (u.indexOf('api/mind/report') === 0) {
      if (opts.resocontoRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.resoconto !== undefined ? opts.resoconto : { resoconto: resoconto() },
        opts.resocontoStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate, corpiInviati });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
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

const OGGI = giornoFa(0);
const IERI = giornoFa(1);
const TRONCAMENTI_LEGITTIMI = new Set(['po', 'mo', 'be', 'da', 'di', 'fa', 'sta', 'va']);
const REFUSO_ACCENTO = /([A-Za-zÀ-ÿ]*[aeiouAEIOU])’(?=[\s.,;:)\]!?»"]|$)/g;

function trovaRefusiApostrofo(testo) {
  const trovati = [];
  for (const m of testo.matchAll(REFUSO_ACCENTO)) {
    if (TRONCAMENTI_LEGITTIMI.has(m[1].toLowerCase())) continue;
    trovati.push(m.index);
  }
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

test('la guardia cattura la CLASSE del refuso, non solo "e’": «sara’», «perche’», «piu’»', () => {
  // Il caso vero, pagato il 14/09/2026: «il grezzo di quel giorno sara’
  // scaduto» nel cappello della sezione 03. La vecchia guardia cercava
  // `[eE]’ ` e non poteva vederlo.
  // Mutazione che la uccide: rimettere la vecchia espressione.
  assert.equal(trovaRefusiApostrofo('il grezzo sara’ scaduto').length, 1, '«sara’»');
  assert.equal(trovaRefusiApostrofo('piu’ tardi').length, 1, '«piu’»');
  assert.equal(trovaRefusiApostrofo('a fine riga: cosi’').length, 1, 'anche a fine stringa');
  assert.equal(trovaRefusiApostrofo('la citta’, e poi').length, 1, 'anche prima di una virgola');
});

test("la guardia NON grida sull’elisione vera né sui troncamenti dell’italiano", () => {
  // Se gridasse su `l’indice` il cancello diventerebbe rumore, e un cancello
  // che grida sempre si spegne. Mutazione che la uccide: togliere il
  // lookahead, o svuotare TRONCAMENTI_LEGITTIMI.
  assert.deepEqual(trovaRefusiApostrofo('l’indice di un’integrazione'), []);
  assert.deepEqual(trovaRefusiApostrofo('ci vuole un po’ di tempo'), []);
  assert.deepEqual(trovaRefusiApostrofo('a mo’ di esempio, va’ avanti'), []);
});

test('mount: "Non sto guardando ancora niente" usa è, non e’', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /HIRIS è appena partito/);
  assert.match(testo, /è normale/);
});

test('mount: il sottotitolo dice i TRE attori, e non rimanda l’analista a domani', async () => {
  const { window, document } = montaConServer();
  window.HirisWatcherRoute.mount();
  await tick(20);

  const sottotitolo = document.querySelector('.page-subtitle').textContent;
  assert.equal(trovaRefusiApostrofo(sottotitolo).length, 0,
    'nessun accento scritto con l’apostrofo');
  assert.match(sottotitolo, /cosa si potrebbe fare/,
    'il terzo attore c’è: la pagina non lo rimanda più a domani');
  assert.doesNotMatch(sottotitolo, /domani/,
    'l’analista ha gia’ parlato: prometterlo per domani sarebbe falso');
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

// ---------------------------------------------------------------------------
// Punto 3 (MEDIO): la descrizione dell'SVG non deve affermare «gli stessi
// numeri» -- falso nel caso generale (i momenti portano orari e percentuali,
// non gli stessi kWh della curva) -- e deve sparire quando i momenti mancano.
// ---------------------------------------------------------------------------





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


// ---------------------------------------------------------------------------
// Il consumo, settima direzione del bilancio (LETTA, non dedotta -- vedi il
// commento sopra DIREZIONI_BILANCIO in mind/facts.py, mandato «il
// bilancio dell'energia», punto 1, 27/08/2026): la pagina deve poterlo
// mostrare come le altre sei, con la stessa etichetta già usata dagli
// episodi di energia.
// ---------------------------------------------------------------------------





// ---------------------------------------------------------------------------
// Corsa sul cambio giorno (rilievo 8b): un contatore di generazione
// ---------------------------------------------------------------------------


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

/* ---------------------------------------------------------- il resoconto (§9)

   La sezione 03 rende il resoconto del giorno PER UN UMANO. Il resoconto non è
   fatto per un umano — serve all'analista, e il suo documento markdown è
   pensato per stare in un prompt — ma la pagina rende lo STESSO dato con
   l'idioma suo: stesso archivio, due rese. È la ragione per cui il documento
   si deriva invece di essere archiviato. */

function resoconto(extra) {
  return Object.assign({ giorno: '2026-09-13', misure: [], forme: [], cronaca: [] }, extra || {});
}

function misura(extra) {
  return Object.assign({
    soggetto: 'dev1', nome: 'Inverter', misura: 'prodotta',
    operazione: 'somma_periodo', valore: 23.71, unita: 'kWh', copertura: 1,
  }, extra || {});
}

/* Una misura che NON si e' potuta fare: `valore` va **tolta**, non messa a
   `undefined` -- la pagina (come `as_document`) separa le due liste con
   `'valore' in m`, e una chiave presente a `undefined` sarebbe «calcolata». */
function nonCalcolabile(nome, perche) {
  const m = misura({ misura: nome, non_calcolabile: perche });
  delete m.valore;
  delete m.unita;
  delete m.copertura;
  return m;
}

function rendiAnalisi(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiAnalisi(corpo, payload.analisi);
  return { window, document, corpo };
}

function rendiResoconto(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiResoconto(corpo, payload);
  return { window, document, corpo };
}

test('seam _rendiResoconto: «cosa non si sa» viene PRIMA delle misure', () => {
  // Mutazione che la uccide: spostare il blocco `ignote` dopo la griglia.
  const { corpo } = rendiResoconto(resoconto({
    misure: [misura(), nonCalcolabile('autosufficienza',
      'copertura 8%, sotto il minimo del 75%')],
  }));

  const testo = corpo.textContent;
  assert.ok(testo.indexOf('Cosa non si sa') >= 0, 'la sezione c\'e\'');
  assert.ok(testo.indexOf('Cosa non si sa') < testo.indexOf('Le misure'),
    'in fondo a una tabella di numeri buoni non salterebbe all\'occhio, ed e\' la ' +
    'parte su cui il proprietario puo\' fare qualcosa');
  assert.match(testo, /copertura 8%/);
});

test('seam _rendiResoconto: la copertura si dice solo quando NON e\' piena', () => {
  // Mutazione che la uccide: togliere `&& m.copertura < 1` dalla guardia.
  const piena = rendiResoconto(resoconto({ misure: [misura()] }));
  assert.doesNotMatch(piena.corpo.textContent, /del giorno/,
    '«su 100% del giorno» accanto a ogni numero e\' rumore su cui l\'occhio smette ' +
    'di fermarsi, ed e\' proprio quando non e\' piena che deve fermarsi');

  const parziale = rendiResoconto(resoconto({ misure: [misura({ copertura: 0.83 })] }));
  assert.match(parziale.corpo.textContent, /83% del giorno/);
});

test('seam _rendiResoconto: la cronaca dice quando, chi, cosa — e i cambi di attributo', () => {
  // Mutazione che la uccide: non appendere la coda dei cambi di attributo.
  const { corpo } = rendiResoconto(resoconto({
    cronaca: [{
      quando_ts: 1789219800, fine_ts: null, chi: 'climate.soggiorno',
      nome: 'Termostato Soggiorno', cosa: 'heat',
      attributi: [{ quando_ts: 1789223400, valori: { hvac_action: 'idle' } }],
    }],
  }));

  const testo = corpo.textContent;
  assert.match(testo, /Termostato Soggiorno/);
  assert.match(testo, /in corso/, '«ancora in corso» e\' un fatto, non un buco');
  assert.match(testo, /1 cambio di attributo/);
});

test('seam _rendiResoconto: un giorno senza niente lo DICE, e non tace', () => {
  // «quel giorno non e' successo niente» e «quel giorno non l'abbiamo
  // guardato» sono due cose diverse: la pagina deve dire la prima.
  // Mutazione che la uccide: tornare presto quando misure e cronaca sono vuote.
  const { corpo } = rendiResoconto(resoconto());

  assert.match(corpo.textContent, /Nessuna misura per questo giorno/);
  assert.match(corpo.textContent, /Nessun fatto/);
});

/* --------------------------------------- il resoconto, montato sulla pagina

   Le prove qui sopra pinnano la RESA. Queste pinnano il FILO: la chiave che
   la rotta usa, e il fatto che il giorno sia uno solo per le due sezioni. È
   la classe di difetto che nessuna prova di resa può vedere -- `corpo.fatti`
   al posto di `corpo.resoconto` renderebbe una sezione vuota, in silenzio,
   con la suite tutta verde. */

test('mount: la sezione 02 legge la chiave «resoconto» della rotta, e rende la misura', async () => {
  // Mutazione che la uccide: in `loadReport`, `occurrence.corpo.risultato`
  // (o qualunque altro nome) al posto di `occurrence.corpo.resoconto`.
  const { window, document } = montaConServer({
    resoconto: { resoconto: resoconto({ misure: [misura()] }) },
  });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const card3 = document.querySelectorAll('.section-card')[1];
  assert.ok(card3, 'la sezione 03 deve esistere sulla pagina');
  assert.match(card3.textContent, /Inverter/);
  assert.match(card3.textContent, /23\.71 kWh/);
});


test('mount: la pagina apre su IERI — OGGI non ha ancora un resoconto (si scrive alle 00:20)', async () => {
  // Il selettore nasce su ieri, e sono LE DUE sezioni a seguirlo. Chiedere
  // OGGI darebbe un 404 a ogni apertura della pagina, su tutt'e due.
  // Mutazione che la uccide: `dayInput.value = localToday()`.
  const ctx = montaConServer();
  ctx.window.HirisWatcherRoute.mount();
  await tick(20);

  const report = ctx.chiamate.filter((u) => u.indexOf('api/mind/report') === 0);
  assert.equal(report.length, 1, 'una sola richiesta all\u2019apertura');
  assert.ok(report[0].indexOf(IERI) !== -1,
    'deve chiedere ieri (' + IERI + '), ha chiesto: ' + report[0]);
  assert.ok(report[0].indexOf(OGGI) === -1, 'e non oggi');
});


test('mount: un giorno senza resoconto (404) lo SPIEGA, e non dice che non è successo niente', async () => {
  // «non c'è ancora» e «non è successo niente» sono due cose diverse, e la
  // seconda al posto della prima sarebbe una bugia tranquillizzante.
  // Mutazione che la uccide: togliere il ramo `status === 404`.
  const { window, document } = montaConServer({ resocontoStatus: 404 });
  window.HirisWatcherRoute.mount();
  await tick(20);

  const card3 = document.querySelectorAll('.section-card')[1];
  assert.match(card3.textContent, /non c’è ancora un resoconto/);
  assert.match(card3.textContent, /00:20/);
});

test('seam _rendiResoconto: le forme orarie si DICONO, non si stampano', () => {
  // Misurato sulla casa vera il 14/09/2026: otto serie orarie pesavano il 75%
  // delle misure del giorno. Stampate in una griglia diventavano una riga di
  // «[object Object],[object Object],…» -- il contrario di leggibile. Si dice
  // che ci sono, con quanti punti, e il dato resta nell'archivio.
  // Mutazione che la uccide: non rendere affatto `forme`.
  const { corpo } = rendiResoconto(resoconto({
    misure: [misura()],
    forme: [{ soggetto: 'dev1', nome: 'Inverter', misura: 'forma_produzione',
              operazione: 'per_ora', unita: 'kWh', copertura: 1,
              valore: [{ ora: 'x', valore: 1 }, { ora: 'y', valore: 2 }] }],
  }));

  const testo = corpo.textContent;
  assert.match(testo, /forma_produzione/);
  assert.match(testo, /2 punti orari/);
  assert.doesNotMatch(testo, /\[object Object\]/,
    'una serie non si stampa: si dice');
});

test('seam _rendiResoconto: un giorno senza forme non apre la sezione', () => {
  // Un titolo sopra il vuoto e' rumore: la sezione compare solo se c'e'.
  // Mutazione che la uccide: rendere il titolo sempre.
  const { corpo } = rendiResoconto(resoconto({ misure: [misura()] }));
  assert.doesNotMatch(corpo.textContent, /Le forme del giorno/);
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
  ctx.window.HirisWatcherRoute.mount();
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
  ctx.window.HirisWatcherRoute.mount();
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
  ctx.window.HirisWatcherRoute.mount();
  await tick(20);

  bottone(ctx.document, 'Salva l’obiettivo').click();
  await tick(20);

  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.match(testo, /era già questo/);
  assert.doesNotMatch(testo, /non è stato possibile/i);
});

/* ------------------------------------------------- l'analista sulla pagina

   Il terzo attore parla dal 15/09/2026, e per un giorno la sua voce e'
   esistita solo su una rotta: la pagina prometteva «domani ragionera'
   l'analista» mentre l'analista aveva gia' parlato. Un dato che nessuno puo'
   chiedere non esiste — e questo si poteva chiedere solo con curl. */

function analisi(osservazioni) {
  return { analisi: { osservazioni: osservazioni || [] } };
}

function osservazione(extra) {
  return Object.assign({
    soggetto: 'dev1', nome: 'Inverter', misura: 'prelievo', chiave: null,
    unita: 'kWh', innesco: 1, cosa: 'il prelievo dalla rete è salito',
    spiegato: null, cosa_cambierebbe: 'spostare i consumi sulle ore di sole',
    valore: 0.74, copertura: 1, quanti_scarti: 2.75, mediana: 0.3, base: 19,
  }, extra || {});
}

test('seam _rendiAnalisi: ogni osservazione dice cosa, perché, e cosa cambierebbe', () => {
  // Le quattro cose che la spec §10 elenca. Mutazione che la uccide: non
  // rendere `cosa_cambierebbe`.
  const { corpo } = rendiAnalisi(analisi([osservazione()]));
  const testo = corpo.textContent;
  assert.match(testo, /Inverter/);
  assert.match(testo, /il prelievo dalla rete è salito/);
  assert.match(testo, /spostare i consumi sulle ore di sole/);
  assert.match(testo, /0\.74 kWh/);
});

test('seam _rendiAnalisi: l’innesco si dice a parole, non col numero', () => {
  // «1» non vuol dire niente per chi legge: i tre inneschi hanno un nome
  // nella spec, ed è quello che va in pagina.
  // Mutazione che la uccide: stampare `o.innesco`.
  const { corpo } = rendiAnalisi(analisi([
    osservazione({ innesco: 1 }),
    osservazione({ innesco: 2, misura: 'batteria' }),
    osservazione({ innesco: 3, misura: 'bilancio' }),
  ]));
  const testo = corpo.textContent;
  assert.match(testo, /è cambiato/);
  assert.match(testo, /stabile e costa/);
  assert.match(testo, /non c’è più/);
  assert.doesNotMatch(testo, /innesco 1/);
});

test('seam _rendiAnalisi: ciò che è SPIEGATO si distingue da ciò che non lo è', () => {
  // È la differenza fra una scoperta e una conferma, e la spec la chiede
  // esplicitamente. Mutazione che la uccide: non rendere `spiegato`.
  const { corpo } = rendiAnalisi(analisi([
    osservazione({ spiegato: 'coerente con il prelievo dello stesso giorno' }),
  ]));
  assert.match(corpo.textContent, /coerente con il prelievo/);
});

test('seam _rendiAnalisi: lo scostamento si dice col suo numero e con la base', () => {
  // «Non si inventa una soglia»: il numero c’è, e con quanti giorni di storia
  // è stato calcolato — «la base è sottile» è un fatto da leggere.
  // Mutazione che la uccide: non rendere `base`.
  const { corpo } = rendiAnalisi(analisi([osservazione()]));
  const testo = corpo.textContent;
  assert.match(testo, /2\.75/);
  assert.match(testo, /19 giorni/);
});

test('seam _rendiAnalisi: il SILENZIO si dice, e non sembra un guasto', () => {
  // «Il silenzio è un esito legittimo»: zero osservazioni vuol dire che ha
  // guardato e non c’era niente da dire.
  // Mutazione che la uccide: lasciare la sezione vuota.
  const { corpo } = rendiAnalisi(analisi([]));
  assert.match(corpo.textContent, /niente da segnalare/);
});

test('mount: la sezione 03 legge la chiave «analisi» della rotta', () => {
  // Mutazione che la uccide: `corpo.osservazioni` al posto di `corpo.analisi`.
  const ctx = montaConServer({ analisi: analisi([osservazione()]) });
  ctx.window.HirisWatcherRoute.mount();
  return tick(20).then(function () {
    const card3 = ctx.document.querySelectorAll('.section-card')[2];
    assert.ok(card3, 'la sezione 03 deve esistere');
    assert.match(card3.textContent, /Inverter/);
  });
});

test('mount: un giorno mai analizzato (404) lo SPIEGA', () => {
  // «Non ho guardato» e «ho guardato e non c’era niente» sono due cose
  // diverse, e la pagina deve dirle diverse.
  // Mutazione che la uccide: mostrare «niente da segnalare» anche sul 404.
  const ctx = montaConServer({ analisiStatus: 404, analisi: { errore: 'x' } });
  ctx.window.HirisWatcherRoute.mount();
  return tick(20).then(function () {
    const testo = ctx.document.querySelectorAll('.section-card')[2].textContent;
    assert.match(testo, /non ha ancora guardato/);
    assert.doesNotMatch(testo, /niente da segnalare/);
  });
});

/* -------------------------------------------- il sapere sulla pagina (§8)

   «Se un dato c'è e nessuno può chiederlo, non esiste»: il sapere si leggeva
   da tre punti del codice e da nessuna pagina. E le righe che il modello non
   ha capito sono precisamente quelle che il proprietario risolverebbe in
   dieci secondi. */

function sapereFinto(extra) {
  return Object.assign({
    conteggi: { totale: 180, righe: [
      { specie: 'tipo', campo: 'significato', provenienza: 'importato', quante: 177 },
      { specie: 'dispositivo', campo: 'ricetta', provenienza: 'dedotto', quante: 3 },
    ] },
    non_capito: [],
  }, extra || {});
}

function rendiSapere(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherRoute._rendiSapere(corpo, payload);
  return { window, document, corpo };
}

test('seam _rendiSapere: dice cosa ha capito, per specie e provenienza', () => {
  // «177 significati importati» e «tre ricette dedotte dal modello» sono due
  // fatti diversi. Mutazione che la uccide: stampare il solo totale.
  const { corpo } = rendiSapere(sapereFinto());
  const testo = corpo.textContent;
  assert.match(testo, /177/);
  assert.match(testo, /significato/);
  assert.match(testo, /importato/);
  assert.match(testo, /ricetta/);
});

test('seam _rendiSapere: ciò che NON ha capito viene prima, con chi e quando', () => {
  // È l’unica parte su cui il proprietario può fare qualcosa: in fondo a un
  // elenco di conteggi non salterebbe all’occhio — stessa regola di «cosa non
  // si sa» nel resoconto.
  // Mutazione che la uccide: metterlo dopo i conteggi.
  const { corpo } = rendiSapere(sapereFinto({ non_capito: [
    { specie: 'dispositivo', soggetto: 'dev1', campo: 'ricetta_non_capita',
      valore: 'non ho capito cosa misura', provenienza: 'dedotto',
      chi: 'modello (ponte)', quando_ts: 1787000000 },
  ] }));
  const testo = corpo.textContent;
  assert.ok(testo.indexOf('non ho capito cosa misura') < testo.indexOf('177'),
    'ciò su cui si può agire viene prima');
  assert.match(testo, /modello \(ponte\)/);
});

test('seam _rendiSapere: se ha capito tutto lo DICE, e non tace', () => {
  // Un elenco vuoto senza una parola sembrerebbe una sezione rotta.
  // Mutazione che la uccide: non scrivere niente quando non c’è niente.
  const { corpo } = rendiSapere(sapereFinto());
  assert.match(corpo.textContent, /niente che non abbia capito/);
});

test('mount: la sezione 04 legge il sapere dalla sua rotta', () => {
  // Mutazione che la uccide: leggere `corpo.sapere` invece della busta vera.
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount();
  return tick(20).then(function () {
    const card4 = ctx.document.querySelectorAll('.section-card')[3];
    assert.ok(card4, 'la sezione 04 deve esistere');
    assert.match(card4.textContent, /177/);
  });
});
