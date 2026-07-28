import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const STATIC = join(ROOT, 'hiris', 'app', 'static');

// Indirect eval: forces evaluation against the *global* scope of whatever
// realm is calling it, instead of the caller's local lexical scope (the
// classic `(0, eval)(code)` trick) — same as loading a plain <script>.
const globalEval = (0, eval);

/**
 * Crea un DOM e valuta gli script indicati (path relativi a static/).
 *
 * NB: la ricetta "libro di testo" per jsdom (`runScripts: 'outside-only'`
 * + `window.eval(code)`) è stata provata per prima e NON funziona per
 * questi test: `window` in quella modalità vive nel proprio vm-realm, per
 * cui gli array/oggetti creati dentro gli script (es. `selection.slice()`
 * dentro entity-picker.js) non sono `instanceof` l'Array del processo
 * Node.js che esegue i test — ogni `assert.deepEqual(picker.getValue(),
 * [...])` falliva con "same structure but are not reference-equal" anche
 * quando il comportamento era corretto.
 *
 * Soluzione: bridge del `window` di jsdom sul `globalThis` di Node (esattamente
 * come farebbe un file caricato con <script> in una pagina reale, dove
 * `window` E il global) ed esecuzione degli IIFE con un eval indiretto nel
 * realm host. Il DOM (elementi, Event, …) resta nel realm di jsdom — coerente,
 * perché i test lo attraversano sempre tramite lo stesso `document` — mentre
 * i dati semplici (array, stringhe) restano nel realm host, combaciando con
 * i literal scritti nei test.
 */
export function loadScripts(paths, { html = '<!doctype html><body></body>' } = {}) {
  const dom = new JSDOM(html, { url: 'http://localhost/' });
  const { window } = dom;

  const define = (name, value) =>
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  define('window', window);
  define('document', window.document);
  define('navigator', window.navigator);
  define('Event', window.Event);
  define('localStorage', window.localStorage);
  // `fetch` è normalmente sovrascritto per-test da stubFetch(window, ...);
  // la getter/setter lo tiene agganciato dinamicamente a window.fetch così
  // gli script (che lo chiamano non qualificato, come farebbero nel browser)
  // vedono sempre lo stub corrente.
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    get() { return window.fetch ? window.fetch.bind(window) : undefined; },
    set(fn) { window.fetch = fn; },
  });

  for (const p of paths) {
    const code = readFileSync(join(STATIC, p), 'utf8');
    globalEval(code);
  }
  return { dom, window, document: window.document };
}

/** fetch finto: mappa url-substring -> payload JSON. */
export function stubFetch(window, routes) {
  const calls = [];
  window.fetch = (url, opts) => {
    calls.push({ url: String(url), opts });
    const hit = Object.entries(routes).find(([frag]) => String(url).includes(frag));
    const body = hit ? hit[1] : {};
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  };
  return calls;
}

export const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
