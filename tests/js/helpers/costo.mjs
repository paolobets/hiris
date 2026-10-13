/* Come si legge il costo di una riga dei consumi, chiesto al suo sorgente
   (`hiris/app/api/handlers_usage.py`: `_COST_NUMBERS`, `_COST_WORDS`,
   `_COST_FLOOR`, C-10) invece di ricopiarlo nelle prove. I finti server
   mettono i campi come li mette `_cost_reading`. */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const SORGENTE = readFileSync(
  new URL('../../../hiris/app/api/handlers_usage.py', import.meta.url), 'utf8');

const numeri = SORGENTE.match(/^_COST_NUMBERS = \(([^)]*)\)/m);
const parole = SORGENTE.match(/^_COST_WORDS = \{([\s\S]*?)\}$/m);
const pavimento = SORGENTE.match(/^_COST_FLOOR = "([^"]*)"$/m);
assert.ok(numeri && parole && pavimento, 'handlers_usage.py: le parole del costo non si leggono');
const NUMERI = [...numeri[1].matchAll(/"([^"]*)"/g)].map((m) => m[1]);
const PAROLE = {};
for (const m of parole[1].matchAll(/"(\w+)": "([^"]*)"/g)) PAROLE[m[1]] = m[2];
assert.ok(NUMERI.length >= 2 && Object.keys(PAROLE).length >= 3, 'lettura del costo rotta');

/* Una riga (modello o secchiello) con la sua lettura del costo. */
export function conLettura(riga) {
  if (!riga || typeof riga.cost_state !== 'string') return riga;
  const numero = NUMERI.includes(riga.cost_state);
  return { ...riga, cost_is_number: numero,
           cost_is_floor: riga.cost_state === pavimento[1] && !!(riga.cost_eur > 0),
           cost_word: numero ? null : (PAROLE[riga.cost_state] ?? riga.cost_state) };
}

/* Una risposta di `GET /api/usage` con la lettura su ogni modello. */
export function conLetture(risposta) {
  if (!risposta || !Array.isArray(risposta.sections)) return risposta;
  return { ...risposta, sections: risposta.sections.map((s) => (
    Array.isArray(s.models) ? { ...s, models: s.models.map(conLettura) } : s)) };
}
