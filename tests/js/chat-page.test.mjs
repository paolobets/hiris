import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 8: rebuild della pagina chat standalone (static/index.html).
   Il JS inline (~610 righe) è stato estratto in static/chat/*.js, uno per
   blocco funzionale (state/messages/agents/send/theme/tasks/sidebar/keyboard/
   main) -- vedi task-8-report.md per il dettaglio dello split. L'onboarding
   che faceva parte di quell'elenco è uscito con la fetta E5 Task 1 (C1: il
   primo gesto del primo utilizzo dava un errore). Questi sono i test
   comportamentali richiesti dal piano (tabella "Test comportamentali
   richiesti per task", riga 8): invio -> POST con chatbot_id, risposta 202
   -> il polling completa, turn-limit blocca l'invio, il pannello task carica
   e cancella.

   Fixture HTML: replica il sottoinsieme di static/index.html che estato.js/
   chat/*.js toccano al load (state.js cattura i riferimenti DOM
   IMMEDIATAMENTE, non dentro un DOMContentLoaded -- lo script vive in fondo
   al <body>, col markup già presente, esattamente come il vecchio <script>
   inline). Solo chat/main.js esegue side-effect (boot(): fetch, setInterval)
   al caricamento -- per questo NON è mai incluso qui: ogni test carica solo
   i moduli che gli servono e li pilota a mano, come fa entity-picker.test.mjs
   con config/*.js. */

function fixtureHtml() {
  return `<!doctype html><body>
    <div id="app">
      <div id="sidebar-overlay" style="display:none"></div>
      <aside id="sidebar">
        <div id="agent-list"></div>
        <div id="usage-widget">
          <span class="usage-val" id="u-requests">—</span>
          <span class="usage-val" id="u-input">—</span>
          <span class="usage-val" id="u-output">—</span>
          <span class="usage-val" id="u-cost">—</span>
        </div>
      </aside>
      <main id="main">
        <header id="header">
          <div id="header-title">HIRIS <span id="header-version"></span></div>
          <button id="theme-toggle"><svg class="ic-moon"></svg><svg class="ic-sun" style="display:none"></svg></button>
          <div id="agent-pill"><span id="ap-avatar"></span><span id="ap-name"></span></div>
          <div id="conn-dot"></div>
        </header>
        <div id="messages">
          <div id="welcome">
            <span id="welcome-hello">Ciao</span>
            <div class="quick-chips">
              <button class="chip" type="button" data-quick="Stato casa">Stato casa</button>
            </div>
          </div>
        </div>
        <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
        <div id="turn-counter" style="display:none"></div>
        <div id="session-ended-msg" style="display:none"></div>
        <div id="task-panel">
          <div id="task-panel-header"><button id="task-panel-back-btn" type="button"></button></div>
          <div id="task-active-list"></div>
          <div id="task-recent-list"></div>
        </div>
      </main>
    </div>
  </body>`;
}

function setupChat() {
  const ctx = loadScripts(
    ['config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js', 'chat/send.js'],
    { html: fixtureHtml() },
  );
  return ctx;
}

// ---------------------------------------------------------------------------
// Invio messaggio -> POST api/chat con chatbot_id + X-Requested-With
// ---------------------------------------------------------------------------

test('inviare un messaggio fa POST a api/chat con chatbot_id nel body e X-Requested-With', async () => {
  const { window } = setupChat();
  window.HirisChatState.activeAgentId = 'mio-chatbot';
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    return { ok: true, status: 200, json: async () => ({ response: 'ok' }) };
  };

  await window.HirisChatSend.send('ciao HIRIS');

  const postCall = calls.find((c) => c.opts.method === 'POST' && c.url.endsWith('api/chat'));
  assert.ok(postCall, 'la POST a api/chat deve essere stata effettuata');
  assert.equal(postCall.opts.headers['X-Requested-With'], 'fetch');
  const body = JSON.parse(postCall.opts.body);
  assert.equal(body.chatbot_id, 'mio-chatbot', 'il wire deve usare chatbot_id, non agent_id');
  assert.equal(body.message, 'ciao HIRIS');
});

// ---------------------------------------------------------------------------
// Risposta 202 (chat via abbonamento) -> il polling completa e la risposta
// viene renderizzata nella bolla placeholder.
// ---------------------------------------------------------------------------

