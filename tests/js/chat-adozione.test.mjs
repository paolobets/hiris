import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, tick, staticSnapshotDir } from './helpers/dom.mjs';
import { fintoFetch, maiRisposta, risposta } from './helpers/fetch.mjs';

/* S-41 (Chiusura, 14/10/2026): cio' che c'era prima delle chat divise passa
   al proprietario con `POST api/chat/adopt`, che `chat/main.js` chiama una
   volta all'apertura; la cronologia e l'elenco delle conversazioni lo
   aspettano. Fino a quel giorno adottavano le GET stesse (lato server lo
   provano `tests/test_chat_divise.py`, `test_conversazioni.py` e
   `test_promesse_divise.py`). Qui gira `chat/main.js` vero, con
   lo stesso schema di chat-build-check-wiring.test.mjs.

   Mutazioni ESEGUITE (14/10/2026): `restore()` chiamata subito invece che
   dopo l'adozione -- rossa la prima prova; `init()` delle conversazioni
   senza aspettare l'adozione -- rossa la prima prova; l'adozione tolta dal
   boot -- rosse tutte e due. */
const MAIN = join(staticSnapshotDir(), 'chat', 'main.js');

const MODULI = [
  'common.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js',
  'chat/conversations.js', 'chat/send.js', 'chat/theme.js', 'chat/sidebar.js', 'chat/keyboard.js',
  'build-check.js', 'pending-badge.js',
];

const HTML = `<!doctype html><body><div id="app">
  <aside id="sidebar"><div id="conv-list"></div><button id="new-conv-btn"></button></aside>
  <main id="main"><header id="header"><div id="header-title"></div><div id="header-subtitle"></div>
  <button id="delete-conv-btn"></button><div id="conn-dot"></div></header>
  <div id="messages"><div id="welcome"></div></div>
  <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
  <div id="turn-counter" style="display:none"></div><div id="conv-notice" hidden></div>
  <div id="session-ended-msg" style="display:none"></div></main></div></body>`;

async function avvia(t, adozione) {
  const ctx = loadScripts(MODULI, { html: HTML });
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  const chiamate = fintoFetch(ctx.window, {
    'POST api/chat/adopt': adozione,
    'api/health': maiRisposta,
    'api/config': maiRisposta,
    'api/chat-settings': maiRisposta,
    'api/pending': maiRisposta,
    'api/chat/history': { messages: [] },
    'api/chat/conversations': { conversations: [] },
  });
  const veroSet = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  try {
    // eslint-disable-next-line no-eval -- eval indiretto del file vero, come in chat-build-check-wiring
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
  }
  t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });
  return chiamate;
}

const letture = (chiamate) => chiamate
  .filter((c) => c.metodo === 'GET' && /^api\/chat\/(history|conversations)$/.test(c.url))
  .map((c) => c.url).sort();

test('all\'apertura l\'adozione parte una volta, e cronologia ed elenco la aspettano', async (t) => {
  let rispondi;
  const chiamate = await avvia(t, () => new Promise((r) => { rispondi = r; }));
  const adozioni = chiamate.filter((c) => c.url === 'api/chat/adopt');
  assert.equal(adozioni.length, 1);
  assert.equal(adozioni[0].metodo, 'POST');
  assert.equal(adozioni[0].opts.headers['X-Requested-With'], 'fetch');
  assert.deepEqual(letture(chiamate), [], 'una lettura e\' partita prima dell\'adozione');
  rispondi(risposta(null, 204));
  await tick(0);
  await tick(0);
  assert.deepEqual(letture(chiamate), ['api/chat/conversations', 'api/chat/history']);
  assert.equal(chiamate.filter((c) => c.url === 'api/chat/adopt').length, 1);
});

test('un\'adozione non riuscita non ferma le letture', async (t) => {
  const errori = [];
  const veroErrore = console.error;
  console.error = (...a) => { errori.push(a.join(' ')); };
  try {
    const chiamate = await avvia(t, () => { throw new Error('rete giu'); });
    await tick(0);
    await tick(0);
    assert.deepEqual(letture(chiamate), ['api/chat/conversations', 'api/chat/history']);
  } finally {
    console.error = veroErrore;
  }
  assert.ok(errori.some((e) => e.includes('adoptOrphans failed')), errori.join(' | '));
});
