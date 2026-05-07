/* HIRIS · Designer · bootstrap (Phase 2.3 stub routes) */
(function() {
  /* Route handlers — placeholder. Real implementations in Phase 4-9. */
  HirisRouter.register(/^#\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Dashboard</h2><p>Route #/ — implementata in Phase 8.</p></div>';
  });
  HirisRouter.register(/^#\/agents\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Lista agenti</h2><p>Route #/agents — implementata in Phase 4.</p></div>';
  });
  HirisRouter.register(/^#\/agents\/new\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Nuovo agente</h2><p>Route #/agents/new — implementata in Phase 4.</p></div>';
  });
  HirisRouter.register(/^#\/agents\/([^/]+)$/, function(m) {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Editor agente: ' + m[1] + '</h2><p>Route #/agents/:id — implementata in Phase 4.</p></div>';
  });
  HirisRouter.register(/^#\/proposals\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Proposte</h2><p>Route #/proposals — implementata in Phase 9.</p></div>';
  });
  HirisRouter.register(/^#\/usage\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Consumi</h2><p>Route #/usage — implementata in Phase 9.</p></div>';
  });
  HirisRouter.register(/^#\/settings\/?$/, function() {
    document.getElementById('route-outlet').innerHTML =
      '<div style="padding:24px"><h2>Impostazioni</h2><p>Route #/settings — implementata in Phase 11.</p></div>';
  });

  /* Provisional side-nav (sostituito da template clone in Phase 4.1) */
  document.getElementById('side-nav').innerHTML =
    '<div style="padding:16px;font-weight:600">HIRIS</div>' +
    '<a href="#/" style="display:block;padding:8px 16px">Dashboard</a>' +
    '<a href="#/agents" style="display:block;padding:8px 16px">Agenti</a>' +
    '<a href="#/proposals" style="display:block;padding:8px 16px">Proposte</a>' +
    '<a href="#/usage" style="display:block;padding:8px 16px">Consumi</a>' +
    '<a href="#/settings" style="display:block;padding:8px 16px">Impostazioni</a>';

  /* Provisional page-chrome (sostituito in Phase 4.1) */
  document.getElementById('page-chrome').innerHTML =
    '<div style="padding:16px">HIRIS Agent Designer</div>';

  HirisRouter.start();
})();
