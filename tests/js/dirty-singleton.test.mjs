import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* FINAL whole-branch review, finding C1 (CRITICAL -- silent data loss,
   regressione del bug che il Task 3 aveva chiuso, riemerso alla giuntura
   fra chatbot-editor.js e agentbot-editor.js).

   HirisEditorKit.dirty.track() (editor-kit.js) osserva #route-outlet -- il
   contenitore STABILE condiviso da OGNI route -- con un MutationObserver.
   Ma ogni editor teneva la propria handle a livello di modulo
   (dirtyTrackHandle in chatbot-editor.js E in agentbot-editor.js) e
   fermava SOLO la propria: aprire un editor Chatbot e poi un editor
   Agentbot lasciava DUE MutationObserver live sullo stesso #route-outlet.

   setupStickyActions gira SEMPRE prima di populate*() (vedi mount() in
   entrambi i file): ogni campo viene quindi iniettato mentre ENTRAMBI gli
   observer sono attivi. Il più vecchio (quello dell'editor già smontato)
   vince la wire race in editor-kit.js::track()/wire() -- il flag
   `el.__hkWired` fa si' che solo il PRIMO observer a processare un nodo
   nuovo lo agganci, quindi i campi del NUOVO editor restano wired alla
   closure markDirty dell'editor MORTO: la sua saveBarHandle punta a
   bottoni ormai detached (outlet.innerHTML='' li ha rimossi dal documento)
   -- il bottone Salva VISIBILE non si abilita mai, editando il nuovo
   editor. Simmetrico (Chatbot->Agentbot rompe Agentbot, Agentbot->Chatbot
   rompe Chatbot).

   Fix: dirty.track() nel kit e' ora un singleton -- installa il tracker e
   ferma AUTOMATICAMENTE quello precedente (chiunque l'avesse installato),
   invece di fare affidamento su ciascun modulo per fermare la propria
   copia. Un solo editor e' mai montato alla volta, quindi un solo tracker
   deve mai esistere alla volta. */

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
  'config/agentbot-editor.js',
];

function setup(extraRoutes) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  const calls = stubFetch(ctx.window, Object.assign({
    'api/models': { providers: [] },
    'api/chatbots': [],
    'api/agentbots': { agentbots: [] },
    'api/sentinel/timeline': { events: [] },
  }, extraRoutes || {}));
  return { ...ctx, calls };
}

test('C1: Agentbot montato dopo Chatbot -- editare un campo di B abilita Save e marca unsaved (nessun observer morto vince la wire race)', async () => {
  const { window, document } = setup();

  // Editor A (Chatbot) montato per primo -- lascia un tracker "morto" se
  // non viene fermato dal kit quando B monta.
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  // Editor B (Agentbot) montato dopo -- stesso #route-outlet, stesso
  // tpl-agent-editor.
  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  const nameInput = document.querySelector('#sc-body-identita input.input');
  assert.ok(nameInput, 'il campo Nome dell\'editor Agentbot deve esistere dopo il mount');

  nameInput.value = 'Garage aperto di notte';
  nameInput.dispatchEvent(new window.Event('input', { bubbles: true }));

  const btnSave = document.getElementById('btn-save');
  assert.equal(btnSave.disabled, false,
    'Save deve abilitarsi editando un campo dell\'editor CORRENTE (Agentbot) -- con due observer live il più vecchio (morto, Chatbot) vince la wire race e Save resta greyed');
  assert.equal(window.HirisState.get('unsaved'), true,
    'HirisState.unsaved deve diventare true -- il nav guard lo legge per avvisare prima di navigare via');
});

test('C1 simmetrico: Chatbot montato dopo Agentbot -- editare un campo di B abilita Save e marca unsaved', async () => {
  const { window, document } = setup();

  window.HirisAgentbotEditor.mount(null);
  await tick(20);

  window.HirisChatbotEditor.mount(null);
  await tick(20);

  const nameInput = document.getElementById('f-name');
  assert.ok(nameInput, 'il campo Nome dell\'editor Chatbot deve esistere dopo il mount');

  nameInput.value = 'Assistente Cucina';
  nameInput.dispatchEvent(new window.Event('input', { bubbles: true }));

  const btnSave = document.getElementById('btn-save');
  assert.equal(btnSave.disabled, false,
    'Save deve abilitarsi editando un campo dell\'editor CORRENTE (Chatbot)');
  assert.equal(window.HirisState.get('unsaved'), true,
    'HirisState.unsaved deve diventare true');
});

test('dirty.track() del kit ferma il tracker precedente chiunque lo avesse installato (singleton a livello di kit, non per-modulo)', async () => {
  const { window, document } = setup();
  document.body.innerHTML += '<div id="root-x"></div><div id="root-y"></div>';

  let calledX = 0;
  let calledY = 0;
  const trackerX = window.HirisEditorKit.dirty.track(document.getElementById('root-x'), function() { calledX += 1; });
  window.HirisEditorKit.dirty.track(document.getElementById('root-y'), function() { calledY += 1; });

  const inpX = document.createElement('input');
  document.getElementById('root-x').appendChild(inpX);
  const inpY = document.createElement('input');
  document.getElementById('root-y').appendChild(inpY);
  await tick(20);

  inpX.dispatchEvent(new window.Event('input', { bubbles: true }));
  inpY.dispatchEvent(new window.Event('input', { bubbles: true }));

  assert.equal(calledX, 0, 'il tracker su root-x deve essere stato fermato quando root-y ha installato il proprio (singleton)');
  assert.equal(calledY, 1, 'il tracker attivo (root-y, il più recente) deve funzionare normalmente');
});
