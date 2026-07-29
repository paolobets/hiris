import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch } from './helpers/dom.mjs';

/* FINAL whole-branch review, finding I5 (Important) -- chiamata cross-file
   senza existence-check al parse time di main.js.

   main.js:19 (prima del fix) chiamava HirisEditorKit.dirty.guard(...) a
   livello top del proprio IIFE, PRIMA di qualunque HirisRouter.register(),
   senza alcun controllo di esistenza -- ogni ALTRA chiamata cross-file in
   main.js (window.HirisDashboard, window.HirisChatbotEditor, ecc.) è
   dietro un `if (window.HirisX)`. Se editor-kit.js fallisse il parse (un
   errore di sintassi spedito in un rilascio), `HirisEditorKit` non
   esisterebbe -- main.js lanciava un ReferenceError non catturato al
   parse, e l'intero resto del file (tutte le HirisRouter.register() e il
   DOMContentLoaded che chiama HirisRouter.start()) non veniva mai
   eseguito: l'intera SPA di config renderizzava bianca (Brain, Chatbot,
   Agentbot, Modelli, Gateway, Storico...), senza errore visibile in
   pagina.

   Questo test carica main.js SENZA editor-kit.js (lo simula "rotto/
   mancante") e verifica che il resto del file esegua comunque -- le
   route si registrano, nessuna eccezione emerge da loadScripts(). */

test('I5: main.js senza HirisEditorKit non lancia al parse -- le route si registrano comunque (nessuna SPA bianca)', () => {
  // Nota: NON carichiamo config/editor-kit.js -- simula un file che ha
  // fallito il parse/caricamento (HirisEditorKit resta undefined).
  const { window } = loadScripts(['config/state.js', 'config/router.js', 'config/main.js'], {
    html: `<!doctype html><body>
      <div id="chrome-here"></div>
      <div id="route-outlet"></div>
      <div id="side-nav"></div>
      <div id="page-chrome"></div>
      <template id="tpl-side-nav"></template>
      <template id="tpl-page-chrome"></template>
    </body>`,
  });
  // mountChrome() (DOMContentLoaded, jsdom lo dispatcha async dopo il load
  // iniziale) fa fetch di badge/contatori -- stub per non sporcare l'output
  // con richieste di rete reali/errori "fetch is not a function".
  stubFetch(window, {});

  assert.equal(typeof window.HirisEditorKit, 'undefined',
    'precondizione del test: editor-kit.js non è caricato, come se avesse fallito il parse');

  assert.ok(
    window.HirisRouter._internal_routes.length > 0,
    'BUG I5: senza HirisEditorKit, main.js deve comunque registrare tutte le HirisRouter.register() sotto -- se si fermasse al parse, la SPA intera renderebbe bianca'
  );

  // La route Dashboard (prima registrata) deve combaciare e non lanciare.
  window.location.hash = '#/';
  assert.doesNotThrow(() => { window.HirisRouter.start(); },
    'HirisRouter.start() deve poter risolvere la route iniziale anche senza HirisEditorKit');
});
