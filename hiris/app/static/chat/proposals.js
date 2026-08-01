/* HIRIS · Chat page · proposals panel.
   Le proposte del Brain sono un'inbox di azioni (approvi -> scrive in HA),
   stessa natura dei Task: qui vivono nella chat, la superficie d'uso quotidiano,
   sotto una voce di navigazione dedicata "Proposte".

   Azione (Attiva/Rifiuta) via il core condiviso HirisProposalsCore: la vista
   aggiorna SOLO il proprio DOM, senza ereditare quello della pagina Proposte
   del config (vedi config/proposals-core.js). `esc()` è il globale di
   config/api.js, già caricato in questa pagina.

   Il ripristino di una plancia sostituita è derivato dallo stato del server
   (GET /api/dashboards/backups), non da quello che è stato applicato qui:
   l'affordance vale ovunque sia stata approvata la sostituzione e sopravvive
   al refresh. Due livelli, per non dare a "torno a una versione vecchia" lo
   stesso peso di "ho appena sbagliato": vedi RECENT_MS.

   Un ripristino riuscito consuma lo snapshot lato server (è tornato a essere
   lo stato corrente della plancia): qui non si tiene traccia di nulla, basta
   ricaricare l'elenco. */
(function() {
  var TYPE_LABELS = {
    ha_automation: '→ automazione HA',
    ha_dashboard: '→ dashboard HA',
    ha_script: '→ script HA',
    ha_scene: '→ scena HA',
    hiris_agent: '→ Agentbot'
  };

  /* Soglia fra "ho appena sbagliato, torno indietro" e "voglio tornare a una
     versione vecchia": entro 24 ore lo snapshot è un undo, oltre è storia. */
  var RECENT_MS = 24 * 60 * 60 * 1000;

  /* Ultimo elenco di snapshot noto dal server (GET /api/dashboards/backups):
     [{url_path, saved_at, count}, ...]. L'affordance di ripristino è DERIVATA
     da qui e non da ciò che è stato applicato in questa pagina: altrimenti un
     replace approvato dalla pagina Proposte del config o dal peek della
     Dashboard non mostrerebbe mai il pulsante, e un refresh del browser lo
     perderebbe, mentre lo snapshot resta sul disco irraggiungibile.
     È solo una cache di rendering: la verità è del server. */
  var backups = [];

  function renderProposal(p) {
    var typeLabel = TYPE_LABELS[p.type] || ('→ ' + esc(p.type || 'config'));
    var date = p.created_at ? String(p.created_at).substring(0, 10) : '';
    var safeId = esc(p.id);
    var cfg = p.config || {};
    var isDashReplace = (p.type === 'ha_dashboard' && cfg.mode === 'replace' && !!cfg.slug);
    /* Solo un replace di plancia vero e proprio: un'altra proposta con un
       config omonimo (stesse chiavi, altro significato) non deve essere
       presentata come sostituzione di plancia. */
    var warn = isDashReplace
      ? '<div class="pp-warn">Sostituisce interamente la plancia "' + esc(cfg.slug) + '".</div>'
      : '';
    return '<div class="pp-card" id="pp-' + safeId + '">'
      + '<div class="pp-head">'
      + '<span class="pp-type">' + esc(typeLabel) + '</span>'
      + (date ? '<span class="pp-date">' + esc(date) + '</span>' : '')
      + '</div>'
      + '<div class="pp-name">' + esc(p.name || '') + '</div>'
      + (p.description ? '<div class="pp-desc">' + esc(p.description) + '</div>' : '')
      + warn
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

  /* Uno snapshot senza istante è anteriore all'introduzione del campo: vale
     come il più vecchio che c'è, quindi mai "recente". */
  function isRecent(savedAt) {
    var t = savedAt ? Date.parse(savedAt) : NaN;
    if (isNaN(t)) return false;
    return (Date.now() - t) < RECENT_MS;
  }

  /* L'istante arriva in ISO 8601 UTC: all'utente va mostrata l'ora locale in
     forma leggibile. Ritorna null se non c'è o non è interpretabile: chi
     chiama deve dichiarare "data non disponibile", non inventarne una. */
  function fmtWhen(savedAt) {
    var t = savedAt ? Date.parse(savedAt) : NaN;
    if (isNaN(t)) return null;
    try {
      return new Date(t).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
    } catch (e) {
      return new Date(t).toLocaleString();
    }
  }

  /* Undo recente: la sostituzione è di poche ore fa, quasi certamente un
     errore che si vuole annullare. Prominente, com'era. */
  function recentBar(b) {
    var safe = esc(b.url_path);
    return '<div class="pp-undo-bar">'
      + '<span>Plancia "' + safe + '" sostituita. Puoi ripristinare la versione precedente.</span>'
      + '<button class="btn pp-undo" type="button" data-pp-undo="' + safe + '">Annulla</button>'
      + '</div>';
  }

  /* Ripristino storico: tornare a una versione vecchia è un'azione più
     impegnativa, non deve avere il peso visivo dell'undo appena sopra. Dice
     sempre QUANDO, e se l'istante manca lo dichiara. */
  function historyRow(b) {
    var when = fmtWhen(b.saved_at);
    var quando = when ? 'versione salvata il ' + esc(when) : 'versione salvata in data non disponibile';
    var safe = esc(b.url_path);
    return '<div class="pp-undo-old">'
      + '<span>Plancia "' + safe + '" — ' + quando + '</span>'
      + '<button class="pp-undo-old-btn" type="button" data-pp-undo="' + safe + '">Ripristina</button>'
      + '</div>';
  }

  /* Strisce di ripristino in cima alla lista, ricostruite da `backups` a ogni
     render: idempotente, chiamarla due volte non duplica nulla (tutto vive in
     un unico contenitore .pp-undo-zone, rimosso e riscritto per intero). */
  function renderUndoBars() {
    var list = document.getElementById('chat-proposals-list');
    if (!list) return;
    var old = list.querySelectorAll('.pp-undo-zone');
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var recenti = [], storici = [];
    for (var j = 0; j < backups.length; j++) {
      var b = backups[j];
      if (!b || !b.url_path) continue;
      (isRecent(b.saved_at) ? recenti : storici).push(b);
    }
    if (!recenti.length && !storici.length) return;
    var html = recenti.map(recentBar).join('');
    if (storici.length) {
      html += '<div class="pp-undo-old-head">Versioni precedenti</div>'
        + storici.map(historyRow).join('');
    }
    list.insertAdjacentHTML('afterbegin', '<div class="pp-undo-zone">' + html + '</div>');
  }

  /* Aggiorna l'elenco degli snapshot dal server e ridisegna le strisce.
     Se la chiamata fallisce si tiene l'ultimo elenco noto: un ripristino
     ancora possibile non deve sparire per un errore di rete. */
  function loadBackups() {
    return HirisProposalsCore.listDashboardBackups().then(function(items) {
      backups = items || [];
      renderUndoBars();
    }, function(e) {
      console.error('loadDashboardBackups failed', e);
      renderUndoBars();
    });
  }

  function load() {
    var bars = loadBackups();
    var proposte = HirisProposalsCore.list('pending').then(function(props) {
      var list = document.getElementById('chat-proposals-list');
      setBadges(props.length);
      if (!list) return;
      list.innerHTML = props.length
        ? props.map(renderProposal).join('')
        : '<div class="task-empty">Nessuna proposta in attesa</div>';
      renderUndoBars();
    }).catch(function(e) {
      console.error('loadProposals failed', e);
      var list = document.getElementById('chat-proposals-list');
      if (list) list.innerHTML = '<div class="task-empty">Errore nel caricamento delle proposte.</div>';
      /* Un errore nel caricare le proposte non deve togliere il ripristino di
         una sostituzione: è un'azione ancora possibile. */
      renderUndoBars();
    });
    /* Le due richieste corrono in parallelo e ognuna riscrive un pezzo della
       lista: un render finale, quando entrambe sono finite, rende l'esito
       indipendente dall'ordine di arrivo delle risposte. */
    return Promise.all([proposte, bars]).then(function() { renderUndoBars(); });
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
      /* Un apply può aver creato uno snapshot: richiedi subito l'elenco al
         server, così l'undo compare senza aspettare il reload differito.
         Chi decide se c'è qualcosa da ripristinare è il server, non questa
         card: una proposta che non ha toccato una plancia non produce voci. */
      if (!isReject) loadBackups();
      setTimeout(load, 1000);
    }, function() { window.alert('Errore di rete'); });
  }

  /* Annulla: ripristina l'ultimo snapshot della plancia sostituita.
     Lo snapshot è quello preso PRIMA dell'ultima sostituzione: se nel
     frattempo la plancia è stata modificata (a mano in HA, o da un altro
     apply fatto altrove), il ripristino riporta indietro anche quelle
     modifiche. Non c'è invalidazione automatica: il rischio va detto qui,
     dove l'utente decide. */
  function undo(urlPath) {
    var msg = 'Ripristinare la plancia "' + urlPath + '" alla versione precedente all\'ultima sostituzione?\n\n'
      + 'Le modifiche fatte alla plancia dopo quella sostituzione andranno perse.';
    if (!window.confirm(msg)) return;
    HirisProposalsCore.restoreDashboard(urlPath).then(function(res) {
      if (!res.ok) { window.alert(res.error || 'Errore'); return; }
      /* Il ripristino consuma lo snapshot sul server: basta ricaricare lo
         stato e la voce sparisce da sé. Niente memoria locale di ciò che è
         già stato ripristinato: sarebbe una seconda fonte di verità sullo
         stesso fatto, e sopravviverebbe solo fino al refresh. */
      load();
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
      var undoBtn = e.target.closest && e.target.closest('[data-pp-undo]');
      if (undoBtn) { undo(undoBtn.getAttribute('data-pp-undo')); return; }
      var btn = e.target.closest && e.target.closest('[data-pp-act]');
      if (btn) act(btn.dataset.pid, btn.dataset.ppAct);
    });

    setInterval(load, 30000);
    load();   /* popola il badge anche senza aprire il pannello */
  }

  window.HirisChatProposals = {
    showPanel: showPanel, load: load, act: act, undo: undo, init: init
  };
})();
