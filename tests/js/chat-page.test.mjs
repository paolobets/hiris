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
// I NOMI DEGLI STRUMENTI NON SI SCRIVONO IN CHAT (17 agosto 2026).
//
// Qui c'era la coppia opposta: pretendeva che le targhette comparissero. Erano
// state aggiunte al ramo del ponte l'11 agosto perche' l'osservabilita' di una
// scrittura di `ricorda` mancava proprio sul percorso che la produce.
//
// Il proprietario le ha viste e non le vuole a schermo. L'osservabilita' non si
// perde: si SPOSTA nei log a livello debug, dove il backend adesso scrive gli
// strumenti del turno -- vedi `handlers_chat.py`. Toglierle senza spostarla
// avrebbe distrutto la capacita' per cui erano nate.
//
// I due test restano una coppia, rovesciata: il primo pretende che NON
// compaiano nemmeno quando il payload le porterebbe, il secondo che la risposta
// arrivi comunque intera -- senza il secondo, "non rendere niente" passerebbe
// il primo.
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

test('i nomi degli strumenti non compaiono in chat, nemmeno se il payload li porta', async (t) => {
  /* LA FINTA E' SCOMODA DI PROPOSITO: manda `debug.tools_called` come faceva il
     backend prima di questa fetta. Cosi' il test coglie sia la rimozione della
     resa nel frontend sia un eventuale ritorno del payload dal backend: basta
     che una delle due strade si riapra e questo cade. */
  const { window, document } = setupChat(t);
  window.fetch = fetchPonte({
    status: 'done',
    reply: 'Ho annotato.',
    debug: { tools_called: [{ tool: 'ricorda', input: { frase: 'la caldaia perde' } }] },
  });

  /* Il messaggio dell'utente NON contiene la parola «ricorda»: altrimenti
     l'ultima asserzione la troverebbe nella sua stessa bolla e cadrebbe per la
     ragione sbagliata (ci sono cascato scrivendola). */
  await window.HirisChatSend.send('annota che la caldaia perde');
  await tick(3700);

  assert.equal(document.querySelectorAll('.debug-row').length, 0,
    'nessuna riga di targhette');
  assert.equal(document.querySelectorAll('.tool-chip').length, 0,
    'nessuna targhetta');
  assert.ok(!document.body.innerHTML.includes('ricorda'),
    'il nome dello strumento non deve comparire da nessuna parte nella pagina');
});

test('e la risposta arriva comunque intera', async (t) => {
  /* La meta' che impedisce di passare il test qui sopra non rendendo NIENTE. */
  const { window, document } = setupChat(t);
  window.fetch = fetchPonte({
    status: 'done',
    reply: 'Ho annotato.',
    debug: { tools_called: [{ tool: 'ricorda', input: {} }] },
  });

  await window.HirisChatSend.send('ricordati che la caldaia perde');
  await tick(3700);

  assert.ok(document.body.textContent.includes('Ho annotato.'),
    'la risposta del modello resta a schermo');
});

// ---------------------------------------------------------------------------
// Il ripiego si annuncia (fetta «la catena diventa l'unica verità», Task 14).
// Quando il turno passa dal Piano Claude Max -- a forfait -- a un provider a
// consumo, la risposta lo dice: una riga sotto la bolla, non un avviso
// invadente. La ragione è dei soldi: un ripiego silenzioso dal forfait al
// consumo si scopre a fine mese.
//
// La riga arriva GIÀ SCRITTA dal server (`decisione_modelli.nota_ripiego`):
// qui non si compone niente, e infatti nessuno di questi test conosce una
// parola del prodotto oltre a quella che il finto server ha appena mandato.
// I test sono a COPPIE, come quelli degli strumenti qui sopra: senza il
// secondo di ciascuna, «disegna sempre una riga» passerebbe il primo.
// ---------------------------------------------------------------------------

const NOTA = 'Il Piano Claude Max non ha risposto in tempo: ha risposto OpenRouter, a consumo.';

