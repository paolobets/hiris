/* I LEGAMI del JavaScript, non i nomi: cio' che un tokenizzatore non puo' dare.
 *
 * **Perche' serve un parser vero, misurato.** In `hiris/app/static/` ci sono
 * 1.542 dichiarazioni che portano 704 nomi distinti: 202 nomi sono dichiarati
 * piu' di una volta, e le dichiarazioni coinvolte sono 1.040 su 1.542 (67%).
 * `corpo` e' dichiarato 34 volte in 7 file, `testo` 25 volte in 10. Uno
 * strumento a token le tratta come una cosa sola e le rinomina insieme: e' la
 * stessa classe che il 1o settembre ha prodotto un guasto vivo in `server.py`
 * (`richiesta -> request` dentro `_security_headers(request, handler)`),
 * moltiplicata per venti.
 *
 * Questo file fa una cosa sola: legge i sorgenti con `acorn`, ricostruisce gli
 * AMBITI, e scrive un JSON in cui ogni LEGAME porta la sua dichiarazione e
 * tutti i suoi riferimenti. Non conosce il glossario e non propone niente --
 * quello lo fa `rinomina_js.py`, che il glossario ce l'ha gia'. Due mestieri,
 * due file: la stessa disciplina di `_comune.py`.
 *
 * Uso:  node scripts/legami_js.mjs > legami.json
 */
import { parse } from 'acorn';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const STATIC = join(ROOT, 'hiris', 'app', 'static');

function tuttiIFile(base) {
  const fuori = [];
  for (const voce of readdirSync(base)) {
    const p = join(base, voce);
    if (statSync(p).isDirectory()) fuori.push(...tuttiIFile(p));
    else if (voce.endsWith('.js')) fuori.push(p);
  }
  return fuori.sort();
}

/* Un ambito. `funzione` distingue quelli che catturano `var` da quelli che
 * catturano solo `let`/`const`: senza la distinzione un `var` dentro un `for`
 * finirebbe legato al blocco, e due `var i` in due cicli della stessa
 * funzione sembrerebbero due legami invece di uno. */
let prossimoId = 0;
function nuovoAmbito(padre, funzione, nodo) {
  return {
    id: prossimoId++, padre, funzione,
    tipo: nodo ? nodo.type : 'Program',
    inizio: nodo ? nodo.start : 0,
    legami: new Map(),
  };
}

function ambitoDiFunzione(a) {
  while (a && !a.funzione) a = a.padre;
  return a;
}

function dichiara(ambito, nome, specie, nodo) {
  const dove = (specie === 'var' || specie === 'function' || specie === 'param')
    ? ambitoDiFunzione(ambito) : ambito;
  let l = dove.legami.get(nome);
  if (!l) { l = { nome, specie, ambito: dove.id, dich: [], rif: [] }; dove.legami.set(nome, l); }
  l.dich.push(nodo.start);
  return l;
}

function risolvi(ambito, nome) {
  for (let a = ambito; a; a = a.padre) {
    const l = a.legami.get(nome);
    if (l) return l;
  }
  return null;
}

/* I nomi introdotti da uno schema di destrutturazione o da un parametro. */
function nomiDelloSchema(nodo, fuori) {
  if (!nodo) return fuori;
  switch (nodo.type) {
    case 'Identifier': fuori.push(nodo); break;
    case 'ObjectPattern': nodo.properties.forEach((p) =>
      nomiDelloSchema(p.type === 'RestElement' ? p.argument : p.value, fuori)); break;
    case 'ArrayPattern': nodo.elements.forEach((e) => nomiDelloSchema(e, fuori)); break;
    case 'AssignmentPattern': nomiDelloSchema(nodo.left, fuori); break;
    case 'RestElement': nomiDelloSchema(nodo.argument, fuori); break;
    default: break;
  }
  return fuori;
}

const E_FUNZIONE = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);

