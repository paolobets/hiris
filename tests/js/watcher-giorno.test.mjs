import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La scheda «Il giorno» (config/watcher-giorno.js): il resoconto di UN
   giorno, col suo selettore.

   Queste prove erano in `watcher-route.test.mjs` fino al taglio del
   18/09/2026 (spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md`).
   Sono le stesse: cambia il namespace della seam
   (`HirisWatcherGiorno._rendiResoconto`), la lista `SCRIPTS`, e il fatto che
   `mount` voglia il nome della scheda. Dove una prova cercava
   `.section-card[1]` ora cerca il pannello della scheda: le sezioni numerate
   sono uscite, i pannelli hanno preso il loro posto. */

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

/* Il finto server della SOLA scheda «Il giorno»: una rotta,
   `api/mind/report`. Un altro indirizzo solleva -- se aprendo questa scheda la
   pagina chiedesse gli 86 KB dell'osservatore, il carico pigro sarebbe rotto e
   si vedrebbe qui. La chiave `resoconto` e' quella vera di
   `handlers_mind.handle_report`, ed e' PINNATA: se una delle due parti la
   rinomina, queste prove cadono. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  const corpiInviati = [];
  ctx.window.fetch = async (url, init) => {
    const u = String(url);
    chiamate.push(u);
    if (init && init.body) corpiInviati.push(String(init.body));
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

function rendiResoconto(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherGiorno._rendiResoconto(corpo, payload);
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
  window.HirisWatcherRoute.mount('giorno');
  await tick(20);

  const card3 = document.getElementById('watcher-panel-giorno');
  assert.ok(card3, 'la sezione 03 deve esistere sulla pagina');
  assert.match(card3.textContent, /Inverter/);
  assert.match(card3.textContent, /23\.71 kWh/);
});


test('mount: la pagina apre su IERI — OGGI non ha ancora un resoconto (si scrive alle 00:20)', async () => {
  // Il selettore nasce su ieri, e sono LE DUE sezioni a seguirlo. Chiedere
  // OGGI darebbe un 404 a ogni apertura della pagina, su tutt'e due.
  // Mutazione che la uccide: `dayInput.value = localToday()`.
  const ctx = montaConServer();
  ctx.window.HirisWatcherRoute.mount('giorno');
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
  window.HirisWatcherRoute.mount('giorno');
  await tick(20);

  const card3 = document.getElementById('watcher-panel-giorno');
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

/* -------------------------------------- il selettore vive nella SCHEDA (§2)

   Il taglio del 18/09/2026 sposta il selettore del giorno dentro la scheda, e
   la spec §2 promette che «lo stato sopravvive: elenchi aperti, giorno scelto,
   posizione». Il giorno scelto e' l'unico dei tre che questa scheda possiede:
   se una rilettura lo riportasse a ieri, «Aggiorna» cancellerebbe la scelta di
   chi l'ha premuto. */

test('la scheda: il selettore si costruisce UNA volta, e il giorno scelto sopravvive a una rilettura', async () => {
  // Mutazione che la uccide: in `carica`, `loadReport(banda.resoconto, null)`
  // -- cioe' rileggere sempre ieri invece del giorno che si sta guardando.
  const ctx = montaConServer();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(20);

  const pannello = ctx.document.getElementById('watcher-panel-giorno');
  const campo = pannello.querySelector('input[type=date]');
  const TRE_GIORNI_FA = giornoFa(3);
  campo.value = TRE_GIORNI_FA;
  campo.dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  assert.ok(ctx.chiamate[ctx.chiamate.length - 1].indexOf(TRE_GIORNI_FA) !== -1,
    'cambiare giorno deve chiedere quel giorno');

  const aggiorna = Array.from(pannello.querySelectorAll('button'))
    .find((b) => b.textContent === 'Aggiorna');
  assert.ok(aggiorna, 'manca «Aggiorna»: e’ l’unico modo di rileggere (spec §2)');
  aggiorna.dispatchEvent(new ctx.window.Event('click'));
  await tick(20);

  assert.equal(pannello.querySelectorAll('input[type=date]').length, 1,
    'rileggere la scheda ha costruito un SECONDO selettore');
  assert.ok(ctx.chiamate[ctx.chiamate.length - 1].indexOf(TRE_GIORNI_FA) !== -1,
    'rileggere e’ tornato a ieri: il giorno scelto non sopravvive');

  // La banda si RITROVA, non si ricostruisce: e' la proprieta' su cui poggia
  // tutto il resto di questa prova, e qui si guarda da sola.
  const banda = ctx.window.HirisWatcherGiorno._rendiBanda(pannello.querySelector('.sc-body'));
  assert.equal(banda.campo, campo, '`_rendiBanda` ha costruito un campo nuovo invece di ritrovare il suo');
});