test('via ponte (202): quando il turno ripiega, la risposta lo dice sotto la bolla', async (t) => {
  const { window, document } = setupChat(t);
  window.fetch = fetchPonte({ status: 'done', reply: 'Le luci accese sono due.', nota: NOTA });

  await window.HirisChatSend.send('quante luci accese?');
  await tick(3700);

  const nota = document.querySelector('.msg-nota');
  assert.ok(nota, 'la nota del ripiego deve comparire');
  assert.match(nota.textContent, /Il Piano Claude Max non ha risposto in tempo/);
  /* Dentro la riga della risposta, e dentro la sua colonna: `.msg-row` è un
     flex ORIZZONTALE (avatar | colonna), quindi un figlio diretto finirebbe
     ACCANTO alla bolla invece che sotto. jsdom non calcola il layout e non se
     ne accorgerebbe mai: qui si pinna la parentela, che è ciò che il layout
     dipende da. */
  const riga = document.querySelector('.msg-row.assistant');
  assert.ok(riga.contains(nota), 'la nota appartiene a QUELLA risposta');
  assert.ok(riga.querySelector('.msg-col').contains(nota),
    'dentro la colonna, sotto la bolla -- non accanto');
  assert.equal(document.querySelectorAll('.debug-row').length, 0,
    'la nota non è una riga di registro: non crea una riga propria');
});

test('via ponte (202): senza nota non compare nessuna riga vuota', async (t) => {
  const { window, document } = setupChat(t);
  window.fetch = fetchPonte({ status: 'done', reply: 'Le luci accese sono due.' });

  await window.HirisChatSend.send('quante luci accese?');
  await tick(3700);

  assert.equal(document.querySelector('.msg-nota'), null,
    'nessun ripiego -> nessuna riga');
});

test('ramo diretto (200): il ripiego a monte si annuncia sotto la bolla', async (t) => {
  const { window, document } = setupChat(t);
  window.fetch = async () => ({
    ok: true, status: 200,
    json: async () => ({ response: 'Le luci accese sono due.', nota: NOTA }),
  });

  await window.HirisChatSend.send('quante luci accese?');

  const nota = document.querySelector('.msg-nota');
  assert.ok(nota, 'anche il ramo sincrono rende la nota: sono due righe gemelle');
  assert.equal(nota.textContent, NOTA);
});

test('ramo diretto (200): senza nota non compare nessuna riga vuota', async (t) => {
  const { window, document } = setupChat(t);
  window.fetch = async () => ({
    ok: true, status: 200, json: async () => ({ response: 'Le luci accese sono due.' }),
  });

  await window.HirisChatSend.send('quante luci accese?');

  assert.equal(document.querySelector('.msg-nota'), null);
});

test('appendNota con una nota vuota non disegna niente', (t) => {
  /* La prova per mutazione lo ha chiesto: togliere `!testo` dalla guardia non
     faceva cadere niente, perché send.js chiama `appendNota` solo dentro un
     `if (data.nota)`. Ma `appendNota` è esportata su `window.HirisChatMessages`
     e la nota è un campo FACOLTATIVO: la stringa vuota è il valore che
     `nota_ripiego` restituisce quando non può parlare (motivo sconosciuto,
     natura sconosciuta), ed è precisamente il caso in cui non si deve vedere
     niente. Una guardia che nessuno prova insegna a fidarsi delle guardie:
     o si toglie, o si prova. */
  const { window, document } = setupChat(t);
  const riga = window.HirisChatMessages.appendMsg('assistant', 'Le luci accese sono due.');
  window.HirisChatMessages.appendNota(riga, '');
  assert.equal(document.querySelector('.msg-nota'), null);
  window.HirisChatMessages.appendNota(riga, 'una nota vera');
  assert.equal(document.querySelectorAll('.msg-nota').length, 1);
});

