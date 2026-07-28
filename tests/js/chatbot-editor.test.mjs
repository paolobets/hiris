import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 4: editor Chatbot ricostruito sul kit (HirisEditorKit,
   Task 3) + il picker istanziabile (HirisEntityPicker, Task 1), con
   chatbot-form.js assorbito (unico owner di load+payload) e knowledge_access
   finalmente esposto in UI. Test comportamentali richiesti dal piano (riga
   "4 editor Chatbot" della tabella "Test comportamentali richiesti per
   task"):
     - caricato un chatbot, il payload di save contiene esattamente i campi
       attesi, incluso knowledge_access;
     - modificare un chip abilita Salva;
     - Annulla con modifiche non salvate chiede conferma. */

// Frammento minimo di config.html (SP-4 Fase B Task 4: le section-card non
// sono più hardcoded nel template -- chatbot-editor.js le genera da
// SECTIONS/buildSections(), vedi anche tests/js/loader-collapse.test.mjs).
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
  'config/templates.js',
  'config/permessi.js',
  'config/log-row.js',
  'config/logs.js',
  'config/usage.js',
  'config/proposals.js',
  'config/chatbot-editor.js',
];

const AGENT = {
  id: 'agent-1',
  name: 'Assistente Cucina',
  system_prompt: 'rispondi in italiano',
  strategic_context: 'casa con 2 adulti',
  allowed_tools: ['get_entity_states'],
  allowed_entities: ['light.cucina'],
  allowed_services: [],
  model: 'auto',
  max_tokens: 4096,
  restrict_to_home: false,
  require_confirmation: false,
  enabled: true,
  max_chat_turns: 0,
  response_mode: 'auto',
  thinking_budget: 0,
  knowledge_access: { allow_sensitive: true, kinds: ['fact', 'note'] },
  is_default: false,
};

const EXPECTED_PAYLOAD_KEYS = [
  'allowed_entities', 'allowed_services', 'allowed_tools', 'enabled',
  'knowledge_access', 'max_chat_turns', 'max_tokens', 'model', 'name',
  'require_confirmation', 'response_mode', 'restrict_to_home',
  'strategic_context', 'system_prompt', 'thinking_budget',
].sort();

function setup(extraRoutes) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  const calls = stubFetch(ctx.window, Object.assign({
    'api/models': { providers: [] },
    'api/gateway': { categories: [], levels: {}, entities: {} },
    'usage': { requests: 0, input_tokens: 0, output_tokens: 0 },
    'context-preview': { context_str: '', token_estimate: 0 },
    'api/chatbots/agent-1': AGENT,
    'api/chatbots': [AGENT],
  }, extraRoutes || {}));
  return { ...ctx, calls };
}

test('caricare un chatbot poi salvare produce un payload con esattamente i campi attesi, incluso knowledge_access', async () => {
  const { window, calls } = setup();

  // Come fa main.js (router) prima di mount(): scrive activeChatbotId,
  // l'editor lo legge soltanto (contratto C9 -- un solo writer).
  window.HirisState.set('activeChatbotId', 'agent-1');
  window.HirisChatbotEditor.mount('agent-1');
  await tick(30);

  await window.saveAgent();
  await tick(10);

  const putCall = calls.find((c) => c.url === 'api/chatbots/agent-1' && c.opts && c.opts.method === 'PUT');
  assert.ok(putCall, 'saveAgent() con un chatbot già caricato deve fare una PUT su api/chatbots/<id>');
  assert.equal(putCall.opts.headers['X-Requested-With'], 'fetch');

  const body = JSON.parse(putCall.opts.body);
  assert.deepEqual(
    Object.keys(body).sort(),
    EXPECTED_PAYLOAD_KEYS,
    'il payload deve contenere esattamente questi campi -- non uno in meno (knowledge_access era assente), non uno in più'
  );
  assert.deepEqual(
    body.knowledge_access,
    { allow_sensitive: true, kinds: ['fact', 'note'] },
    'knowledge_access caricato dall\'agente deve tornare intatto nel payload di save (round-trip UI)'
  );
  assert.equal(body.name, 'Assistente Cucina');
  assert.deepEqual(body.allowed_entities, ['light.cucina']);
});

test('modificare un chip entità (Scope) abilita il bottone Salva', async () => {
  const { window, document } = setup();
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  const btnSave = document.getElementById('btn-save');
  assert.equal(btnSave.disabled, true, 'appena montato, senza modifiche, Salva resta disabled');

  const pill = document.querySelector('#sc-body-scope .domain-pill');
  assert.ok(pill, 'la pillola di dominio deve esistere nella sezione Scope');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(
    btnSave.disabled,
    false,
    'il chip aggiunto dal picker (non è un <input>, l\'onChange deve marcare dirty esplicitamente) deve abilitare Salva'
  );
  assert.equal(window.HirisState.get('unsaved'), true);
});

test('Annulla con modifiche non salvate chiede conferma (e non naviga se l\'utente rifiuta)', async () => {
  const { window, document } = setup();
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  const pill = document.querySelector('#sc-body-scope .domain-pill');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(window.HirisState.get('unsaved'), true, 'precondizione: editor dirty dopo la modifica');

  let confirmCalls = 0;
  window.confirm = () => { confirmCalls += 1; return false; }; // utente rifiuta

  document.getElementById('btn-cancel').dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(confirmCalls, 1, 'Annulla con modifiche non salvate deve chiedere conferma');
  assert.notEqual(window.location.hash, '#/chatbots', 'rifiutando la conferma non deve navigare via');
});

test('Annulla con modifiche non salvate: confermando, naviga a #/chatbots', async () => {
  const { window, document } = setup();
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  const pill = document.querySelector('#sc-body-scope .domain-pill');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));

  window.confirm = () => true; // utente conferma di voler uscire
  document.getElementById('btn-cancel').dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(window.location.hash, '#/chatbots', 'confermando, la navigazione deve procedere');
});
