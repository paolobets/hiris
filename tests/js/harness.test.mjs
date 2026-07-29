import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Review indipendente Task 2 (Finding 1): l'harness bridga ogni
   `window.X = ...` su `globalThis` tramite un Proxy (vedi il commento in
   helpers/dom.mjs), ma prima di questo fix non faceva NESSUN teardown.
   `node --test` isola i FILE di test in processi separati, ma NON le
   singole `test()` dentro lo stesso file: girano nello stesso
   processo/globalThis, in sequenza. Senza teardown, un global lasciato da
   `loadScripts()` in un test sopravvive alla `loadScripts()` di un test
   "fratello" successivo — innocuo finché ogni test ricarica la STESSA
   lista di script (il valore viene semplicemente sovrascritto), ma un
   test che carica un SOTTOINSIEME diverso vedrebbe comunque il global del
   test precedente: un `typeof X === 'function'` potrebbe risultare vero
   per un global ereditato, non prodotto dagli script appena caricati —
   falso positivo silenzioso.

   Questo test riproduce esattamente lo scenario: il test A carica SOLO
   config/state.js (espone `window.HirisState`, specchiato su
   `globalThis.HirisState` dal proxy). Il test B carica SOLO config/api.js
   (utility bare-function, non tocca affatto HirisState) e verifica che
   `HirisState` NON sia più visibile su `globalThis`.

   Prova RED-before-fix: con l'harness precedente (nessun teardown) questo
   test B falliva — `HirisState` restava agganciato a `globalThis` dal test
   A. Con il fix (auto-cleanup a inizio di ogni loadScripts() delle chiavi
   specchiate dall'istanza precedente), il test B passa. */

test('isolamento harness (test A): state.js definisce HirisState su globalThis', () => {
  loadScripts(['config/state.js']);
  assert.equal(
    typeof globalThis.HirisState,
    'object',
    'state.js deve esporre window.HirisState, specchiato su globalThis dal proxy'
  );
});

test('isolamento harness (test B): un loadScripts() con una lista DIVERSA non deve vedere il global lasciato dal test precedente', () => {
  // Lista diversa da quella del test A: api.js espone solo funzioni bare
  // (esc/escHtml/fmtNum/...), non tocca mai HirisState.
  loadScripts(['config/api.js']);
  assert.equal(
    typeof globalThis.HirisState,
    'undefined',
    'HirisState del test A (sibling nello stesso file/processo) NON deve sopravvivere: ' +
      'se questo assert fallisce, l\'harness ha un leak di globali fra test() diversi'
  );
});
