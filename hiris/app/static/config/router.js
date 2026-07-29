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
        try {
          r.handler(m);
        } catch(e) {
          console.error('route handler error', e);
          /* Review finale pre-1.0, finding I3 (Important): NON marcare
             lastResolvedHash quando l'handler lancia. Prima veniva
             comunque scritto (nel blocco try/catch/finally implicito che
             seguiva SEMPRE, errore o no) -- una route andata in errore
             risultava "già risolta", quindi ridispacciare lo stesso hash
             (il solo modo che l'utente ha per "riprovare": dashboard.js e
             usage-route.js non hanno un bottone Riprova dedicato, vedi i
             rispettivi commenti) faceva early-return alla riga sopra senza
             richiamare l'handler -- nessun modo di ritentare senza un hard
             reload. Ritornando qui SENZA aggiornare lastResolvedHash (né
             HirisState.route, sotto), un secondo dispatch dello stesso
             hash rientra nel for e richiama di nuovo r.handler(m). */
          return;
        }
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
