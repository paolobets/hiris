import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, staticSnapshotDir } from './helpers/dom.mjs';

/* Il cassetto della barra laterale (static/chat/sidebar.js). Pinnato PRIMA
   della fetta «il seguito delle chat divise» (spec 2026-09-26 §4), che mette
   nella barra le voci delle conversazioni e chiede che il tocco su una voce
   chiuda il cassetto come gia' fa con Impegni/Proposte. */

function fixtureDrawer() {
  return `<!doctype html><body>
    <div id="sidebar-overlay" style="display:none"></div>
    <aside id="sidebar">
      <div id="sidebar-nav"><a href="#x" class="sb-nav-item" id="voce">Impegni</a></div>
    </aside>
    <button id="menu-btn" aria-expanded="false"></button>
  </body>`;
}

function avviaCassetto(t, stretto) {
  const ctx = loadScripts(['chat/sidebar.js'], { html: fixtureDrawer() });
  ctx.window.matchMedia = () => ({ matches: stretto });
  ctx.window.HirisChatSidebar.init();
  if (t) t.after(() => ctx.dom.window.close());
  return ctx;
}

test('telefono: il tocco su una voce chiude il cassetto aperto', (t) => {
  const { window, document } = avviaCassetto(t, true);
  window.HirisChatSidebar.toggle(true);
  assert.equal(document.getElementById('sidebar').classList.contains('open'), true);

  document.getElementById('voce').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  assert.equal(document.getElementById('sidebar').classList.contains('open'), false);
  assert.equal(document.getElementById('sidebar-overlay').style.display, 'none');
  assert.equal(document.getElementById('menu-btn').getAttribute('aria-expanded'), 'false');
});

test('fra 721 e 768 px il pannello e\' ancora un cassetto: il tocco lo chiude', (t) => {
  /* Il foglio fa del pannello un cassetto fino a 768 px (hiris-chat.css);
     sidebar.js chiedeva `max-width: 720px`, e l'iPad in verticale restava
     col cassetto aperto sopra la conversazione appena scelta. Qui
     `matchMedia` risponde «no» come per quella larghezza. */
  const { window, document } = avviaCassetto(t, false);
  window.HirisChatSidebar.toggle(true);

  document.getElementById('voce').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));

  assert.equal(document.getElementById('sidebar').classList.contains('open'), false);
});

test('schermo largo: il tocco su una voce non apre niente', (t) => {
  const { window, document } = avviaCassetto(t, false);
  document.getElementById('voce').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  assert.equal(document.getElementById('sidebar').classList.contains('open'), false);
  assert.equal(document.getElementById('sidebar-overlay').style.display, 'none');
});

/* ── Le conversazioni del filo (spec 2026-09-26 §4, Task 7) ─────────────────

   Il server risponde `GET api/chat/conversations` con `{conversations: [{id,
   titolo, ultimo_messaggio, attiva}]}`; la pagina disegna l'elenco da li', e
   l'id della conversazione aperta lo prende da `attiva` (non lo indovina).
   Ogni prova qui asserisce cio' che si vede nel DOM e le chiamate che partono
   davvero, con la forma esatta (metodo, percorso, intestazione). */

const CONFERMA = 'Perdi i messaggi di questa conversazione e il suo riassunto. '
  + 'Le tue altre conversazioni restano nell\'elenco delle conversazioni.\n'
  + 'I ricordi non si toccano: restano finché non li cancelli tu, uno per uno, dalla pagina Memoria.\n'
  + 'Non si può annullare.\n\nCancellare questa conversazione?';
const VUOTO = 'Le tue conversazioni con HIRIS compariranno qui.';
const LIMITE = 'Hai raggiunto il limite di messaggi per questa conversazione. '
  + 'Avviane una nuova dalla barra laterale.';
const IN_ARRIVO = 'C’è già una risposta in arrivo per questa conversazione.';

