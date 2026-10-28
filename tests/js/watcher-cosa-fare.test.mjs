import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';
import { fintoFetch, risposta } from './helpers/fetch.mjs';

/* La scheda «Cosa fare» (config/watcher-cosa-fare.js): le osservazioni
   dell'analista, l'unica cosa della pagina che chiede un'AZIONE.

   Queste prove erano in `watcher-route.test.mjs` fino al taglio del
   18/09/2026 (spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md`).
   Sono le stesse: cambia il namespace della seam
   (`HirisWatcherCosaFare._rendiAnalisi`), la lista `SCRIPTS`, e il fatto che
   `mount` voglia il nome della scheda. */

const SCRIPTS = ['common.js', 'config/watcher-shared.js', 'config/watcher-giorno.js',
  'config/watcher-cosa-fare.js', 'config/watcher-sapere.js',
  'config/watcher-lavoro.js', 'config/state.js', 'config/router.js',
  'config/watcher-route.js'];

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

/* Il finto server della SOLA scheda «Cosa fare»: una rotta,
   `api/mind/analysis`. Un altro indirizzo fa fallire la prova (helpers/fetch.mjs). */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  fintoFetch(ctx.window, {
    'api/mind/analysis': () => {
      if (opts.analisiRotta) throw new Error('rete interrotta');
      return risposta(
        opts.analisi !== undefined ? opts.analisi : { analisi: { osservazioni: [] } },
        opts.analisiStatus);
    },
  });
  return ctx;
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

