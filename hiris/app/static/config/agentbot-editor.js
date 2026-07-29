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
   primo salvataggio -- vedi il round-trip check nel report del task.

   ── Agenti v1.1 Fase 2 Task 6: la MODALITA' ─────────────────────────────
   Un Agentbot ha due modalita' (watcher/agentbots.py::validate_agentbot):

     mode="rule"       trigger (evento o pianificazione) + AZIONE dichiarata.
                       `objective` e `perimeter` sono VIETATI: presenti ->
                       l'intero Agentbot viene RIGETTATO.
     mode="objective"  `objective` (stringa non vuota) + `perimeter` sempre
                       materializzato dal validatore. `action` VIETATA (le
                       azioni nascono a valle come Task dichiarativi) e
                       trigger a EVENTO vietato (un turno LLM e' pesante:
                       gli eventi restano dominio delle regole).

   Whitelist di buildPayload() -- la trappola dichiarata del task: il
   payload e' costruito DA ZERO campo per campo. Prima di questo task
   conteneva { name, enabled, severity, trigger, reasoning, action }: un
   agente-obiettivo aperto e risalvato dalla SPA sarebbe stato
   silenziosamente RICONVERTITO IN REGOLA (mode assente -> default "rule",
   objective/perimeter persi, `action` reintrodotta). Ora `mode` e'
   esplicito SEMPRE, e i tre campi per-modalita' sono mutuamente esclusivi
   per costruzione, non per convenzione.

   Convenzione null-vs-[] del perimetro (unica in tutta la catena, vedi
   watcher/agentbots.py::_validate_str_list e tools/dispatcher.py):
     null = NESSUNA restrizione su quell'asse (resta il solo semaforo)
     []   = NEGA TUTTO su quell'asse
   Sono OPPOSTI, mai intercambiabili. Per questo il perimetro qui non e' un
   picker nudo (un picker vuoto non sa dire quale delle due cose intendeva
   l'utente) ma una coppia "interruttore + elenco": interruttore spento ->
   `null`; acceso -> l'elenco cosi' com'e', vuoto compreso -> `[]`.

   `max_tier` NON e' esposto in questa UI, deliberatamente: e' nello schema
   ma nessun runtime lo onora (debito noto dichiarato della fase, vedi
   docs/design/2026-07-29-piano-agenti-v1.1-fase2.md). Un controllo che non
   fa nulla e' una promessa falsa; omesso, il validatore applica da se' il
   default piu' stretto ("green"). Va esposto quando qualcuno lo legge. */
(function() {
  'use strict';

  /* ── sezione: fonte unica per section-card + anchor-nav (stesso pattern
     di chatbot-editor.js SECTIONS/buildSections, Task 4) ─────────────── */
  var SECTIONS = [
    { id: 'identita',   title: 'Identità',      desc: 'Nome, modalità e severità.' },
    { id: 'trigger',    title: 'Trigger',       desc: 'Cosa lo fa partire: un evento su un\'entità o una pianificazione.' },
    { id: 'obiettivo',  title: 'Obiettivo e perimetro', desc: 'Solo in modalità obiettivo: cosa deve ottenere l\'agente e dentro quali confini.' },
    { id: 'modello',    title: 'Modello',       desc: 'Se e con quale modello AI ragionare prima di agire.' },
    { id: 'verdetto',   title: 'Verdetto',      desc: 'Istruzioni per il ragionamento AI (usate solo se abilitato).' },
    { id: 'azione',     title: 'Azione',        desc: 'Solo in modalità regola: cosa fare quando scatta, notifica o servizio Home Assistant.' },
    { id: 'stato',      title: 'Abilitazione',  desc: 'Se questa regola è attiva.' },
    { id: 'osservabilita', title: 'Osservabilità', desc: 'Eventi recenti generati da questa regola.' }
  ];

  /* Il testo che spiega la cosa meno intuitiva del perimetro: NON e' solo
     un limite sull'azione. La stessa `allowed_entities` filtra le LETTURE
     del ragionatore (tools/dispatcher.py: get_entity_states, get_history,
     get_home_status, get_entities_on, get_entities_by_domain,
     get_area_entities) e le azioni dei Task che l'agente emette
     (task_engine._run_action). L'utente deve saperlo PRIMA, non scoprirlo
     quando l'agente non vede il sensore che gli serve per decidere. */
  var PERIMETER_HELP =
    'Il perimetro limita sia ciò che l\'agente può toccare sia ciò che può vedere: ' +
    'un\'entità fuori dall\'elenco non è solo non azionabile, non è nemmeno leggibile ' +
    'dal suo ragionamento — un agente limitato a light.cucina non può leggere ' +
    'sensor.consumo_cucina, quindi va elencato anche ciò che gli serve solo per capire. ' +
    'Se non dichiari nulla non è bloccato: resta confinato dal solo semaforo.';

  /* Pattern glob abbreviati per il picker del perimetro: task_engine
     confronta con fnmatch, quindi "light.*" e' un valore legittimo tanto
     quanto un entity_id esplicito. */
  var PERIMETER_PILLS = [
    { label: 'luci', pattern: 'light.*' },
    { label: 'switch', pattern: 'switch.*' },
    { label: 'sensori', pattern: 'sensor.*' },
    { label: 'clima', pattern: 'climate.*' },
    { label: 'tapparelle', pattern: 'cover.*' },
    { label: 'binari', pattern: 'binary_sensor.*' }
  ];

  var PERIMETER_BUDGET_TOKENS_DEFAULT = 4096;   /* = watcher/agentbots.py::_PERIMETER_BUDGET_TOKENS_DEFAULT */
  var PERIMETER_DEADLINE_MIN_DEFAULT = 5;       /* = watcher/agentbots.py::_PERIMETER_DEADLINE_MIN_DEFAULT */

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
  /* budget_tokens/deadline_min devono arrivare al validatore come INTERI
     positivi: `is_positive_int` (watcher/agentbots.py) rifiuta i float, e
     JSON.stringify(4096.5) resta "4096.5" -> float lato Python -> l'intero
     Agentbot viene rigettato. parseInt tronca, il fallback e' il default
     esplicito (mai `null`, cosi' il campo resta sempre leggibile in UI). */
  function toPosIntOr(v, fallback) {
    var x = parseInt(v, 10);
    return (isNaN(x) || x <= 0) ? fallback : x;
  }
  function defaultAgentbot() {
    return {
      id: null, name: '', enabled: true, severity: 'info', mode: 'rule',
      trigger: { type: 'event', entity_id: '', operator: '==', threshold: '' },
      reasoning: { enabled: false, model: 'auto', prompt: '' },
      action: { type: 'notify', message: '' },
      objective: '', perimeter: null
    };
  }

  /* ── stato di modulo (un solo editor Agentbot montato alla volta,
     stesso pattern di chatbot-editor.js) ──────────────────────────────── */
  var evEntityPicker = null;         /* trigger event: entità osservata */
  var schCondEntityPicker = null;    /* trigger schedule: entità della condizione opzionale */
  var actEntityPicker = null;        /* azione service: entità target */
  var perEntityPicker = null;        /* perimetro (mode=objective): entità consentite */
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

  var nameInp, severitySel, enabledChk, modeSel;
  function populateIdentita() {
    var body = document.getElementById('sc-body-identita');
    body.innerHTML = '';
    nameInp = HirisEditorKit.field.text(body, { label: 'Nome', placeholder: 'Es: Garage aperto di notte' });
    modeSel = HirisEditorKit.field.select(body, {
      id: 'ab-mode',
      label: 'Modalità',
      options: [
        { value: 'rule', label: 'Regola — scatta e fa l\'azione che dichiari' },
        { value: 'objective', label: 'Obiettivo — ragiona verso un traguardo ed emette task' }
      ],
      value: 'rule',
      hint: 'Una regola è deterministica: trigger e azione li scrivi tu. Un agente-obiettivo ragiona da solo dentro un perimetro ed emette task; gira solo su pianificazione e non dichiara un\'azione propria.'
    });
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

  var triggerTypeSel, eventWrap, scheduleWrap, scheduleOnlyNote;
  var updateTriggerVisibilityRef = null;
  var evOperator, evThreshold, evDuration;
  var schKindSel, schCron, schInterval, schCondOperator, schCondThreshold;
  function populateTrigger() {
    var body = document.getElementById('sc-body-trigger');
    body.innerHTML = '';

    if (evEntityPicker) { evEntityPicker.destroy(); evEntityPicker = null; }
    if (schCondEntityPicker) { schCondEntityPicker.destroy(); schCondEntityPicker = null; }

    triggerTypeSel = HirisEditorKit.field.select(body, {
      id: 'ab-trigger-type',
      label: 'Tipo trigger',
      options: [
        { value: 'event', label: 'Evento' },
        { value: 'schedule', label: 'Pianificazione' }
      ],
      value: 'event'
    });

    /* Mostrato solo in modalità obiettivo, al posto della scelta
       evento/pianificazione: il validatore rifiuta objective+evento
       (watcher/agentbots.py, gate cross-campo), quindi qui non c'è una
       scelta da fare -- va detto perché, non lasciato sparire in silenzio. */
    scheduleOnlyNote = el('p', 'sc-desc',
      'La modalità obiettivo gira solo su pianificazione: un turno di ragionamento è pesante, gli eventi restano dominio delle regole.');
    scheduleOnlyNote.style.display = 'none';
    body.appendChild(scheduleOnlyNote);

    /* ── Evento ── */
    eventWrap = document.createElement('div');
    eventWrap.id = 'ab-trigger-event-wrap';
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
    scheduleWrap.id = 'ab-trigger-schedule-wrap';
    schKindSel = HirisEditorKit.field.select(scheduleWrap, {
      label: 'Modalità',
      options: [
        { value: 'cron', label: 'Cron' },
        { value: 'interval', label: 'Intervallo (minuti)' }
      ],
      value: 'cron'
    });
    schCron = HirisEditorKit.field.text(scheduleWrap, { id: 'ab-trigger-cron', label: 'Cron (es. "0 7 * * *")' });
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
    /* Riferimento a livello di modulo: updateModeVisibility() deve poterla
       richiamare DIRETTAMENTE dopo aver forzato il tipo trigger, senza un
       dispatchEvent sintetico (che dirty.track leggerebbe come modifica). */
    updateTriggerVisibilityRef = updateTriggerVisibility;
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

  /* ── Obiettivo + perimetro (solo mode="objective") ──────────────────── */
  var objectiveTa, perEntitiesChk, perEntitiesWrap, perServicesChk, perServicesWrap;
  var perServicesGroup, perBudget, perDeadline;
  function populateObiettivo() {
    var body = document.getElementById('sc-body-obiettivo');
    body.innerHTML = '';

    if (perEntityPicker) { perEntityPicker.destroy(); perEntityPicker = null; }

    objectiveTa = HirisEditorKit.field.textarea(body, {
      id: 'ab-objective',
      label: 'Obiettivo',
      rows: 3,
      placeholder: 'Es: tieni sotto controllo i consumi elettrici della cucina',
      hint: 'Cosa deve ottenere l\'agente, non come. Le istruzioni operative per il ragionamento restano nella sezione Verdetto.'
    });

    body.appendChild(el('div', 'fg-label', 'Perimetro'));
    body.appendChild(el('p', 'sc-desc', PERIMETER_HELP));

    /* Interruttore + elenco, non un picker nudo: un elenco vuoto e
       "nessuna restrizione" sono OPPOSTI lungo tutta la catena (null vs [],
       vedi il commento in testa al file) e un picker vuoto da solo non sa
       dire quale dei due l'utente intendeva. */
    perEntitiesChk = HirisEditorKit.field.checkbox(body, {
      id: 'ab-per-entities-on',
      label: 'Limita le entità a un elenco'
    });
    perEntitiesWrap = document.createElement('div');
    perEntitiesWrap.appendChild(el('p', 'field-hint',
      'Spuntato: l\'agente vede e tocca solo quello che elenchi qui (elenco vuoto = niente). Non spuntato: nessuna restrizione di entità, resta il solo semaforo. Sono ammessi id espliciti e glob (light.*).'));
    var perPickerRoot = document.createElement('div');
    perPickerRoot.id = 'ab-per-entities-root';
    perEntitiesWrap.appendChild(perPickerRoot);
    perEntityPicker = HirisEntityPicker.create(perPickerRoot, {
      placeholder: 'Cerca entità…',
      pills: PERIMETER_PILLS,
      onChange: function() { if (markDirtyRef) markDirtyRef(); }
    });
    body.appendChild(perEntitiesWrap);

    perServicesChk = HirisEditorKit.field.checkbox(body, {
      id: 'ab-per-services-on',
      label: 'Limita i servizi a un elenco'
    });
    perServicesWrap = document.createElement('div');
    perServicesWrap.appendChild(el('p', 'field-hint',
      'Quali famiglie di servizi Home Assistant i task emessi dall\'agente possono chiamare. Non spuntato: nessuna restrizione di servizi, resta il solo semaforo.'));
    var perServicesRoot = document.createElement('div');
    perServicesRoot.id = 'ab-per-services-root';
    perServicesWrap.appendChild(perServicesRoot);
    perServicesGroup = HirisEditorKit.checkGroup(perServicesRoot, {
      /* ACTIONS è un global bare (config/templates.js dichiara `var ACTIONS
         = [...]` a livello top) -- stesso pattern di lettura di
         chatbot-editor.js/create-wizard.js. */
      items: (typeof ACTIONS !== 'undefined' ? ACTIONS : []),
      selected: [],
      idPrefix: 'ab-per-svc'
    });
    body.appendChild(perServicesWrap);

    /* Budget e scadenza SONO onorati (Fase 2 Task 5: l'esecuzione si ferma
       e lascia un esito leggibile). max_tier no -- per questo non c'è. */
    perBudget = HirisEditorKit.field.number(body, {
      id: 'ab-per-budget', label: 'Budget token per esecuzione', min: 1,
      value: PERIMETER_BUDGET_TOKENS_DEFAULT,
      hint: 'Tetto sui token di una singola esecuzione: superato, l\'esecuzione si ferma e lo dice.'
    });
    perDeadline = HirisEditorKit.field.number(body, {
      id: 'ab-per-deadline', label: 'Scadenza per esecuzione (minuti)', min: 1,
      value: PERIMETER_DEADLINE_MIN_DEFAULT,
      hint: 'Tempo massimo di una singola esecuzione.'
    });

    perEntitiesChk.addEventListener('change', updatePerimeterVisibility);
    perServicesChk.addEventListener('change', updatePerimeterVisibility);
    updatePerimeterVisibility();
  }

  /* Chiamata direttamente da openAgentbot (non via dispatchEvent): un
     evento sintetico su un controllo gia' agganciato da dirty.track
     segnerebbe l'editor come "modificato" per il solo fatto di aver
     CARICATO un Agentbot esistente. */
  function updatePerimeterVisibility() {
    if (perEntitiesWrap) perEntitiesWrap.style.display = perEntitiesChk.checked ? '' : 'none';
    if (perServicesWrap) perServicesWrap.style.display = perServicesChk.checked ? '' : 'none';
  }

  var reasoningChk, reasoningModelSel, reasoningLockNote;
  function populateModello() {
    var body = document.getElementById('sc-body-modello');
    body.innerHTML = '';
    reasoningChk = HirisEditorKit.field.checkbox(body, { id: 'ab-reasoning-enabled', label: 'Abilita ragionamento AI' });
    /* In modalità obiettivo il ragionamento NON è opzionale: senza,
       watcher/agentbot_runner.py::_on_wake non entra mai nel ramo che porta
       identità e perimetro a run_decision -- l'agente cadrebbe sul percorso
       deterministico e non emetterebbe alcun task. La casella resta visibile
       (l'utente vede cosa sta succedendo) ma bloccata, con il motivo. */
    reasoningLockNote = el('p', 'field-hint',
      'In modalità obiettivo il ragionamento è sempre attivo: è l\'agente stesso. Senza, non ci sarebbe nulla che ragiona verso l\'obiettivo.');
    reasoningLockNote.style.display = 'none';
    body.appendChild(reasoningLockNote);
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

  /* ── ramo modalità: cosa si vede in "regola" e cosa in "obiettivo" ──── */

  function setSectionVisible(sectionId, visible) {
    var sec = document.getElementById('sec-' + sectionId);
    if (sec) sec.style.display = visible ? '' : 'none';
    /* Anche la voce dell'anchor-nav: una sezione nascosta con il suo link
       ancora nel rail manda l'utente su una scheda invisibile. */
    var link = document.querySelector('.anchor-link[href="#sec-' + sectionId + '"]');
    if (link) link.style.display = visible ? '' : 'none';
  }

  function isObjectiveMode() { return modeSel && modeSel.value === 'objective'; }

  function updateModeVisibility() {
    var objective = isObjectiveMode();

    setSectionVisible('obiettivo', objective);
    /* L'azione dichiarata non esiste in modalità obiettivo: il validatore
       rigetta un Agentbot objective che ne porti una (le azioni nascono a
       valle come Task, confinati dal perimetro). */
    setSectionVisible('azione', !objective);

    /* Trigger: objective ammette SOLO la pianificazione. La scelta
       evento/pianificazione sparisce (non c'è nulla da scegliere) e al suo
       posto compare il motivo. */
    if (triggerTypeSel) {
      if (objective) triggerTypeSel.value = 'schedule';
      if (triggerTypeSel.parentNode) triggerTypeSel.parentNode.style.display = objective ? 'none' : '';
      if (updateTriggerVisibilityRef) updateTriggerVisibilityRef();
    }
    if (scheduleOnlyNote) scheduleOnlyNote.style.display = objective ? '' : 'none';

    if (reasoningChk) {
      if (objective) reasoningChk.checked = true;
      reasoningChk.disabled = objective;
    }
    if (reasoningLockNote) reasoningLockNote.style.display = objective ? '' : 'none';
  }

  /* ── payload / open / save ───────────────────────────────────────── */

  function openAgentbot(a) {
    nameInp.value = a.name || '';
    severitySel.value = a.severity || 'info';
    enabledChk.checked = !!a.enabled;
    modeSel.value = a.mode === 'objective' ? 'objective' : 'rule';

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

    /* Obiettivo + perimetro. La lettura rispetta la stessa convenzione
       della scrittura: un ARRAY (anche vuoto) = limite dichiarato ->
       interruttore acceso; `null`/assente = nessuna restrizione ->
       interruttore spento. Collassare i due casi qui riaprirebbe dal lato
       carico esattamente il buco che buildPerimeter() chiude in scrittura. */
    objectiveTa.value = a.objective || '';
    var per = a.perimeter || {};
    var perEntities = per.allowed_entities;
    perEntitiesChk.checked = Array.isArray(perEntities);
    if (perEntityPicker) perEntityPicker.setValue(Array.isArray(perEntities) ? perEntities : []);
    var perServices = per.allowed_services;
    perServicesChk.checked = Array.isArray(perServices);
    if (perServicesGroup) perServicesGroup.setSelected(Array.isArray(perServices) ? perServices : []);
    perBudget.value = per.budget_tokens != null ? per.budget_tokens : PERIMETER_BUDGET_TOKENS_DEFAULT;
    perDeadline.value = per.deadline_min != null ? per.deadline_min : PERIMETER_DEADLINE_MIN_DEFAULT;
    updatePerimeterVisibility();

    updateModeVisibility();

    var btnDel = document.getElementById('btn-delete');
    if (btnDel) btnDel.style.display = a.id ? '' : 'none';

    populateOsservabilita(a.id);
  }

  function initNewAgentbot() {
    var empty = defaultAgentbot();
    openAgentbot(empty);
  }

  /* TRAPPOLA null-vs-[] (vedi commento in testa al file): l'interruttore
     spento significa "non ho dichiarato restrizioni su quest'asse" e deve
     viaggiare come `null` -- MAI come `[]`, che lungo tutta la catena
     significa l'opposto ("nega tutto") e farebbe nascere paralizzato ogni
     agente creato senza selezione: leggerebbe tutto ma ogni Task emesso
     verrebbe rifiutato in esecuzione da task_engine._run_action.
     L'interruttore acceso manda l'elenco così com'è, vuoto compreso: quella
     è una negazione VOLUTA e deve restare rappresentabile.

     `max_tier` non compare: non è onorato da nessun runtime (debito noto
     della fase). Assente -> il validatore mette "green", il default più
     stretto; esposto, sarebbe un controllo che promette e non mantiene. */
  function buildPerimeter() {
    return {
      allowed_entities: perEntitiesChk.checked
        ? (perEntityPicker ? perEntityPicker.getValue() : [])
        : null,
      allowed_services: perServicesChk.checked
        ? (perServicesGroup ? perServicesGroup.getSelected() : [])
        : null,
      budget_tokens: toPosIntOr(perBudget.value, PERIMETER_BUDGET_TOKENS_DEFAULT),
      deadline_min: toPosIntOr(perDeadline.value, PERIMETER_DEADLINE_MIN_DEFAULT)
    };
  }

  function buildPayload() {
    /* `mode` è ESPLICITO anche per una regola: la whitelist di questo
       builder è costruita da zero, e un `mode` omesso significherebbe
       affidarsi al default del validatore -- che per una regola è corretto,
       ma per un agente-obiettivo lo riconvertirebbe in regola in silenzio.
       Un solo punto in cui la modalità viene decisa, per entrambe. */
    var mode = isObjectiveMode() ? 'objective' : 'rule';
    var payload = {
      name: nameInp.value,
      enabled: enabledChk.checked,
      severity: severitySel.value,
      mode: mode
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

    /* I tre campi per-modalità sono mutuamente esclusivi PER COSTRUZIONE
       (un solo ramo li scrive), non per convenzione: validate_agentbot
       rigetta l'intero Agentbot se un objective porta `action`, o se una
       regola porta `objective`/`perimeter`. */
    if (mode === 'objective') {
      payload.objective = objectiveTa.value;
      payload.perimeter = buildPerimeter();
      return payload;
    }

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
        /* Pulisce 'unsaved' oltre allo stato dell'entità (finding I2):
           senza, un editor lasciato dirty prima di premere Elimina fa
           chiedere al guard "Ci sono modifiche non salvate…" subito dopo
           un'eliminazione riuscita -- non c'è più nulla da salvare. */
        HirisState.set('activeAgentbotId', null);
        HirisState.set('unsaved', false);
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

    /* HirisEditorKit.dirty.track() è ora un singleton a livello di kit
       (review finale pre-1.0, finding C1): ferma da sé qualunque tracker
       precedente, anche se installato da un editor di TIPO diverso --
       niente più handle locale da tenere/fermare qui. */
    HirisEditorKit.dirty.track(outlet, markDirty);
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
        /* Pulisce 'unsaved' PRIMA di cambiare hash (finding I2): l'utente
           ha già confermato lo scarto qui sopra -- senza, il guard
           installato in main.js vede lo stesso 'unsaved' ancora true sul
           hashchange che questa riga genera e chiede conferma UNA SECONDA
           volta, a vuoto, per una scelta già fatta. */
        HirisState.set('unsaved', false);
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
      step('populateObiettivo', populateObiettivo);
      step('populateModello', populateModello);
      step('populateVerdetto', populateVerdetto);
      step('populateAzione', populateAzione);
      step('populateStato', populateStato);
      step('setupAnchorNav', setupAnchorNav);
      /* Il ramo modalità si aggancia DOPO che tutte le populate*() hanno
         creato i controlli che deve mostrare/nascondere (trigger, azione,
         ragionamento) -- non dentro populateIdentita, che gira per prima e
         non li vedrebbe ancora. */
      step('wireMode', function() {
        modeSel.addEventListener('change', updateModeVisibility);
        updateModeVisibility();
      });

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