function fixtureChat() {
  return `<!doctype html><body>
    <div id="app">
      <div id="sidebar-overlay" style="display:none"></div>
      <aside id="sidebar">
        <div id="sidebar-nav"></div>
        <div id="sidebar-conversations">
          <button type="button" id="new-conv-btn" class="sb-nav-item">Nuova conversazione</button>
          <ul id="conv-list" aria-label="Le tue conversazioni"></ul>
          <p id="conv-empty" hidden></p>
        </div>
        <div id="sidebar-footer"></div>
      </aside>
      <main id="main">
        <header id="header">
          <button id="menu-btn" aria-expanded="false"></button>
          <button id="delete-conv-btn" disabled></button>
          <div id="agent-pill"><span id="ap-avatar"></span><span id="ap-name"></span></div>
          <div id="conn-dot"></div>
        </header>
        <div id="messages">
          <div id="welcome"><span id="welcome-hello">Ciao</span></div>
        </div>
        <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
        <div id="turn-counter" style="display:none"></div>
        <div id="conv-notice" role="status" hidden></div>
        <div id="session-ended-msg" style="display:none"></div>
      </main>
    </div>
  </body>`;
}

const MODULI_CHAT = ['config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js',
  'chat/conversations.js', 'chat/send.js', 'chat/sidebar.js', 'pending-badge.js'];

function risposta(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/* Un server finto con un comportamento per (metodo, percorso). `rotte` e' un
   oggetto `'METODO percorso' -> funzione o corpo`; ogni chiamata si registra
   con percorso, metodo e intestazioni, per asserirne la forma. */
function server(window, rotte) {
  const chiamate = [];
  window.fetch = async (url, opts = {}) => {
    const metodo = opts.method || 'GET';
    const percorso = String(url);
    chiamate.push({ metodo, percorso, headers: opts.headers || {} });
    const voce = rotte[metodo + ' ' + percorso];
    if (voce === undefined) return risposta(200, {});
    return typeof voce === 'function' ? voce() : risposta(200, voce);
  };
  return chiamate;
}

function avviaChat(t) {
  const ctx = loadScripts(MODULI_CHAT, { html: fixtureChat() });
  ctx.window.matchMedia = () => ({ matches: true });
  if (t) t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });
  return ctx;
}

const DUE = [
  { id: 'c2', titolo: 'Accendi la luce della cucina', ultimo_messaggio: '2026-09-26T10:00:00Z', attiva: true },
  { id: 'c1', titolo: 'Che tempo fa domani?', ultimo_messaggio: '2026-09-20T08:00:00Z', attiva: false },
];

test("l'elenco si disegna dalla risposta; la voce attiva ha .active e aria-current, le altre no", async (t) => {
  const { window, document } = avviaChat(t);
  server(window, { 'GET api/chat/conversations': { conversations: DUE } });

  await window.HirisChatConversations.refresh();

  const voci = [...document.querySelectorAll('#conv-list li > button.sb-nav-item')];
  assert.equal(voci.length, 2);
  assert.equal(voci[0].type, 'button');
  assert.equal(voci[0].querySelector('.conv-title').textContent, 'Accendi la luce della cucina');
  assert.equal(voci[1].querySelector('.conv-title').textContent, 'Che tempo fa domani?');
  assert.equal(voci[0].classList.contains('active'), true);
  assert.equal(voci[0].getAttribute('aria-current'), 'true');
  assert.equal(voci[1].classList.contains('active'), false);
  assert.equal(voci[1].hasAttribute('aria-current'), false, 'aria-current solo sulla voce attiva (7.9)');
  assert.equal(voci[0].querySelector('time').getAttribute('datetime'), '2026-09-26T10:00:00Z',
    'la data e\' quella del server, cosi\' com\'e\'');
  assert.equal(document.getElementById('conv-empty').hidden, true);
  assert.equal(window.HirisChatConversations.activeId(), 'c2');
  assert.equal(document.getElementById('delete-conv-btn').disabled, false,
    'c\'e\' una conversazione aperta: il cestino ha qualcosa da cancellare');
});

test('il titolo e\' testo dell\'utente: resta testo, mai markup (7.1)', async (t) => {
  const { window, document } = avviaChat(t);
  const trappola = '<img src=x onerror=alert(1)>';
  server(window, { 'GET api/chat/conversations': { conversations: [
    { id: 'c1', titolo: trappola, ultimo_messaggio: '2026-09-26T10:00:00Z', attiva: true }] } });

  await window.HirisChatConversations.refresh();

  assert.equal(document.querySelector('#conv-list img'), null);
  assert.equal(document.querySelector('#conv-list .conv-title').textContent, trappola);
});

