/* HIRIS · Designer · Agentbot editor (SP-4 Fase B Task 5)
   Editor per-entità per una singola regola Agentbot, estratto dal blocco 4
   di agentbot-route.js (righe 340-605 pre-split, vedi grounding A5): quel
   blocco aveva già semantica di entità (id proprio, POST/PUT/DELETE
   proprio, salvataggio per riga) mentre il resto della vecchia pagina
   Sentinella è UN documento unico (policy detector+situazioni+preparazione,
   vedi agentbot-route.js). Costruito sul kit condiviso (config/editor-kit.js,
   Task 3 -- field.* reintrodotte in QUESTO task come loro primo consumatore
   reale) e sul componente entità istanziabile (config/entity-picker.js,
   Task 1): ogni regola ne usa TRE istanze indipendenti, non lo slot
   singleton `window.HirisAgentEntityPicker` introdotto come bridge nel
   Task 1 (rimosso qui, vedi in fondo al file -- niente altro lo consuma).

   Sicurezza (invariante, non toccata da questo task):
   - l'azione (notify | service) resta DICHIARATA in config -- l'utente la
     sceglie qui in UI, il ragionamento AI (reasoning.enabled) non la
     sceglie mai: watcher/agentbot_runner.py calcola SEMPRE
     `suggested = agentbot_action(agentbot)` dal config validato, MAI
     dall'output del modello (vedi run_decision/force_notify_only lì);
   - il ragionamento AI gira con allowed_tools=[] (nessun tool esposto al
     modello per una regola Agentbot -- solo verdetto/severità in testo);
   - il semaforo (security/semaphore.py::gate_action) resta l'UNICO gate
     sull'esecuzione dell'azione, qualunque sia il verdetto del
     ragionamento. Questo editor non introduce alcun percorso che aggiri
     quel gate: costruisce solo il payload che watcher/agentbots.py::
     validate_agentbot valida server-side.

   ATTENZIONE (grounding): validate_agentbot SCARTA IN SILENZIO i campi
   sconosciuti al suo whitelist -- payload = { name, enabled, severity,
   trigger, reasoning, action } (mai `id` nel body: la create striscia un
   id client-fornito, la update usa l'id del path). Qualunque campo nuovo
   aggiunto qui va aggiunto ANCHE a watcher/agentbots.py o sparisce al
   primo salvataggio -- vedi il round-trip check nel report del task. */
