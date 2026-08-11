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
        (route === 'usage' && hash.indexOf('#/usage') === 0) ||
        (route === 'models' && hash.indexOf('#/models') === 0) ||
        (route === 'history' && hash.indexOf('#/history') === 0) ||
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
  HirisRouter.register(/^#\/history\/?$/, function() {
    setCrumbHere('Storicizzazione');
    if (window.HirisHistoryRoute) {
      HirisHistoryRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Storicizzazione</div>';
    }
  });
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

  document.addEventListener('DOMContentLoaded', function() {
    mountChrome();
    window.addEventListener('hashchange', updateNavActive);
    HirisState.subscribe('route', updateNavActive);
    HirisRouter.start();
    updateNavActive();
  });
})();
