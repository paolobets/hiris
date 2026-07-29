import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 5: editor Agentbot per-entità, estratto dal blocco CRUD
   che viveva dentro agentbot-route.js (grounding A5, blocco 4). Costruito
   sul kit condiviso (HirisEditorKit, Task 3 -- field.* reintrodotte QUI
   come loro primo consumatore reale) e sul componente entità istanziabile
   (HirisEntityPicker, Task 1): ogni regola ne usa TRE istanze indipendenti
   (entità trigger, entità condizione schedule, entità target azione) --
   MAI lo slot singleton window.HirisAgentEntityPicker introdotto come
   bridge nel Task 1 (qui non esiste: niente altro lo consuma).

   Test comportamentali richiesti dal piano (riga "5 editor Agentbot"):
     - tre picker indipendenti in una riga non si interferiscono;
     - passare da trigger event a schedule mostra/nasconde i campi giusti;
     - il payload salvato ha la forma accettata da validate_agentbot
       (watcher/agentbots.py), con l'azione DICHIARATA (mai dall'LLM). */

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <template id="tpl-agent-editor">
    <div class="editor-grid">
      <div class="editor-content">
        <div class="sticky-actions-wrap" id="sticky-actions-wrap">
          <div class="sticky-actions" id="sticky-actions">
            <button class="btn btn-ghost" id="btn-cancel">Annulla</button>
            <button class="btn" id="btn-test-run">Test Run</button>
            <button class="btn btn-danger" id="btn-delete" style="display:none">Elimina</button>
            <button class="btn btn-primary" id="btn-save" disabled>Salva</button>
          </div>
        </div>
      </div>
      <aside class="anchor-nav" id="anchor-nav"></aside>
    </div>
  </template>
