import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Collaudo 3.22, C4 ("la chat inventa l'ora dei messaggi"): misurato dal
   vivo il 07/09/2026 -- alle 08:28 tutte le bolle mostravano «08:28»,
   ricaricando alle 08:33 tutte mostravano «08:33», compresa la prima
   domanda della sessione. Causa: `GET api/chat/history` non portava
   nessun orario, e il client timbrava ogni bolla con `new Date()` al
   momento del DISEGNO, non dell'invio.

   La cura (chat_store.py + handlers_chat_history.py): la cronologia porta
   gia' l'ora vera in colonna (`timestamp`), scritta da `append()` a ogni
   turno -- bastava restituirla, non inventare una seconda fonte. Il client
   (chat/agents.js::applyHistory, chat/messages.js::appendMsg) la usa per
   disegnare le bolle ripristinate; un invio VIVO (chat/send.js) resta
   timbrato con "adesso", perche' e' proprio adesso che nasce.

   Questi due test pinnano ENTRAMBE le meta' della cura: la migliore (l'ora
   vera, quando c'e') e il minimo accettabile come difesa (nessuna ora
   inventata quando non c'e' -- oggi non capita mai, perche' la colonna e'
   NOT NULL fin dalla v3 dello schema, ma appendMsg() non deve indovinare
   comunque se un giorno arrivasse un payload malformato). */

function fixtureHtml() {
  return `<!doctype html><body>
    <div id="app">
      <main id="main">
        <div id="messages">
          <div id="welcome"><span id="welcome-hello">Ciao</span></div>
        </div>
        <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
        <div id="turn-counter" style="display:none"></div>
        <div id="session-ended-msg" style="display:none"></div>
        <div id="conn-dot"></div>
      </main>
    </div>
  </body>`;
}

function setup(t) {
  const ctx = loadScripts(
    ['config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js'],
    { html: fixtureHtml() },
  );
  if (t) t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });
  return ctx;
}

test("un messaggio ripristinato mostra l'ora VERA del server, non quella del ricaricamento", async (t) => {
  const { window, document } = setup(t);
  const timestampFisso = '2020-01-01T03:15:00Z';
  window.fetch = async (url) => {
    if (String(url).includes('api/chat/history')) {
      return {
        ok: true, status: 200,
        json: async () => ({ messages: [{ role: 'user', content: 'ciao', timestamp: timestampFisso }] }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatAgents.restore();

  const timeEl = document.querySelector('.msg-time');
  assert.ok(timeEl, 'la bolla ripristinata deve avere un elemento .msg-time');

  const atteso = new Date(timestampFisso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const adesso = new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  // Precondizione anti-coincidenza: se per puro caso l'ora reale del test
  // combaciasse con quella (fissa, del 2020) del timestamp, l'assert sotto
  // non distinguerebbe piu' "ha usato il timestamp" da "ha usato new Date()
  // al momento del disegno" -- il difetto misurato il 07/09.
  assert.notEqual(atteso, adesso,
    'precondizione di prova: le due ore non devono coincidere per caso in questa corsa');

  assert.equal(timeEl.textContent, atteso,
    "l'ora mostrata deve venire dal timestamp del server (2020), non da new Date() al momento del ricaricamento (oggi)");
});

test("un messaggio ripristinato SENZA timestamp non mostra un'ora inventata (difesa, minimo accettabile)", async (t) => {
  const { window, document } = setup(t);
  window.fetch = async (url) => {
    if (String(url).includes('api/chat/history')) {
      return {
        ok: true, status: 200,
        json: async () => ({ messages: [{ role: 'user', content: 'ciao senza orario' }] }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatAgents.restore();

  const timeEl = document.querySelector('.msg-time');
  assert.ok(timeEl, 'la bolla ripristinata deve avere un elemento .msg-time');
  assert.equal(timeEl.textContent, '',
    "senza un orario vero in cronologia, la bolla non deve mostrare NESSUN orario -- nemmeno quello di adesso");
});
