/* HIRIS · Chat page · bootstrap (SP-4 Fase B Task 8; fetta E5 Task 3)
   Wires the buttons that used to carry inline onclick="..." attributes and
   runs the boot sequence. Loads last (mirrors config/main.js being the
   final <script> in config.html). */
(function() {
  function wireHeaderAndSidebarButtons() {
    var newConvBtn = document.getElementById('new-conv-btn');
    if (newConvBtn) newConvBtn.addEventListener('click', window.HirisChatAgents.clearConversation);
  }

  /* Unica fonte del "connesso/offline": estende la chiamata a GET api/health
     che questa pagina gia' faceva per il numero di versione (Task 3 -- prima
     l'indicatore leggeva l'esito di GET api/chatbots, la fetch che
     costruiva l'elenco dei bot ora uscito). Nessuna seconda fetch aggiunta:
     e' la stessa chiamata, con un lettore in piu' sulla risposta/sul fallimento. */
  function checkHealth() {
    var state = window.HirisChatState;
    return fetch('api/health').then(function(r) {
      if (!r.ok) throw new Error('api/health: ' + r.status);
      return r.json();
    }).then(function(d) {
      var el = document.getElementById('header-version');
      /* Mostra anche il build stamp: cambia a ogni modifica del frontend, cosi'
         verifichi CHE COSA gira davvero (cache vs container non ricostruito). */
      if (el && d.version) el.textContent = 'v' + d.version + (d.build ? ' · ' + d.build : '');
      if (state.els.connDot) {
        state.els.connDot.classList.remove('offline');
        state.els.connDot.textContent = 'connesso';
      }
    }).catch(function() {
      if (state.els.connDot) {
        state.els.connDot.classList.add('offline');
        state.els.connDot.textContent = 'offline';
      }
    });
  }

  /* Il riquadro "Utilizzo" si aggiorna a intervalli, ma smette da solo quando
     non c'e' niente da aggiornare. `loadUsage()` (config/api.js) restituisce
     `false` SOLO quando il server dichiara che su questa configurazione i
     consumi non si misurano (percorso abbonamento, o nessun provider): e' un
     fatto che non cambia senza un riavvio dell'add-on, quindi ripetere la
     chiamata ogni 30 secondi produce solo rumore -- prima erano un 503 e un
     console.error ogni mezzo minuto, per sempre, senza che l'utente leggesse
     mai il perche'. Un errore di rete o un HTTP non-200 restituiscono invece
     `true`: quelli possono passare, e il timer resta. */
  var timerConsumi = null;

  function aggiornaConsumi() {
    return loadUsage().then(function (continua) {
      if (continua === false && timerConsumi !== null) {
        clearInterval(timerConsumi);
        timerConsumi = null;
      }
    });
  }

  function boot() {
    window.HirisChatTheme.init();

    checkHealth();
    setInterval(checkHealth, 30000);

    window.HirisChatAgents.loadSettings();
    /* Ricarica la history della conversazione: senza questo, tornando alla chat
       da config (reload pieno) si vedeva una chat vuota pur essendo salvata. */
    window.HirisChatAgents.restore();
    aggiornaConsumi();
    window.HirisChatAgents.updateGreeting();
    setInterval(window.HirisChatAgents.loadSettings, 30000);
    timerConsumi = setInterval(aggiornaConsumi, 30000);
    setInterval(window.HirisChatAgents.updateGreeting, 60 * 60 * 1000); /* refresh greeting every hour */

    window.HirisChatSidebar.init();
    window.HirisChatKeyboard.init();
    window.HirisChatSend.wireComposer();
    wireHeaderAndSidebarButtons();
  }

  boot();
})();
