import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch } from './helpers/dom.mjs';

/* `config/main.js` è l'ultimo script di config.html ed è l'unico posto in cui
   OGNI route della SPA di configurazione viene registrata. Se il suo IIFE si
   ferma al parse -- una chiamata cross-file a un modulo che non è stato
   caricato -- non si perde una pagina: non si registra NESSUNA route e la SPA
   intera rende bianca, senza alcun errore in pagina (solo in console).

   La regola che questo file pinna è quindi una sola, e non riguarda un
   modulo particolare: **main.js non deve mai dereferenziare un altro modulo
   al parse time**. Ogni riferimento a `window.HirisX` vive dentro un handler
   di route, dietro un `if (window.HirisX)` con un ramo `else` che rende un
   segnaposto dichiarato.

   Storia, perché il nome del file la ricorda: fino alla fetta E5 Task 6
   l'eccezione era `HirisEditorKit.dirty.guard(...)`, chiamata a livello top
   dell'IIFE senza existence-check (FINAL whole-branch review, finding I5).
   Quella riga è uscita insieme a `editor-kit.js` e ai tre editor che la
   usavano; il test NON è uscito con lei, perché il suo soggetto non era
   l'editor-kit ma main.js, che è vivo. Verificare `typeof HirisEditorKit ===
   'undefined'` sarebbe però diventato tautologico (il file non esiste più):
   la precondizione ora è che NESSUN modulo di route sia caricato, che è la
   stessa ipotesi resa vera per ogni modulo invece che per uno solo. */

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <div id="side-nav"></div>
  <div id="page-chrome"></div>
  <template id="tpl-side-nav"></template>
  <template id="tpl-page-chrome"></template>
</body>`;

/* Solo le due dipendenze che main.js usa davvero al parse (HirisState,
   HirisRouter). NESSUN modulo di route: è la simulazione di "ognuno di loro
   ha fallito il parse/caricamento". */
const SOLO_LO_SCHELETRO = ['config/state.js', 'config/router.js', 'config/main.js'];

/* Le route che config.html deve saper montare, con il testo del segnaposto
   che il ramo `else` di ciascuna promette. Se questo elenco e main.js
   divergono, o è uscita una pagina senza aggiornare il test, o ne è entrata
   una senza segnaposto. */
const ROUTE = [
  // fetta E5 Task 8: la home non e' piu' la "Dashboard" del prodotto vecchio,
  // e' «Cosa HIRIS sa» -- il segnaposto e la briciola sono cambiati con lei.
  ['#/', 'Cosa HIRIS sa'],
  // Reperto 26: la faccia di `casa.piani` (gerarchia()).
  ['#/tree', 'Albero della casa'],
  // fetta E5 Task 9: sostituisce il pannello Memoria della chat.
  ['#/memory', 'Memoria'],
  // fetta «lo schedulatore» Task 9: la terza condizione della spec, «si vede».
  ['#/agenda', 'Promesse'],
  // fetta «costruire» Task 11: approvare o rifiutare cio' che HIRIS propone
  // di scrivere in Home Assistant, leggere il prima/dopo, tornare indietro.
  ['#/constructions', 'Costruzioni'],
  // fetta «l'osservatore» Task 7: guarda la casa e ne ricava oggetti -- non
  // conclude, non parla, non tocca niente.
  ['#/watcher', 'L’osservatore'],
  ['#/usage', 'Consumi'],
  ['#/models', 'Modelli'],
  // fetta «esce il documentale»: qui c'era ['#/history', 'Storicizzazione'].
  // La pagina è uscita con la cattura dello storico che configurava, quindi
  // la route non è più registrata da main.js: lasciarla qui avrebbe fatto
  // fallire il conteggio, che è esattamente il compito di questo elenco.
  ['#/settings', 'Impostazioni chat'],
];

function avvia() {
  const ctx = loadScripts(SOLO_LO_SCHELETRO, { html: HTML });
  // fetta E5 Task 8: mountChrome() non fa piu' NESSUNA fetch -- il badge
  // `#nav-adv-count`, che interrogava una rotta uscita con la fetta E3 e
  // scriveva `0` sul suo 404, e' uscito con la sua fonte. Lo stub resta
  // perche' questo test simula "nessun modulo di route caricato" e la
  // cornice potrebbe tornare a fare rete in futuro: senza, un domani il
  // fallimento sarebbe "fetch is not a function" invece del vero motivo.
  stubFetch(ctx.window, {});
  return ctx;
}

test('main.js non dereferenzia nessun modulo di route al parse: senza NESSUNO di loro, tutte le route si registrano lo stesso', () => {
  const { window } = avvia();

  for (const globale of ['HirisDashboard', 'HirisTreeRoute', 'HirisMemoryRoute', 'HirisAgendaRoute',
                         'HirisConstructions', 'HirisWatcherRoute', 'HirisUsageRoute', 'HirisModelsRoute',
                         'HirisSettingsRoute']) {
    assert.equal(typeof window[globale], 'undefined',
      `precondizione: ${globale} non deve essere caricato in questo test`);
  }

  assert.equal(
    window.HirisRouter._internal_routes.length, ROUTE.length,
    'senza alcun modulo di route, main.js deve comunque registrarle tutte -- se si ' +
    'fermasse al parse la SPA intera renderebbe bianca, senza errore visibile in pagina'
  );
});

test('ogni route senza il proprio modulo degrada in un segnaposto dichiarato, non in una pagina muta', () => {
  const { window, document } = avvia();
  window.HirisRouter.start();

  for (const [hash, atteso] of ROUTE) {
    window.location.hash = hash;
    assert.doesNotThrow(
      () => { window.dispatchEvent(new window.Event('hashchange')); },
      `la route ${hash} non deve lanciare quando il suo modulo manca`
    );
    const outlet = document.getElementById('route-outlet');
    assert.match(outlet.textContent, new RegExp(atteso),
      `la route ${hash} deve rendere il proprio segnaposto ("${atteso}"), non restare vuota`);
    assert.equal(document.getElementById('chrome-here').textContent, atteso,
      `la briciola di ${hash} deve dire dove siamo anche senza il modulo`);
  }
});
