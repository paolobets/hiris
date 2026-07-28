import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* Review indipendente Task 2 (Finding 2): usage.js:80-87 registra un
   UNICO listener 'click' via event delegation su #route-outlet (contenitore
   stabile, mai ricreato — solo il suo innerHTML cambia a ogni mount/route,
   vedi il commento in cima a usage.js). E' il fix "safe-at-load" del Task 2
   E ospita l'implementazione "vincitrice" del toggle (confirm() +
   loadChatbots() + openAgent(fresh) — miglioramento reale sulla copia
   dell'editor, che non ricaricava/riapriva).

   Prima di questo test, l'unica copertura era un grep testuale su
   getElementById(...).onclick / addEventListener('click' in
   tests/test_fe_loader_collapse.py::test_usage_js_has_no_iife_time_dom_access
   — passerebbe anche se il listener fosse agganciato al contenitore
   sbagliato o non agganciato affatto (basta che la stringa
   "addEventListener('click'" compaia da qualche parte nel file).

   Questo test è comportamentale: monta un #route-outlet VUOTO, carica gli
   script (che registrano il listener sull'outlet mentre è ancora vuoto),
   INIETTA i bottoni dentro l'outlet DOPO il load (i bottoni non esistono al
   momento in cui il listener viene agganciato — è l'unico modo in cui può
   funzionare in produzione, dato che vengono ricreati a ogni mount
   dell'editor), poi dispatcha un click VERO e verifica gli effetti reali:
   la richiesta di rete uscita (PUT + header CSRF) e che il "reload path"
   (loadChatbots + openAgent) sia effettivamente girato. Se il listener
   fosse su document/window invece che sull'outlet, o mai agganciato, il
   click non produrrebbe nessuno di questi effetti — a differenza del grep,
   che non se ne accorgerebbe. */

const HTML = '<!doctype html><body><div id="chrome-here"></div><div id="route-outlet"></div></body>';
// SP-4 Fase B Task 4: chatbot-form.js è stato assorbito in chatbot-editor.js
// (unico owner di openAgent/loadChatbots, esposti come globali bare -- vedi
// il commento in fondo a chatbot-editor.js) ed eliminato. editor-kit.js è
// richiesto perché chatbot-editor.js chiama HirisEditorKit.dirty.guard(...)
// al parse time (top-level, non dentro mount()).
const SCRIPTS = ['config/api.js', 'config/state.js', 'config/editor-kit.js', 'config/chatbot-editor.js', 'config/usage.js'];

function injectButtons(document) {
  const outlet = document.getElementById('route-outlet');
  outlet.innerHTML =
    '<button id="u-ag-toggle-btn">toggle</button><button id="u-ag-reset-btn">reset</button>';
  return outlet;
}

/** Sostituisce un global bare (funzione dichiarata a livello top-level in
 * uno degli script legacy, es. `openAgent`/`loadChatbots`/`loadAgentUsage`)
 * con una spy, tenendo traccia delle chiamate. Usato per isolare
 * l'asserzione "il reload path è girato" dalle dipendenze DOM pesanti di
 * `openAgent` (form dell'editor intero) che sono fuori scope per QUESTO
 * test — usage.js chiama questi collaboratori come identificatori bare,
 * quindi sovrascrivere la proprietà su globalThis li sostituisce ovunque
 * vengano referenziati. */
function spyOn(name, impl) {
  const calls = [];
  globalThis[name] = async function(...args) {
    calls.push(args);
    return impl ? impl(...args) : undefined;
  };
  return calls;
}

test('click delegato su #u-ag-toggle-btn (iniettato DOPO il load): PUT + reload path', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: HTML });
  const outlet = injectButtons(document);

  window.HirisState.set('activeChatbotId', 'agent-1');
  window.chatbots = [{ id: 'agent-1', name: 'Test', enabled: true }];
  window.confirm = () => true;

  const calls = stubFetch(window, {
    // route piu' specifica PRIMA di quella generica: stubFetch fa un
    // includes() sequenziale sulle chiavi nell'ordine di inserimento.
    'api/chatbots/agent-1': {},
    'api/chatbots': [{ id: 'agent-1', name: 'Test', enabled: false }],
  });

  const openAgentCalls = spyOn('openAgent');
  const realLoadChatbots = globalThis.loadChatbots;
  const loadChatbotsCalls = spyOn('loadChatbots', () => realLoadChatbots());

  const btn = outlet.querySelector('#u-ag-toggle-btn');
  assert.ok(btn, 'il bottone toggle deve esistere dopo l\'iniezione');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  // 1) la richiesta PUT e' uscita con l'header CSRF, sull'URL corretto.
  const putCall = calls.find((c) => c.url === 'api/chatbots/agent-1' && c.opts && c.opts.method === 'PUT');
  assert.ok(putCall, 'deve partire una PUT verso api/chatbots/<id>');
  assert.equal(putCall.opts.headers['X-Requested-With'], 'fetch', 'header CSRF richiesto dal middleware (SEC-025)');
  assert.deepEqual(JSON.parse(putCall.opts.body), { enabled: false }, 'agent.enabled=true -> newEnabled=false');

  // 2) il "reload path" e' girato: loadChatbots() chiamata (che a sua
  //    volta ha rifatto una GET api/chatbots) DOPO la PUT.
  assert.equal(loadChatbotsCalls.length, 1, 'loadChatbots() deve essere chiamata dopo la PUT riuscita');
  const getCall = calls.find((c) => c.url === 'api/chatbots' && (!c.opts || !c.opts.method));
  assert.ok(getCall, 'loadChatbots() deve rifare una GET su api/chatbots');
  assert.ok(calls.indexOf(putCall) < calls.indexOf(getCall), 'la GET di reload deve avvenire DOPO la PUT');

  // 3) openAgent(fresh) viene richiamato con l'agente aggiornato preso
  //    dalla lista appena ricaricata (non con lo stato stale pre-toggle).
  assert.equal(openAgentCalls.length, 1, 'openAgent deve essere richiamato una volta sola (riapre l\'agente)');
  assert.equal(openAgentCalls[0][0].id, 'agent-1');
  assert.equal(openAgentCalls[0][0].enabled, false, 'openAgent deve ricevere lo stato AGGIORNATO (post-reload), non quello stale');
});

