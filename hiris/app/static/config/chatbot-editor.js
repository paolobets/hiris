/* HIRIS · Designer · agent editor mount (long-form, Phase 4.2)
   Mount delle 8 section-card di un editor Persona (Task 4/Slice 5 rimosse
   Tipo/Trigger da Identità e l'intera section-card Azioni) e bridge alla
   logica legacy in chatbot-form.js. */
(function() {
  /* Cache-bust automatico per i 7 legacy script dynamic-loaded via loadScript().
     Il backend (_inject_version in server.py, via _ASSET_REF_RE/_asset_fingerprint)
     appende già un content-hash "?v=<hash>" alla src di QUESTO script quando
     serve config.html — lo leggiamo qui (nessuna chiamata di rete aggiuntiva,
     solo lettura sincrona di document.currentScript.src) e lo riusiamo per
     bustare la cache dei legacy script iniettati lato client. Così il bust
     cambia automaticamente ogni volta che chatbot-editor.js viene modificato,
     senza bump manuale.
     Limite noto: l'hash è quello di QUESTO file, non dei singoli LEGACY_SCRIPTS
     (che non passano da _inject_version perché iniettati via JS, non presenti
     come <script src> in config.html). Se cambia SOLO uno dei LEGACY_SCRIPTS
     senza toccare questo file, il bust non cambia — in quel caso serve comunque
     un tocco (anche solo un commento) a questo file per forzare il refresh.
     Fallback alla costante sotto se lo script non è servito con query string
     (es. accesso diretto al file senza passare da _serve_config). */
  var V6_CACHE_BUST = (function() {
    try {
      var selfScript = document.currentScript ||
        document.querySelector('script[src*="chatbot-editor.js"]');
      if (selfScript && selfScript.src) {
        var m = /[?&]v=([^&]+)/.exec(selfScript.src);
        if (m && m[1]) return decodeURIComponent(m[1]);
      }
    } catch (e) {}
    return '0.11.0'; /* fallback manuale se non c'è query string sulla src */
  })();

  /* Istanza corrente del selettore entità (config/entity-picker.js,
     istanziabile — non più il vecchio singleton _entitySelectionSet di
     permessi.js). Ricreata a ogni populatePermessi(); la vecchia istanza
     viene distrutta prima (destroy() stacca il listener documento del
     click-fuori, altrimenti leak a ogni remount). Esposta anche su
     window.HirisAgentEntityPicker perché chatbot-form.js (openAgent/
     buildPayload) è un file separato senza accesso a questa closure. */
  var entityPickerInstance = null;

  var legacyLoaded = false;
  /* Task 4 (Slice 5): rimossi cron.js/cron-popover.js/triggers.js/
     action-editor.js/script-action.js — erano la macchina di trigger e
     sequenza-azioni ritirata insieme al backend (Task 1-3). Il Designer
     ora carica solo i moduli di un editor Persona. */
  var LEGACY_SCRIPTS = [
    'static/config/templates.js',
    'static/config/permessi.js',
    'static/config/log-row.js',
    'static/config/logs.js',
    'static/config/usage.js',
    'static/config/proposals.js',
    'static/config/chatbot-form.js',
  ];

  function loadScript(src) {
    return new Promise(function(resolve, reject) {
      if (document.querySelector('script[data-legacy="' + src + '"]')) {
        resolve(); return;
      }
      var s = document.createElement('script');
      s.src = src + (src.indexOf('?') >= 0 ? '&' : '?') + 'v=' + encodeURIComponent(V6_CACHE_BUST);
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

  /* Task 4 (Slice 5): rimossi il selettore Tipo (agent/chat) e l'intera
     sezione Trigger — l'esecuzione trigger-based/autonoma è stata ritirata
     (Task 1-3). Il Designer edita solo Persona: il campo Nome è quanto
     resta di "Identità". */
  function populateIdentita() {
    document.getElementById('sc-body-identita').innerHTML =
      '<div class="field-group">' +
        '<div class="fg-label">Identità</div>' +
        '<div class="field-row">' +
          '<div class="field"><label for="f-name">Nome</label><input class="input" type="text" id="f-name" placeholder="Es: Assistente Cucina"></div>' +
        '</div>' +
      '</div>';
  }

  function populateIstruzioni() {
    document.getElementById('sc-body-istruzioni').innerHTML =
      '<div class="field"><label for="f-template">Template contesto</label>' +
        '<select class="select" id="f-template"><option value="">— nessun template —</option></select>' +
        '<p class="field-hint">Seleziona un template per precompilare contesto + system prompt.</p></div>' +
      '<div class="field"><label for="f-strategic">Contesto Strategico</label>' +
        '<textarea class="textarea" id="f-strategic" rows="5" placeholder="Es: La famiglia è composta da 2 adulti..."></textarea>' +
        '<p class="field-hint">Informazioni stabili sulla casa. Precedono il System Prompt.</p></div>' +
      '<div class="field"><label for="f-prompt">System Prompt</label>' +
        '<textarea class="textarea" id="f-prompt" rows="4" placeholder="Descrivi il comportamento specifico..."></textarea>' +
        '<p class="field-hint">Istruzioni operative specifiche per questo Chatbot.</p></div>' +
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

  /* Task 4 (Slice 5): rimossa la riga "confirm-free" (era legata al tipo
     agente autonomo/schedulato, ritirato con Task 1-3 — ogni persona è
     chat). max-turns-row era nascosta di default e mostrata solo per
     type==='chat'; ora è sempre visibile (nessun altro tipo esiste). */
  function populateModello() {
    document.getElementById('sc-body-modello').innerHTML =
      '<div class="field"><label for="f-model">Modello</label><select class="select" id="f-model"><option value="auto">auto — sceglie il modello migliore</option></select>' +
      '<p class="field-hint" id="model-hint">Seleziona il modello AI. <em>auto</em> sceglie automaticamente.</p></div>' +
      '<div class="field-row">' +
        '<div class="field"><label for="f-max-tokens">Max token risposta</label><input class="input" type="number" id="f-max-tokens" value="4096" min="256" max="16000"></div>' +
        '<div class="field"><label for="f-thinking-budget">Extended Thinking budget</label><select class="select" id="f-thinking-budget">' +
          '<option value="0">disabilitato</option>' +
          '<option value="2048">2048 (light)</option>' +
          '<option value="4096">4096 (standard)</option>' +
          '<option value="8192">8192 (deep)</option>' +
          '<option value="16384">16384 (max)</option>' +
        '</select></div>' +
      '</div>' +
      '<div id="max-turns-row"><div class="field"><label for="f-max-chat-turns">Max messaggi per sessione</label>' +
        '<input class="input" type="number" id="f-max-chat-turns" value="0" min="0" max="9999">' +
        '<p class="field-hint">0 = illimitato.</p></div></div>' +
      '<label class="checkbox-row"><input type="checkbox" id="f-restrict"> Limita conversazione alla casa</label>' +
      '<div class="field"><label for="f-response-mode">Modalità risposta</label><select class="select" id="f-response-mode">' +
        '<option value="auto">auto</option>' +
        '<option value="compact">compact (max 2-3 frasi)</option>' +
        '<option value="minimal">minimal (1 riga)</option>' +
      '</select></div>';
  }

  function populatePermessi() {
    /* Istanza precedente (mount precedente) non ancora distrutta -> stacca
       il suo listener documento prima di buttare via il DOM sotto di lei. */
    if (entityPickerInstance) {
      entityPickerInstance.destroy();
      entityPickerInstance = null;
      window.HirisAgentEntityPicker = null;
    }

    document.getElementById('sc-body-permessi').innerHTML =
      '<div class="field-group"><div class="fg-label">Strumenti</div>' +
        '<div class="tool-checkboxes" id="tool-checks"></div></div>' +
      '<div class="field-group"><div class="fg-label">Entità accessibili</div>' +
        '<div id="entity-picker-root"></div></div>' +
      '<div id="f-actions-section" class="field-group" style="display:none">' +
        '<div class="fg-label">Azioni permesse</div>' +
        '<div class="tool-checkboxes" id="action-checks"></div></div>';

    entityPickerInstance = HirisEntityPicker.create(document.getElementById('entity-picker-root'), {
      placeholder: 'Cerca entità…',
      pills: [
        { label: '💡 luci', pattern: 'light.*' },
        { label: '🔌 switch', pattern: 'switch.*' },
        { label: '📊 sensori', pattern: 'sensor.*' },
        { label: '🌡️ clima', pattern: 'climate.*' },
        { label: '🪟 tapparelle', pattern: 'cover.*' },
        { label: '🚰 valvole', pattern: 'valve.*' },
        { label: '⚡ binari', pattern: 'binary_sensor.*' },
        { label: '🧑 persone', pattern: 'person.*' },
      ],
    });
    window.HirisAgentEntityPicker = entityPickerInstance;
  }

  function populateStato() {
    document.getElementById('sc-body-stato').innerHTML =
      '<label class="checkbox-row"><input type="checkbox" id="f-enabled"> Chatbot abilitato</label>' +
      '<p class="field-hint">Controlla solo lo stato dell\'entità switch Home Assistant di questo Chatbot; puoi comunque verificarlo con Test Run indipendentemente da questo interruttore.</p>' +
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

  /* Task 4 (Slice 5) review fix: rimosso il controllo "Budget massimo (€)"
     (PUT budget_eur_limit) — il backend ha ritirato quel campo (Task 2) e lo
     scarta silenziosamente, quindi la UI mostrava un controllo che non
     faceva più nulla. */
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
          '<button type="button" class="btn btn-sm btn-danger" id="u-ag-toggle-btn">⊘ Blocca Chatbot</button>' +
        '</div>' +
      '</div>';
  }

  function setupAnchorNav() {
    var sections = document.querySelectorAll('.section-card');
    var links = {};
    document.querySelectorAll('.anchor-link[href^="#sec-"]').forEach(function(l) {
      links[l.getAttribute('href').slice(1)] = l;
      /* v0.10.5: intercetta click anchor per evitare cambio di hash.
         Click <a href="#sec-X"> nativo cambia URL hash → router fires
         hashchange → no route matched → service worker HA Ingress prova
         fetch del nuovo URL e fallisce ("Uncaught (in promise) Object").
         Più: history pollution + remount loop quando user torna su #/chatbots/<id>. */
      l.addEventListener('click', function(e) {
        e.preventDefault();
        var targetId = l.getAttribute('href').slice(1);
        var target = document.getElementById(targetId);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
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
    /* v0.10.8: rimosso sa-status. Lo stato dirty/saved è indicato dal solo
       pulsante Salva (disabled = saved, enabled = changes pending). */

    function markDirty() {
      HirisState.set('unsaved', true);
      if (btnSave) btnSave.disabled = false;
    }
    function markClean() {
      HirisState.set('unsaved', false);
      if (btnSave) btnSave.disabled = true;
    }

    document.querySelectorAll('.section-card input, .section-card select, .section-card textarea').forEach(function(el) {
      el.addEventListener('change', markDirty);
      el.addEventListener('input', markDirty);
    });

    btnSave.addEventListener('click', function() {
      if (typeof saveAgent === 'function') {
        try {
          var p = saveAgent();
          if (p && p.then) p.then(function(res) { markClean(); }).catch(function(err) { console.error('save rejected:', err); });
          else markClean();
        } catch(e) { console.error('saveAgent threw:', e); alert('Save error: ' + (e.message || e)); }
      } else {
        console.warn('saveAgent not defined — markClean only');
        alert('window.saveAgent non definito. Hard reload Ctrl+Shift+R per scaricare cache stale.');
        markClean();
      }
    });
    btnCancel.addEventListener('click', function() {
      if (HirisState.get('unsaved') && !confirm('Annullare le modifiche non salvate?')) return;
      window.location.hash = '#/chatbots';
    });
    btnTestRun.addEventListener('click', function() {
      if (typeof runAgent === 'function') {
        try { runAgent(); } catch(e) { console.error('runAgent threw:', e); alert('TestRun error: ' + (e.message || e)); }
      } else {
        console.warn('runAgent not defined');
        alert('window.runAgent non definito. Hard reload Ctrl+Shift+R per scaricare cache stale.');
      }
    });
    btnDelete.addEventListener('click', function() {
      if (typeof deleteAgent === 'function') {
        try { deleteAgent(); } catch(e) { console.error('deleteAgent threw:', e); alert('Delete error: ' + (e.message || e)); }
      } else {
        console.warn('deleteAgent not defined');
        alert('window.deleteAgent non definito. Hard reload Ctrl+Shift+R per scaricare cache stale.');
      }
    });

    btnDelete.style.display = agentId ? '' : 'none';
  }

  /* Compatibility shims for legacy chatbot-form.js & friends — they touch DOM IDs
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
    /* v0.10.5 cleanup: ridotto stub list a soli ID ancora referenziati dal
       codice legacy live (openAgent + usage.js IIFE).
       Rimossi: new-btn/save-btn/run-btn (handler IIFE eliminati in cleanup),
       agent-list/agent-tabs/tab-azioni (renderList + #agent-tabs querySelector
       eliminati).
       delete-btn ancora qui perché openAgent setta is_default visibility su
       quel ID (legacy markup); il vero pulsante v6 è #btn-delete e la sua
       visibility è gestita da setupStickyActions + resolveAgent then-block. */
    var stubIds = [
      'no-selection',     /* chatbot-form.js openAgent legacy compat */
      'form',             /* chatbot-form.js openAgent legacy compat */
      'form-title',       /* chatbot-form.js openAgent legacy compat */
      'delete-btn',       /* chatbot-form.js openAgent is_default check (legacy) */
      'usage-reset-btn',  /* usage.js IIFE — id legacy global panel rimosso in v6 */
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
    /* Task 4 (Slice 5): rimossi i rebind di new-trigger-type/nt-entity/
       btn-add-trigger/triggers-list — la sezione Trigger e triggers.js sono
       stati ritirati insieme alla macchina action/rules/states (Task 1-3). */

    /* SP-4 Fase B Task 1: rimosso il rebind manuale di domain-pill/
       entity-search/entity-suggestions. Il selettore entità ora è
       config/entity-picker.js (HirisEntityPicker.create), istanziato da
       populatePermessi() con listener propri per istanza — questo
       "rewire dopo il fatto" esisteva solo per ricollegare i listener
       IIFE-time del vecchio singleton (permessi.js) a nodi rimontati.
       Non serve più: ogni mount crea una nuova istanza con i propri
       listener già corretti, e la vecchia viene distrutta (destroy(),
       che stacca il listener documento del click-fuori invece di
       lasciarlo agganciato a nodi detached — era un leak). */

    /* Task 4 (Slice 5): rimossi i rebind di f-type/f-action-mode/f-states —
       quei campi non esistono più nel markup (Tipo/Azioni/Stati ritirati).
       f-model non ha più un handler qui: updateConfirmFreeVisibility era
       legato solo al tipo agente autonomo, anch'esso ritirato. */

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
      var aid = HirisState.get('activeChatbotId');
      if (!aid || !confirm('Azzerare i contatori di questo Chatbot?')) return;
      fetch('api/chatbots/' + encodeURIComponent(aid) + '/usage/reset', {
        method: 'POST', headers: { 'X-Requested-With': 'fetch' }
      }).then(function(r) {
        if (r.ok && typeof loadAgentUsage === 'function') loadAgentUsage(aid);
      }).catch(function(){});
    };
    var ut = document.getElementById('u-ag-toggle-btn');
    if (ut) ut.onclick = function() {
      var aid = HirisState.get('activeChatbotId');
      if (!aid) return;
      var enabledNow = document.getElementById('f-enabled').checked;
      var newVal = !enabledNow;
      fetch('api/chatbots/' + encodeURIComponent(aid), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
        body: JSON.stringify({ enabled: newVal })
      }).then(function(r) {
        if (r.ok) {
          document.getElementById('f-enabled').checked = newVal;
          ut.textContent = newVal ? '⊘ Blocca Chatbot' : '✓ Riabilita Chatbot';
        }
      }).catch(function(){});
    };
    /* Task 4 (Slice 5) review fix: rimosso il rebind di u-ag-budget-save-btn
       — il controllo "Budget massimo (€)" (PUT budget_eur_limit) è stato
       tolto dal markup in populateConsumi(), il backend scarta quel campo. */
  }

  /* Init form for "Nuovo agente" (was in chatbot-form.js #new-btn IIFE handler).
     Replicates the reset sequence: clear fields + load empty persona state.
     Task 4 (Slice 5): rimossi i reset di triggers/actions/stati/action-mode/
     tipo/confirm-free/budget — tutti campi ritirati insieme alla macchina
     action/rules/states (Task 1-3) e al tab Azioni (questo task). */
  function initNewAgent() {
    /* chatbot-form.js currentId — reset */
    if (typeof window !== 'undefined') window.currentId = null;
    if (window.HirisAgentEntityPicker) window.HirisAgentEntityPicker.setValue([]);
    if (typeof buildToolChecks === 'function') buildToolChecks([]);
    if (typeof buildActionChecks === 'function') buildActionChecks([]);

    var setVal = function(id, v) { var el = document.getElementById(id); if (el) el.value = v; };
    var setChk = function(id, v) { var el = document.getElementById(id); if (el) el.checked = v; };

    setVal('f-template', '');
    setVal('f-name', '');
    setVal('f-prompt', '');
    setVal('f-strategic', '');
    setChk('f-enabled', true);
    if (typeof _setModelValue === 'function') _setModelValue('auto');
    setVal('f-max-tokens', 4096);
    setChk('f-restrict', false);
    setChk('f-require-confirmation', false);
    setVal('f-max-chat-turns', 0);
    setVal('f-response-mode', 'auto');
    setVal('f-thinking-budget', '0');

    if (typeof updateTokenCounter === 'function') updateTokenCounter();

    /* Hide context preview, run output, agent usage stats */
    var ctxWrap = document.getElementById('context-preview-wrap');
    if (ctxWrap) ctxWrap.style.display = 'none';
    var ro = document.getElementById('run-output');
    if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }
  }

  /* Save / Run / Delete globals — chatbot-form.js bind these via IIFE on save-btn/
     run-btn/delete-btn (ID legacy non più presenti in v6), e i suoi binding NON
     vengono mai eseguiti per il TypeError IIFE. setupStickyActions cerca le
     callback come typeof === 'function' → senza queste rimangono no-op. */
  window.saveAgent = function() {
    if (typeof buildPayload !== 'function') {
      alert('buildPayload non caricato — riprova');
      return Promise.reject(new Error('buildPayload missing'));
    }
    var payload = buildPayload();
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeChatbotId');
    var method = cid ? 'PUT' : 'POST';
    var url = cid ? ('api/chatbots/' + encodeURIComponent(cid)) : 'api/chatbots';
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(payload),
    }).then(function(r) {
      if (!r.ok) {
        return r.json().catch(function() { return {}; }).then(function(d) {
          alert(d.error || ('Errore salvataggio Chatbot (HTTP ' + r.status + ')'));
          throw new Error('save failed');
        });
      }
      return r.json();
    }).then(function(a) {
      if (typeof loadChatbots === 'function') {
        return loadChatbots().then(function() {
          if (typeof openAgent === 'function') openAgent(a);
          /* If new agent: navigate to its detail route */
          if (!cid && a.id) window.location.hash = '#/chatbots/' + encodeURIComponent(a.id);
          return a;
        });
      }
      return a;
    });
  };

  /* v0.10.8: flag globale anti-doppio-click (button.disabled non basta, il
     click handler in setupStickyActions ha console.log PRIMA del check). */
  var _runInFlight = false;
  window.runAgent = function() {
    if (_runInFlight) {
      console.warn('runAgent già in flight — click ignorato');
      return Promise.resolve();
    }
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeChatbotId');
    if (!cid) {
      console.warn('runAgent: nessun agentId attivo');
      return Promise.resolve();
    }

    _runInFlight = true;

    var btn = document.getElementById('btn-test-run');
    var btnOriginalText = btn ? btn.textContent : '';
    var section = document.getElementById('sec-run');
    var sb = document.getElementById('sc-body-run');
    var out = document.getElementById('run-output');

    /* v0.10.8: feedback visivo IMMEDIATO PRIMA del fetch:
       - Banner "Test Run in corso" in cima alla section sec-run
       - Spinner sul bottone (CSS .running) + label change "⏱ In esecuzione…"
       - Scroll smooth alla section sec-run cosicché user veda il banner
       - Pulsante disabled */
    if (btn) {
      btn.classList.add('running');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>⏱ In esecuzione…';
    }

    /* Inietta banner + reset run-output dentro sc-body-run */
    if (sb) {
      sb.innerHTML =
        '<div class="run-running-banner" id="run-running-banner">' +
          '<span class="spinner"></span>' +
          '<span><strong>Test Run in corso…</strong> &nbsp;il Chatbot sta elaborando, attendere fino a 10 minuti.</span>' +
        '</div>' +
        '<pre id="run-output" style="background:var(--surface-2);padding:12px 14px;border-radius:6px;white-space:pre-wrap;min-height:60px;font-family:var(--font-mono);font-size:12px"></pre>';
      out = document.getElementById('run-output');
    }
    if (out) {
      out.className = '';
      out.textContent = 'Avvio esecuzione…';
    }

    /* Scroll alla section dopo che il banner è in DOM (rAF garantisce paint) */
    if (section) {
      requestAnimationFrame(function() {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }

    /* v0.10.9: timeout frontend 90s → 600s (10 min). Allineato al backend
       AGENT_RUN_TIMEOUT che fallback su OLLAMA_REQUEST_TIMEOUT * 1.2 (default
       600 con local_model.request_timeout=500). User con agente locale
       (es. IRRIGAZIONE su gemma4:e4b) e setting 600/800s vedeva fetch
       abortita lato frontend a 90s anche se backend era configurato per più. */
    var ctrl = new AbortController();
    var FRONTEND_RUN_TIMEOUT_MS = 600000; /* 10 min */
    var timer = setTimeout(function() { ctrl.abort(); }, FRONTEND_RUN_TIMEOUT_MS);

    function cleanupRunning() {
      _runInFlight = false;
      if (btn) {
        btn.classList.remove('running');
        btn.disabled = false;
        btn.innerHTML = '<span class="spinner"></span>▶ Test Run';
      }
      var banner = document.getElementById('run-running-banner');
      if (banner) banner.remove();
    }

    return fetch('api/chatbots/' + encodeURIComponent(cid) + '/run', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }, signal: ctrl.signal,
    }).then(function(r) {
      return r.json();
    }).then(function(data) {
      clearTimeout(timer);
      cleanupRunning();
      var raw = (data.result || data.error || '').trim();
      var hasError = !!data.error;
      if (out) {
        if (!raw) {
          out.className = 'run-empty';
          out.textContent = '(nessun risultato restituito dal Chatbot)';
        } else if (hasError) {
          out.className = 'run-error-text';
          out.textContent = '✗ ' + raw;
        } else if (typeof highlightOutput === 'function' && typeof esc === 'function') {
          out.className = '';
          out.innerHTML = '<div style="color:var(--ok);font-size:11px;font-weight:600;margin-bottom:6px;font-family:var(--font-sans)">✓ ESEGUITO</div>' + highlightOutput(esc(raw));
        } else {
          out.className = '';
          out.textContent = '✓ ' + raw;
        }
      }
      /* Refresh log + usage after run */
      fetch('api/chatbots/' + encodeURIComponent(cid)).then(function(r){return r.ok?r.json():null;}).then(function(a){
        if (a && typeof renderExecutionLog === 'function') renderExecutionLog(a);
        if (a && typeof loadAgentUsage === 'function') loadAgentUsage(cid);
      }).catch(function(){});
    }).catch(function(e) {
      clearTimeout(timer);
      cleanupRunning();
      console.error('runAgent error:', e);
      if (out) {
        out.className = 'run-error-text';
        out.textContent = e.name === 'AbortError'
          ? '⏱ Timeout: il Chatbot non ha risposto entro 10 minuti. Il modello locale potrebbe essere troppo lento o stuck — verifica i log Ollama.'
          : '✗ Errore: ' + (e.message || e);
      }
    });
  };

  window.deleteAgent = function() {
    var cid = (typeof window.currentId !== 'undefined' && window.currentId) || HirisState.get('activeChatbotId');
    if (!cid) return;
    if (!confirm('Eliminare questo Chatbot?')) return;
    return fetch('api/chatbots/' + encodeURIComponent(cid), {
      method: 'DELETE', headers: { 'X-Requested-With': 'fetch' }
    }).then(function(r) {
      if (!r.ok && r.status !== 204) {
        return r.json().catch(function(){return{};}).then(function(d){
          alert(d.error || ('Errore eliminazione (HTTP ' + r.status + ')'));
          throw new Error('delete failed');
        });
      }
      window.currentId = null;
      if (typeof loadChatbots === 'function') loadChatbots();
      window.location.hash = '#/chatbots';
    });
  };

  /* Resolve an agentId to a full agent object via the API. The legacy openAgent()
     in chatbot-form.js expects the full object, not just an id. */
  function resolveAgent(agentId) {
    /* Try cached list from HirisState first */
    var cached = HirisState.get('chatbots');
    if (cached && cached.length) {
      var hit = cached.filter(function(a) { return a.id === agentId; })[0];
      if (hit) return Promise.resolve(hit);
    }
    /* Fallback: fetch full list and find */
    return fetch('api/chatbots')
      .then(function(r) { return r.ok ? r.json() : []; })
      .then(function(d) {
        var list = Array.isArray(d) ? d : (d.agents || []);
        HirisState.set('chatbots', list);
        /* Also populate legacy global so renderList etc work */
        if (typeof window !== 'undefined') window.chatbots = list;
        var found = list.filter(function(a) { return a.id === agentId; })[0];
        if (!found) throw new Error('Chatbot non trovato: ' + agentId);
        return found;
      });
  }

  /* Wrap a step in try/catch with named logging. Re-throws to bubble to mount catch
     but prepends the step name so we can pinpoint which step crashed. */
  function step(name, fn) {
    try {
      return fn();
    } catch(e) {
      var msg = (e && e.message) ? e.message : String(e);
      var wrapped = new Error('[' + name + '] ' + msg);
      wrapped.cause = e;
      wrapped.step = name;
      console.error('Step "' + name + '" failed:', e);
      throw wrapped;
    }
  }

  function mount(agentId) {
    console.log('[HirisChatbotEditor] mount v' + V6_CACHE_BUST + ' agentId=' + agentId);
    var outlet = document.getElementById('route-outlet');
    if (!outlet) {
      console.error('route-outlet element missing — config.html broken');
      return;
    }

    /* Use Promise chain so all steps fall into the .catch with named errors */
    Promise.resolve().then(function() {
      step('clear outlet', function() { outlet.innerHTML = ''; });
      step('clone template', function() {
        var tpl = document.getElementById('tpl-agent-editor');
        if (!tpl) throw new Error('tpl-agent-editor not in config.html — BROKEN BUILD');
        outlet.appendChild(tpl.content.cloneNode(true));
      });
      step('populateIdentita', populateIdentita);
      step('populateIstruzioni', populateIstruzioni);
      step('populateModello', populateModello);
      step('populatePermessi', populatePermessi);
      step('populateStato', populateStato);
      step('populateLog', populateLog);
      step('populateRun', populateRun);
      step('populateConsumi', populateConsumi);
      step('setupAnchorNav', setupAnchorNav);
      step('addLegacyShims', addLegacyShims);
    }).then(function() {
      return ensureLegacy();
    }).then(function() {
      step('populateTemplateSelector', function() {
        if (typeof populateTemplateSelector === 'function') populateTemplateSelector();
      });
      step('loadModels', function() {
        if (typeof loadModels === 'function') loadModels();
      });
      step('rewireLegacyAfterMount', rewireLegacyAfterMount);
      step('setupStickyActions', function() { setupStickyActions(agentId); });

      if (agentId && typeof openAgent === 'function') {
        return resolveAgent(agentId).then(function(agentObj) {
          step('openAgent', function() { openAgent(agentObj); });
          /* Update breadcrumb con nome agente invece di id bare */
          var hereEl = document.getElementById('chrome-here');
          if (hereEl && agentObj && agentObj.name) {
            hereEl.textContent = 'Chatbot / ' + agentObj.name;
          }
          /* v0.10.5: hide btn-delete per default agents (HIRIS) */
          var btnDel = document.getElementById('btn-delete');
          if (btnDel && agentObj && agentObj.is_default) {
            btnDel.style.display = 'none';
          }
        });
      } else if (!agentId) {
        step('initNewAgent', initNewAgent);
      }
    }).catch(function(e) {
      console.error('[HirisChatbotEditor] mount failed:', e);
      var outlet2 = document.getElementById('route-outlet');
      if (outlet2) {
        var msg = (e && e.message) ? e.message : String(e);
        var stepName = e && e.step ? e.step : 'unknown';
        outlet2.innerHTML =
          '<div style="padding:24px;color:var(--err)">' +
            '<h2>Errore caricamento editor</h2>' +
            '<p>' + msg + '</p>' +
            '<p style="font-size:12px;color:var(--text-3);font-family:var(--font-mono);margin-top:16px">' +
              'Step: <strong>' + stepName + '</strong> · v' + V6_CACHE_BUST +
            '</p>' +
            '<p style="font-size:12px;color:var(--text-3)">' +
              'Se questo errore persiste dopo l\'aggiornamento dell\'addon HIRIS, fai <strong>hard reload</strong>: ' +
              'su PC <code>Ctrl+Shift+R</code>, su tablet pulisci cache da Impostazioni → App → Browser → Cancella dati. ' +
              'Apri DevTools console per stack trace completo.' +
            '</p>' +
          '</div>';
      }
    });
  }

  window.HirisChatbotEditor = { mount: mount };
})();
