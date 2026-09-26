/* HIRIS · Chat page · la conversazione a schermo: nome, turn limit,
   cronologia, cestino (fetta E5 Task 3 -- "via l'elenco dei bot dalla
   sidebar")

   Dalla E4 esiste un solo assistente: non c'e' piu' niente da elencare o da
   scambiare. Questo file non costruisce piu' una lista (era sempre un
   elemento solo, con un pallino "acceso/spento" che leggeva un booleano
   letterale) ne' seleziona un id diverso da se stesso -- portava rumore, e
   per un tester era una promessa falsa ("ci sono piu' assistenti"). Restano
   le funzioni con un comportamento reale da preservare: la cancellazione
   della conversazione aperta (con conferma), il limite di turni per
   conversazione, la cronologia della conversazione attiva, il nome mostrato
   nella pill dell'header.

   La cronologia si legge da `GET api/chat/history`, senza parametri: e' la
   conversazione attiva del filo di chi guarda, e il filo lo decide il
   confine del server, non la pagina. Le conversazioni del filo (elenco,
   nuova, riprendi, cancella) sono di chat/conversations.js (fetta «il
   seguito delle chat divise», spec 2026-09-26 §4): da li' passa anche la
   DELETE del cestino, che cancella UNA conversazione per id. */
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

  /* La frase del limite ha una casa sola (spec 2026-09-26 §4): la riga fissa
     sotto il campo (`#session-ended-msg`, che index.html lascia vuota) e la
     bolla che chat/send.js scrive quando il server risponde
     `max_turns_reached` la leggono tutte e due da qui. Erano due testi, e
     dicevano «avvia una nuova conversazione» senza nessun bottone dietro:
     adesso il bottone c'e', e la frase dice dove. */
  var LIMIT_TEXT = 'Hai raggiunto il limite di messaggi per questa conversazione. '
    + 'Avviane una nuova dalla barra laterale.';

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
    if (sessionMsg) {
      sessionMsg.textContent = LIMIT_TEXT;
      sessionMsg.style.display = reached ? '' : 'none';
    }
  }

  /* La conferma del cestino dice COSA si perde e COSA RESTA (reperto C-6,
     23/09/2026): chi preme «cancella» sta chiedendo «togli quello che ho
     detto a HIRIS», e tacere che i ricordi sopravvivono gli farebbe credere
     di aver pulito tutto -- questo prodotto non fa credere cose. Si dice
     anche DOVE si tolgono. Dalla fetta «il seguito delle chat divise» il
     cestino cancella la conversazione APERTA, non tutto il filo (decisione
     9): il testo lo dice, e dice che le altre restano in elenco. Testo
     esatto della spec 2026-09-26 §4, deciso con ux-ui-specialist; «in elenco
     qui a fianco» e' diventato «nell'elenco delle conversazioni» il 26/09
     (review UX): sul telefono l'elenco sta nel cassetto, non a fianco. */
  var DELETE_CONFIRM = 'Perdi i messaggi di questa conversazione e il suo riassunto. '
    + 'Le tue altre conversazioni restano nell\'elenco delle conversazioni.\n'
    + 'I ricordi non si toccano: restano finché non li cancelli tu, uno per uno, '
    + 'dalla pagina Memoria.\n'
    + 'Non si può annullare.\n\n'
    + 'Cancellare questa conversazione?';

  async function clearConversation() {
    /* L'id e' quello che il server marca `attiva` nell'elenco: senza, non
       c'e' niente da cancellare (il bottone e' gia' spento, vedi
       chat/conversations.js::syncControls) e nessuna domanda ha senso.
       Irreversibile, quindi con conferma. Un fallimento lascia la vista
       com'e' e lo dice (chat/conversations.js): la UI non finge di aver
       cancellato quello che il server ha tenuto. */
    var id = window.HirisChatConversations.activeId();
    if (id === null) return;
    if (!window.confirm(DELETE_CONFIRM)) return;
    await window.HirisChatConversations.remove(id);
  }

  /* Svuota la vista prima di disegnarci un'altra conversazione. Prima di
     buttare via le righe ferma quello che ci gira dentro: un indicatore
     d'attesa lasciato acceso continuerebbe a far battere il suo cronometro
     su un nodo che non esiste piu'. */
  function resetView() {
    window.HirisChatMessages.stopAllWaits();
    state.els.messages.innerHTML = '';
    state.els.messages.appendChild(state.els.welcome);
    state.els.welcome.style.display = '';
    state.hasMessages = false;
    state.turnCount = 0;
    /* Il limite della conversazione di prima non resta appeso alla vista
       vuota se la storia poi non arriva. */
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
        return false;
      }
      var data = await r.json();
      var msgs = data.messages || [];
      msgs.forEach(function(m) {
        /* `true` = "e' cronologia, non un invio vivo": l'ora della bolla
           viene da `m.timestamp` (collaudo 3.22, C4), mai da `new Date()`
           al momento del disegno -- vedi chat/messages.js::appendMsg. */
        window.HirisChatMessages.appendMsg(m.role === 'user' ? 'user' : 'assistant', m.content, true, m.timestamp);
      });
      state.turnCount = msgs.filter(function(m) { return m.role === 'user'; }).length;
      updateTurnCounter();
      checkTurnLimit();
      return true;
    } catch (e) {
      console.error('applyHistory failed', e);
      return false;
    }
  }

  /* Mostra, da capo, la conversazione che il server dice attiva. Al boot
     (senza, tornando alla chat da config si vedeva una chat vuota pur
     essendo salvata) e dopo ogni nuova/ripresa/cancellazione
     (chat/conversations.js): il contatore dei turni viene dalla storia
     riletta, cosi' una conversazione ripresa porta il SUO limite. Dice se
     la storia e' arrivata: chat/conversations.js lo fa sapere a chi guarda. */
  async function restore() {
    resetView();
    return applyHistory();
  }

  window.HirisChatAgents = {
    updateTurnCounter: updateTurnCounter,
    checkTurnLimit: checkTurnLimit,
    clearConversation: clearConversation,
    updateAgentPill: updateAgentPill,
    updateGreeting: updateGreeting,
    loadSettings: loadSettings,
    restore: restore,
    LIMIT_TEXT: LIMIT_TEXT,
  };
})();
