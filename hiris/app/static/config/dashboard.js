/* HIRIS · Designer · dashboard adaptive route (Phase 8) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function midTruncate(s, n) {
    if (!s || s.length <= n) return s || '';
    return s.slice(0, Math.ceil((n-1)/2)) + '…' + s.slice(-Math.floor((n-1)/2));
  }

  function formatTokens(n) {
    n = Number(n) || 0;
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'k';
    return String(n);
  }

  function greeting() {
    var h = new Date().getHours();
    if (h < 6) return 'Buonanotte';
    if (h < 12) return 'Buongiorno';
    if (h < 18) return 'Buon pomeriggio';
    return 'Buonasera';
  }

  /* Fallback fetch: loadChatbots() in chatbot-editor.js mutates module state
     and touches DOM (#agent-list, dell'editor); non è sicuro chiamarlo prima
     che quel DOM esista, né lo script è detto sia già caricato in questa
     route. */
  /* --- "Nuovo dall'ultima visita" (issue live-verify #1, increment 2) -------
     Le notifiche portano su HIRIS (increment 1) ma HA non dice QUALE notifica
     hai toccato. Invece di un mapping fragile notifica->item, evidenziamo tutto
     cio' che nel feed e' piu' recente dell'ultima apertura: qualunque notifica
     tu tocchi, apri HIRIS e vedi cosa e' nuovo. Stato per-dispositivo in
     localStorage; nessuno store server. Timestamp ISO -> confronto stringa =
     confronto cronologico. */
  var _FEED_SEEN_KEY = 'hiris_feed_last_seen';
  var _feedLastSeen = '';   // '' = prima visita -> NON evidenziare nulla

  function feedReadLastSeen() {
    try { return window.localStorage.getItem(_FEED_SEEN_KEY) || ''; }
    catch (e) { return ''; }
  }
  function feedWriteLastSeen(ts) {
    try { window.localStorage.setItem(_FEED_SEEN_KEY, ts); } catch (e) { /* no-op */ }
  }
  function feedMarkNew(scope) {
    /* Aggiunge .feed-new agli item con data-ts piu' recente dell'ultima visita.
       Prima visita (_feedLastSeen vuoto) non marca nulla, cosi' il primo
       caricamento non lampeggia l'intero feed. */
    if (!_feedLastSeen || !scope) return;
    var els = scope.querySelectorAll('[data-ts]');
    for (var i = 0; i < els.length; i++) {
      var ts = els[i].getAttribute('data-ts') || '';
      if (ts && ts > _feedLastSeen) els[i].classList.add('feed-new');
    }
  }
  function feedFinalizeNew() {
    /* Scrolla sul singolo item nuovo piu' recente (pulse via CSS), poi registra
       questa visita cosi' nulla si ri-evidenzia la prossima volta. */
    var news = document.querySelectorAll('.feed-new');
    var newest = null, newestTs = '';
    for (var i = 0; i < news.length; i++) {
      var ts = news[i].getAttribute('data-ts') || '';
      if (ts > newestTs) { newestTs = ts; newest = news[i]; }
    }
    if (newest && newest.scrollIntoView) {
      try { newest.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
      catch (e) { newest.scrollIntoView(); }
    }
    var now = new Date().toISOString();
    // non arretrare mai il puntatore (item futuri gia' visti restano visti)
    if (now > _feedLastSeen) feedWriteLastSeen(now);
  }

  function fetchAgentsDirect() {
    /* Rejects on failure (does NOT coerce to []) so mount() can tell a real
       network/server error apart from a genuinely-empty first run -- otherwise
       a blip would show the first-run onboarding to a user who has agents. */
    return fetch('api/chatbots').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      /* api/chatbots returns either an array or {agents: [...]} */
      if (Array.isArray(d)) return d;
      return d.agents || [];
    });
  }

  function renderEmpty(outlet) {
    outlet.innerHTML =
      '<div class="page-title">Benvenuto in HIRIS</div>' +
      '<p class="page-subtitle">Configura il tuo primo Chatbot per Home Assistant. Scegli un template per iniziare velocemente, oppure parti da zero.</p>' +
      '<div class="stat-grid" style="grid-template-columns:repeat(auto-fit, minmax(150px, 1fr))">' +
        '<a class="stat-tile" href="#/nuovo" style="text-decoration:none">' +
          '<div class="st-label">⚡ Energia</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Monitor consumi</div>' +
          '<div class="st-delta">Rileva anomalie e suggerisce azioni</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/nuovo" style="text-decoration:none">' +
          '<div class="st-label">🏠 Rientro</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Scenario casa</div>' +
          '<div class="st-delta">Attiva luci/clima al rientro</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/nuovo" style="text-decoration:none">' +
          '<div class="st-label">⏰ Promemoria</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Notifiche schedulate</div>' +
          '<div class="st-delta">Reminder ricorrenti</div>' +
        '</a>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:12px">' +
        '<a class="btn btn-primary" href="#/nuovo">+ Crea Chatbot vuoto</a>' +
        '<a class="btn btn-ghost" href="docs/" target="_blank">Cosa è HIRIS?</a>' +
      '</div>';
  }

  /* v0.28+ (SP-3 Task 9): #/ diventa la home del Brain, in 3 zone:
     1. Supervisione casa (stat tiles: Chatbot / Segnalazioni aperte / Proposte)
     2. Stream ragionamenti (api/brain/feed — reasoning + brain_action)
     3. Azioni: Segnalazioni del Brain (advisories, ack/dismiss) + Proposte pending
     Il vecchio pannello "Esecuzioni 24h / Token / Costo" + "Ultimi log" resta
     raggiungibile da #/usage; qui teniamo solo ciò che serve a capire "cosa
     osserva/deduce/propone" il Brain, come da task brief. */
  function renderPopulated(outlet, agents) {
    outlet.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:8px">' +
        '<div>' +
          '<h1 style="font-size:var(--fs-24);font-weight:600;letter-spacing:-0.02em">' + greeting() + '</h1>' +
          '<p class="page-subtitle" style="margin-top:4px">Cosa osserva, deduce e propone la tua casa.</p>' +
        '</div>' +
        '<div style="display:flex;gap:8px">' +
          '<a class="btn btn-primary" href="#/nuovo">+ Nuovo Chatbot</a>' +
          '<a class="btn" href="./">Vai alla chat</a>' +
        '</div>' +
      '</div>' +

      /* Zona 1 — Supervisione casa */
      '<div class="stat-grid" id="dash-supervision">' +
        '<div class="stat-tile">' +
          '<div class="st-label">Chatbot</div>' +
          '<div class="st-value">' + escHtml(String(agents.length)) + '</div>' +
          '<div class="st-delta">configurati</div>' +
        '</div>' +
        '<div class="stat-tile">' +
          '<div class="st-label">Segnalazioni aperte</div>' +
          '<div class="st-value" id="dash-adv-count">—</div>' +
          '<div class="st-delta">dal Brain</div>' +
        '</div>' +
        '<div class="stat-tile">' +
          '<div class="st-label">Proposte</div>' +
          '<div class="st-value" id="dash-prop-count">—</div>' +
          '<div class="st-delta">in attesa</div>' +
        '</div>' +
      '</div>' +

      /* Zona 2 — Stream ragionamenti */
      '<section class="dash-list dash-section">' +
        '<h3>Stream ragionamenti</h3>' +
        '<div id="dash-reasoning-body"><div style="padding:16px;color:var(--text-3)">Caricamento…</div></div>' +
      '</section>' +

      /* Zona 3 — Azioni: advisory + proposte */
      '<section class="dash-list dash-section">' +
        '<h3>Segnalazioni del Brain</h3>' +
        '<div id="dash-advisories-body"><div style="padding:16px;color:var(--text-3)">Caricamento…</div></div>' +
      '</section>' +
      '<section class="dash-list dash-section">' +
        '<h3>Proposte</h3>' +
        '<div id="dash-proposals-body"><div style="padding:16px;color:var(--text-3)">Caricamento…</div></div>' +
      '</section>';

    _feedLastSeen = feedReadLastSeen();
    Promise.all([loadReasoning(), loadAdvisories(), loadProposalsPeek()])
      .then(feedFinalizeNew, feedFinalizeNew);
  }

  function loadReasoning() {
    return fetch('api/brain/feed?type=reasoning,brain_action&limit=10').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      var body = document.getElementById('dash-reasoning-body');
      if (!body) return;
      var items = d.items || [];
      if (!items.length) {
        body.innerHTML = '<div style="padding:16px;color:var(--text-3)">Il Brain non ha ancora ragionamenti registrati.</div>';
        return;
      }
      body.innerHTML = items.map(function(it) {
        return '<div class="dl-row" data-ts="' + escHtml(it.ts || '') + '">' +
          '<span class="dl-time">' + escHtml(it.ts || '') + '</span>' +
          '<span class="dl-text">' + escHtml(it.body || '') + '</span>' +
        '</div>';
      }).join('');
      feedMarkNew(body);
    }).catch(function(err) {
      console.error('dashboard reasoning fetch failed', err);
      var body = document.getElementById('dash-reasoning-body');
      if (body) body.innerHTML = '<div class="proposals-error">Errore nel caricamento dei ragionamenti.</div>';
    });
  }

  function loadAdvisories() {
    return fetch('api/brain/advisories?status=open').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      var advs = d.advisories || [];
      var countEl = document.getElementById('dash-adv-count');
      if (countEl) countEl.textContent = advs.length;
      var body = document.getElementById('dash-advisories-body');
      if (!body) return;
      if (!advs.length) {
        body.innerHTML = '<div style="padding:16px;color:var(--text-3)">Nessuna segnalazione. Tutto in ordine.</div>';
        return;
      }
      body.innerHTML = advs.map(function(a) {
        var link = (a.fix_kind === 'hiris_config')
          ? '<a class="btn btn-sm" href="#/gateway">Apri Gateway</a>' : '';
        var severity = a.severity || 'info';
        /* Classe CSS sul valore grezzo (adv-info/adv-warn/adv-high, per lo
           styling), etichetta visibile dal dizionario condiviso (labels.js)
           -- prima qui finiva severity.toUpperCase() (INFO/WARN/HIGH, mai
           tradotto). */
        return '<div class="adv-card adv-' + escHtml(severity) + '" id="adv-' + escHtml(String(a.id)) + '"' +
          ' data-ts="' + escHtml(String(a.ts_updated || a.ts || '')) + '">' +
          '<div class="adv-sev">' + escHtml(HirisLabels.advisorySeverityLabel(severity)) + '</div>' +
          '<div class="adv-title">' + escHtml(a.title || '') + '</div>' +
          '<div class="prop-desc">' + escHtml(a.suggested_fix || '') + '</div>' +
          '<div class="prop-actions">' + link +
            '<button class="btn btn-sm" data-adv-act="ack" data-aid="' + escHtml(String(a.id)) + '">Ho capito</button>' +
            '<button class="btn btn-sm" data-adv-act="dismiss" data-aid="' + escHtml(String(a.id)) + '">Ignora</button>' +
          '</div></div>';
      }).join('');
      body.querySelectorAll('[data-adv-act]').forEach(function(b) {
        b.addEventListener('click', function() {
          advisoryAction(b.dataset.aid, b.dataset.advAct);
        });
      });
      feedMarkNew(body);
    }).catch(function(err) {
      console.error('dashboard advisories fetch failed', err);
      var countEl = document.getElementById('dash-adv-count');
      if (countEl) countEl.textContent = '—';
      var body = document.getElementById('dash-advisories-body');
      if (body) body.innerHTML = '<div class="proposals-error">Errore nel caricamento delle segnalazioni.</div>';
    });
  }

  function advisoryAction(id, act) {
    /* act is always 'ack' or 'dismiss' (set via data-adv-act on the buttons
       rendered by loadAdvisories); branch explicitly rather than
       concatenating act into the URL, so both endpoints are literal here. */
    var url = (act === 'dismiss')
      ? 'api/brain/advisories/' + encodeURIComponent(id) + '/dismiss'
      : 'api/brain/advisories/' + encodeURIComponent(id) + '/ack';
    fetch(url, {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(function(r) {
      if (!r.ok) { alert('Errore'); return; }
      var row = document.getElementById('adv-' + id);
      if (row) { row.style.opacity = '0.5'; setTimeout(function() { loadAdvisories(); }, 600); }
    }).catch(function() { alert('Errore di rete'); });
  }

  var PROPOSAL_LABELS = {
    ha_automation: '→ automazione HA',
    ha_dashboard: '→ dashboard HA',
    ha_script: '→ script HA',
    ha_scene: '→ scena HA',
    hiris_agent: '→ Agentbot'
  };

  function peekAction(id, kind) {
    var isReject = (kind === 'reject');
    if (!window.confirm(isReject ? 'Rifiutare questa proposta?' : 'Attivare questa proposta?')) return;
    var fn = isReject ? HirisProposalsCore.reject : HirisProposalsCore.apply;
    fn(id).then(function(res) {
      if (!res.ok) { window.alert(res.error || 'Errore'); return; }
      loadProposalsPeek();   // ricarica il peek: la card sparisce, il conteggio si aggiorna
    }, function() { window.alert('Errore di rete'); });
  }

  function loadProposalsPeek() {
    return fetch('api/proposals?status=pending').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      var props = (d.proposals || []).slice(0, 5);
      var countEl = document.getElementById('dash-prop-count');
      if (countEl) countEl.textContent = (d.proposals || []).length;
      var body = document.getElementById('dash-proposals-body');
      if (!body) return;
      if (!props.length) {
        body.innerHTML = '<div style="padding:16px;color:var(--text-3)">Nessuna proposta in attesa.</div>';
        return;
      }
      body.innerHTML = props.map(function(p) {
        var typeLabel = PROPOSAL_LABELS[p.type] || ('→ ' + escHtml(p.type || ''));
        /* Anche da qui si può attivare una proposta: se è una plancia con
           mode=replace, la sostituisce per intero. L'avviso deve stare dove
           l'utente decide, non solo nelle altre due viste. (L'azione Annulla
           resta invece solo nel pannello Proposte della chat.) */
        var pcfg = p.config || {};
        var warn = (p.type === 'ha_dashboard' && pcfg.mode === 'replace')
          ? '<div class="pp-warn">Sostituisce interamente la plancia "' + escHtml(String(pcfg.slug || '')) + '".</div>'
          : '';
        return '<div class="prop-card" data-ts="' + escHtml(String(p.created_at || '')) + '">' +
          '<div class="prop-title">' +
            '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;background:var(--accent-tint);color:var(--accent-ink);padding:1px 6px;border-radius:4px;font-family:var(--font-mono);margin-right:6px;vertical-align:middle">' + escHtml(typeLabel) + '</span>' +
            escHtml(p.name) +
          '</div>' +
          '<div class="prop-desc">' + escHtml(p.description || '') + '</div>' +
          warn +
          '<div class="prop-actions">' +
            '<button class="btn btn-sm btn-primary" data-act="apply" data-pid="' + escHtml(p.id) + '">Attiva</button>' +
            '<button class="btn btn-sm" data-act="reject" data-pid="' + escHtml(p.id) + '">Rifiuta</button>' +
          '</div>' +
        '</div>';
      }).join('');

      /* Apply/reject via il core condiviso + ricarica IL PROPRIO peek.
         NON deleghiamo più a applyProposal()/rejectProposal() di proposals.js:
         quelle sono cablate sul DOM della pagina Proposte (#pr-<id>,
         #proposals-list) e qui, dopo un apply riuscito, cadevano su
         checkEmptyList() -> null.querySelector -> falso "Errore di rete"
         (mentre l'automazione ERA già stata attivata). Vedi proposals-core.js. */
      body.querySelectorAll('[data-act="apply"]').forEach(function(b) {
        b.addEventListener('click', function() { peekAction(b.dataset.pid, 'apply'); });
      });
      body.querySelectorAll('[data-act="reject"]').forEach(function(b) {
        b.addEventListener('click', function() { peekAction(b.dataset.pid, 'reject'); });
      });
      feedMarkNew(body);
    }).catch(function(err) {
      console.error('dashboard proposals fetch failed', err);
      var body = document.getElementById('dash-proposals-body');
      var countEl = document.getElementById('dash-prop-count');
      if (countEl) countEl.textContent = '—';
      if (body) body.innerHTML = '<div class="proposals-error">Errore caricamento proposte.</div>';
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    var agents = HirisState.get('chatbots') || [];

    if (agents.length === 0) {
      /* Fetch agents directly (avoids depending on chatbot-editor.js loadChatbots) */
      fetchAgentsDirect().then(function(loaded) {
        HirisState.set('chatbots', loaded);
        if (loaded.length === 0) renderEmpty(outlet);
        else renderPopulated(outlet, loaded);
      }).catch(function(err) {
        /* Network/server error: show an error, NOT the first-run onboarding,
           and do not clobber shared state with a false empty list. */
        console.error('[dashboard] agents fetch failed', err);
        outlet.innerHTML = '<div class="proposals-error">Errore nel caricamento della dashboard. Riprova.</div>';
      });
    } else {
      renderPopulated(outlet, agents);
    }
  }

  window.HirisDashboard = {
    mount: mount,
    /* test seam (increment 2): la logica "nuovo dall'ultima visita" e' pura
       DOM + localStorage e va pinnata senza montare l'intera dashboard. */
    _feed: {
      markNew: feedMarkNew,
      finalize: feedFinalizeNew,
      setLastSeen: function(v) { _feedLastSeen = v; },
      readLastSeen: feedReadLastSeen
    }
  };
})();