test('risposta 202 pending: il polling completa e la risposta finale viene renderizzata', async () => {
  const { window, document } = setupChat();
  window.HirisChatState.activeAgentId = 'bot-202';
  window.fetch = async (url) => {
    const u = String(url);
    if (u.endsWith('api/chat')) {
      return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'job-1' }) };
    }
    if (u.includes('api/chat/reply/')) {
      return { ok: true, status: 200, json: async () => ({ status: 'done', reply: 'Risposta via abbonamento' }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatSend.send('quanto consumo oggi?');

  // Bolla "in elaborazione" (logo pulsante + timer) inserita subito, prima del poll
  const think = document.querySelector('.msg-row.assistant .bubble.thinking-live');
  assert.ok(think, 'la bolla "in elaborazione" deve comparire subito');
  assert.match(think.textContent, /elaborando/i);
  assert.ok(think.querySelector('.thinking-timer'), 'con il timer che scorre');

  // Il polling usa un vero setTimeout(3.5s) (stesso pattern accettato in
  // chat-card.test.mjs per _pollChatReply) -- nessun mock dei timer, per
  // restare fedeli al comportamento reale invece di far avanzare a mano
  // una catena di await fragile. Il test è quindi ~3.5s più lento.
  await tick(3700);

  const finalBubbles = document.querySelectorAll('.msg-row.assistant .bubble');
  assert.equal(finalBubbles[finalBubbles.length - 1].textContent, 'Risposta via abbonamento');
});

// ---------------------------------------------------------------------------
// Persistenza chat (bug live-verify #3): tornando alla chat da config (reload
// pieno) la conversazione spariva perche' la history dell'agente attivo non
// veniva MAI ricaricata al boot (setActive la carica solo al CAMBIO agente).
// restore() la ricarica.
// ---------------------------------------------------------------------------

test('restore() ricarica la history salvata dell\'agente attivo', async () => {
  const { window, document } = setupChat();
  window.HirisChatState.activeAgentId = 'bot-restore';
  const seen = [];
  window.fetch = async (url) => {
    seen.push(String(url));
    if (String(url).includes('/chat-history')) {
      return { ok: true, status: 200, json: async () => ({ messages: [
        { role: 'user', content: 'ciao' },
        { role: 'assistant', content: 'risposta salvata' },
      ] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatAgents.restore();

  assert.ok(seen.some((u) => /api\/chatbots\/bot-restore\/chat-history/.test(u)),
    'restore deve fetchare la history dell\'agente attivo');
  const bubbles = document.querySelectorAll('.msg-row .bubble');
  assert.ok(bubbles.length >= 2, 'i messaggi salvati devono ricomparire');
  assert.equal(document.getElementById('welcome').style.display, 'none',
    'il welcome si nasconde quando c\'e\' history');
  assert.equal(window.HirisChatState.agentTurnCounts['bot-restore'], 1,
    'un turno utente contato dalla history ricaricata');
});

// ---------------------------------------------------------------------------
// Mentre HIRIS elabora (richiesta utente): indicatore stile code + input
// bloccato per TUTTA l'elaborazione, incluso il poll della risposta via
// abbonamento (202) -- prima il finally di send() sbloccava troppo presto.
// ---------------------------------------------------------------------------

test('showTyping mostra l\'indicatore "stile code"', () => {
  const { window, document } = setupChat();
  window.HirisChatMessages.showTyping();
  const el = document.querySelector('#typing-indicator .thinking-code');
  assert.ok(el, 'l\'indicatore stile code deve comparire');
  assert.ok(el.querySelector('.tk-stream i'), 'con le barrette animate del "codice"');
});

test('showThinking: logo pulsante + timer; updateBubble ferma il timer e scrive la risposta', () => {
  const { window, document } = setupChat();
  const row = window.HirisChatMessages.showThinking();
  assert.ok(row.querySelector('.avatar.thinking-logo'), 'il logo HIRIS che pulsa');
  assert.ok(row.querySelector('.bubble.thinking-live .thinking-timer'), 'il timer che scorre');
  assert.ok(row._thinkingTimer, 'il timer e\' attivo durante l\'attesa');

  window.HirisChatMessages.updateBubble(row, 'Ecco la risposta');

  assert.equal(row._thinkingTimer, null, 'updateBubble ferma il timer');
  assert.match(row.querySelector('.bubble').textContent, /Ecco la risposta/);
  assert.equal(row.querySelector('.bubble').classList.contains('thinking-live'), false,
    'la bolla non e\' piu\' in stato "in elaborazione"');
});

test('durante la risposta via abbonamento (202) l\'input resta bloccato e un secondo invio non parte', async () => {
  const { window } = setupChat();
  const state = window.HirisChatState;
  state.activeAgentId = 'bot-lock';
  window.fetch = async (url) => {
    const u = String(url);
    if (u.endsWith('api/chat')) return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'j1' }) };
    if (u.includes('api/chat/reply/')) return { ok: true, status: 200, json: async () => ({ status: 'done', reply: 'fatto' }) };
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatSend.send('ciao');
  assert.equal(state.isLoading, true, 'lock attivo durante il poll');
  assert.equal(state.els.input.disabled, true, 'textarea disabilitata mentre elabora');

  const before = state.els.messages.querySelectorAll('.msg-row.user').length;
  await window.HirisChatSend.send('secondo messaggio');
  const after = state.els.messages.querySelectorAll('.msg-row.user').length;
  assert.equal(after, before, 'un secondo messaggio non deve partire mentre HIRIS elabora');

  await tick(3700); // il poll completa -> sblocco
  assert.equal(state.isLoading, false, 'sbloccato a fine poll');
  assert.equal(state.els.input.disabled, false, 'textarea riabilitata dopo la risposta');
});

// ---------------------------------------------------------------------------
// Turn limit: blocca l'invio disabilitando textarea + bottone (il vero
// meccanismo usato dalla pagina -- send() stesso non ha mai controllato il
// limite, solo checkTurnLimit() decide se i controlli sono utilizzabili;
// un browser reale non genera click/tastiera sui controlli disabled). jsdom
// non applica la semantica "disabled" alle dispatchEvent programmatiche
// (verificato: un click dispatchato su un <button disabled> continua a
// invocare i listener), quindi qui si asserisce lo STATO disabled prodotto
// da checkTurnLimit() -- è il segnale reale e verificabile del blocco.
// ---------------------------------------------------------------------------

test('turn-limit raggiunto disabilita input e send-btn (blocca l\'invio)', () => {
  const { window, document } = setupChat();
  const state = window.HirisChatState;
  state.activeAgentId = 'bot-limit';
  state.agentMaxTurns['bot-limit'] = 2;
  state.agentTurnCounts['bot-limit'] = 2;

  window.HirisChatAgents.checkTurnLimit();

  assert.equal(state.els.input.disabled, true);
  assert.equal(state.els.sendBtn.disabled, true);
  assert.equal(document.getElementById('session-ended-msg').style.display, '');

  // Sotto al limite: i controlli tornano utilizzabili.
  state.agentTurnCounts['bot-limit'] = 1;
  window.HirisChatAgents.checkTurnLimit();
  assert.equal(state.els.input.disabled, false);
  assert.equal(state.els.sendBtn.disabled, false);
});

// ---------------------------------------------------------------------------
// Sprint coerenza, lotto A, task 5 (A7): cancellare la cronologia era
// irreversibile e senza conferma -- la card Lovelace (hiris-chat-card.js)
// chiede conferma per la STESSA azione con lo stesso testo, qui mancava.
// Fratello nello stesso file: il fetch DELETE aveva un catch(e) {} vuoto --
// se il server falliva, la UI cancellava comunque i messaggi mostrati,
// dicendo "fatto" quando non lo era.
// ---------------------------------------------------------------------------

test('clearConversation chiede conferma prima di cancellare (come la card Lovelace)', async () => {
  const { window, document } = setupChat();
  window.HirisChatState.activeAgentId = 'bot-clear';
  window.HirisChatMessages.appendMsg('user', 'ciao');
  document.getElementById('welcome').style.display = 'none';

  let confirmMsg = null;
  window.confirm = (msg) => { confirmMsg = msg; return false; };
  const calls = [];
  window.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return { ok: true, status: 200, json: async () => ({}) }; };

  await window.HirisChatAgents.clearConversation();

  assert.equal(confirmMsg, 'Cancellare la cronologia di questa conversazione?',
    'stesso testo della card Lovelace (hiris-chat-card.js:1222)');
  assert.equal(calls.length, 0, 'con la conferma negata nessuna DELETE deve partire');
  assert.ok(document.querySelector('.msg-row.user'), 'i messaggi non devono sparire se non confermato');
});

test('clearConversation confermata: DELETE parte e i messaggi si svuotano', async () => {
  const { window, document } = setupChat();
  window.HirisChatState.activeAgentId = 'bot-clear-2';
  window.HirisChatMessages.appendMsg('user', 'ciao');
  window.confirm = () => true;
  const calls = [];
  window.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return { ok: true, status: 200, json: async () => ({}) }; };

  await window.HirisChatAgents.clearConversation();

  const del = calls.find((c) => c.opts && c.opts.method === 'DELETE');
  assert.ok(del, 'la DELETE deve partire dopo conferma');
  assert.match(del.url, /api\/chatbots\/bot-clear-2\/chat-history$/);
  assert.equal(document.querySelectorAll('.msg-row.user').length, 0, 'i messaggi devono svuotarsi');
});

test('clearConversation: se la DELETE fallisce lato server, i messaggi NON spariscono e viene avvisato', async () => {
  const { window, document } = setupChat();
  window.HirisChatState.activeAgentId = 'bot-clear-3';
  window.HirisChatMessages.appendMsg('user', 'messaggio importante');
  window.confirm = () => true;
  window.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  await window.HirisChatAgents.clearConversation();

  assert.equal(alerts.length, 1, 'un fallimento non deve restare invisibile');
  assert.match(alerts[0], /[Nn]on è stato possibile cancellare/);
  assert.ok(document.querySelector('.msg-row.user'),
    'la UI non deve fingere di aver cancellato se il server non lo ha fatto');
});

// ---------------------------------------------------------------------------
// Pannello task: carica le card e permette di cancellare una task.
// ---------------------------------------------------------------------------

test('il pannello task carica le card e puo\' cancellare una task pending', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/labels.js', 'chat/state.js', 'chat/tasks.js'],
    { html: fixtureHtml() },
  );
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (opts && opts.method === 'DELETE') {
      return { ok: true, status: 204, json: async () => ({}) };
    }
    return {
      ok: true, status: 200,
      json: async () => ([{ id: 't1', label: 'Irrigazione giardino', status: 'pending', trigger: { type: 'delay', minutes: 5 } }]),
    };
  };
  window.confirm = () => true;

  await window.HirisChatTasks.load();

  const card = document.querySelector('#task-active-list .task-card');
  assert.ok(card, 'la card della task pending deve comparire in task-active-list');
  const cancelBtn = document.querySelector('.task-cancel-btn');
  assert.ok(cancelBtn, 'una task pending deve avere il bottone Annulla');
  assert.equal(cancelBtn.dataset.taskId, 't1');

  // Wire della delegazione click (init()) senza lasciare un vero
  // setInterval(30s) attivo nel processo di test -- lo stub-e-ripristina
  // qui sotto è lo stesso principio del teardown in helpers/dom.mjs: non
  // lasciare side-effect fuori dallo scope del singolo test().
  const realSetInterval = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatTasks.init();
  globalThis.setInterval = realSetInterval;
  await tick(10); // lascia assestare il load() interno di init()

  const callsBeforeCancel = calls.length;
  document.querySelector('.task-cancel-btn').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(10);

  const deleteCall = calls.slice(callsBeforeCancel).find((c) => c.opts.method === 'DELETE');
  assert.ok(deleteCall, 'annullare la task deve fare una DELETE');
  assert.match(deleteCall.url, /api\/tasks\/t1$/);
  assert.equal(deleteCall.opts.headers['X-Requested-With'], 'fetch');
});

// ---------------------------------------------------------------------------
// M-6 (review indipendente su bee3ab1, fratello di A7 nella stessa pagina):
// una DELETE fallita non produceva NIENTE -- ne' un alert ne' un log.
// ---------------------------------------------------------------------------

test('annullare una task: una DELETE fallita lo dice, non resta muta (M-6)', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/labels.js', 'chat/state.js', 'chat/tasks.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async (url, opts) => {
    if (opts && opts.method === 'DELETE') {
      return { ok: false, status: 500, json: async () => ({}) };
    }
    return {
      ok: true, status: 200,
      json: async () => ([{ id: 't1', label: 'Irrigazione giardino', status: 'pending', trigger: { type: 'delay', minutes: 5 } }]),
    };
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  await window.HirisChatTasks.load();
  await window.HirisChatTasks.cancel('t1');

  assert.equal(alerts.length, 1, 'una DELETE fallita deve produrre un alert, non silenzio');
  assert.match(alerts[0], /[Nn]on è stato possibile annullare/);
});
