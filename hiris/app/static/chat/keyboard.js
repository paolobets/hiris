/* HIRIS · Chat page · mobile keyboard viewport fix (preserved from original)
   (SP-4 Fase B Task 8) */
(function() {
  function init() {
    var state = window.HirisChatState;
    var appEl = document.getElementById('app');
    var inputEl = state.els.input;
    var messagesEl = state.els.messages;
    var isTouchDevice = navigator.maxTouchPoints > 0 || 'ontouchstart' in window;

    function applyKbH(kbH) {
      var vvh = window.innerHeight - Math.max(0, kbH);
      document.body.style.height = vvh + 'px';
      appEl.style.height = vvh + 'px';
      if (kbH > 50) messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    function resetKbH() { document.body.style.height = ''; appEl.style.height = ''; }

    if (window.visualViewport) {
      function onVV() { applyKbH(window.innerHeight - window.visualViewport.height); }
      window.visualViewport.addEventListener('resize', onVV);
      window.visualViewport.addEventListener('scroll', onVV);
    }
    inputEl.addEventListener('focus', function() {
      if (!isTouchDevice) return;
      setTimeout(function() {
        var vvKbH = window.visualViewport ? Math.max(0, window.innerHeight - window.visualViewport.height) : 0;
        if (vvKbH < 50) {
          var est = Math.min(Math.max(Math.round(window.innerHeight * 0.44), 220), 380);
          applyKbH(est);
        }
      }, 400);
    });
    inputEl.addEventListener('blur', function() {
      setTimeout(function() {
        var vvKbH = window.visualViewport ? Math.max(0, window.innerHeight - window.visualViewport.height) : 0;
        if (vvKbH < 50) resetKbH();
      }, 300);
    });
  }

  window.HirisChatKeyboard = { init: init };
})();