test('la data relativa: oggi, ieri, poi gg-mm; niente data se il server non ne manda una valida', (t) => {
  const { window } = avviaChat(t);
  const giorno = window.HirisChatConversations.relativeDay;
  const adesso = new Date(2026, 8, 26, 9, 30);
  assert.equal(giorno(new Date(2026, 8, 26, 0, 5).toISOString(), adesso), 'oggi');
  assert.equal(giorno(new Date(2026, 8, 25, 23, 50).toISOString(), adesso), 'ieri');
  assert.equal(giorno(new Date(2026, 8, 24, 12, 0).toISOString(), adesso), '24-09');
  assert.equal(giorno(new Date(2026, 0, 3, 12, 0).toISOString(), adesso), '03-01');
  assert.equal(giorno('', adesso), '');
  assert.equal(giorno('non-una-data', adesso), '');
});

test('elenco vuoto: il testo di spec §4, e il cestino non ha niente da cancellare', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, { 'GET api/chat/conversations': { conversations: [] } });

  await window.HirisChatConversations.refresh();

  const vuoto = document.getElementById('conv-empty');
  assert.equal(vuoto.hidden, false);
  assert.equal(vuoto.textContent, VUOTO);
  assert.equal(document.querySelectorAll('#conv-list li').length, 0);
  const cestino = document.getElementById('delete-conv-btn');
  assert.equal(cestino.disabled, true);
  assert.match(cestino.getAttribute('aria-label') || '', /nessuna conversazione aperta/i,
    'spento, e dice perche\' a chi non lo vede spento');
});

test('dopo «Nuova conversazione» nessuna voce e\' attiva: il cestino si spegne (extra 7)', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, { 'GET api/chat/conversations': { conversations: [{ ...DUE[1] }] } });

  await window.HirisChatConversations.refresh();

  assert.equal(window.HirisChatConversations.activeId(), null);
  assert.equal(document.querySelector('#conv-list [aria-current]'), null);
  assert.equal(document.getElementById('delete-conv-btn').disabled, true);

  const domande = [];
  window.confirm = (m) => { domande.push(m); return true; };
  const chiamate = server(window, {});
  await window.HirisChatAgents.clearConversation();
  assert.equal(domande.length, 0, 'niente da cancellare: nessuna domanda');
  assert.equal(chiamate.length, 0, 'e nessuna chiamata');
});

test('«Nuova conversazione» fa la POST, svuota la vista, rilegge storia ed elenco, e il fuoco va a #input', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, {
    'POST api/chat/conversations': { ok: true },
    'GET api/chat/history': { messages: [] },
    'GET api/chat/conversations': { conversations: [{ ...DUE[0], attiva: false }] },
  });
  window.HirisChatSidebar.init();
  await window.HirisChatConversations.init();
  window.HirisChatMessages.appendMsg('user', 'messaggio della conversazione di prima');
  window.HirisChatState.turnCount = 1;

  document.getElementById('new-conv-btn').click();
  await window.HirisChatConversations.idle();

  const post = chiamate.find((c) => c.metodo === 'POST');
  assert.ok(post, 'la POST deve partire');
  assert.equal(post.percorso, 'api/chat/conversations');
  assert.equal(post.headers['X-Requested-With'], 'fetch', '7.2');
  assert.equal(document.querySelectorAll('.msg-row').length, 0, 'la vista e\' vuota');
  assert.notEqual(document.getElementById('welcome').style.display, 'none');
  assert.equal(window.HirisChatState.turnCount, 0);
  const dopo = chiamate.slice(chiamate.indexOf(post) + 1).map((c) => c.metodo + ' ' + c.percorso);
  assert.deepEqual(dopo, ['GET api/chat/history', 'GET api/chat/conversations']);
  assert.equal(document.activeElement, document.getElementById('input'));
});

