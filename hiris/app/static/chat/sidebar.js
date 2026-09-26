/* HIRIS · Chat page · off-canvas sidebar (mobile) (SP-4 Fase B Task 8) */
(function() {
  function toggle(force) {
    var sb = document.getElementById('sidebar');
    var ov = document.getElementById('sidebar-overlay');
    if (!sb) return;
    var open = (force === undefined) ? !sb.classList.contains('open') : !!force;
    sb.classList.toggle('open', open);
    if (ov) ov.style.display = open ? 'block' : 'none';
    var menuBtn = document.getElementById('menu-btn');
    if (menuBtn) menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function init() {
    var menuBtn = document.getElementById('menu-btn');
    if (menuBtn) menuBtn.addEventListener('click', function() { toggle(); });
    var overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.addEventListener('click', function() { toggle(false); });
    /* C1 (audit 2026-08-24): bottone di chiusura esplicito in cima al
       pannello, nello stesso angolo dell'hamburger che il pannello copre
       da sotto. */
    var closeBtn = document.getElementById('sidebar-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', function() { toggle(false); });
    /* Il tocco su una voce chiude il cassetto: le voci di navigazione e,
       dalla fetta «il seguito delle chat divise» (spec 2026-09-26 §4), le
       conversazioni e «Nuova conversazione», che sono `.sb-nav-item` anche
       loro. La domanda e' «il cassetto e' aperto?», e la risposta e' la
       classe `open`: prima si chiedeva a una larghezza scritta qui (720 px)
       mentre il foglio fa del pannello un cassetto fino a 768 px
       (hiris-chat.css), e fra le due -- l'iPad in verticale -- il cassetto
       restava aperto sopra la conversazione appena scelta. Su schermo largo
       il pannello non e' mai `open`, e chiuderlo non cambia niente. */
    var sb = document.getElementById('sidebar');
    if (sb) sb.addEventListener('click', function(e) {
      var hit = e.target.closest('.sb-nav-item');
      if (hit && sb.classList.contains('open')) toggle(false);
    });
  }

  window.HirisChatSidebar = { toggle: toggle, init: init };
})();
