import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La scheda «Cosa fare» (config/watcher-cosa-fare.js): le osservazioni
   dell'analista, l'unica cosa della pagina che chiede un'AZIONE.

   Queste prove erano in `watcher-route.test.mjs` fino al taglio del
   18/09/2026 (spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md`).
   Sono le stesse: cambia il namespace della seam
   (`HirisWatcherCosaFare._rendiAnalisi`), la lista `SCRIPTS`, e il fatto che
   `mount` voglia il nome della scheda. */

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

/* Il finto server della SOLA scheda «Cosa fare»: una rotta,
   `api/mind/analysis`. Un altro indirizzo solleva. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url) => {
    const u = String(url);
    chiamate.push(u);
    if (u.indexOf('api/mind/analysis') === 0) {
      if (opts.analisiRotta) throw new Error('rete interrotta');
      return jsonResponse(
        opts.analisi !== undefined ? opts.analisi : { analisi: { osservazioni: [] } },
        opts.analisiStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate });
}

function rendiAnalisi(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherCosaFare._rendiAnalisi(corpo, payload.analisi);
  return { window, document, corpo };
}

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
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  return tick(20).then(function () {
    const card3 = ctx.document.getElementById('watcher-panel-cosa-fare');
    assert.ok(card3, 'la sezione 03 deve esistere');
    assert.match(card3.textContent, /Inverter/);
  });
});

test('mount: un giorno mai analizzato (404) lo SPIEGA', () => {
  // «Non ho guardato» e «ho guardato e non c’era niente» sono due cose
  // diverse, e la pagina deve dirle diverse.
  // Mutazione che la uccide: mostrare «niente da segnalare» anche sul 404.
  const ctx = montaConServer({ analisiStatus: 404, analisi: { errore: 'x' } });
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  return tick(20).then(function () {
    const testo = ctx.document.getElementById('watcher-panel-cosa-fare').textContent;
    assert.match(testo, /non ha ancora guardato/);
    assert.doesNotMatch(testo, /niente da segnalare/);
  });
});
