import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Plance a proposta: la card deve dire a chiare lettere quando una proposta
   SOSTITUISCE interamente una plancia esistente, e dopo l'apply deve offrire
   l'azione Annulla (ripristino dell'ultimo snapshot, endpoint di Task 6). */

function fixtureHtml() {
  return `<!doctype html><body>
    <a id="nav-proposals"><span id="proposals-badge" data-count="0"></span></a>
    <button id="mobile-proposals-btn"><span id="mobile-proposals-badge" data-count="0"></span></button>
    <div id="messages"></div><div id="input-area"></div>
    <div id="turn-counter"></div><div id="session-ended-msg"></div>
    <div id="task-panel"></div>
    <div id="proposals-panel"><div id="proposals-panel-header"></div>
      <div id="chat-proposals-list"></div></div>
  </body>`;
}

function dashProposal(mode) {
  return {
    id: 'p1', type: 'ha_dashboard', name: 'Casa Mia',
    description: 'x',
    config: { kind: 'dashboard', mode: mode, slug: 'casa-mia', ha_config: { views: [] } },
  };
}

test('la card di una sostituzione avvisa che sostituisce interamente', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ proposals: [dashProposal('replace')] }) });

  await window.HirisChatProposals.load();

  const warn = document.querySelector('#chat-proposals-list .pp-warn');
  assert.ok(warn, 'una sostituzione deve mostrare un avviso');
  assert.match(warn.textContent, /[Ss]ostituisce interamente/);
});

test('la card di una creazione NON mostra l\'avviso di sostituzione', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ proposals: [dashProposal('create')] }) });

  await window.HirisChatProposals.load();
  assert.equal(document.querySelector('#chat-proposals-list .pp-warn'), null);
});

test('dopo un replace applicato compare Annulla, che chiama il restore', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).indexOf('/apply') !== -1) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    if (String(url).indexOf('/restore') !== -1) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    return { ok: true, status: 200, json: async () => ({ proposals: [dashProposal('replace')] }) };
  };
  window.confirm = () => true;
  window.alert = () => {};

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();
  globalThis.setInterval = realSI;
  await tick(10);

  document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const undo = document.querySelector('.pp-undo');
  assert.ok(undo, 'dopo un replace applicato deve comparire Annulla');
  undo.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const restore = calls.find((c) => c.url.indexOf('/restore') !== -1);
  assert.ok(restore, 'Annulla deve chiamare l\'endpoint di restore');
  assert.match(restore.url, /api\/dashboards\/casa-mia\/restore$/);
  assert.equal(restore.opts.method, 'POST');
});

test('Annulla sopravvive al ricaricamento della lista e sparisce dopo il ripristino', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  let pending = [dashProposal('replace')];
  window.fetch = async (url) => {
    if (String(url).indexOf('/apply') !== -1) {
      pending = [];   // applicata: non è più in attesa
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }
    if (String(url).indexOf('/restore') !== -1) return { ok: true, status: 200, json: async () => ({ ok: true }) };
    return { ok: true, status: 200, json: async () => ({ proposals: pending }) };
  };
  window.confirm = () => true;
  window.alert = () => {};

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();
  globalThis.setInterval = realSI;
  await tick(10);

  document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  // Il polling periodico (o il rientro nel pannello) ricarica la lista: la
  // proposta applicata sparisce, l'azione Annulla no.
  await window.HirisChatProposals.load();
  assert.ok(document.querySelector('.pp-undo'), 'Annulla deve sopravvivere a un load()');
  assert.equal(document.querySelector('.pp-card'), null, 'la proposta applicata non è più in attesa');
  assert.equal(document.getElementById('proposals-badge').dataset.count, '0', 'il badge deve aggiornarsi');

  document.querySelector('.pp-undo').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.equal(document.querySelector('.pp-undo'), null, 'dopo il ripristino Annulla sparisce');
});