test('la nota non viene interpretata: è testo, non markup', async (t) => {
  const { window, document } = setupChat(t);
  window.fetch = async () => ({
    ok: true, status: 200,
    json: async () => ({ response: 'ok', nota: '<img src=x onerror=alert(1)>' }),
  });

  await window.HirisChatSend.send('ciao');

  const nota = document.querySelector('.msg-nota');
  assert.equal(nota.querySelector('img'), null,
    'textContent, mai innerHTML: il testo viene dal server');
  assert.equal(nota.textContent, '<img src=x onerror=alert(1)>');
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
    /* Ogni test si porta via i timer che ha acceso, con l\'id che vede lui e
       senza passare dalla funzione di pulizia del prodotto: se un giorno quella
       si rompe, il file deve diventare ROSSO, non piantarsi in silenzio. */
    /* L'id va preso ADESSO, non dentro il gancio: i ganci di `t.after` girano
       nell'ordine in cui sono stati registrati, e quello di `setupChat` viene
       prima -- a quel punto `fermaTutteLeAttese()` ha gia' azzerato `_attesa` e
       il gancio non troverebbe piu' niente da spegnere. E `clearInterval`
       nudo, non `window.clearInterval`: in questo harness il `setInterval`
       nudo di messages.js e' quello di Node, e i due non condividono lo spazio
       degli id. */
    const idCronometro = row2._attesa.intervallo;
    t.after(() => clearInterval(idCronometro));

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
    /* Il nodo del cronometro va tenuto per mano PRIMA della risposta: dopo,
       `updateBubble` riscrive la bolla e quel nodo resta staccato dal
       documento. E\' proprio li che un intervallo sopravvissuto continuerebbe
       a scrivere -- invisibile a chi guarda la pagina, invisibile a
       `row.querySelector`, e visibilissimo qui. Prima questa verifica
       confrontava una variabile con se stessa: non poteva fallire, e infatti
       togliendo il `clearInterval` da messages.js nessuna asserzione cadeva --
       il file di test si limitava a non terminare piu\'. Un blocco muto e\'
       peggio di un rosso. */
    const nodoCronometro = row.querySelector('.thinking-timer');
    const idIntervallo = row._attesa.intervallo;
    /* Se la correzione non c\'e\', questo e\' l\'unico modo di far FALLIRE il
       test invece di piantare il file: l\'intervallo orfano terrebbe vivo
       l\'event loop per sempre. */
    t.after(() => clearInterval(idIntervallo));
    const testoPrima = nodoCronometro.textContent;

    window.HirisChatMessages.updateBubble(row, 'Ecco la risposta');
    assert.equal(row._attesa, null, 'updateBubble ferma tutto: cronometro e cambi d\'etichetta');
    assert.match(row.querySelector('.bubble').textContent, /Ecco la risposta/);
    assert.equal(row.querySelector('.bubble').classList.contains('thinking-live'), false,
      'la bolla non e\' piu\' in stato "in elaborazione"');
    assert.equal(row.querySelector('.thinking-timer'), null, 'il cronometro sparisce con l\'attesa');
    /* La bolla deve restare una regione live ANCORA per un po\': e\' cosi\' che
       la risposta si annuncia da sola. Misurato in Chromium con
       l\'accessibilita\' forzata: togliendo gli attributi dopo un solo giro
       dell\'event loop, al primo fotogramma la bolla era gia\' `generic`, con
       zero proprieta\' live -- cioe\' proprio il silenzio che C6 doveva
       togliere. */
    assert.equal(row.querySelector('.bubble').getAttribute('aria-live'), 'polite',
      'la risposta deve poter essere annunciata: la regione live non muore con lei');
    /* E deve sopravvivere a MOLTO PIU\' di un giro dell\'event loop. Questa
       riga e\' la traduzione in test della misura fatta nel browser: con la
       rimozione rimandata di un solo giro, a cento millisecondi la regione era
       gia\' sparita -- e con lei l\'annuncio. */
    await tick(100);
    assert.equal(row.querySelector('.bubble').getAttribute('aria-live'), 'polite',
      'un solo giro dell\'event loop non basta: Chrome smaltisce le regioni live al fotogramma dopo');

    await tick(1400);
    assert.equal(nodoCronometro.textContent, testoPrima,
      'nessun intervallo sopravvive alla risposta: il cronometro staccato non deve piu\' cambiare');
    assert.equal(row.querySelector('.thinking-timer'), null,
      'e non ne ricompare uno scrivendo su un nodo che non c\'e\' piu\'');
    /* La finestra dell\'annuncio finisce, ma QUANDO lo decide la costante, non
       questo test: l\'attesa qui sotto la insegue. Prima era un `tick` fisso, e
       vietava anche di ALLUNGARE il ritardo -- cioe\' la direzione prudente,
       quella verso cui si andrebbe davanti a un tablet lento e a uno screen
       reader che non parla. Il vincolo utile e\' il minimo (le due asserzioni
       qui sopra), non il massimo. */
    await tick(Math.max(0, soglie.uscitaRegioneLive - 1500) + 300);
    assert.equal(row.querySelector('.bubble').getAttribute('role'), null,
      'passata la finestra dell\'annuncio, la bolla smette di essere una regione live');
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

// ---------------------------------------------------------------------------
// La linea del tempo dell\'attesa, dove le due strade dicono cose diverse.
//
// Non e\' una differenza di stile: e\' verificata sul server. Un turno affidato
// al ponte (HTTP 202) e\' gia\' in cronologia prima di essere accodato
// (`handlers_chat.py`, `_enqueue_chat_job`) e la risposta ci finisce da fuori
// la richiesta (`server.py`, `_submit_chat_reply`): chiudere non perde niente,
// e una scadenza esiste (`CHAT_POLL_MAX_MS`). Un turno servito direttamente
// viene scritto solo alla fine, dentro la stessa richiesta che la pagina
// aspetta, e quella `fetch` non ha nessun timeout: chiudere perde tutto, e una
// resa non arrivera\' mai.
//
// Questi quattro test esistono perche\' senza di loro la decisione piu\'
// discussa del lavoro non era difesa da niente: chi passa di qui la
// uniformerebbe in buona fede, e il prodotto ricomincerebbe a mentire a meta\'
// dei suoi utenti proprio nell\'istante in cui decidono se abbandonare.
// ---------------------------------------------------------------------------

/* `fetch` che non risponde mai: e\' l\'unico modo di tenere viva l\'attesa sul
   percorso diretto, che e\' appunto quello senza scadenza. */
function fetchCheNonTorna() {
  return () => new Promise(() => {});
}

test('a due minuti, sul ponte, l\'attesa dice che si puo\' chiudere la pagina', async (t) => {
  const { window, document } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.servizio;
  soglie.servizio = 60;
  try {
    window.fetch = async (url) => {
      if (String(url).endsWith('api/chat')) {
        return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'j1' }) };
      }
      return { ok: true, status: 200, json: async () => ({ status: 'pending' }) };
    };

    await window.HirisChatSend.send('dimmi tutto della casa');
    await tick(200);

    const servizio = document.querySelector('.tl-servizio');
    assert.ok(servizio, 'passata la soglia, l\'attesa dice che fine fa il turno');
    assert.match(servizio.textContent, /[Pp]uoi anche chiudere/,
      'il turno e\' gia\' sul server: spaventare chi vuole chiudere sarebbe una paura inventata');
    assert.doesNotMatch(servizio.textContent, /si perde/);
  } finally {
    soglie.servizio = originale;
  }
});