</body>`;

const SCRIPTS = [
  'config/state.js',
  'config/api.js',
  'config/entity-picker.js',
  'config/editor-kit.js',
  // Agenti v1.1 Fase 2 Task 6: il perimetro della modalita' obiettivo legge
  // il catalogo ACTIONS (global bare di templates.js, come fanno gia'
  // chatbot-editor.js e create-wizard.js). config.html lo carica prima
  // dell'editor (riga 194 vs 222): la lista qui rispecchia quell'ordine.
  'config/templates.js',
  'config/agentbot-editor.js',
];

function setup(extraRoutes) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  const calls = stubFetch(ctx.window, Object.assign({
    'api/models': { providers: [] },
  }, extraRoutes || {}));
  return { ...ctx, calls };
}

function pickerSearchInputs(document) {
  // Ordine DOM garantito da buildSections()/SECTIONS: sec-trigger (evento
  // poi condizione schedule) viene prima di sec-azione (target).
  //
  // Agenti v1.1 Fase 2 Task 6: la query e' SCOPED alle due sezioni che
  // possiedono i tre picker della REGOLA. Prima era un
  // querySelectorAll('.ep-search') su tutto il documento, che ora
  // pescherebbe anche il quarto picker (il perimetro della modalita'
  // obiettivo, sezione "obiettivo", montato sempre anche se nascosto in
  // modalita' regola) -- rendendo "esattamente tre" falso e spostando gli
  // indici dei chip. Lo scope tiene il significato originale del test
  // ("i picker della regola non si contaminano fra loro") indipendente da
  // quanti altri picker esistano altrove nella pagina.
  return [].concat(
    Array.from(document.getElementById('sc-body-trigger').querySelectorAll('.ep-search')),
    Array.from(document.getElementById('sc-body-azione').querySelectorAll('.ep-search')),
  );
}

function ruleChipsContainers(document) {
  return [].concat(
    Array.from(document.getElementById('sc-body-trigger').querySelectorAll('.ep-chips')),
    Array.from(document.getElementById('sc-body-azione').querySelectorAll('.ep-chips')),
  );
}

function addChip(window, input, value) {
  input.value = value;
  // entity-picker.js legge e.key === 'Enter' -- serve un vero KeyboardEvent
  // (un Event generico non popola .key).
  input.dispatchEvent(new window.KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter' }));
}

test('i tre picker (trigger evento, condizione schedule, target azione) hanno stato indipendente', async () => {
  const { window, document } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  const inputs = pickerSearchInputs(document);
  assert.equal(inputs.length, 3, 'devono esistere esattamente tre ricerche picker (trigger/condizione/target)');
  const [evInput, condInput, targetInput] = inputs;

  addChip(window, evInput, 'binary_sensor.garage');
  addChip(window, condInput, 'sun.sun');
  addChip(window, targetInput, 'notify.mobile_app');

  const chipsContainers = ruleChipsContainers(document);
  const texts = chipsContainers.map((c) => c.textContent);

  assert.match(texts[0], /binary_sensor\.garage/);
  assert.doesNotMatch(texts[0], /sun\.sun|notify\.mobile_app/, 'il picker trigger non deve vedere i valori degli altri due');

  assert.match(texts[1], /sun\.sun/);
  assert.doesNotMatch(texts[1], /binary_sensor\.garage|notify\.mobile_app/, 'il picker condizione non deve vedere i valori degli altri due');

  assert.match(texts[2], /notify\.mobile_app/);
  assert.doesNotMatch(texts[2], /binary_sensor\.garage|sun\.sun/, 'il picker target non deve vedere i valori degli altri due');
});

test('passare da trigger evento a pianificazione mostra/nasconde i campi giusti (e viceversa)', async () => {
  const { window, document } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  // Agganciati per id, non per posizione fra i figli: la sezione trigger ha
  // guadagnato una nota (visibile solo in modalita' obiettivo) e un indice
  // posizionale la rincorrerebbe a ogni ritocco del markup.
  const eventWrap = document.getElementById('ab-trigger-event-wrap');
  const scheduleWrap = document.getElementById('ab-trigger-schedule-wrap');
  assert.ok(eventWrap && scheduleWrap, 'il DOM del trigger deve avere i due wrap evento/pianificazione');

  assert.notEqual(eventWrap.style.display, 'none', 'di default il trigger è "evento": i suoi campi sono visibili');
  assert.equal(scheduleWrap.style.display, 'none', 'i campi di pianificazione sono nascosti finché non selezionata');

  const triggerTypeSel = document.getElementById('ab-trigger-type');
  triggerTypeSel.value = 'schedule';
  triggerTypeSel.dispatchEvent(new window.Event('change', { bubbles: true }));

  assert.equal(eventWrap.style.display, 'none', 'passando a pianificazione i campi evento si nascondono');
  assert.notEqual(scheduleWrap.style.display, 'none', 'i campi di pianificazione diventano visibili');

  triggerTypeSel.value = 'event';
  triggerTypeSel.dispatchEvent(new window.Event('change', { bubbles: true }));

  assert.notEqual(eventWrap.style.display, 'none', 'tornando a evento i suoi campi ricompaiono');
  assert.equal(scheduleWrap.style.display, 'none', 'i campi di pianificazione tornano nascosti');
});

test('payload salvato (azione notify): forma accettata da validate_agentbot, azione dichiarata', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  document.getElementById('sc-body-identita').querySelector('input[type="text"]').value = 'Garage aperto di notte';

  const [evInput] = pickerSearchInputs(document);
  addChip(window, evInput, 'binary_sensor.garage');

  const triggerBody = document.getElementById('sc-body-trigger');
  const [, evOperator] = triggerBody.querySelectorAll('select');
  evOperator.value = '==';
  const evThreshold = triggerBody.querySelectorAll('input[type="text"]')[1]; // [0] è il search del picker
  evThreshold.value = 'on';

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  assert.ok(postCall, 'un Agentbot nuovo deve fare POST su api/agentbots');
  assert.equal(postCall.opts.headers['X-Requested-With'], 'fetch');

  const body = JSON.parse(postCall.opts.body);
  assert.deepEqual(
    Object.keys(body).sort(),
    ['action', 'enabled', 'mode', 'name', 'reasoning', 'severity', 'trigger'].sort(),
    'esattamente i campi che watcher/agentbots.py::validate_agentbot accetta -- niente id nel body (create sempre fresh)'
  );
  // Agenti v1.1 Fase 2 Task 6: `mode` e' ora ESPLICITO anche per le regole.
  // Il record salvato resta identico (validate_agentbot fa gia' default
  // "rule" quando la chiave e' assente), ma dichiararlo rende impossibile
  // che una futura riorganizzazione di buildPayload lo perda per strada.
  assert.equal(body.mode, 'rule');
  assert.equal('objective' in body, false, 'una regola non dichiara mai un obiettivo (validate_agentbot la rigetterebbe)');
  assert.equal('perimeter' in body, false, 'il perimetro e\' VIETATO in mode="rule": mandarlo fa rigettare l\'Agentbot');
  assert.equal(body.name, 'Garage aperto di notte');
  assert.equal(body.trigger.type, 'event');
  assert.equal(body.trigger.entity_id, 'binary_sensor.garage', 'il valore deve venire dal picker istanziabile, non da un campo testo libero');
  assert.equal(body.trigger.operator, '==');
  assert.equal(body.trigger.threshold, 'on');
  // Azione DICHIARATA in config -- mai un campo che il ragionamento AI possa scegliere.
  assert.deepEqual(body.action, { type: 'notify', message: '' });
  assert.equal(body.reasoning.enabled, false);
});

test('payload salvato (azione service): domain/service/entity_id dichiarati, entity_id dal picker target', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  const azioneBody = document.getElementById('sc-body-azione');
  const actionTypeSel = azioneBody.querySelector('select');
  actionTypeSel.value = 'service';
  actionTypeSel.dispatchEvent(new window.Event('change', { bubbles: true }));

  const textInputs = azioneBody.querySelectorAll('input[type="text"]');
  // [0] = dominio, [1] = servizio, [2] = ricerca del picker target (letto sotto via chip)
  textInputs[0].value = 'switch';
  textInputs[1].value = 'turn_off';

  const targetInput = pickerSearchInputs(document)[2];
  addChip(window, targetInput, 'switch.cancello');

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  const body = JSON.parse(postCall.opts.body);
  assert.deepEqual(body.action, {
    type: 'service', domain: 'switch', service: 'turn_off', entity_id: 'switch.cancello',
  });
});

test('caricare un Agentbot esistente ripopola i tre picker con i rispettivi valori (round-trip di carico)', async () => {
  const AGENTBOT = {
    id: 'ab0123456789',
    name: 'Rientro sole',
    enabled: true,
    severity: 'warn',
    trigger: {
      type: 'schedule',
      cron: '0 7 * * *',
      condition: { entity_id: 'sun.sun', operator: '==', threshold: 'above_horizon' },
    },
    reasoning: { enabled: true, model: 'auto', prompt: 'valuta se è nuvoloso' },
    action: { type: 'service', domain: 'cover', service: 'close_cover', entity_id: 'cover.living' },
  };
  const { window, document, calls } = setup({
    'api/agentbots': { agentbots: [AGENTBOT] },
  });

  window.HirisState.set('activeAgentbotId', 'ab0123456789');
  window.HirisAgentbotEditor.mount('ab0123456789');
  await tick(30);

  const chipsContainers = ruleChipsContainers(document);
  assert.match(chipsContainers[1].textContent, /sun\.sun/, 'il picker condizione deve riportare il valore caricato');
  assert.match(chipsContainers[2].textContent, /cover\.living/, 'il picker target deve riportare il valore caricato, indipendente dal picker condizione');
  assert.doesNotMatch(chipsContainers[1].textContent, /cover\.living/);

  await window.saveAgentbot();
  await tick(10);

  const putCall = calls.find((c) => c.url === 'api/agentbots/ab0123456789' && c.opts && c.opts.method === 'PUT');
  assert.ok(putCall, 'un Agentbot esistente deve fare PUT su api/agentbots/<id>');
  const body = JSON.parse(putCall.opts.body);
  assert.equal(body.trigger.condition.entity_id, 'sun.sun');
  assert.equal(body.action.entity_id, 'cover.living');
});

test('modificare il Nome (campo dal kit field.text) abilita il bottone Salva', async () => {
  const { window, document } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  const btnSave = document.getElementById('btn-save');
  assert.equal(btnSave.disabled, true, 'appena montato, senza modifiche, Salva resta disabled');

  const nameInput = document.getElementById('sc-body-identita').querySelector('input[type="text"]');
  nameInput.value = 'Nuovo nome';
  nameInput.dispatchEvent(new window.Event('input', { bubbles: true }));

  assert.equal(btnSave.disabled, false, 'un campo del kit (field.text, un vero <input>) deve marcare dirty via dirty.track');
});

/* ────────────────────────────────────────────────────────────────────────
   Agenti v1.1 Fase 2 Task 6 — modalita' obiettivo nell'editor.

   Un Agentbot ha due modalita' (watcher/agentbots.py::validate_agentbot):
     - mode="rule": trigger (evento o pianificazione) + AZIONE dichiarata;
       `objective` e `perimeter` sono VIETATI (presenti -> rigetto).
     - mode="objective": `objective` non vuoto + `perimeter` sempre
       materializzato; `action` VIETATA; trigger a evento VIETATO (solo
       pianificazione -- la modalita' obiettivo costa un turno LLM).

   Convenzione del perimetro, unica in tutta la catena (_validate_str_list):
   `null` = NESSUNA restrizione su quell'asse; `[]` = NEGA TUTTO. Sono
   opposti. Una selezione vuota nella UI significa "non ho dichiarato
   restrizioni" -> deve viaggiare come `null`, MAI come `[]`, altrimenti
   ogni agente creato senza selezione nascerebbe paralizzato.
   ──────────────────────────────────────────────────────────────────────── */

function selectObjectiveMode(window, document) {
  const modeSel = document.getElementById('ab-mode');
  modeSel.value = 'objective';
  modeSel.dispatchEvent(new window.Event('change', { bubbles: true }));
  return modeSel;
}

test('modalita\' obiettivo: mostra obiettivo + perimetro, nasconde trigger-evento e azione', async () => {
  const { window, document } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  const secObiettivo = document.getElementById('sec-obiettivo');
  const secAzione = document.getElementById('sec-azione');
  assert.ok(secObiettivo, 'deve esistere una sezione per obiettivo + perimetro');
  assert.equal(secObiettivo.style.display, 'none', 'in modalita\' regola la sezione obiettivo resta nascosta');
  assert.notEqual(secAzione.style.display, 'none', 'in modalita\' regola l\'azione dichiarata e\' visibile');

  selectObjectiveMode(window, document);

  assert.notEqual(secObiettivo.style.display, 'none', 'scegliendo obiettivo la sezione obiettivo+perimetro compare');
  assert.equal(secAzione.style.display, 'none', 'in modalita\' obiettivo l\'azione dichiarata sparisce (le azioni nascono come Task)');

  const triggerBody = document.getElementById('sc-body-trigger');
  const triggerTypeSel = document.getElementById('ab-trigger-type');
  const eventWrap = document.getElementById('ab-trigger-event-wrap');
  const scheduleWrap = document.getElementById('ab-trigger-schedule-wrap');
  assert.equal(eventWrap.style.display, 'none', 'la modalita\' obiettivo non ammette un trigger a evento');
  assert.notEqual(scheduleWrap.style.display, 'none', 'resta la sola pianificazione');
  assert.equal(triggerTypeSel.value, 'schedule', 'il tipo trigger e\' forzato a pianificazione');
  assert.equal(triggerTypeSel.parentNode.style.display, 'none', 'la scelta evento/pianificazione non ha senso qui: sparisce');
  assert.ok(triggerBody.textContent.includes('pianificazione'), 'la UI deve spiegare perche\' l\'evento non c\'e\' piu\'');

  // Tornando a regola, tutto ricompare com'era.
  const modeSel = document.getElementById('ab-mode');
  modeSel.value = 'rule';
  modeSel.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(secObiettivo.style.display, 'none');
  assert.notEqual(secAzione.style.display, 'none');
  assert.notEqual(triggerTypeSel.parentNode.style.display, 'none');
});

test('la UI dice esplicitamente che il perimetro limita anche la LETTURA, non solo l\'azione', async () => {
  const { window, document } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);
  selectObjectiveMode(window, document);

  const testo = document.getElementById('sc-body-obiettivo').textContent;
  assert.match(testo, /sia ciò che l'agente può toccare sia ciò che può vedere/,
    'il perimetro governa la lettura oltre che l\'azione: l\'utente deve leggerlo, non scoprirlo dopo');
  assert.match(testo, /non è nemmeno leggibile/,
    'va detto che un\'entità fuori perimetro non è solo non azionabile: è invisibile al ragionamento');
  assert.match(testo, /confinato dal solo semaforo/,
    'non dichiarare nulla significa «confinato dal solo semaforo», non «bloccato»');
});

test('payload obiettivo: mode/objective/perimeter presenti, NESSUN action', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  document.getElementById('sc-body-identita').querySelector('input[type="text"]').value = 'Consumi cucina';
  selectObjectiveMode(window, document);
  document.getElementById('ab-objective').value = 'tieni sotto controllo i consumi della cucina';
  document.getElementById('ab-trigger-cron').value = '0 7 * * *';

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  assert.ok(postCall, 'un agente nuovo deve fare POST su api/agentbots');
  const body = JSON.parse(postCall.opts.body);

  assert.deepEqual(
    Object.keys(body).sort(),
    ['enabled', 'mode', 'name', 'objective', 'perimeter', 'reasoning', 'severity', 'trigger'].sort(),
    'esattamente i campi che validate_agentbot accetta per mode="objective"',
  );
  assert.equal(body.mode, 'objective');
  assert.equal(body.objective, 'tieni sotto controllo i consumi della cucina');
  assert.equal('action' in body, false, 'un\'azione dichiarata in modalita\' obiettivo fa RIGETTARE l\'agente dal validatore');
  assert.equal(body.trigger.type, 'schedule');
  assert.equal(body.trigger.cron, '0 7 * * *');
  assert.equal(body.reasoning.enabled, true, 'senza ragionamento un agente-obiettivo e\' inerte: agentbot_runner._on_wake non entra mai nel ramo con perimetro');
});

test('TRAPPOLA null-vs-[]: perimetro non dichiarato viaggia come null, MAI come []', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  selectObjectiveMode(window, document);
  document.getElementById('ab-objective').value = 'valuta i consumi';
  document.getElementById('ab-trigger-cron').value = '0 7 * * *';

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  const raw = postCall.opts.body;
  const body = JSON.parse(raw);

  assert.strictEqual(body.perimeter.allowed_entities, null,
    'nessuna selezione = NESSUNA restrizione (null). Un [] qui significherebbe "nega tutto" e l\'agente nascerebbe paralizzato');
  assert.strictEqual(body.perimeter.allowed_services, null,
    'idem per i servizi: null = nessuna restrizione, [] = nega tutto');
  assert.equal(/"allowed_entities":\s*\[\s*\]/.test(raw), false, 'nel JSON serializzato non deve comparire un array vuoto');
  assert.equal(/"allowed_services":\s*\[\s*\]/.test(raw), false, 'nel JSON serializzato non deve comparire un array vuoto');
  // Budget/scadenza sono interi positivi (is_positive_int rifiuta i float).
  assert.equal(Number.isInteger(body.perimeter.budget_tokens), true);
  assert.equal(Number.isInteger(body.perimeter.deadline_min), true);
});

test('«nega tutto» resta rappresentabile: limite attivo con elenco vuoto manda [] (non null)', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  selectObjectiveMode(window, document);
  document.getElementById('ab-objective').value = 'valuta i consumi';
  document.getElementById('ab-trigger-cron').value = '0 7 * * *';
  // L'utente attiva esplicitamente il limite ma non elenca nulla: "non
  // concedere niente" -- opposto di "nessuna restrizione".
  document.getElementById('ab-per-entities-on').checked = true;
  document.getElementById('ab-per-services-on').checked = true;

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  const body = JSON.parse(postCall.opts.body);
  assert.deepEqual(body.perimeter.allowed_entities, [], 'limite attivo + elenco vuoto = nega tutto');
  assert.deepEqual(body.perimeter.allowed_services, []);
});

test('perimetro dichiarato: le entita\' selezionate finiscono in allowed_entities', async () => {
  const { window, document, calls } = setup();
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  selectObjectiveMode(window, document);
  document.getElementById('ab-objective').value = 'valuta i consumi della cucina';
  document.getElementById('ab-trigger-cron').value = '0 7 * * *';
  document.getElementById('ab-per-entities-on').checked = true;
  document.getElementById('ab-per-entities-on').dispatchEvent(new window.Event('change', { bubbles: true }));

  const perInput = document.getElementById('ab-per-entities-root').querySelector('.ep-search');
  addChip(window, perInput, 'light.cucina');
  addChip(window, perInput, 'sensor.consumo_cucina');

  await window.saveAgentbot();
  await tick(10);

  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  const body = JSON.parse(postCall.opts.body);
  assert.deepEqual(body.perimeter.allowed_entities, ['light.cucina', 'sensor.consumo_cucina']);
});

test('round-trip: un agente-obiettivo caricato ripopola modalita\', obiettivo e perimetro e si risalva uguale', async () => {
  const OBJECTIVE_BOT = {
    id: 'ob0123456789',
    name: 'Consumi cucina',
    enabled: true,
    severity: 'warn',
    mode: 'objective',
    objective: 'tieni sotto controllo i consumi della cucina',
    trigger: { type: 'schedule', cron: '0 7 * * *' },
    reasoning: { enabled: true, model: 'auto', prompt: 'valuta i consumi' },
    action: null,
    perimeter: {
      allowed_entities: ['light.cucina', 'sensor.consumo_cucina'],
      allowed_services: ['light.*'],
      max_tier: 'green',
      budget_tokens: 2048,
      deadline_min: 3,
    },
  };
  const { window, document, calls } = setup({ 'api/agentbots': { agentbots: [OBJECTIVE_BOT] } });

  window.HirisState.set('activeAgentbotId', 'ob0123456789');
  window.HirisAgentbotEditor.mount('ob0123456789');
  await tick(30);

  assert.equal(document.getElementById('ab-mode').value, 'objective');
  assert.equal(document.getElementById('ab-objective').value, 'tieni sotto controllo i consumi della cucina');
  assert.equal(document.getElementById('ab-per-entities-on').checked, true, 'un elenco presente = limite ATTIVO');
  assert.match(document.getElementById('ab-per-entities-root').textContent, /sensor\.consumo_cucina/);
  assert.equal(document.getElementById('ab-per-budget').value, '2048');
  assert.equal(document.getElementById('ab-per-deadline').value, '3');
  assert.equal(document.getElementById('sec-azione').style.display, 'none');

  await window.saveAgentbot();
  await tick(10);

  const putCall = calls.find((c) => c.url === 'api/agentbots/ob0123456789' && c.opts && c.opts.method === 'PUT');
  assert.ok(putCall, 'un agente esistente deve fare PUT su api/agentbots/<id>');
  const body = JSON.parse(putCall.opts.body);
  assert.equal(body.mode, 'objective', 'TRAPPOLA buildPayload: un salvataggio dalla SPA non deve riconvertire l\'agente in regola');
  assert.equal('action' in body, false);
  assert.equal(body.objective, 'tieni sotto controllo i consumi della cucina');
  assert.deepEqual(body.perimeter.allowed_entities, ['light.cucina', 'sensor.consumo_cucina']);
  assert.deepEqual(body.perimeter.allowed_services, ['light.*']);
  assert.equal(body.perimeter.budget_tokens, 2048);
  assert.equal(body.perimeter.deadline_min, 3);
});

test('NON-REGRESSIONE: una regola esistente aperta e risalvata resta una regola identica', async () => {
  const RULE_BOT = {
    id: 'ab0123456789',
    name: 'Rientro sole',
    enabled: true,
    severity: 'warn',
    mode: 'rule',
    objective: null,
    perimeter: null,
    trigger: {
      type: 'schedule',
      cron: '0 7 * * *',
      condition: { entity_id: 'sun.sun', operator: '==', threshold: 'above_horizon' },
    },
    reasoning: { enabled: true, model: 'auto', prompt: 'valuta se è nuvoloso' },
    action: { type: 'service', domain: 'cover', service: 'close_cover', entity_id: 'cover.living' },
  };
  const { window, document, calls } = setup({ 'api/agentbots': { agentbots: [RULE_BOT] } });

  window.HirisState.set('activeAgentbotId', 'ab0123456789');
  window.HirisAgentbotEditor.mount('ab0123456789');
  await tick(30);

  assert.equal(document.getElementById('ab-mode').value, 'rule');
  assert.equal(document.getElementById('sec-obiettivo').style.display, 'none');

  await window.saveAgentbot();
  await tick(10);

  const putCall = calls.find((c) => c.url === 'api/agentbots/ab0123456789' && c.opts && c.opts.method === 'PUT');
  const body = JSON.parse(putCall.opts.body);
  assert.deepEqual(
    Object.keys(body).sort(),
    ['action', 'enabled', 'mode', 'name', 'reasoning', 'severity', 'trigger'].sort(),
    'una regola non guadagna ne\' objective ne\' perimeter -- entrambi la farebbero RIGETTARE',
  );
  assert.equal(body.mode, 'rule');
  assert.deepEqual(body.action, { type: 'service', domain: 'cover', service: 'close_cover', entity_id: 'cover.living' });
  assert.deepEqual(body.trigger, RULE_BOT.trigger);
  assert.equal(body.severity, 'warn');
  assert.equal(body.enabled, true);
  assert.equal(body.reasoning.enabled, true);
  assert.equal(body.reasoning.prompt, 'valuta se è nuvoloso');
});
