import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

/* ── Cancellare dice anche COSA RESTA (reperto C-6, 23/09/2026) ────────────

   La conferma diceva bene cosa si perde — i messaggi che vedi e i riassunti
   delle conversazioni precedenti — e taceva sul resto. Ma un proprietario che
   preme «cancella» sta chiedendo *«togli quello che ho detto a HIRIS»*, e due
   cose sopravvivono a quel gesto:

   - i **ricordi** (`remember`), che restano per sempre finché non li cancelli
     tu dalla pagina Memoria. È una scelta giusta — un ricordo è una cosa che
     hai chiesto di tenere, non un residuo della conversazione — ma era
     dichiarata solo nel codice;
   - la **risposta del modello** nella coda del ragionamento, dimenticata
     entro un quarto d'ora dalla consegna.

   Tacere la prima fa credere che «cancella» pulisca tutto, e questo prodotto
   non fa credere cose. */

const SORGENTE = fs.readFileSync(
  new URL('../../hiris/app/static/chat/agents.js', import.meta.url), 'utf8');

function conferma() {
  /* La funzione si estrae e si esegue da sola: e' l'unico modo di leggere la
     frase VERA invece di cercarne dei pezzi nel file, e una prova che cercasse
     pezzi resterebbe verde anche se la frase non venisse mai composta. */
  const inizio = SORGENTE.indexOf('function domandaDiConferma()');
  const fine = SORGENTE.indexOf('\n  }', SORGENTE.indexOf('Cancellare?', inizio)) + 4;
  const corpo = SORGENTE.slice(inizio, fine);
  const fn = new Function('state', corpo + '\nreturn domandaDiConferma();');
  return fn({ els: { messages: null } });
}

test('la conferma dice cosa si perde', () => {
  assert.match(conferma(), /riassunti delle tue conversazioni precedenti/);
});

test('e dice che tocca solo la propria conversazione (fetta «le chat divise»)', () => {
  /* Mutazione che la uccide: togliere la frase che distingue il proprio
     filo da quello degli altri in casa -- da questa fetta la DELETE non
     cancella piu' tutto, solo il filo di chi la chiede. */
  assert.match(conferma(), /quelle degli altri in casa restano intatte/);
});

test('e dice che i RICORDI restano, e dove si cancellano', () => {
  /* Mutazione che la uccide: togliere la frase sui ricordi. */
  const testo = conferma();
  assert.match(testo, /ricordi/i);
  assert.match(testo, /Memoria/,
    'non basta dire che restano: bisogna dire dove si tolgono');
});

test('non si può annullare, e continua a dirlo', () => {
  assert.match(conferma(), /non si può annullare/i);
});

/* La pagina dove la conferma manda il proprietario deve confermare la stessa
   cosa: due frasi che dicono conservazioni diverse sono peggio di una sola. */

const MEMORIA = fs.readFileSync(
  new URL('../../hiris/app/static/config/memory-route.js', import.meta.url), 'utf8');

test('la pagina Memoria dichiara che i ricordi non scadono', () => {
  /* Mutazione che la uccide: togliere la frase dal sottotitolo. */
  assert.match(MEMORIA, /non scadono/);
  assert.match(MEMORIA, /non se ne vanno cancellando la conversazione/,
    'è il legame fra le due pagine: senza, la conferma della chat rimanda a '
    + 'una pagina che non conferma niente');
});
