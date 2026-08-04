/* HIRIS · Chat page · scheduled tasks panel (SP-4 Fase B Task 8)
   Load + cancel task cards in the sidebar-embedded panel. Independent from
   config/tasks-route.js (a full CRUD-ish log view for the config SPA, with
   its own markup) -- this is the compact panel embedded in the chat page,
   not a duplicate to fold away. */
(function() {
  function renderTask(task) {
    var isPending = task.status === 'pending';
    var safeId = esc(task.id);
    var cancelBtn = isPending ? '<button class="task-cancel-btn" data-task-id="' + safeId + '" type="button">Annulla</button>' : '';
    /* Descrizione del trigger dal dizionario condiviso (labels.js): prima
       questo file replicava a mano gli stessi quattro rami di
       config/tasks-route.js senza 'immediate' -- un solo posto ora elenca
       i cinque tipi reali per entrambe le viste. */
    var rawMeta = task.result || task.error || HirisLabels.triggerDescription(task.trigger);
    var meta = rawMeta ? esc(rawMeta) : '';
    var statusLabel = HirisLabels.taskStatusLabel(task.status);
    return '<div class="task-card" id="task-' + safeId + '">'
      + '<div class="task-card-header">'
      + '<span class="task-label">' + esc(task.label) + '</span>'
      + '<span class="task-status ' + esc(task.status) + '">' + esc(statusLabel) + '</span>'
      + cancelBtn
      + '</div>'
      + (meta ? '<div class="task-meta">' + meta + '</div>' : '')
      + '</div>';
  }

  async function load() {
    try {
      var resp = await fetch('api/tasks');
      var tasks = await resp.json();
      var active = tasks.filter(function(t) { return t.status === 'pending' || t.status === 'running'; });
      var recent = tasks.filter(function(t) { return t.status !== 'pending' && t.status !== 'running'; });
      var activeEl = document.getElementById('task-active-list');
      var recentEl = document.getElementById('task-recent-list');
      if (activeEl) activeEl.innerHTML = active.length ? active.map(renderTask).join('') : '<div class="task-empty">Nessuna task attiva</div>';
      if (recentEl) recentEl.innerHTML = recent.length ? recent.map(renderTask).join('') : '<div class="task-empty">Nessuna task recente</div>';
      var badge = document.getElementById('task-badge');
      if (badge) { badge.textContent = active.length || ''; badge.dataset.count = active.length; }
      var mbadge = document.getElementById('mobile-task-badge');
      if (mbadge) { mbadge.textContent = active.length || ''; mbadge.dataset.count = active.length; }
    } catch (e) { console.error('loadTasks failed', e); }
  }

  /* M-6 (review indipendente su bee3ab1, fratello di A7 nella stessa pagina):
     una DELETE fallita non produceva NIENTE -- ne' un log ne' un avviso, la
     task restava li' senza che l'utente sapesse perche' "Annulla" non ha
     avuto effetto. A7 (agents.js::clearConversation) e resolve() di
     gateway-route.js seguono gia' la stessa regola: un fallimento va detto,
     mai in silenzio. */
  async function cancel(taskId) {
    if (!confirm('Annullare questa task?')) return;
    try {
      var resp = await fetch('api/tasks/' + taskId, { method: 'DELETE', headers: { 'X-Requested-With': 'fetch' } });
      if (resp.ok || resp.status === 204) { load(); return; }
      console.error('cancelTask failed', resp.status);
      alert('Non è stato possibile annullare questa task. Riprova più tardi.');
    } catch (e) {
      console.error('cancelTask failed', e);
      alert('Errore di rete: riprova.');
    }
  }

  function showPanel(name) {
    var isTask = name === 'tasks';
    document.getElementById('messages').style.display = isTask ? 'none' : '';
    document.getElementById('input-area').style.display = isTask ? 'none' : '';
    var tc = document.getElementById('turn-counter'); if (tc) tc.style.display = isTask ? 'none' : '';
    var se = document.getElementById('session-ended-msg'); if (se) se.style.display = isTask ? 'none' : '';
    /* mutua esclusione coi pannelli Proposte e Memoria (stessa area overlay) */
    var propPanel = document.getElementById('proposals-panel'); if (propPanel) propPanel.style.display = 'none';
    var kbPanel = document.getElementById('knowledge-panel'); if (kbPanel) kbPanel.style.display = 'none';
    if (isTask) {
      var navProp = document.getElementById('nav-proposals'); if (navProp) navProp.classList.remove('active');
      var mobileProp = document.getElementById('mobile-proposals-btn'); if (mobileProp) mobileProp.classList.remove('active');
      var navKb = document.getElementById('nav-knowledge'); if (navKb) navKb.classList.remove('active');
      var mobileKb = document.getElementById('mobile-knowledge-btn'); if (mobileKb) mobileKb.classList.remove('active');
    }
    document.getElementById('task-panel').style.display = isTask ? 'flex' : 'none';
    var navTasks = document.getElementById('nav-tasks');
    if (navTasks) navTasks.classList.toggle('active', isTask);
    var mobileBtn = document.getElementById('mobile-task-btn');
    if (mobileBtn) mobileBtn.classList.toggle('active', isTask);
    var taskHeader = document.getElementById('task-panel-header');
    if (taskHeader) taskHeader.style.display = (isTask && window.innerWidth <= 720) ? 'flex' : 'none';
    if (isTask) load();
  }

  function init() {
    var navTasks = document.getElementById('nav-tasks');
    if (navTasks) navTasks.addEventListener('click', function(e) { e.preventDefault(); showPanel('tasks'); });
    var mobileBtn = document.getElementById('mobile-task-btn');
    if (mobileBtn) mobileBtn.addEventListener('click', function(e) { e.preventDefault(); showPanel('tasks'); });
    var backBtn = document.getElementById('task-panel-back-btn');
    if (backBtn) backBtn.addEventListener('click', function() { showPanel('chat'); });

    /* Delegated cancel click -- replaces the old inline
       onclick="cancelTask(this.dataset.taskId)". */
    var panel = document.getElementById('task-panel');
    if (panel) panel.addEventListener('click', function(e) {
      var btn = e.target.closest && e.target.closest('.task-cancel-btn');
      if (btn) cancel(btn.dataset.taskId);
    });

    setInterval(load, 30000);
    load();
  }

  window.HirisChatTasks = { showPanel: showPanel, load: load, cancel: cancel, init: init };
})();
