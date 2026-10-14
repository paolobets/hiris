/* Il vocabolario degli stati, chiesto al suo sorgente (`hiris/app/states.py`,
   Tappa 8, D4 e C-10) invece di ricopiarlo nelle prove: le pagine ricevono
   la frase di ogni stato dalla rotta (`stato_leggibile`), e i finti server
   delle prove la mettono come la mette il server vero.

   Regex, non un parser: lo stesso grado di sofisticazione delle letture di
   sorgenti Python gia' in uso (`helpers/costruzioni.mjs`). Se una
   lettura si rompe, `tupla` e `FRASI` lo dicono invece di tornare vuoti. */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const SORGENTE = readFileSync(new URL('../../../hiris/app/states.py', import.meta.url), 'utf8');

/* `NOME = "parola"`, al margine: le costanti del vocabolario. */
const PAROLE = {};
for (const m of SORGENTE.matchAll(/^([A-Z_]+) = "([^"]*)"$/gm)) PAROLE[m[1]] = m[2];
assert.ok(Object.keys(PAROLE).length >= 10,
  'states.py: troppe poche costanti lette -- il formato e\' cambiato?');

/* Una tupla di nomi di `states.py` (`SUSPENDED`, `PROMISE_STATES`...), o di
   un altro sorgente Python che la compone dalle stesse costanti, risolta
   nelle parole. */
export function tupla(nome, sorgente = SORGENTE) {
  const m = sorgente.match(new RegExp('^' + nome + ' = \\(([^)]*)\\)', 'm'));
  assert.ok(m, 'tupla non trovata: ' + nome);
  return m[1].split(',').map((s) => s.trim()).filter(Boolean).map((n) => {
    assert.ok(n in PAROLE, nome + ': «' + n + '» non e\' una costante di states.py');
    return PAROLE[n];
  });
}

/* `READABLE`: stato -> frase. */
const blocco = SORGENTE.match(/^READABLE = \{([\s\S]*?)^\}/m);
assert.ok(blocco, 'READABLE non trovata in states.py');
export const FRASI = {};
for (const m of blocco[1].matchAll(/^\s+([A-Z_]+): "([^"]*)",$/gm)) FRASI[PAROLE[m[1]]] = m[2];
assert.ok(Object.keys(FRASI).length >= 10, 'READABLE: troppe poche frasi lette');

/* Una riga come la manda il server: con la frase del suo stato. Uno stato
   che il vocabolario non conosce torna com'e', come `states.readable`. */
export function conFrase(riga) {
  if (!riga || typeof riga.stato !== 'string' || 'stato_leggibile' in riga) return riga;
  return { ...riga, stato_leggibile: FRASI[riga.stato] ?? riga.stato };
}

/* La frase come la pagina la mette in un'etichetta: prima lettera maiuscola. */
export function etichetta(stato) {
  const frase = FRASI[stato];
  assert.ok(frase, 'nessuna frase per «' + stato + '»');
  return frase.charAt(0).toUpperCase() + frase.slice(1);
}

/* Cosa vuol dire lo stato di una promessa, come lo calcola
   `keeper/promise.py::serializza` (C-12): `sospesa` (`states.SUSPENDED`) ed
   `esito` (`promise.STATES_ESITO`), letti dai sorgenti. */
const PROMESSA = readFileSync(
  new URL('../../../hiris/app/keeper/promise.py', import.meta.url), 'utf8');
const SOSPESI = tupla('SUSPENDED');
const ESITI = tupla('STATES_ESITO', PROMESSA);

/* `disdicibile` (C-10, 14/10/2026): la regola di `AgendaStore.cancel`, cioe'
   lo stato `CANCELLABLE` di promise.py, che nomina una costante di
   states.py (`CANCELLABLE = PENDING`). */
const disdicibile = PROMESSA.match(/^CANCELLABLE = ([A-Z_]+)$/m);
assert.ok(disdicibile && disdicibile[1] in PAROLE, 'promise.py: CANCELLABLE non si legge');
const DISDICIBILE = PAROLE[disdicibile[1]];

export function conLetturaPromessa(riga) {
  const r = conFrase(riga);
  if (!r || typeof r.stato !== 'string' || 'sospesa' in r) return r;
  return resaPromessa({ ...r, sospesa: SOSPESI.includes(r.stato), esito: ESITI.includes(r.stato),
    disdicibile: r.stato === DISDICIBILE });
}

/* Gli istanti di una promessa come li manda la resa
   (`hiris/app/home_space/render.py::render_promise`, C-32): il nome in
   `_ts` dell'archivio diventa quello di `_PROMISE_INSTANTS`, e l'epoch un
   ISO con l'offset. Le prove scrivono i record in epoch, come l'archivio. */
const RESA = readFileSync(
  new URL('../../../hiris/app/home_space/render.py', import.meta.url), 'utf8');
const bloccoIstanti = RESA.match(/^_PROMISE_INSTANTS = \{([\s\S]*?)\}/m);
assert.ok(bloccoIstanti, 'render.py: _PROMISE_INSTANTS non si legge');
const ISTANTI = {};
for (const m of bloccoIstanti[1].matchAll(/"(\w+)": "(\w+)"/g)) ISTANTI[m[1]] = m[2];
assert.ok(Object.keys(ISTANTI).length >= 5, '_PROMISE_INSTANTS: troppo pochi istanti letti');

function resaPromessa(riga) {
  const out = {};
  for (const [chiave, valore] of Object.entries(riga)) {
    if (!(chiave in ISTANTI)) { out[chiave] = valore; continue; }
    out[ISTANTI[chiave]] = valore == null ? valore
      : new Date(valore * 1000).toISOString().replace(/\.\d{3}Z$/, '+00:00');
  }
  return out;
}
