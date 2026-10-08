/* `static/common.js`: le utilita' del frontend scritte una volta (registro
   C-20, C-22, C-19, C-16), e la prova che le copie per file non tornano.

   Il cancello CHIEDE i nomi a `common.js` (CLAUDE.md, I-0): li ricava eseguendo
   il file in un contesto vuoto e guardando quali funzioni vi lascia. Nessun
   elenco scritto qui. Poi cerca, in ogni altro `.js` di `static/`, una
   funzione con uno di quei nomi -- dichiarata, o assegnata a una variabile.
   Una variabile locale che si chiama `el` ma porta un elemento
   (`var el = document.getElementById(...)`) non e' una copia, e non conta.

   Questo file prende il posto delle copie che le prove fissavano una per
   file (T-10): `el`, `api` e il resto si provano qui, una volta. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import vm from 'node:vm';
import * as acorn from 'acorn';
import * as walk from 'acorn-walk';
import { loadScripts, STATIC_VIVO } from './helpers/dom.mjs';

const COMMON = 'common.js';

/* I globali che un sorgente lascia dietro di se'. `vm` esegue lo script come
   farebbe un `<script>` classico: le dichiarazioni di primo livello diventano
   proprieta' del contesto. Al caricamento common.js dichiara soltanto, quindi
   un contesto vuoto basta. */
function exportedFunctions(source) {
  const ctx = vm.createContext({});
  vm.runInContext(source, ctx);
  return new Set(Object.keys(ctx).filter((k) => typeof ctx[k] === 'function'));
}

function jsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (name.endsWith('.js')) out.push(p);
  }
  return out;
}

/* Le funzioni che un sorgente definisce con uno dei nomi dati. */
function definitionsOf(source, names) {
  const found = [];
  const ast = acorn.parse(source, { ecmaVersion: 'latest', locations: true });
  walk.full(ast, (node) => {
    if (node.type === 'FunctionDeclaration' && node.id && names.has(node.id.name)) {
      found.push(node.id.name + ':' + node.loc.start.line);
    }
    if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier'
        && names.has(node.id.name) && node.init
        && /^(FunctionExpression|ArrowFunctionExpression)$/.test(node.init.type)) {
      found.push(node.id.name + ':' + node.loc.start.line);
    }
  });
  return found;
}

/* La lista di AMMISSIONE (CLAUDE.md, I-0): non ricopia niente, enuncia il
   cancello. Una voce nuova e' vietata finche' qualcuno non la scrive qui con
   la ragione. Chiave: «file nome». */
const AMMESSI = {
  'pending-badge.js configures':
    'e\' la fonte a cui `configures()` di common.js delega '
    + '(`HirisPendingBadge.configures()`), non una sua copia: common.js aggiunge '
    + 'la chiusura nel dubbio quando il pallino non c\'e\'',
};

/* Il cancello: ogni file di `static/` (tranne common.js) che definisce una
   funzione col nome di una esportata da common.js. */
function copiesOutside(commonSource, files) {
  const names = exportedFunctions(commonSource);
  const copies = [];
  for (const [rel, src] of files) {
    for (const d of definitionsOf(src, names)) {
      if (Object.hasOwn(AMMESSI, rel + ' ' + d.split(':')[0])) continue;
      copies.push(rel + ' ' + d);
    }
  }
  return { names, copies };
}

function staticFiles() {
  return jsFiles(STATIC_VIVO)
    .map((p) => [relative(STATIC_VIVO, p).split('\\').join('/'), readFileSync(p, 'utf8')])
    .filter(([rel]) => rel !== COMMON);
}

const commonSource = () => readFileSync(join(STATIC_VIVO, COMMON), 'utf8');

test('nessun file di static/ ridefinisce una funzione di common.js', () => {
  const { copies } = copiesOutside(commonSource(), staticFiles());
  assert.deepEqual(copies, [], 'copie fuori da common.js:\n' + copies.join('\n'));
});

test('la derivazione non e\' vuota: il cancello guarda davvero qualcosa', () => {
  const { names } = copiesOutside(commonSource(), staticFiles());
  // Nessun elenco ricopiato: basta che il cancello abbia nomi da cercare, e
  // che siano funzioni vere del file.
  assert.ok(names.size > 0, 'common.js non esporta nessuna funzione: il cancello e\' cieco');
  assert.ok(staticFiles().length > 0, 'nessun file da guardare in static/');
});

