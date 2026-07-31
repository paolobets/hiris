/* HIRIS · Chat page · proposals panel.
   Le proposte del Brain sono un'inbox di azioni (approvi -> scrive in HA),
   stessa natura dei Task: qui vivono nella chat, la superficie d'uso quotidiano,
   sotto una voce di navigazione dedicata "Proposte".

   Azione (Attiva/Rifiuta) via il core condiviso HirisProposalsCore: la vista
   aggiorna SOLO il proprio DOM, senza ereditare quello della pagina Proposte
   del config (vedi config/proposals-core.js). `esc()` è il globale di
   config/api.js, già caricato in questa pagina. */
(function() {
  var TYPE_LABELS = {
    ha_automation: '→ automazione HA',
    ha_dashboard: '→ dashboard HA',
    ha_script: '→ script HA',
    ha_scene: '→ scena HA',
    hiris_agent: '→ Agentbot'
  };

  function renderProposal(p) {
    var typeLabel = TYPE_LABELS[p.type] || ('→ ' + esc(p.type || 'config'));
    var date = p.created_at ? String(p.created_at).substring(0, 10) : '';
    var safeId = esc(p.id);
    return '<div class="pp-card" id="pp-' + safeId + '">'
      + '<div class="pp-head">'
      + '<span class="pp-type">' + esc(typeLabel) + '</span>'
      + (date ? '<span class="pp-date">' + esc(date) + '</span>' : '')
      + '</div>'
      + '<div class="pp-name">' + esc(p.name || '') + '</div>'
      + (p.description ? '<div class="pp-desc">' + esc(p.description) + '</div>' : '')
      + (p.routing_reason ? '<div class="pp-reason"><strong>Motivo:</strong> ' + esc(p.routing_reason) + '</div>' : '')
      + '<div class="pp-actions">'
      + '<button class="btn pp-apply" type="button" data-pp-act="apply" data-pid="' + safeId + '">Attiva</button>'
      + '<button class="btn pp-reject" type="button" data-pp-act="reject" data-pid="' + safeId + '">Rifiuta</button>'
      + '</div>'
      + '</div>';
  }

  function setBadges(n) {
    var b = document.getElementById('proposals-badge');
    if (b) { b.textContent = n || ''; b.dataset.count = n; }
    var mb = document.getElementById('mobile-proposals-badge');
    if (mb) { mb.textContent = n || ''; mb.dataset.count = n; }
  }

  function load() {
    return HirisProposalsCore.list('pending').then(function(props) {
      var list = document.getElementById('chat-proposals-list');
      setBadges(props.length);
      if (!list) return;
      list.innerHTML = props.length
        ? props.map(renderProposal).join('')
        : '<div class="task-empty">Nessuna proposta in attesa</div>';
    }).catch(function(e) {
      console.error('loadProposals failed', e);
      var list = document.getElementById('chat-proposals-list');
      if (list) list.innerHTML = '<div class="task-empty">Errore nel caricamento delle proposte.</div>';
    });
  }

  function act(id, kind) {
    var isReject = (kind === 'reject');
    if (!window.confirm(isReject ? 'Rifiutare questa proposta?' : 'Attivare questa proposta?')) return;
    var fn = isReject ? HirisProposalsCore.reject : HirisProposalsCore.apply;
    var card = document.getElementById('pp-' + id);
    fn(id).then(function(res) {
      if (!res.ok) { window.alert(res.error || 'Errore'); return; }
      if (card) {
        card.style.opacity = '0.5';
        var nameEl = card.querySelector('.pp-name');
        if (nameEl) nameEl.innerHTML = isReject
          ? '<span style="color:var(--text-3)">Proposta rifiutata</span>'
          : '<span style="color:var(--success,#3ba55d)">✓ Proposta attivata</span>';
        var actsEl = card.querySelector('.pp-actions');
        if (actsEl) actsEl.remove();
      }
      setTimeout(load, 1000);
    }, function() { window.alert('Errore di rete'); });
  }

  function showPanel(name) {
    var isProp = (name === 'proposals');
    var messages = document.getElementById('messages');
    var inputArea = document.getElementById('input-area');
    if (messages) messages.style.display = isProp ? 'none' : '';
    if (inputArea) inputArea.style.display = isProp ? 'none' : '';
    var tc = document.getElementById('turn-counter'); if (tc) tc.style.display = isProp ? 'none' : '';
    var se = document.getElementById('session-ended-msg'); if (se) se.style.display = isProp ? 'none' : '';
    /* mutua esclusione col pannello Task */
    var taskPanel = document.getElementById('task-panel'); if (taskPanel) taskPanel.style.display = 'none';
    var panel = document.getElementById('proposals-panel');
    if (panel) panel.style.display = isProp ? 'flex' : 'none';
    var nav = document.getElementById('nav-proposals');
    if (nav) nav.classList.toggle('active', isProp);
    var mobileBtn = document.getElementById('mobile-proposals-btn');
    if (mobileBtn) mobileBtn.classList.toggle('active', isProp);
    /* disattiva l'evidenza nav dei Task quando si apre Proposte */
    if (isProp) {
      var navTasks = document.getElementById('nav-tasks'); if (navTasks) navTasks.classList.remove('active');
      var mobileTask = document.getElementById('mobile-task-btn'); if (mobileTask) mobileTask.classList.remove('active');
    }
    var header = document.getElementById('proposals-panel-header');
    if (header) header.style.display = (isProp && window.innerWidth <= 720) ? 'flex' : 'none';
    if (isProp) load();
  }

  function init() {
    var nav = document.getElementById('nav-proposals');
    if (nav) nav.addEventListener('click', function(e) { e.preventDefault(); showPanel('proposals'); });
    var mobileBtn = document.getElementById('mobile-proposals-btn');
    if (mobileBtn) mobileBtn.addEventListener('click', function(e) { e.preventDefault(); showPanel('proposals'); });
    var backBtn = document.getElementById('proposals-panel-back-btn');
    if (backBtn) backBtn.addEventListener('click', function() { showPanel('chat'); });

    var panel = document.getElementById('proposals-panel');
    if (panel) panel.addEventListener('click', function(e) {
      var btn = e.target.closest && e.target.closest('[data-pp-act]');
      if (btn) act(btn.dataset.pid, btn.dataset.ppAct);
    });

    setInterval(load, 30000);
    load();   /* popola il badge anche senza aprire il pannello */
  }

  window.HirisChatProposals = { showPanel: showPanel, load: load, act: act, init: init };
})();
