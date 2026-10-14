/* Le parole di una costruzione, chieste ai loro sorgenti Python invece di
   ricopiarle nelle prove (C-10): il nome del dominio e del gesto da
   `handlers_constructions.py` (`_DOMAIN_WORDS`, `_GESTURE_WORDS`),
   l'articolo da `workshop.py` (`ARTICOLO_DETERMINATIVO`). I finti server
   delle prove mettono i campi come li mette `construction_words`. */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { paroleDellaRotta, parolaDi, tupla } from './stati.mjs';

const ROTTA = readFileSync(
  new URL('../../../hiris/app/api/handlers_constructions.py', import.meta.url), 'utf8');
const OFFICINA = readFileSync(
  new URL('../../../hiris/app/action/construction/workshop.py', import.meta.url), 'utf8');
const RIFACIMENTO = readFileSync(
  new URL('../../../hiris/app/mind/proposal_redo.py', import.meta.url), 'utf8');

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

/* Cosa si puo' fare di una costruzione, con le regole dell'officina
   (`workshop.DECIDABLE`, `RESTORABLE`), come lo mette
   `handlers_constructions.construction_rules` (C-10, Chiusura, 14/10/2026). */
const DECIDIBILE = parolaDi('DECIDABLE', OFFICINA);
const RIPRISTINABILI = tupla('RESTORABLE', OFFICINA);
assert.ok(RIPRISTINABILI.length >= 2, 'workshop.py: RESTORABLE troppo corta');

/* Le parole degli stati che la rotta manda all'elenco (`stati`,
   `stati_rifacimento`), lette da `handlers_constructions.py` e risolte nei
   loro sorgenti. */
export const STATI = paroleDellaRotta(ROTTA, 'PAGE_STATES');
export const STATI_RIFACIMENTO = paroleDellaRotta(ROTTA, 'REDO_STATES',
  { proposal_redo: RIFACIMENTO });

/* Una riga costruibile come la manda il server, con le sue parole e le sue
   regole. Le righe a mano (`a_mano`) non hanno dominio ne' gesto, e restano
   com'erano. */
export function conParole(riga) {
  if (!riga || riga.a_mano || typeof riga.dominio !== 'string' || 'dominio_nome' in riga) return riga;
  const gesto = GESTI[riga.gesto] || { parola: riga.gesto, tocca: false };
  return { ...riga, dominio_nome: DOMINI[riga.dominio] ?? riga.dominio,
           articolo: ARTICOLI[riga.dominio] ?? null, gesto_leggibile: gesto.parola,
           esisteva: gesto.tocca && riga.prima != null,
           decidibile: riga.stato === DECIDIBILE,
           ripristinabile: RIPRISTINABILI.includes(riga.stato) };
}

/* L'elenco come lo manda `GET api/constructions`: le righe con parole e
   regole, e le parole degli stati che la pagina riconosce. */
export function elencoCome(risposta, conFrase = (r) => r) {
  return risposta && Array.isArray(risposta.constructions)
    ? { stati: STATI, stati_rifacimento: STATI_RIFACIMENTO, ...risposta,
        constructions: risposta.constructions.map((r) => conParole(conFrase(r))) }
    : risposta;
}
