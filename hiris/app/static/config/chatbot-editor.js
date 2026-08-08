/* HIRIS · Designer · Chatbot editor (SP-4 Fase B Task 4)
   Editor unico per l'entità Chatbot, costruito sul kit condiviso
   (config/editor-kit.js, Task 3) e sul componente entità istanziabile
   (config/entity-picker.js, Task 1). Assorbe integralmente
   chatbot-form.js (rimosso, DELETED da questo task): openAgent/
   buildPayload/loadChatbots erano l'ultimo file separato del vecchio
   editor -- ora questo file è l'UNICO owner del payload e del ciclo di
   vita del form. Chiude anche la doppia fonte di verità che restava:
   `window.currentId` (chatbot-form.js) vs `HirisState.get('activeChatbotId')`
   (scritto dal router in main.js) -- resta solo la seconda, letta
   ovunque questo file debba sapere quale Chatbot è in editing
   (window.saveAgent/runAgent/deleteAgent sotto).

   Sezioni -- fonte unica: l'array SECTIONS qui sotto genera SIA le
   section-card in pagina SIA il rail anchor-nav (buildSections()). Prima
   (grounding A3) lo stesso elenco di 8 voci era scritto 3 volte:
   <template id="tpl-agent-editor"> (section-card statiche), l'<aside>
   anchor-nav (link statici) e i letterali `sc-body-*` sparsi nei
   populate*() -- cambiare/aggiungere una sezione richiedeva toccare 3
   posti in sync. Ora `config.html` tiene solo la cornice (editor-grid +
   sticky-actions-wrap + <aside> vuoto con la sola label "Indice"): tutto
   il resto nasce da questo array.

   knowledge_access (Task 4, nuovo): campo finora solo-API -- mai esposto
   in UI, mai inviato dal payload (buildPayload() sotto lo ignorava del
   tutto). Sezione Knowledge: un checkbox allow_sensitive + un gruppo di
   checkbox "kinds" (fact/preference/obligation/expense/note, vedi
   config/templates.js KNOWLEDGE_KINDS) dietro un master-switch "Tutte le
   categorie" (kinds:"all" quando spuntato, altrimenti l'elenco dei kind
   selezionati -- kinds:[] è una scelta valida e significa "nessun
   accesso al second brain", vedi brain/knowledge_store.py). Validato
   lato backend in handlers_chatbots.py::_validate_chatbot_payload (prima:
   setattr grezzo, accettava qualunque tipo JSON).

   Autonomia (Task 4, nuova sezione): riepilogo READ-ONLY del tier
   semaforo delle entità in scope + il setting require_confirmation
   (spostato qui da Abilitazione: è un consenso sull'autonomia del
   Chatbot, non uno stato on/off del Chatbot stesso). La pagina Gateway
   (#/gateway) resta l'UNICA fonte per CONFIGURARE i tier -- questa
   sezione non scrive mai una policy, si limita a leggerla e a contare.
   Nessuna fusione del semaforo (vincolo esplicito del piano).

   Review finding (Important, chiuso in questo stesso task): il riepilogo
   ricalcolava il tier lato client, mirror di effective_tier in
   handlers_gateway_policy.py, MA senza la denylist DANGEROUS_DOMAINS che
   il gate del semaforo applica sempre sopra al tier (lock/
   alarm_control_panel/cover/siren/garage_door -- "difesa in profondità";
   quel gate era security/semaphore.py::gate_action quando questo finding fu
   chiuso, è inline in watcher/executor.py::execute da quando gate_action è
   uscita, review finale fetta E2 I-1). Risultato: bastava mettere `cover.*`
   in scope (uno dei SCOPE_PILLS qui sotto) e impostarlo verde in #/gateway
   perché il riepilogo mostrasse "verde" su un dominio che il backend nega
   SEMPRE. Display-only (nessun buco di sicurezza, l'enforcement non era
   toccato) ma disinformava l'utente proprio sui domini più delicati. Fix:
   niente più calcolo lato client -- renderAutonomiaSummary() chiama POST
   api/gateway/autonomy-summary, che nel backend usa security/semaphore.py::
   summarize_autonomy (la STESSA funzione che il gate del semaforo usa per
   una vera decisione) e ritorna i conteggi già corretti, incluso un bucket
   "dangerous" separato dai tier. Un'unica implementazione: un domino
   aggiunto a DANGEROUS_DOMAINS non può più disallineare silenziosamente la
   UI. Vedi tests/js/chatbot-editor.test.mjs ("cover.* pericoloso non è mai
   verde") e tests/test_gateway_policy.py. */