test('toccare una voce: resume, storia ricaricata senza parametri, fuoco a #input, cassetto chiuso', async (t) => {
  const { window, document } = avviaChat(t);
  window.HirisChatSidebar.init();
  const chiamate = server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'POST api/chat/conversations/c1/resume': { ok: true },
    'GET api/chat/history': { messages: [
      { role: 'user', content: 'Che tempo fa domani?', timestamp: '2026-09-20T08:00:00Z' },
      { role: 'assistant', content: 'Sereno.', timestamp: '2026-09-20T08:00:05Z' }] },
  });
  await window.HirisChatConversations.init();
  window.HirisChatMessages.appendMsg('user', 'messaggio della conversazione aperta');
  window.HirisChatSidebar.toggle(true);

  document.querySelectorAll('#conv-list button')[1].click();
  assert.equal(document.getElementById('sidebar').classList.contains('open'), false,
    'su telefono il tocco chiude il cassetto');
  await window.HirisChatConversations.idle();

  const resume = chiamate.find((c) => c.metodo === 'POST');
  assert.equal(resume.percorso, 'api/chat/conversations/c1/resume');
  assert.equal(resume.headers['X-Requested-With'], 'fetch');
  const storia = chiamate.filter((c) => c.percorso.includes('history'));
  assert.deepEqual(storia.map((c) => c.metodo + ' ' + c.percorso), ['GET api/chat/history'], '7.8');
  const bolle = [...document.querySelectorAll('.msg-row .bubble')].map((b) => b.textContent);
  assert.deepEqual(bolle, ['Che tempo fa domani?', 'Sereno.'],
    'la vista mostra la conversazione ripresa, non quella di prima');
  assert.equal(document.activeElement, document.getElementById('input'));
});

test('toccare la voce gia\' attiva non la riprende: porta solo il fuoco a #input', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, { 'GET api/chat/conversations': { conversations: DUE } });
  await window.HirisChatConversations.init();

  document.querySelector('#conv-list button.active').click();
  await window.HirisChatConversations.idle();

  assert.equal(chiamate.filter((c) => c.metodo !== 'GET').length, 0);
  assert.equal(document.activeElement, document.getElementById('input'));
});

test('dopo una ripresa il limite viene dalla storia del server, non da un conteggio nuovo (extra 4)', async (t) => {
  const { window, document } = avviaChat(t);
  window.HirisChatState.maxChatTurns = 2;
  server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'GET api/chat/history': { messages: [
      { role: 'user', content: 'uno' }, { role: 'assistant', content: 'a' },
      { role: 'user', content: 'due' }, { role: 'assistant', content: 'b' }] },
  });
  await window.HirisChatConversations.refresh();

  await window.HirisChatConversations.resume('c1');

  assert.equal(window.HirisChatState.turnCount, 2);
  assert.equal(document.getElementById('input').disabled, true);
  const fine = document.getElementById('session-ended-msg');
  assert.equal(fine.style.display, '');
  assert.equal(fine.textContent, LIMITE, '#session-ended-msg col testo di spec §4');
});

test("l'id va nel percorso codificato e senza barra iniziale (7.3)", async (t) => {
  const { window } = avviaChat(t);
  const chiamate = server(window, {});
  await window.HirisChatConversations.resume('a/b?c#d');
  await window.HirisChatConversations.remove('a/b?c#d');

  const scritture = chiamate.filter((c) => c.metodo !== 'GET');
  assert.deepEqual(scritture.map((c) => c.metodo + ' ' + c.percorso), [
    'POST api/chat/conversations/a%2Fb%3Fc%23d/resume',
    'DELETE api/chat/conversations/a%2Fb%3Fc%23d',
  ]);
  for (const c of chiamate) assert.equal(c.percorso.startsWith('/'), false, c.percorso);
  for (const c of scritture) assert.equal(c.headers['X-Requested-With'], 'fetch');
});

test('409: si mostra il testo del server, la vista resta, nessun nuovo tentativo (7.5)', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'POST api/chat/conversations/c1/resume': () => risposta(409, { error: IN_ARRIVO }),
  });
  await window.HirisChatConversations.refresh();
  window.HirisChatMessages.appendMsg('user', 'resta qui');

  const esito = await window.HirisChatConversations.resume('c1');

  assert.equal(esito, false);
  const avviso = document.getElementById('conv-notice');
  assert.equal(avviso.hidden, false);
  assert.equal(avviso.textContent, IN_ARRIVO);
  assert.equal(document.querySelectorAll('.msg-row.user').length, 1, 'la vista non si tocca');
  assert.equal(chiamate.filter((c) => c.metodo === 'POST').length, 1, 'nessun nuovo tentativo');
  assert.equal(chiamate.filter((c) => c.percorso.includes('history')).length, 0);
});

