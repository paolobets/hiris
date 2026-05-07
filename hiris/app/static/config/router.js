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
