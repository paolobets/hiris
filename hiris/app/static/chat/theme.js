/* HIRIS · Chat page · theme toggle (SP-4 Fase B Task 8)
   Initial theme resolution (localStorage > server config > system) is
   shared with the config SPA via config/api.js::applyTheme() -- the page's
   private copy was removed by this rebuild. Painting the sun/moon icon and
   wiring the click-to-toggle stay page-local: the chat page button uses
   .ic-sun/.ic-moon classes inside a single <button>, a different DOM shape
   than the config SPA's #ic-sun/#ic-moon (see config/main.js::mountChrome),
   so there is nothing generic left to share once the icon markup differs. */
(function() {
  function currentTheme() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

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
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('hiris-theme', next); } catch (e) {}
      paint();
    });
  }

  async function init() {
    await applyTheme();
    paint();
    wireToggle();
  }

  window.HirisChatTheme = { init: init, paint: paint, currentTheme: currentTheme };
})();
