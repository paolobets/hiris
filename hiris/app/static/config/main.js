/* HIRIS · Designer · bootstrap (Phase 4.1: chrome + nav active state) */
(function() {
  /* Guard di navigazione (bug live #2) -- hoistato qui dal Task 6 (SP-4
     Fase B). Prima era installato dal top-level IIFE di chatbot-editor.js:
     funzionava solo perché config.html carica SEMPRE quel file insieme a
     ogni route, non perché ogni editor fosse garantito protetto -- un
     accoppiamento strutturale fragile (una futura route/editor che non lo
     includesse resterebbe silenziosamente senza guard). Qui la garanzia è
     "per costruzione": main.js è l'ultimo script caricato da config.html
     ed è comune a OGNI route. 'unsaved' resta la chiave HirisState
     GLOBALE condivisa fra tutti gli editor (vedi C9 nel grounding) -- un
     solo guard() per l'intera pagina, mai uno per editor (altrimenti
     confirm() doppio -- vedi le note lasciate in chatbot-editor.js e
     agentbot-editor.js). Deve girare PRIMA che HirisRouter.start() (sotto,
     dentro DOMContentLoaded) registri il proprio listener 'hashchange':
     gira qui a livello top dell'IIFE, cioè al parse dello script --
     sempre prima che DOMContentLoaded scateni mountChrome()/
     HirisRouter.start(). */
  /* Secondo argomento (review finale pre-1.0, finding I2): quando l'utente
     CONFERMA di uscire da un editor con modifiche non salvate, pulisce
     'unsaved' -- senza, restava true dopo la navigazione e ogni click
     successivo fra pagine SENZA form (es. Consumi -> Task) ririchiedeva la
     stessa conferma a vuoto, finché l'utente non riapriva un editor
     (unico altro punto che lo azzerava, setupStickyActions).

     Guardia if(window.HirisEditorKit) (review finale pre-1.0, finding I5
     -- Important): questa chiamata gira al PARSE del file, prima che
     qualunque route si registri (vedi commento sopra) -- era l'unica
     chiamata cross-file di main.js SENZA existence-check (ogni altro
     window.HirisX qui sotto, es. HirisDashboard/HirisChatbotEditor/ecc.,
     è dietro un `if (window.HirisX)`). Se editor-kit.js fallisse il parse
     (sintassi rotta in un rilascio), questa riga lanciava un
     ReferenceError NON catturato al top-level dell'IIFE -- l'intero resto
     del file (tutte le HirisRouter.register() sotto + il DOMContentLoaded
     che chiama HirisRouter.start()) non veniva mai eseguito: l'intera SPA
     di config (Brain, Chatbot, Agentbot, Modelli, Gateway, Storico...)
     renderizzava bianca, senza alcun errore visibile in pagina (solo in
     console). Qui: se il kit manca, si salta silenziosamente
     l'installazione del guard (nessuna protezione da modifiche non
     salvate finché non si risolve il file rotto) invece di bloccare
     l'intera pagina -- degradazione, non crash totale. */
  if (window.HirisEditorKit && window.HirisEditorKit.dirty) {
    HirisEditorKit.dirty.guard(
      function() { return !!HirisState.get('unsaved'); },
      function() { HirisState.set('unsaved', false); }
    );
  }

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

    /* v0.10.5: fetch diretto invece di loadChatbots() (in chatbot-editor.js, caricato
       solo quando user apre editor). Al boot loadChatbots non è ancora definito,
       quindi badge restava "—" finché user non apriva un agente. */
    fetch('api/chatbots').then(function(r) { return r.ok ? r.json() : []; })
      .then(function(d) {
        var agents = Array.isArray(d) ? d : (d.agents || []);
        var el = document.getElementById('nav-chatbots-count');
        if (el) el.textContent = agents.length;
        HirisState.set('chatbots', agents);
        /* Anche populate window.chatbots per legacy compat */
        if (typeof window !== 'undefined') window.chatbots = agents;
      }).catch(function() { /* silent */ });

    /* Update proposals count badge — hide when 0 (no work pending) */
    fetch('api/proposals?status=pending').then(function(r) { return r.json(); }).then(function(d) {
      var el = document.getElementById('nav-proposals-count');
      if (!el) return;
      var n = (d.proposals || []).length;
      el.textContent = n;
      el.classList.toggle('is-empty', n === 0);
    }).catch(function() { /* silent */ });

    /* Update tasks count badge — pending tasks come default; hide when 0 */
    fetch('api/tasks?status=pending').then(function(r) { return r.ok ? r.json() : []; })
      .then(function(tasks) {
        var el = document.getElementById('nav-tasks-count');
        if (!el) return;
        var n = (tasks || []).length;
        el.textContent = n;
        el.classList.toggle('is-empty', n === 0);
      }).catch(function() { /* silent */ });

    /* Update Brain advisories count badge on Dashboard nav item — hide when 0
       (SP-3 Task 9: #/ è la home del Brain, il badge segnala segnalazioni aperte) */
    fetch('api/brain/advisories?status=open').then(function(r) { return r.ok ? r.json() : { advisories: [] }; })
      .then(function(d) {
        var el = document.getElementById('nav-adv-count');
        if (!el) return;
        var n = (d.advisories || []).length;
        el.textContent = n;
        el.classList.toggle('is-empty', n === 0);
      }).catch(function() { /* silent */ });
  }

  function updateNavActive() {
    var hash = window.location.hash || '#/';
    document.querySelectorAll('.nav-item[data-route]').forEach(function(item) {
      var route = item.getAttribute('data-route');
      var isActive =
        (route === 'dashboard' && (hash === '#/' || hash === '')) ||
        (route === 'chatbots' && hash.indexOf('#/chatbots') === 0) ||
        (route === 'proposals' && hash.indexOf('#/proposals') === 0) ||
        (route === 'usage' && hash.indexOf('#/usage') === 0) ||
        (route === 'models' && hash.indexOf('#/models') === 0) ||
        (route === 'tasks' && hash.indexOf('#/tasks') === 0) ||
        (route === 'gateway' && hash.indexOf('#/gateway') === 0) ||
        (route === 'history' && hash.indexOf('#/history') === 0) ||
        (route === 'agentbots' && hash.indexOf('#/agentbots') === 0) ||
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

  /* Route handlers — placeholder (real implementations Phase 4.2-9) */
  HirisRouter.register(/^#\/?$/, function() {
    setCrumbHere('Dashboard');
    if (window.HirisDashboard) {
      HirisDashboard.mount();
    } else {
      document.getElementById('route-outlet').innerHTML =
        '<div class="page-title">Dashboard</div><p class="page-subtitle">Caricamento…</p>';
    }
  });
  HirisRouter.register(/^#\/chatbots\/?$/, function() {
    setCrumbHere('Chatbot');
    if (window.HirisChatbotsList) {
      HirisChatbotsList.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Lista Chatbot</div>';
    }
  });
  /* SP-4 Fase B Task 6: creazione goal-first (config/create-wizard.js).
     #/nuovo È il percorso di creazione predefinito (le CTA di dashboard.js/
     chatbots-list.js puntano qui): Obiettivo -> deriva il tipo (euristica
     deterministica, nessun LLM, sempre modificabile) -> step guidati per
     tipo -> crea via POST e apre l'editor completo su #/chatbots/{id} o
     #/agentbots/{id} come livello "Avanzate". #/chatbots/new RESTA il
     percorso diretto/avanzato (subito l'editor Chatbot vuoto) -- non
     rimosso, non redirect: sono due ingressi distinti sulla stessa
     entità, non un alias. */
  HirisRouter.register(/^#\/nuovo\/?$/, function() {
    setCrumbHere('Nuovo');
    HirisState.set('activeChatbotId', null);
    HirisState.set('activeAgentbotId', null);
    HirisCreateWizard.mount();
  });
  HirisRouter.register(/^#\/chatbots\/new\/?$/, function() {
    setCrumbHere('Chatbot / Nuovo');
    HirisState.set('activeChatbotId', null);
    HirisChatbotEditor.mount(null);
  });
  HirisRouter.register(/^#\/chatbots\/([^/]+)$/, function(m) {
    setCrumbHere('Chatbot / ' + m[1]);
    HirisState.set('activeChatbotId', m[1]);
    HirisChatbotEditor.mount(m[1]);
  });
  HirisRouter.register(/^#\/proposals\/?$/, function() {
    setCrumbHere('Proposte');
    /* SP-4 Fase B Task 2: proposals.js è ora un <script src> statico in
       config.html (era l'unico loader ad-hoc rimasto, separato da quello di
       chatbot-editor.js) — loadProposals() è già definita a questo punto. */
    if (window.HirisProposalsRoute) {
      HirisProposalsRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Proposte</div>';
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
  HirisRouter.register(/^#\/tasks\/?$/, function() {
    setCrumbHere('Task pianificati');
    if (window.HirisTasksRoute) {
      HirisTasksRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Task</div>';
    }
  });
  HirisRouter.register(/^#\/gateway\/?$/, function() {
    setCrumbHere('Accessi Gateway');
    if (window.HirisGatewayRoute) {
      HirisGatewayRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Accessi Gateway</div>';
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
  HirisRouter.register(/^#\/agentbots\/?$/, function() {
    setCrumbHere('Agentbot');
    if (window.HirisAgentbotRoute) {
      HirisAgentbotRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Agentbot</div>';
    }
  });
  /* SP-4 Fase B Task 5: editor per-entità (config/agentbot-editor.js),
     estratto dal blocco CRUD che agentbot-route.js possedeva -- stesso
     pattern di #/chatbots/new e #/chatbots/{id} sopra. Il pattern "/new"
     va registrato PRIMA di quello generico "/([^/]+)$": altrimenti
     "#/agentbots/new" combacerebbe comunque con [^/]+ e finirebbe nel ramo
     sbagliato (stesso ordine già usato per i Chatbot qui sopra). */
  HirisRouter.register(/^#\/agentbots\/new\/?$/, function() {
    setCrumbHere('Agentbot / Nuovo');
    HirisState.set('activeAgentbotId', null);
    HirisAgentbotEditor.mount(null);
  });
  HirisRouter.register(/^#\/agentbots\/([^/]+)$/, function(m) {
    setCrumbHere('Agentbot / ' + m[1]);
    HirisState.set('activeAgentbotId', m[1]);
    HirisAgentbotEditor.mount(m[1]);
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
