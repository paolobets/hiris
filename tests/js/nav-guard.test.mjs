import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Fix guard/router echo (CRITICAL -- live bug #2 NON chiuso da Task 3).

   HirisEditorKit.dirty.guard() (editor-kit.js) chiude correttamente il
   percorso "conferma -> esci": su hashchange, se isDirtyFn() e l'utente
   conferma, la navigazione procede. Ma il percorso che conta di più --
   "rifiuta -> resta ed edita ancora" -- NON era chiuso:

   1) utente su #/chatbots/abc (dirty), clic su un link sidebar ->
      hashchange verso #/tasks.
   2) il guard (listener registrato PRIMA del router -- in config.html
      chatbot-editor.js chiama dirty.guard() al parse time, main.js
      registra il proprio hashchange solo dentro HirisRouter.start() in
      DOMContentLoaded) intercetta l'evento, chiede conferma, l'utente
      RIFIUTA.
   3) il guard ripristina window.location.hash all'hash precedente e
      chiama stopImmediatePropagation() SU QUESTO evento -- corretto, il
      router non vede la navigazione verso #/tasks.
   4) MA quel ripristino dell'hash genera un SECONDO hashchange (l'eco,
      B->A) -- su questo il guard vede reverting=true, si limita a
      resettare il flag e ritorna SENZA stopImmediatePropagation(). Il
      router (secondo listener, ordine di registrazione) ri-risolve
      #/chatbots/abc -- che è ESATTAMENTE la route già montata -- e la
      rimonta. mount() azzera lo stato dell'editor (setupStickyActions
      resetta 'unsaved' a false, ripopola dai dati salvati sul server):
      scegliere "resta" perdeva comunque le modifiche.

   Harness fedele all'ordine di caricamento reale (config.html righe
   219-256): state.js, router.js, editor-kit.js. Una coppia di route
   fittizie con contatore di mount sta al posto della registrazione reale
   di main.js (main.js:138-142 per la route chatbot). */

function setup() {
  return loadScripts(['config/state.js', 'config/router.js', 'config/editor-kit.js']);
}

test('guard: decline-and-stay non deve rimontare la route (eco hashchange del revert)', () => {
  const { window } = setup();

  let mountCountA = 0;
  let mountCountB = 0;
  window.HirisRouter.register(/^#\/chatbots\/([^/]+)$/, function() {
    mountCountA += 1;
    // Mimica setupStickyActions (chatbot-editor.js): ogni mount resetta
    // 'unsaved' a false -- è esattamente il meccanismo che cancella le
    // modifiche se la route rimonta a torto.
    window.HirisState.set('unsaved', false);
  });
  window.HirisRouter.register(/^#\/tasks\/?$/, function() {
    mountCountB += 1;
  });

  // Ordine dei listener come in produzione: il guard viene installato
  // PRIMA che il router parta (chatbot-editor.js gira prima di
  // main.js/DOMContentLoaded).
  window.location.hash = '#/chatbots/abc';
  window.HirisEditorKit.dirty.guard(function() { return !!window.HirisState.get('unsaved'); });
  window.HirisRouter.start(); // mount iniziale di #/chatbots/abc

  assert.equal(mountCountA, 1, 'mount iniziale della route A');

  // L'utente edita -> editor dirty.
  window.HirisState.set('unsaved', true);

  // Clic su un link sidebar -> hashchange verso #/tasks. Il guard chiede
  // conferma; l'utente RIFIUTA (vuole restare sull'editor).
  window.confirm = () => false;
  window.location.hash = '#/tasks';
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(mountCountB, 0, 'la route B non deve mai montare: il guard blocca la navigazione sul primo evento');
  assert.equal(window.location.hash, '#/chatbots/abc', 'hash ripristinato ad A dal guard');

  // Il ripristino dell'hash sopra genera, in un browser vero, un SECONDO
  // hashchange (B->A) come evento/task separato -- l'harness lo riproduce
  // esplicitamente qui perché jsdom in questa configurazione non lo
  // dispatcha da solo (stesso pattern già usato in editor-kit.test.mjs
  // per il primo hashchange).
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(mountCountA, 1,
    'BUG CRITICO #2: la route A non deve rimontare sull\'eco del revert -- un remount cancella le modifiche non salvate anche scegliendo "resta"');
  assert.equal(window.HirisState.get('unsaved'), true,
    'lo stato dirty deve sopravvivere: se il mount fosse ripartito, setupStickyActions lo avrebbe resettato a false');
});
