import { JSDOM } from 'jsdom';
import { readFileSync, cpSync, mkdtempSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const STATIC = join(ROOT, 'hiris', 'app', 'static');
// Esportato per il test di cablaggio di m8 (ri-review): il solo modo per
// provare che `staticSnapshotDir()` restituisca DAVVERO una copia isolata
// (mkdtempSync), non l'albero static/ vivo stesso, e' avere entrambi i
// percorsi da confrontare da fuori.
export const STATIC_VIVO = STATIC;

/* m5 (review finale): `loadScripts()` (e i due file di cablaggio di B8, che
 * leggono `chat/main.js` a parte) facevano `readFileSync` dei sorgenti di
 * PRODUZIONE dal filesystem, al momento della corsa, senza istantanea --
 * qualunque scrittura concorrente in `static/` (un editor aperto, un altro
 * agente, un `git checkout`) durante l'esecuzione della suite colora quella
 * corsa e non la successiva. `staticSnapshotDir()` copia l'intero albero UNA
 * SOLA volta per processo (`node --test` isola ogni file di test in un
 * processo separato, quindi la copia e' per-file, non condivisa fra file) in
 * una cartella temporanea, e ogni lettura successiva in questo processo passa
 * da li' -- congelata all'istante in cui il PRIMO test del file ha chiamato
 * `loadScripts()`, indipendente da qualunque scrittura sull'albero vero che
 * segua. */
// m1 (ri-review): ogni copia (sia il singleton di staticSnapshotDir() sia le
// copie ad-hoc dei test, es. static-snapshot.test.mjs) e' una cartella vera
// in %TEMP%/tmpdir() e nessuno la rimuoveva -- misurato: ~68 cartelle
// `hiris-static-snapshot-*` accumulate dopo poche corse, ~6 MB a corsa.
// Ogni chiamata la registra qui; l'exit handler sotto le rimuove tutte alla
// fine del processo (node --test isola i FILE in processi separati, quindi
// e' il punto giusto: non prima, o una loadScripts() successiva nello
// stesso file perderebbe la copia da sotto i piedi).
const _cartelleDaRimuovere = [];

// Funzione pura, esportata a parte cosi' la sua proprieta' di isolamento
// (una scrittura sulla SORGENTE dopo la copia non tocca la copia) e'
// verificabile da un test dedicato senza toccare l'albero vero del repo.
export function copiaIstantanea(sorgente) {
  const dest = mkdtempSync(join(tmpdir(), 'hiris-static-snapshot-'));
  cpSync(sorgente, dest, { recursive: true });
  _cartelleDaRimuovere.push(dest);
  return dest;
}

process.on('exit', () => {
  for (const dir of _cartelleDaRimuovere) {
    try { rmSync(dir, { recursive: true, force: true }); } catch (e) { /* pulizia a fine processo, best-effort */ }
  }
});

let _snapshotDir = null;

export function staticSnapshotDir() {
  if (_snapshotDir === null) {
    _snapshotDir = copiaIstantanea(STATIC);
  }
  return _snapshotDir;
}

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
 * cui gli array/oggetti creati dentro gli script non sono `instanceof`
 * l'Array del processo
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
 *
 * SP-4 Fase B Task 2: ogni modulo `config/*.js` di questo repo espone la
 * propria API con `window.Foo = ...` dentro un IIFE (mai `var Foo = ...` a
 * livello globale). In un vero browser è equivalente a un global bare
 * (`window === globalThis` lì), ma qui `window` è un oggetto bridged
 * DIVERSO da `globalThis` — quindi `window.Foo = ...` non creava
 * `globalThis.Foo`, e un secondo script che referenzia `Foo` bare (es. un
 * modulo di route che chiama `HirisState.set(...)`) falliva con
 * ReferenceError. Il proxy sotto
 * intercetta ogni assegnazione `window.X = ...` e la specchia anche su
 * `globalThis.X`, replicando la semantica reale del browser. Necessario da
 * quando i test hanno iniziato a caricare più moduli che si referenziano a
 * vicenda (prima, i test accedevano sempre via `window.HirisX` esplicito dal
 * lato test, non da altro codice IIFE caricato insieme).
 *
 * Isolamento fra test() nello stesso file: `node --test` isola i FILE di
 * test in processi separati, ma NON le singole `test()` dentro lo stesso
 * file — girano nello stesso processo/globalThis. Senza teardown, ogni
 * chiave che il proxy sotto specchia su `globalThis` (HirisState,
 * HirisChatbotEditor, HirisEntityPicker, ...) sopravviverebbe alla
 * chiamata di `loadScripts()` successiva: oggi innocuo (i test ricaricano
 * sempre la stessa lista di script, quindi il valore viene sovrascritto),
 * ma un futuro test che carica un SOTTOINSIEME diverso di script
 * troverebbe comunque il global lasciato da un test "fratello" — un
 * `typeof X === 'function'` potrebbe risultare vero per un global
 * ereditato, non prodotto dagli script appena caricati (falso positivo).
 * Rimedio a due livelli, pensato per essere difficile da usare male:
 * 1) ogni chiamata di `loadScripts()` traccia le chiavi che IL PROPRIO
 *    proxy specchia su `globalThis` e, PRIMA di iniziare, ripulisce quelle
 *    lasciate dall'istanza precedente (`previousMirroredKeys`) — pulizia
 *    automatica, non serve ricordarsene nel test;
 * 2) restituisce comunque un `dispose()` esplicito, per chi vuole liberare
 *    i global a metà test senza aspettare la prossima `loadScripts()`.
 */
