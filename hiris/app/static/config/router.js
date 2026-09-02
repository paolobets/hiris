/* HIRIS · Config · hash router minimal */
(function() {
  var routes = [];
  /* Ultimo hash effettivamente risolto (route handler invocata). Serve a
     ignorare l'"eco" di un hashchange: quando qualcosa riporta
     window.location.hash al valore corrente, il browser genera un secondo
     hashchange verso lo STESSO hash, e senza questo controllo
     resolveRoute() rimonterebbe la route corrente azzerandone lo stato.
     Storia: il caso reale era il guard di navigazione contro le modifiche
     non salvate (uscito con editor-kit.js alla fetta E5 Task 6, insieme ai
     tre editor che lo usavano); il meccanismo resta perche' vale per
     qualunque riscrittura dell'hash, non solo per quel guard, ed e'
     pinnato da tests/js/router-retry.test.mjs. Un hashchange verso un hash
     DIVERSO aggiorna sempre lastResolvedHash piu' sotto, quindi ogni
     navigazione vera (anche "vai altrove e poi torna sulla stessa route")
     monta regolarmente. */
  var lastResolvedHash = null;

  /* ── Gli indirizzi DI PRIMA ───────────────────────────────────
     Fino alla fetta della rinomina (02/09) le sei pagine italiane avevano
     un hash italiano. L'hash si vede nella barra del browser e finisce nei
     SEGNALIBRI: su questa casa la porta 8099 puo' essere esposta da Home
     Assistant (`config.yaml`, `ports`), quindi
     `http://<casa>:8099/config.html#/promesse` e' un URL stabile che
     qualcuno puo' aver salvato -- e anche sotto ingress il token di
     percorso dell'add-on sopravvive alle sessioni. Rinominare senza questa
     tabella avrebbe risposto «Pagina non trovata» a un segnalibro valido.

     **CONDIZIONE D'USCITA**: questa tabella si toglie il giorno in cui
     nessun segnalibro in circolazione punta piu' a un hash italiano. Come
     per l'avviso sui nomi vecchi degli strumenti
     (`agent/prompts.py::_OLD_NAMES_NOTICE`), quel giorno **si misura
     sull'USO, non su questo repository**: qui dentro non resta nessun hash
     italiano gia' da oggi, quindi il repository direbbe «togliila» subito e
     avrebbe torto. Quando si toglie, si toglie insieme a
     `tests/js/router-alias.test.mjs`, che e' scritto per andare rosso se la
     tabella si svuota -- il suo rosso E' il promemoria.

     La meta' ESEGUIBILE della condizione vive li': ogni bersaglio deve
     essere una route che `main.js` registra davvero (altrimenti la tabella
     manderebbe un segnalibro valido su una pagina che non c'e' piu', in
     silenzio), e nessuna sorgente puo' essere a sua volta una route viva
     (altrimenti la tabella ne oscurerebbe una vera). ────────────────── */
  var HASH_DI_PRIMA = {
    '#/albero': '#/tree',
    '#/memoria': '#/memory',
    '#/promesse': '#/agenda',
    '#/costruzioni': '#/constructions',
    '#/osservatore': '#/watcher',
    '#/impostazioni': '#/settings',
  };

  /* `history.replaceState` e NON `window.location.hash = ...`, per due
     ragioni misurate:
     1. assegnare l'hash aggiungerebbe una voce di cronologia, e il tasto
        «indietro» riporterebbe sull'hash vecchio, che rimanda avanti: un
        utente non potrebbe piu' tornare indietro;
     2. assegnare l'hash fa partire un `hashchange` ASINCRONO, quindi la
        route si monterebbe in un secondo giro invece che in questo. Con
        `replaceState` la correzione e' sincrona: si prosegue nello stesso
        `resolveRoute()` col nome nuovo, e la barra dice gia' il vero.
     Il ripiego per un browser senza `replaceState` assegna l'hash: il
     `hashchange` che ne segue viene assorbito da `lastResolvedHash`, che a
     quel punto vale gia' l'hash NUOVO. */
  function correggiHashDiPrima(hash) {
    var nudo = hash.replace(/\/$/, '');
    if (!Object.prototype.hasOwnProperty.call(HASH_DI_PRIMA, nudo)) return hash;
    var nuovo = HASH_DI_PRIMA[nudo];
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', nuovo);
    } else {
      window.location.hash = nuovo;
    }
    return nuovo;
  }

  function resolveRoute() {
    var hash = correggiHashDiPrima(window.location.hash || '#/');
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
        '<p class="page-subtitle">La pagina richiesta non esiste. <a href="#/">Torna a «Cosa HIRIS sa»</a></p>';
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
    _hash_di_prima: HASH_DI_PRIMA, /* exposed for test only */
  };
})();
