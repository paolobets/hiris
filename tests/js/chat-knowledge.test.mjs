import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Coda di approvazione della memoria nella pagina chat.
   `save_knowledge` scrive in stato "pending" e la ricerca legge solo gli
   "approved": senza questa coda quel ricordo non torna mai. Qui si verifica
   che la coda esista, dica il vero quando non riesce a leggere, non mostri in
   chiaro cio' che e' marcato sensibile, e non riporti in pagina l'HTML
   scritto da un LLM. */

function fixtureHtml() {
  return `<!doctype html><body>
    <a id="nav-tasks"></a>
    <a id="nav-proposals"><span class="task-badge" id="proposals-badge" data-count="0"></span></a>
    <a id="nav-knowledge"><span class="task-badge" id="knowledge-badge" data-count="0"></span></a>
    <button id="mobile-task-btn"></button>
    <button id="mobile-proposals-btn"><span id="mobile-proposals-badge" data-count="0"></span></button>
    <button id="mobile-knowledge-btn"><span id="mobile-knowledge-badge" data-count="0"></span></button>
    <div id="messages"></div>
    <div id="input-area"></div>
    <div id="turn-counter" style="display:none"></div>
    <div id="session-ended-msg" style="display:none"></div>
    <div id="task-panel"></div>
    <div id="proposals-panel"></div>
    <div id="knowledge-panel">
      <div id="knowledge-panel-header"><button id="knowledge-panel-back-btn"></button></div>
      <div id="chat-knowledge-list"></div>
    </div>
  </body>`;
}

const SCRIPTS = ['config/api.js', 'chat/knowledge-core.js', 'chat/knowledge.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

test('la coda mostra gli elementi in attesa e aggiorna il badge', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  window.fetch = async () => jsonResponse({ items: [
    { id: 1, kind: 'obligation', content: 'La caldaia va revisionata a ottobre',
      due_date: '2026-10-01', source: 'chat', created_at: '2026-08-02T09:00:00Z',
      sensitivity: 'normal' },
    { id: 2, kind: 'fact', content: 'Il codice del cancello e 1234',
      source: 'chat', created_at: '2026-08-01T09:00:00Z', sensitivity: 'normal' },
  ] });

  await window.HirisChatKnowledge.load();

  const cards = document.querySelectorAll('#chat-knowledge-list .kb-card');
  assert.equal(cards.length, 2, 'una card per elemento in attesa');
  assert.equal(document.getElementById('knowledge-badge').textContent, '2');
  assert.equal(document.getElementById('mobile-knowledge-badge').dataset.count, '2');
  assert.ok(document.querySelector('[data-kb-act="approve"]'), 'deve esserci Approva');
  assert.ok(document.querySelector('[data-kb-act="reject"]'), 'deve esserci Scarta');
  const testo = document.getElementById('chat-knowledge-list').textContent;
  assert.match(testo, /caldaia va revisionata/);
  assert.match(testo, /scade il 01\/10\/2026/, 'la scadenza si legge in formato italiano');
  assert.match(testo, /conversazione/, 'da dove viene, se il dato c e');
});

test('il contenuto scritto dal modello e sempre escapato', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  window.fetch = async () => jsonResponse({ items: [
    { id: 7, kind: '<b>x</b>', content: '<img src=x onerror="boom()">',
      title: '<script>bad()</script>', source: '<i>chat</i>',
      created_at: '2026-08-02T09:00:00Z', sensitivity: 'normal' },
  ] });

  await window.HirisChatKnowledge.load();

  const list = document.getElementById('chat-knowledge-list');
  assert.equal(list.querySelector('img'), null, 'nessun tag iniettato dal contenuto');
  assert.equal(list.querySelector('script'), null, 'nessuno script iniettato dal titolo');
  assert.match(list.innerHTML, /&lt;img/, 'il contenuto compare escapato');
});

test('un elemento sensibile non e mostrato in chiaro finche non lo si chiede', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  /* Il contenuto porta dentro un tag riconoscibile: e l unico punto del file
     che salta esc() di proposito, ed e sicuro solo perche reveal() scrive con
     textContent. Se qualcuno lo riscrivesse con innerHTML il testo comparirebbe
     lo stesso -- e il test passerebbe identico -- ma nel DOM comparirebbe anche
     #kb-xss-probe. E quello che qui si verifica non esista. */
  window.fetch = async () => jsonResponse({ items: [
    { id: 9, kind: 'fact',
      content: 'IBAN IT60X0542811101000000123456 <b id="kb-xss-probe">x</b>',
      source: 'chat', created_at: '2026-08-02T09:00:00Z', sensitivity: 'sensitive' },
  ] });

  /* init() e non solo load(): il click e delegato sul contenitore, come in
     chat/proposals.js, perche la lista viene ricostruita a ogni caricamento. */
  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatKnowledge.init();
  globalThis.setInterval = realSI;
  await tick(10);

  const list = document.getElementById('chat-knowledge-list');
  assert.equal(list.innerHTML.indexOf('IT60X0542811101000000123456'), -1,
    'il contenuto sensibile non deve finire nel DOM prima di essere richiesto');
  assert.ok(list.querySelector('.kb-sensitive'), 'la card deve dichiararsi sensibile');

  const revealBtn = list.querySelector('[data-kb-act="reveal"]');
  assert.ok(revealBtn, 'deve esserci un modo esplicito per mostrarlo');
  revealBtn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);

  assert.match(list.textContent, /IT60X0542811101000000123456/,
    'dopo il click il contenuto e visibile');
  assert.equal(list.querySelector('#kb-xss-probe'), null,
    'la rivelazione deve inserire testo, non HTML: nessun elemento costruito dal contenuto');
  assert.match(list.textContent, /<b id="kb-xss-probe">x<\/b>/,
    'il markup si legge come testo, esattamente com e stato salvato');
});

