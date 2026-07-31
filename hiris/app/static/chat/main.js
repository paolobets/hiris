/* HIRIS · Chat page · bootstrap (SP-4 Fase B Task 8)
   Wires the buttons that used to carry inline onclick="..." attributes and
   runs the boot sequence. Loads last (mirrors config/main.js being the
   final <script> in config.html). */
(function() {
  function wireHeaderAndSidebarButtons() {
    var newConvBtn = document.getElementById('new-conv-btn');
    if (newConvBtn) newConvBtn.addEventListener('click', window.HirisChatAgents.clearConversation);
  }

  function boot() {
    window.HirisChatTheme.init();

    fetch('api/health').then(function(r) { return r.json(); }).then(function(d) {
      var el = document.getElementById('header-version');
      if (el && d.version) el.textContent = 'v' + d.version;
    }).catch(function() {});

    window.HirisChatAgents.load();
    /* Ricarica la history dell'agente attivo: senza questo, tornando alla chat
       da config (reload pieno) si vedeva una chat vuota pur essendo salvata. */
    window.HirisChatAgents.restore();
    loadUsage();
    window.HirisChatAgents.updateGreeting();
    setInterval(window.HirisChatAgents.load, 30000);
    setInterval(loadUsage, 30000);
    setInterval(window.HirisChatAgents.updateGreeting, 60 * 60 * 1000); /* refresh greeting every hour */

    window.HirisChatSidebar.init();
    window.HirisChatTasks.init();
    window.HirisChatOnboarding.init();
    window.HirisChatKeyboard.init();
    window.HirisChatSend.wireComposer();
    wireHeaderAndSidebarButtons();
  }

  boot();
})();
