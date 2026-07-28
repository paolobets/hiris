import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* SP-4 Fase B Task 7: rebuild della card Lovelace (hiris-chat-card.js) sulle
   specifiche 1.0. Grounding B7 elenca cosa va preservato senza aggiungere
   retrocompat: il fallback chatbot_id/agent_id in setConfig, e "i tre modi
   di risposta" di _sendMessage — 202 (chat via abbonamento -> polling),
   text/event-stream (SSE manuale su righe `data: `), JSON semplice
   (`data.response`). Finora l'unica copertura reale era testuale
   (tests/test_lovelace_registration.py legge il sorgente con `in`); questi
   sono i primi test comportamentali richiesti dal piano (tabella "Test
   comportamentali richiesti per task", riga 7).

   Harness — perché il file viene caricato UNA SOLA volta:
   hiris-chat-card.js non è un IIFE come i moduli config/*.js (quelli
   nascondono `const`/`let` dentro una closure): è un vero script di
   pagina, pensato per un <script type="module"> HA, con `const POLL_MS`,
   `class HirisCard`, ecc. dichiarati a livello TOP. loadScripts() esegue il
   sorgente con un eval indiretto contro il global dell'host (vedi
   helpers/dom.mjs): un secondo `loadScripts(['hiris-chat-card.js'])` nello
   stesso processo ridichiarerebbe quegli stessi `const`/`class` e
   lancerebbe "SyntaxError: Identifier 'POLL_MS' has already been
   declared". Per questo il file è caricato UNA VOLTA a livello di modulo
   (fuori da ogni test()) — esattamente come un browser che carica lo
   script una volta sola — e ogni test() costruisce una propria istanza
   della card via `customElements.get('hiris-chat-card')`, come farebbe
   `document.createElement('hiris-chat-card')` in una dashboard reale.
   `HTMLElement`/`customElements`/`CustomEvent` sono stati aggiunti al
   bridge di helpers/dom.mjs per questo file (vedi commento lì): erano
   assenti perché nessun modulo config/*.js precedente è un vero Custom
   Element.

   Stato modulo condiviso fra i test() (_cachedIngressBase, il modulo mette
   in cache la base ingress al PRIMO discover e non la ri-richiede più):
   lo stub di fetch qui sotto risponde sempre "niente ingress_url" per
   hiris-ingress.json, quindi _cachedIngressBase resta null in ogni test,
   indipendentemente dall'ordine di esecuzione — nessuna dipendenza fra
   test().

   Cosa NON è testato qui e perché: l'apertura websocket reale verso HA
   (_ensureIngressSession → hass.callApi) non è esercitata — tutti i test
   usano un `hass` nullo o senza `callApi`, che fa tornare la funzione
   subito (branch già coperto a livello di guardia, non richiede una vera
   sessione HA). Il modo 202 aspetta un vero `setTimeout` di 3.5s
   (POLL_INTERVAL_MS in _pollChatReply, non configurabile dall'esterno) —
   si è scelto di NON mockare i timer per evitare di dover far avanzare a
   mano una catena di await/microtask fragile; il test è quindi ~3.5s più
   lento degli altri ma deterministico e fedele al comportamento reale. */

const { window } = loadScripts(['hiris-chat-card.js']);
const Card = window.customElements.get('hiris-chat-card');
const Editor = window.customElements.get('hiris-chat-card-editor');

assert.ok(Card, 'hiris-chat-card deve essere registrato via customElements.define');
assert.ok(Editor, 'hiris-chat-card-editor deve essere registrato via customElements.define');

/**
 * Stub di fetch per lo scenario "manda un messaggio". Instrada per URL:
 *  - hiris-ingress.json  -> nessun ingress_url (fallback su hassUrl)
 *  - .../api/chat/reply/<job> -> risposta al polling (modo 202)
 *  - .../api/chat (esatto, niente segmenti dopo)  -> risposta all'invio
 *  - .../api/chatbots...  -> fallback generico (toggle / status)
 * Ogni chiamata è registrata in `calls` per asserire su method/headers.
 */
function stubChatFetch({ chat, reply, chatbots } = {}) {
  const calls = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    calls.push({ url: u, opts: opts || {} });
    if (u.includes('hiris-ingress.json')) {
      return { ok: false, status: 404, json: async () => ({}) };
    }
    if (u.includes('api/chat/reply/')) {
      if (typeof reply === 'function') return reply(u, opts);
      return { ok: true, status: 200, json: async () => reply };
    }
    if (u.endsWith('/api/chat')) {
      if (typeof chat === 'function') return chat(u, opts);
      return chat;
    }
    if (u.includes('api/chatbots')) {
      if (typeof chatbots === 'function') return chatbots(u, opts);
      return chatbots || { ok: true, status: 200, json: async () => ([]) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
  return calls;
}

function sseBody(chunks) {
  let i = 0;
  return {
    getReader: () => ({
      read: async () => {
        if (i < chunks.length) {
          return { done: false, value: new TextEncoder().encode(chunks[i++]) };
        }
        return { done: true, value: undefined };
      },
    }),
  };
}

// ---------------------------------------------------------------------------
// setConfig: fallback legacy agent_id
// ---------------------------------------------------------------------------

test('setConfig con la sola chiave legacy agent_id risolve comunque l\'id (dashboard esistenti)', () => {
  const card = new Card();
  card.setConfig({ agent_id: 'legacy-chatbot' });

  assert.equal(card._agentId, 'legacy-chatbot',
    'niente nuova retrocompat da aggiungere (1.0), ma questo fallback esiste già e non va rotto');
  // Con un id risolto la card deve renderizzare lo stato configurato, non
  // il placeholder "Card non configurata".
  assert.ok(!card.shadowRoot.querySelector('.unconfigured'),
    'con agent_id risolto in _agentId la card non deve mostrare lo stato non configurato');
});

test('setConfig con chatbot_id (chiave 1.0) prevale se entrambe le chiavi sono presenti', () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'new-key', agent_id: 'old-key' });
  assert.equal(card._agentId, 'new-key');
});

