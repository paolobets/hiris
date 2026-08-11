import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Task 11 (fetta E5 "il vocabolario che resta dice il vero"), Step 3:
   tests/static/test_state.html era un harness manuale (nessuno lo esegue:
   ne' npm test, ne' la CI) sul soggetto `config/state.js`, che e' vivo --
   `main.js` chiama `HirisState.subscribe('route', updateNavActive)` e
   `router.js` chiama `HirisState.set('route', ...)` a ogni navigazione
   riuscita. Nessun test in tests/js/*.test.mjs esercitava pero' il
   contratto pubblico di state.js (get/set/subscribe/unsubscribe) in modo
   diretto: router-retry.test.mjs e main-boot-guard.test.mjs lo *usano*
   (indirettamente, via router.js/main.js) ma non ne asseriscono il
   comportamento. Le quattro asserzioni che seguono sono la migrazione di
   quelle di test_state.html che difendono un comportamento vivo.

   Non migrata: "dirty flag default false" (HirisState.get('unsaved')).
   La chiave 'unsaved' non ha piu' alcun lettore in hiris/app/static/ --
   il guard che la leggeva viveva in editor-kit.js, uscito alla fetta E5
   Task 6 insieme ai tre editor che lo usavano. Il default `unsaved: false`
   resta nell'oggetto interno di state.js ma non protegge piu' nulla:
   portare quell'assert avrebbe difeso una chiave morta, non un
   comportamento vivo. */

function setup() {
  return loadScripts(['config/state.js']);
}

test('HirisState esiste ed espone l\'oggetto pub-sub', () => {
  const { window } = setup();
  assert.equal(typeof window.HirisState, 'object');
});

test('set/get funzionano', () => {
  const { window } = setup();
  window.HirisState.set('foo', 42);
  assert.equal(window.HirisState.get('foo'), 42);
});

test('subscribe scatta su set -- il meccanismo che main.js usa per aggiornare il nav attivo a ogni cambio di route', () => {
  const { window } = setup();
  let fired = false;
  const unsub = window.HirisState.subscribe('bar', (v) => { fired = (v === 'baz'); });
  window.HirisState.set('bar', 'baz');
  unsub();
  assert.equal(fired, true);
});

test('unsubscribe ferma le notifiche successive', () => {
  const { window } = setup();
  let count = 0;
  const unsub = window.HirisState.subscribe('q', () => { count += 1; });
  window.HirisState.set('q', 1);
  unsub();
  window.HirisState.set('q', 2);
  assert.equal(count, 1);
});
