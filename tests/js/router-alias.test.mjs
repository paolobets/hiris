import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch } from './helpers/dom.mjs';

/* Gli indirizzi DI PRIMA -- la tabella di `config/router.js` che manda un
   hash italiano sulla pagina che oggi ha un nome inglese.

   Perché esiste, in una riga: l'hash si vede nella barra del browser e
   finisce nei segnalibri. La porta 8099 dell'add-on può essere esposta da
   Home Assistant (`hiris/config.yaml`, sezione `ports`), quindi
   `http://<casa>:8099/config.html#/promesse` è un URL stabile che qualcuno
   può aver salvato prima della fetta della rinomina (02/09). Senza la
   tabella quel segnalibro riceverebbe «Pagina non trovata».

   **QUESTO FILE È LA METÀ ESEGUIBILE DELLA CONDIZIONE D'USCITA.** La
   tabella si toglie il giorno in cui nessun segnalibro in circolazione
   punta più a un hash italiano -- e quel giorno si misura sull'USO, non su
   questo repository, esattamente come per l'avviso sui nomi vecchi degli
   strumenti (`agent/prompts.py::_OLD_NAMES_NOTICE`). Il repository, da
   oggi, non contiene già più un solo hash italiano: se la condizione la
   decidesse lui, direbbe «togliila» subito e avrebbe torto.

   Ciò che questo file PUÒ decidere da solo, e decide:
   1. ogni BERSAGLIO deve essere una route che `main.js` registra davvero --
      altrimenti il giorno in cui `#/tree` venisse rinominato di nuovo la
      tabella manderebbe un segnalibro valido su una pagina che non c'è più,
      in silenzio;
   2. nessuna SORGENTE può essere a sua volta una route viva -- altrimenti
      la tabella oscurerebbe una pagina vera;
   3. la tabella non può svuotarsi: il giorno in cui qualcuno la svuota
      questo test diventa rosso e dice di togliere anche sé stesso. È il
      promemoria, e non c'è nessun altro posto in cui vivrebbe. */

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <div id="side-nav"></div>
  <div id="page-chrome"></div>
  <template id="tpl-side-nav"></template>
  <template id="tpl-page-chrome"></template>
</body>`;

/* Nessun modulo di route: ogni handler degrada nel proprio segnaposto, che
   è quanto basta per dire SU QUALE pagina si è atterrati. Stessa ipotesi di
   `main-boot-guard.test.mjs`, e per la stessa ragione: il soggetto qui è il
   router, non le pagine. */
const SCRIPTS = ['config/state.js', 'config/router.js', 'config/main.js'];

/* Il segnaposto che ogni bersaglio deve rendere -- è così che si prova di
   essere ATTERRATI sulla pagina, invece di guardare solo la barra. */
const SEGNAPOSTO = {
  '#/tree': 'Albero della casa',
  '#/memory': 'Memoria',
  '#/agenda': 'Promesse',
  '#/constructions': 'Costruzioni',
  '#/watcher': 'L’osservatore',
  '#/settings': 'Impostazioni chat',
};

function avvia() {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  stubFetch(ctx.window, {});
  return ctx;
}

test('ogni hash italiano di prima porta sulla pagina di oggi, e la barra dice il nome nuovo', () => {
  const { window, document } = avvia();
  const tabella = window.HirisRouter._hash_di_prima;

  for (const [prima, adesso] of Object.entries(tabella)) {
    window.location.hash = prima;
    window.HirisRouter.start();
    window.dispatchEvent(new window.Event('hashchange'));

    assert.equal(window.location.hash, adesso,
      `un segnalibro su ${prima} deve finire su ${adesso}, non restare dov'era`);
    assert.match(document.getElementById('route-outlet').textContent,
      new RegExp(SEGNAPOSTO[adesso]),
      `${prima} deve MONTARE la pagina di ${adesso}, non solo cambiare la barra`);
    assert.equal(document.getElementById('chrome-here').textContent,
      SEGNAPOSTO[adesso],
      `la briciola dopo ${prima} deve dire dove si è finiti`);
  }
});

test('il tasto «indietro» non resta in trappola: la correzione SOSTITUISCE la voce di cronologia', () => {
  const { window } = avvia();
  /* Assegnare `location.hash` invece di `history.replaceState` aggiungerebbe
     una voce: «indietro» tornerebbe su `#/albero`, che rimanda avanti, e
     l'utente non potrebbe più uscire. Si conta la lunghezza della
     cronologia intorno alla correzione: deve restare la stessa. */
  window.location.hash = '#/albero';
  const prima = window.history.length;
  window.HirisRouter.start();
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(window.location.hash, '#/tree');
  assert.equal(window.history.length, prima,
    'la correzione deve sostituire la voce di cronologia, non aggiungerne una');
});

test('un hash sconosciuto non passa dalla tabella: resta «Pagina non trovata»', () => {
  const { window, document } = avvia();
  window.location.hash = '#/inventato';
  window.HirisRouter.start();
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(window.location.hash, '#/inventato',
    'la tabella non deve toccare un hash che non le appartiene');
  assert.match(document.getElementById('route-outlet').textContent, /Pagina non trovata/);
});

/* ── La condizione d'uscita, eseguibile ─────────────────────────────────── */

test('ogni bersaglio della tabella è una route che main.js registra DAVVERO', () => {
  const { window } = avvia();
  const registrate = window.HirisRouter._internal_routes;
  const tabella = window.HirisRouter._hash_di_prima;

  for (const [prima, adesso] of Object.entries(tabella)) {
    const trovata = registrate.some((r) => r.pattern.test(adesso));
    assert.ok(trovata,
      `la tabella manda ${prima} su ${adesso}, che nessuna route registra: ` +
      'un segnalibro valido finirebbe su una pagina che non esiste più, in ' +
      'silenzio. Se la pagina è stata rinominata di nuovo, aggiorna il ' +
      'bersaglio; se è uscita, togli la riga.');
  }
});

test('nessuna sorgente della tabella è a sua volta una route viva', () => {
  const { window } = avvia();
  const registrate = window.HirisRouter._internal_routes;
  const tabella = window.HirisRouter._hash_di_prima;

  for (const prima of Object.keys(tabella)) {
    const viva = registrate.some((r) => r.pattern.test(prima));
    assert.ok(!viva,
      `${prima} è insieme una sorgente della tabella e una route viva: la ` +
      'tabella oscurerebbe una pagina vera. Togli la riga.');
  }
});

test('la tabella non è vuota -- e il giorno in cui lo sarà, questo file esce con lei', () => {
  const { window } = avvia();
  const tabella = window.HirisRouter._hash_di_prima;

  assert.ok(Object.keys(tabella).length > 0,
    'la tabella degli indirizzi di prima è vuota: il reindirizzamento non ' +
    'serve più a nessuno. Toglila da config/router.js e cancella QUESTO ' +
    'file insieme a lei -- è la condizione d\'uscita scritta accanto alla ' +
    'tabella, e questo rosso è il suo unico promemoria.');
});
