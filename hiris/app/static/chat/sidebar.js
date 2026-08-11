/* HIRIS · Chat page · off-canvas sidebar (mobile) (SP-4 Fase B Task 8) */
(function() {
  function toggle(force) {
    var sb = document.getElementById('sidebar');
    var ov = document.getElementById('sidebar-overlay');
    if (!sb) return;
    var open = (force === undefined) ? !sb.classList.contains('open') : !!force;
    sb.classList.toggle('open', open);
    if (ov) ov.style.display = open ? 'block' : 'none';
  }

  function init() {
    var menuBtn = document.getElementById('menu-btn');
    if (menuBtn) menuBtn.addEventListener('click', function() { toggle(); });
    var overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.addEventListener('click', function() { toggle(false); });
    /* Close the drawer after tapping a nav item (fetta E5 Task 3: l'elenco
       bot -- .agent-item -- e' uscito dalla sidebar, non c'e' piu' niente da
       scegliere li' dentro). */
    var sb = document.getElementById('sidebar');
    if (sb) sb.addEventListener('click', function(e) {
      var hit = e.target.closest('.sb-nav-item');
      if (hit && window.matchMedia('(max-width: 720px)').matches) toggle(false);
    });
  }

  window.HirisChatSidebar = { toggle: toggle, init: init };
})();
