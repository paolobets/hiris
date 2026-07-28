/* HIRIS · Designer · hash router minimal */
(function() {
  var routes = [];
  /* Ultimo hash effettivamente risolto (route handler invocata). Chiude il
     bug live #2 (guard di navigazione, editor-kit.js dirty.guard()): quando
     l'utente RIFIUTA di uscire con modifiche non salvate, il guard ripristina
     window.location.hash all'hash corrente -- ma quel ripristino genera un
     SECONDO hashchange (l'"eco"), sul quale il guard stesso non richiama più
     stopImmediatePropagation() (già "consumato" sul primo evento reale).
     Senza questo controllo, resolveRoute() rimonta la route CORRENTE su
     quell'eco -- mount() azzera lo stato (es. setupStickyActions in
     chatbot-editor.js resetta 'unsaved'), quindi scegliere "resta" perdeva
     comunque le modifiche. Un hashchange verso un hash DIVERSO aggiorna
     sempre lastResolvedHash più sotto, quindi ogni navigazione vera (anche
     "vai altrove e poi torna sulla stessa route") monta regolarmente. */
  var lastResolvedHash = null;

  function resolveRoute() {
    var hash = window.location.hash || '#/';
    if (hash === lastResolvedHash) return;
    for (var i = 0; i < routes.length; i++) {
      var r = routes[i];
      var m = hash.match(r.pattern);
      if (m) {
        try { r.handler(m); } catch(e) { console.error('route handler error', e); }
        lastResolvedHash = hash;
        HirisState.set('route', { hash: hash, pattern: String(r.pattern) });
        return;
      }
    }
    console.warn('no route matched', hash);
    lastResolvedHash = hash;
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
