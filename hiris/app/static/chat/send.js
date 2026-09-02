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
            /* Il ripiego si annuncia (decisione del proprietario, 13 agosto):
               quando il turno passa dal piano a forfait a un provider a
               consumo, la risposta lo dice. Il campo e' FACOLTATIVO e la
               forma della risposta non cambia -- `status`/`reply` restano
               identici -- quindi un client che lo ignori continua a
               funzionare. Una riga per ramo, e le due righe sono gemelle:
               quella del ramo diretto sta in fondo a send(). */
            if (data.nota) window.HirisChatMessages.appendNota(placeholderRow, data.nota);
            /* Qui il ramo del ponte disegnava le targhette degli strumenti,
               aggiunte l'11 agosto perche' l'osservabilita' di una scrittura di
               `ricorda` mancava proprio sul percorso che la produce. Sono uscite
               il 17 agosto: il proprietario non le vuole a schermo, e i nomi
               degli strumenti (con i loro ARGOMENTI, che per `ricorda` sono il
               testo del ricordo) non sono cose da scrivere in una conversazione.

               L'osservabilita' non e' stata tolta ma SPOSTATA: il backend scrive
               gli strumenti del turno nei log a livello debug
               (`api/handlers_chat.py`). Il payload non li manda piu' affatto. */
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
        } catch {
          /* Transient network hiccup while polling -- keep retrying until the
           * overall timeout above gives up. */
        }
      }
      /* Cinque minuti di attesa non possono finire in un vicolo cieco. Su
         questo percorso il turno vive sul server: se la risposta arriva dopo
         che abbiamo smesso di chiedere, finisce comunque in cronologia
         (`server.py::_submit_chat_reply`) e ricompare al caricamento dopo.
         Dirlo e' piu' vero -- e piu' utile -- di un «Riprova» che
         rimanderebbe la stessa domanda una seconda volta. */
      window.HirisChatMessages.updateBubble(placeholderRow,
        'Ho smesso di aspettare dopo cinque minuti. Se la risposta arriva, la trovi in questa conversazione ricaricando la pagina.');
    } finally {
      setLoadingState(false);
      if (!state.els.input.disabled) state.els.input.focus();
    }
  }

  var SEGNAPOSTO_NORMALE = 'Scrivi un messaggio\u2026';
  var SEGNAPOSTO_ATTESA = 'HIRIS sta rispondendo \u2014 potrai scrivere appena ha finito';

  function setLoadingState(loading) {
    state.isLoading = loading;
    /* La textarea diventa `readOnly`, non `disabled`. Un controllo disabilitato
       PERDE IL FUOCO: su un tablet questo chiude la tastiera di sistema, e
       chat/keyboard.js se ne accorge 300 ms dopo e ricalcola l'altezza della
       pagina -- cioe' a ogni invio la conversazione saltava sotto il dito, e
       alla risposta risaliva. In sola lettura il fuoco resta dov'e', la
       tastiera resta aperta, e il secondo invio e' comunque impossibile: lo
       ferma la guardia `state.isLoading` in send(), che e' il vero blocco.
       Il segnaposto dice PERCHE' non si puo' scrivere, invece di lasciare un
       campo muto e inerte davanti a chi ci ha appena cliccato dentro.
       Allo sblocco NON forziamo abilitato: ripristiniamo lo stato reale via
       checkTurnLimit (potrebbe essere disabilitato per turn-limit -- e li' il
       `disabled` e' giusto, perche' la sessione e' finita davvero). */
    if (loading) {
      state.els.input.readOnly = true;
      state.els.input.placeholder = SEGNAPOSTO_ATTESA;
      state.els.sendBtn.disabled = true;
    } else {
      state.els.input.readOnly = false;
      state.els.input.placeholder = SEGNAPOSTO_NORMALE;
      window.HirisChatAgents.checkTurnLimit();
    }
    /* Il bottone «cancella conversazione» non deve poter rispondere mentre
       HIRIS elabora: premuto in quel momento svuotava la lista, e la risposta
       -- gia' pagata in token -- veniva poi scritta dentro una riga staccata
       dal DOM, che nessuno vedeva mai. E' la stessa condizione che blocca il
       composer, quindi vive qui e non in un secondo posto da tenere allineato. */
    var btnCancella = document.getElementById('cancella-conv-btn');
    if (btnCancella) btnCancella.disabled = loading;
    state.els.sendBtn.classList.toggle('loading', loading);
  }

  async function send(text) {
    text = (text !== undefined) ? text : state.els.input.value.trim();
    if (!text || state.isLoading) return;
    state.els.input.value = '';
    autoResize();
    setLoadingState(true);
    window.HirisChatMessages.appendMsg('user', text);
    /* L'indicatore d'attesa e la risposta sono LO STESSO NODO, su tutti e due i
       percorsi. Prima il ramo diretto creava una riga d'attesa, la rimuoveva e
       ne aggiungeva un'altra: un fotogramma di vuoto, un cambio d'altezza e uno
       scorrimento, proprio nell'istante in cui l'occhio sta cercando la
       risposta. Adesso ogni ramo scrive DENTRO la bolla che c'e' gia'. */
    var pending = window.HirisChatMessages.showThinking();
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
      if (r.status === 202 && data.status === 'pending' && data.job_id) {
        /* Da qui in poi il turno vive sul server: il messaggio dell'utente e'
           gia' in cronologia e la risposta ci finira' da sola. L'indicatore lo
           sa, e ai due minuti lo dice con la frase giusta invece di spaventare
           chi vuole chiudere la pagina.
           Gli passiamo anche `CHAT_POLL_MAX_MS`, che vive qui e solo qui: e'
           la scadenza VERA di questa attesa, e vale solo su questo ramo --
           `pollChatReply` e' l'unico posto del prodotto che smette di
           aspettare. Sul ramo diretto la `fetch` qui sotto non ha ne un
           `AbortController` ne un timeout: nessuna scadenza da dichiarare, e
           l'indicatore infatti non ne promette una. */
        window.HirisChatMessages.attesaAlSicuroSulServer(pending, CHAT_POLL_MAX_MS);
        handedOff = true;
        pollChatReply(data.job_id, pending);
        return;
      }
      if (data.error === 'max_turns_reached') {
        window.HirisChatMessages.updateBubble(pending, 'Sessione completata. Avvia una nuova conversazione.');
        window.HirisChatAgents.checkTurnLimit();
        return;
      }
      window.HirisChatMessages.updateBubble(pending, data.response || data.error || 'Errore sconosciuto');
      /* Vedi la gemella nel ramo del poll, sopra. Qui il ripiego e' quello a
         monte: il piano non poteva ricevere il turno (niente token, o tetto
         giornaliero pieno) e la catena ha risposto sincrona. */
      if (data.nota) window.HirisChatMessages.appendNota(pending, data.nota);
      state.turnCount = (state.turnCount || 0) + 1;
      window.HirisChatAgents.updateTurnCounter();
      window.HirisChatAgents.checkTurnLimit();
    } catch {
      window.HirisChatMessages.updateBubble(pending, 'Errore di connessione. Riprova tra poco.');
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
    var acapoVoluto = false;
    state.els.input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.keyCode === 13) {
        if (e.shiftKey) {
          /* Maiusc+Invio e' l'unico gesto di composizione che esiste in una
             chat, e vuol dire «vado a capo». Il gestore `input` qui sotto
             lo vedeva come un a-capo qualsiasi e mandava il messaggio: il
             gesto faceva l'opposto di se stesso. */
          acapoVoluto = true;
          return;
        }
        e.preventDefault();
        enterSent = true;
        send();
        setTimeout(function() { enterSent = false; }, 200);
      }
    });
    /* Questa euristica esiste per UNA ragione sola: certe tastiere di sistema
       (mobile) inseriscono un a-capo nel testo invece di emettere un `keydown`
       con Invio, e senza di lei il tasto «invia» del telefono non
       inviava niente. Reagiva pero' a QUALUNQUE a-capo comparso nel campo --
       quindi anche a Maiusc+Invio e a un incolla di due righe prese dai log di
       Home Assistant: il messaggio partiva da solo, con un testo che l'utente
       non aveva finito di scrivere, bruciando un turno del tetto di sessione.
       E le righe venivano saldate cancellando l'a-capo (`\n` -> stringa
       vuota), non sostituendolo: «riga uno\nriga due» diventava
       «riga unoriga due». Adesso guarda `inputType`, che dice quale
       gesto ha prodotto la modifica, e resta accesa solo sul suo caso. */
    state.els.input.addEventListener('input', function(e) {
      autoResize();
      if (acapoVoluto) { acapoVoluto = false; return; }
      /* incolla, dettatura, annulla, correzione automatica: non sono invii */
      if (e && e.inputType && e.inputType !== 'insertLineBreak') return;
      if (enterSent) return;
      if (state.els.input.value.indexOf('\n') === -1) return;
      var msg = state.els.input.value.replace(/\n+/g, ' ').trim();
      state.els.input.value = msg;
      autoResize();
      if (msg) send(msg);
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
