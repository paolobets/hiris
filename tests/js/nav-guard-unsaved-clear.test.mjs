import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* FINAL whole-branch review, finding I2 (Important) -- 'unsaved' non
   veniva mai pulito uscendo da un editor.

   Prima: HirisState.set('unsaved', false) veniva scritto SOLO dal mount
   di un editor (setupStickyActions). Confermare l'uscita da un editor
   dirty via il guard (editor-kit.js::dirty.guard(), installato in
   main.js) lasciava 'unsaved' true -- ogni navigazione successiva fra
   pagine SENZA form (es. Consumi -> Task) ririchiedeva la stessa conferma
   "Ci sono modifiche non salvate…", a vuoto, finché l'utente non riapriva
   un editor. File separato da tests/js/editor-unsaved-clear.test.mjs (che
   copre Annulla/deleteAgent): node --test isola i FILE in processi
   separati, non le singole test() nello stesso file -- vedi la nota in
   helpers/dom.mjs. */

test('I2a: confermando di uscire da un editor dirty, unsaved si pulisce -- navigare fra due route NON-editor dopo non richiede più conferma', () => {
  const { window } = loadScripts(['config/state.js', 'config/router.js', 'config/editor-kit.js']);

  let mountEditor = 0, mountUsage = 0, mountTasks = 0;
  window.HirisRouter.register(/^#\/chatbots\/([^/]+)$/, function() {
    mountEditor += 1;
    window.HirisState.set('unsaved', false); // setupStickyActions mimicato
  });
  window.HirisRouter.register(/^#\/usage\/?$/, function() { mountUsage += 1; });
  window.HirisRouter.register(/^#\/tasks\/?$/, function() { mountTasks += 1; });

  window.location.hash = '#/chatbots/abc';
  // Stesso pattern di main.js: onLeave pulisce 'unsaved' quando l'utente
  // conferma di uscire da un editor dirty.
  window.HirisEditorKit.dirty.guard(
    function() { return !!window.HirisState.get('unsaved'); },
    function() { window.HirisState.set('unsaved', false); }
  );
  window.HirisRouter.start();
  assert.equal(mountEditor, 1);

  // Utente edita l'editor -> dirty.
  window.HirisState.set('unsaved', true);

  let confirmCalls = 0;
  window.confirm = () => { confirmCalls += 1; return true; }; // utente conferma di uscire

  window.location.hash = '#/usage';
  window.dispatchEvent(new window.Event('hashchange'));
  assert.equal(mountUsage, 1, 'la route usage deve montare dopo la conferma');
  assert.equal(confirmCalls, 1, 'un solo confirm per uscire dall\'editor dirty');
  assert.equal(window.HirisState.get('unsaved'), false,
    'unsaved deve pulirsi quando la navigazione fuori dall\'editor viene confermata');

  // Ora naviga fra DUE pagine senza form: nessuna deve più chiedere conferma.
  window.location.hash = '#/tasks';
  window.dispatchEvent(new window.Event('hashchange'));
  assert.equal(mountTasks, 1);
  assert.equal(confirmCalls, 1,
    'BUG I2: navigare fra pagine senza form dopo aver lasciato un editor dirty non deve ririchiedere conferma');
});
