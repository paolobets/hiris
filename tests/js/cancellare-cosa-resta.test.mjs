import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { loadScripts } from './helpers/dom.mjs';

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

/* La domanda VERA, quella che compare a chi preme il cestino: si fa girare la
   pagina (agents.js + conversations.js) con una conversazione aperta e si
   legge cio' che arriva a `confirm`. Una prova che cercasse pezzi nel file
   resterebbe verde anche se la frase non venisse mai mostrata. Dalla fetta
   «il seguito delle chat divise» (spec 2026-09-26 §4) il cestino cancella la
   conversazione APERTA: la frase non e' piu' composta contando i messaggi, e'
   il testo esatto della spec. */
async function conferma() {
  const { window } = loadScripts(
    ['config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js',
     'chat/conversations.js'],
    { html: `<!doctype html><body><div id="messages"><div id="welcome"></div></div>
      <textarea id="input"></textarea><button id="send-btn"></button>
      <div id="turn-counter"></div><div id="session-ended-msg"></div>
      <button id="delete-conv-btn"></button></body>` },
  );
  window.fetch = async () => ({ ok: true, status: 200, json: async () => ({ conversations: [
    { id: 'c1', titolo: 'ciao', ultimo_messaggio: '', attiva: true }] }) });
  await window.HirisChatConversations.refresh();
  let domanda = null;
  window.confirm = (m) => { domanda = m; return false; };
  await window.HirisChatAgents.clearConversation();
  return domanda;
}

test('la conferma dice cosa si perde', async () => {
  assert.match(await conferma(), /Perdi i messaggi di questa conversazione e il suo riassunto/);
});

test('e dice che tocca solo QUESTA conversazione (fetta «il seguito delle chat divise»)', async () => {
  /* Mutazione che la uccide: togliere la frase sulle altre conversazioni.
     Era «quelle degli altri in casa restano intatte» quando la DELETE
     cancellava il filo intero; adesso cancella una conversazione, e cio'
     che resta da dire e' che le altre -- le tue -- restano. */
  assert.match(await conferma(), /Le tue altre conversazioni restano/);
});

test('e dice che i RICORDI restano, e dove si cancellano', async () => {
  /* Mutazione che la uccide: togliere la frase sui ricordi. */
  const testo = await conferma();
  assert.match(testo, /ricordi/i);
  assert.match(testo, /Memoria/,
    'non basta dire che restano: bisogna dire dove si tolgono');
});

test('non si può annullare, e continua a dirlo', async () => {
  assert.match(await conferma(), /non si può annullare/i);
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