test('una funzione aggiunta a common.js entra nel cancello senza toccare la prova', () => {
  const nuova = 'zzFunzioneDiProva';
  const mutato = commonSource() + `\nfunction ${nuova}() { return 1; }\n`;
  const copia = ['config/finta.js', `(function(){ function ${nuova}() { return 2; } })();`];
  const { names, copies } = copiesOutside(mutato, [...staticFiles(), copia]);
  assert.ok(names.has(nuova));
  assert.deepEqual(copies.filter((c) => c.includes(nuova)), ['config/finta.js ' + nuova + ':1']);
});

test('una variabile locale che porta un elemento non e\' una copia', () => {
  const src = '(function(){ var el = document.getElementById("x"); return el; })();';
  const { copies } = copiesOutside(commonSource(), [['config/x.js', src]]);
  assert.deepEqual(copies, []);
});

/* ------------------------------------------------- le utilita', una volta */

const HTML = '<!DOCTYPE html><html><body><div id="x"></div></body></html>';

test('el: classe e testo, il testo sempre come testo', () => {
  loadScripts([COMMON], { html: HTML });
  const n = el('p', 'a b', '<b>no</b>');
  assert.equal(n.tagName, 'P');
  assert.equal(n.className, 'a b');
  assert.equal(n.textContent, '<b>no</b>');
  assert.equal(n.children.length, 0);
  assert.equal(el('span', null, 0).textContent, '0', 'lo zero e\' un testo, non un vuoto');
  assert.equal(el('span').textContent, '');
});

test('clearEl svuota e restituisce il nodo; byId lo trova', () => {
  loadScripts([COMMON], { html: HTML });
  const x = byId('x');
  x.appendChild(el('i')); x.appendChild(el('i'));
  assert.equal(clearEl(x), x);
  assert.equal(x.childNodes.length, 0);
  assert.equal(clearEl(null), null);
});

test('pad2', () => {
  loadScripts([COMMON], { html: HTML });
  assert.equal(pad2(3), '03');
  assert.equal(pad2(12), '12');
});

test('stateLabel: la frase della rotta; senza, la parola grezza senza trattino basso', () => {
  /* ux-ui-specialist, 08/10/2026: il ripiego `x.stato_leggibile || x.stato`
     mostrava «In_corso». Mutazione ESEGUITA: tolto il `replace` -- rossa. */
  loadScripts([COMMON], { html: HTML });
  assert.equal(stateLabel('In attesa del momento'), 'In attesa del momento');
  assert.equal(stateLabel('in_corso'), 'In corso');
  assert.equal(stateBadge('fallita'), 'badge-err');
  assert.equal(stateBadge('una_parola_nuova'), 'badge-off');
});

test('api: Content-Type JSON e l\'intestazione anti-CSRF, quelle di chi chiama vincono', async () => {
  loadScripts([COMMON], { html: HTML });
  const calls = [];
  globalThis.fetch = (url, opts) => { calls.push({ url, opts }); return Promise.resolve({ ok: true }); };
  await api('api/x', { method: 'POST', headers: { 'Content-Type': 'text/plain' } });
  assert.equal(calls[0].url, 'api/x');
  assert.equal(calls[0].opts.method, 'POST');
  assert.equal(calls[0].opts.headers['X-Requested-With'], 'fetch');
  assert.equal(calls[0].opts.headers['Content-Type'], 'text/plain');
  await api('api/y');
  assert.equal(calls[1].opts.headers['Content-Type'], 'application/json');
});

test('renderError: la frase di chi chiama e un «Riprova» che rilancia', () => {
  loadScripts([COMMON], { html: HTML });
  const x = byId('x');
  x.appendChild(el('p', null, 'Caricamento…'));
  let rilanci = 0;
  renderError(x, 'Non è stato possibile leggere.', () => { rilanci += 1; });
  assert.equal(x.children.length, 2);
  assert.equal(x.children[0].className, 'proposals-error');
  assert.equal(x.children[0].textContent, 'Non è stato possibile leggere.');
  assert.equal(x.children[1].textContent, 'Riprova');
  assert.equal(x.children[1].type, 'button');
  x.children[1].click();
  assert.equal(rilanci, 1);
});

