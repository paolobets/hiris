import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts } from './helpers/dom.mjs';

/* Sprint coerenza, lotto A, task 5 (A9): il widget "Utilizzo" della chat
   (static/index.html) mostra richieste/token/costo ma non diceva MAI da
   quando quei numeri contano -- l'elemento #usage-last-reset che
   config/api.js::loadUsage() cerca non esisteva in nessun file. La risposta
   con `last_reset` faceva sollevare quell'ultimo assegnamento (elemento
   assente) e il `catch(e) {}` vuoto lo inghiottiva senza mai loggare, ogni
   30 secondi (chat/main.js chiama loadUsage() a intervalli).

   Correzione I-3 (review indipendente su bee3ab1): il commento originale di
   questo commit sosteneva che l'elemento mancante impedisse anche ai QUATTRO
   contatori (richieste/input/output/costo) di popolarsi. E' falso e verificato
   qui sotto (worktree di bee3ab1~1): in loadUsage() quei quattro assegnamenti
   vengono PRIMA di usage-last-reset, quindi giravano gia' regolarmente --
   solo la data di azzeramento restava sempre vuota, in silenzio. Il test
   "gli altri contatori si popolano comunque" passava gia' prima di questa
   correzione: non e' una regressione di niente, resta come test di
   caratterizzazione dell'invariante (ora garantita per costruzione da
   _setUsageText, non per un ordine di codice che potrebbe cambiare). I test
   che verificano davvero il fix sono: l'elemento aggiunto (sotto), il
   logging del fallimento di rete (che PRIMA era silenzioso), e la presenza
   del nodo in index.html (che prima di questa correzione nessun test
   copriva -- si poteva cancellare il div e la suite restava verde). */

const SCRIPTS = ['config/api.js'];

function fixtureHtml(withLastReset) {
  return `<!doctype html><body>
    <div id="usage-widget">
      <span class="usage-val" id="u-requests">—</span>
      <span class="usage-val" id="u-input">—</span>
      <span class="usage-val" id="u-output">—</span>
      <span class="usage-val" id="u-cost">—</span>
      ${withLastReset ? '<div class="usage-reset" id="usage-last-reset"></div>' : ''}
    </div>
  </body>`;
}

function jsonResponse(body) {
  return { ok: true, status: 200, json: async () => body };
}

test('con tutti gli elementi presenti, loadUsage popola anche la data di azzeramento', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml(true) });
  window.fetch = async () => jsonResponse({
    total_requests: 42, input_tokens: 1200, output_tokens: 800,
    cost_eur: 0.1234, last_reset: '2026-07-01T00:00:00Z',
  });

  await globalThis.loadUsage();

  assert.equal(document.getElementById('u-requests').textContent, '42');
  /* Era `€0.1234`. Un costo si legge a due decimali, e soprattutto si legge
     ALLO STESSO MODO nelle due superfici: la pagina «Consumi» mostrava gli
     stessi dati come `€ 3.21` mentre questo riquadro scriveva `€3.2149`, e chi
     guardava l'una dopo l'altra aveva ragione di credere che una delle due
     stesse sbagliando. Adesso il formato viene da `fmtEuro` (config/api.js),
     che e' l'unico posto in cui e' scritto. */
  assert.equal(document.getElementById('u-cost').textContent, '€ 0.12');
  assert.match(document.getElementById('usage-last-reset').textContent, /Azzerato il/,
    'deve dire da quando i numeri contano');
});

test('senza #usage-last-reset in pagina, gli altri contatori si popolano comunque (caratterizzazione -- gia\' vera prima di bee3ab1, vedi commento in cima al file)', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml(false) });
  window.fetch = async () => jsonResponse({
    total_requests: 7, input_tokens: 500, output_tokens: 300,
    cost_eur: 0.02, last_reset: '2026-07-01T00:00:00Z',
  });

  // NON e' una regressione di bee3ab1 (i quattro assegnamenti precedono
  // usage-last-reset in loadUsage(), quindi giravano gia'): resta come test
  // dell'invariante "un elemento mancante non blocca gli altri", ora
  // garantita per costruzione da _setUsageText() invece che da un ordine di
  // codice che potrebbe cambiare senza preavviso.
  await assert.doesNotReject(() => globalThis.loadUsage());
  assert.equal(document.getElementById('u-requests').textContent, '7');
  assert.equal(document.getElementById('u-input').textContent, '500');
  assert.equal(document.getElementById('u-output').textContent, '300');
  assert.equal(document.getElementById('u-cost').textContent, '€ 0.02');
});

// ---------------------------------------------------------------------------
// I-3: il test che manca davvero. Oggi si puo' cancellare il div
// #usage-last-reset da index.html e la suite resta verde (loadUsage() lo
// cerca via _setUsageText, che non solleva se l'elemento non c'e' -- quindi
// nessun test sopra si accorgerebbe della sua sparizione). Verifica diretta
// sul markup spedito, non sul comportamento di loadUsage().
// ---------------------------------------------------------------------------

test('static/index.html contiene #usage-last-reset (senza, il div si puo\' cancellare senza che nulla se ne accorga)', () => {
  const html = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'index.html'),
    'utf8'
  );
  assert.match(html, /id=["']usage-last-reset["']/,
    'index.html deve contenere il nodo che loadUsage() popola con la data di azzeramento');
});

test('un fallimento di rete non lascia il guasto invisibile: console.error registra qualcosa', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml(true) });
  window.fetch = async () => { throw new Error('offline'); };

  const realError = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args);
  try {
    await globalThis.loadUsage();
  } finally {
    console.error = realError;
  }

  assert.ok(logged.length > 0, 'il catch vuoto non deve più inghiottire il guasto senza traccia');
  // i contatori restano al placeholder iniziale, non un valore inventato
  assert.equal(document.getElementById('u-requests').textContent, '—');
});