test('il click delegato funziona ANCHE dopo un remount (outlet.innerHTML sostituito, listener mai riattaccato)', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: HTML });
  let outlet = injectButtons(document);

  window.HirisState.set('activeChatbotId', 'agent-1');
  window.chatbots = [{ id: 'agent-1', name: 'Test', enabled: true }];
  window.confirm = () => true;
  const calls = stubFetch(window, {
    'api/chatbots/agent-1': {},
    'api/chatbots': [{ id: 'agent-1', name: 'Test', enabled: false }],
  });
  spyOn('openAgent');
  const realLoadChatbots = globalThis.loadChatbots;
  spyOn('loadChatbots', () => realLoadChatbots());

  // Simula la navigazione via da questa route (il router sostituisce il
  // contenuto di #route-outlet con un'altra pagina — il nodo outlet stesso
  // NON viene mai ricreato, solo il suo innerHTML) e poi il remount, che
  // ricrea i bottoni come nodi NUOVI.
  document.getElementById('route-outlet').innerHTML = '<div class="page-title">Altra pagina</div>';
  outlet = injectButtons(document);

  const btn = outlet.querySelector('#u-ag-toggle-btn');
  assert.ok(btn, 'il bottone deve esistere anche dopo il remount (nodo nuovo)');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  const putCall = calls.find((c) => c.url === 'api/chatbots/agent-1' && c.opts && c.opts.method === 'PUT');
  assert.ok(putCall, 'la delegation deve funzionare anche sui nodi ricreati dopo il remount, senza alcun rewire manuale');
  assert.equal(putCall.opts.headers['X-Requested-With'], 'fetch');
});

test('click delegato su #u-ag-reset-btn: reset riuscito (r.ok) ricarica i consumi', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: HTML });
  const outlet = injectButtons(document);

  window.HirisState.set('activeChatbotId', 'agent-1');
  window.confirm = () => true;
  const calls = stubFetch(window, { 'usage/reset': {} });
  const loadAgentUsageCalls = spyOn('loadAgentUsage');

  const btn = outlet.querySelector('#u-ag-reset-btn');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  const resetCall = calls.find((c) => c.url.includes('usage/reset'));
  assert.ok(resetCall, 'deve partire una POST verso .../usage/reset');
  assert.equal(resetCall.opts.method, 'POST');
  assert.equal(resetCall.opts.headers['X-Requested-With'], 'fetch');
  assert.equal(loadAgentUsageCalls.length, 1, 'con r.ok=true (stub di default) loadAgentUsage(aid) deve girare (gate r.ok)');
  assert.equal(loadAgentUsageCalls[0][0], 'agent-1');
});

test('click delegato su #u-ag-reset-btn: reset FALLITO (r.ok=false) NON ricarica i consumi (fix minore: gate r.ok ripristinato)', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: HTML });
  const outlet = injectButtons(document);

  window.HirisState.set('activeChatbotId', 'agent-1');
  window.confirm = () => true;
  // Stub manuale (non stubFetch, che restituisce sempre ok:true): serve
  // simulare una risposta non-ok per provare il gate ripristinato in
  // _resetAgentUsage() — prima del fix minore, loadAgentUsage(aid) veniva
  // chiamata incondizionatamente anche quando il reset falliva lato server.
  const calls = [];
  window.fetch = (url, opts) => {
    calls.push({ url: String(url), opts });
    return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
  };
  const loadAgentUsageCalls = spyOn('loadAgentUsage');

  const btn = outlet.querySelector('#u-ag-reset-btn');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  assert.equal(calls.length, 1, 'la POST di reset deve comunque partire');
  assert.equal(loadAgentUsageCalls.length, 0, 'con r.ok=false loadAgentUsage NON deve essere chiamata (gate ripristinato)');
});
