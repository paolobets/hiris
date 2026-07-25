/* HIRIS · Designer · hash router minimal */
(function() {
  var routes = [];

  function resolveRoute() {
    var hash = window.location.hash || '#/';
    for (var i = 0; i < routes.length; i++) {
      var r = routes[i];
      var m = hash.match(r.pattern);
      if (m) {
        try { r.handler(m); } catch(e) { console.error('route handler error', e); }
        HirisState.set('route', { hash: hash, pattern: String(r.pattern) });
        return;
      }
    }
    console.warn('no route matched', hash);
    renderNotFound();
  }

  function renderNotFound() {
    var here = document.getElementById('chrome-here');
    if (here) here.textContent = 'Pagina non trovata';
    var outlet = document.getElementById('route-outlet');
    if (outlet) {
      outlet.innerHTML =
        '<div class="page-title">Pagina non trovata</div>' +
        '<p class="page-subtitle">La pagina richiesta non esiste. <a href="#/">Torna alla Dashboard</a></p>';
    }
  }

  window.HirisRouter = {
    register: function(pattern, handler) {
      routes.push({ pattern: pattern, handler: handler });
    },
    start: function() {
      window.addEventListener('hashchange', resolveRoute);
      resolveRoute();
    },
    navigate: function(hash) {
      window.location.hash = hash;
    },
    _internal_routes: routes, /* exposed for test only */
  };
})();
