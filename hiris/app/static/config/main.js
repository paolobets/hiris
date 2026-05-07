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
      if (moon) moon.style.display = t === 'dark' ? 'none' : '';
      if (sun) sun.style.display = t === 'dark' ? '' : 'none';
    }
    var current = document.documentElement.getAttribute('data-theme') ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    paint(current);
    if (btn) btn.addEventListener('click', function() {
      paint(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });

    /* Update agent count badge from API (best-effort) */
    if (typeof loadAgents === 'function') {
      loadAgents().then(function(agents) {
        var el = document.getElementById('nav-agents-count');
        if (el) el.textContent = agents.length;
        HirisState.set('agents', agents);
      }).catch(function() { /* silent */ });
    }

    /* Update proposals count badge */
    fetch('api/proposals?status=pending').then(function(r) { return r.json(); }).then(function(d) {
      var el = document.getElementById('nav-proposals-count');
      if (el) el.textContent = (d.proposals || []).length;
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
  HirisRouter.register(/^#\/settings\/?$/, function() {
    setCrumbHere('Impostazioni');
    document.getElementById('route-outlet').innerHTML =
      '<div class="page-title">Impostazioni</div><p class="page-subtitle">Implementata in Phase 11.</p>';
  });

  document.addEventListener('DOMContentLoaded', function() {
    mountChrome();
    window.addEventListener('hashchange', updateNavActive);
    HirisState.subscribe('route', updateNavActive);
    HirisRouter.start();
    updateNavActive();
  });
})();