test("il testo d'errore del server e' testo, non markup", async (t) => {
  const { window, document } = avviaChat(t);
  server(window, {
    'POST api/chat/conversations': () => risposta(409, { error: '<img src=x onerror=alert(1)>' }),
  });
  await window.HirisChatConversations.startNew();
  const avviso = document.getElementById('conv-notice');
  assert.equal(avviso.querySelector('img'), null);
  assert.equal(avviso.textContent, '<img src=x onerror=alert(1)>');
});

test('una conversazione riuscita spegne l\'avviso rimasto da un tentativo fallito', async (t) => {
  const { window, document } = avviaChat(t);
  let occupato = true;
  server(window, {
    'POST api/chat/conversations': () => (occupato ? risposta(409, { error: IN_ARRIVO }) : risposta(200, { ok: true })),
    'GET api/chat/history': { messages: [] },
  });
  await window.HirisChatConversations.startNew();
  assert.equal(document.getElementById('conv-notice').hidden, false);

  occupato = false;
  await window.HirisChatConversations.startNew();
  assert.equal(document.getElementById('conv-notice').hidden, true);
});

test('il cestino chiede la conferma col testo esatto di spec §4 e cancella QUELLA conversazione', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'DELETE api/chat/conversations/c2': { ok: true },
    'GET api/chat/history': { messages: [] },
  });
  await window.HirisChatConversations.refresh();
  window.HirisChatMessages.appendMsg('user', 'da cancellare');
  const domande = [];
  window.confirm = (m) => { domande.push(m); return true; };

  await window.HirisChatAgents.clearConversation();

  assert.deepEqual(domande, [CONFERMA]);
  const del = chiamate.filter((c) => c.metodo === 'DELETE');
  assert.equal(del.length, 1);
  assert.equal(del[0].percorso, 'api/chat/conversations/c2');
  assert.equal(del[0].headers['X-Requested-With'], 'fetch');
  assert.equal(chiamate.some((c) => c.percorso === 'api/chat/history' && c.metodo === 'DELETE'), false,
    'la rotta che cancellava tutta la cronologia non esiste piu\'');
  assert.equal(document.querySelectorAll('.msg-row').length, 0);
});

test('il cestino negato non cancella niente', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, { 'GET api/chat/conversations': { conversations: DUE } });
  await window.HirisChatConversations.refresh();
  window.HirisChatMessages.appendMsg('user', 'resta');
  window.confirm = () => false;

  await window.HirisChatAgents.clearConversation();

  assert.equal(chiamate.filter((c) => c.metodo === 'DELETE').length, 0);
  assert.equal(document.querySelectorAll('.msg-row.user').length, 1);
});

test('il cestino fallito: la vista resta e lo si dice (7.4)', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'DELETE api/chat/conversations/c2': () => risposta(500, {}),
  });
  await window.HirisChatConversations.refresh();
  window.HirisChatMessages.appendMsg('user', 'messaggio importante');
  window.confirm = () => true;

  await window.HirisChatAgents.clearConversation();

  assert.equal(document.querySelectorAll('.msg-row.user').length, 1);
  const avviso = document.getElementById('conv-notice');
  assert.equal(avviso.hidden, false);
  assert.match(avviso.textContent, /Non è stato possibile cancellare/);
});

test('il cestino senza rete: la vista resta e lo si dice', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, { 'GET api/chat/conversations': { conversations: DUE } });
  await window.HirisChatConversations.refresh();
  window.HirisChatMessages.appendMsg('user', 'messaggio importante');
  window.confirm = () => true;
  window.fetch = async () => { throw new Error('rete giu'); };

  await window.HirisChatAgents.clearConversation();

  assert.equal(document.querySelectorAll('.msg-row.user').length, 1);
  assert.equal(document.getElementById('conv-notice').hidden, false);
});

