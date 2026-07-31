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