test('a due minuti, sul percorso diretto, l\'attesa dice di tenere la pagina aperta', async (t) => {
  const { window, document } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.servizio;
  soglie.servizio = 60;
  try {
    window.fetch = fetchCheNonTorna();
    window.HirisChatSend.send('dimmi tutto della casa'); // non si conclude: e\' il punto
    await tick(200);

    const servizio = document.querySelector('.tl-servizio');
    assert.ok(servizio, 'passata la soglia, l\'attesa dice che fine fa il turno');
    assert.match(servizio.textContent, /si perde/,
      'qui la risposta vive solo dentro questa richiesta: promettere la cronologia sarebbe una bugia');
    assert.doesNotMatch(servizio.textContent, /[Pp]uoi anche chiudere/);
  } finally {
    soglie.servizio = originale;
  }
});

test('l\'attesa annuncia che sta per arrendersi SOLO dove una resa esiste', async (t) => {
  const { window, document } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const margine = soglie.margineResa;
  /* La scadenza vera (`CHAT_POLL_MAX_MS`, 5 minuti) la porta chat/send.js e non
     si tocca: sposto il MARGINE, cosi\' l\'avviso cade poco dopo l\'invio
     passando per la strada vera -- send(), il 202, la consegna della scadenza.
     700 ms e non 80: serve una finestra abbastanza larga da guardarci dentro
     PRIMA che scatti. Verificare solo che l\'avviso compaia lascerebbe passare
     un avviso programmato a zero -- cioe\' l\'utente che preme invio e si sente
     dire «fra poco smetto di aspettare» mentre HIRIS ha appena cominciato. E\'
     la stessa promessa falsa di R1, spostata dal percorso al tempo. */
  soglie.margineResa = 5 * 60 * 1000 - 700;
  try {
    window.fetch = async (url) => {
      if (String(url).endsWith('api/chat')) {
        return { ok: true, status: 202, json: async () => ({ status: 'pending', job_id: 'j1' }) };
      }
      return { ok: true, status: 200, json: async () => ({ status: 'pending' }) };
    };

    await window.HirisChatSend.send('una domanda lunga');

    await tick(250);
    assert.match(document.querySelector('.tl-label').textContent, /sta elaborando/,
      'l\'avviso di resa non deve arrivare all\'inizio: qui HIRIS ha appena cominciato');

    await tick(700);
    assert.match(document.querySelector('.tl-label').textContent, /smetto di aspettare/,
      'ma deve arrivare a ridosso della scadenza vera: il poll si ferma davvero, e annunciarlo prima e\' corretto');
  } finally {
    soglie.margineResa = margine;
  }
});