let previousMirroredKeys = null;

function cleanupKeys(keys) {
  for (const key of keys) {
    try { delete globalThis[key]; } catch (e) { /* proprietà non configurabile del global host, ignora */ }
  }
}

export function loadScripts(paths, { html = '<!doctype html><body></body>' } = {}) {
  // Auto-teardown: rimuove i global lasciati dall'istanza precedente di
  // loadScripts() PRIMA di caricarne una nuova, cosi' un test non puo'
  // accidentalmente vedere un global di un test "fratello" nello stesso file.
  if (previousMirroredKeys) {
    cleanupKeys(previousMirroredKeys);
    previousMirroredKeys = null;
  }

  const dom = new JSDOM(html, { url: 'http://localhost/' });
  const rawWindow = dom.window;
  const mirroredKeys = new Set();

  const windowProxy = new Proxy(rawWindow, {
    set(target, prop, value) {
      target[prop] = value;
      if (typeof prop === 'string') {
        try { globalThis[prop] = value; mirroredKeys.add(prop); } catch (e) { /* proprietà read-only del global host, ignora */ }
      }
      return true;
    },
  });

  const define = (name, value) =>
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  define('window', windowProxy);
  define('document', rawWindow.document);
  define('navigator', rawWindow.navigator);
  define('Event', rawWindow.Event);
  define('localStorage', rawWindow.localStorage);
  // Task B8: build-check.js usa `sessionStorage` bare (stesso pattern di
  // `localStorage` sopra) per la guardia anti-anello dei ricaricamenti.
  define('sessionStorage', rawWindow.sessionStorage);
  // `HTMLElement` non è un global di Node — esiste solo su `window` in jsdom —
  // e va bridged sul globalThis dell'host esattamente come document/navigator/
  // Event sopra, per gli script che lo usano bare come farebbero nel browser.
  //
  // fetta E5 Task 5: qui stavano anche `customElements` e `CustomEvent`, per
  // l'unico Custom Element del progetto (`hiris-chat-card.js`), uscito col
  // prodotto. fetta E5 Task 6: i due file che usavano `HTMLElement` bare
  // (`config/drawer.js`, `config/popover.js`) sono usciti a loro volta --
  // oggi nessuno script di `static/` lo nomina (verificato col grep). Il
  // bridge resta perche' e' un global standard del browser che un qualunque
  // script caricato qui puo' legittimamente usare, non un'impalcatura per un
  // consumatore specifico: a differenza di `customElements`, non promette
  // niente su cosa esiste nel prodotto.
  define('HTMLElement', rawWindow.HTMLElement);
  // `fetch` è normalmente sovrascritto per-test da stubFetch(window, ...);
  // la getter/setter lo tiene agganciato dinamicamente a window.fetch così
  // gli script (che lo chiamano non qualificato, come farebbero nel browser)
  // vedono sempre lo stub corrente.
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    get() { return rawWindow.fetch ? rawWindow.fetch.bind(rawWindow) : undefined; },
    set(fn) { rawWindow.fetch = fn; },
  });

  for (const p of paths) {
    const code = readFileSync(join(staticSnapshotDir(), p), 'utf8');
    globalEval(code);
  }

  // `previousMirroredKeys` punta allo stesso Set restituito da `mirroredKeys`:
  // eventuali chiavi aggiunte DOPO il return (es. `stubFetch(window, ...)`
  // che fa `window.fetch = ...`) restano tracciate, perché il Set è lo
  // stesso oggetto, non una copia.
  previousMirroredKeys = mirroredKeys;

  const dispose = () => {
    cleanupKeys(mirroredKeys);
    mirroredKeys.clear();
    if (previousMirroredKeys === mirroredKeys) previousMirroredKeys = null;
  };

  return { dom, window: windowProxy, document: rawWindow.document, dispose };
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
