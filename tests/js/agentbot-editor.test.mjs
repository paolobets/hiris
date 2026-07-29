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
  return Array.from(document.querySelectorAll('.ep-search'));
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

  const chipsContainers = Array.from(document.querySelectorAll('.ep-chips'));
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

  const triggerBody = document.getElementById('sc-body-trigger');
  const eventWrap = triggerBody.children[1];
  const scheduleWrap = triggerBody.children[2];
  assert.ok(eventWrap && scheduleWrap, 'il DOM del trigger deve avere i due wrap evento/pianificazione');

  assert.notEqual(eventWrap.style.display, 'none', 'di default il trigger è "evento": i suoi campi sono visibili');
  assert.equal(scheduleWrap.style.display, 'none', 'i campi di pianificazione sono nascosti finché non selezionata');

  const triggerTypeSel = triggerBody.querySelector('select');
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
    ['action', 'enabled', 'name', 'reasoning', 'severity', 'trigger'].sort(),
    'esattamente i campi che watcher/agentbots.py::validate_agentbot accetta -- niente id nel body (create sempre fresh)'
  );
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

  const [, condInput, targetInput] = pickerSearchInputs(document);
  const chipsContainers = Array.from(document.querySelectorAll('.ep-chips'));
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
