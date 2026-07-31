import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Regressione del bug: "Attiva" su una proposta dal peek della Dashboard dava
   "Errore di rete", mentre dalla pagina Proposte funzionava.

   Causa: la Dashboard riusava il globale applyProposal() di proposals.js,
   cablato sul DOM della pagina Proposte (#pr-<id>, #proposals-list). Dopo un
   apply RIUSCITO, sul DOM della dashboard `row` era null -> ramo else ->
   checkEmptyList() -> getElementById('proposals-list') null ->
   null.querySelector -> TypeError -> catch -> alert('Errore di rete').
   L'automazione VENIVA attivata, ma l'utente vedeva un falso errore.

   Fix: il peek usa HirisProposalsCore + ricarica se stesso. Questo test pinna
   che clic su Attiva faccia la POST apply e NON produca alcun alert d'errore. */

test('peek Dashboard: Attiva fa apply e ricarica, senza falso "Errore di rete"', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/state.js', 'config/proposals-core.js', 'config/dashboard.js'],
    { html: '<!doctype html><body><div id="route-outlet"></div></body>' },
  );

  const pending = [{ id: 'p9', type: 'ha_automation', name: 'Modifica automazione luci' }];
  const calls = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    calls.push({ url: u, opts: opts || {} });
    if (u.indexOf('/apply') !== -1) return { ok: true, status: 200, json: async () => ({ status: 'applied' }) };
    if (u.indexOf('api/chatbots') !== -1) return { ok: true, status: 200, json: async () => ([{ id: 'a1', name: 'Iris' }]) };
    if (u.indexOf('api/proposals') !== -1) return { ok: true, status: 200, json: async () => ({ proposals: pending }) };
    if (u.indexOf('api/brain/feed') !== -1) return { ok: true, status: 200, json: async () => ({ items: [] }) };
    if (u.indexOf('api/brain/advisories') !== -1) return { ok: true, status: 200, json: async () => ({ advisories: [] }) };
    return { ok: true, status: 200, json: async () => ({}) };
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  window.HirisDashboard.mount();
  await tick(30);

  const applyBtn = document.querySelector('#dash-proposals-body [data-act="apply"]');
  assert.ok(applyBtn, 'nel peek deve comparire una card proposta con bottone Attiva');
  assert.equal(applyBtn.dataset.pid, 'p9');

  applyBtn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  const applyCall = calls.find((c) => c.url.indexOf('/apply') !== -1);
  assert.ok(applyCall, 'clic su Attiva deve fare la POST di apply');
  assert.match(applyCall.url, /api\/proposals\/p9\/apply$/);
  assert.equal(applyCall.opts.method, 'POST');
  assert.deepEqual(alerts, [], 'nessun alert: il falso "Errore di rete" non deve più comparire');
});
