/* HIRIS · Designer · bootstrap (Phase 4.1: chrome + nav active state) */
(function() {
  function mountChrome() {
    var sn = document.getElementById('side-nav');
    var pc = document.getElementById('page-chrome');
    sn.innerHTML = '';
    sn.appendChild(document.getElementById('tpl-side-nav').content.cloneNode(true));
    pc.innerHTML = '';
    pc.appendChild(document.getElementById('tpl-page-chrome').content.cloneNode(true));

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

    /* v0.10.5: fetch diretto invece di loadAgents() (in agent-form.js, caricato
       solo quando user apre editor). Al boot loadAgents non è ancora definito,
       quindi badge restava "—" finché user non apriva un agente. */
    fetch('api/agents').then(function(r) { return r.ok ? r.json() : []; })
      .then(function(d) {
        var agents = Array.isArray(d) ? d : (d.agents || []);
        var el = document.getElementById('nav-agents-count');
        if (el) el.textContent = agents.length;
        HirisState.set('agents', agents);
        /* Anche populate window.agents per legacy compat */
        if (typeof window !== 'undefined') window.agents = agents;
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
  }

  function updateNavActive() {
    var hash = window.location.hash || '#/';
    document.querySelectorAll('.nav-item[data-route]').forEach(function(item) {
      var route = item.getAttribute('data-route');
      var isActive =
        (route === 'dashboard' && (hash === '#/' || hash === '')) ||
        (route === 'agents' && hash.indexOf('#/agents') === 0) ||
        (route === 'proposals' && hash.indexOf('#/proposals') === 0) ||
        (route === 'usage' && hash.indexOf('#/usage') === 0) ||
        (route === 'tasks' && hash.indexOf('#/tasks') === 0) ||
        (route === 'gateway' && hash.indexOf('#/gateway') === 0) ||
        (route === 'settings' && hash.indexOf('#/settings') === 0);
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
  HirisRouter.register(/^#\/agents\/?$/, function() {
    setCrumbHere('Agenti');
    if (window.HirisAgentsList) {
      HirisAgentsList.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Lista agenti</div>';
    }
  });
  HirisRouter.register(/^#\/agents\/new\/?$/, function() {
    setCrumbHere('Agenti / Nuovo');
    HirisState.set('activeAgentId', null);
    HirisAgentEditor.mount(null);
  });
  HirisRouter.register(/^#\/agents\/([^/]+)$/, function(m) {
    setCrumbHere('Agenti / ' + m[1]);
    HirisState.set('activeAgentId', m[1]);
    HirisAgentEditor.mount(m[1]);
  });
  HirisRouter.register(/^#\/proposals\/?$/, function() {
    setCrumbHere('Proposte');
    if (window.HirisProposalsRoute) {
      HirisProposalsRoute.mount();
    } else {
      document.getElementById('route-outlet').innerHTML = '<div class="page-title">Proposte</div>';
    }
    /* proposals.js è in LEGACY_SCRIPTS — lo carichiamo on-demand qui */
    if (typeof loadProposals !== 'function' && window.HirisAgentEditor) {
      /* Reuse the legacy loader from agent-editor.js by triggering a no-op mount path? */
      /* Simpler: load proposals.js directly */
      var s = document.querySelector('script[data-legacy="static/config/proposals.js"]');
      if (!s) {
        s = document.createElement('script');
        s.src = 'static/config/proposals.js';
        s.dataset.legacy = 'static/config/proposals.js';
        s.onload = function() {
          if (typeof loadProposals === 'function' && window.HirisProposalsRoute) {
            loadProposals('pending');
          }
        };
        document.head.appendChild(s);
      }
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
  /* v0.10.5: rimosso route /settings — la nav voce è stata tolta da config.html
     (era solo placeholder "Implementata in Phase 11"). Re-aggiungere quando
     ci sarà contenuto reale (theme persist, version info, diagnostic export). */

  document.addEventListener('DOMContentLoaded', function() {
    mountChrome();
    window.addEventListener('hashchange', updateNavActive);
    HirisState.subscribe('route', updateNavActive);
    HirisRouter.start();
    updateNavActive();
  });
})();
