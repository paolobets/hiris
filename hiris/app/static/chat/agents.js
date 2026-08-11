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

   `CHAT_ID` e' la chiave (letterale, non piu' scelta dall'utente) delle due
   rotte di cronologia -- superficie di compatibilita' che esce al Task 10;
   fino ad allora restano `GET/DELETE api/chatbots/{id}/chat-history`,
   invariate qui (vedi impostazioni_chat.ID_CHAT_DEFAULT lato server). */
(function() {
  var state = window.HirisChatState;
  var CHAT_ID = 'hiris-default';

  function updateTurnCounter() {
    var counter = document.getElementById('turn-counter');
    var max = state.maxChatTurns || 0;
    if (max === 0) { counter.style.display = 'none'; return; }
    var current = state.turnCount || 0;
    counter.style.display = '';
    counter.textContent = current + ' / ' + max + ' messaggi';
    counter.style.color = current >= max ? 'var(--err)' : 'var(--text-3)';
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

  async function clearConversation() {
    /* Irreversibile: la card Lovelace (hiris-chat-card.js) chiede conferma
       per la stessa identica azione con lo stesso testo -- qui mancava. */
    if (!window.confirm('Cancellare la cronologia di questa conversazione?')) return;
    try {
      var r = await fetch('api/chatbots/' + CHAT_ID + '/chat-history', { method: 'DELETE', headers: { 'X-Requested-With': 'fetch' } });
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
    var letter = (agentName || 'I').trim().charAt(0).toUpperCase();
    if (avatar) avatar.textContent = letter;
    if (name) name.textContent = agentName || 'Iris';
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
     `GET /api/impostazioni-chat`), non piu' dalla superficie di
     compatibilita' `GET /api/chatbots`: e' il primo chiamante che se ne
     stacca. L'indicatore "connesso/offline" non vive piu' qui -- e'
     diventato parte del controllo di salute che chat/main.js gia' fa al
     boot (`GET api/health`), invece di una fetch separata. */
  async function loadSettings() {
    try {
      var r = await fetch('api/impostazioni-chat');
      if (!r.ok) throw new Error('impostazioni-chat: ' + r.status);
      var dati = await r.json();
      state.maxChatTurns = dati.max_chat_turns || 0;
      updateAgentPill(dati.nome);
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
      var r = await fetch('api/chatbots/' + CHAT_ID + '/chat-history');
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
