/* HIRIS · Designer · agent editor mount (long-form, Phase 4.2)
   Mount delle 8 section-card di un editor Persona (Task 4/Slice 5 rimosse
   Tipo/Trigger da Identità e l'intera section-card Azioni) e bridge alla
   logica legacy in chatbot-form.js. */
(function() {
  /* SP-4 Fase B Task 2: rimosso il loader dinamico (cache-bust constant,
     lista script, funzione di caricamento a catena) — i 7 file prima
     iniettati dopo il mount sono ora <script src> statici in config.html
     (ordine dipendenze in testa al file). Questo risolve anche il
     cache-busting: _inject_version (server.py) fingerprinta ogni
     <script src> letterale individualmente, quindi ognuno di quei file
     ha ora il proprio hash invece di ereditare quello di chatbot-editor.js. */

  /* Istanza corrente del selettore entità (config/entity-picker.js,
     istanziabile — non più il vecchio singleton _entitySelectionSet di
     permessi.js). Ricreata a ogni populatePermessi(); la vecchia istanza
     viene distrutta prima (destroy() stacca il listener documento del
     click-fuori, altrimenti leak a ogni remount). Esposta anche su
     window.HirisAgentEntityPicker perché chatbot-form.js (openAgent/
     buildPayload) è un file separato senza accesso a questa closure. */
  var entityPickerInstance = null;

  /* SP-4 Fase B Task 3: stato del kit editor condiviso (config/editor-kit.js).
     - dirtyTrackHandle: il MutationObserver di HirisEditorKit.dirty.track(),
       ricreato a ogni mount (setupStickyActions) e fermato prima di quello
       nuovo — evita di accumulare observer su nodi ormai detached.
     - entityPickerOnDirty: riferimento a markDirty(), letto da
       populatePermessi() per agganciare l'onChange dell'entity-picker (i
       chip non sono <input>, quindi il MutationObserver da solo non li
       vedrebbe mai cambiare valore — vanno notificati esplicitamente).
       populatePermessi() gira DOPO setupStickyActions nel mount() qui
       sotto, così markDirty esiste già quando viene letto.
     - saveBarHandle: HirisEditorKit.saveBar(), il suo setDirty(bool)
       sostituisce il vecchio btnSave.disabled diretto.
     - toolCheckGroupInstance / actionCheckGroupInstance: le due istanze
       HirisEditorKit.checkGroup() (sostituiscono buildToolChecks/
       buildActionChecks/getSelectedTools/getSelectedActions di permessi.js,
       Task 3) esposte su window perché chatbot-form.js (openAgent/
       buildPayload) è un file separato senza accesso a questa closure —
       stesso pattern di window.HirisAgentEntityPicker (Task 1). */
  var dirtyTrackHandle = null;
  var entityPickerOnDirty = null;
  var saveBarHandle = null;

  /* Guard di navigazione (bug live #2): installato UNA VOLTA al caricamento
     dello script, non per-mount — 'unsaved' è uno stato HirisState globale,
     valido a prescindere da quale route lo abbia impostato. Deve girare
     PRIMA che main.js registri il proprio listener 'hashchange' (main.js
     carica per ultimo e si aggancia solo a DOMContentLoaded), così il
     guard intercetta la navigazione prima che il router rimonti la pagina. */
  HirisEditorKit.dirty.guard(function() { return !!HirisState.get('unsaved'); });

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

    /* Token counter (logs.js) — wired qui direttamente al momento della
       creazione dei campi, invece che in un rewire differito dopo il mount:
       ogni populateIstruzioni() crea nodi nuovi, quindi il binding è sempre
       fresco (nessun rischio di nodo detached). Vincitore SP-4 Fase B Task 2
       (copia editor; l'originale in logs.js era già stato rimosso). */
    if (typeof updateTokenCounter === 'function') {
      var fst = document.getElementById('f-strategic');
      if (fst) fst.oninput = updateTokenCounter;
      var fp = document.getElementById('f-prompt');
      if (fp) fp.oninput = updateTokenCounter;
    }
  }

  /* Task 4 (Slice 5): rimossa la riga "confirm-free" (era legata al tipo
     agente autonomo/schedulato, ritirato con Task 1-3 — ogni persona è
     chat). max-turns-row era nascosta di default e mostrata solo per
     type==='chat'; ora è sempre visibile (nessun altro tipo esiste). */
  function populateModello() {
    var body = document.getElementById('sc-body-modello');
    body.innerHTML = '<div id="model-select-root"></div>' +
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

    /* SP-4 Fase B Task 3: il <select> modello (prima markup statico +
       api.js.loadModels()) è ora HirisEditorKit.modelSelect() — stessi id
       (f-model / model-hint) per non toccare i lettori esterni
       (chatbot-form.js openAgent/buildPayload), ma la fetch api/models è
       condivisa/cachata nel kit invece che riscaricata a ogni mount. */
    HirisEditorKit.modelSelect(document.getElementById('model-select-root'), {
      id: 'f-model',
      hintId: 'model-hint',
      label: 'Modello',
      value: 'auto',
    });
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
        '<div id="tool-checks-root"></div></div>' +
      '<div class="field-group"><div class="fg-label">Entità accessibili</div>' +
        '<div id="entity-picker-root"></div></div>' +
      '<div id="f-actions-section" class="field-group" style="display:none">' +
        '<div class="fg-label">Azioni permesse</div>' +
        '<div id="action-checks-root"></div></div>';

    /* Chip entità: non sono <input>, quindi dirty.track (MutationObserver su
       input/select/textarea) non le vedrebbe mai cambiare — l'onChange del
       picker va agganciato esplicitamente a markDirty (nota del Task 3). */
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
      onChange: function() { if (entityPickerOnDirty) entityPickerOnDirty(); },
    });
    window.HirisAgentEntityPicker = entityPickerInstance;

    /* SP-4 Fase B Task 3: buildToolChecks/buildActionChecks/getSelectedTools/
       getSelectedActions (ex permessi.js) assorbiti in
       HirisEditorKit.checkGroup — istanza-scoped, non più #tool-checks/
       #action-checks globali. Esposte su window per chatbot-form.js
       (openAgent/buildPayload), stesso pattern dell'entity-picker sopra.
       La regola "call_ha_service abilita la sezione Azioni" resta qui
       (business logic dell'editor, non generica del kit): il kit si limita
       a rendere i checkbox, il caller decide cosa farne al change. */
    var actionsSection = document.getElementById('f-actions-section');
    var actionCheckGroup = HirisEditorKit.checkGroup(document.getElementById('action-checks-root'), {
      items: ACTIONS,
      selected: [],
      idPrefix: 'action',
    });
    var toolsRoot = document.getElementById('tool-checks-root');
    var toolCheckGroup = HirisEditorKit.checkGroup(toolsRoot, {
      items: TOOLS,
      selected: [],
      idPrefix: 'tool',
    });
    function syncActionsVisibility() {
      actionsSection.style.display = toolCheckGroup.getSelected().indexOf('call_ha_service') >= 0 ? '' : 'none';
    }
    toolsRoot.addEventListener('change', syncActionsVisibility);
    syncActionsVisibility();

    window.HirisAgentActionChecks = actionCheckGroup;
    window.HirisAgentToolChecks = {
      getSelected: toolCheckGroup.getSelected,
      setSelected: function(vals) {
        toolCheckGroup.setSelected(vals);
        syncActionsVisibility();
      },
    };
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

  /* SP-4 Fase B Task 3: sticky actions ricostruita sul kit condiviso.
     Prima: un singolo querySelectorAll('.section-card input, select,
     textarea') FOTOGRAFAVA i controlli presenti al momento della chiamata —
     i checkbox tool/azioni e i chip entità, creati DOPO (dentro
     populatePermessi/openAgent), non erano mai agganciati a markDirty
     (bug live #1). Ora HirisEditorKit.dirty.track() osserva il sottoalbero
     con un MutationObserver: qualunque input/select/textarea aggiunto in
     seguito viene wired automaticamente. Per questo setupStickyActions gira
     PRIMA di populateIdentita/.../populatePermessi nel mount() qui sotto —
     il tracking è già attivo quando quei populate*() riempiono il DOM. */
  function setupStickyActions(agentId) {
    var outlet = document.getElementById('route-outlet');

    /* Reset esplicito: senza, uno stato 'unsaved' lasciato true da un mount
       precedente (es. l'utente ha confermato "esci senza salvare" sul
       guard) sopravviverebbe al remount e il guard richiederebbe conferma
       di nuovo alla prossima navigazione, anche a editor pulito. */
    HirisState.set('unsaved', false);

    function markDirty() { HirisState.set('unsaved', true); if (saveBarHandle) saveBarHandle.setDirty(true); }
    function markClean() { HirisState.set('unsaved', false); if (saveBarHandle) saveBarHandle.setDirty(false); }

    if (dirtyTrackHandle) { dirtyTrackHandle.stop(); dirtyTrackHandle = null; }
    dirtyTrackHandle = HirisEditorKit.dirty.track(outlet, markDirty);
    entityPickerOnDirty = markDirty;

    saveBarHandle = HirisEditorKit.saveBar(outlet, {
      onSave: function() {
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
      },
      onCancel: function() {
        if (HirisState.get('unsaved') && !confirm('Annullare le modifiche non salvate?')) return;
        window.location.hash = '#/chatbots';
      },
      onDelete: agentId ? function() {
        if (typeof deleteAgent === 'function') {
          try { deleteAgent(); } catch(e) { console.error('deleteAgent threw:', e); alert('Delete error: ' + (e.message || e)); }
        } else {
          console.warn('deleteAgent not defined');
          alert('window.deleteAgent non definito. Hard reload Ctrl+Shift+R per scaricare cache stale.');
        }
      } : null,
      onTestRun: function() {
        if (typeof runAgent === 'function') {
          try { runAgent(); } catch(e) { console.error('runAgent threw:', e); alert('TestRun error: ' + (e.message || e)); }
        } else {
          console.warn('runAgent not defined');
          alert('window.runAgent non definito. Hard reload Ctrl+Shift+R per scaricare cache stale.');
        }
      },
    });
    saveBarHandle.setDirty(false);
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
    if (window.HirisAgentToolChecks) window.HirisAgentToolChecks.setSelected([]);
    if (window.HirisAgentActionChecks) window.HirisAgentActionChecks.setSelected([]);

    var setVal = function(id, v) { var el = document.getElementById(id); if (el) el.value = v; };
    var setChk = function(id, v) { var el = document.getElementById(id); if (el) el.checked = v; };

    setVal('f-template', '');
    setVal('f-name', '');
    setVal('f-prompt', '');
    setVal('f-strategic', '');
    setChk('f-enabled', true);
    HirisEditorKit.setModelValue(document.getElementById('f-model'), 'auto');
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
    console.log('[HirisChatbotEditor] mount agentId=' + agentId);
    var outlet = document.getElementById('route-outlet');
    if (!outlet) {
      console.error('route-outlet element missing — config.html broken');
      return;
    }

    /* Use Promise chain so all steps fall into the .catch with named errors.
       SP-4 Fase B Task 2: rimosso lo step di caricamento a runtime — i moduli
       prima "legacy" (templates/permessi/log-row/logs/usage/proposals/
       chatbot-form) sono ora <script src> statici in config.html, già
       disponibili qui senza attendere un caricamento di rete a metà mount. */
    Promise.resolve().then(function() {
      step('clear outlet', function() { outlet.innerHTML = ''; });
      step('clone template', function() {
        var tpl = document.getElementById('tpl-agent-editor');
        if (!tpl) throw new Error('tpl-agent-editor not in config.html — BROKEN BUILD');
        outlet.appendChild(tpl.content.cloneNode(true));
      });
      /* SP-4 Fase B Task 3: setupStickyActions gira SUBITO dopo il clone,
         PRIMA di ogni populate*() — installa HirisEditorKit.dirty.track()
         su un outlet ancora vuoto, così il MutationObserver è già attivo
         quando populateModello/populatePermessi/ecc. riempiono il DOM (i
         loro input/select/textarea vengono wired dall'observer stesso,
         nessuna scansione a posteriori necessaria — era questo lo shape
         del bug live #1: uno snapshot preso troppo presto). */
      step('setupStickyActions', function() { setupStickyActions(agentId); });
      step('populateIdentita', populateIdentita);
      step('populateIstruzioni', populateIstruzioni);
      step('populateModello', populateModello);
      step('populatePermessi', populatePermessi);
      step('populateStato', populateStato);
      step('populateLog', populateLog);
      step('populateRun', populateRun);
      step('populateConsumi', populateConsumi);
      step('setupAnchorNav', setupAnchorNav);
      step('populateTemplateSelector', function() {
        if (typeof populateTemplateSelector === 'function') populateTemplateSelector();
      });

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
              'Step: <strong>' + stepName + '</strong>' +
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
