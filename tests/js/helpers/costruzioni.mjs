/* Le parole di una costruzione, chieste ai loro sorgenti Python invece di
   ricopiarle nelle prove (C-10): il nome del dominio e del gesto da
   `handlers_constructions.py` (`_DOMAIN_WORDS`, `_GESTURE_WORDS`),
   l'articolo da `workshop.py` (`ARTICOLO_DETERMINATIVO`). I finti server
   delle prove mettono i campi come li mette `construction_words`. */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const ROTTA = readFileSync(
  new URL('../../../hiris/app/api/handlers_constructions.py', import.meta.url), 'utf8');
const OFFICINA = readFileSync(
  new URL('../../../hiris/app/action/construction/workshop.py', import.meta.url), 'utf8');

function dizionario(sorgente, nome) {
  const m = sorgente.match(new RegExp('^' + nome + ' = \\{([\\s\\S]*?)\\}$', 'm'));
  assert.ok(m, nome + ' non trovato');
  return m[1];
}

const DOMINI = {};
for (const m of dizionario(ROTTA, '_DOMAIN_WORDS').matchAll(/"(\w+)": "([^"]*)"/g)) DOMINI[m[1]] = m[2];
const GESTI = {};
for (const m of dizionario(ROTTA, '_GESTURE_WORDS').matchAll(/"(\w+)": \("([^"]*)", (True|False)\)/g)) {
  GESTI[m[1]] = { parola: m[2], tocca: m[3] === 'True' };
}
const ARTICOLI = {};
for (const m of dizionario(OFFICINA, 'ARTICOLO_DETERMINATIVO').matchAll(/"(\w+)": "([^"]*)"/g)) ARTICOLI[m[1]] = m[2];
assert.ok(Object.keys(DOMINI).length >= 3 && Object.keys(GESTI).length >= 3
  && Object.keys(ARTICOLI).length >= 3, 'parole delle costruzioni: lettura rotta');

/* Una riga costruibile come la manda il server, con le sue parole. Le righe a
   mano (`a_mano`) non hanno dominio ne' gesto, e restano com'erano. */
export function conParole(riga) {
  if (!riga || riga.a_mano || typeof riga.dominio !== 'string' || 'dominio_nome' in riga) return riga;
  const gesto = GESTI[riga.gesto] || { parola: riga.gesto, tocca: false };
  return { ...riga, dominio_nome: DOMINI[riga.dominio] ?? riga.dominio,
           articolo: ARTICOLI[riga.dominio] ?? null, gesto_leggibile: gesto.parola,
           esisteva: gesto.tocca && riga.prima != null };
}