test('seam _rendiAnalisi: l’innesco si dice a parole, quelle che manda la rotta (C-11)', () => {
  // «1» non vuol dire niente per chi legge: la parola arriva accanto al
  // numero (`innesco_parole`, `mind/analyst.TRIGGER_WORDS`). Parole finte:
  // se la pagina le scrive, le ha lette dalla rotta e non da una sua copia.
  // Mutazioni che la uccidono: stampare `o.innesco`; tornare a una tabella
  // della pagina indicizzata dal numero.
  const { corpo } = rendiAnalisi(analisi([
    osservazione({ innesco: 1, innesco_parole: 'PAROLA UNO DAL SERVER' }),
    osservazione({ innesco: 2, misura: 'batteria', innesco_parole: 'PAROLA DUE DAL SERVER' }),
  ]));
  const testo = corpo.textContent;
  assert.match(testo, /Perché l’ho guardata: PAROLA UNO DAL SERVER\./);
  assert.match(testo, /PAROLA DUE DAL SERVER/);
  assert.doesNotMatch(testo, /è cambiato|stabile e costa/);
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

test('seam _rendiAnalisi: la domanda e la risposta stanno su righe DIVERSE, e il «non lo so» si dice', () => {
  /* Fase B (28/10/2026), frase (b) della fotografia della Fase L: «è
     cambiato, e non è spiegato. È spiegato: …» in una riga sola, e «..».
     Mutazioni ESEGUITE il 28/10/2026: innesco e spiegazione di nuovo nella
     stessa riga -- rossa sul conto delle righe; `closeSentence` sostituito
     da `+ '.'` -- rossa su «..». Ripristinate, `git status` pulito. */
  const spiegata = rendiAnalisi(analisi([osservazione({
    innesco_parole: 'è cambiato rispetto al solito',
    spiegato: 'il forno è rimasto acceso.',
  })])).corpo;
  const righe = [...spiegata.querySelectorAll('.sc-row-why')].map((r) => r.textContent);
  assert.ok(righe.includes('Perché l’ho guardata: è cambiato rispetto al solito.'), righe);
  assert.ok(righe.includes('Si spiega con: il forno è rimasto acceso.'), righe);
  assert.doesNotMatch(spiegata.textContent, /\.\./, 'nessun punto raddoppiato');

  const ignota = rendiAnalisi(analisi([osservazione({ spiegato: null })])).corpo;
  assert.match(ignota.textContent, /Non so ancora spiegarlo\./);
  assert.doesNotMatch(ignota.textContent, /Si spiega con/);
});

test('seam _rendiAnalisi: accanto all’osservazione c’è la casa di ADESSO, dai `soggetti`', () => {
  /* Rimedio B.2 (23/10/2026): la rotta manda `adesso`, la pagina lo mostra
     dalla Fase B. Mutazione ESEGUITA il 28/10/2026: `rigaAdesso` che non
     disegna niente -- rossa. Ripristinata, `git status` pulito. */
  const { corpo } = rendiAnalisi(analisi([
    osservazione({ adesso: [
      { id: 'climate.cucina', nome: 'Termostato cucina', stato: 'heat', stato_leggibile: 'riscalda' },
      { id: 'sensor.t', nome: 'Temperatura', stato: '20.5', unita: '°C' },
    ] }),
    osservazione({ misura: 'vecchia' }),
  ]));
  const adesso = [...corpo.querySelectorAll('.field-hint')]
    .map((r) => r.textContent).filter((t) => t.indexOf('Adesso:') === 0);
  assert.deepEqual(adesso, ['Adesso: Termostato cucina · riscalda', 'Adesso: Temperatura · 20.5 °C'],
    'una riga per soggetto, e niente per l’osservazione scritta prima dei soggetti');
});

test('seam _rendiAnalisi: la novità si dice con la parola del server', () => {
  const { corpo } = rendiAnalisi(analisi([
    osservazione({ novita: 'nuova', novita_parole: 'nuova' }),
    osservazione({ misura: 'b', novita: 'prova cambiata', novita_parole: 'già detta, ma la prova è cambiata' }),
    osservazione({ misura: 'c' }),
  ]));
  // Le parole sono del server (`analyst.NOVELTY_WORDS`): la pagina non ne
  // tiene una tabella, e una riga senza `novita_parole` non dice niente.
  // Mutazione ESEGUITA il 28/10/2026: la riga tolta da `renderAnalysis` --
  // rossa qui. Ripristinata.
  const righe = [...corpo.querySelectorAll('.sc-row')].map((r) =>
    [...r.querySelectorAll('.field-hint')].map((h) => h.textContent));
  assert.ok(righe[0].includes('Nuova.'), righe[0]);
  assert.ok(righe[1].includes('Già detta, ma la prova è cambiata.'), righe[1]);
  assert.ok(!righe[2].some((t) => /nuova|già detta/i.test(t)), righe[2]);
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
  const ctx = montaConServer({ analisiStatus: 404, analisi: { error: 'x' } });
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  return tick(20).then(function () {
    const testo = ctx.document.getElementById('watcher-panel-cosa-fare').textContent;
    assert.match(testo, /non ha ancora guardato/);
    assert.doesNotMatch(testo, /niente da segnalare/);
  });
});

test('mount: il 404 dice ogni quanto gira l’analista col numero della rotta (C-11)', () => {
  // `analista_ogni_s` arriva col rifiuto (`mind/report.ANALYST_EVERY_MINUTES`).
  // Un valore che non e' quello vero: la pagina non deve dire «ogni ora».
  const ctx = montaConServer({ analisiStatus: 404, analisi: { error: 'x', analista_ogni_s: 7200 } });
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  return tick(20).then(function () {
    const testo = ctx.document.getElementById('watcher-panel-cosa-fare').textContent;
    assert.match(testo, /Gira ogni 2 ore/);
    assert.doesNotMatch(testo, /all’ora|ogni ora/);
  });
});

test('mount: con 3600 secondi il 404 dice «ogni ora», non «ogni 1 ora»', () => {
  const ctx = montaConServer({ analisiStatus: 404, analisi: { error: 'x', analista_ogni_s: 3600 } });
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  return tick(20).then(function () {
    const testo = ctx.document.getElementById('watcher-panel-cosa-fare').textContent;
    assert.match(testo, /Gira ogni ora,/);
  });
});


/* -------------------------------------------------------------------------
   Il PROPONENTE sulla scheda (attori, strato 4, Task 4.6).

   Le osservazioni sono domande, e la risposta va **sotto la domanda**: in una
   pagina sua servirebbe una giuntura per rimetterle insieme. L'esito arriva
   gia' attaccato dalla rotta (`mind/view._with_outcomes`), nella forma del
   proponente: `costruita` e `a_mano` col solo riferimento alla proposta,
   `niente` col suo perché.
   ------------------------------------------------------------------------- */

function conEsito(esito) {
  return {
    osservazioni: [{ soggetto: 'dev1', nome: 'Inverter', misura: 'prelievo',
      innesco: 1, base: 19, cosa: 'il prelievo si stacca',
      cosa_cambierebbe: 'spostare i consumi', esito: esito }],
  };
}

test('seam _rendiAnalisi: «niente» si legge col suo PERCHÉ', () => {
  /* Rossa su `9f478891`: la scheda conosceva solo i gesti del vecchio
     attuatore, e l'esito del proponente non diceva niente.
     Mutazione che la uccide: non disegnare il perché. */
  const { corpo } = rendiAnalisi({ analisi: conEsito({ impronta: 'k', esito: 'niente',
    perche: 'il prelievo è dello scaldabagno, fra le 19 e le 22' }) });

  assert.match(corpo.textContent, /fra le 19 e le 22/);
  assert.match(corpo.textContent, /niente da proporre/i,
    'l\'esito si dice, o il perché è una frase orfana');
});

test('seam _rendiAnalisi: una proposta COSTRUITA rimanda alle Proposte', () => {
  /* La proposta vive nel suo archivio: qui c'è il riferimento, non la copia.
     Mutazione che la uccide: usare la frase di «a_mano». */
  const { corpo } = rendiAnalisi({ analisi: conEsito({ impronta: 'k', esito: 'costruita',
    proposta_id: 'c1' }) });

  assert.match(corpo.textContent, /HIRIS può fare/);
  assert.match(corpo.textContent, /Proposte/);
});

test('seam _rendiAnalisi: una proposta DA FARE A MANO rimanda alle Proposte', () => {
  /* Mutazione che la uccide: usare la frase di «costruita». */
  const { corpo } = rendiAnalisi({ analisi: conEsito({ impronta: 'k', esito: 'a_mano',
    proposta_id: 'p1' }) });

  assert.match(corpo.textContent, /da fare a mano/);
  assert.match(corpo.textContent, /Proposte/);
});

test('seam _rendiAnalisi: senza esito la scheda non dice niente sul proponente', () => {
  /* Un'osservazione senza esito è una domanda a cui il proponente non ha
     ancora risposto: il giro dopo la richiede. Dire «non so cosa proporre»
     sarebbe falso, e un esito che non conosciamo non si inventa.
     Mutazione che la uccide: scrivere una frase anche senza esito. */
  const { corpo } = rendiAnalisi({ analisi: conEsito(null) });
  const { corpo: ignoto } = rendiAnalisi({ analisi: conEsito({ impronta: 'k',
    esito: 'indagine', trovato: 'x' }) });

  assert.doesNotMatch(corpo.textContent, /propo/i);
  assert.doesNotMatch(ignoto.textContent, /propo/i);
});