test("finito un turno l'elenco si rilegge: la conversazione nata scrivendo diventa l'attiva (extra 7)", async (t) => {
  const { window, document } = avviaChat(t);
  server(window, {
    'POST api/chat': { response: 'ok' },
    'GET api/chat/conversations': { conversations: [
      { id: 'c3', titolo: 'ciao', ultimo_messaggio: '2026-09-26T10:00:00Z', attiva: true }] },
  });
  assert.equal(window.HirisChatConversations.activeId(), null);

  await window.HirisChatSend.send('ciao');
  await window.HirisChatConversations.idle();

  assert.equal(window.HirisChatConversations.activeId(), 'c3');
  assert.equal(document.getElementById('delete-conv-btn').disabled, false);
});

test('la frase del limite ha una casa sola: la stessa nella riga fissa e nella bolla (7.7)', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, { 'POST api/chat': { error: 'max_turns_reached' } });
  window.HirisChatState.maxChatTurns = 1;
  window.HirisChatState.turnCount = 1;
  window.HirisChatAgents.checkTurnLimit();
  assert.equal(document.getElementById('session-ended-msg').textContent, LIMITE);

  window.HirisChatState.turnCount = 0;
  window.HirisChatAgents.checkTurnLimit();
  await window.HirisChatSend.send('ancora uno');
  const bolle = document.querySelectorAll('.msg-row.assistant .bubble');
  assert.equal(bolle[bolle.length - 1].textContent, LIMITE);
});

/* ── Correzione 1 (review UX e sicurezza del Task 7) ─────────────────────── */

test('dopo una cancellazione riuscita il fuoco va a #input, non al <body>', async (t) => {
  /* Il cestino premuto si spegne (non c'e' piu' una conversazione aperta):
     senza questo il fuoco cadrebbe sul <body> e chi usa la tastiera
     ripartirebbe dall'inizio della pagina. */
  const { window, document } = avviaChat(t);
  server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'DELETE api/chat/conversations/c2': { ok: true },
    'GET api/chat/history': { messages: [] },
  });
  await window.HirisChatConversations.refresh();
  window.confirm = () => true;
  document.getElementById('delete-conv-btn').focus();

  await window.HirisChatAgents.clearConversation();

  assert.equal(document.activeElement, document.getElementById('input'));
});

test('mentre HIRIS risponde «Nuova conversazione» e le voci sono spente; dopo, riaccese', async (t) => {
  const { window, document } = avviaChat(t);
  let rispondi;
  const chiamate = server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'POST api/chat': () => new Promise((r) => { rispondi = () => r(risposta(200, { response: 'ok' })); }),
  });
  await window.HirisChatConversations.refresh();
  const comandi = () => [document.getElementById('new-conv-btn'),
    ...document.querySelectorAll('#conv-list button')];
  assert.ok(comandi().every((b) => !b.disabled), 'precondizione: tutto acceso');

  const invio = window.HirisChatSend.send('ciao');
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(comandi().length, 3);
  assert.ok(comandi().every((b) => b.disabled), 'durante il turno: tutto spento');

  rispondi();
  await invio;
  await window.HirisChatConversations.idle();
  assert.ok(comandi().every((b) => !b.disabled), 'dopo il turno: tutto riacceso');
  assert.equal(chiamate.filter((c) => c.metodo === 'POST' && c.percorso !== 'api/chat').length, 0);
});

test('un doppio tocco su una voce fa partire UNA ripresa sola', async (t) => {
  const { window, document } = avviaChat(t);
  const chiamate = server(window, {
    'GET api/chat/conversations': { conversations: DUE },
    'POST api/chat/conversations/c1/resume': { ok: true },
    'GET api/chat/history': { messages: [] },
  });
  await window.HirisChatConversations.init();

  const voce = document.querySelectorAll('#conv-list button')[1];
  voce.click();
  voce.click();
  await window.HirisChatConversations.idle();

  assert.equal(chiamate.filter((c) => c.metodo === 'POST').length, 1);
});

test('gesto riuscito ma storia non arrivata: lo si dice, niente vista vuota muta', async (t) => {
  const { window, document } = avviaChat(t);
  server(window, {
    'POST api/chat/conversations/c1/resume': { ok: true },
    'GET api/chat/history': () => risposta(500, {}),
    'GET api/chat/conversations': { conversations: DUE },
  });

  const esito = await window.HirisChatConversations.resume('c1');

  assert.equal(esito, true, 'la ripresa e\' avvenuta sul server');
  const avviso = document.getElementById('conv-notice');
  assert.equal(avviso.hidden, false);
  assert.equal(avviso.textContent, window.HirisChatConversations.HISTORY_TEXT);
  assert.match(avviso.textContent, /messaggi/);
});

