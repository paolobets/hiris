/* Il vocabolario degli stati, chiesto al suo sorgente (`hiris/app/states.py`,
   Tappa 8, D4 e C-10) invece di ricopiarlo nelle prove: le pagine ricevono
   la frase di ogni stato dalla rotta (`stato_leggibile`), e i finti server
   delle prove la mettono come la mette il server vero.

   Regex, non un parser: lo stesso grado di sofisticazione delle letture di
   sorgenti Python gia' in uso (`agenda-route-vocabulary.test.mjs`). Se una
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
