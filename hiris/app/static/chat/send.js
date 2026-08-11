/* HIRIS · Chat page · send + poll (SP-4 Fase B Task 8; fetta E5 Task 3: il
   wire smette di mandare chatbot_id -- un solo assistente non ha bisogno di
   dirsi quale, e la chiave resta accettata-e-ignorata lato server fino al
   Task 10, che smonta anche quella lettura)
   POSTs api/chat with just the message.

   Slice 4b (chat via abbonamento): when the backend enqueues the turn to
   the subscription runner instead of replying synchronously, it returns
   HTTP 202 {status:"pending", job_id}. Poll the reply endpoint every ~3.5s,
   replacing the placeholder bubble once a terminal state ("done" or
   "error") arrives. Gives up after CHAT_POLL_MAX_MS so the UI never spins
   forever.

   This is the page's own polling loop, not shared with hiris-chat-card.js:
   the card is a Shadow-DOM custom element copied into HA's www/ folder and
   deployed via a completely different mechanism (Lovelace module registry,
   see hiris-chat-card.js header), so it cannot <script src> this file --
   sharing would mean shipping an extra file into www/ for one function.
   Project-wide there are now exactly two implementations (this one and the
   card's _pollChatReply), each the single owner for its surface -- down
   from the three near-duplicates the SP-4 grounding found (this file's old
   private copy, plus the card's). See task-8-report.md. */
(function() {
  var state = window.HirisChatState;
  var CHAT_POLL_INTERVAL_MS = 3500;
  var CHAT_POLL_MAX_MS = 5 * 60 * 1000;

  function sleep(ms) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
  }

  async function pollChatReply(jobId, placeholderRow) {
    /* Il lock dell'input (setLoadingState) resta attivo per TUTTO il poll: send()
       lo passa a noi (handedOff) invece di sbloccarlo nel suo finally, cosi' non
       si puo' inviare un altro messaggio mentre HIRIS elabora la risposta via
       abbonamento. Sblocchiamo qui, su QUALSIASI uscita (done/error/timeout). */
    try {
      var start = Date.now();
      while (Date.now() - start < CHAT_POLL_MAX_MS) {
        await sleep(CHAT_POLL_INTERVAL_MS);
        try {
          var r = await fetch('api/chat/reply/' + encodeURIComponent(jobId));
          var data = await r.json();
          if (data.status === 'done') {
            window.HirisChatMessages.updateBubble(placeholderRow, data.reply || '');
            state.turnCount = (state.turnCount || 0) + 1;
            window.HirisChatAgents.updateTurnCounter();
            window.HirisChatAgents.checkTurnLimit();
            return;
          }
          if (data.status === 'error') {
            window.HirisChatMessages.updateBubble(placeholderRow, data.message || 'Errore nella risposta.');
            return;
          }
          /* status === 'pending' (or unexpected 404/503 body without a status)
           * -- keep polling until CHAT_POLL_MAX_MS is reached. */
        } catch (e) {
          /* Transient network hiccup while polling -- keep retrying until the
           * overall timeout above gives up. */
        }
      }
      window.HirisChatMessages.updateBubble(placeholderRow, 'La risposta non è arrivata in tempo. Riprova.');
    } finally {
      setLoadingState(false);
      if (!state.els.input.disabled) state.els.input.focus();
    }
  }

  function setLoadingState(loading) {
    state.isLoading = loading;
    /* Blocca la textarea (non solo il bottone) mentre HIRIS elabora: niente
       secondo messaggio finche' non arriva la risposta. Allo sblocco NON
       forziamo abilitato -- ripristiniamo lo stato reale via checkTurnLimit
       (potrebbe essere disabilitato per turn-limit). */
    if (loading) {
      state.els.input.disabled = true;
      state.els.sendBtn.disabled = true;
    } else {
      window.HirisChatAgents.checkTurnLimit();
    }
    state.els.sendBtn.classList.toggle('loading', loading);
  }

  async function send(text) {
    text = (text !== undefined) ? text : state.els.input.value.trim();
    if (!text || state.isLoading) return;
    state.els.input.value = '';
    autoResize();
    setLoadingState(true);
    window.HirisChatMessages.appendMsg('user', text);
    var typing = window.HirisChatMessages.showTyping();
    /* handedOff: sul path 202 il lock passa a pollChatReply (che sblocca a fine
       poll), quindi il finally qui NON deve sbloccare -- altrimenti l'input si
       riaprirebbe mentre HIRIS sta ancora elaborando la risposta. */
    var handedOff = false;
    try {
      var r = await fetch('api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
        body: JSON.stringify({ message: text }),
      });
      var data = await r.json();
      typing.remove();
      if (r.status === 202 && data.status === 'pending' && data.job_id) {
        var placeholder = window.HirisChatMessages.showThinking();
        handedOff = true;
        pollChatReply(data.job_id, placeholder);
        return;
      }
      if (data.error === 'max_turns_reached') {
        window.HirisChatMessages.appendMsg('assistant', 'Sessione completata. Avvia una nuova conversazione.');
        window.HirisChatAgents.checkTurnLimit();
        return;
      }
      window.HirisChatMessages.appendMsg('assistant', data.response || data.error || 'Errore sconosciuto');
      if (data.debug && data.debug.tools_called && data.debug.tools_called.length > 0) {
        window.HirisChatMessages.appendDebug(data.debug.tools_called);
      }
      state.turnCount = (state.turnCount || 0) + 1;
      window.HirisChatAgents.updateTurnCounter();
      window.HirisChatAgents.checkTurnLimit();
    } catch (e) {
      typing.remove();
      window.HirisChatMessages.appendMsg('assistant', 'Errore di connessione. Riprova tra poco.');
    } finally {
      if (!handedOff) {
        setLoadingState(false);
        if (!state.els.input.disabled) state.els.input.focus();
      }
    }
  }

  function sendQuick(text) { send(text); }

  function autoResize() {
    state.els.input.style.height = 'auto';
    state.els.input.style.height = Math.min(state.els.input.scrollHeight, 160) + 'px';
  }

  function wireComposer() {
    var enterSent = false;
    state.els.input.addEventListener('keydown', function(e) {
      if ((e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey) {
        e.preventDefault();
        enterSent = true;
        send();
        setTimeout(function() { enterSent = false; }, 200);
      }
    });
    state.els.input.addEventListener('input', function() {
      autoResize();
      if (!enterSent && state.els.input.value.includes('\n')) {
        var msg = state.els.input.value.replace(/\n/g, '').trim();
        state.els.input.value = msg;
        autoResize();
        if (msg) send(msg);
      }
    });
    state.els.sendBtn.addEventListener('click', function() { send(); });

    /* Quick-reply chips in the welcome screen (was onclick="sendQuick(...)"
       per button -- one delegated listener instead). */
    if (state.els.welcome) {
      state.els.welcome.addEventListener('click', function(e) {
        var chip = e.target.closest && e.target.closest('.chip[data-quick]');
        if (chip) send(chip.getAttribute('data-quick'));
      });
    }
  }

  window.HirisChatSend = {
    send: send,
    sendQuick: sendQuick,
    autoResize: autoResize,
    wireComposer: wireComposer,
  };
})();
