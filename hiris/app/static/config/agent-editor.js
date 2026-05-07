/* HIRIS · Designer · agent editor mount (long-form, Phase 4.2)
   Mount delle 9 section-card e bridge alla logica legacy in agent-form.js. */
(function() {
  var legacyLoaded = false;
  var LEGACY_SCRIPTS = [
    'static/config/templates.js',
    'static/config/cron.js',
    'static/config/cron-popover.js',
    'static/config/triggers.js',
    'static/config/permessi.js',
    'static/config/action-editor.js',
    'static/config/script-action.js',
    'static/config/log-row.js',
    'static/config/logs.js',
    'static/config/usage.js',
    'static/config/proposals.js',
    'static/config/agent-form.js',
  ];

  function loadScript(src) {
    return new Promise(function(resolve, reject) {
      if (document.querySelector('script[data-legacy="' + src + '"]')) {
        resolve(); return;
      }
      var s = document.createElement('script');
      s.src = src;
      s.dataset.legacy = src;
      s.onload = resolve;
      s.onerror = function() { reject(new Error('failed to load ' + src)); };
      document.head.appendChild(s);
    });
  }

  function ensureLegacy() {
    if (legacyLoaded) return Promise.resolve();
    return LEGACY_SCRIPTS.reduce(function(p, src) {
      return p.then(function() { return loadScript(src); });
    }, Promise.resolve()).then(function() { legacyLoaded = true; });
  }

  function populateIdentita() {
    document.getElementById('sc-body-identita').innerHTML =
      '<div class="field-group">' +
        '<div class="fg-label">Identità</div>' +
        '<div class="field-row">' +
          '<div class="field"><label>Nome</label><input class="input" type="text" id="f-name" placeholder="Es: Monitor energia"></div>' +
          '<div class="field"><label>Tipo</label><select class="select" id="f-type">' +
            '<option value="agent">Agent — autonomo, trigger-based</option>' +
            '<option value="chat">Chat — risponde a messaggi utente</option>' +
          '</select></div>' +
        '</div>' +
      '</div>' +
      '<div class="field-group" id="agent-triggers-section">' +
        '<div class="fg-label">Trigger</div>' +
        '<p class="field-hint">L\'agente si attiva in risposta a questi eventi.</p>' +
        '<div id="triggers-list" style="display:flex;flex-wrap:wrap;gap:6px;min-height:10px;margin-bottom:8px"></div>' +
        '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start">' +
          '<select id="new-trigger-type" class="select" style="width:auto">' +
            '<option value="schedule">Periodico (ogni N min)</option>' +
            '<option value="state_changed">Cambio stato entità</option>' +
            '<option value="cron">Cron expression</option>' +
            '<option value="manual">Manuale (solo test run)</option>' +
          '</select>' +
          '<div id="nt-schedule-fields" style="display:flex;gap:6px;align-items:center">' +
            '<input class="input" type="number" id="nt-interval" value="5" min="1" style="width:90px">' +
            '<span style="font-size:12px;color:var(--text-3)">min</span>' +
          '</div>' +
          '<div id="nt-state-fields" style="display:none">' +
            '<input class="input" type="text" id="nt-entity" placeholder="binary_sensor.door" style="width:240px">' +
          '</div>' +
          '<div id="nt-cron-fields" style="display:none">' +
            '<span class="cron-chip" id="nt-cron-chip" tabindex="0">' +
              '<span>🕐</span><span id="nt-cron-chip-label">Ogni giorno alle 06:00</span><code id="nt-cron-chip-expr">0 6 * * *</code><span>▾</span>' +
            '</span>' +
            '<input type="hidden" id="nt-cron" value="0 6 * * *">' +
          '</div>' +
          '<button type="button" id="btn-add-trigger" class="btn btn-sm">+ Aggiungi</button>' +
        '</div>' +
      '</div>';
  }

  function populateIstruzioni() {
    document.getElementById('sc-body-istruzioni').innerHTML =
      '<div class="field"><label>Template contesto</label>' +
        '<select class="select" id="f-template"><option value="">— nessun template —</option></select>' +
        '<p class="field-hint">Seleziona un template per precompilare contesto + system prompt.</p></div>' +
      '<div class="field"><label>Contesto Strategico</label>' +
        '<textarea class="textarea" id="f-strategic" rows="5" placeholder="Es: La famiglia è composta da 2 adulti..."></textarea>' +
        '<p class="field-hint">Informazioni stabili sulla casa. Precedono il System Prompt.</p></div>' +
      '<div class="field"><label>System Prompt</label>' +
        '<textarea class="textarea" id="f-prompt" rows="4" placeholder="Descrivi il comportamento specifico..."></textarea>' +
        '<p class="field-hint">Istruzioni operative specifiche per questo agente.</p></div>' +
      '<div class="token-bar" id="token-bar">' +
        '<div class="token-row"><span class="token-label">Contesto strategico</span><span class="token-val" id="tc-strategic">—</span></div>' +
        '<div class="token-sep"></div>' +
        '<div class="token-row"><span class="token-label">System prompt</span><span class="token-val" id="tc-prompt">—</span></div>' +
        '<div class="token-sep"></div>' +
        '<div class="token-row"><span class="token-label">Totale statico (stima)</span><span class="token-val" id="tc-total">—</span></div>' +
        '<div class="token-sep"></div>' +
        '<div class="token-row"><span class="token-label">Context dinamico (≈)</span><span class="token-val" id="tc-context">—</span></div>' +
      '</div>' +
      '<details class="context-preview-wrap" id="context-preview-wrap" style="display:none">' +
        '<summary>🔍 Anteprima context_str</summary>' +
        '<pre id="context-preview-content"></pre>' +
      '</details>';
  }

  function populateModello() {
    document.getElementById('sc-body-modello').innerHTML =
      '<div class="field"><label>Modello</label><select class="select" id="f-model"><option value="auto">auto — segue tipo agente</option></select>' +
      '<p class="field-hint" id="model-hint">Seleziona il modello AI. <em>auto</em> sceglie automaticamente.</p></div>' +
      '<div id="confirm-free-row" style="display:none"><label class="checkbox-row"><input type="checkbox" id="f-confirm-free"> Accetto i rischi del modello :free per agente schedulato</label>' +
      '<p class="field-hint">I modelli :free di OpenRouter hanno quota giornaliera bassa…</p></div>' +
      '<div class="field-row">' +
        '<div class="field"><label>Max token risposta</label><input class="input" type="number" id="f-max-tokens" value="4096" min="256" max="16000"></div>' +
        '<div class="field"><label>Extended Thinking budget</label><select class="select" id="f-thinking-budget">' +
          '<option value="0">disabilitato</option>' +
          '<option value="2048">2048 (light)</option>' +
          '<option value="4096">4096 (standard)</option>' +
          '<option value="8192">8192 (deep)</option>' +
          '<option value="16384">16384 (max)</option>' +
        '</select></div>' +
      '</div>' +
      '<div id="max-turns-row" style="display:none"><div class="field"><label>Max messaggi per sessione</label>' +
        '<input class="input" type="number" id="f-max-chat-turns" value="0" min="0" max="9999">' +
        '<p class="field-hint">0 = illimitato.</p></div></div>' +
      '<label class="checkbox-row"><input type="checkbox" id="f-restrict"> Limita conversazione alla casa</label>' +
      '<div class="field"><label>Modalità risposta</label><select class="select" id="f-response-mode">' +
        '<option value="auto">auto</option>' +
        '<option value="compact">compact (max 2-3 frasi)</option>' +
        '<option value="minimal">minimal (1 riga)</option>' +
      '</select></div>';
  }

  function populatePermessi() {
    document.getElementById('sc-body-permessi').innerHTML =
      '<div class="field-group"><div class="fg-label">Strumenti</div>' +
        '<div class="tool-checkboxes" id="tool-checks"></div></div>' +
      '<div class="field-group"><div class="fg-label">Entità accessibili</div>' +
        '<div class="entity-selector">' +
          '<div class="entity-domain-pills" id="entity-domain-pills">' +
            '<span class="domain-pill" data-pattern="light.*">💡 luci</span>' +
            '<span class="domain-pill" data-pattern="switch.*">🔌 switch</span>' +
            '<span class="domain-pill" data-pattern="sensor.*">📊 sensori</span>' +
            '<span class="domain-pill" data-pattern="climate.*">🌡️ clima</span>' +
            '<span class="domain-pill" data-pattern="cover.*">🪟 tapparelle</span>' +
            '<span class="domain-pill" data-pattern="valve.*">🚰 valvole</span>' +
            '<span class="domain-pill" data-pattern="binary_sensor.*">⚡ binari</span>' +
            '<span class="domain-pill" data-pattern="person.*">🧑 persone</span>' +
          '</div>' +
          '<input class="input" id="entity-search" placeholder="Cerca entità…">' +
          '<div id="entity-suggestions" class="entity-suggestions" style="display:none"></div>' +
          '<div id="entity-chips" class="entity-chips"></div>' +
          '<input type="hidden" id="f-entities">' +
        '</div></div>' +
      '<div id="f-actions-section" class="field-group" style="display:none">' +
        '<div class="fg-label">Azioni permesse</div>' +
        '<div class="tool-checkboxes" id="action-checks"></div></div>';
  }

  function populateAzioni() {
    document.getElementById('sc-body-azioni').innerHTML =
      '<div class="field-row">' +
        '<div class="field"><label>Modalità azioni</label><select class="select" id="f-action-mode">' +
          '<option value="automatic">Automatica — il modello decide</option>' +
          '<option value="configured">Configurata — regole esplicite</option>' +
        '</select></div>' +
      '</div>' +
      '<div id="configured-actions-section">' +
        '<div id="trigger-on-section" class="field-group">' +
          '<div class="fg-label">Stati agente</div>' +
          '<input class="input" type="text" id="f-states" value="OK, ATTENZIONE, ANOMALIA">' +
          '<label>Valutazione che attiva azioni</label>' +
          '<div id="trigger-on-checks" style="display:flex;flex-wrap:wrap;gap:10px"></div>' +
        '</div>' +
        '<div class="field-group"><div class="fg-label">Sequenza azioni</div>' +
          '<div id="actions-list" class="actions-list"></div>' +
          '<button type="button" class="btn btn-sm" id="btn-add-action">+ Aggiungi azione</button>' +
        '</div>' +
        '<div id="action-editor" class="action-editor" style="display:none">' +
          '<p class="field-hint">Action editor inline placeholder — sostituito da drawer in Phase 6.</p>' +
        '</div>' +
      '</div>';
  }

  function populateStato() {
    document.getElementById('sc-body-stato').innerHTML =
      '<label class="checkbox-row"><input type="checkbox" id="f-enabled"> Agente abilitato</label>' +
      '<p class="field-hint">Disabilitato = non gira automaticamente, ma può essere lanciato con Test Run.</p>' +
      '<label class="checkbox-row"><input type="checkbox" id="f-require-confirmation"> Richiedi conferma prima delle azioni</label>' +
      '<p class="field-hint">Attende "sì/ok" prima di chiamare call_ha_service.</p>';
  }

  function populateLog() {
    document.getElementById('sc-body-log').innerHTML =
      '<div id="log-body"><div class="log-empty">Nessuna esecuzione registrata.</div></div>';
  }

  function populateRun() {
    document.getElementById('sc-body-run').innerHTML = '<pre id="run-output"></pre>';
  }

  function populateConsumi() {
    document.getElementById('sc-body-consumi').innerHTML =
      '<div class="usage-content">' +
        '<div class="usage-grid">' +
          '<div class="usage-stat"><div class="us-val" id="u-ag-requests">—</div><div class="us-label">Richieste</div></div>' +
          '<div class="usage-stat"><div class="us-val" id="u-ag-input">—</div><div class="us-label">Token IN</div></div>' +
          '<div class="usage-stat"><div class="us-val" id="u-ag-output">—</div><div class="us-label">Token OUT</div></div>' +
          '<div class="usage-stat"><div class="us-val" id="u-ag-cost">—</div><div class="us-label">Costo stimato</div></div>' +
        '</div>' +
        '<div class="usage-last-run">Ultima esecuzione: <span id="u-ag-last-run">—</span></div>' +
        '<div class="usage-actions">' +
          '<button type="button" class="btn btn-sm" id="u-ag-reset-btn">↺ Azzera contatori</button>' +
          '<button type="button" class="btn btn-sm btn-danger" id="u-ag-toggle-btn">⊘ Blocca agente</button>' +
        '</div>' +
        '<div class="usage-budget">' +
          '<label>Budget massimo (€, 0 = nessun limite)</label>' +
          '<input class="input" type="number" id="u-ag-budget" min="0" step="0.01" value="0">' +
          '<button type="button" class="btn btn-sm" id="u-ag-budget-save-btn">Salva soglia</button>' +
        '</div>' +
      '</div>';
  }

  function setupAnchorNav() {
    var sections = document.querySelectorAll('.section-card');
    var links = {};
    document.querySelectorAll('.anchor-link[href^="#sec-"]').forEach(function(l) {
      links[l.getAttribute('href').slice(1)] = l;
    });
    if (!('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function(entries) {
      entries.forEach(function(e) {
        if (e.isIntersecting) {
          Object.values(links).forEach(function(x){ x.classList.remove('active'); });
          if (links[e.target.id]) links[e.target.id].classList.add('active');
        }
      });
    }, { rootMargin: '-30% 0px -60% 0px' });
    sections.forEach(function(s) { io.observe(s); });
  }

  function setupStickyActions(agentId) {
    var btnSave = document.getElementById('btn-save');
    var btnCancel = document.getElementById('btn-cancel');
    var btnTestRun = document.getElementById('btn-test-run');
    var btnDelete = document.getElementById('btn-delete');
    var status = document.getElementById('sa-status');

    function markDirty() {
      HirisState.set('unsaved', true);
      status.textContent = 'Modifiche non salvate ●';
      btnSave.disabled = false;
    }
    function markClean() {
      HirisState.set('unsaved', false);
      status.textContent = 'Salvato ✓';
      btnSave.disabled = true;
    }

    document.querySelectorAll('.section-card input, .section-card select, .section-card textarea').forEach(function(el) {
      el.addEventListener('change', markDirty);
      el.addEventListener('input', markDirty);
    });

    btnSave.addEventListener('click', function() {
      if (typeof saveAgent === 'function') {
        try { var p = saveAgent(); if (p && p.then) p.then(markClean); else markClean(); } catch(e) { console.error(e); }
      } else { markClean(); }
    });
    btnCancel.addEventListener('click', function() {
      if (HirisState.get('unsaved') && !confirm('Annullare le modifiche non salvate?')) return;
      window.location.hash = '#/agents';
    });
    btnTestRun.addEventListener('click', function() {
      if (typeof runAgent === 'function') runAgent();
    });
    btnDelete.addEventListener('click', function() {
      if (typeof deleteAgent === 'function') deleteAgent();
    });

    btnDelete.style.display = agentId ? '' : 'none';
  }

  /* Compatibility shims for legacy agent-form.js & friends — they touch DOM IDs
     of the old config.html markup that don't exist in v6 long-form. We create
     hidden stubs so .style/.textContent/.innerHTML/.classList accesses don't
     throw. Also provide no-op stubs for missing global functions (resetToFirstTab
     was in tabs.js which is removed in v6). */
  function addLegacyShims() {
    var shim = document.getElementById('legacy-shim-container');
    if (shim) return; /* already mounted (cached after first mount) */
    shim = document.createElement('div');
    shim.id = 'legacy-shim-container';
    shim.style.display = 'none';
    shim.setAttribute('aria-hidden', 'true');
    var stubIds = [
      'no-selection',     /* agent-form.js openAgent line 104 */
      'form',             /* agent-form.js openAgent line 105 */
      'form-title',       /* agent-form.js openAgent line 107 */
      'delete-btn',       /* agent-form.js openAgent line 140 + IIFE 265 (!= v6 #btn-delete) */
      'new-btn',          /* agent-form.js IIFE line 161 addEventListener */
      'agent-list',       /* agent-form.js renderList */
      'agent-tabs',       /* agent-form.js showAgentMode querySelector */
      'tab-azioni',       /* agent-form.js showAgentMode classList check */
      'save-btn',         /* agent-form.js IIFE line 245 — sennò TypeError ferma IIFE */
      'run-btn',          /* agent-form.js IIFE line 291 — idem */
      'usage-reset-btn',  /* usage.js IIFE line 74 — id legacy global panel rimosso in v6 */
    ];
    stubIds.forEach(function(id) {
      if (document.getElementById(id)) return;
      var el = document.createElement('div');
      el.id = id;
      shim.appendChild(el);
    });
    document.body.appendChild(shim);

    /* No-op global stubs for functions whose modules were removed in v6 refactor */
    if (typeof window.resetToFirstTab !== 'function') {
      window.resetToFirstTab = function() { /* no-op: v6 long-form has no tabs */ };
    }
    if (typeof window.switchTab !== 'function') {
      window.switchTab = function() { /* no-op: v6 long-form has no tabs */ };
    }
  }

  /* Rebind legacy IIFE-time event listeners to the v6 DOM nodes.
     Le legacy attaccano i listener a getElementById(...) UNA VOLTA al loro IIFE
     load. Ad ogni mount, populate*() rimpiazza l'innerHTML dei sc-body con
     nodi NUOVI ma stessi ID — i listener IIFE-bound puntano a nodi rimossi.
     Qui rebindiamo via .onchange/.onclick/.oninput (overwrite) sui nodi nuovi. */
  function rewireLegacyAfterMount() {
    /* triggers.js — switch tipo trigger reveals fields conditional */
    var nt = document.getElementById('new-trigger-type');
    if (nt) {
      nt.onchange = function() {
        var v = this.value;
        var s = document.getElementById('nt-schedule-fields');
        var st = document.getElementById('nt-state-fields');
        var cr = document.getElementById('nt-cron-fields');
        if (s) s.style.display = v === 'schedule' ? 'flex' : 'none';
        if (st) st.style.display = v === 'state_changed' ? '' : 'none';
        if (cr) cr.style.display = v === 'cron' ? '' : 'none';
        if (v === 'cron' && typeof _cronInitUI === 'function') {
          try { _cronInitUI(); } catch(e) {}
        }
      };
    }
    /* triggers.js — btn-add-trigger */
    var bat = document.getElementById('btn-add-trigger');
    if (bat) {
      bat.onclick = function() {
        var ttype = document.getElementById('new-trigger-type').value;
        var trigger = { type: ttype };
        if (ttype === 'schedule') trigger.interval_minutes = parseInt(document.getElementById('nt-interval').value) || 5;
        else if (ttype === 'state_changed') trigger.entity_id = document.getElementById('nt-entity').value.trim();
        else if (ttype === 'cron') trigger.cron = document.getElementById('nt-cron').value.trim();
        if (typeof window._agentTriggers === 'undefined') window._agentTriggers = [];
        window._agentTriggers.push(trigger);
        if (typeof _triggersRender === 'function') _triggersRender();
        var entityIn = document.getElementById('nt-entity');
        if (entityIn) entityIn.value = '';
        if (ttype === 'cron' && typeof _cronApply === 'function') _cronApply('0 6 * * *');
        else {
          var cronIn = document.getElementById('nt-cron');
          if (cronIn) cronIn.value = '';
        }
      };
    }
    /* triggers.js — chip remove on triggers-list */
    var tl = document.getElementById('triggers-list');
    if (tl) {
      tl.onclick = function(e) {
        var btn = e.target.closest('.chip-remove');
        if (!btn) return;
        var idx = parseInt(btn.dataset.idx);
        if (typeof window._agentTriggers !== 'undefined') {
          window._agentTriggers.splice(idx, 1);
          if (typeof _triggersRender === 'function') _triggersRender();
        }
      };
    }

    /* permessi.js — domain pills + entity search */
    document.querySelectorAll('.domain-pill').forEach(function(pill) {
      pill.onclick = function() {
        if (typeof _entitySelectorAdd === 'function') {
          _entitySelectorAdd(this.dataset.pattern);
        }
        var s = document.getElementById('entity-search');
        if (s) s.value = '';
      };
    });
    var es = document.getElementById('entity-search');
    var sg = document.getElementById('entity-suggestions');
    if (es && sg) {
      var searchTimer = null;
      es.oninput = function() {
        clearTimeout(searchTimer);
        var q = es.value.trim();
        if (!q) { sg.style.display = 'none'; return; }
        searchTimer = setTimeout(function() {
          fetch('api/entities?q=' + encodeURIComponent(q))
            .then(function(r) { return r.json(); })
            .then(function(items) {
              sg.innerHTML = '';
              if (!items.length) { sg.style.display = 'none'; return; }
              items.slice(0, 20).forEach(function(item) {
                var div = document.createElement('div');
                div.className = 'suggestion-item';
                var nm = item.name || '';
                div.innerHTML = '<span>' + (item.id || '').replace(/[<>&]/g, '') + '</span><span class="s-name">' + nm.replace(/[<>&]/g, '') + '</span>';
                div.addEventListener('click', function() {
                  if (typeof _entitySelectorAdd === 'function') _entitySelectorAdd(item.id);
                  es.value = ''; sg.style.display = 'none';
                });
                sg.appendChild(div);
              });
              sg.style.display = 'block';
            }).catch(function() {});
        }, 300);
      };
      es.onkeydown = function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var q = es.value.trim();
          if (q && typeof _entitySelectorAdd === 'function') {
            _entitySelectorAdd(q);
            es.value = ''; sg.style.display = 'none';
          }
        } else if (e.key === 'Escape') {
          sg.style.display = 'none';
        }
      };
    }

    /* agent-form.js — change handlers */
    var ft = document.getElementById('f-type');
    if (ft) ft.onchange = function(e) {
      if (typeof showAgentMode === 'function') showAgentMode(e.target.value);
      if (typeof updateConfirmFreeVisibility === 'function') updateConfirmFreeVisibility();
    };
    var fa = document.getElementById('f-action-mode');
    if (fa && typeof showActionMode === 'function') {
      fa.onchange = function(e) { showActionMode(e.target.value); };
    }
    var fm = document.getElementById('f-model');
    if (fm && typeof updateConfirmFreeVisibility === 'function') {
      fm.onchange = updateConfirmFreeVisibility;
    }
    var fs = document.getElementById('f-states');
    if (fs && typeof _buildTriggerOnChecks === 'function' &&
        typeof _defaultStates === 'function' && typeof _triggerOnValue === 'function') {
      fs.onblur = function() {
        _buildTriggerOnChecks(_defaultStates(), _triggerOnValue());
      };
    }

    /* logs.js — token counter on input */
    if (typeof updateTokenCounter === 'function') {
      var fst = document.getElementById('f-strategic');
      if (fst) fst.oninput = updateTokenCounter;
      var fp = document.getElementById('f-prompt');
      if (fp) fp.oninput = updateTokenCounter;
    }

    /* usage.js — agent-level usage buttons (overwrite IIFE-bound onclick) */
    var ur = document.getElementById('u-ag-reset-btn');
    if (ur) ur.onclick = function() {
      if (typeof window === 'undefined' || !window.HirisState) return;
      var aid = HirisState.get('activeAgentId');
      if (!aid || !confirm('Azzerare i contatori di questo agente?')) return;
      fetch('api/agents/' + encodeURIComponent(aid) + '/usage/reset', {
        method: 'POST', headers: { 'X-Requested-With': 'fetch' }
      }).then(function(r) {
        if (r.ok && typeof loadAgentUsage === 'function') loadAgentUsage(aid);
      }).catch(function(){});
    };
    var ut = document.getElementById('u-ag-toggle-btn');
    if (ut) ut.onclick = function() {
      var aid = HirisState.get('activeAgentId');
      if (!aid) return;
      var enabledNow = document.getElementById('f-enabled').checked;
      var newVal = !enabledNow;
      fetch('api/agents/' + encodeURIComponent(aid), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
        body: JSON.stringify({ enabled: newVal })
      }).then(function(r) {
        if (r.ok) {
          document.getElementById('f-enabled').checked = newVal;
          ut.textContent = newVal ? '⊘ Blocca agente' : '✓ Riabilita agente';
        }
      }).catch(function(){});
    };
    var ub = document.getElementById('u-ag-budget-save-btn');
    if (ub) ub.onclick = function() {
      var aid = HirisState.get('activeAgentId');
      if (!aid) return;
      var val = parseFloat(document.getElementById('u-ag-budget').value) || 0;
      fetch('api/agents/' + encodeURIComponent(aid), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
        body: JSON.stringify({ budget_eur_limit: val })
      }).catch(function(){});
    };
  }

  /* Init form for "Nuovo agente" (was in agent-form.js #new-btn IIFE handler).
     Replicates the reset sequence: clear fields + load empty triggers/actions/etc. */
  function initNewAgent() {
    /* agent-form.js currentId — reset */
    if (typeof window !== 'undefined') window.currentId = null;
    /* Replicate reset from agent-form.js:161-200 */
    if (typeof _triggersLoad === 'function') _triggersLoad([]);
    if (typeof _entitySelectorLoad === 'function') _entitySelectorLoad([]);
    if (typeof _actionsLoad === 'function') _actionsLoad([]);
    if (typeof buildToolChecks === 'function') buildToolChecks([]);
    if (typeof buildActionChecks === 'function') buildActionChecks([]);
    if (typeof _buildTriggerOnChecks === 'function') _buildTriggerOnChecks(['OK','ATTENZIONE','ANOMALIA'], ['ANOMALIA']);
    if (typeof showAgentMode === 'function') showAgentMode('agent');
    if (typeof showActionMode === 'function') showActionMode('automatic');

    var setVal = function(id, v) { var el = document.getElementById(id); if (el) el.value = v; };
    var setChk = function(id, v) { var el = document.getElementById(id); if (el) el.checked = v; };

    setVal('f-template', '');
    setVal('f-name', '');
    setVal('f-type', 'agent');
    setVal('f-prompt', '');
    setVal('f-strategic', '');
    setChk('f-enabled', true);
    setVal('f-confirm-free', '');
    setChk('f-confirm-free', false);
    if (typeof _setModelValue === 'function') _setModelValue('auto');
    if (typeof updateConfirmFreeVisibility === 'function') updateConfirmFreeVisibility();
    setVal('f-max-tokens', 4096);
    setChk('f-restrict', false);
    setChk('f-require-confirmation', false);
    setVal('f-max-chat-turns', 0);
    setVal('f-response-mode', 'auto');
    setVal('f-thinking-budget', '0');
    setVal('f-action-mode', 'automatic');
    setVal('u-ag-budget', 0);
    setVal('f-states', 'OK, ATTENZIONE, ANOMALIA');

    if (typeof updateTokenCounter === 'function') updateTokenCounter();

    /* Hide context preview, run output, agent usage stats */
    var ctxWrap = document.getElementById('context-preview-wrap');
    if (ctxWrap) ctxWrap.style.display = 'none';
    var ro = document.getElementById('run-output');
    if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }
  }

  /* Save / Run / Delete globals — agent-form.js bind these via IIFE on save-btn/
     run-btn/delete-btn (ID legacy non più presenti in v6), e i suoi binding NON
     vengono mai eseguiti per il TypeError IIFE. setupStickyActions cerca le
     callback come typeof === 'function' → senza queste rimangono no-op. */
  window.saveAgent = function() {
    if (typeof buildPayload !== 'function') {
      alert('buildPayload non caricato — riprova');
      return Promise.reject(new Error('buildPayload missing'));
    }
    var payload = buildPayload();
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeAgentId');
    var method = cid ? 'PUT' : 'POST';
    var url = cid ? ('api/agents/' + encodeURIComponent(cid)) : 'api/agents';
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(payload),
    }).then(function(r) {
      if (!r.ok) {
        return r.json().catch(function() { return {}; }).then(function(d) {
          alert(d.error || ('Errore salvataggio agente (HTTP ' + r.status + ')'));
          throw new Error('save failed');
        });
      }
      return r.json();
    }).then(function(a) {
      if (typeof loadAgents === 'function') {
        return loadAgents().then(function() {
          if (typeof openAgent === 'function') openAgent(a);
          /* If new agent: navigate to its detail route */
          if (!cid && a.id) window.location.hash = '#/agents/' + encodeURIComponent(a.id);
          return a;
        });
      }
      return a;
    });
  };

  window.runAgent = function() {
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeAgentId');
    if (!cid) return;
    var btn = document.getElementById('btn-test-run');
    var out = document.getElementById('run-output');
    if (btn) { btn.classList.add('running'); btn.disabled = true; }
    if (out) { out.style.display = ''; out.className = ''; out.textContent = 'Avvio esecuzione…'; }

    var ctrl = new AbortController();
    var timer = setTimeout(function() { ctrl.abort(); }, 90000);
    return fetch('api/agents/' + encodeURIComponent(cid) + '/run', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }, signal: ctrl.signal,
    }).then(function(r) { return r.json(); }).then(function(data) {
      clearTimeout(timer);
      var raw = (data.result || data.error || '').trim();
      if (out) {
        if (!raw) {
          out.className = 'run-empty';
          out.textContent = '(nessun risultato restituito dall\'agente)';
        } else if (typeof highlightOutput === 'function' && typeof esc === 'function') {
          out.innerHTML = highlightOutput(esc(raw));
        } else {
          out.textContent = raw;
        }
      }
      /* Refresh log + usage after run */
      if (typeof openAgent === 'function' && typeof window.agents !== 'undefined') {
        var found = window.agents.filter(function(a){return a.id===cid;})[0];
        if (typeof renderExecutionLog === 'function' && found) {
          /* Fetch fresh agent for updated execution_log */
          fetch('api/agents/' + encodeURIComponent(cid)).then(function(r){return r.ok?r.json():null;}).then(function(a){
            if (a && typeof renderExecutionLog === 'function') renderExecutionLog(a);
            if (a && typeof loadAgentUsage === 'function') loadAgentUsage(cid);
          });
        }
      }
    }).catch(function(e) {
      clearTimeout(timer);
      if (out) {
        out.className = 'run-error-text';
        out.textContent = e.name === 'AbortError'
          ? '⏱ Timeout: l\'agente non ha risposto entro 90 secondi.'
          : 'Errore: ' + (e.message || e);
      }
    }).then(function() {
      if (btn) { btn.classList.remove('running'); btn.disabled = false; }
    });
  };

  window.deleteAgent = function() {
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeAgentId');
    if (!cid) return;
    if (!confirm('Eliminare questo agente?')) return;
    return fetch('api/agents/' + encodeURIComponent(cid), {
      method: 'DELETE', headers: { 'X-Requested-With': 'fetch' }
    }).then(function(r) {
      if (!r.ok && r.status !== 204) {
        return r.json().catch(function(){return{};}).then(function(d){
          alert(d.error || ('Errore eliminazione (HTTP ' + r.status + ')'));
          throw new Error('delete failed');
        });
      }
      window.currentId = null;
      if (typeof loadAgents === 'function') loadAgents();
      window.location.hash = '#/agents';
    });
  };

  /* Resolve an agentId to a full agent object via the API. The legacy openAgent()
     in agent-form.js expects the full object, not just an id. */
  function resolveAgent(agentId) {
    /* Try cached list from HirisState first */
    var cached = HirisState.get('agents');
    if (cached && cached.length) {
      var hit = cached.filter(function(a) { return a.id === agentId; })[0];
      if (hit) return Promise.resolve(hit);
    }
    /* Fallback: fetch full list and find */
    return fetch('api/agents')
      .then(function(r) { return r.ok ? r.json() : []; })
      .then(function(d) {
        var list = Array.isArray(d) ? d : (d.agents || []);
        HirisState.set('agents', list);
        /* Also populate legacy global so renderList etc work */
        if (typeof window !== 'undefined') window.agents = list;
        var found = list.filter(function(a) { return a.id === agentId; })[0];
        if (!found) throw new Error('Agente non trovato: ' + agentId);
        return found;
      });
  }

  function mount(agentId) {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML = '';
    outlet.appendChild(document.getElementById('tpl-agent-editor').content.cloneNode(true));
    populateIdentita();
    populateIstruzioni();
    populateModello();
    populatePermessi();
    populateAzioni();
    populateStato();
    populateLog();
    populateRun();
    populateConsumi();
    setupAnchorNav();
    addLegacyShims();

    /* Load legacy modules dynamically (only first time, then cached) */
    ensureLegacy().then(function() {
      /* Bootstrap functions never called by v6 (vecchio main.js le chiamava) */
      if (typeof populateTemplateSelector === 'function') {
        try { populateTemplateSelector(); } catch(e) { console.error('populateTemplateSelector', e); }
      }
      if (typeof loadModels === 'function') {
        try { loadModels(); } catch(e) { console.error('loadModels', e); }
      }

      /* Rebind IIFE-time legacy listeners ai nodi v6 (necessario ad ogni mount
         perché populate*() ricrea il DOM con gli stessi ID ma nodi diversi) */
      rewireLegacyAfterMount();

      setupStickyActions(agentId);

      if (agentId && typeof openAgent === 'function') {
        return resolveAgent(agentId).then(function(agentObj) {
          openAgent(agentObj);
        });
      } else if (!agentId) {
        /* New agent — replicate vecchio #new-btn IIFE handler reset */
        initNewAgent();
      }
    }).catch(function(e) {
      console.error('Failed to load legacy modules or open agent', e);
      var outlet = document.getElementById('route-outlet');
      outlet.innerHTML = '<div style="padding:24px;color:var(--err)"><h2>Errore caricamento editor</h2><p>' + (e && e.message ? e.message : String(e)) + '</p></div>';
    });
  }

  window.HirisAgentEditor = { mount: mount };
})();
