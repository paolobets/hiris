/* HIRIS · Designer · creazione goal-first (SP-4 Fase B Task 6)
   Flusso unico di creazione, sostituto della vecchia scelta esplicita
   "Chatbot o Agentbot?" davanti a un form vuoto:
     1) Obiettivo — nome + missione in linguaggio naturale.
     2) Derivazione del tipo — euristica leggera e DETERMINISTICA (conteggio
        di pattern testuali), MAI un LLM: nessuna fetch verso un endpoint di
        ragionamento avviene in questo file, in nessun punto del flusso.
        La scelta resta SEMPRE esplicita e sovrascrivibile dall'utente,
        prima di continuare.
     3) Step guidati per tipo:
        - Chatbot → tool (allowlist) + scope (entità) + knowledge.
        - Agentbot → trigger (evento/pianificazione) + azione dichiarata +
          scope (le stesse entità di trigger/azione, non un campo separato:
          vedi spec "Agentbot → entità trigger + target azione").
     4) Crea via POST api/chatbots o api/agentbots, poi naviga sull'editor
        completo (#/chatbots/{id} o #/agentbots/{id}) come livello
        "Avanzate" — stessa entità, editabile a piena granularità.

   Linea rossa E.2 (docs/design/2026-07-28-spec-SP4-config-unificata.md) —
   enforcement STRUTTURALE, non un controllo aggiunto sopra:
     - buildAgentbotPayload() qui sotto non referenzia MAI la chiave
       "allowed_tools": non esiste alcun percorso in questo builder che
       possa introdurne una. Il payload Agentbot ha SEMPRE la stessa forma
       che watcher/agentbots.py::validate_agentbot accetta (name, enabled,
       severity, trigger, reasoning, action) — reasoning gira sempre con
       allowed_tools=[] lato runner (nessun tool esposto al modello), e
       l'azione è sempre quella DICHIARATA qui dall'utente, mai una scelta
       del ragionamento AI.
     - buildChatbotPayload() non include mai trigger/scheduling: il
       contratto Chatbot (tool liberi entro allowlist, nessun trigger
       autonomo) non ha nemmeno il vocabolario per rappresentarne uno.
     - Il wizard non produce mai un'unica entità con "tool liberi +
       trigger autonomi + attuazione": mappa l'obiettivo sull'entità
       GIUSTA (Chatbot O Agentbot), non fonde i due contratti — sono due
       builder separati, con due whitelist di campi separate, verso due
       endpoint separati. */