test('Approva chiama POST approve e non mostra un falso errore di rete', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).indexOf('/approve') !== -1) return jsonResponse({ ok: true });
    return jsonResponse({ items: [
      { id: 5, kind: 'fact', content: 'x', source: 'chat',
        created_at: '2026-08-02T09:00:00Z', sensitivity: 'normal' },
    ] });
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatKnowledge.init();
  globalThis.setInterval = realSI;
  await tick(10);

  const btn = document.querySelector('[data-kb-act="approve"]');
  assert.ok(btn, 'il bottone Approva deve esistere dopo il load di init()');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const approveCall = calls.find((c) => c.url.indexOf('/approve') !== -1);
  assert.ok(approveCall, 'il click deve fare la POST di approve');
  assert.match(approveCall.url, /api\/knowledge\/5\/approve$/);
  assert.equal(approveCall.opts.method, 'POST');
  assert.deepEqual(alerts, [], 'nessun alert: niente falso errore di rete');
});

test('un elemento gia gestito altrove lo dice in italiano, senza echo del backend', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  window.fetch = async (url) => {
    if (String(url).indexOf('/approve') !== -1) {
      return jsonResponse({ error: 'not found' }, 404);
    }
    return jsonResponse({ items: [
      { id: 5, kind: 'fact', content: 'x', source: 'chat',
        created_at: '2026-08-02T09:00:00Z', sensitivity: 'normal' },
    ] });
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatKnowledge.init();
  globalThis.setInterval = realSI;
  await tick(10);

  document.querySelector('[data-kb-act="approve"]')
    .dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(alerts.length, 1);
  assert.doesNotMatch(alerts[0], /not found/, 'niente stringa tecnica del backend');
  assert.match(alerts[0], /gi[aà] stato gestito/i);
});

test('coda vuota e coda illeggibile dicono due cose diverse', async () => {
  const vuota = loadScripts(SCRIPTS, { html: fixtureHtml() });
  vuota.window.fetch = async () => jsonResponse({ items: [] });
  await vuota.window.HirisChatKnowledge.load();
  const testoVuoto = vuota.document.getElementById('chat-knowledge-list').textContent;
  assert.match(testoVuoto, /Nessun/i, 'coda vuota: lo dice');
  assert.equal(vuota.document.getElementById('knowledge-badge').textContent, '');
  vuota.dispose();

  const rotta = loadScripts(SCRIPTS, { html: fixtureHtml() });
  rotta.window.fetch = async () => jsonResponse(
    { error: 'knowledge store not configured', items: [] }, 503);
  await rotta.window.HirisChatKnowledge.load();
  const testoRotto = rotta.document.getElementById('chat-knowledge-list').textContent;
  assert.doesNotMatch(testoRotto, /Nessun/i,
    'store irraggiungibile non deve sembrare una coda vuota');
  assert.match(testoRotto, /non/i, 'deve dichiarare di non aver potuto leggere');
  assert.notEqual(testoRotto, testoVuoto, 'i due stati devono essere distinguibili');
  assert.equal(rotta.document.getElementById('knowledge-badge').textContent, '',
    'nessun conteggio inventato quando la lettura fallisce');
});

test('aprire la Memoria chiude Proposte e Task', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/labels.js', 'config/proposals-core.js', 'chat/proposals.js',
      'chat/tasks.js', 'chat/knowledge-core.js', 'chat/knowledge.js'],
    { html: fixtureHtml() },
  );
  window.fetch = async (url) => (String(url).indexOf('api/tasks') !== -1
    ? jsonResponse([])
    : jsonResponse({ items: [], proposals: [] }));

  document.getElementById('proposals-panel').style.display = 'flex';
  document.getElementById('task-panel').style.display = 'flex';
  document.getElementById('nav-proposals').classList.add('active');
  document.getElementById('nav-tasks').classList.add('active');

  window.HirisChatKnowledge.showPanel('knowledge');
  await tick(5);

  assert.equal(document.getElementById('knowledge-panel').style.display, 'flex');
  assert.equal(document.getElementById('proposals-panel').style.display, 'none');
  assert.equal(document.getElementById('task-panel').style.display, 'none');
  assert.equal(document.getElementById('nav-proposals').classList.contains('active'), false);
  assert.equal(document.getElementById('nav-tasks').classList.contains('active'), false);
  assert.equal(document.getElementById('nav-knowledge').classList.contains('active'), true);

  /* e viceversa: aprire Proposte deve chiudere la Memoria */
  window.HirisChatProposals.showPanel('proposals');
  await tick(5);
  assert.equal(document.getElementById('knowledge-panel').style.display, 'none');
  assert.equal(document.getElementById('nav-knowledge').classList.contains('active'), false);

  window.HirisChatTasks.showPanel('tasks');
  await tick(5);
  assert.equal(document.getElementById('knowledge-panel').style.display, 'none');
});
