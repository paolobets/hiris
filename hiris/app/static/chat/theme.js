/* HIRIS · Chat page · theme toggle (SP-4 Fase B Task 8)
   Il tema si legge e si scrive in common.js (`applyTheme`, `currentTheme`,
   `toggleTheme`), lo stesso per le due pagine (registro C-16). Restano qui
   solo l'icona sole/luna e l'aggancio del clic: the chat page button uses
   .ic-sun/.ic-moon classes inside a single <button>, a different DOM shape
   than the config SPA's #ic-sun/#ic-moon (see config/main.js::mountChrome),
   so there is nothing generic left to share once the icon markup differs. */
(function() {
  function paint() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    var t = currentTheme();
    var sun = btn.querySelector('.ic-sun');
    var moon = btn.querySelector('.ic-moon');
    if (sun) sun.style.display = (t === 'dark') ? '' : 'none';
    if (moon) moon.style.display = (t === 'dark') ? 'none' : '';
  }

  function wireToggle() {
    document.addEventListener('click', function(e) {
      var btn = e.target.closest && e.target.closest('#theme-toggle');
      if (!btn) return;
      toggleTheme();
      paint();
    });
  }

  async function init() {
    await applyTheme();
    paint();
    wireToggle();
  }

  window.HirisChatTheme = { init: init, paint: paint };
})();
