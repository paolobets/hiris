import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { FRASI, tupla } from './helpers/stati.mjs';

/* Il vocabolario degli stati e le due pagine che lo disegnano (Impegni e
   Proposte).

   **Le parole vivono in Python** (`hiris/app/states.py`, Tappa 8, D4): le
   tre code -- promesse, costruzioni, proposte da fare a mano -- le compongono
   da li', e la rotta manda a ogni riga la frase del suo stato
   (`stato_leggibile`, C-10). Le pagine non tengono piu' una tabella delle
   parole (`STATE_LABEL`, uscita l'08/10/2026); il COLORE del badge e' uno
   per tutte le code (`STATE_BADGE` in common.js, dall'08/10/2026) e, la
   pagina Impegni, tiene i due filtri delle sue sezioni
   (`PENDING_STATES`, `OUTCOME_STATES`). Sono quelle copie che possono
   divergere in silenzio, e questo file le lega ai vocabolari Python per
   VALORI, mai per nomi.

   Review finale della fetta «lo schedulatore», rilievo ②: uno stato non
   conclusivo aggiunto in Python e dimenticato nel JavaScript sparirebbe in
   silenzio dalla sezione «In sospeso» della pagina.

   Mutazioni ESEGUITE l'08/10/2026: tolta `fallita` da `STATE_BADGE` (allora
   di constructions-route.js, oggi di common.js) -- rossa; aggiunto uno stato a `STATES_CONCLUSI`
   di promise.py senza la sua frase in states.py -- rosse la prova del
   badge e della frase, e quella che vuole i due insiemi diversi della sola
   `disdetta`. */

const PROMESSA_PY = readFileSync(
  new URL('../../hiris/app/keeper/promise.py', import.meta.url), 'utf8');
const AGENDA_JS = readFileSync(
  new URL('../../hiris/app/static/config/agenda-route.js', import.meta.url), 'utf8');
const COSTRUZIONI_JS = readFileSync(
  new URL('../../hiris/app/static/config/constructions-route.js', import.meta.url), 'utf8');
const COMMON_JS = readFileSync(
  new URL('../../hiris/app/static/common.js', import.meta.url), 'utf8');

