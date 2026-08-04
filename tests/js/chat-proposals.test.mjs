import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Pannello Proposte nella pagina chat (voce di navigazione dedicata).
   Le proposte sono un'inbox di azioni come i Task: qui vivono nella chat.
   Azione via il core condiviso HirisProposalsCore. */

function fixtureHtml() {
  return `<!doctype html><body>
    <a id="nav-tasks"></a>
    <a id="nav-proposals"><span class="task-badge" id="proposals-badge" data-count="0"></span></a>
    <button id="mobile-task-btn"></button>
    <button id="mobile-proposals-btn"><span id="mobile-proposals-badge" data-count="0"></span></button>
    <div id="messages"></div>
    <div id="input-area"></div>
    <div id="turn-counter" style="display:none"></div>
    <div id="session-ended-msg" style="display:none"></div>
    <div id="task-panel"></div>
    <div id="proposals-panel">
      <div id="proposals-panel-header"><button id="proposals-panel-back-btn"></button></div>
      <div id="chat-proposals-list"></div>
    </div>
  </body>`;
}

test('il pannello Proposte carica le pending e aggiorna il badge', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async () => ({
    ok: true, status: 200,
    json: async () => ({ proposals: [
      { id: 'p1', type: 'ha_automation', name: 'Spegni luci a mezzanotte', description: 'Trovato pattern', created_at: '2026-07-31T10:00:00' },
    ] }),
  });

  await window.HirisChatProposals.load();

  const card = document.querySelector('#chat-proposals-list .pp-card');
  assert.ok(card, 'la card della proposta deve comparire');
  assert.equal(document.getElementById('proposals-badge').textContent, '1');
  assert.equal(document.getElementById('mobile-proposals-badge').dataset.count, '1');
  assert.ok(document.querySelector('.pp-apply'), 'deve esserci il bottone Attiva');
});

test('Attiva chiama POST apply e NON mostra un falso "Errore di rete"', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).indexOf('/apply') !== -1) {
      return { ok: true, status: 200, json: async () => ({ status: 'applied' }) };
    }
    return { ok: true, status: 200, json: async () => ({ proposals: [
      { id: 'p1', type: 'ha_automation', name: 'X' },
    ] }) };
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();       // fa il load() iniziale + wire click delegato
  globalThis.setInterval = realSI;
  await tick(10);

  const btn = document.querySelector('.pp-apply');
  assert.ok(btn, 'il bottone Attiva deve esistere dopo il load di init()');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const applyCall = calls.find((c) => c.url.indexOf('/apply') !== -1);
  assert.ok(applyCall, 'clic su Attiva deve fare la POST di apply');
  assert.match(applyCall.url, /api\/proposals\/p1\/apply$/);
  assert.equal(applyCall.opts.method, 'POST');
  assert.deepEqual(alerts, [], 'nessun alert: niente falso "Errore di rete"');
});

// ---------------------------------------------------------------------------
// I-5 (review indipendente su bee3ab1): act()/undo() mostravano
// `res.error || 'Errore'` -- la stringa tecnica del backend
// (handlers_proposals.py/handlers_dashboards.py) direttamente all'utente.
// ---------------------------------------------------------------------------

test('HirisProposalsCore.errorMessage: mai la stringa del backend, derivato dallo stato', () => {
  const { window } = loadScripts(['config/api.js', 'config/proposals-core.js']);
  const M = window.HirisProposalsCore.errorMessage;

  const raw409 = M({ status: 409, error: 'Proposal not found or not in pending state' });
  assert.doesNotMatch(raw409, /Proposal not found/);

  const raw503 = M({ status: 503, error: 'ProposalStore not initialized' });
  assert.doesNotMatch(raw503, /ProposalStore/);
  assert.notEqual(raw503, raw409, '409 e 503 devono dire cose diverse');

  const raw502 = M({ status: 502, error: 'Automazione non creata in HA: connection refused' });
  assert.doesNotMatch(raw502, /connection refused/);
  assert.notEqual(raw502, raw409);
  assert.notEqual(raw502, raw503);

  // I-5: quando lo stato non rientra in nessun caso noto, mostra almeno il
  // codice HTTP -- "Errore 500" e "Errore 404" devono restare distinguibili,
  // non un "Errore" generico e basta.
  const unknown500 = M({ status: 500, error: null });
  const unknown404 = M({ status: 404, error: null });
  assert.match(unknown500, /500/);
  assert.notEqual(unknown500, unknown404);
});

test('Attiva fallita: l\'alert NON mostra la stringa tecnica del backend, ma un testo derivato dallo stato (I-5)', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async (url) => {
    if (String(url).indexOf('/apply') !== -1) {
      return { ok: false, status: 503, json: async () => ({ error: 'ProposalStore not initialized' }) };
    }
    return { ok: true, status: 200, json: async () => ({ proposals: [
      { id: 'p1', type: 'ha_automation', name: 'X' },
    ] }) };
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);
  const realError = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args);

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();
  globalThis.setInterval = realSI;
  await tick(10);

  try {
    document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
    await tick(20);
  } finally {
    console.error = realError;
  }

  assert.equal(alerts.length, 1, 'un fallimento applicativo deve produrre un alert');
  assert.doesNotMatch(alerts[0], /ProposalStore/,
    'niente stringa tecnica del backend nell\'alert');
  assert.match(alerts[0], /servizio|disponibile/i,
    'un 503 deve dire che il servizio non e\' disponibile, non "Errore" generico');
  assert.ok(logged.length > 0, 'il dettaglio tecnico deve comunque finire in console, per diagnosticare');
});