test('nomiRegistriInItaliano: il nome e l\'ambito caduto', () => {
  loadScripts([COMMON], { html: HTML });
  assert.deepEqual(nomiRegistriInItaliano(['aree', 'categorie:script', 'ignoto']),
    ['Aree', 'Categorie (ambito «script»)', 'ignoto']);
});

/* ------------------------------------------------------------- il tema */

function stubStorage(initial) {
  const mem = Object.assign({}, initial);
  return {
    getItem: (k) => (k in mem ? mem[k] : null),
    setItem: (k, v) => { mem[k] = String(v); },
    mem,
  };
}

function withStorage(storage) {
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true });
}

test('il tema: la scelta salvata vince sul server, e non si chiede la rete', async () => {
  loadScripts([COMMON], { html: HTML });
  withStorage(stubStorage({ 'hiris-theme': 'dark' }));
  let chiamate = 0;
  globalThis.fetch = () => { chiamate += 1; return Promise.resolve({ json: () => ({ theme: 'light' }) }); };
  globalThis.paintSavedTheme();
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  await applyTheme();
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  assert.equal(chiamate, 0);
});

test('il tema: senza scelta salvata vale quello del server, e non si salva', async () => {
  loadScripts([COMMON], { html: HTML });
  const storage = stubStorage({});
  withStorage(storage);
  globalThis.fetch = () => Promise.resolve({ json: () => ({ theme: 'dark' }) });
  globalThis.paintSavedTheme();
  assert.equal(document.documentElement.getAttribute('data-theme'), null);
  await applyTheme();
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  assert.deepEqual(storage.mem, {}, 'il tema del server non diventa una scelta di chi guarda');
});

test('il tema: il clic passa all\'opposto e lo ricorda', () => {
  loadScripts([COMMON], { html: HTML });
  const storage = stubStorage({});
  withStorage(storage);
  document.documentElement.setAttribute('data-theme', 'dark');
  assert.equal(currentTheme(), 'dark');
  assert.equal(toggleTheme(), 'light');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(storage.mem['hiris-theme'], 'light');
});

/* Il bootstrap in linea delle due pagine (l'unico `<script>` senza `src`)
   chiama solo funzioni di common.js, e common.js gli e' caricato prima. Le
   pagine si leggono dalla cartella, i nomi da common.js: niente si ricopia.
   E' l'unica sponda che `scripts/sponde_js.py` non vede, perche' guarda i
   file `.js` e non lo script in linea. */
function pages() {
  return readdirSync(STATIC_VIVO).filter((n) => n.endsWith('.html')).sort()
    .map((n) => [n, readFileSync(join(STATIC_VIVO, n), 'utf8')]);
}

test('il bootstrap del tema in linea chiama common.js, caricato prima di lui', () => {
  const names = exportedFunctions(commonSource());
  const viste = pages();
  assert.ok(viste.length >= 2, 'le due pagine non si trovano piu\' nella cartella');
  for (const [nome, html] of viste) {
    const tag = '<script src="static/' + COMMON + '"></script>';
    const posCommon = html.indexOf(tag);
    assert.ok(posCommon >= 0, nome + ': common.js non e\' caricato');
    const primoScript = html.search(/<script[\s>]/);
    assert.equal(primoScript, posCommon, nome + ': common.js deve essere il primo script');
    const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    assert.equal(inline.length, 1, nome + ': un solo script in linea, il bootstrap del tema');
    const corpo = inline[0][1];
    assert.ok(inline[0].index > posCommon, nome + ': il bootstrap gira prima di common.js');
    const chiamate = [...corpo.matchAll(/([A-Za-z_$][\w$]*)\s*\(/g)].map((m) => m[1]);
    assert.ok(chiamate.length > 0, nome + ': il bootstrap non chiama niente');
    for (const c of chiamate) assert.ok(names.has(c), nome + ': «' + c + '» non e\' di common.js');
  }
});

test('ogni ammissione nomina una definizione che c\'e\' ancora', () => {
  const files = new Map(staticFiles());
  for (const chiave of Object.keys(AMMESSI)) {
    const [rel, nome] = chiave.split(' ');
    assert.ok(files.has(rel), chiave + ': il file non c\'e\' piu\'');
    assert.ok(definitionsOf(files.get(rel), new Set([nome])).length > 0,
      chiave + ': la definizione non c\'e\' piu\', l\'ammissione va tolta');
  }
});
