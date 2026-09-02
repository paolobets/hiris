/* HIRIS · Chat page · una conversazione sola: nome, turn limit, cronologia
   (fetta E5 Task 3 -- "via l'elenco dei bot dalla sidebar")

   Dalla E4 esiste un solo assistente: non c'e' piu' niente da elencare o da
   scambiare. Questo file non costruisce piu' una lista (era sempre un
   elemento solo, con un pallino "acceso/spento" che leggeva un booleano
   letterale) ne' seleziona un id diverso da se stesso -- portava rumore, e
   per un tester era una promessa falsa ("ci sono piu' assistenti"). Restano
   le funzioni con un comportamento reale da preservare: la cancellazione
   della cronologia (con conferma), il limite di turni per sessione, il
   ripristino della cronologia al boot, il nome mostrato nella pill
   dell'header.

   Le due rotte di cronologia sono `GET/DELETE api/chat/history` (fetta E5
   Task 4 -- "nasce la rotta onesta e muore il placeholder"): fino a quel
   task portavano ancora un id di bot nel path (`{agent_id}`, sempre
   'hiris-default', mai piu' letto dal server); ora il percorso non porta
   nessun identificatore, perche' non c'e' niente da identificare. */
(function() {
  var state = window.HirisChatState;

  function updateTurnCounter() {
    var counter = document.getElementById('turn-counter');
    var max = state.maxChatTurns || 0;
    if (max === 0) { counter.style.display = 'none'; return; }
    var current = state.turnCount || 0;
    counter.style.display = '';
    counter.textContent = current + ' / ' + max + ' messaggi';
    /* `--err-ink` e non `--err`: e' testo, e sul tema chiaro `--err` sta a
       4.05:1, sotto la soglia AA. */
    counter.style.color = current >= max ? 'var(--err-ink)' : 'var(--text-3)';
  }

  function checkTurnLimit() {
    var max = state.maxChatTurns || 0;
    var sessionMsg = document.getElementById('session-ended-msg');
    if (max === 0) {
      state.els.input.disabled = false;
      state.els.sendBtn.disabled = false;
      if (sessionMsg) sessionMsg.style.display = 'none';
      return;
    }
    var current = state.turnCount || 0;
    var reached = current >= max;
    state.els.input.disabled = reached;
    state.els.sendBtn.disabled = reached;
    if (sessionMsg) sessionMsg.style.display = reached ? '' : 'none';
  }

  /* Costruisce la domanda della conferma dicendo COSA si perde, come si fa
     gia' nella pagina Memoria (dove il `confirm` cita la frase esatta del
     ricordo). Il vecchio testo -- «Cancellare la cronologia di questa
     conversazione?» -- sottodichiarava due volte: non diceva quanto, e
     soprattutto diceva «questa» mentre la DELETE porta via TUTTO.
     Verificato: `chat_store.ChatStore.clear()` svuota `chat_messages` e
     `chat_sessions`, quindi spariscono anche i riassunti delle sessioni chiuse
     che `handlers_chat.compose_chat_context` inietta nel prompt come
     «Sessioni precedenti (memory)». Non e' una conversazione: e' la
     memoria delle conversazioni. */
  function domandaDiConferma() {
    var quanti = state.els.messages
      ? state.els.messages.querySelectorAll('.msg-row').length : 0;
    var visible = quanti === 0
      ? 'Qui non c’è niente da cancellare'
      : quanti === 1
        ? 'Perdi il messaggio che vedi'
        : 'Perdi i ' + quanti + ' messaggi che vedi';
    return visible + ', e anche i riassunti delle conversazioni precedenti '
      + 'che HIRIS si tiene da parte. Non si può annullare.\n\nCancellare?';
  }

  async function clearConversation() {
    /* Irreversibile: la conferma qui mancava, ed e' stata aggiunta copiando
       il testo dalla card Lovelace, che per la stessa azione la chiedeva. La
       card e' uscita col Task 5 della E5: la conferma resta perche' e' il
       comportamento giusto, non perche' un'altra superficie la imponga. */
    if (!window.confirm(domandaDiConferma())) return;
    try {
      var r = await fetch('api/chat/history', { method: 'DELETE', headers: { 'X-Requested-With': 'fetch' } });
      if (!r.ok) {
        /* Se il server non ha cancellato, la UI non deve fingere che l'abbia
           fatto: altrove in questo file un catch vuoto ha nascosto per mesi
           un guasto identico (vedi A9/api.js). */
        console.error('clearConversation failed', r.status);
        window.alert('Non è stato possibile cancellare la cronologia. Riprova più tardi.');
        return;
      }
    } catch (e) {
      console.error('clearConversation failed', e);
      window.alert('Non è stato possibile cancellare la cronologia. Riprova più tardi.');
      return;
    }
    /* Prima di buttare via le righe, ferma quello che ci gira dentro: un
       indicatore d'attesa lasciato acceso continuerebbe a far battere il suo
       cronometro su un nodo che non esiste piu'. In pratica non ci si arriva
       (il bottone e' spento durante l'elaborazione), ma un timer orfano non
       deve dipendere da un `disabled` per non nascere. */
    window.HirisChatMessages.stopAllWaits();
    state.els.messages.innerHTML = '';
    state.els.messages.appendChild(state.els.welcome);
    state.els.welcome.style.display = '';
    state.hasMessages = false;
    state.turnCount = 0;
    updateTurnCounter();
    checkTurnLimit();
  }

  function updateAgentPill(agentName) {
    var pill = document.getElementById('agent-pill');
    if (!pill) return;
    var avatar = document.getElementById('ap-avatar');
    var name = document.getElementById('ap-name');
    /* Il ripiego e' il nome del prodotto, non quello di un assistente
       che non esiste piu': la 2.0 ha una chat sola, ed e' HIRIS. */
    var letter = (agentName || 'HIRIS').trim().charAt(0).toUpperCase();
    if (avatar) avatar.textContent = letter;
    if (name) name.textContent = agentName || 'HIRIS';
  }

  function updateGreeting() {
    var hello = document.getElementById('welcome-hello');
    if (!hello) return;
    var h = new Date().getHours();
    var word = (h < 5 || h >= 22) ? 'Buonanotte'
             : (h < 12) ? 'Buongiorno'
             : (h < 18) ? 'Buon pomeriggio'
             : 'Buonasera';
    hello.textContent = word;
  }

  /* Sostituisce il vecchio `load()` (costruttore d'elenco). Legge il nome e
     il tetto di turni dalle impostazioni della chat (Task 2,
     `GET /api/chat-settings`), non piu' dalla superficie di
     compatibilita' `GET /api/chatbots`: e' il primo chiamante che se ne
     stacca. L'indicatore "connesso/offline" non vive piu' qui -- e'
     diventato parte del controllo di salute che chat/main.js gia' fa al
     boot (`GET api/health`), invece di una fetch separata. */
  async function loadSettings() {
    try {
      var r = await fetch('api/chat-settings');
      if (!r.ok) throw new Error('impostazioni-chat: ' + r.status);
      var data = await r.json();
      state.maxChatTurns = data.max_chat_turns || 0;
      updateAgentPill(data.name);
    } catch (e) {
      console.error('loadSettings failed', e);
    }
  }

  /* Carica e mostra la history salvata della conversazione. Estratta da un
     vecchio `setActive()` per essere riusata al boot (restore); il guard
     sul cambio d'agente che c'era qui e' uscito con l'agente stesso -- non
     esiste piu' un secondo id con cui la risposta possa arrivare in
     ritardo. */
  async function applyHistory() {
    try {
      var r = await fetch('api/chat/history');
      if (!r.ok) {
        /* Fratello dello stesso difetto: prima ne' il ramo r.ok=false ne' il
           catch sotto lasciavano traccia -- la cronologia restava vuota senza
           che nulla lo dicesse nemmeno in console. */
        console.error('applyHistory failed', r.status);
        return;
      }
      var data = await r.json();
      var msgs = data.messages || [];
      msgs.forEach(function(m) {
        window.HirisChatMessages.appendMsg(m.role === 'user' ? 'user' : 'assistant', m.content);
      });
      state.turnCount = msgs.filter(function(m) { return m.role === 'user'; }).length;
      updateTurnCounter();
      checkTurnLimit();
    } catch (e) {
      console.error('applyHistory failed', e);
    }
  }

  /* Boot: senza questo, tornando alla chat da config (reload pieno) si
     vedeva una chat vuota pur essendo salvata lato server. */
  async function restore() {
    await applyHistory();
  }

  window.HirisChatAgents = {
    updateTurnCounter: updateTurnCounter,
    checkTurnLimit: checkTurnLimit,
    clearConversation: clearConversation,
    updateAgentPill: updateAgentPill,
    updateGreeting: updateGreeting,
    loadSettings: loadSettings,
    restore: restore,
  };
})();