function analizza(sorgente) {
  const albero = parse(sorgente, { ecmaVersion: 2021, sourceType: 'script', locations: true });
  const globale = nuovoAmbito(null, true, null);
  const tutti = [globale];
  const liberi = [];         // riferimenti che nessun ambito risolve
  const proprieta = [];      // accessi per punto: nome, lato, riga
  const scritture = new Set();   // posizioni di `x.nome = ...`
  const verita = new Set();      // posizioni lette in posizione di verita'
  /* La verita' si PROPAGA. `if (!a || b.c)` mette `b.c` in posizione di
   * verita' tanto quanto `a`: il test dell'`if` e' l'intera espressione, e gli
   * operandi di `||` e `&&` la ereditano. Una prima stesura marcava solo
   * l'operando sinistro e perdeva `scadenza` -- uno dei quattro casi ciechi
   * misurati. Un predicato che manca un caso che gia' conosciamo non e' un
   * predicato, e' una speranza: si propaga. */
  function veritaDi(n) {
    if (!n) return;
    if (n.type === 'MemberExpression' && !n.computed && n.property.type === 'Identifier') {
      verita.add(n.property.start);
      return;
    }
    if (n.type === 'LogicalExpression') { veritaDi(n.left); veritaDi(n.right); return; }
    if (n.type === 'UnaryExpression' && n.operator === '!') { veritaDi(n.argument); return; }
    if (n.type === 'ParenthesizedExpression') { veritaDi(n.expression); return; }
    if (n.type === 'ConditionalExpression') { veritaDi(n.consequent); veritaDi(n.alternate); }
  }

  /* Primo giro: le dichiarazioni. Si fa PRIMA dei riferimenti perche' in JS
   * `var` e `function` sono issate: una chiamata che precede la `function`
   * nel testo e' legittima, e un solo giro la direbbe libera. */
  const pila = [];
  function visita(nodo, ambito, primo) {
    if (!nodo || typeof nodo.type !== 'string') return;
    let qui = ambito;
    if (E_FUNZIONE.has(nodo.type)) {
      if (primo && nodo.type === 'FunctionDeclaration' && nodo.id) {
        dichiara(ambito, nodo.id.name, 'function', nodo.id);
      }
      qui = nuovoAmbito(ambito, true, nodo);
      tutti.push(qui);
      nodo.__ambito = qui;
      if (primo) {
        if (nodo.type === 'FunctionExpression' && nodo.id) dichiara(qui, nodo.id.name, 'function', nodo.id);
        for (const p of nodo.params) for (const n of nomiDelloSchema(p, [])) dichiara(qui, n.name, 'param', n);
      }
    } else if (nodo.type === 'BlockStatement' || nodo.type === 'ForStatement'
               || nodo.type === 'ForInStatement' || nodo.type === 'ForOfStatement') {
      if (!(ambito.inizio === nodo.start)) {
        qui = nodo.__ambito || nuovoAmbito(ambito, false, nodo);
        if (!nodo.__ambito) { tutti.push(qui); nodo.__ambito = qui; }
      }
    } else if (nodo.type === 'CatchClause' && nodo.param) {
      qui = nodo.__ambito || nuovoAmbito(ambito, false, nodo);
      if (!nodo.__ambito) { tutti.push(qui); nodo.__ambito = qui; }
      if (primo) for (const n of nomiDelloSchema(nodo.param, [])) dichiara(qui, n.name, 'catch', n);
    }
    if (primo && nodo.type === 'VariableDeclaration') {
      for (const d of nodo.declarations) {
        for (const n of nomiDelloSchema(d.id, [])) dichiara(qui, n.name, nodo.kind, n);
      }
    }
    if (primo && nodo.type === 'ClassDeclaration' && nodo.id) dichiara(qui, nodo.id.name, 'class', nodo.id);

    if (!primo) {
      /* Secondo giro: i riferimenti. Si salta cio' che NON e' un nome:
       * la chiave di un oggetto letterale, il nome dopo un punto, l'etichetta. */
      if (nodo.type === 'MemberExpression' && !nodo.computed && nodo.property.type === 'Identifier') {
        nodo.property.__proprieta = true;
        proprieta.push({ nome: nodo.property.name, lato: 'lettura',
                         riga: nodo.property.loc.start.line, start: nodo.property.start });
      }
      if (nodo.type === 'Property' && !nodo.computed && nodo.key.type === 'Identifier') {
        nodo.key.__proprieta = true;
        proprieta.push({ nome: nodo.key.name, lato: 'chiave',
                         riga: nodo.key.loc.start.line, start: nodo.key.start });
      }
      /* la SCRITTURA per attributo: `x.nome = ...`. Va distinta dalla lettura
       * perche' e' un lato-definizione, ed e' quello che una rinomina di un
       * lato solo lascia indietro. */
      if (nodo.type === 'AssignmentExpression' && nodo.left.type === 'MemberExpression'
          && !nodo.left.computed && nodo.left.property.type === 'Identifier') {
        scritture.add(nodo.left.property.start);
      }
      /* posizione di VERITA': `!x`, `x || y`, `x && y`, `x ? a : b`, `if (x)`.
       * E' la forma in cui una lettura orfana restituisce `undefined` e
       * `undefined` diventa `false` senza che niente lanci -- i 4 casi ciechi
       * su 41 mutazioni hanno tutti questa forma, e nessun altro ce l'ha. */
      if (nodo.type === 'UnaryExpression' && nodo.operator === '!') veritaDi(nodo.argument);
      if (nodo.type === 'LogicalExpression') { veritaDi(nodo.left); veritaDi(nodo.right); }
      if (nodo.type === 'ConditionalExpression') veritaDi(nodo.test);
      if (nodo.type === 'IfStatement' || nodo.type === 'WhileStatement'
          || nodo.type === 'DoWhileStatement') veritaDi(nodo.test);
      if (nodo.type === 'ForStatement' && nodo.test) veritaDi(nodo.test);
      if (nodo.type === 'Identifier' && !nodo.__proprieta && !nodo.__dichiarazione) {
        const l = risolvi(qui, nodo.name);
        if (l) l.rif.push(nodo.start);
        else liberi.push({ nome: nodo.name, riga: nodo.loc.start.line });
      }
    }
    for (const k of Object.keys(nodo)) {
      if (k === 'type' || k === 'start' || k === 'end' || k === 'loc' || k.startsWith('__')) continue;
      const v = nodo[k];
      if (Array.isArray(v)) v.forEach((x) => visita(x, qui, primo));
      else if (v && typeof v.type === 'string') visita(v, qui, primo);
    }
  }

  visita(albero, globale, true);
  /* marca le posizioni di dichiarazione, cosi' il secondo giro non le conta
   * come riferimenti */
  const posizioniDich = new Set();
  for (const a of tutti) for (const l of a.legami.values()) for (const p of l.dich) posizioniDich.add(p);
  function marca(nodo) {
    if (!nodo || typeof nodo.type !== 'string') return;
    if (nodo.type === 'Identifier' && posizioniDich.has(nodo.start)) nodo.__dichiarazione = true;
    for (const k of Object.keys(nodo)) {
      if (k === 'type' || k === 'start' || k === 'end' || k === 'loc' || k.startsWith('__')) continue;
      const v = nodo[k];
      if (Array.isArray(v)) v.forEach(marca);
      else if (v && typeof v.type === 'string') marca(v);
    }
  }
  marca(albero);
  visita(albero, globale, false);

  const legami = [];
  for (const a of tutti) {
    for (const l of a.legami.values()) {
      legami.push({ nome: l.nome, specie: l.specie, ambito: l.ambito,
                    dich: l.dich, rif: l.rif, globale: l.ambito === globale.id });
    }
  }
  for (const p of proprieta) {
    if (p.lato === 'lettura' && scritture.has(p.start)) p.lato = 'scrittura';
    p.verita = verita.has(p.start);
    delete p.start;
  }
  return { legami, liberi, proprieta, ambiti: tutti.length };
}

