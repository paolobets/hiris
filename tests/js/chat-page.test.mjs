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
        <button id="cancella-conv-btn"></button>
        <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
        <div id="turn-counter" style="display:none"></div>
        <div id="session-ended-msg" style="display:none"></div>
      </main>
    </div>
  </body>`;
}

/* `t` non e' decorativo: l'indicatore d'attesa programma dei timer che
   arrivano fino a 4 minuti e mezzo (chat/messages.js, SOGLIE_ATTESA), e un
   turno che nel test non si conclude li lascia pendenti. Sono timer di jsdom,
   cioe' timer di Node: tengono vivo l'event loop e il file di test non
   terminerebbe finche' non scadono tutti. Chiudere la finestra a fine test li
   spegne tutti insieme. */
function setupChat(t) {
  const ctx = loadScripts(
    ['config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js', 'chat/send.js'],
    { html: fixtureHtml() },
  );
  if (t) t.after(() => {
    /* `fermaTutteLeAttese()` PRIMA di chiudere: i timer dell'indicatore
       nascono da un `setTimeout` non qualificato, che in questo harness e'
       quello di Node e non quello di jsdom -- `window.close()` da solo non li
       spegne. Senza questa riga, un test che fallisce a meta' turno lascia
       pendenti fino a 4 minuti e mezzo di timer e il file di test non
       termina. */
    ctx.window.HirisChatMessages.fermaTutteLeAttese();
    ctx.dom.window.close();
  });
  return ctx;
}

// ---------------------------------------------------------------------------
// Invio messaggio -> POST api/chat con chatbot_id + X-Requested-With
// ---------------------------------------------------------------------------

test('inviare un messaggio fa POST a api/chat con X-Requested-With (niente più chatbot_id, Task 3)', async (t) => {
  const { window } = setupChat(t);
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

test('risposta 202 pending: il polling completa e la risposta finale viene renderizzata', async (t) => {
  const { window, document } = setupChat(t);
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

  // Bolla "in elaborazione" inserita subito, prima del poll. Il cronometro NO:
  // compare solo dopo dieci secondi (chat/messages.js, SOGLIE_ATTESA.timer), e
  // ha un test suo qui sotto.
  const think = document.querySelector('.msg-row.assistant .bubble.thinking-live');
  assert.ok(think, 'la bolla "in elaborazione" deve comparire subito');
  assert.match(think.textContent, /elaborando/i);
  assert.equal(think.querySelector('.thinking-timer'), null,
    'nei primi secondi niente cronometro: non c\'e\' ancora niente da cronometrare');

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

test('via ponte (202): gli strumenti usati compaiono anche sul ramo del polling', async (t) => {
  const { window, document } = setupChat(t);
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

test('via ponte (202): senza strumenti non compare nessuna riga vuota', async (t) => {
  const { window, document } = setupChat(t);
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

test('restore() ricarica la history salvata della conversazione', async (t) => {
  const { window, document } = setupChat(t);
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
// L'attesa. C'erano DUE indicatori -- `showTyping` (prompt di terminale con
// barrette monospace, ramo diretto) e `showThinking` (logo + scritta, ramo via
// abbonamento) -- e quale ne vedessi dipendeva da come il server aveva smaltito
// il turno. Il test di `showTyping` non e' stato adattato: e' stato cancellato,
// perche' quel comportamento non esiste piu'. Ne resta uno solo, per tutti i
// modelli e tutti i percorsi.
// ---------------------------------------------------------------------------

test('l\'indicatore d\'attesa e\' uno solo: logo, scritta di marca e una regione live', (t) => {
  const { window, document } = setupChat(t);
  const row = window.HirisChatMessages.showThinking();

  assert.ok(row.querySelector('.avatar.thinking-logo'), 'il logo HIRIS che pulsa');
  assert.equal(row.querySelector('.avatar').getAttribute('aria-hidden'), 'true',
    'il logo e\' decorazione: uno screen reader non deve leggerlo');
  const bolla = row.querySelector('.bubble.thinking-live');
  assert.ok(bolla, 'la bolla in elaborazione');
  assert.equal(bolla.getAttribute('role'), 'status',
    'senza regione live chi usa uno screen reader non sa nemmeno che il messaggio e\' partito');
  assert.equal(bolla.getAttribute('aria-live'), 'polite');
  assert.match(bolla.textContent, /HIRIS sta elaborando/);
  assert.equal(document.querySelector('.thinking-code'), null,
    'l\'estetica "stile code" e\' uscita: non deve poter ricomparire da nessun ramo');

  window.HirisChatMessages.fermaTutteLeAttese();
});

test('il cronometro non c\'e\' nei primi secondi, e compare quando l\'attesa si allunga', async (t) => {
  const { window } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.timer;
  soglie.timer = 5000; // la soglia vera e' 10 s: qui interessa il PRIMA/DOPO
  try {
    const row = window.HirisChatMessages.showThinking();
    assert.equal(row.querySelector('.thinking-timer'), null,
      'sotto la soglia il tempo non e\' informazione: e\' una risposta rapida cronometrata');
    /* E non basta che manchi nell'istante zero: deve mancare ANCHE dopo che
       l'event loop ha girato piu' volte. Senza questa seconda attesa, un
       cronometro programmato con ritardo nullo -- il difetto di prima,
       travestito -- passerebbe il controllo qui sopra. */
    await tick(200);
    assert.equal(row.querySelector('.thinking-timer'), null,
      'e non deve comparire al primo giro dell\'event loop');
    window.HirisChatMessages.fermaTutteLeAttese();

    soglie.timer = 40;
    const row2 = window.HirisChatMessages.showThinking();
    await tick(200);

    const timer = row2.querySelector('.thinking-timer');
    assert.ok(timer, 'passata la soglia il cronometro compare');
    assert.match(timer.textContent, /^\d+:\d\d$/, 'nel formato m:ss');
    assert.equal(timer.getAttribute('aria-hidden'), 'true',
      'un m:ss dentro una regione live verrebbe letto ogni secondo');
    window.HirisChatMessages.fermaTutteLeAttese();
  } finally {
    soglie.timer = originale;
  }
});

test('updateBubble ferma il cronometro e scrive la risposta nella stessa bolla', async (t) => {
  const { window } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.timer;
  soglie.timer = 20;
  try {
    const row = window.HirisChatMessages.showThinking();
    await tick(80);
    const testoPrima = row.querySelector('.thinking-timer').textContent;

    window.HirisChatMessages.updateBubble(row, 'Ecco la risposta');
    assert.equal(row._attesa, null, 'updateBubble ferma tutto: cronometro e cambi d\'etichetta');
    assert.match(row.querySelector('.bubble').textContent, /Ecco la risposta/);
    assert.equal(row.querySelector('.bubble').classList.contains('thinking-live'), false,
      'la bolla non e\' piu\' in stato "in elaborazione"');
    assert.equal(row.querySelector('.thinking-timer'), null, 'il cronometro sparisce con l\'attesa');

    await tick(80);
    assert.equal(testoPrima, testoPrima, 'nessun intervallo sopravvive alla risposta');
    assert.equal(row.querySelector('.thinking-timer'), null,
      'e non ne ricompare uno scrivendo su un nodo che non c\'e\' piu\'');
  } finally {
    soglie.timer = originale;
  }
});

test('la risposta arriva anche se la riga e\' stata staccata dal DOM mentre HIRIS elaborava', (t) => {
  const { window, document } = setupChat(t);
  const row = window.HirisChatMessages.showThinking();
  row.parentNode.removeChild(row); // e' quel che faceva il bottone di cancellazione

  window.HirisChatMessages.updateBubble(row, 'Risposta pagata in token');

  assert.ok(row.parentNode, 'la riga deve tornare in conversazione, non restare nel vuoto');
  assert.match(document.getElementById('messages').textContent, /Risposta pagata in token/,
    'una risposta gia\' pagata non puo\' sparire senza che nessuno lo dica');
});

test('durante la risposta via abbonamento (202) l\'input resta bloccato e un secondo invio non parte', async (t) => {
  const { window, document } = setupChat(t);
  const state = window.HirisChatState;
  window.fetch = async (url) => {
    const u = String(url);
    if (u.endsWith('api/chat')) return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'j1' }) };
    if (u.includes('api/chat/reply/')) return { ok: true, status: 200, json: async () => ({ status: 'done', reply: 'fatto' }) };
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await window.HirisChatSend.send('ciao');
  assert.equal(state.isLoading, true, 'lock attivo durante il poll');
  /* `readOnly` e NON `disabled`: un controllo disabilitato perde il fuoco, e su
     un tablet questo chiude la tastiera di sistema e fa saltare l'altezza della
     pagina a ogni invio (chat/keyboard.js reagisce al viewport). Il secondo
     invio lo ferma `state.isLoading`, non l'attributo. */
  assert.equal(state.els.input.readOnly, true, 'textarea in sola lettura mentre elabora');
  assert.equal(state.els.input.disabled, false, 'ma non disabilitata: perderebbe il fuoco');
  assert.match(state.els.input.placeholder, /sta rispondendo/,
    'il campo dice PERCHE\' non si puo\' scrivere, invece di restare muto');
  assert.equal(document.getElementById('cancella-conv-btn').disabled, true,
    'cancellare la conversazione mentre HIRIS elabora faceva sparire la risposta');

  const before = state.els.messages.querySelectorAll('.msg-row.user').length;
  await window.HirisChatSend.send('secondo messaggio');
  const after = state.els.messages.querySelectorAll('.msg-row.user').length;
  assert.equal(after, before, 'un secondo messaggio non deve partire mentre HIRIS elabora');

  await tick(3700); // il poll completa -> sblocco
  assert.equal(state.isLoading, false, 'sbloccato a fine poll');
  assert.equal(state.els.input.readOnly, false, 'textarea riscrivibile dopo la risposta');
  assert.equal(document.getElementById('cancella-conv-btn').disabled, false,
    'e il bottone torna premibile');
});

// ---------------------------------------------------------------------------
// C1 -- il composer. L'euristica sull'a-capo esiste per UNA ragione: certe
// tastiere di sistema inseriscono un a-capo nel testo invece di emettere un
// keydown con Invio. Reagiva pero' a QUALUNQUE a-capo comparso nel campo:
// Maiusc+Invio (l'unico gesto di composizione che esiste in una chat) e un
// incolla di due righe facevano partire il messaggio da soli, e le righe
// venivano saldate senza spazio -- "riga uno\nriga due" -> "riga unoriga due".
// I tre test sotto sono una terna: i primi due pretendono che NON parta, il
// terzo che il caso per cui l'euristica e' nata continui a funzionare. Senza
// il terzo, "non inviare mai" passerebbe i primi due.
// ---------------------------------------------------------------------------

function componiComposer(window, document, testo, evento) {
  window.HirisChatSend.wireComposer();
  const input = document.getElementById('input');
  input.value = testo;
  input.dispatchEvent(evento);
}

test('Maiusc+Invio va a capo e NON invia', (t) => {
  const { window, document } = setupChat(t);
  const inviati = [];
  window.fetch = async (url, opts) => {
    inviati.push(String(url));
    return { ok: true, status: 200, json: async () => ({ response: 'ok' }) };
  };
  window.HirisChatSend.wireComposer();
  const input = document.getElementById('input');

  input.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }));
  input.value = 'riga uno\n';
  input.dispatchEvent(new window.InputEvent('input', { inputType: 'insertLineBreak', bubbles: true }));

  assert.equal(inviati.filter((u) => u.endsWith('api/chat')).length, 0,
    'Maiusc+Invio significa "vado a capo", non "manda"');
  assert.equal(input.value, 'riga uno\n', 'e l\'a-capo appena scritto deve restare nel campo');
});

test('incollare due righe non invia, e non salda le parole', async (t) => {
  const { window, document } = setupChat(t);
  const inviati = [];
  window.fetch = async (url) => { inviati.push(String(url)); return { ok: true, status: 200, json: async () => ({ response: 'ok' }) }; };

  componiComposer(window, document, 'riga uno\nriga due',
    new window.InputEvent('input', { inputType: 'insertFromPaste', bubbles: true }));

  assert.equal(inviati.filter((u) => u.endsWith('api/chat')).length, 0,
    'un incolla non e\' un invio');
  assert.equal(document.getElementById('input').value, 'riga uno\nriga due',
    'il testo incollato resta come l\'utente lo vede, a-capo compreso');
});

test('la tastiera che inserisce un a-capo invece di premere Invio invia ancora, unendo con uno spazio', async (t) => {
  const { window, document } = setupChat(t);
  const corpi = [];
  window.fetch = async (url, opts) => {
    if (String(url).endsWith('api/chat') && opts && opts.body) corpi.push(JSON.parse(opts.body));
    return { ok: true, status: 200, json: async () => ({ response: 'ok' }) };
  };

  componiComposer(window, document, 'riga uno\nriga due',
    new window.InputEvent('input', { inputType: 'insertLineBreak', bubbles: true }));
  await tick(20);

  assert.equal(corpi.length, 1, 'e\' il caso per cui questa euristica esiste: deve inviare');
  assert.equal(corpi[0].message, 'riga uno riga due',
    'le righe si uniscono con uno SPAZIO: cancellare l\'a-capo saldava le parole');
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

test('turn-limit raggiunto disabilita input e send-btn (blocca l\'invio)', (t) => {
  const { window, document } = setupChat(t);
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

test('clearConversation chiede conferma prima di cancellare', async (t) => {
  const { window, document } = setupChat(t);
  window.HirisChatMessages.appendMsg('user', 'ciao');
  document.getElementById('welcome').style.display = 'none';

  let confirmMsg = null;
  window.confirm = (msg) => { confirmMsg = msg; return false; };
  const calls = [];
  window.fetch = async (url, opts) => { calls.push({ url: String(url), opts }); return { ok: true, status: 200, json: async () => ({}) }; };

  await window.HirisChatAgents.clearConversation();

  /* Il vecchio testo -- «Cancellare la cronologia di questa conversazione?»
     -- sottodichiarava due volte: non diceva quanto si perde e diceva
     «questa» mentre `chat_store.clear()` svuota `chat_messages` E
     `chat_sessions`, cioe' porta via anche i riassunti delle conversazioni
     chiuse che finiscono nel prompt. La conferma adesso cita l'oggetto, come
     gia' fa la pagina Memoria. */
  assert.match(confirmMsg, /Perdi il messaggio che vedi/,
    'la conferma deve dire QUANTO si perde');
  assert.match(confirmMsg, /riassunti delle conversazioni precedenti/,
    'e che non si perde soltanto quel che si vede');
  assert.equal(calls.length, 0, 'con la conferma negata nessuna DELETE deve partire');
  assert.ok(document.querySelector('.msg-row.user'), 'i messaggi non devono sparire se non confermato');
});

test('clearConversation confermata: DELETE parte e i messaggi si svuotano', async (t) => {
  const { window, document } = setupChat(t);
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

test('clearConversation: se la DELETE fallisce lato server, i messaggi NON spariscono e viene avvisato', async (t) => {
  const { window, document } = setupChat(t);
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
