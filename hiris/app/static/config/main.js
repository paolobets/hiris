/* HIRIS · configurazione · bootstrap: cornice (sidebar + header) e route. */
(function() {
  /* fetta E5 Task 6: qui viveva l'installazione del guard di navigazione
     (HirisEditorKit.dirty.guard) contro le modifiche non salvate. E' uscita
     insieme a editor-kit.js e ai tre editor che la usavano (Chatbot,
     Agentbot, wizard): in questa SPA non c'e' piu' nessuna pagina che possa
     avere modifiche pendenti da perdere -- le due che scrivono
     (#/impostazioni e #/models) salvano al click, senza stato "sporco". Un
     `if (window.HirisEditorKit)` su un modulo che non esiste piu' sarebbe
     una dichiarazione falsa, non una degradazione. */

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
    function paint(t) {
      document.documentElement.setAttribute('data-theme', t);
      try { localStorage.setItem('hiris-theme', t); } catch(e) {}
      /* v0.10.4: usa visibility (non display) per evitare FOUC.
         Template inizia con entrambe icone hidden via style="visibility:hidden". */
      if (moon) moon.style.visibility = t === 'dark' ? 'hidden' : 'visible';
      if (sun) sun.style.visibility = t === 'dark' ? 'visible' : 'hidden';
    }
    var current = document.documentElement.getAttribute('data-theme') ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    paint(current);
    if (btn) btn.addEventListener('click', function() {
      paint(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
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
        (route === 'conoscenza' && (hash === '#/' || hash === '')) ||
        (route === 'albero' && hash.indexOf('#/albero') === 0) ||
        (route === 'memoria' && hash.indexOf('#/memoria') === 0) ||
        (route === 'promesse' && hash.indexOf('#/promesse') === 0) ||
        (route === 'costruzioni' && hash.indexOf('#/costruzioni') === 0) ||
        (route === 'osservatore' && hash.indexOf('#/osservatore') === 0) ||
        (route === 'usage' && hash.indexOf('#/usage') === 0) ||
        (route === 'models' && hash.indexOf('#/models') === 0) ||
        /* fetta E5 Task 2: qui c'era un ramo `settings` orfano -- nessuna
           voce di nav con data-route="settings" (tolta in v0.10.5) e nessuna
           route `#/settings` registrata sotto, quindi la condizione non
           poteva essere vera per nessun elemento. Non se ne aggiunge un
           secondo accanto: quel ramo diventa questo, l'unico, sulla pagina
           che ora esiste davvero. */
        (route === 'impostazioni' && hash.indexOf('#/impostazioni') === 0);
      item.classList.toggle('active', isActive);
    });
  }

  function setCrumbHere(text) {
    var here = document.getElementById('chrome-here');
    if (here) here.textContent = text;
  }

  /* Le route della SPA di configurazione. Ognuna ha una voce di nav in
     config.html (tranne nessuna: il rapporto e' 1:1 dopo la fetta E5
     Task 6) e un modulo che la monta; il ramo `else` e' il degrado se lo
     script del modulo non ha caricato. */
  HirisRouter.register(/^#\/?$/, function() {
    setCrumbHere('Cosa HIRIS sa');
    if (window.HirisDashboard) {
      HirisDashboard.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<div class="page-title">Cosa HIRIS sa</div><p class="page-subtitle">Caricamento…</p>';
    }
  });
  /* Reperto 26: la faccia di `casa.piani` -- vedi config/albero-route.js
     per il perché. */
  HirisRouter.register(/^#\/albero\/?$/, function() {
    setCrumbHere('Albero della casa');
    if (window.HirisAlberoRoute) {
      HirisAlberoRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Albero della casa</div>';
    }
  });
  /* fetta E5 Task 9: sostituisce il pannello Memoria della chat -- vedi
     config/memoria-route.js per il perché. */
  HirisRouter.register(/^#\/memoria\/?$/, function() {
    setCrumbHere('Memoria');
    if (window.HirisMemoriaRoute) {
      HirisMemoriaRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Memoria</div>';
    }
  });
  /* fetta «lo schedulatore» Task 9: la pagina #/promesse -- vedi
     config/promesse-route.js per il perche'. Una sola rotta: la pagina
     legge UNA GET /api/promesse?tutte=1 e filtra lì per `stato`, invece di
     chiederne due -- lo stato di una promessa è un campo, non un
     endpoint. */
  HirisRouter.register(/^#\/promesse\/?$/, function() {
    setCrumbHere('Promesse');
    if (window.HirisPromesseRoute) {
      HirisPromesseRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Promesse</div>';
    }
  });
  /* fetta «costruire» Task 11: la pagina #/costruzioni -- vedi
     config/costruzioni-route.js per il perche'. `mount(outlet)` porta il
     proprio outlet, a differenza delle altre route qui sopra: e' l'unico
     modulo di questa SPA con quella firma, pinnata dal Task 11. */
  HirisRouter.register(/^#\/costruzioni\/?$/, function() {
    setCrumbHere('Costruzioni');
    if (window.HirisCostruzioni) {
      HirisCostruzioni.mount(document.getElementById('route-outlet'));
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Costruzioni</div>';
    }
  });
  /* fetta «l'osservatore» Task 7: la pagina #/osservatore -- vedi
     config/osservatore-route.js per il perche'. `mount()` senza argomenti,
     legge da solo `#route-outlet`: stesso pattern di albero-route.js e
     memoria-route.js, non quello di costruzioni-route.js (che porta
     l'outlet come parametro). */
  HirisRouter.register(/^#\/osservatore\/?$/, function() {
    setCrumbHere('L’osservatore');
    if (window.HirisOsservatoreRoute) {
      HirisOsservatoreRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">L’osservatore</div>';
    }
  });
  HirisRouter.register(/^#\/usage\/?$/, function() {
    setCrumbHere('Consumi');
    if (window.HirisUsageRoute) {
      HirisUsageRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Consumi</div>';
    }
  });
  HirisRouter.register(/^#\/models\/?$/, function() {
    setCrumbHere('Modelli');
    if (window.HirisModelsRoute) {
      HirisModelsRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Modelli</div>';
    }
  });
  /* fetta "esce il documentale": qui era registrata la route #/history
     (Storicizzazione). Esce con la pagina, il suo modulo
     (config/history-route.js) e le rotte /api/history/policy. */
  /* fetta E5 Task 2: la route che in v0.10.5 era stata rimossa perché
     placeholder vuoto (`#/settings`, «Implementata in Phase 11») rinasce qui
     con contenuto reale e con il nome italiano del resto della fetta:
     `#/impostazioni`, i sette campi di ImpostazioniChat. */
  HirisRouter.register(/^#\/impostazioni\/?$/, function() {
    setCrumbHere('Impostazioni chat');
    if (window.HirisImpostazioniRoute) {
      HirisImpostazioniRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<div class="page-title">Impostazioni chat</div>';
    }
  });

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

  document.addEventListener('DOMContentLoaded', function() {
    mountChrome();
    checkBuild();
    window.addEventListener('hashchange', updateNavActive);
    HirisState.subscribe('route', updateNavActive);
    HirisRouter.start();
    updateNavActive();
  });
})();
