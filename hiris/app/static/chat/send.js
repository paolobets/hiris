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

   fetta E5 Task 5: questo e' adesso l'UNICO ciclo di polling della risposta
   di tutto il prodotto. Erano due -- questo e il `_pollChatReply` della card
   Lovelace, che girava dentro Home Assistant e non poteva condividere questo
   file. Quello della card **non leggeva `debug`**, cioe' la tracciabilita'
   delle chiamate agli strumenti (rilievo I-7 della review di parita' B):
   chi usava la card vedeva la risposta senza sapere cosa HIRIS avesse
   guardato. Con l'uscita della card il doppione sparisce, e con lui la
   possibilita' che le due superfici raccontino il turno in due modi diversi.
   Erano tre near-duplicati alla ricognizione SP-4 (questo file ne aveva una
   copia privata, piu' quella della card): adesso e' uno. */
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
            /* Review totale della fetta E5: il ramo del ponte (202 -> job_id) e'
               l'UNICO che un tester con l'abbonamento percorre, ed era l'unico che
               NON mostrava gli strumenti usati. Il backend li manda anche qui
               (`handlers_chat.py:352`, "il conteggio esposto dove l'utente lo vede
               e' len() di questa lista lato client") -- ma nessuno li leggeva: la
               cosa costruita perche' una scrittura di `ricorda` fosse OSSERVABILE
               non era osservabile proprio sul percorso che la produce. Stessa
               chiamata e stesse condizioni del ramo sincrono venti righe sotto, in
               modo che i due percorsi non divergano una seconda volta. */
            if (data.debug && data.debug.tools_called && data.debug.tools_called.length > 0) {
              window.HirisChatMessages.appendDebug(data.debug.tools_called);
            }
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
