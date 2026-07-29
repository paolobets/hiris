import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* FINAL whole-branch review, finding I2 (Important), parte 2/2 (vedi anche
   tests/js/nav-guard-unsaved-clear.test.mjs -- file separato apposta,
   node --test isola per FILE non per singola test() nello stesso file).

   Annulla (onCancel) e deleteAgent avevano lo stesso buco di 'unsaved' mai
   pulito: confermavano/eliminavano e cambiavano hash SENZA pulire
   'unsaved', quindi il guard (installato in main.js, hashchange listener
   registrato PRIMA del router) vedeva ancora true sul hashchange che loro
   stessi generavano e chiedeva conferma UNA SECONDA volta -- per una
   scelta già fatta (Annulla) o su un'entità che non esiste più
   (deleteAgent, appena cancellata). */

const CHATBOT_HTML = `<!doctype html><body>
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

const CHATBOT_SCRIPTS = [
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

function setupChatbot(extraRoutes) {
  const ctx = loadScripts(CHATBOT_SCRIPTS, { html: CHATBOT_HTML });
  const calls = stubFetch(ctx.window, Object.assign({
    'api/models': { providers: [] },
    'api/chatbots': [],
  }, extraRoutes || {}));
  // Stesso pattern di main.js (installato prima di ogni mount, come nella pagina reale).
  ctx.window.HirisEditorKit.dirty.guard(
    function() { return !!ctx.window.HirisState.get('unsaved'); },
    function() { ctx.window.HirisState.set('unsaved', false); }
  );
  return { ...ctx, calls };
}

test('I2b: Annulla (Chatbot) con conferma non ririchiede conferma una seconda volta sul suo stesso hashchange', async () => {
  const { window, document } = setupChatbot();
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  const pill = document.querySelector('#sc-body-scope .domain-pill');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(window.HirisState.get('unsaved'), true, 'precondizione: editor dirty');

  let confirmCalls = 0;
  window.confirm = () => { confirmCalls += 1; return true; }; // utente conferma Annulla

  document.getElementById('btn-cancel').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(10);

  assert.equal(window.location.hash, '#/chatbots', 'Annulla confermato deve navigare via');
  assert.equal(confirmCalls, 1,
    'BUG I2: Annulla chiede conferma UNA volta sola -- il guard non deve ririchiederla sullo stesso hashchange che Annulla genera');
});

test('I2c: deleteAgent (Chatbot) su editor dirty non chiede "modifiche non salvate" dopo l\'eliminazione riuscita', async () => {
  const AGENT = { id: 'agent-1', name: 'X', is_default: false };
  const { window, document } = setupChatbot({
    'api/chatbots/agent-1': AGENT,
    'api/chatbots': [AGENT],
  });
  window.HirisState.set('activeChatbotId', 'agent-1');
  window.HirisChatbotEditor.mount('agent-1');
  await tick(20);

  // Editor dirty prima di eliminare.
  const pill = document.querySelector('#sc-body-scope .domain-pill');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(window.HirisState.get('unsaved'), true, 'precondizione: editor dirty');

  let confirmCalls = 0;
  window.confirm = () => { confirmCalls += 1; return true; }; // "Eliminare questo Chatbot?" -> sì

  await window.deleteAgent();
  await tick(10);

  assert.equal(window.location.hash, '#/chatbots', 'delete riuscito deve navigare a #/chatbots');
  assert.equal(confirmCalls, 1,
    'BUG I2: deleteAgent deve chiedere UNA sola conferma ("Eliminare?") -- non anche "modifiche non salvate" per un\'entità appena eliminata');
});
