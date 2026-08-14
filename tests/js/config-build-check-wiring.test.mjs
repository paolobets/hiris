import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* Task B8: la SPA di configurazione non faceva NESSUNA fetch a api/health
   prima di questo task (verificato: `grep -rn "api/health" static/config/`
   dava zero righe) -- e' per questo che config/main.js guadagna qui una
   fetch nuova, mentre chat/main.js ESTENDE quella che gia' aveva.
   build-check.test.mjs prova il modulo condiviso isolato; questo file prova
   che config/main.js lo chiama DAVVERO al boot, con lo stesso rischio
   "classe testata ma mai collegata" di chat-build-check-wiring.test.mjs. */

const HTML = (buildLocale) => `<!doctype html><head>
  <meta name="hiris-build" content="${buildLocale}">
</head><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <div id="side-nav"></div>
  <div id="page-chrome"></div>
  <template id="tpl-side-nav"></template>
  <template id="tpl-page-chrome"></template>
</body>`;

const MODULI = ['config/state.js', 'config/router.js', 'config/main.js', 'build-check.js'];

function avvia(buildLocale, buildRemoto) {
  const ctx = loadScripts(MODULI, { html: HTML(buildLocale) });
  const reloadCalls = [];
  ctx.window.HirisBuildCheck._internal_reload = () => { reloadCalls.push(true); };
  try { ctx.window.sessionStorage.clear(); } catch (e) {}
  stubFetch(ctx.window, { 'api/health': { status: 'ok', version: '3.0.0', build: buildRemoto } });
  return { ...ctx, reloadCalls };
}

test('boot della configurazione: build locale e remoto combaciano -- config/main.js reale non ricarica mai', async () => {
  const { window, document, reloadCalls } = avvia('stampX', 'stampX');
  document.dispatchEvent(new window.Event('DOMContentLoaded'));
  await tick(0);
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('boot della configurazione: build locale diverso dal remoto -- config/main.js reale lo scopre da solo e tenta il ricaricamento', async () => {
  const { window, document, reloadCalls } = avvia('vecchio-nella-pagina', 'nuovo-sul-server');
  document.dispatchEvent(new window.Event('DOMContentLoaded'));
  await tick(0);
  assert.equal(reloadCalls.length, 1,
    'config/main.js deve fare GET api/health e passare d.build a HirisBuildCheck.verifica() al boot -- ' +
    'se questa chiamata manca, la pagina Modelli puo\' restare col guscio vecchio senza che nessuno se ne accorga (il fatto che ha aperto questo task)');
});