function elencoJs(sorgente, nome) {
  const m = sorgente.match(new RegExp('var ' + nome + ' = \\[([^\\]]*)\\]'));
  assert.ok(m, nome + ' non trovata');
  return m[1].split(',').map((s) => s.trim()).filter(Boolean)
    .map((s) => s.replace(/^["']|["']$/g, ''));
}

function chiaviDiOggetto(sorgente, nome) {
  const m = sorgente.match(new RegExp('var ' + nome + ' = \\{([\\s\\S]*?)\\};'));
  assert.ok(m, nome + ' non trovata');
  return new Set(Array.from(m[1].matchAll(/(\w+):/g)).map((mm) => mm[1]));
}

test('gli stati in sospeso: lo stesso insieme in states.py (SUSPENDED) e in agenda-route.js (PENDING_STATES)', () => {
  const python = tupla('SUSPENDED');
  // Se questa riga fallisse, il problema e' la lettura del sorgente Python,
  // non ancora un confronto col JS.
  assert.deepEqual(new Set(python), new Set(['in_attesa', 'in_corso']));
  assert.deepEqual(new Set(elencoJs(AGENDA_JS, 'PENDING_STATES')), new Set(python),
    'gli stati "in sospeso" devono essere lo stesso insieme in Python e in JavaScript');
});

test('ogni stato di una promessa ha un badge in common.js e una frase in states.py', () => {
  const stati = tupla('PROMISE_STATES');
  // I conclusivi di promise.py sono fra questi: la tupla li compone dal vocabolario.
  for (const s of tupla('STATES_CONCLUSI', PROMESSA_PY)) assert.ok(stati.includes(s), s);
  const badge = chiaviDiOggetto(COMMON_JS, 'STATE_BADGE');
  for (const stato of stati) {
    assert.ok(badge.has(stato), 'STATE_BADGE di common.js non conosce «' + stato + '»');
    assert.ok(FRASI[stato], 'states.READABLE non ha la frase di «' + stato + '»');
  }
});

test('ogni stato di una costruzione ha un badge in common.js e una frase in states.py', () => {
  const badge = chiaviDiOggetto(COMMON_JS, 'STATE_BADGE');
  for (const stato of tupla('CONSTRUCTION_STATES')) {
    assert.ok(badge.has(stato), 'STATE_BADGE di common.js non conosce «' + stato + '»');
    assert.ok(FRASI[stato], 'states.READABLE non ha la frase di «' + stato + '»');
  }
  /* E non conosce parole che il vocabolario non ha: un colore per uno stato
     che nessun archivio scrive e' una copia rimasta indietro (era `rifiutata`
     fino all'08/10/2026). */
  const note = new Set([...tupla('CONSTRUCTION_STATES'), ...tupla('PROMISE_STATES')]);
  for (const stato of badge) assert.ok(note.has(stato), 'STATE_BADGE conosce «' + stato + '», che non e\' uno stato');
});

test('il colore del badge e\' uno per tutte le code: le pagine non tengono una mappa loro', () => {
  /* Fino all'08/10/2026 agenda-route.js e constructions-route.js avevano
     ciascuna la sua `STATE_BADGE` (ux-ui-specialist, 08/10/2026).
     Mutazione ESEGUITA: una `var STATE_BADGE` rimessa in agenda-route.js --
     rossa. */
  for (const [nome, sorgente] of [['agenda-route.js', AGENDA_JS], ['constructions-route.js', COSTRUZIONI_JS]]) {
    assert.doesNotMatch(sorgente, /var STATE_BADGE\b/, nome + ' ha di nuovo la sua mappa dei colori');
    assert.match(sorgente, /stateBadge\(\w+\.stato\)/, nome + ' non chiede il colore a common.js');
  }
});

test('ogni stato di una proposta da fare a mano ha una frase in states.py', () => {
  for (const stato of tupla('PROPOSAL_STATES')) {
    assert.ok(FRASI[stato], 'states.READABLE non ha la frase di «' + stato + '»');
  }
});

test('le pagine non tengono piu\' una tabella delle parole: la frase arriva dalla rotta', () => {
  for (const [nome, sorgente] of [['agenda-route.js', AGENDA_JS], ['constructions-route.js', COSTRUZIONI_JS]]) {
    assert.doesNotMatch(sorgente, /var STATE_LABEL\b/, nome + ' ha di nuovo la sua tabella delle parole');
    assert.match(sorgente, /stateLabel\(\w+\.stato_leggibile/, nome + ' non legge la frase della rotta');
  }
});

/* Il terzo vocabolario: gli stati che sono una NOTIZIA (`STATES_ESITO` /
   `OUTCOME_STATES`). Non coincide con quello dei conclusi: `disdetta` e'
   fuori, perche' una promessa disdetta e' un ordine dell'utente, non un
   esito che gli e' capitato. */
test('gli stati che sono una notizia: lo stesso insieme in promise.py (STATES_ESITO) e in agenda-route.js (OUTCOME_STATES)', () => {
  const python = tupla('STATES_ESITO', PROMESSA_PY);
  assert.deepEqual(new Set(python), new Set(['mantenuta', 'saltata', 'fallita']));
  assert.deepEqual(new Set(elencoJs(AGENDA_JS, 'OUTCOME_STATES')), new Set(python));
});

test('«disdetta» e\' conclusa ma NON e\' una notizia: i due insiemi differiscono di lei sola', () => {
  const conclusi = new Set(tupla('STATES_CONCLUSI', PROMESSA_PY));
  const esiti = new Set(tupla('STATES_ESITO', PROMESSA_PY));
  assert.deepEqual([...conclusi].filter((s) => !esiti.has(s)), ['disdetta']);
});
