import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 8: rebuild della pagina chat standalone (static/index.html).
   Il JS inline (~610 righe) è stato estratto in static/chat/*.js, uno per
   blocco funzionale (state/messages/agents/send/theme/sidebar/keyboard/
   main) -- vedi task-8-report.md per il dettaglio dello split. L'onboarding
   che faceva parte di quell'elenco è uscito con la fetta E5 Task 1 (C1: il
   primo gesto del primo utilizzo dava un errore). Questi sono i test
   comportamentali richiesti dal piano (tabella "Test comportamentali
   richiesti per task", riga 8): invio -> POST api/chat, risposta 202
   -> il polling completa, turn-limit blocca l'invio. I due casi sul pannello
   Task sono usciti con la fetta E5 Task 6, insieme a chat/tasks.js e alla
   rotta /api/tasks che serviva. La fetta E5 Task 3 ("via l'elenco dei bot dalla sidebar") ha
   tolto `chatbot_id` dal body -- un solo assistente non ha più bisogno di
   dirsi quale -- e sostituito le mappe `agentMaxTurns`/`agentTurnCounts`
   indicizzate per id con `state.maxChatTurns`/`state.turnCount`, valori
   singoli per l'unica conversazione.

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

test('inviare un messaggio fa POST a api/chat con X-Requested-With (niente più chatbot_id, Task 3)', async () => {
  const { window } = setupChat();
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
  assert.equal(body.message, 'ciao HIRIS');
  assert.equal('chatbot_id' in body, false, 'un solo assistente non ha piu\' bisogno di dirsi quale');
});

// ---------------------------------------------------------------------------
// Risposta 202 (chat via abbonamento) -> il polling completa e la risposta
// viene renderizzata nella bolla placeholder.
// ---------------------------------------------------------------------------

test('risposta 202 pending: il polling completa e la risposta finale viene renderizzata', async () => {
  const { window, document } = setupChat();
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

  // Il polling usa un vero setTimeout(3.5s) -- nessun mock dei timer, per
  // restare fedeli al comportamento reale invece di far avanzare a mano
  // una catena di await fragile. Il test è quindi ~3.5s più lento.
  await tick(3700);

  const finalBubbles = document.querySelectorAll('.msg-row.assistant .bubble');
  assert.equal(finalBubbles[finalBubbles.length - 1].textContent, 'Risposta via abbonamento');
});

// ---------------------------------------------------------------------------
// Review totale della fetta E5: sul ramo del ponte (202 -> job_id) gli strumenti
// usati NON comparivano. Il backend li manda anche li' (handlers_chat.py:352) e
// il ramo sincrono li rende da sempre: era l'osservabilita' promessa che mancava
// PROPRIO sul percorso che la produce -- cioe' quello di un tester UAT con
// l'abbonamento. I due test sotto sono una coppia: il primo pretende che
// compaiano quando ci sono, il secondo che NON si inventi una riga vuota quando
// non ci sono (senza il secondo, "mostra sempre una riga" passerebbe il primo).
// ---------------------------------------------------------------------------

function fetchPonte(replyPayload) {
  return async (url) => {
    const u = String(url);
    if (u.endsWith('api/chat')) {
      return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'job-1' }) };
    }
    if (u.includes('api/chat/reply/')) {
      return { ok: true, status: 200, json: async () => replyPayload };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };
}

test('via ponte (202): gli strumenti usati compaiono anche sul ramo del polling', async () => {
  const { window, document } = setupChat();
  window.fetch = fetchPonte({
    status: 'done',
    reply: 'Ho annotato.',
    debug: { tools_called: [{ tool: 'ricorda', input: { frase: 'la caldaia perde' } }] },
  });

  await window.HirisChatSend.send('ricordati che la caldaia perde');
  await tick(3700);

  const chips = document.querySelectorAll('.debug-row .tool-chip .tc-name');
  assert.equal(chips.length, 1, 'la riga degli strumenti deve comparire sul ramo del ponte');
  assert.equal(chips[0].textContent, 'ricorda');
});

test('via ponte (202): senza strumenti non compare nessuna riga vuota', async () => {
  const { window, document } = setupChat();
  window.fetch = fetchPonte({ status: 'done', reply: 'Le luci accese sono due.' });

  await window.HirisChatSend.send('quante luci accese?');
  await tick(3700);

  assert.equal(document.querySelectorAll('.debug-row').length, 0,
    'nessun strumento usato -> nessuna riga strumenti');
});

// ---------------------------------------------------------------------------
// Persistenza chat (bug live-verify #3): tornando alla chat da config (reload
// pieno) la conversazione spariva perche' la history non veniva MAI
// ricaricata al boot. restore() la ricarica.
// Task 3 ("via l'elenco dei bot"): non esiste piu' un "agente attivo" da
// scegliere -- c'e' una sola conversazione. Task 4 ("nasce la rotta
// onesta"): la cronologia vive su `GET/DELETE api/chat/cronologia`, senza
// piu' nessun id di bot nel percorso (prima era una chiave fissa,
// 'hiris-default', dentro `/api/chatbots/{id}/chat-history` -- un
// placeholder mai letto dal server).
// ---------------------------------------------------------------------------

test('restore() ricarica la history salvata della conversazione', async () => {
  const { window, document } = setupChat();
  const seen = [];
  window.fetch = async (url) => {
    seen.push(String(url));
    if (String(url).includes('/cronologia')) {
      return { ok: true, status: 200, json: async () => ({ messages: [
        { role: 'user', content: 'ciao' },
        { role: 'assistant', content: 'risposta salvata' },
      ] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatAgents.restore();

  assert.ok(seen.some((u) => /api\/chat\/cronologia/.test(u)),
    'restore deve fetchare la history della conversazione');
  const bubbles = document.querySelectorAll('.msg-row .bubble');
  assert.ok(bubbles.length >= 2, 'i messaggi salvati devono ricomparire');
  assert.equal(document.getElementById('welcome').style.display, 'none',
    'il welcome si nasconde quando c\'e\' history');
  assert.equal(window.HirisChatState.turnCount, 1,
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
  state.maxChatTurns = 2;
  state.turnCount = 2;

  window.HirisChatAgents.checkTurnLimit();

  assert.equal(state.els.input.disabled, true);
  assert.equal(state.els.sendBtn.disabled, true);
  assert.equal(document.getElementById('session-ended-msg').style.display, '');

  // Sotto al limite: i controlli tornano utilizzabili.
  state.turnCount = 1;
  window.HirisChatAgents.checkTurnLimit();
  assert.equal(state.els.input.disabled, false);
  assert.equal(state.els.sendBtn.disabled, false);
});

// ---------------------------------------------------------------------------
// Sprint coerenza, lotto A, task 5 (A7): cancellare la cronologia era
// irreversibile e senza conferma. Il testo della conferma fu preso dalla card
// Lovelace, che per la stessa azione la chiedeva; la card e' uscita col Task 5
// della E5, la conferma resta perche' e' il comportamento giusto.
// Fratello nello stesso file: il fetch DELETE aveva un catch(e) {} vuoto --
// se il server falliva, la UI cancellava comunque i messaggi mostrati,
// dicendo "fatto" quando non lo era.
// ---------------------------------------------------------------------------

test('clearConversation chiede conferma prima di cancellare', async () => {
  const { window, document } = setupChat();
  window.HirisChatMessages.appendMsg('user', 'ciao');
  document.getElementById('welcome').style.display = 'none';

  let confirmMsg = null;
  window.confirm = (msg) => { confirmMsg = msg; return false; };
  const calls = [];
  window.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return { ok: true, status: 200, json: async () => ({}) }; };

  await window.HirisChatAgents.clearConversation();

  assert.equal(confirmMsg, 'Cancellare la cronologia di questa conversazione?',
    'il testo della conferma non deve cambiare sotto i piedi di chi la legge');
  assert.equal(calls.length, 0, 'con la conferma negata nessuna DELETE deve partire');
  assert.ok(document.querySelector('.msg-row.user'), 'i messaggi non devono sparire se non confermato');
});

test('clearConversation confermata: DELETE parte e i messaggi si svuotano', async () => {
  const { window, document } = setupChat();
  window.HirisChatMessages.appendMsg('user', 'ciao');
  window.confirm = () => true;
  const calls = [];
  window.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return { ok: true, status: 200, json: async () => ({}) }; };

  await window.HirisChatAgents.clearConversation();

  const del = calls.find((c) => c.opts && c.opts.method === 'DELETE');
  assert.ok(del, 'la DELETE deve partire dopo conferma');
  assert.match(del.url, /api\/chat\/cronologia$/);
  assert.equal(document.querySelectorAll('.msg-row.user').length, 0, 'i messaggi devono svuotarsi');
});

test('clearConversation: se la DELETE fallisce lato server, i messaggi NON spariscono e viene avvisato', async () => {
  const { window, document } = setupChat();
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