const fuori = {};
for (const f of tuttiIFile(STATIC)) {
  const rel = relative(STATIC, f).split(sep).join('/');
  const sorgente = readFileSync(f, 'utf8');
  prossimoId = 0;
  try {
    const esito = analizza(sorgente);
    /* **La misura del testo che ho letto, perche' chi applica possa
     * verificare di leggere lo STESSO testo.** Gli offset qui sotto sono
     * indici dentro questa stringa: se chi li usa apre il file in un modo che
     * la cambia -- la lettura universale di Python normalizza i `
` e
     * accorcia di una posizione per riga -- ogni offset scivola, e senza
     * questa misura il primo segnale arriva solo al momento di scrivere.
     * Successo davvero: all'offset 10666 di `osservatore-route.js` c'era
     * `' num'` invece di `'riga'`. `unita` conta le unita' UTF-16 (la base
     * degli offset di acorn), `punti` i punti di codice (la base di Python):
     * se differiscono, il file porta un carattere fuori dal piano base e gli
     * offset non si possono usare da Python senza conversione. */
    esito.misura = { unita: sorgente.length, punti: [...sorgente].length };
    fuori[rel] = esito;
  } catch (e) {
    fuori[rel] = { errore: String(e && e.message) };
  }
}
process.stdout.write(JSON.stringify(fuori));