test('senza rete la frase e\' quella della chat, con una casa sola', async (t) => {
  const { window, document } = avviaChat(t);
  window.fetch = async () => { throw new Error('rete giu'); };
  await window.HirisChatConversations.startNew();
  assert.equal(document.getElementById('conv-notice').textContent,
    window.HirisChatState.NETWORK_ERROR_TEXT);

  await window.HirisChatSend.send('ciao');
  const bolle = document.querySelectorAll('.msg-row.assistant .bubble');
  assert.equal(bolle[bolle.length - 1].textContent, window.HirisChatState.NETWORK_ERROR_TEXT);
  for (const nome of ['chat/send.js', 'chat/conversations.js']) {
    assert.doesNotMatch(sorgente(nome), /Errore di connessione|raggiungere HIRIS/, nome);
  }
});

test('un titolo con caratteri di direzione e invisibili resta testo, e la data accanto non cambia (Low-3)', async (t) => {
  const { window, document } = avviaChat(t);
  const titolo = 'abc' + String.fromCharCode(0x202e) + 'def' + String.fromCharCode(0x200b) + 'ghi';
  server(window, { 'GET api/chat/conversations': { conversations: [
    { id: 'c1', titolo, ultimo_messaggio: '2026-09-20T08:00:00Z', attiva: true }] } });

  await window.HirisChatConversations.refresh();

  assert.equal(document.querySelector('.conv-title').textContent, titolo);
  assert.equal(document.querySelector('.conv-when').textContent,
    window.HirisChatConversations.relativeDay('2026-09-20T08:00:00Z'));
  assert.equal(document.querySelector('.conv-when').parentElement,
    document.querySelector('.conv-title').parentElement, 'fratelli, non l\'uno dentro l\'altro');
  /* Il ribaltamento lo contiene il foglio: `unicode-bidi: isolate` chiude la
     direzione dentro il titolo. jsdom non calcola la resa, si guarda la regola. */
  const css = sorgente('hiris-chat.css').replace(/\/\*[\s\S]*?\*\//g, '');
  assert.match(css, /\.conv-title\s*\{[^}]*unicode-bidi:\s*isolate/);
});

test('il cestino dice la stessa cosa a chi lo legge e a chi ci passa sopra', () => {
  const html = sorgente('index.html');
  const bottone = html.match(/<button id="delete-conv-btn"[^>]*title="([^"]*)"[^>]*>([\s\S]*?)<\/button>/);
  assert.ok(bottone, 'il cestino con un title');
  const visibile = bottone[2].replace(/<svg[\s\S]*?<\/svg>/, '').trim();
  assert.equal(bottone[1], visibile);
});

/* ── Il sorgente: le proprieta' che nessun comportamento mostra ─────────── */

function sorgente(nome) {
  return readFileSync(join(staticSnapshotDir(), nome), 'utf8');
}

test('conversations.js non scrive mai HTML e lo dichiara in testa (7.1)', () => {
  const testo = sorgente('chat/conversations.js');
  assert.doesNotMatch(testo,
    /innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|DOMParser|srcdoc|\beval\(|new Function/);
  assert.match(testo.slice(0, 1500), /Sicurezza: testi via textContent/);
  assert.doesNotMatch(testo, /formatContent/, 'il formattatore dei messaggi non serve ai titoli');
});

test('conversations.js non usa gestori in linea (7.6)', () => {
  const testo = sorgente('chat/conversations.js');
  assert.doesNotMatch(testo, /setAttribute\(\s*['"]on/);
  assert.doesNotMatch(testo, /\.on[a-z]+\s*=/);
});

test('la frase del limite non e\' scritta in index.html: la sua casa e\' una (7.7)', () => {
  const html = sorgente('index.html');
  assert.doesNotMatch(html, /limite di messaggi/);
  assert.doesNotMatch(sorgente('chat/send.js'), /limite di messaggi|Sessione completata/);
});
