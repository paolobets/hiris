/* Come si legge l'esito di un tentativo dell'osservatore, chiesto ai suoi
   sorgenti invece di ricopiarlo nelle prove (G-25): gli esiti vivono in
   `hiris/app/mind/store.py` (`ATTEMPT_*`), la parola e il segno in
   `hiris/app/api/handlers_mind.py` (`_ATTEMPT_WORDS`). Il finto server mette i
   campi come li mette `attempt_out`. */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const STORE = readFileSync(
  new URL('../../../hiris/app/mind/store.py', import.meta.url), 'utf8');
const GESTORE = readFileSync(
  new URL('../../../hiris/app/api/handlers_mind.py', import.meta.url), 'utf8');

const ESITI = {};
for (const m of STORE.matchAll(/^(ATTEMPT_\w+) = "([^"]*)"$/gm)) ESITI[m[1]] = m[2];
const blocco = GESTORE.match(/^_ATTEMPT_WORDS = \{([\s\S]*?)^\}/m);
assert.ok(blocco, 'handlers_mind.py: _ATTEMPT_WORDS non si legge');
const LETTURA = {};
for (const m of blocco[1].matchAll(/(ATTEMPT_\w+): \("([^"]*)", "(\w+)"\)/g)) {
  assert.ok(ESITI[m[1]], m[1] + ' non e\' in mind/store.py');
  LETTURA[ESITI[m[1]]] = { parola: m[2], segno: m[3] };
}
assert.ok(Object.keys(LETTURA).length >= 4, 'lettura degli esiti rotta');

/* Il valore di un esito, per nome della costante: `esito('ATTEMPT_FAILED')`. */
export function esito(nome) {
  assert.ok(ESITI[nome], nome + ' non e\' in mind/store.py');
  return ESITI[nome];
}

/* Un tentativo con la sua lettura; un esito sconosciuto resta grezzo. */
export function conLettura(t) {
  const l = LETTURA[t.esito];
  return { ...t, esito_leggibile: l ? l.parola : t.esito,
           in_attesa: !!l && l.segno === 'attesa', riuscito: !!l && l.segno === 'riuscito',
           guasto: !!l && l.segno === 'guasto' };
}