// ---------------------------------------------------------------------------
// I tre modi di risposta di _sendMessage
// ---------------------------------------------------------------------------

test('modo 202 (chat via abbonamento): passa al polling e mostra la risposta finale', async () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'c-202' });
  stubChatFetch({
    chat: {
      ok: true,
      status: 202,
      headers: { get: (h) => (h === 'Content-Type' ? 'application/json' : null) },
      json: async () => ({ status: 'pending', job_id: 'job-abc' }),
    },
    reply: { status: 'done', reply: 'Risposta via abbonamento' },
  });

  await card._sendMessage('ciao');

  const last = card._messages[card._messages.length - 1];
  assert.equal(last.role, 'assistant');
  assert.equal(last.text, 'Risposta via abbonamento');
  assert.equal(last.streaming, false);
});

test('modo SSE (text/event-stream): assembla i token e chiude su done', async () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'c-sse' });
  stubChatFetch({
    chat: {
      ok: true,
      status: 200,
      headers: { get: (h) => (h === 'Content-Type' ? 'text/event-stream' : null) },
      body: sseBody([
        'data: {"type":"token","text":"Ciao"}\n\n',
        'data: {"type":"token","text":" mondo"}\n\n',
        'data: {"type":"done"}\n\n',
      ]),
    },
  });

  await card._sendMessage('ciao');

  const last = card._messages[card._messages.length - 1];
  assert.equal(last.text, 'Ciao mondo');
  assert.equal(last.streaming, false);
});

test('modo SSE: discard_collected svuota il buffer accumulato finora', async () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'c-sse-discard' });
  stubChatFetch({
    chat: {
      ok: true,
      status: 200,
      headers: { get: (h) => (h === 'Content-Type' ? 'text/event-stream' : null) },
      body: sseBody([
        'data: {"type":"token","text":"scarta questo"}\n\n',
        'data: {"type":"discard_collected"}\n\n',
        'data: {"type":"token","text":"testo finale"}\n\n',
        'data: {"type":"done"}\n\n',
      ]),
    },
  });

  await card._sendMessage('ciao');

  const last = card._messages[card._messages.length - 1];
  assert.equal(last.text, 'testo finale');
});

test('modo JSON semplice: usa data.response', async () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'c-json' });
  stubChatFetch({
    chat: {
      ok: true,
      status: 200,
      headers: { get: (h) => (h === 'Content-Type' ? 'application/json' : null) },
      json: async () => ({ response: 'Risposta diretta JSON' }),
    },
  });

  await card._sendMessage('ciao');

  const last = card._messages[card._messages.length - 1];
  assert.equal(last.text, 'Risposta diretta JSON');
  assert.equal(last.streaming, false);
});

// ---------------------------------------------------------------------------
// X-Requested-With sulle scritture (guardia CSRF, C9 del piano)
// ---------------------------------------------------------------------------

test('X-Requested-With presente sulla POST api/chat', async () => {
  const card = new Card();
  card.setConfig({ chatbot_id: 'c-csrf-post' });
  const calls = stubChatFetch({
    chat: {
      ok: true,
      status: 200,
      headers: { get: (h) => (h === 'Content-Type' ? 'application/json' : null) },
      json: async () => ({ response: 'ok' }),
    },
  });

  await card._sendMessage('ciao');

  const postCall = calls.find((c) => c.opts.method === 'POST' && c.url.endsWith('/api/chat'));
  assert.ok(postCall, 'la POST a api/chat deve essere stata effettuata');
  assert.equal(postCall.opts.headers['X-Requested-With'], 'fetch');
});

test('X-Requested-With presente sulla PUT di toggle (api/chatbots/<id>)', async () => {
  const card = new Card();
  // hass impostato PRIMA di setConfig: quando l'agentId è ancora nullo il
  // setter di `hass` non avvia il polling di stato (branch dedicato in
  // `set hass`), evitando un setInterval reale che terrebbe vivo il
  // processo di test oltre la fine della suite.
  card.hass = { connection: { options: { hassUrl: 'http://ha.local' } }, states: {} };
  card.setConfig({ chatbot_id: 'c-csrf-put' });

  const calls = stubChatFetch({
    chatbots: { ok: true, status: 200, json: async () => ({ enabled: false }) },
  });

  await card._toggleAgent(true /* skipUndo: niente snackbar/timer nel test */);

  const putCall = calls.find((c) => c.opts.method === 'PUT' && c.url.includes('api/chatbots/'));
  assert.ok(putCall, 'la PUT di toggle deve essere stata effettuata');
  assert.equal(putCall.opts.headers['X-Requested-With'], 'fetch');
});