(function() {
  'use strict';

  /* ── derivazione tipo: euristica leggera, deterministica, NESSUN LLM ──
     Conta quanti pattern "agisce/segnala da solo" (Agentbot) e quanti
     "risponde quando lo chiami" (Chatbot) compaiono nel testo. La
     differenza dei conteggi decide: margine ≥2 → suggerimento "strong"
     (pre-selezionato); margine 1 → "weak" (mostrato ma NON pre-selezionato,
     copy che segnala l'incertezza); pareggio (incluso 0-0) → "none",
     presentazione neutra, nessuna preselezione — onestà quando il segnale
     è debole, invece di indovinare con sicurezza. */

  var AGENTBOT_SIGNALS = [
    { re: /\bavvisami\b/,                          label: 'avvisami' },
    { re: /\bavvisa(?:mi|re)?\b/,                  label: 'avvisa' },
    { re: /\ballarme\b/,                           label: 'allarme' },
    { re: /\ballert[ao]\b/,                        label: 'allerta' },
    { re: /\bnotificami\b/,                        label: 'notificami' },
    { re: /\bsegnalami\b/,                         label: 'segnalami' },
    { re: /\bogni\s+(?:giorno|notte|ora|volta|mattina|sera)\b/, label: 'ogni…' },
    { re: /\balle\s?\d{1,2}([:.]\d{2})?\b/,        label: 'alle <ora>' },
    { re: /\bresta(?:no)?\s+apert[oai]/,           label: 'resta aperto' },
    { re: /\brimane(?:no)?\s+apert[oai]/,          label: 'rimane aperto' },
    { re: /\bsuper[ai](?:no|sse)?\b/,              label: 'supera/i' },
    { re: /\boltre\s?\d/,                          label: 'oltre <soglia>' },
    { re: /\bsopra\s?\d/,                          label: 'sopra <soglia>' },
    { re: /\bsotto\s?\d/,                          label: 'sotto <soglia>' },
  ];

  var CHATBOT_SIGNALS = [
    { re: /\bassistente\b/,                        label: 'assistente' },
    { re: /\brispond[ei]\w*\b/,                    label: 'rispondi/e' },
    { re: /\bchiedimi\b/,                          label: 'chiedimi' },
    { re: /\bdimmi\b/,                             label: 'dimmi' },
    { re: /\baiutami\b/,                           label: 'aiutami' },
    { re: /\baiuta(?:mi)? a capire\b/,              label: 'aiuta a capire' },
    { re: /\bconsulta(?:mi)?\b/,                   label: 'consulta' },
    { re: /\bspiegami\b/,                          label: 'spiegami' },
    { re: /\braccontami\b/,                        label: 'raccontami' },
    { re: /\bcome va\b/,                           label: 'come va' },
    { re: /\bqual\s?[eè]\b/,                       label: 'qual è' },
    { re: /\bquanto\s+(?:consum|cost)\w*\b/,       label: 'quanto consumo/costa' },
  ];

  function labelsOf(hits) { return hits.map(function(h) { return h.label; }).join(', '); }
  function scan(text, patterns) { return patterns.filter(function(p) { return p.re.test(text); }); }

  /** Deterministica: nessuna fetch, nessuna chiamata a un modello.
      Ritorna { type: 'agentbot'|'chatbot'|null, confidence: 'strong'|'weak'|'none', reason } */
  function deriveType(freeText) {
    var text = (freeText || '').toLowerCase();
    var agentbotHits = scan(text, AGENTBOT_SIGNALS);
    var chatbotHits = scan(text, CHATBOT_SIGNALS);
    var score = agentbotHits.length - chatbotHits.length;

    if (score === 0) {
      return { type: null, confidence: 'none',
        reason: 'Il testo non ha segnali chiari in un senso o nell\'altro: scegli tu il tipo.' };
    }
    var type = score > 0 ? 'agentbot' : 'chatbot';
    var hits = score > 0 ? agentbotHits : chatbotHits;
    var confidence = Math.abs(score) >= 2 ? 'strong' : 'weak';
    var what = type === 'agentbot' ? 'agisce o segnala da solo' : 'risponde quando lo chiami';
    var reason = confidence === 'strong'
      ? 'Il testo parla di qualcosa che ' + what + ' (' + labelsOf(hits) + ').'
      : 'Forse ' + what + ' (' + labelsOf(hits) + '), ma il segnale è debole: verifica tu la scelta.';
    return { type: type, confidence: confidence, reason: reason };
  }

  /* ── cataloghi condivisi con l'editor Chatbot (config/templates.js) ── */
  var OPERATORS = [
    { value: '>', label: '>' }, { value: '<', label: '<' },
    { value: '>=', label: '>=' }, { value: '<=', label: '<=' },
    { value: '==', label: '==' }, { value: '!=', label: '!=' },
  ];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ── stato di modulo (un solo wizard montato alla volta) ─────────────── */
  var state = null;

  /* Riferimenti ai controlli vivi dello step 3 (per-tipo). captureStep3()
     li travasa in `state.*` prima di distruggerli/ricrearli o di creare
     l'entità — `state.*` resta l'unica fonte di verità per i payload,
     indipendente dal fatto che i nodi DOM siano ancora montati. */
  var toolGroup = null, scopePicker = null, knowledgeGroup = null;
  var knowledgeAllChk = null, knowledgeSensitiveChk = null;
  var triggerTypeSel = null, triggerPicker = null, triggerOperatorSel = null, triggerThresholdInp = null, triggerCronInp = null;
  var reasoningChk = null, actionTypeSel = null, actionMessageTa = null;
  var actionDomainInp = null, actionServiceInp = null, targetPicker = null;

  function freshState() {
    return {
      step: 1,
      name: '', mission: '',
      derived: { type: null, confidence: 'none', reason: '' },
      type: null,
      chatbotTools: [], chatbotScope: [],
      chatbotKnowledgeAll: true, chatbotKnowledgeKinds: [], chatbotKnowledgeSensitive: false,
      agentbotTriggerType: 'event', agentbotTriggerEntity: '',
      agentbotOperator: '==', agentbotThreshold: '', agentbotCron: '',
      agentbotReasoningEnabled: false,
      agentbotActionType: 'notify', agentbotMessage: '',
      agentbotDomain: '', agentbotService: '', agentbotTargetEntity: '',
    };
  }

  function destroyChatbotPickers() {
    if (scopePicker) { scopePicker.destroy(); scopePicker = null; }
  }
  function destroyAgentbotPickers() {
    if (triggerPicker) { triggerPicker.destroy(); triggerPicker = null; }
    if (targetPicker) { targetPicker.destroy(); targetPicker = null; }
  }

  /* Travasa i valori correnti dei controlli step 3 (se montati) in
     state.* — no-op sicuro se i controlli non esistono ancora (prima
     visita) o sono già stati distrutti. */
  function captureStep3() {
    if (toolGroup) state.chatbotTools = toolGroup.getSelected();
    if (scopePicker) state.chatbotScope = scopePicker.getValue();
    if (knowledgeAllChk) state.chatbotKnowledgeAll = knowledgeAllChk.checked;
    if (knowledgeGroup) state.chatbotKnowledgeKinds = knowledgeGroup.getSelected();
    if (knowledgeSensitiveChk) state.chatbotKnowledgeSensitive = knowledgeSensitiveChk.checked;
    if (triggerTypeSel) state.agentbotTriggerType = triggerTypeSel.value;
    if (triggerPicker) state.agentbotTriggerEntity = triggerPicker.getValue()[0] || '';
    if (triggerOperatorSel) state.agentbotOperator = triggerOperatorSel.value;
    if (triggerThresholdInp) state.agentbotThreshold = triggerThresholdInp.value;
    if (triggerCronInp) state.agentbotCron = triggerCronInp.value;
    if (reasoningChk) state.agentbotReasoningEnabled = reasoningChk.checked;
    if (actionTypeSel) state.agentbotActionType = actionTypeSel.value;
    if (actionMessageTa) state.agentbotMessage = actionMessageTa.value;
    if (actionDomainInp) state.agentbotDomain = actionDomainInp.value;
    if (actionServiceInp) state.agentbotService = actionServiceInp.value;
    if (targetPicker) state.agentbotTargetEntity = targetPicker.getValue()[0] || '';
  }

  /* ── Step 1: Obiettivo ────────────────────────────────────────────── */

  function renderStep1(outlet) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Crea — definisci l\'obiettivo'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Dai un nome e descrivi in linguaggio naturale cosa deve fare. Al passo successivo ti proponiamo il tipo più adatto (Chatbot o Agentbot) — resta sempre una tua scelta.'));

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');
    card.appendChild(body);

    var nameInp = HirisEditorKit.field.text(body, {
      id: 'cw-name', label: 'Nome', value: state.name,
      placeholder: 'Es: Controllo garage notturno',
    });
    var missionTa = HirisEditorKit.field.textarea(body, {
      id: 'cw-mission', label: 'Obiettivo', rows: 4, value: state.mission,
      placeholder: 'Es: avvisami se il garage resta aperto di notte',
      hint: 'Scrivi come parleresti a qualcuno: quello che vuoi che succeda, non come deve essere configurato.',
    });

    var actions = el('div', 'cw-actions');
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.className = 'btn btn-primary'; nextBtn.id = 'cw-step1-next';
    nextBtn.textContent = 'Continua';
    function syncEnabled() { nextBtn.disabled = !(nameInp.value.trim() && missionTa.value.trim()); }
    nameInp.addEventListener('input', syncEnabled);
    missionTa.addEventListener('input', syncEnabled);
    syncEnabled();
    nextBtn.addEventListener('click', function() {
      state.name = nameInp.value.trim();
      state.mission = missionTa.value.trim();
      state.derived = deriveType(state.name + ' ' + state.mission);
      /* Preseleziona SOLO quando il segnale è forte -- onestà quando è
         debole o assente (vedi commento sopra deriveType). */
      state.type = state.derived.confidence === 'strong' ? state.derived.type : null;
      state.step = 2;
      render();
    });
    actions.appendChild(nextBtn);
    card.appendChild(actions);
    outlet.appendChild(card);
  }

  /* ── Step 2: Derivazione del tipo ─────────────────────────────────── */

  function renderStep2(outlet) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Crea — che tipo di entità è?'));
    var note = el('p', 'page-subtitle', state.derived.reason);
    note.id = 'cw-derivation-note';
    outlet.appendChild(note);

    var row = el('div', 'cw-type-row');
    row.style.cssText = 'display:flex;gap:16px;margin:16px 0';
    outlet.appendChild(row);

    var cards = {};
    function buildTypeCard(type, title, desc) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'cw-type-btn section-card';
      btn.id = 'cw-type-' + type;
      btn.setAttribute('data-type', type);
      btn.style.cssText = 'flex:1;text-align:left;cursor:pointer;border:2px solid transparent';
      var badge = el('span', 'cw-badge', 'Suggerito');
      badge.style.display = 'none';
      var h = el('div', 'sc-title', title);
      var d = el('p', 'sc-desc', desc);
      btn.appendChild(badge);
      btn.appendChild(h);
      btn.appendChild(d);
      btn.addEventListener('click', function() {
        state.type = type;
        updateSelectionUI();
      });
      cards[type] = { btn: btn, badge: badge };
      row.appendChild(btn);
      return btn;
    }
    buildTypeCard('chatbot', 'Chatbot', 'Conversa quando lo chiami.');
    buildTypeCard('agentbot', 'Agentbot', 'Agisce o segnala da solo su un evento.');

    var actions = el('div', 'cw-actions');
    var backBtn = document.createElement('button');
    backBtn.type = 'button'; backBtn.className = 'btn btn-ghost'; backBtn.id = 'cw-step2-back';
    backBtn.textContent = 'Indietro';
    backBtn.addEventListener('click', function() { state.step = 1; render(); });
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.className = 'btn btn-primary'; nextBtn.id = 'cw-step2-next';
    nextBtn.textContent = 'Continua';
    nextBtn.addEventListener('click', function() { state.step = 3; render(); });
    actions.appendChild(backBtn);
    actions.appendChild(nextBtn);
    outlet.appendChild(actions);

    function updateSelectionUI() {
      ['chatbot', 'agentbot'].forEach(function(t) {
        var isSelected = state.type === t;
        /* Il badge "Suggerito" compare solo quando il segnale è forte --
           un segnale debole non deve travestirsi da consiglio sicuro. */
        var isSuggested = state.derived.type === t && state.derived.confidence === 'strong';
        cards[t].btn.classList.toggle('is-selected', isSelected);
        cards[t].btn.style.borderColor = isSelected ? 'var(--accent, #6366f1)' : 'transparent';
        cards[t].btn.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        cards[t].badge.style.display = isSuggested ? '' : 'none';
        if (isSuggested) cards[t].btn.setAttribute('data-suggested', state.derived.confidence);
        else cards[t].btn.removeAttribute('data-suggested');
      });
      nextBtn.disabled = !state.type;
    }
    updateSelectionUI();
  }

  /* ── Step 3: guidato per tipo ──────────────────────────────────────── */

  var SCOPE_PILLS = [
    { label: 'luci', pattern: 'light.*' },
    { label: 'switch', pattern: 'switch.*' },
    { label: 'sensori', pattern: 'sensor.*' },
    { label: 'clima', pattern: 'climate.*' },
    { label: 'tapparelle', pattern: 'cover.*' },
    { label: 'binari', pattern: 'binary_sensor.*' },
  ];

  function renderChatbotGuidedFields(body) {
    body.appendChild(el('div', 'fg-label', 'Tool'));
    body.appendChild(el('p', 'sc-desc', 'Cosa può leggere/fare su Home Assistant quando lo chiami.'));
    var toolsRoot = el('div'); toolsRoot.id = 'cw-tools-root';
    body.appendChild(toolsRoot);
    toolGroup = HirisEditorKit.checkGroup(toolsRoot, {
      /* TOOLS è un global bare (config/templates.js dichiara `var TOOLS =
         [...]` a livello top, non `window.TOOLS =`) -- stesso pattern di
         lettura di chatbot-editor.js. */
      items: (typeof TOOLS !== 'undefined' ? TOOLS : []), selected: state.chatbotTools, idPrefix: 'cw-tool',
    });

    body.appendChild(el('div', 'fg-label', 'Scope'));
    body.appendChild(el('p', 'sc-desc', 'Quali entità può leggere o usare.'));
    var scopeRoot = el('div'); scopeRoot.id = 'cw-scope-root';
    body.appendChild(scopeRoot);
    scopePicker = HirisEntityPicker.create(scopeRoot, {
      placeholder: 'Cerca entità…', initial: state.chatbotScope, pills: SCOPE_PILLS,
    });

    body.appendChild(el('div', 'fg-label', 'Knowledge'));
    knowledgeAllChk = HirisEditorKit.field.checkbox(body, {
      id: 'cw-knowledge-all', label: 'Tutte le categorie', value: state.chatbotKnowledgeAll,
    });
    var kindsRoot = el('div'); kindsRoot.id = 'cw-knowledge-kinds-root';
    body.appendChild(kindsRoot);
    knowledgeGroup = HirisEditorKit.checkGroup(kindsRoot, {
      items: (typeof KNOWLEDGE_KINDS !== 'undefined' ? KNOWLEDGE_KINDS : []), selected: state.chatbotKnowledgeKinds, idPrefix: 'cw-kind',
    });
    kindsRoot.style.display = knowledgeAllChk.checked ? 'none' : '';
    knowledgeAllChk.addEventListener('change', function() {
      kindsRoot.style.display = knowledgeAllChk.checked ? 'none' : '';
    });
    /* Invariante 4 (spec): esporre knowledge_access in UI non allarga i
       default -- allow_sensitive resta false finché l'utente non lo spunta
       esplicitamente qui. */
    knowledgeSensitiveChk = HirisEditorKit.field.checkbox(body, {
      id: 'cw-knowledge-sensitive', label: 'Includi anche dati sensibili', value: state.chatbotKnowledgeSensitive,
    });
  }

  function renderAgentbotGuidedFields(body) {
    body.appendChild(el('div', 'fg-label', 'Trigger'));
    triggerTypeSel = HirisEditorKit.field.select(body, {
      id: 'cw-trigger-type', label: 'Tipo trigger',
      options: [{ value: 'event', label: 'Evento' }, { value: 'schedule', label: 'Pianificazione' }],
      value: state.agentbotTriggerType,
    });

    var eventWrap = el('div'); eventWrap.id = 'cw-trigger-event-wrap';
    eventWrap.appendChild(el('p', 'sc-desc', 'Entità osservata (anche lo scope di questa regola).'));
    var triggerPickerRoot = el('div'); triggerPickerRoot.id = 'cw-trigger-entity-root';
    eventWrap.appendChild(triggerPickerRoot);
    triggerPicker = HirisEntityPicker.create(triggerPickerRoot, {
      single: true, placeholder: 'Cerca entità…',
      initial: state.agentbotTriggerEntity ? [state.agentbotTriggerEntity] : [],
    });
    triggerOperatorSel = HirisEditorKit.field.select(eventWrap, {
      id: 'cw-trigger-operator', label: 'Operatore', options: OPERATORS, value: state.agentbotOperator,
    });
    triggerThresholdInp = HirisEditorKit.field.text(eventWrap, {
      id: 'cw-trigger-threshold', label: 'Soglia', value: state.agentbotThreshold,
    });
    body.appendChild(eventWrap);

    var scheduleWrap = el('div'); scheduleWrap.id = 'cw-trigger-schedule-wrap';
    triggerCronInp = HirisEditorKit.field.text(scheduleWrap, {
      id: 'cw-trigger-cron', label: 'Cron (es. "0 7 * * *")', value: state.agentbotCron,
    });
    body.appendChild(scheduleWrap);

    function updateTriggerVisibility() {
      var isEvent = triggerTypeSel.value === 'event';
      eventWrap.style.display = isEvent ? '' : 'none';
      scheduleWrap.style.display = isEvent ? 'none' : '';
    }
    triggerTypeSel.addEventListener('change', updateTriggerVisibility);
    updateTriggerVisibility();

    body.appendChild(el('div', 'fg-label', 'Verdetto'));
    /* Se abilitato, il ragionamento AI viene interpellato SOLO al momento
       del trigger (non ora, non da questo wizard) e gira SEMPRE con
       allowed_tools=[] lato runner -- produce un verdetto testuale, mai
       una scelta di azione: quella resta sempre quanto dichiarato sotto. */
    reasoningChk = HirisEditorKit.field.checkbox(body, {
      id: 'cw-reasoning-enabled', label: 'Fai valutare a un\'AI prima di agire',
      value: state.agentbotReasoningEnabled,
    });
    body.appendChild(el('p', 'field-hint',
      'Se abilitato, il modello legge la tua missione come istruzione e restituisce solo un verdetto testuale -- nessun tool, nessuna scelta d\'azione: quella resta sempre quella dichiarata sotto.'));

    body.appendChild(el('div', 'fg-label', 'Azione'));
    actionTypeSel = HirisEditorKit.field.select(body, {
      id: 'cw-action-type', label: 'Tipo azione',
      options: [{ value: 'notify', label: 'Notifica' }, { value: 'service', label: 'Servizio HA' }],
      value: state.agentbotActionType,
    });

    var notifyWrap = el('div'); notifyWrap.id = 'cw-action-notify-wrap';
    actionMessageTa = HirisEditorKit.field.textarea(notifyWrap, {
      id: 'cw-action-message', label: 'Messaggio', rows: 2,
      value: state.agentbotMessage || state.mission,
    });
    body.appendChild(notifyWrap);

    var serviceWrap = el('div'); serviceWrap.id = 'cw-action-service-wrap';
    actionDomainInp = HirisEditorKit.field.text(serviceWrap, {
      id: 'cw-action-domain', label: 'Dominio (es. switch)', value: state.agentbotDomain,
    });
    actionServiceInp = HirisEditorKit.field.text(serviceWrap, {
      id: 'cw-action-service', label: 'Servizio (es. turn_on)', value: state.agentbotService,
    });
    serviceWrap.appendChild(el('p', 'sc-desc', 'Entità target (anche lo scope dell\'azione).'));
    var targetPickerRoot = el('div'); targetPickerRoot.id = 'cw-action-target-root';
    serviceWrap.appendChild(targetPickerRoot);
    targetPicker = HirisEntityPicker.create(targetPickerRoot, {
      single: true, placeholder: 'Cerca entità…',
      initial: state.agentbotTargetEntity ? [state.agentbotTargetEntity] : [],
    });
    body.appendChild(serviceWrap);

    function updateActionVisibility() {
      var isNotify = actionTypeSel.value === 'notify';
      notifyWrap.style.display = isNotify ? '' : 'none';
      serviceWrap.style.display = isNotify ? 'none' : '';
    }
    actionTypeSel.addEventListener('change', updateActionVisibility);
    updateActionVisibility();
  }

  function renderStep3(outlet) {
    captureStep3();
    destroyChatbotPickers();
    destroyAgentbotPickers();
    toolGroup = null; knowledgeGroup = null; knowledgeAllChk = null; knowledgeSensitiveChk = null;
    triggerTypeSel = null; triggerOperatorSel = null; triggerThresholdInp = null; triggerCronInp = null;
    reasoningChk = null; actionTypeSel = null; actionMessageTa = null; actionDomainInp = null; actionServiceInp = null;

    outlet.innerHTML = '';
    var isAgentbot = state.type === 'agentbot';
    outlet.appendChild(el('div', 'page-title',
      isAgentbot ? 'Crea Agentbot — trigger, verdetto, azione' : 'Crea Chatbot — tool, scope, knowledge'));

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');
    body.id = 'cw-step3-body';
    card.appendChild(body);
    if (isAgentbot) renderAgentbotGuidedFields(body);
    else renderChatbotGuidedFields(body);
    outlet.appendChild(card);

    var actions = el('div', 'cw-actions');
    var backBtn = document.createElement('button');
    backBtn.type = 'button'; backBtn.className = 'btn btn-ghost'; backBtn.id = 'cw-step3-back';
    backBtn.textContent = 'Indietro';
    backBtn.addEventListener('click', function() { captureStep3(); state.step = 2; render(); });
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.className = 'btn btn-primary'; nextBtn.id = 'cw-step3-next';
    nextBtn.textContent = 'Continua';
    nextBtn.addEventListener('click', function() { captureStep3(); state.step = 4; render(); });
    actions.appendChild(backBtn);
    actions.appendChild(nextBtn);
    outlet.appendChild(actions);
  }

  /* ── Step 4: riepilogo + crea ──────────────────────────────────────── */

  /* Chatbot: tool liberi entro allowlist, NESSUN trigger -- il payload non
     ha nemmeno il campo per rappresentarne uno. */
  function buildChatbotPayload() {
    return {
      name: state.name,
      system_prompt: state.mission,
      strategic_context: '',
      allowed_tools: state.chatbotTools.slice(),
      allowed_entities: state.chatbotScope.slice(),
      allowed_services: [],
      model: 'auto',
      max_tokens: 4096,
      restrict_to_home: true,
      require_confirmation: true,
      enabled: true,
      max_chat_turns: 0,
      response_mode: 'auto',
      thinking_budget: 0,
      knowledge_access: {
        allow_sensitive: !!state.chatbotKnowledgeSensitive,
        kinds: state.chatbotKnowledgeAll ? 'all' : state.chatbotKnowledgeKinds.slice(),
      },
    };
  }

  /* Agentbot: azione SEMPRE dichiarata qui, reasoning gira SEMPRE con
     allowed_tools=[] lato runner -- questo builder non conosce nemmeno il
     concetto di "allowed_tools" per un Agentbot: la chiave non esiste in
     nessun ramo del codice sotto. Stessa forma esatta di
     watcher/agentbots.py::validate_agentbot (name, enabled, severity,
     trigger, reasoning, action) -- mai un `id` nel body (create sempre
     fresh, come agentbot-editor.js). */
  function buildAgentbotPayload() {
    var payload = { name: state.name, enabled: true, severity: 'info' };
    if (state.agentbotTriggerType === 'schedule') {
      payload.trigger = { type: 'schedule', cron: state.agentbotCron };
    } else {
      payload.trigger = {
        type: 'event',
        entity_id: state.agentbotTriggerEntity,
        operator: state.agentbotOperator,
        threshold: state.agentbotThreshold,
      };
    }
    payload.reasoning = {
      enabled: !!state.agentbotReasoningEnabled,
      model: 'auto',
      prompt: state.mission,
    };
    if (state.agentbotActionType === 'service') {
      payload.action = {
        type: 'service',
        domain: state.agentbotDomain,
        service: state.agentbotService,
        entity_id: state.agentbotTargetEntity,
      };
    } else {
      payload.action = { type: 'notify', message: state.agentbotMessage || state.mission };
    }
    return payload;
  }

  function renderStep4(outlet) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Crea — riepilogo'));

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');
    body.appendChild(el('p', null, 'Nome: ' + state.name));
    body.appendChild(el('p', null, 'Tipo: ' + (state.type === 'agentbot' ? 'Agentbot' : 'Chatbot')));
    body.appendChild(el('p', 'sc-desc', state.mission));
    card.appendChild(body);
    outlet.appendChild(card);

    var errorEl = el('p', 'cw-error', '');
    errorEl.id = 'cw-error';
    errorEl.style.display = 'none';
    outlet.appendChild(errorEl);

    var actions = el('div', 'cw-actions');
    var backBtn = document.createElement('button');
    backBtn.type = 'button'; backBtn.className = 'btn btn-ghost'; backBtn.id = 'cw-step4-back';
    backBtn.textContent = 'Indietro';
    backBtn.addEventListener('click', function() { state.step = 3; render(); });
    var createBtn = document.createElement('button');
    createBtn.type = 'button'; createBtn.className = 'btn btn-primary'; createBtn.id = 'cw-create-btn';
    createBtn.textContent = 'Crea';
    createBtn.addEventListener('click', function() { createEntity(createBtn, errorEl); });
    actions.appendChild(backBtn);
    actions.appendChild(createBtn);
    outlet.appendChild(actions);
  }

  function createEntity(btn, errorEl) {
    btn.disabled = true;
    errorEl.style.display = 'none';
    var isAgentbot = state.type === 'agentbot';
    var payload = isAgentbot ? buildAgentbotPayload() : buildChatbotPayload();
    var url = isAgentbot ? 'api/agentbots' : 'api/chatbots';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(payload),
    }).then(function(r) {
      if (!r.ok) {
        return r.json().catch(function() { return {}; }).then(function(d) {
          throw new Error(d.error || ('HTTP ' + r.status));
        });
      }
      return r.json();
    }).then(function(created) {
      /* Forma di risposta diversa fra i due endpoint (vedi
         handlers_chatbots.py::handle_create_chatbot -- asdict(agent), id
         in cima; handlers_agentbots.py::handle_create_agentbot -- {ok,
         agentbot:{id,...}, agentbots:[...]}, id annidato). */
      var id = isAgentbot ? (created && created.agentbot && created.agentbot.id)
                           : (created && created.id);
      var dest = isAgentbot ? ('#/agentbots/' + encodeURIComponent(id))
                             : ('#/chatbots/' + encodeURIComponent(id));
      HirisRouter.navigate(dest);
    }).catch(function(err) {
      btn.disabled = false;
      errorEl.textContent = 'Errore nella creazione: ' + (err && err.message ? err.message : 'riprova.');
      errorEl.style.display = '';
    });
  }

  /* ── mount/render ──────────────────────────────────────────────────── */

  function render() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    if (state.step === 1) renderStep1(outlet);
    else if (state.step === 2) renderStep2(outlet);
    else if (state.step === 3) renderStep3(outlet);
    else renderStep4(outlet);
  }

  function mount() {
    destroyChatbotPickers();
    destroyAgentbotPickers();
    toolGroup = null; knowledgeGroup = null; knowledgeAllChk = null; knowledgeSensitiveChk = null;
    triggerTypeSel = null; triggerOperatorSel = null; triggerThresholdInp = null; triggerCronInp = null;
    reasoningChk = null; actionTypeSel = null; actionMessageTa = null; actionDomainInp = null; actionServiceInp = null;
    state = freshState();
    render();
  }

  window.HirisCreateWizard = { mount: mount, deriveType: deriveType };
})();
