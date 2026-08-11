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

/* Spostato qui dalla fetta E5 Task 6, da tests/js/chat-proposals.test.mjs:
   quel file aveva come soggetto chat/proposals.js, uscito con /api/proposals*,
   ma QUESTO caso ha come soggetto config/proposals-core.js, che sopravvive
   perche' il peek della Dashboard qui sopra lo usa. Soggetto vivo, sola via
   d'accesso cambiata: si sposta, non si butta. Esce insieme al peek quando il
   Task 8 riscrive dashboard.js. */
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
