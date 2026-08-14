import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Task B8: `build-check.js` e' la meta' che mancava a `app["build_stamp"]`
   (server.py) -- il guscio dichiara da quale build e' nato con una
   `<meta name="hiris-build">` (server._inject_version), e questo modulo la
   confronta col `build` che GET api/health restituisce (gia' mostrato a
   schermo da chat/main.js, mai confrontato con niente prima di questo task).

   Il fatto misurato che ha aperto il task: un service worker di HA puo'
   servire un guscio HTML vecchio nonostante gli asset siano fingerprintati
   e mai in cache HTTP -- il guscio e' l'unico file che CONTIENE quegli hash,
   e chiede gli script vecchi per nome. Qui si prova, PRIMA di ogni altra
   cosa, che un guscio rimasto vecchio non possa ricaricare all'infinito: un
   anello di ricaricamenti sarebbe un guasto peggiore di quello che si sta
   chiudendo.

   `window.location.reload()` non e' overridabile in jsdom (proprieta' non
   scrivibile sul prototipo di Location -- verificato: un'assegnazione diretta
   fallisce in silenzio e la vera navigazione jsdom "Not implemented" parte
   comunque). Per questo il verificatore vero non chiama mai
   `window.location.reload` direttamente: passa da `_internal_reload`,
   esposto "for test only" come `_internal_routes` in config/router.js. */

function fixtureHtml(buildMeta) {
  const meta = buildMeta ? `<meta name="hiris-build" content="${buildMeta}">` : '';
  return `<!doctype html><head>${meta}</head><body></body>`;
}

function avvia(buildMeta) {
  const ctx = loadScripts(['build-check.js'], { html: fixtureHtml(buildMeta) });
  const reloadCalls = [];
  ctx.window.HirisBuildCheck._internal_reload = () => { reloadCalls.push(true); };
  try { ctx.window.sessionStorage.clear(); } catch (e) {}
  return { ...ctx, reloadCalls };
}

test('build combaciano: nessun ricaricamento, nessuna striscia', () => {
  const { window, document, reloadCalls } = avvia('abc123');
  window.HirisBuildCheck.verifica('abc123');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('build diversi, prima volta: UN ricaricamento', () => {
  const { window, document, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222');
  assert.equal(reloadCalls.length, 1, 'deve ricaricare esattamente una volta');
  assert.equal(document.getElementById('hiris-build-mismatch'), null,
    'al primo disallineamento non si dichiara ancora nulla: si tenta il ricaricamento');
});

test('anti-anello: build ancora diversi dopo il ricaricamento (guscio rimasto vecchio) -- niente secondo ricaricamento, si dichiara', () => {
  const { window, document, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222'); // 1a chiamata: ricarica (simulata)
  window.HirisBuildCheck.verifica('nuovo222'); // 2a chiamata: il SW ha riservito lo stesso guscio vecchio

  assert.equal(reloadCalls.length, 1,
    'la guardia deve impedire un secondo ricaricamento: un anello sarebbe un guasto peggiore');
  const striscia = document.getElementById('hiris-build-mismatch');
  assert.notEqual(striscia, null, 'dopo il secondo disallineamento la striscia deve comparire');
  assert.equal(
    striscia.textContent,
    'questa interfaccia viene da un build diverso da quello in esecuzione ' +
    '(vecchio111 invece di nuovo222): svuota i dati del sito di Home Assistant',
    'la striscia deve avere il testo esatto, coi due valori dentro'
  );
});

test('la guardia si libera quando i build tornano a combaciare: un disallineamento futuro puo' + ' di nuovo ricaricare', () => {
  const { window, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222'); // tentativo di ricaricamento, guardia impostata
  window.HirisBuildCheck.verifica('vecchio111'); // combaciano ora (es. server tornato indietro)
  assert.equal(reloadCalls.length, 1);

  const reloadCalls2 = [];
  window.HirisBuildCheck._internal_reload = () => { reloadCalls2.push(true); };
  window.HirisBuildCheck.verifica('build-nuovissimo'); // un NUOVO disallineamento
  assert.equal(reloadCalls2.length, 1, 'la guardia libera deve permettere un nuovo tentativo');
});

test('senza <meta name="hiris-build"> (guscio precedente a questo task): nessun ricaricamento, nessuna striscia -- non si puo\' confrontare', () => {
  const { window, document, reloadCalls } = avvia(null);
  window.HirisBuildCheck.verifica('qualsiasi');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('senza build remoto (es. api/health fallita): nessun ricaricamento, nessuna striscia', () => {
  const { window, document, reloadCalls } = avvia('abc123');
  window.HirisBuildCheck.verifica('');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('la striscia non duplica se verifica() la richiama con la guardia gia\' scattata', () => {
  const { window, document } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222');
  window.HirisBuildCheck.verifica('nuovo222');
  window.HirisBuildCheck.verifica('nuovo222');
  const strisce = document.querySelectorAll('#hiris-build-mismatch');
  assert.equal(strisce.length, 1);
});
