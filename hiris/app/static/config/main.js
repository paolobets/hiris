/* HIRIS · configurazione · bootstrap: cornice (sidebar + header) e route. */
(function() {
  function mountChrome() {
    var sn = document.getElementById('side-nav');
    var pc = document.getElementById('page-chrome');
    sn.innerHTML = '';
    sn.appendChild(document.getElementById('tpl-side-nav').content.cloneNode(true));
    pc.innerHTML = '';
    pc.appendChild(document.getElementById('tpl-page-chrome').content.cloneNode(true));

    /* Off-canvas drawer (mobile ≤768px): hamburger opens the side-nav. */
    var menuBtn = document.getElementById('cfg-menu-btn');
    var overlay = document.getElementById('sidenav-overlay');
    function toggleNav(open) {
      var snEl = document.getElementById('side-nav');
      if (!snEl) return;
      var o = (open === undefined) ? !snEl.classList.contains('open') : !!open;
      snEl.classList.toggle('open', o);
      if (overlay) overlay.style.display = o ? 'block' : 'none';
      if (menuBtn) menuBtn.setAttribute('aria-expanded', o ? 'true' : 'false');
    }
    if (menuBtn) menuBtn.addEventListener('click', function () { toggleNav(); });
    if (overlay) overlay.addEventListener('click', function () { toggleNav(false); });
    /* C1 (audit 2026-08-24): bottone di chiusura esplicito in cima al
       cassetto, nello stesso angolo dell'hamburger che il cassetto copre
       da sotto. */
    var closeBtn = document.getElementById('sidenav-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', function () { toggleNav(false); });
    sn.addEventListener('click', function (e) {
      if (e.target.closest('.nav-item') && window.matchMedia('(max-width: 768px)').matches) toggleNav(false);
    });

    /* Theme toggle */
    var btn = document.getElementById('theme-toggle');
    var moon = document.getElementById('ic-moon');
    var sun = document.getElementById('ic-sun');
    /* Il tema si legge e si scrive in common.js (registro C-16); qui si
       disegna solo l'icona, che in questa pagina e' fatta a modo suo.
       v0.10.4: usa visibility (non display) per evitare FOUC.
       Template inizia con entrambe icone hidden via style="visibility:hidden". */
    function paint() {
      var t = currentTheme();
      /* Questa pagina ha sempre scritto il tema sull'attributo anche quando
         veniva dal sistema, e alcune regole scure dei fogli di stile
         (`[data-theme="dark"]`) non hanno un gemello sotto
         `prefers-color-scheme`: senza attributo la pagina si disegnerebbe
         diversa. Si dichiara il tema mostrato, senza salvarlo: salvare
         resta al clic. */
      document.documentElement.setAttribute('data-theme', t);
      if (moon) moon.style.visibility = t === 'dark' ? 'hidden' : 'visible';
      if (sun) sun.style.visibility = t === 'dark' ? 'visible' : 'hidden';
    }
    paint();
    /* Il tema del server vale anche qui, come nella chat: prima questa
       pagina non lo chiedeva mai (registro C-16). */
    applyTheme().then(paint);
    if (btn) btn.addEventListener('click', function() {
      toggleTheme();
      paint();
    });

    /* fetta E5 Task 8: qui viveva l'ultimo badge della cornice, `#nav-adv-count`
       sulla voce Dashboard. Interrogava `api/brain/advisories?status=open`, una
       rotta uscita con la fetta E3 Task 6, e degradava in SILENZIO: il `.catch`
       vuoto lasciava il badge a «—» e il ramo `r.ok ? ... : {advisories: []}`
       scriveva `0` su un 404. Cioe' l'utente non poteva distinguere «nessuna
       segnalazione» da «la rotta non esiste piu'» -- il difetto ricorrente n.1
       di questo prodotto, dentro la cornice stessa. Non si sostituisce con un
       altro contatore: la home ora e' «Cosa HIRIS sa», e cio' che HIRIS ignora
       si legge nella pagina, con la sua fonte accanto, non in un numero senza
       fonte appiccicato alla voce di menu. La cornice non fa piu' nessuna
       fetch. */
  }

  function updateNavActive() {
    var hash = window.location.hash || '#/';
    document.querySelectorAll('.nav-item[data-route]').forEach(function(item) {
      var route = item.getAttribute('data-route');
      var isActive =
        (route === 'knowledge' && (hash === '#/' || hash === '')) ||
        (route === 'tree' && hash.indexOf('#/tree') === 0) ||
        (route === 'memory' && hash.indexOf('#/memory') === 0) ||
        (route === 'agenda' && hash.indexOf('#/agenda') === 0) ||
        (route === 'constructions' && hash.indexOf('#/constructions') === 0) ||
        (route === 'watcher' && hash.indexOf('#/watcher') === 0) ||
        (route === 'usage' && hash.indexOf('#/usage') === 0) ||
        (route === 'models' && hash.indexOf('#/models') === 0) ||
        (route === 'services' && hash.indexOf('#/services') === 0) ||
        /* fetta E5 Task 2: qui c'era un ramo `settings` orfano -- nessuna
           voce di nav con data-route="settings" (tolta in v0.10.5) e nessuna
           route `#/settings` registrata sotto, quindi la condizione non
           poteva essere vera per nessun elemento. Non se ne aggiunge un
           secondo accanto: quel ramo diventa questo, l'unico, sulla pagina
           che ora esiste davvero.
           02/09: da questa fetta la route si chiama `#/settings` per davvero
           (era `#/impostazioni`), quindi il nome del ramo e quello dell'hash
           coincidono di nuovo -- il paragrafo qui sopra resta perche' e' la
           misura di allora, non una descrizione di oggi. */
        (route === 'settings' && hash.indexOf('#/settings') === 0);
      item.classList.toggle('active', isActive);
    });
  }

  function setCrumbHere(text) {
    var here = document.getElementById('chrome-here');
    if (here) here.textContent = text;
  }

  /* ── Chi non configura (spec 2026-09-27 §4) ─────────────────────────
     Per lui il guscio e' Impegni e Memoria: le altre voci portano
     `data-configure-only` (config.html) e le spegne static/pending-badge.js.
     Una pagina di configurazione aperta per indirizzo non si monta -- non
     chiede i suoi dati (security-constraints 4.5) e non disegna moduli che
     il server rifiuterebbe al salvataggio -- e dice il rifiuto del SERVER,
     che arriva nella stessa risposta di `api/pending` (`configure_refusal`,
     la costante del cancello: fix round 1 del Task 4).

     **Una regola sola, chiusa nel dubbio** (fix round 1): si configura solo
     col `true` detto dal server o dal ricordo. Senza il pallino, o finche'
     non si sa, no -- come la Memoria (config/memory-route.js). Un
     amministratore non lo vede: senza ricordo il guscio aspetta la prima
     risposta prima di scegliere la pagina (sotto, `ROUTER_WAIT_MS`). La
     regola e' `configures()` di common.js, la stessa della Memoria. */

  /* Mai una pagina vuota: il titolo, il testo del server quando c'e' (un
     «no» ricordato arriva senza, e la pagina si ridisegna quando la risposta
     lo porta) e una strada per uscire. Tutto via `textContent`. */
  function renderRefusal(title) {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    while (outlet.firstChild) outlet.removeChild(outlet.firstChild);
    var h1 = document.createElement('h1');
    h1.className = 'page-title';
    h1.textContent = title;
    outlet.appendChild(h1);
    var text = window.HirisPendingBadge ? window.HirisPendingBadge.configureRefusal() : '';
    if (text) {
      var reason = document.createElement('p');
      reason.className = 'page-subtitle';
      reason.textContent = text;
      outlet.appendChild(reason);
    }
    var exit = document.createElement('p');
    exit.className = 'page-subtitle';
    var link = document.createElement('a');
    link.href = '#/agenda';
    link.textContent = 'Vai agli Impegni';
    exit.appendChild(link);
    outlet.appendChild(exit);
  }

  /* Una route di configurazione: la briciola la scrive il guscio per
     entrambi i rami, il titolo e' lo stesso, montata o rifiutata. */
  function configureOnlyRoute(title, mount) {
    return function (m) {
      setCrumbHere(title);
      if (configures()) mount(m);
      else renderRefusal(title);
    };
  }

  /* Le route della SPA di configurazione. Ognuna ha una voce di nav in
     config.html (tranne nessuna: il rapporto e' 1:1 dopo la fetta E5
     Task 6) e un modulo che la monta; il ramo `else` e' il degrado se lo
     script del modulo non ha caricato. */
  HirisRouter.register(/^#\/?$/, function() {
    /* La home di chi non configura -- e di chi non si sa -- sono gli
       Impegni: «Cosa HIRIS sa» legge `api/home-space` e `api/briefing`, che
       il cancello gli chiude. */
    if (!configures()) return '#/agenda';
    setCrumbHere('Cosa HIRIS sa');
    if (window.HirisDashboard) {
      HirisDashboard.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<h1 class="page-title">Cosa HIRIS sa</h1><p class="page-subtitle">Caricamento…</p>';
    }
  });
  /* Reperto 26: la faccia di `casa.piani` -- vedi config/tree-route.js
     per il perché. */
  HirisRouter.register(/^#\/tree\/?$/, configureOnlyRoute('Albero della casa', function() {
    if (window.HirisTreeRoute) {
      HirisTreeRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Albero della casa</h1>';
    }
  }));
  /* fetta E5 Task 9: sostituisce il pannello Memoria della chat -- vedi
     config/memory-route.js per il perché. */
  HirisRouter.register(/^#\/memory\/?$/, function() {
    setCrumbHere('Memoria');
    if (window.HirisMemoryRoute) {
      HirisMemoryRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Memoria</h1>';
    }
  });
  /* fetta «lo schedulatore» Task 9: la pagina #/agenda -- vedi
     config/agenda-route.js per il perche'. Una sola rotta: la pagina
     legge UNA GET /api/agenda?all=1 e filtra lì per `stato`, invece di
     chiederne due -- lo stato di una promessa è un campo, non un
     endpoint. */
  HirisRouter.register(/^#\/agenda\/?$/, function() {
    setCrumbHere('Impegni');
    if (window.HirisAgendaRoute) {
      HirisAgendaRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Impegni</h1>';
    }
  });
  /* fetta «costruire» Task 11: la pagina #/constructions -- vedi
     config/constructions-route.js per il perche'. `mount(outlet)` porta il
     proprio outlet, a differenza delle altre route qui sopra: e' l'unico
     modulo di questa SPA con quella firma, pinnata dal Task 11. */
  HirisRouter.register(/^#\/constructions\/?$/, function() {
    setCrumbHere('Proposte');
    if (window.HirisConstructions) {
      HirisConstructions.mount(document.getElementById('route-outlet'));
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Proposte</h1>';
    }
  });
  /* fetta «la pagina dell'osservatore» (18/09/2026): quattro schede, quattro
     indirizzi. `#/watcher` nudo resta valido -- un segnalibro vecchio non
     trova «Pagina non trovata» -- e il guscio lo riscrive su «giorno» senza
     aggiungere una voce di cronologia. `updateNavActive` non cambia: guarda
     gia' `hash.indexOf('#/watcher') === 0`, quindi tutte e quattro le schede
     accendono la stessa voce di menu (una voce, schede: decisione 2).
     `mount(scheda)` legge da solo `#route-outlet`: stesso pattern di
     tree-route.js e memory-route.js, non quello di constructions-route.js
     (che porta l'outlet come parametro). */
  HirisRouter.register(/^#\/watcher(?:\/(giorno|cosa-fare|sapere|lavoro))?\/?$/, configureOnlyRoute('L’osservatore', function(m) {
    if (window.HirisWatcherRoute) {
      HirisWatcherRoute.mount(m && m[1]);
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">L’osservatore</h1>';
    }
  }));
  HirisRouter.register(/^#\/usage\/?$/, configureOnlyRoute('Consumi', function() {
    if (window.HirisUsageRoute) {
      HirisUsageRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Consumi</h1>';
    }
  }));
  HirisRouter.register(/^#\/models\/?$/, configureOnlyRoute('Modelli', function() {
    if (window.HirisModelsRoute) {
      HirisModelsRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<h1 class="page-title">Modelli</h1>';
    }
  }));
  /* fetta «l'accoppiamento» (22/09/2026): la pagina dei servizi esterni --
     vedi config/services-route.js per il perche'. E' l'unica route di questa
     SPA che si RILEGGE da sola: le righe in attesa arrivano da un'altra
     macchina mentre la finestra e' aperta, e chi dovesse ricaricare per
     vederle penserebbe che l'accoppiamento non funziona. Il giro si ferma da
     se' quando la finestra si chiude o quando si lascia la pagina. */
  HirisRouter.register(/^#\/services\/?$/, configureOnlyRoute('Servizi', function() {
    if (window.HirisServicesRoute) {
      HirisServicesRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<h1 class="page-title">Servizi</h1>';
    }
  }));
  /* fetta "esce il documentale": qui era registrata la route #/history
     (Storicizzazione). Esce con la pagina, il suo modulo
     (config/history-route.js) e le rotte /api/history/policy. */
  /* fetta E5 Task 2: la route che in v0.10.5 era stata rimossa perché
     placeholder vuoto (`#/settings`, «Implementata in Phase 11») rinasce qui
     con contenuto reale e con il nome italiano del resto della fetta:
     `#/settings`, i sette campi di ChatSettings. */
  HirisRouter.register(/^#\/settings\/?$/, configureOnlyRoute('Impostazioni chat', function() {
    if (window.HirisSettingsRoute) {
      HirisSettingsRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<h1 class="page-title">Impostazioni chat</h1>';
    }
  }));

  /* Task B8: la pagina Modelli mostrava i testi nuovi (dal backend) senza il
     bottone nuovo (nel JavaScript) -- il guscio HTML era rimasto vecchio
     sotto un service worker che serve file per nome, non per contenuto.
     Confronta la <meta name="hiris-build"> di QUESTO guscio (scritta da
     server._inject_version) col build che il server dice di eseguire ORA
     (GET api/health). Nessun'altra pagina della SPA di configurazione lo
     rifa': una sola verifica all'avvio basta, e' il guscio che invecchia,
     non la route dentro di esso. */
  function checkBuild() {
    return fetch('api/health').then(function(r) {
      if (!r.ok) throw new Error('api/health: ' + r.status);
      return r.json();
    }).then(function(d) {
      window.HirisBuildCheck.verifica(d.build);
    }).catch(function() { /* nessun health, nessuna verifica possibile: silenzio */ });
  }

  var routerStarted = false;

  /* Quanto si aspetta la prima risposta di `api/pending` prima di scegliere
     la pagina senza saperla: una richiesta appesa non deve lasciare il
     guscio bianco (fix round 1, F1). Scaduta l'attesa si parte chiusi -- gli
     Impegni -- e una risposta che arriva dopo rimonta la pagina. */
  var ROUTER_WAIT_MS = 3000;

  function startRouter() {
    if (routerStarted) return;
    routerStarted = true;
    HirisRouter.start();
    updateNavActive();
  }

  document.addEventListener('DOMContentLoaded', function() {
    mountChrome();
    checkBuild();
    window.addEventListener('hashchange', updateNavActive);
    HirisState.subscribe('route', updateNavActive);
    /* Il pallino DOPO `mountChrome()`: le voci di menu nascono da
       `tpl-side-nav`, e prima di quella riga i due `data-badge` non
       esistono ancora nel DOM -- il pallino non troverebbe dove attaccarsi
       e non lo direbbe a nessuno (per disegno: non e' un guasto che una
       pagina non abbia quelle voci). E PRIMA del router: la pagina
       d'atterraggio dipende da `can_configure`. */
    var badge = window.HirisPendingBadge;
    if (!badge) { startRouter(); return; }
    /* Il router parte al primo `can_configure` saputo -- dal ricordo, gia'
       dentro `mount`, o da una risposta, anche una successiva alla prima
       (il ritorno del fuoco) -- oppure allo scadere dell'attesa, o se la
       prima risposta fallisce. Dopo, un cambio rimonta la pagina aperta:
       quella rifiutata diventa vera, quella vera diventa il rifiuto. */
    badge.onChange(function (field, granted) {
      if (field !== 'can_configure') return;
      if (routerStarted) HirisRouter.refresh();
      else if (granted !== null) startRouter();
    });
    badge.mount().then(startRouter);
    setTimeout(startRouter, ROUTER_WAIT_MS);
  });
})();