(function() {

  /* ── sezione: fonte unica per section-card + anchor-nav ─────────────── */
  var SECTIONS = [
    { id: 'identita',   title: 'Identità',        desc: 'Nome della persona.' },
    { id: 'istruzioni', title: 'Istruzioni',      desc: 'Cosa il Chatbot sa della casa e cosa deve fare.' },
    { id: 'modello',    title: 'Modello AI',      desc: 'Quale modello usa, budget token, livello reasoning.' },
    { id: 'scope',      title: 'Scope',           desc: 'Quali entità Home Assistant il Chatbot può leggere o usare.' },
    { id: 'permessi',   title: 'Permessi',        desc: 'Quali tool e quali azioni HA può eseguire.' },
    { id: 'knowledge',  title: 'Knowledge',       desc: 'Cosa può richiamare dal second brain di casa.' },
    { id: 'autonomia',  title: 'Autonomia',       desc: 'Cosa può fare in autonomia: tier del semaforo e conferma.' },
    { id: 'stato',      title: 'Abilitazione',    desc: 'Quando il Chatbot è abilitato.' },
    { id: 'log',        title: 'Log esecuzioni',  desc: 'Ultimi 20 run. Click su una riga per il dettaglio.' },
    { id: 'run',        title: 'Test Run',        desc: 'Ultimo Test Run lanciato manualmente. Non esegue azioni reali.' },
    { id: 'consumi',    title: 'Consumi Chatbot', desc: 'Conteggio richieste, token e costo stimato.' }
  ];

  /* ── stato di modulo (un solo editor Chatbot montato alla volta) ─────── */
  var chatbots = [];                    /* cache locale + mirror window.chatbots (usage.js/log-row.js la leggono bare) + HirisState('chatbots') */
  var entityPickerInstance = null;      /* config/entity-picker.js -- sezione Scope */
  var toolCheckGroup = null;            /* HirisEditorKit.checkGroup -- sezione Permessi (tool) */
  var actionCheckGroup = null;          /* HirisEditorKit.checkGroup -- sezione Permessi (azioni, visibili solo con call_ha_service tra i tool) */
  var syncActionsVisibilityRef = null;
  var knowledgeKindsGroup = null;       /* HirisEditorKit.checkGroup -- sezione Knowledge (kinds) */
  var syncKnowledgeKindsVisibilityRef = null;
  var markDirtyRef = null;              /* letto dall'onChange dell'entity-picker (i chip non sono <input>, dirty.track da solo non li vede) */
  var saveBarHandle = null;             /* HirisEditorKit.saveBar() */

  /* Guard di navigazione (bug live #2, chiuso nel Task 3): NON più
     installato qui dal Task 6 in poi -- era un accoppiamento strutturale
     fragile (funzionava solo perché config.html carica SEMPRE questo file,
     non perché ogni route fosse garantita protetta). Hoistato in main.js
     (installato UNA VOLTA a livello top del suo IIFE, prima che
     DOMContentLoaded/HirisRouter.start() registrino i propri listener):
     main.js è l'ultimo script caricato ed è comune a OGNI route, quindi la
     garanzia è "per costruzione" invece che "perché questo file capita di
     essere incluso". 'unsaved' resta la chiave HirisState GLOBALE (vedi
     C9 nel grounding) -- un solo guard() per l'intera pagina. */

  /* ───────────────────────── data layer (ex chatbot-form.js) ───────────────────────── */

  function loadChatbots() {
    return fetch('api/chatbots').then(function(r) { return r.ok ? r.json() : []; }).then(function(d) {
      chatbots = Array.isArray(d) ? d : (d.agents || []);
      HirisState.set('chatbots', chatbots);
      window.chatbots = chatbots;   /* letto bare da usage.js/log-row.js (globale non-strict, ex chatbot-form.js) */
      return chatbots;
    }).catch(function() { return chatbots; });
  }

  function highlightOutput(text) {
    return text
      .replace(/("error")/g, '<span style="color:#ff7b72">$1</span>')
      .replace(/("[\w_]+")\s*:/g, '<span style="color:#79c0ff">$1</span>:')
      .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span style="color:#a5d6a7">$1</span>');
  }

  function openAgent(a) {
    var _fn = document.getElementById('f-name'); if (_fn) _fn.value = a.name;
    document.getElementById('f-prompt').value = a.system_prompt || '';
    document.getElementById('f-strategic').value = a.strategic_context || '';
    if (entityPickerInstance) entityPickerInstance.setValue(a.allowed_entities || []);
    document.getElementById('f-enabled').checked = a.enabled;
    HirisEditorKit.setModelValue(document.getElementById('f-model'), a.model || 'auto');
    document.getElementById('f-max-tokens').value = a.max_tokens || 4096;
    document.getElementById('f-restrict').checked = !!a.restrict_to_home;
    document.getElementById('f-require-confirmation').checked = !!a.require_confirmation;
    document.getElementById('f-max-chat-turns').value = a.max_chat_turns || 0;
    document.getElementById('f-response-mode').value = a.response_mode || 'auto';
    document.getElementById('f-thinking-budget').value = String(a.thinking_budget || 0);
    if (actionCheckGroup) actionCheckGroup.setSelected(a.allowed_services || []);
    /* tool DOPO azioni: syncActionsVisibility dipende da call_ha_service
       tra i tool selezionati -- stesso ordine di dipendenza di sempre. */
    if (toolCheckGroup) toolCheckGroup.setSelected(a.allowed_tools || []);
    if (syncActionsVisibilityRef) syncActionsVisibilityRef();

    var ka = (a.knowledge_access && typeof a.knowledge_access === 'object') ? a.knowledge_access : {};
    var sensitiveChk = document.getElementById('f-knowledge-sensitive');
    if (sensitiveChk) sensitiveChk.checked = !!ka.allow_sensitive;
    var allKindsChk = document.getElementById('f-knowledge-all-kinds');
    var isAllKinds = ka.kinds == null || ka.kinds === 'all';
    if (allKindsChk) allKindsChk.checked = isAllKinds;
    if (knowledgeKindsGroup) knowledgeKindsGroup.setSelected(isAllKinds ? [] : (Array.isArray(ka.kinds) ? ka.kinds : []));
    if (syncKnowledgeKindsVisibilityRef) syncKnowledgeKindsVisibilityRef();

    var btnDel = document.getElementById('btn-delete');
    if (btnDel) btnDel.style.display = a.is_default ? 'none' : '';
    var ro = document.getElementById('run-output');
    if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }

    renderExecutionLog(a);
    loadAgentUsage(a.id);
    updateAgentUsageToggleBtn(a);
    updateTokenCounter();
    loadContextPreview(a.id);
    /* setValue() sull'entity-picker sopra NON emette onChange (è il
       caricamento, non una modifica utente) -- il riepilogo Autonomia va
       quindi aggiornato esplicitamente qui con lo scope appena caricato. */
    renderAutonomiaSummary();
  }

  function buildPayload() {
    return {
      name: document.getElementById('f-name').value,
      system_prompt: document.getElementById('f-prompt').value,
      strategic_context: document.getElementById('f-strategic').value,
      allowed_tools: toolCheckGroup ? toolCheckGroup.getSelected() : [],
      allowed_entities: entityPickerInstance ? entityPickerInstance.getValue() : [],
      allowed_services: actionCheckGroup ? actionCheckGroup.getSelected() : [],
      model: document.getElementById('f-model').value,
      max_tokens: parseInt(document.getElementById('f-max-tokens').value) || 4096,
      restrict_to_home: document.getElementById('f-restrict').checked,
      require_confirmation: document.getElementById('f-require-confirmation').checked,
      enabled: document.getElementById('f-enabled').checked,
      max_chat_turns: parseInt(document.getElementById('f-max-chat-turns').value) || 0,
      response_mode: document.getElementById('f-response-mode').value,
      thinking_budget: parseInt(document.getElementById('f-thinking-budget').value) || 0,
      /* Task 4: il dial knowledge non è più solo-API -- prima buildPayload()
         non includeva affatto questa chiave. */
      knowledge_access: {
        allow_sensitive: !!document.getElementById('f-knowledge-sensitive').checked,
        kinds: document.getElementById('f-knowledge-all-kinds').checked
          ? 'all'
          : (knowledgeKindsGroup ? knowledgeKindsGroup.getSelected() : []),
      },
    };
  }

  /* ───────────────────────── populate*() per sezione ───────────────────────── */

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

    /* Token counter (logs.js) -- wired qui direttamente al momento della
       creazione dei campi (ogni populateIstruzioni() crea nodi nuovi, il
       binding è sempre fresco: nessun rischio di nodo detached). */
    if (typeof updateTokenCounter === 'function') {
      var fst = document.getElementById('f-strategic');
      if (fst) fst.oninput = updateTokenCounter;
      var fp = document.getElementById('f-prompt');
      if (fp) fp.oninput = updateTokenCounter;
    }
  }

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

    /* HirisEditorKit.modelSelect() -- stessi id (f-model / model-hint) dei
       lettori (openAgent/buildPayload qui sopra), ma la fetch api/models è
       condivisa/cachata nel kit invece che riscaricata a ogni mount. */
    HirisEditorKit.modelSelect(document.getElementById('model-select-root'), {
      id: 'f-model',
      hintId: 'model-hint',
      label: 'Modello',
      value: 'auto',
    });
  }

  var SCOPE_PILLS = [
    { label: '💡 luci', pattern: 'light.*' },
    { label: '🔌 switch', pattern: 'switch.*' },
    { label: '📊 sensori', pattern: 'sensor.*' },
    { label: '🌡️ clima', pattern: 'climate.*' },
    { label: '🪟 tapparelle', pattern: 'cover.*' },
    { label: '🚰 valvole', pattern: 'valve.*' },
    { label: '⚡ binari', pattern: 'binary_sensor.*' },
    { label: '🧑 persone', pattern: 'person.*' },
  ];

  function populateScope() {
    /* Istanza precedente (mount precedente) non ancora distrutta -> stacca
       il suo listener documento prima di buttare via il DOM sotto di lei. */
    if (entityPickerInstance) {
      entityPickerInstance.destroy();
      entityPickerInstance = null;
      window.HirisAgentEntityPicker = null;
    }

    document.getElementById('sc-body-scope').innerHTML =
      '<div class="field-group"><div class="fg-label">Entità accessibili</div>' +
        '<div id="entity-picker-root"></div></div>';

    /* Chip entità: non sono <input>, quindi dirty.track (MutationObserver
       su input/select/textarea) non le vedrebbe mai cambiare -- l'onChange
       del picker va agganciato esplicitamente a markDirty. Aggiorna anche
       il riepilogo Autonomia: il tier è funzione dello scope. */
    entityPickerInstance = HirisEntityPicker.create(document.getElementById('entity-picker-root'), {
      placeholder: 'Cerca entità…',
      pills: SCOPE_PILLS,
      onChange: function() {
        if (markDirtyRef) markDirtyRef();
        renderAutonomiaSummary();
      },
    });
    window.HirisAgentEntityPicker = entityPickerInstance;   /* mirror esposto per debug/test -- nessun altro file lo consuma più */
  }

  function populatePermessi() {
    document.getElementById('sc-body-permessi').innerHTML =
      '<div class="field-group"><div class="fg-label">Strumenti</div>' +
        '<div id="tool-checks-root"></div></div>' +
      '<div id="f-actions-section" class="field-group" style="display:none">' +
        '<div class="fg-label">Azioni permesse</div>' +
        '<div id="action-checks-root"></div></div>';

    var actionsSection = document.getElementById('f-actions-section');
    actionCheckGroup = HirisEditorKit.checkGroup(document.getElementById('action-checks-root'), {
      items: ACTIONS,
      selected: [],
      idPrefix: 'action',
    });
    var toolsRoot = document.getElementById('tool-checks-root');
    toolCheckGroup = HirisEditorKit.checkGroup(toolsRoot, {
      items: TOOLS,
      selected: [],
      idPrefix: 'tool',
    });
    function syncActionsVisibility() {
      actionsSection.style.display = toolCheckGroup.getSelected().indexOf('call_ha_service') >= 0 ? '' : 'none';
    }
    syncActionsVisibilityRef = syncActionsVisibility;
    toolsRoot.addEventListener('change', syncActionsVisibility);
    syncActionsVisibility();
  }

  function populateKnowledge() {
    document.getElementById('sc-body-knowledge').innerHTML =
      '<label class="checkbox-row"><input type="checkbox" id="f-knowledge-sensitive"> Consenti dati sensibili</label>' +
      '<p class="field-hint">Il Chatbot può leggere anche le voci del second brain marcate come sensibili (es. importi, documenti riservati).</p>' +
      '<label class="checkbox-row"><input type="checkbox" id="f-knowledge-all-kinds" checked> Tutte le categorie</label>' +
      '<div id="knowledge-kinds-root" style="display:none"></div>' +
      '<p class="field-hint">Disattiva "Tutte le categorie" per scegliere quali tipi di informazione il Chatbot può richiamare dal second brain.</p>';

    knowledgeKindsGroup = HirisEditorKit.checkGroup(document.getElementById('knowledge-kinds-root'), {
      items: KNOWLEDGE_KINDS,
      selected: [],
      idPrefix: 'kind',
    });
    var allChk = document.getElementById('f-knowledge-all-kinds');
    var kindsRoot = document.getElementById('knowledge-kinds-root');
    function syncKnowledgeKindsVisibility() {
      kindsRoot.style.display = allChk.checked ? 'none' : '';
    }
    syncKnowledgeKindsVisibilityRef = syncKnowledgeKindsVisibility;
    allChk.addEventListener('change', syncKnowledgeKindsVisibility);
    syncKnowledgeKindsVisibility();
  }

  /* Riepilogo READ-ONLY: chiede al backend (POST api/gateway/autonomy-
     summary) i conteggi tier delle entità/pattern in scope. Il backend usa
     security/semaphore.py::summarize_autonomy -- la stessa funzione che il
     gate del semaforo usa per una vera decisione (watcher/executor.py::
     execute, denylist DANGEROUS_DOMAINS inclusa -- non più
     security/semaphore.py::gate_action, uscita con la review finale fetta
     E2, I-1) -- quindi qui non si ricalcola più nulla: nessun rischio che
     questa vista disallinei dal reale enforcement (vedi il commento in
     testa al file). Non scrive mai nulla: la pagina #/gateway resta
     l'unica fonte per configurare i tier. */
  function renderAutonomiaSummary() {
    var el = document.getElementById('autonomia-summary');
    if (!el) return;
    var entities = entityPickerInstance ? entityPickerInstance.getValue() : [];
    if (!entities.length) {
      el.textContent = 'Nessuna entità in scope: questo Chatbot non ha azioni da autorizzare.';
      return;
    }
    el.textContent = 'Calcolo tier in corso…';
    fetch('api/gateway/autonomy-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify({ entities: entities }),
    })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        var counts = data && data.counts;
        if (!counts) { el.textContent = 'Impossibile leggere la policy Gateway.'; return; }
        var text = '🟢 ' + (counts.green || 0) + ' verde · 🟡 ' + (counts.yellow || 0) + ' giallo · 🔴 ' +
          (counts.red || 0) + ' rosso · ⚪ ' + (counts.off || 0) + ' spenta';
        if (counts.dangerous) {
          /* Mai un tier: dominio nella denylist DANGEROUS_DOMAINS -- il
             backend nega SEMPRE, qualunque tier sia configurato in
             #/gateway. Etichetta esplicita, non conteggiato come verde/
             giallo/rosso/spenta, così non può leggersi come "permesso". */
          text += ' · 🔒 ' + counts.dangerous + ' sempre bloccato (dominio pericoloso)';
        }
        text += ' (su ' + entities.length + ' voci di scope).';
        el.textContent = text;
      })
      .catch(function() { el.textContent = 'Impossibile leggere la policy Gateway.'; });
  }

  function populateAutonomia() {
    document.getElementById('sc-body-autonomia').innerHTML =
      '<div class="field-group"><div class="fg-label">Tier semaforo (riepilogo)</div>' +
        '<p id="autonomia-summary" class="field-hint">Caricamento…</p>' +
        '<p class="field-hint">Il tier di ogni entità/dominio si configura nella pagina ' +
          '<a href="#/gateway">Accessi Gateway</a> — questa sezione lo riepiloga soltanto, non lo modifica.</p></div>' +
      '<div class="field-group"><div class="fg-label">Conferma</div>' +
        '<label class="checkbox-row"><input type="checkbox" id="f-require-confirmation"> Richiedi conferma prima delle azioni</label>' +
        '<p class="field-hint">Istruzione al modello di chiedere un "sì/ok" prima di agire. Oggi la ' +
          'chat offre solo strumenti di conoscenza (cerca, guarda, ricorda, richiama): nessuno agisce ' +
          'sulla casa, quindi questa opzione resta configurabile ma non ha al momento alcun effetto ' +
          'osservabile.</p></div>';
    renderAutonomiaSummary();
  }

  /* Task 4: solo lo stato on/off resta in Abilitazione -- require_confirmation
     è ora nella sezione Autonomia (è un consenso sull'autonomia, non uno
     stato del Chatbot). */
  function populateStato() {
    document.getElementById('sc-body-stato').innerHTML =
      '<label class="checkbox-row"><input type="checkbox" id="f-enabled"> Chatbot abilitato</label>' +
      '<p class="field-hint">Controlla solo lo stato dell\'entità switch Home Assistant di questo Chatbot; puoi comunque verificarlo con Test Run indipendentemente da questo interruttore.</p>';
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
          '<button type="button" class="btn btn-sm btn-danger" id="u-ag-toggle-btn">⊘ Blocca Chatbot</button>' +
        '</div>' +
      '</div>';
  }

  /* Genera le section-card + i link anchor-nav dall'array SECTIONS (fonte
     unica, vedi commento in testa al file). Le section-card sono inserite
     PRIMA di #sticky-actions-wrap (che il template porta già con sé),
     l'ordine dentro .editor-content resta identico a quello statico di
     prima. textContent/createElement ovunque -- nessun rischio XSS anche
     se in futuro SECTIONS venisse esteso con dati non hardcoded. */
  function buildSections(content, anchorNav) {
    var stickyWrap = content.querySelector('#sticky-actions-wrap');
    SECTIONS.forEach(function(s, idx) {
      var numStr = String(idx + 1);
      if (numStr.length < 2) numStr = '0' + numStr;

      var section = document.createElement('section');
      section.className = 'section-card';
      section.id = 'sec-' + s.id;

      var header = document.createElement('div');
      header.className = 'sc-header';
      var num = document.createElement('span');
      num.className = 'sc-num';
      num.textContent = numStr;
      var title = document.createElement('h2');
      title.className = 'sc-title';
      title.textContent = s.title;
      header.appendChild(num);
      header.appendChild(title);

      var desc = document.createElement('p');
      desc.className = 'sc-desc';
      desc.textContent = s.desc;

      var scBody = document.createElement('div');
      scBody.className = 'sc-body';
      scBody.id = 'sc-body-' + s.id;

      section.appendChild(header);
      section.appendChild(desc);
      section.appendChild(scBody);
      if (stickyWrap) content.insertBefore(section, stickyWrap);
      else content.appendChild(section);

      var link = document.createElement('a');
      link.className = 'anchor-link';
      link.setAttribute('href', '#sec-' + s.id);
      var linkNum = document.createElement('span');
      linkNum.textContent = numStr;
      var linkTitle = document.createElement('span');
      linkTitle.textContent = s.title;
      link.appendChild(linkNum);
      link.appendChild(linkTitle);
      anchorNav.appendChild(link);
    });
  }

  function setupAnchorNav() {
    var sections = document.querySelectorAll('.section-card');
    var links = {};
    document.querySelectorAll('.anchor-link[href^="#sec-"]').forEach(function(l) {
      links[l.getAttribute('href').slice(1)] = l;
      /* Intercetta click anchor per evitare cambio di hash: un <a href="#sec-X">
         nativo cambierebbe l'URL hash -> router fires hashchange -> nessuna
         route combacia -> il service worker HA Ingress tenta il fetch del
         nuovo URL e fallisce, più history pollution e remount loop quando
         l'utente torna su #/chatbots/<id>. */
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

  /* Sticky actions sul kit condiviso (Task 3): HirisEditorKit.dirty.track()
     osserva il sottoalbero di #route-outlet con un MutationObserver -- ogni
     input/select/textarea aggiunto DOPO il mount (checkbox tool/azioni/
     knowledge, creati dai populate*() sotto) viene wired automaticamente.
     Per questo setupStickyActions gira PRIMA di ogni populate*() nel
     mount() sotto -- il tracking è già attivo quando i populate*()
     riempiono il DOM. */
  function setupStickyActions(agentId) {
    var outlet = document.getElementById('route-outlet');

    /* Reset esplicito: senza, uno stato 'unsaved' lasciato true da un mount
       precedente (es. l'utente ha confermato "esci senza salvare" sul
       guard) sopravviverebbe al remount e il guard richiederebbe conferma
       di nuovo alla prossima navigazione, anche a editor pulito. */
    HirisState.set('unsaved', false);

    function markDirty() { HirisState.set('unsaved', true); if (saveBarHandle) saveBarHandle.setDirty(true); }
    function markClean() { HirisState.set('unsaved', false); if (saveBarHandle) saveBarHandle.setDirty(false); }

    /* HirisEditorKit.dirty.track() è ora un singleton a livello di kit
       (review finale pre-1.0, finding C1): ferma da sé qualunque tracker
       precedente, anche se installato da un editor di TIPO diverso --
       niente più handle locale da tenere/fermare qui. */
    HirisEditorKit.dirty.track(outlet, markDirty);
    markDirtyRef = markDirty;

    saveBarHandle = HirisEditorKit.saveBar(outlet, {
      onSave: function() {
        try {
          var p = saveAgent();
          if (p && p.then) p.then(function() { markClean(); }).catch(function(err) { console.error('save rejected:', err); });
          else markClean();
        } catch(e) { console.error('saveAgent threw:', e); alert('Save error: ' + (e.message || e)); }
      },
      onCancel: function() {
        if (HirisState.get('unsaved') && !confirm('Annullare le modifiche non salvate?')) return;
        /* Pulisce 'unsaved' PRIMA di cambiare hash (finding I2): l'utente
           ha già confermato lo scarto qui sopra -- senza, il guard
           installato in main.js vede lo stesso 'unsaved' ancora true sul
           hashchange che questa riga genera e chiede conferma UNA SECONDA
           volta, a vuoto, per una scelta già fatta. */
        HirisState.set('unsaved', false);
        window.location.hash = '#/chatbots';
      },
      onDelete: agentId ? function() {
        try { deleteAgent(); } catch(e) { console.error('deleteAgent threw:', e); alert('Delete error: ' + (e.message || e)); }
      } : null,
      onTestRun: function() {
        try { runAgent(); } catch(e) { console.error('runAgent threw:', e); alert('TestRun error: ' + (e.message || e)); }
      },
    });
    saveBarHandle.setDirty(false);
  }

  /* Init form per "Nuovo Chatbot" (#/chatbots/new). */
  function initNewAgent() {
    if (entityPickerInstance) entityPickerInstance.setValue([]);
    if (toolCheckGroup) toolCheckGroup.setSelected([]);
    if (actionCheckGroup) actionCheckGroup.setSelected([]);
    if (syncActionsVisibilityRef) syncActionsVisibilityRef();
    if (knowledgeKindsGroup) knowledgeKindsGroup.setSelected([]);

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
    setChk('f-knowledge-sensitive', false);
    setChk('f-knowledge-all-kinds', true);
    if (syncKnowledgeKindsVisibilityRef) syncKnowledgeKindsVisibilityRef();

    if (typeof updateTokenCounter === 'function') updateTokenCounter();

    var ctxWrap = document.getElementById('context-preview-wrap');
    if (ctxWrap) ctxWrap.style.display = 'none';
    var ro = document.getElementById('run-output');
    if (ro) { ro.style.display = 'none'; ro.textContent = ''; ro.className = ''; }

    renderAutonomiaSummary();
  }

  /* Save / Run / Delete globals -- chiamati da setupStickyActions sopra
     tramite i bottoni #btn-save/#btn-test-run/#btn-delete. Restano globali
     (window.X) senza bisogno di un typeof-guard: sono definiti qui, nello
     stesso file/IIFE che li consuma, non più su un file "legacy" separato
     che poteva non essere ancora caricato. */
  window.saveAgent = function() {
    var payload = buildPayload();
    var cid = HirisState.get('activeChatbotId');
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
      /* Refresh di HirisState.chatbots dopo create/update -- lo legge
         dashboard.js:273 per decidere fra empty-state e dashboard popolata. */
      return loadChatbots().then(function() {
        openAgent(a);
        /* Nuovo agente: naviga al suo dettaglio. HirisState.activeChatbotId
           lo scrive il router (main.js) alla hashchange, non questo file
           (contratto C9: un solo writer). */
        if (!cid && a.id) window.location.hash = '#/chatbots/' + encodeURIComponent(a.id);
        return a;
      });
    });
  };

  var _runInFlight = false;
  window.runAgent = function() {
    if (_runInFlight) {
      console.warn('runAgent già in flight — click ignorato');
      return Promise.resolve();
    }
    var cid = HirisState.get('activeChatbotId');
    if (!cid) {
      console.warn('runAgent: nessun agentId attivo');
      return Promise.resolve();
    }

    _runInFlight = true;

    var btn = document.getElementById('btn-test-run');
    var section = document.getElementById('sec-run');
    var sb = document.getElementById('sc-body-run');
    var out = document.getElementById('run-output');

    if (btn) {
      btn.classList.add('running');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>⏱ In esecuzione…';
    }

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

    if (section) {
      requestAnimationFrame(function() {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }

    /* Timeout frontend allineato al backend AGENT_RUN_TIMEOUT (fallback su
       OLLAMA_REQUEST_TIMEOUT * 1.2, default 600s con local_model.request_
       timeout=500) -- un agente locale lento non deve vedere la fetch
       abortita lato client prima che il backend abbia finito. */
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
        } else if (typeof esc === 'function') {
          out.className = '';
          out.innerHTML = '<div style="color:var(--ok);font-size:11px;font-weight:600;margin-bottom:6px;font-family:var(--font-sans)">✓ ESEGUITO</div>' + highlightOutput(esc(raw));
        } else {
          out.className = '';
          out.textContent = '✓ ' + raw;
        }
      }
      /* Refresh log + usage after run */
      fetch('api/chatbots/' + encodeURIComponent(cid)).then(function(r){return r.ok?r.json():null;}).then(function(a){
        if (a) renderExecutionLog(a);
        if (a) loadAgentUsage(cid);
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
    var cid = HirisState.get('activeChatbotId');
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
      /* L'entità appena eliminata non esiste più: pulisce lo stato prima
         che qualunque altro codice possa leggerlo (nessuna route verso
         #/chatbots lo fa da sola). Pulisce anche 'unsaved' (finding I2):
         senza, un editor lasciato dirty prima di premere Elimina fa
         chiedere al guard "Ci sono modifiche non salvate…" SUBITO DOPO
         l'eliminazione riuscita -- non ha più senso, l'entità non esiste
         più e non c'è nulla da salvare. */
      HirisState.set('activeChatbotId', null);
      HirisState.set('unsaved', false);
      return loadChatbots().then(function() {
        window.location.hash = '#/chatbots';
      });
    });
  };

  /* Resolve un agentId nell'oggetto completo via API -- openAgent() sopra
     si aspetta l'oggetto, non il solo id. */
  function resolveAgent(agentId) {
    var cached = HirisState.get('chatbots');
    if (cached && cached.length) {
      var hit = cached.filter(function(a) { return a.id === agentId; })[0];
      if (hit) return Promise.resolve(hit);
    }
    return fetch('api/chatbots')
      .then(function(r) { return r.ok ? r.json() : []; })
      .then(function(d) {
        var list = Array.isArray(d) ? d : (d.agents || []);
        chatbots = list;
        HirisState.set('chatbots', list);
        window.chatbots = list;
        var found = list.filter(function(a) { return a.id === agentId; })[0];
        if (!found) throw new Error('Chatbot non trovato: ' + agentId);
        return found;
      });
  }

  /* Wrap di uno step in try/catch con logging per nome. Ripropaga l'errore
     (con il nome dello step incollato) per farlo emergere nel .catch di
     mount() qui sotto, così si capisce quale step è crashato. */
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

    Promise.resolve().then(function() {
      step('clear outlet', function() { outlet.innerHTML = ''; });
      step('clone template', function() {
        var tpl = document.getElementById('tpl-agent-editor');
        if (!tpl) throw new Error('tpl-agent-editor not in config.html — BROKEN BUILD');
        outlet.appendChild(tpl.content.cloneNode(true));
      });
      /* setupStickyActions gira SUBITO dopo il clone, PRIMA di buildSections
         e di ogni populate*() -- installa HirisEditorKit.dirty.track() su un
         outlet ancora (quasi) vuoto, così il MutationObserver è già attivo
         quando le sezioni e i loro campi vengono creati sotto. */
      step('setupStickyActions', function() { setupStickyActions(agentId); });
      step('buildSections', function() {
        var content = outlet.querySelector('.editor-content');
        var anchorNav = outlet.querySelector('.anchor-nav');
        buildSections(content, anchorNav);
      });
      step('populateIdentita', populateIdentita);
      step('populateIstruzioni', populateIstruzioni);
      step('populateModello', populateModello);
      step('populateScope', populateScope);
      step('populatePermessi', populatePermessi);
      step('populateKnowledge', populateKnowledge);
      step('populateAutonomia', populateAutonomia);
      step('populateStato', populateStato);
      step('populateLog', populateLog);
      step('populateRun', populateRun);
      step('populateConsumi', populateConsumi);
      step('setupAnchorNav', setupAnchorNav);
      step('populateTemplateSelector', function() {
        if (typeof populateTemplateSelector === 'function') populateTemplateSelector();
      });

      if (agentId) {
        return resolveAgent(agentId).then(function(agentObj) {
          step('openAgent', function() { openAgent(agentObj); });
          /* Breadcrumb con nome agente invece di id bare (main.js l'aveva
             impostato al solo id prima del mount). */
          var hereEl = document.getElementById('chrome-here');
          if (hereEl && agentObj && agentObj.name) {
            hereEl.textContent = 'Chatbot / ' + agentObj.name;
          }
          /* Nasconde Elimina per gli agenti di default (HIRIS). */
          var btnDel = document.getElementById('btn-delete');
          if (btnDel && agentObj && agentObj.is_default) {
            btnDel.style.display = 'none';
          }
        });
      } else {
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

  /* loadChatbots/openAgent restano globali (letti bare da usage.js e
     log-row.js, ex chatbot-form.js -- vedi C9 nel grounding). buildPayload/
     highlightOutput non servono più fuori da questo file (window.saveAgent/
     runAgent qui sopra li chiamano come chiusure locali), quindi non sono
     più esposte su window: erano globali solo perché prima vivevano in un
     file diverso da chi le chiamava. */
  window.loadChatbots = loadChatbots;
  window.openAgent = openAgent;

  window.HirisChatbotEditor = { mount: mount };
})();