test('sul percorso diretto non promette nessuna resa, perche\' non ne ha una', async (t) => {
  const { window, document } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.senzaScadenza;
  soglie.senzaScadenza = 80;
  try {
    window.fetch = fetchCheNonTorna();
    window.HirisChatSend.send('una domanda lunga');
    await tick(250);

    const etichetta = document.querySelector('.tl-label').textContent;
    assert.doesNotMatch(etichetta, /smetto di aspettare/,
      'questa fetch non ha ne AbortController ne timeout: la pagina non smette mai, e non deve dire il contrario');
    assert.match(etichetta, /non ho un tempo massimo/,
      'e il silenzio non e\' la risposta: lo dichiara');
  } finally {
    soglie.senzaScadenza = originale;
  }
});

test('svuotare la conversazione ferma i cronometri delle attese che ci vivevano dentro', async (t) => {
  const { window } = setupChat(t);
  const soglie = window.HirisChatMessages.SOGLIE_ATTESA;
  const originale = soglie.timer;
  soglie.timer = 20;
  try {
    const row = window.HirisChatMessages.showThinking();
    await tick(80);
    const idIntervallo = row._attesa.intervallo;
    assert.ok(idIntervallo, 'il cronometro sta girando');
    /* Come nel test dell\'intervallo: senza questo, se la correzione manca il
       file non fallisce, si pianta. */
    t.after(() => clearInterval(idIntervallo));

    window.confirm = () => true;
    window.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
    await window.HirisChatAgents.clearConversation();

    assert.equal(row._attesa, null,
      'le righe se ne vanno, i loro cronometri devono andarsene con loro');
  } finally {
    soglie.timer = originale;
  }
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
  window.fetch = async (url, _opts) => {
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
