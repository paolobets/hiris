import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 6: creazione goal-first (config/create-wizard.js).

   Test comportamentali richiesti dal piano (riga "6 wizard"):
     - "avvisami se il garage resta aperto di notte" -> deriva Agentbot;
     - "un assistente che risponde sui miei consumi" -> deriva Chatbot;
     - la scelta resta modificabile (override esplicito);
     - nessuna chiamata a un endpoint LLM (asserire sullo stub fetch: solo
       api/chatbots|api/agentbots|api/entities|api/models sono ammessi --
       qui nemmeno api/models compare, il wizard non tocca il modello);
     - un Agentbot creato dal wizard ha allowed_tools assente/vuoto e
       un'azione dichiarata (linea rossa E.2 tenuta). */

const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
</body>`;

const SCRIPTS = [
  'config/state.js',
  'config/router.js',
  'config/api.js',
  'config/entity-picker.js',
  'config/editor-kit.js',
  'config/templates.js',
  'config/create-wizard.js',
];

const ALLOWED_FETCH_PREFIXES = ['api/chatbots', 'api/agentbots', 'api/entities', 'api/models'];

function setup(extraRoutes) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  const calls = stubFetch(ctx.window, Object.assign({
    'api/chatbots': { id: 'newchat1', name: 'x' },
    'api/agentbots': { ok: true, agentbot: { id: 'ab-new-1' }, agentbots: [] },
  }, extraRoutes || {}));
  return { ...ctx, calls };
}

function assertOnlyAllowedFetches(calls) {
  calls.forEach((c) => {
    const ok = ALLOWED_FETCH_PREFIXES.some((prefix) => c.url.startsWith(prefix));
    assert.ok(ok, `chiamata fetch non consentita (nessun endpoint LLM ammesso): ${c.url}`);
  });
}

function fillStep1(document, name, mission) {
  document.getElementById('cw-name').value = name;
  document.getElementById('cw-name').dispatchEvent(new document.defaultView.Event('input', { bubbles: true }));
  document.getElementById('cw-mission').value = mission;
  document.getElementById('cw-mission').dispatchEvent(new document.defaultView.Event('input', { bubbles: true }));
  document.getElementById('cw-step1-next').click();
}

test('deriveType è deterministica: nessuna proprietà "then"/promise, ritorno sincrono', () => {
  const { window } = setup();
  const result = window.HirisCreateWizard.deriveType('avvisami se il garage resta aperto di notte');
  assert.equal(typeof result.then, 'undefined', 'deriveType deve essere sincrona, non una Promise (mai un LLM dietro)');
  assert.equal(result.type, 'agentbot');
});

test('"avvisami se il garage resta aperto di notte" deriva Agentbot (suggerito, forte)', async () => {
  const { window, document, calls } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Garage notturno', 'avvisami se il garage resta aperto di notte');
  await tick(10);

  const agentbotBtn = document.getElementById('cw-type-agentbot');
  const chatbotBtn = document.getElementById('cw-type-chatbot');
  assert.ok(agentbotBtn && chatbotBtn, 'entrambe le card tipo devono esistere sempre (scelta sempre visibile)');
  assert.equal(agentbotBtn.getAttribute('aria-pressed'), 'true', 'Agentbot deve essere preselezionato (segnale forte)');
  assert.equal(chatbotBtn.getAttribute('aria-pressed'), 'false');
  assert.equal(agentbotBtn.getAttribute('data-suggested'), 'strong');

  assertOnlyAllowedFetches(calls);
});

test('"un assistente che risponde sui miei consumi" deriva Chatbot (suggerito, forte)', async () => {
  const { window, document, calls } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Consumi casa', 'un assistente che risponde sui miei consumi');
  await tick(10);

  const chatbotBtn = document.getElementById('cw-type-chatbot');
  const agentbotBtn = document.getElementById('cw-type-agentbot');
  assert.equal(chatbotBtn.getAttribute('aria-pressed'), 'true', 'Chatbot deve essere preselezionato (segnale forte)');
  assert.equal(agentbotBtn.getAttribute('aria-pressed'), 'false');
  assert.equal(chatbotBtn.getAttribute('data-suggested'), 'strong');

  assertOnlyAllowedFetches(calls);
});

test('segnale debole/assente: nessuna card preselezionata, copy neutra', async () => {
  const { window, document } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  // Testo senza pattern riconosciuti in nessuna delle due liste.
  fillStep1(document, 'Casa', 'gestisci la casa in generale');
  await tick(10);

  const agentbotBtn = document.getElementById('cw-type-agentbot');
  const chatbotBtn = document.getElementById('cw-type-chatbot');
  assert.equal(agentbotBtn.getAttribute('aria-pressed'), 'false', 'nessuna preselezione quando il segnale è assente (onestà, non un indovinare)');
  assert.equal(chatbotBtn.getAttribute('aria-pressed'), 'false');
  assert.equal(agentbotBtn.hasAttribute('data-suggested'), false);
  assert.equal(chatbotBtn.hasAttribute('data-suggested'), false);
  assert.equal(document.getElementById('cw-step2-next').disabled, true, 'senza scelta esplicita non si può continuare');
});

test('la derivazione resta sempre sovrascrivibile dall\'utente (override esplicito)', async () => {
  const { window, document } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  // Testo che deriva fortemente Agentbot...
  fillStep1(document, 'Garage notturno', 'avvisami se il garage resta aperto di notte');
  await tick(10);
  assert.equal(document.getElementById('cw-type-agentbot').getAttribute('aria-pressed'), 'true');

  // ...ma l'utente sceglie comunque Chatbot: deve essere permesso e deve
  // effettivamente cambiare lo stato (non un badge cosmetico).
  document.getElementById('cw-type-chatbot').click();
  assert.equal(document.getElementById('cw-type-chatbot').getAttribute('aria-pressed'), 'true', 'override deve applicarsi');
  assert.equal(document.getElementById('cw-type-agentbot').getAttribute('aria-pressed'), 'false');
  assert.equal(document.getElementById('cw-step2-next').disabled, false);

  document.getElementById('cw-step2-next').click();
  await tick(10);
  // Lo step 3 mostra i campi Chatbot (tool/scope/knowledge), non quelli Agentbot.
  assert.ok(document.getElementById('cw-tools-root'), 'lo step 3 deve seguire il TIPO SCELTO (chatbot), non quello derivato (agentbot)');
  assert.equal(document.getElementById('cw-trigger-type'), null);
});

test('nessuna chiamata a un endpoint LLM in tutto il flusso Chatbot (solo api/entities/api/chatbots)', async () => {
  const { window, document, calls } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Consumi casa', 'un assistente che risponde sui miei consumi');
  await tick(10);
  document.getElementById('cw-step2-next').click();
  await tick(10);

  // Interagisce con lo scope (fa scattare una fetch api/entities -- consentita).
  const scopeInput = document.querySelector('#cw-scope-root .ep-search');
  scopeInput.value = 'light.cucina';
  scopeInput.dispatchEvent(new window.KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter' }));

  document.getElementById('cw-step3-next').click();
  await tick(10);
  document.getElementById('cw-create-btn').click();
  await tick(20);

  assertOnlyAllowedFetches(calls);
  assert.ok(calls.some((c) => c.url === 'api/chatbots' && c.opts.method === 'POST'), 'deve creare via POST api/chatbots');
});

test('payload Chatbot creato dal wizard: tool liberi, nessun campo trigger nello schema', async () => {
  const { window, document, calls } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Consumi casa', 'un assistente che risponde sui miei consumi');
  await tick(10);
  document.getElementById('cw-step2-next').click();
  await tick(10);

  const toolChk = document.querySelector('#cw-tools-root input[type="checkbox"]');
  toolChk.checked = true;
  toolChk.dispatchEvent(new window.Event('change', { bubbles: true }));

  document.getElementById('cw-step3-next').click();
  await tick(10);
  document.getElementById('cw-create-btn').click();
  await tick(20);

  const postCall = calls.find((c) => c.url === 'api/chatbots' && c.opts && c.opts.method === 'POST');
  assert.ok(postCall);
  const body = JSON.parse(postCall.opts.body);
  assert.ok(Array.isArray(body.allowed_tools) && body.allowed_tools.length === 1, 'il tool spuntato deve arrivare nel payload');
  assert.equal('trigger' in body, false, 'il contratto Chatbot non ha nemmeno il campo trigger -- nessun trigger autonomo possibile');
  assert.equal(body.knowledge_access.allow_sensitive, false, 'default allow_sensitive resta false (invariante 4)');
});

test('LINEA ROSSA E.2: payload Agentbot creato dal wizard ha allowed_tools assente e azione dichiarata', async () => {
  const { window, document, calls } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Garage notturno', 'avvisami se il garage resta aperto di notte');
  await tick(10);
  // Segnale forte -> Agentbot già preselezionato, ma clicchiamo comunque
  // esplicitamente per esercitare lo stesso percorso click-based degli altri test.
  document.getElementById('cw-type-agentbot').click();
  document.getElementById('cw-step2-next').click();
  await tick(10);

  const triggerInput = document.querySelector('#cw-trigger-entity-root .ep-search');
  triggerInput.value = 'binary_sensor.garage';
  triggerInput.dispatchEvent(new window.KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter' }));
  document.getElementById('cw-trigger-operator').value = '==';
  document.getElementById('cw-trigger-threshold').value = 'on';

  document.getElementById('cw-step3-next').click();
  await tick(10);
  document.getElementById('cw-create-btn').click();
  await tick(20);

  assertOnlyAllowedFetches(calls);
  const postCall = calls.find((c) => c.url === 'api/agentbots' && c.opts && c.opts.method === 'POST');
  assert.ok(postCall, 'un Agentbot nuovo deve fare POST su api/agentbots');
  assert.equal(postCall.opts.headers['X-Requested-With'], 'fetch');

  const body = JSON.parse(postCall.opts.body);
  assert.equal('allowed_tools' in body, false, 'LINEA ROSSA: un Agentbot creato dal wizard non deve MAI avere allowed_tools (nemmeno vuoto per errore -- la chiave non esiste proprio)');
  assert.deepEqual(
    Object.keys(body).sort(),
    ['action', 'enabled', 'name', 'reasoning', 'severity', 'trigger'].sort(),
    'stessa forma esatta accettata da watcher/agentbots.py::validate_agentbot',
  );
  assert.equal(body.trigger.entity_id, 'binary_sensor.garage');
  assert.ok(body.action && body.action.type, 'l\'azione deve essere DICHIARATA nel payload, non lasciata al ragionamento AI');
  assert.equal(body.action.type, 'notify');
  assert.equal(typeof body.action.message, 'string');
  assert.equal(body.reasoning.enabled, false, 'wizard di default non abilita il ragionamento AI (deterministico, opt-in esplicito)');
});

test('naviga sull\'editor completo dopo la creazione (Chatbot -> #/chatbots/{id})', async () => {
  const { window, document } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Consumi casa', 'un assistente che risponde sui miei consumi');
  await tick(10);
  document.getElementById('cw-step2-next').click();
  await tick(10);
  document.getElementById('cw-step3-next').click();
  await tick(10);
  document.getElementById('cw-create-btn').click();
  await tick(20);

  assert.equal(window.location.hash, '#/chatbots/newchat1');
});

test('naviga sull\'editor completo dopo la creazione (Agentbot -> #/agentbots/{id}, id annidato in .agentbot)', async () => {
  const { window, document } = setup();
  window.HirisCreateWizard.mount();
  await tick(10);

  fillStep1(document, 'Garage notturno', 'avvisami se il garage resta aperto di notte');
  await tick(10);
  document.getElementById('cw-step2-next').click();
  await tick(10);
  document.getElementById('cw-step3-next').click();
  await tick(10);
  document.getElementById('cw-create-btn').click();
  await tick(20);

  assert.equal(window.location.hash, '#/agentbots/ab-new-1');
});