(function() {
  'use strict';

  /* ── sezione: fonte unica per section-card + anchor-nav (stesso pattern
     di chatbot-editor.js SECTIONS/buildSections, Task 4) ─────────────── */
  var SECTIONS = [
    { id: 'identita',   title: 'Identità',      desc: 'Nome, severità della regola.' },
    { id: 'trigger',    title: 'Trigger',       desc: 'Cosa fa scattare la regola: un evento su un\'entità o una pianificazione.' },
    { id: 'modello',    title: 'Modello',       desc: 'Se e con quale modello AI ragionare prima di agire.' },
    { id: 'verdetto',   title: 'Verdetto',      desc: 'Istruzioni per il ragionamento AI (usate solo se abilitato).' },
    { id: 'azione',     title: 'Azione',        desc: 'Cosa fare quando la regola scatta: notifica o servizio Home Assistant.' },
    { id: 'stato',      title: 'Abilitazione',  desc: 'Se questa regola è attiva.' },
    { id: 'osservabilita', title: 'Osservabilità', desc: 'Eventi recenti generati da questa regola.' }
  ];

  var OPERATORS = [
    { value: '>', label: '>' }, { value: '<', label: '<' },
    { value: '>=', label: '>=' }, { value: '<=', label: '<=' },
    { value: '==', label: '==' }, { value: '!=', label: '!=' }
  ];
  function isEqualityOp(op) { return op === '==' || op === '!='; }
  function toNumOrNull(v) {
    if (v === '' || v == null) return null;
    var x = parseFloat(v);
    return isNaN(x) ? null : x;
  }
  function buildThresholdValue(operator, raw) {
    if (isEqualityOp(operator)) return raw;
    var x = parseFloat(raw);
    return isNaN(x) ? raw : x;
  }
  function defaultAgentbot() {
    return {
      id: null, name: '', enabled: true, severity: 'info',
      trigger: { type: 'event', entity_id: '', operator: '==', threshold: '' },
      reasoning: { enabled: false, model: 'auto', prompt: '' },
      action: { type: 'notify', message: '' }
    };
  }

  /* ── stato di modulo (un solo editor Agentbot montato alla volta,
     stesso pattern di chatbot-editor.js) ──────────────────────────────── */
  var evEntityPicker = null;         /* trigger event: entità osservata */
  var schCondEntityPicker = null;    /* trigger schedule: entità della condizione opzionale */
  var actEntityPicker = null;        /* azione service: entità target */
  var dirtyTrackHandle = null;
  var markDirtyRef = null;           /* letto dall'onChange dei tre picker sopra (i chip non sono <input>) */
  var saveBarHandle = null;

  /* Guard di navigazione (bug live #2): NON installato di nuovo qui.
     Dal Task 6, main.js lo installa UNA volta a livello top del proprio
     IIFE (era chatbot-editor.js prima -- hoistato per non dipendere dal
     fatto che quel file capitasse di essere incluso) su
     HirisState.get('unsaved') -- chiave GLOBALE condivisa (vedi C9 nel
     grounding), non per-editor. Un secondo guard() qui aprirebbe DUE
     listener su 'hashchange'/'beforeunload' che leggono la STESSA chiave,
     quindi un confirm() doppio a ogni navigazione con modifiche pendenti. */

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(path, opts);
  }

  /* ───────────────────────── data layer ───────────────────────── */

  function loadAgentbots() {
    return api('api/agentbots', { method: 'GET' })
      .then(function(r) { return r.ok ? r.json() : { agentbots: [] }; })
      .then(function(d) { return d.agentbots || []; })
      .catch(function() { return []; });
  }

  function resolveAgentbot(agentbotId) {
    return loadAgentbots().then(function(list) {
      var found = list.filter(function(a) { return a.id === agentbotId; })[0];
      if (!found) throw new Error('Agentbot non trovato: ' + agentbotId);
      return found;
    });
  }

  /* ───────────────────────── populate*() per sezione ───────────────────────── */

  var nameInp, severitySel, enabledChk;
  function populateIdentita() {
    var body = document.getElementById('sc-body-identita');
    body.innerHTML = '';
    nameInp = HirisEditorKit.field.text(body, { label: 'Nome', placeholder: 'Es: Garage aperto di notte' });
    severitySel = HirisEditorKit.field.select(body, {
      label: 'Severità',
      options: [
        { value: 'info', label: 'Info' },
        { value: 'warn', label: 'Warn' },
        { value: 'alert', label: 'Alert' }
      ],
      value: 'info'
    });
  }

  var triggerTypeSel, eventWrap, scheduleWrap;
  var evOperator, evThreshold, evDuration;
  var schKindSel, schCron, schInterval, schCondOperator, schCondThreshold;
  function populateTrigger() {
    var body = document.getElementById('sc-body-trigger');
    body.innerHTML = '';

    if (evEntityPicker) { evEntityPicker.destroy(); evEntityPicker = null; }
    if (schCondEntityPicker) { schCondEntityPicker.destroy(); schCondEntityPicker = null; }

    triggerTypeSel = HirisEditorKit.field.select(body, {
      label: 'Tipo trigger',
      options: [
        { value: 'event', label: 'Evento' },
        { value: 'schedule', label: 'Pianificazione' }
      ],
      value: 'event'
    });

    /* ── Evento ── */
    eventWrap = document.createElement('div');
    eventWrap.appendChild(el('p', 'sc-desc', 'Entità osservata (picker indipendente #1)'));
    var evPickerRoot = document.createElement('div');
    eventWrap.appendChild(evPickerRoot);
    evEntityPicker = HirisEntityPicker.create(evPickerRoot, {
      single: true,
      placeholder: 'Cerca entità…',
      onChange: function() { if (markDirtyRef) markDirtyRef(); }
    });
    evOperator = HirisEditorKit.field.select(eventWrap, { label: 'Operatore', options: OPERATORS, value: '==' });
    evThreshold = HirisEditorKit.field.text(eventWrap, { label: 'Soglia (numero, o testo per ==/!=)' });
    evDuration = HirisEditorKit.field.number(eventWrap, { label: 'Durata (minuti, opzionale)', min: 0 });
    body.appendChild(eventWrap);

    /* ── Pianificazione ── */
    scheduleWrap = document.createElement('div');
    schKindSel = HirisEditorKit.field.select(scheduleWrap, {
      label: 'Modalità',
      options: [
        { value: 'cron', label: 'Cron' },
        { value: 'interval', label: 'Intervallo (minuti)' }
      ],
      value: 'cron'
    });
    schCron = HirisEditorKit.field.text(scheduleWrap, { label: 'Cron (es. "0 7 * * *")' });
    schInterval = HirisEditorKit.field.number(scheduleWrap, { label: 'Intervallo (minuti)', min: 1 });
    scheduleWrap.appendChild(el('p', 'sc-desc', 'Condizione aggiuntiva (opzionale, picker indipendente #2)'));
    var schCondPickerRoot = document.createElement('div');
    scheduleWrap.appendChild(schCondPickerRoot);
    schCondEntityPicker = HirisEntityPicker.create(schCondPickerRoot, {
      single: true,
      placeholder: 'Cerca entità condizione…',
      onChange: function() { if (markDirtyRef) markDirtyRef(); }
    });
    schCondOperator = HirisEditorKit.field.select(scheduleWrap, { label: 'Operatore condizione', options: OPERATORS, value: '==' });
    schCondThreshold = HirisEditorKit.field.text(scheduleWrap, { label: 'Soglia condizione' });
    body.appendChild(scheduleWrap);

    function updateTriggerVisibility() {
      var isEvent = triggerTypeSel.value === 'event';
      eventWrap.style.display = isEvent ? '' : 'none';
      scheduleWrap.style.display = isEvent ? 'none' : '';
    }
    function updateScheduleKindVisibility() {
      var isCron = schKindSel.value === 'cron';
      schCron.parentNode.style.display = isCron ? '' : 'none';
      schInterval.parentNode.style.display = isCron ? 'none' : '';
    }
    triggerTypeSel.addEventListener('change', updateTriggerVisibility);
    schKindSel.addEventListener('change', updateScheduleKindVisibility);
    evOperator.addEventListener('change', function() {
      evThreshold.type = isEqualityOp(evOperator.value) ? 'text' : 'number';
    });
    schCondOperator.addEventListener('change', function() {
      schCondThreshold.type = isEqualityOp(schCondOperator.value) ? 'text' : 'number';
    });
    updateTriggerVisibility();
    updateScheduleKindVisibility();
    evThreshold.type = isEqualityOp(evOperator.value) ? 'text' : 'number';
    schCondThreshold.type = isEqualityOp(schCondOperator.value) ? 'text' : 'number';
  }

  var reasoningChk, reasoningModelSel;
  function populateModello() {
    var body = document.getElementById('sc-body-modello');
    body.innerHTML = '';
    reasoningChk = HirisEditorKit.field.checkbox(body, { label: 'Abilita ragionamento AI' });
    var modelWrap = document.createElement('div');
    body.appendChild(modelWrap);
    reasoningModelSel = HirisEditorKit.modelSelect(modelWrap, { label: 'Modello', value: 'auto' });
  }

  var reasoningPrompt;
  function populateVerdetto() {
    var body = document.getElementById('sc-body-verdetto');
    body.innerHTML = '';
    reasoningPrompt = HirisEditorKit.field.textarea(body, {
      label: 'Prompt personalizzato',
      rows: 4,
      hint: 'Usato solo se "Abilita ragionamento AI" è attivo nella sezione Modello. Il ragionamento non ha mai accesso a tool: produce solo un verdetto testuale, l\'azione resta quella dichiarata qui sotto.'
    });
  }

  var actionTypeSel, notifyWrap, serviceWrap, notifyMessage;
  var actDomain, actService, actOffAfter;
  function populateAzione() {
    var body = document.getElementById('sc-body-azione');
    body.innerHTML = '';

    if (actEntityPicker) { actEntityPicker.destroy(); actEntityPicker = null; }

    actionTypeSel = HirisEditorKit.field.select(body, {
      label: 'Tipo azione',
      options: [
        { value: 'notify', label: 'Notifica' },
        { value: 'service', label: 'Servizio HA' }
      ],
      value: 'notify'
    });

    notifyWrap = document.createElement('div');
    notifyMessage = HirisEditorKit.field.textarea(notifyWrap, { label: 'Messaggio', rows: 3 });
    body.appendChild(notifyWrap);

    serviceWrap = document.createElement('div');
    actDomain = HirisEditorKit.field.text(serviceWrap, { label: 'Dominio (es. switch)' });
    actService = HirisEditorKit.field.text(serviceWrap, { label: 'Servizio (es. turn_on)' });
    serviceWrap.appendChild(el('p', 'sc-desc', 'Entità target (picker indipendente #3)'));
    var actPickerRoot = document.createElement('div');
    serviceWrap.appendChild(actPickerRoot);
    actEntityPicker = HirisEntityPicker.create(actPickerRoot, {
      single: true,
      placeholder: 'Cerca entità target…',
      onChange: function() { if (markDirtyRef) markDirtyRef(); }
    });
    actOffAfter = HirisEditorKit.field.number(serviceWrap, { label: 'Spegni dopo (minuti, opzionale)', min: 0 });
    body.appendChild(serviceWrap);

    function updateActionVisibility() {
      var isNotify = actionTypeSel.value === 'notify';
      notifyWrap.style.display = isNotify ? '' : 'none';
      serviceWrap.style.display = isNotify ? 'none' : '';
    }
    actionTypeSel.addEventListener('change', updateActionVisibility);
    updateActionVisibility();
  }

  function populateStato() {
    var body = document.getElementById('sc-body-stato');
    body.innerHTML = '';
    enabledChk = HirisEditorKit.field.checkbox(body, { label: 'Regola abilitata' });
  }

  function populateOsservabilita(agentbotId) {
    var body = document.getElementById('sc-body-osservabilita');
    body.innerHTML = '';
    if (!agentbotId) {
      body.appendChild(el('p', 'sc-desc', 'Salva questo Agentbot per vedere qui gli eventi recenti che ha generato.'));
      return;
    }
    body.appendChild(el('p', 'sc-desc', 'Caricamento…'));
    api('api/sentinel/timeline', { method: 'GET' })
      .then(function(r) { return r.ok ? r.json() : { events: [] }; })
      .then(function(t) {
        body.innerHTML = '';
        var kind = 'agentbot:' + agentbotId;
        var events = (t.events || []).filter(function(ev) { return ev.kind === kind; });
        if (!events.length) {
          body.appendChild(el('p', 'sc-desc', 'Nessun evento registrato per questa regola.'));
          return;
        }
        events.forEach(function(ev) {
          body.appendChild(el('div', 'log-row',
            (ev.entity_id || '') + ' · ' + (ev.outcome || '') + ' · ' + (ev.message || '')));
        });
      })
      .catch(function() {
        body.innerHTML = '';
        body.appendChild(el('p', 'sc-desc', 'Errore nel caricamento degli eventi.'));
      });
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ── section-card + anchor-nav builder (identico a chatbot-editor.js) ── */
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
    document.querySelectorAll('.anchor-link[href^="#sec-"]').forEach(function(l) {
      l.addEventListener('click', function(e) {
        e.preventDefault();
        var target = document.getElementById(l.getAttribute('href').slice(1));
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  /* ── payload / open / save ───────────────────────────────────────── */

  function openAgentbot(a) {
    nameInp.value = a.name || '';
    severitySel.value = a.severity || 'info';
    enabledChk.checked = !!a.enabled;

    var trg = a.trigger || {};
    triggerTypeSel.value = trg.type || 'event';
    if (trg.type === 'event') {
      if (evEntityPicker) evEntityPicker.setValue(trg.entity_id ? [trg.entity_id] : []);
      evOperator.value = trg.operator || '==';
      evThreshold.value = trg.threshold != null ? trg.threshold : '';
      evThreshold.type = isEqualityOp(evOperator.value) ? 'text' : 'number';
      evDuration.value = trg.duration_min != null ? trg.duration_min : '';
    } else {
      schKindSel.value = trg.interval_min != null ? 'interval' : 'cron';
      schCron.value = trg.cron || '';
      schInterval.value = trg.interval_min != null ? trg.interval_min : '';
      var cond = trg.condition || {};
      if (schCondEntityPicker) schCondEntityPicker.setValue(cond.entity_id ? [cond.entity_id] : []);
      schCondOperator.value = cond.operator || '==';
      schCondThreshold.value = cond.threshold != null ? cond.threshold : '';
      schCondThreshold.type = isEqualityOp(schCondOperator.value) ? 'text' : 'number';
    }
    triggerTypeSel.dispatchEvent(new Event('change'));
    schKindSel.dispatchEvent(new Event('change'));

    var reasoning = a.reasoning || {};
    reasoningChk.checked = !!reasoning.enabled;
    HirisEditorKit.setModelValue(reasoningModelSel, reasoning.model || 'auto');
    reasoningPrompt.value = reasoning.prompt || '';

    var act = a.action || {};
    actionTypeSel.value = act.type || 'notify';
    notifyMessage.value = act.type !== 'service' ? (act.message || '') : '';
    actDomain.value = act.domain || '';
    actService.value = act.service || '';
    if (actEntityPicker) actEntityPicker.setValue(act.entity_id ? [act.entity_id] : []);
    actOffAfter.value = act.off_after_min != null ? act.off_after_min : '';
    actionTypeSel.dispatchEvent(new Event('change'));

    var btnDel = document.getElementById('btn-delete');
    if (btnDel) btnDel.style.display = a.id ? '' : 'none';

    populateOsservabilita(a.id);
  }

  function initNewAgentbot() {
    var empty = defaultAgentbot();
    openAgentbot(empty);
  }

  function buildPayload() {
    var payload = {
      name: nameInp.value,
      enabled: enabledChk.checked,
      severity: severitySel.value
    };
    if (triggerTypeSel.value === 'event') {
      var trigger = {
        type: 'event',
        entity_id: (evEntityPicker ? evEntityPicker.getValue()[0] : '') || '',
        operator: evOperator.value,
        threshold: buildThresholdValue(evOperator.value, evThreshold.value)
      };
      var dur = toNumOrNull(evDuration.value);
      if (dur != null) trigger.duration_min = dur;
      payload.trigger = trigger;
    } else {
      var trigger2 = { type: 'schedule' };
      if (schKindSel.value === 'cron') {
        trigger2.cron = schCron.value;
      } else {
        var iv = toNumOrNull(schInterval.value);
        if (iv != null) trigger2.interval_min = iv;
      }
      var condEntity = schCondEntityPicker ? schCondEntityPicker.getValue()[0] : '';
      if (condEntity) {
        trigger2.condition = {
          entity_id: condEntity,
          operator: schCondOperator.value,
          threshold: buildThresholdValue(schCondOperator.value, schCondThreshold.value)
        };
      }
      payload.trigger = trigger2;
    }
    payload.reasoning = {
      enabled: reasoningChk.checked,
      model: reasoningModelSel.value,
      prompt: reasoningPrompt.value
    };
    /* Azione: DICHIARATA qui dall'utente in config, mai scelta dal
       ragionamento AI (vedi commento di sicurezza in testa al file). */
    if (actionTypeSel.value === 'notify') {
      payload.action = { type: 'notify', message: notifyMessage.value };
    } else {
      var action = {
        type: 'service',
        domain: actDomain.value,
        service: actService.value,
        entity_id: (actEntityPicker ? actEntityPicker.getValue()[0] : '') || ''
      };
      var off = toNumOrNull(actOffAfter.value);
      if (off != null) action.off_after_min = off;
      payload.action = action;
    }
    return payload;
  }

  window.saveAgentbot = function() {
    var payload = buildPayload();
    var cid = HirisState.get('activeAgentbotId');
    var method = cid ? 'PUT' : 'POST';
    var url = cid ? ('api/agentbots/' + encodeURIComponent(cid)) : 'api/agentbots';
    return api(url, { method: method, body: JSON.stringify(payload) })
      .then(function(r) {
        if (!r.ok) {
          return r.json().catch(function() { return {}; }).then(function(d) {
            alert(d.error || ('Errore salvataggio Agentbot (HTTP ' + r.status + ')'));
            throw new Error('save failed');
          });
        }
        return r.json();
      })
      .then(function(res) {
        var saved = res && res.agentbot;
        if (saved) openAgentbot(saved);
        if (!cid && saved && saved.id) {
          window.location.hash = '#/agentbots/' + encodeURIComponent(saved.id);
        }
        return saved;
      });
  };

  window.deleteAgentbot = function() {
    var cid = HirisState.get('activeAgentbotId');
    if (!cid) return;
    if (!confirm('Eliminare questo Agentbot?')) return;
    return api('api/agentbots/' + encodeURIComponent(cid), { method: 'DELETE' })
      .then(function(r) {
        if (!r.ok) {
          return r.json().catch(function() { return {}; }).then(function(d) {
            alert(d.error || ('Errore eliminazione (HTTP ' + r.status + ')'));
            throw new Error('delete failed');
          });
        }
        HirisState.set('activeAgentbotId', null);
        window.location.hash = '#/agentbots';
      });
  };

  /* ── sticky actions: stesso pattern di chatbot-editor.js Task 3/4 --
     dirty.track() osserva il sottoalbero, i tre picker notificano onChange
     esplicitamente (i chip non sono <input>). Nessun onTestRun: non esiste
     un endpoint "esegui ora" per un singolo Agentbot -- il bottone Test Run
     del template condiviso viene nascosto sotto. */
  function setupStickyActions(agentbotId) {
    var outlet = document.getElementById('route-outlet');
    HirisState.set('unsaved', false);

    function markDirty() { HirisState.set('unsaved', true); if (saveBarHandle) saveBarHandle.setDirty(true); }
    function markClean() { HirisState.set('unsaved', false); if (saveBarHandle) saveBarHandle.setDirty(false); }

    if (dirtyTrackHandle) { dirtyTrackHandle.stop(); dirtyTrackHandle = null; }
    dirtyTrackHandle = HirisEditorKit.dirty.track(outlet, markDirty);
    markDirtyRef = markDirty;

    saveBarHandle = HirisEditorKit.saveBar(outlet, {
      onSave: function() {
        try {
          var p = saveAgentbot();
          if (p && p.then) p.then(function() { markClean(); }).catch(function(err) { console.error('save rejected:', err); });
          else markClean();
        } catch(e) { console.error('saveAgentbot threw:', e); alert('Save error: ' + (e.message || e)); }
      },
      onCancel: function() {
        if (HirisState.get('unsaved') && !confirm('Annullare le modifiche non salvate?')) return;
        window.location.hash = '#/agentbots';
      },
      onDelete: agentbotId ? function() {
        try { deleteAgentbot(); } catch(e) { console.error('deleteAgentbot threw:', e); alert('Delete error: ' + (e.message || e)); }
      } : null,
    });
    saveBarHandle.setDirty(false);

    var btnTestRun = outlet.querySelector('#btn-test-run');
    if (btnTestRun) btnTestRun.style.display = 'none';
  }

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

  function mount(agentbotId) {
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
      step('setupStickyActions', function() { setupStickyActions(agentbotId); });
      step('buildSections', function() {
        var content = outlet.querySelector('.editor-content');
        var anchorNav = outlet.querySelector('.anchor-nav');
        buildSections(content, anchorNav);
      });
      step('populateIdentita', populateIdentita);
      step('populateTrigger', populateTrigger);
      step('populateModello', populateModello);
      step('populateVerdetto', populateVerdetto);
      step('populateAzione', populateAzione);
      step('populateStato', populateStato);
      step('setupAnchorNav', setupAnchorNav);

      if (agentbotId) {
        return resolveAgentbot(agentbotId).then(function(a) {
          step('openAgentbot', function() { openAgentbot(a); });
          var hereEl = document.getElementById('chrome-here');
          if (hereEl && a && a.name) hereEl.textContent = 'Agentbot / ' + a.name;
        });
      } else {
        step('initNewAgentbot', initNewAgentbot);
      }
    }).catch(function(e) {
      console.error('[HirisAgentbotEditor] mount failed:', e);
      var outlet2 = document.getElementById('route-outlet');
      if (outlet2) {
        var msg = (e && e.message) ? e.message : String(e);
        var stepName = e && e.step ? e.step : 'unknown';
        outlet2.innerHTML =
          '<div style="padding:24px;color:var(--err)">' +
            '<h2>Errore caricamento editor</h2>' +
            '<p>' + msg + '</p>' +
            '<p style="font-size:12px;color:var(--text-3);font-family:var(--font-mono)">Step: <strong>' + stepName + '</strong></p>' +
          '</div>';
      }
    });
  }

  window.HirisAgentbotEditor = { mount: mount };
})();
