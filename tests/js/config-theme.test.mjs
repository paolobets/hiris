import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* Registro C-16, il cambio dichiarato del Task 3 della Tappa 4: il tema
   dell'add-on (opzione `theme`, servita da GET api/config) vale anche per la
   configurazione. Prima questa pagina non lo chiedeva mai, e in piu' salvava
   nel browser, a ogni apertura, il tema che trovava: dopo una visita nemmeno
   la chat guardava piu' il server. Qui si prova il guscio vero
   (`config/main.js`), non solo common.js. */

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <div id="side-nav"></div>
  <div id="page-chrome"></div>
  <template id="tpl-side-nav"></template>
  <template id="tpl-page-chrome">
    <button id="theme-toggle"><svg id="ic-moon"></svg><svg id="ic-sun"></svg></button>
  </template>
</body>`;

const MODULI = ['common.js', 'config/state.js', 'config/router.js', 'config/main.js'];

async function avvia(temaServer, salvato) {
  const ctx = loadScripts(MODULI, { html: HTML });
  ctx.window.localStorage.clear();
  if (salvato) ctx.window.localStorage.setItem('hiris-theme', salvato);
  ctx.document.documentElement.removeAttribute('data-theme');
  const calls = stubFetch(ctx.window, { 'api/config': { theme: temaServer } });
  ctx.document.dispatchEvent(new ctx.window.Event('DOMContentLoaded'));
  await tick(0);
  return { ...ctx, calls };
}

test('la configurazione chiede il tema al server e lo mostra, senza salvarlo come scelta', async () => {
  const { window, document, calls } = await avvia('dark', null);
  assert.ok(calls.some((c) => c.url === 'api/config'), 'il guscio non ha chiesto il tema al server');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  assert.equal(document.getElementById('ic-sun').style.visibility, 'visible');
  assert.equal(window.localStorage.getItem('hiris-theme'), null,
    'il tema del server non diventa una scelta di chi guarda');
});

test('la scelta salvata vince sul server anche nella configurazione', async () => {
  const { document, calls } = await avvia('dark', 'light');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(calls.filter((c) => c.url === 'api/config').length, 0);
});

test('il clic sul bottone passa all\'opposto, lo ricorda, e ridisegna l\'icona', async () => {
  const { window, document } = await avvia('dark', null);
  document.getElementById('theme-toggle').click();
  assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(window.localStorage.getItem('hiris-theme'), 'light');
  assert.equal(document.getElementById('ic-moon').style.visibility, 'visible');
});
