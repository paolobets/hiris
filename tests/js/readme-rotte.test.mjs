import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts } from './helpers/dom.mjs';
import { fintoFetch, maiRisposta } from './helpers/fetch.mjs';

/* Le rotte del pannello che il README elenca sono quelle che `main.js`
   registra: l'elenco si CHIEDE al router vero, non si ricopia.

   Perché esiste: il 07/09/2026 il README elencava nove rotte e sei avevano
   il nome di prima della rinomina (`#/albero`, `#/memoria`...). La tabella
   era stata corretta a mano, ma niente impediva che invecchiasse di nuovo:
   una pagina nuova o rinominata e il README tornava a mentire in silenzio.
   Qui si confrontano nelle due direzioni la tabella «Interface» del README e
   le route che il router registra all'avvio.

   Fino alla Chiusura dello sprint (F9, 14/10/2026) lo facevano due prove in
   `watcher-route.test.mjs`, che leggevano il TESTO di `main.js` con una
   regex: una contava le route contro la frase «with ten live routes», l'altra
   confrontava i nomi. La regex si era gia' rotta una volta (18/09/2026,
   quando `#/watcher` ha preso le schede facoltative) e gridava contro una
   route registrata eccome. Qui le route si chiedono al router avviato
   (`_internal_routes`), che sa riconoscere da se' anche le schede; e il
   README non dichiara piu' un numero, che e' un fatto che invecchia da solo.

   La riga di una route comincia con `| \`#/...\` |`: l'ancora a inizio riga
   la distingue da una rotta soltanto MENZIONATA nella descrizione di
   un'altra («chosen per provider in `#/models`», nella riga di
   `#/settings`). */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <div id="side-nav"></div>
  <div id="page-chrome"></div>
  <template id="tpl-side-nav"></template>
  <template id="tpl-page-chrome"></template>
</body>`;

/* Le rotte della tabella sotto «## Interface»: la prima cella di ogni riga,
   un hash fra apici inversi. */
function rotteDelReadme() {
  const testo = readFileSync(join(ROOT, 'README.md'), 'utf8');
  const inizio = testo.indexOf('## Interface');
  const fine = testo.indexOf('\n## ', inizio + 1);
  const sezione = testo.slice(inizio, fine);
  return [...sezione.matchAll(/^\| `(#\/[^`]*)` \|/gm)].map((m) => m[1]);
}

function registrate() {
  const { window } = loadScripts(
    ['common.js', 'config/state.js', 'config/router.js', 'config/main.js'], { html: HTML });
  fintoFetch(window, { 'api/config': maiRisposta, 'api/health': maiRisposta });
  return window.HirisRouter._internal_routes.map((r) => r.pattern);
}

test('la lettura non si è rotta: il README e il router portano rotte', () => {
  /* Un insieme vuoto farebbe passare le due prove sotto guardando niente. */
  assert.ok(rotteDelReadme().length > 1, 'la tabella delle rotte del README è stata letta vuota');
  assert.ok(registrate().length > 1, 'il router non ha registrato nessuna rotta');
});

test('ogni rotta del README è una route che il router registra', () => {
  const route = registrate();
  for (const rotta of rotteDelReadme()) {
    assert.ok(route.some((p) => p.test(rotta)),
      `il README elenca ${rotta}, che il router non registra: la pagina è stata ` +
      'rinominata o è uscita, e il README non lo sa');
  }
});

test('ogni route che il router registra ha la sua riga nel README', () => {
  const readme = rotteDelReadme();
  for (const pattern of registrate()) {
    assert.ok(readme.some((rotta) => pattern.test(rotta)),
      `il router registra ${pattern}, e la tabella «Interface» del README non ` +
      'ha una riga per quella pagina');
  }
});
