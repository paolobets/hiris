import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Sprint coerenza, lotto A, task 5 (A9): il widget "Utilizzo" della chat
   (static/index.html) mostra richieste/token/costo ma non diceva MAI da
   quando quei numeri contano -- l'elemento #usage-last-reset che
   config/api.js::loadUsage() cerca non esisteva in nessun file. Quando la
   risposta portava `last_reset`, l'assegnamento su un elemento assente
   sollevava e il `catch(e) {}` vuoto la inghiottiva -- ogni 30 secondi
   (chat/main.js chiama loadUsage() a intervalli), per sempre, senza che
   nulla lo segnalasse in console. Qui si verifica sia l'elemento aggiunto
   sia la resilienza: un nodo mancante non deve piu' bloccare gli altri. */

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
  assert.equal(document.getElementById('u-cost').textContent, '€0.1234');
  assert.match(document.getElementById('usage-last-reset').textContent, /Azzerato il/,
    'deve dire da quando i numeri contano');
});

test('senza #usage-last-reset in pagina, gli altri contatori si popolano comunque (fix del difetto A9)', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml(false) });
  window.fetch = async () => jsonResponse({
    total_requests: 7, input_tokens: 500, output_tokens: 300,
    cost_eur: 0.02, last_reset: '2026-07-01T00:00:00Z',
  });

  // Prima della correzione, l'assegnamento su #usage-last-reset (assente)
  // sollevava e il catch vuoto impediva a QUESTI di girare -- restavano
  // fermi a '—' per sempre, ogni 30 secondi, senza una riga in console.
  await assert.doesNotReject(() => globalThis.loadUsage());
  assert.equal(document.getElementById('u-requests').textContent, '7');
  assert.equal(document.getElementById('u-input').textContent, '500');
  assert.equal(document.getElementById('u-output').textContent, '300');
  assert.equal(document.getElementById('u-cost').textContent, '€0.0200');
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
