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

  /* Fallback fetch: loadAgents() in agent-form.js mutates module state and
     touches DOM (#agent-list); not safe to call before that DOM exists. */
  function fetchAgentsDirect() {
    /* Rejects on failure (does NOT coerce to []) so mount() can tell a real
       network/server error apart from a genuinely-empty first run -- otherwise
       a blip would show the first-run onboarding to a user who has agents. */
    return fetch('api/agents').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      /* api/agents returns either an array or {agents: [...]} */
      if (Array.isArray(d)) return d;
      return d.agents || [];
    });
  }

  function renderEmpty(outlet) {
    outlet.innerHTML =
      '<div class="page-title">Benvenuto in HIRIS</div>' +
      '<p class="page-subtitle">Configura il tuo primo Chatbot per Home Assistant. Scegli un template per iniziare velocemente, oppure parti da zero.</p>' +
      '<div class="stat-grid" style="grid-template-columns:repeat(auto-fit, minmax(150px, 1fr))">' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">⚡ Energia</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Monitor consumi</div>' +
          '<div class="st-delta">Rileva anomalie e suggerisce azioni</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">🏠 Rientro</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Scenario casa</div>' +
          '<div class="st-delta">Attiva luci/clima al rientro</div>' +
        '</a>' +
        '<a class="stat-tile" href="#/agents/new" style="text-decoration:none">' +
          '<div class="st-label">⏰ Promemoria</div>' +
          '<div class="st-value" style="font-size:var(--fs-15);font-weight:500;letter-spacing:normal">Notifiche schedulate</div>' +
          '<div class="st-delta">Reminder ricorrenti</div>' +
        '</a>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:12px">' +
        '<a class="btn btn-primary" href="#/agents/new">+ Crea Chatbot vuoto</a>' +
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
          '<a class="btn btn-primary" href="#/agents/new">+ Nuovo Chatbot</a>' +
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

    loadReasoning();
    loadAdvisories();
    loadProposalsPeek();
  }

  function loadReasoning() {
    fetch('api/brain/feed?type=reasoning,brain_action&limit=10').then(function(r) {
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
        return '<div class="dl-row">' +
          '<span class="dl-time">' + escHtml(it.ts || '') + '</span>' +
          '<span class="dl-text">' + escHtml(it.body || '') + '</span>' +
        '</div>';
      }).join('');
    }).catch(function(err) {
      console.error('dashboard reasoning fetch failed', err);
      var body = document.getElementById('dash-reasoning-body');
      if (body) body.innerHTML = '<div class="proposals-error">Errore nel caricamento dei ragionamenti.</div>';
    });
  }

  function loadAdvisories() {
    fetch('api/brain/advisories?status=open').then(function(r) {
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
        return '<div class="prop-card" id="adv-' + escHtml(String(a.id)) + '">' +
          '<div class="prop-title">' + escHtml(a.title || '') + '</div>' +
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

  function loadProposalsPeek() {
    fetch('api/proposals?status=pending').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      var props = (d.proposals || []).slice(0, 5);
      var countEl = document.getElementById('dash-prop-count');
      if (countEl) countEl.textContent = (d.proposals || []).length;
      var body = document.getElementById('dash-proposals-body');
      if (!body) return;
      if (!props.length) {
        body.innerHTML = '<div style="padding:16px;color:var(--text-3)">Nessuna proposta pending.</div>';
        return;
      }
      body.innerHTML = props.map(function(p) {
        return '<div class="prop-card">' +
          '<div class="prop-title">' +
            '<span style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;background:var(--accent-tint);color:var(--accent-ink);padding:1px 6px;border-radius:4px;font-family:var(--font-mono);margin-right:6px;vertical-align:middle">→ automazione HA</span>' +
            escHtml(p.name) +
          '</div>' +
          '<div class="prop-desc">' + escHtml(p.description || '') + '</div>' +
          '<div class="prop-actions">' +
            '<button class="btn btn-sm btn-primary" data-act="apply" data-pid="' + escHtml(p.id) + '">Attiva</button>' +
            '<button class="btn btn-sm" data-act="reject" data-pid="' + escHtml(p.id) + '">Rifiuta</button>' +
          '</div>' +
        '</div>';
      }).join('');

      /* Wire apply/reject buttons (delegate to existing logic in proposals.js if loaded) */
      body.querySelectorAll('[data-act="apply"]').forEach(function(b) {
        b.addEventListener('click', function() {
          if (typeof applyProposal === 'function') applyProposal(b.dataset.pid);
        });
      });
      body.querySelectorAll('[data-act="reject"]').forEach(function(b) {
        b.addEventListener('click', function() {
          if (typeof rejectProposal === 'function') rejectProposal(b.dataset.pid);
        });
      });
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
    var agents = HirisState.get('agents') || [];

    if (agents.length === 0) {
      /* Fetch agents directly (avoids depending on agent-form.js loadAgents) */
      fetchAgentsDirect().then(function(loaded) {
        HirisState.set('agents', loaded);
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

  window.HirisDashboard = { mount: mount };
})();
