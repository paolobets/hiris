/* HIRIS · build-check · condiviso dalle due pagine (chat e configurazione).

   Task B8, dal fatto misurato il 14 agosto: il proprietario aveva la 3.0.0
   installata e in esecuzione, la pagina Modelli mostrava i TESTI nuovi (dal
   backend) ma non il bottone "Mettilo primo" (nel JavaScript). Ha risolto
   svuotando i dati del sito. Riprodotto in negativo con Playwright: il
   bottone c'era nel DOM, visibile -- quindi non era ne' il backend ne' il
   codice sorgente.

   Il buco: gli asset sono fingerprintati (?v=HASH) e non vanno mai in cache
   HTTP stantia, ma il guscio HTML e' l'UNICO file che CONTIENE quegli hash,
   ed e' servito no-store -- che vincola la cache HTTP, non un service
   worker. HIRIS gira dentro l'interfaccia di Home Assistant, una PWA col suo
   service worker: un guscio vecchio chiede gli script vecchi PER NOME, e la
   rivalidazione degli asset non serve a niente.

   Il pezzo che mancava esisteva gia': `app["build_stamp"]` (server.py) e'
   l'hash del contenuto del frontend, restituito da GET api/health e gia'
   mostrato a schermo da chat/main.js -- ma nessuno lo confrontava con
   niente. Da questo task, server._inject_version scrive nel guscio servito
   una `<meta name="hiris-build" content="...">` con quello stesso valore
   (una fonte sola, non ricalcolato qui): questo modulo la legge e la
   confronta col `build` che GET api/health restituisce in quel momento.

   Limite dichiarato, e non aggirabile: un guscio GIA' vecchio ha caricato
   anche il JavaScript vecchio, che questo controllo non contiene. Il
   meccanismo protegge dalla prima build che lo contiene in poi -- un client
   fermo a una build precedente a questa non puo' autodiagnosticarsi, ed e'
   per questo che il server logga lato suo (server.py, richiesta di un asset
   con un'impronta ?v= stantia): quella riga funziona SUBITO, anche coi
   client vecchi. Qui non si prova a "riparare" un client vecchio: si prova
   solo a impedire che, ANDANDO AVANTI, lo stesso buco si ripeta senza che
   nessuno se ne accorga. */
(function () {
  var GUARD_KEY = 'hiris-build-reload-guard';

  function letturaLocale() {
    var meta = document.querySelector('meta[name="hiris-build"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function mostraStriscia(locale, remoto) {
    if (document.getElementById('hiris-build-mismatch')) return; // gia' mostrata
    var div = document.createElement('div');
    div.id = 'hiris-build-mismatch';
    div.setAttribute('role', 'alert');
    div.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:99999;' +
      'background:#b91c1c;color:#fff;padding:10px 16px;' +
      'font:14px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;' +
      'text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.3);';
    div.textContent =
      'questa interfaccia viene da un build diverso da quello in esecuzione ' +
      '(' + locale + ' invece di ' + remoto + '): svuota i dati del sito di Home Assistant';
    if (document.body) document.body.appendChild(div);
  }

  /* Punto di innesto per i test: window.location.reload() non e' sovrascrivibile
     in jsdom (proprieta' non scrivibile sul prototipo di Location -- una
     riassegnazione diretta fallisce in silenzio), quindi il verificatore vero
     non chiama mai window.location.reload direttamente. Stesso pattern di
     `_internal_routes` in config/router.js: esposto SOLO per i test. */
  function _internal_reload() {
    window.location.reload();
  }

  /* Confronta il build dichiarato dal guscio (la <meta>, immutabile per
     tutta la vita di QUESTA pagina caricata) col build che il server
     restituisce ORA (GET api/health, la verita' vivente).

     - Combaciano: nessun rumore, nessuna riga -- e la guardia si libera,
       cosi' un disallineamento futuro (un'altra build) puo' di nuovo tentare
       un ricaricamento invece di trovare la guardia gia' scattata per un
       valore che non e' piu' quello in gioco.
     - Diversi, prima volta per QUESTO guscio: un ricaricamento, uno solo --
       la guardia (sessionStorage, sopravvive al reload, muore col tab) si
       marca con l'esatto build locale che ha tentato.
     - Diversi, guardia gia' marcata per QUESTO build locale: il ricaricamento
       non ha risolto niente (il service worker ha riservito lo stesso guscio
       vecchio) -- niente secondo tentativo, si dichiara con la striscia. Un
       anello di ricaricamenti sarebbe un guasto peggiore di quello che questo
       meccanismo chiude. */
  function verifica(remoto) {
    var locale = letturaLocale();
    if (!locale || !remoto || locale === remoto) {
      try { sessionStorage.removeItem(GUARD_KEY); } catch (e) {}
      return;
    }
    var giaTentato = false;
    try { giaTentato = sessionStorage.getItem(GUARD_KEY) === locale; } catch (e) {}
    if (!giaTentato) {
      try { sessionStorage.setItem(GUARD_KEY, locale); } catch (e) {}
      window.HirisBuildCheck._internal_reload();
      return;
    }
    mostraStriscia(locale, remoto);
  }

  window.HirisBuildCheck = {
    verifica: verifica,
    _internal_reload: _internal_reload, /* exposed for test only */
  };
})();
