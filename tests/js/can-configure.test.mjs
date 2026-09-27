import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, tick, staticSnapshotDir, installaFogli, displayRisolto } from './helpers/dom.mjs';

/* Le pagine per chi non amministra (spec 2026-09-27 §4, Task 4).
 *
 * `GET /api/pending` porta `can_configure` accanto a `can_build`: con
 * `false` la chat non offre i consumi ne' «Configurazione», il guscio
 * `/config` offre solo Impegni e Memoria, la Memoria e' in sola lettura, e
 * una pagina aperta per indirizzo dice il rifiuto del SERVER. Il server resta
 * il giudice -- ogni porta che qui sparisce e' gia' chiusa dal cancello
 * (`api/admission.py`) -- la pagina smette solo di offrirla.
 *
 * Si caricano i gusci VERI (`index.html`, `config.html`) e gli script nel
 * loro ordine, letto dal guscio: un finto direbbe solo che il test sa
 * copiarsi. I PIN (prefisso «PIN») sono stati scritti e visti verdi sul
 * codice di partenza, prima di cambiare una riga: per un amministratore non
 * deve cambiare niente. */

const STATIC = staticSnapshotDir();
const read = (file) => readFileSync(join(STATIC, file), 'utf8');

/* Gli script di un guscio, nel suo ordine: si leggono dal `.html`, non si
   scrivono qui (stessa disciplina di `installaFogli`). */
function shellScripts(shell) {
  return [...read(shell).matchAll(/<script src="static\/([^"]+\.js)"><\/script>/g)].map((m) => m[1]);
}

function json(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function pendingBody(canConfigure, extra = {}) {
  return { agenda_unread: 0, constructions_pending: 0, can_build: canConfigure, can_configure: canConfigure, ...extra };
}

/* Il fetch finto: `answers` mappa un frammento d'indirizzo a una risposta
   (o a una funzione che la produce). Registra OGNI indirizzo chiesto: le
   prove leggono da qui il fatto «questa richiesta non e' partita». */
function fakeFetch(window, answers) {
  const calls = [];
  window.fetch = (url, opts) => {
    const u = String(url);
    calls.push({ url: u, method: (opts && opts.method) || 'GET' });
    const hit = Object.keys(answers).find((frag) => u.includes(frag));
    const answer = hit ? answers[hit] : json(200, {});
    return Promise.resolve(typeof answer === 'function' ? answer(u, opts) : answer);
  };
  return calls;
}

const asked = (calls, frag) => calls.some((c) => c.url.includes(frag));

async function settle(n = 6) {
  for (let i = 0; i < n; i++) await tick(0);
}

/* ── La chat ─────────────────────────────────────────────────────────── */

const CHAT_MAIN = join(STATIC, 'chat', 'main.js');

/* Il guscio vero, gli script veri tranne `chat/main.js`, che parte al
   caricamento (e' un IIFE che chiama `boot()`): si esegue per ultimo, con
   fetch e timer gia' finti. Gli intervalli si CATTURANO invece di girare:
   `runIntervals()` fa scattare un giro di tutti quelli ancora vivi, ed e'
   cosi' che si vede se il giro dei consumi e' partito, o si e' fermato. */
async function bootChat(t, { canConfigure, remembered, pending }) {
  const scripts = shellScripts('index.html').filter((s) => s !== 'chat/main.js');
  const ctx = loadScripts(scripts, { html: read('index.html') });
  installaFogli(ctx.document, 'index.html');
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  if (remembered !== undefined) ctx.window.localStorage.setItem('hiris.can_configure', remembered);
  const calls = fakeFetch(ctx.window, {
    'api/pending': pending || json(200, pendingBody(canConfigure)),
    'api/usage': json(200, { total_requests: 3, input_tokens: 10, output_tokens: 5, cost_eur: 0.01, sections: [] }),
    'api/health': json(200, { status: 'ok', version: '0.0.0' }),
    'api/chat/conversations': json(200, { conversations: [] }),
    'api/chat/history': json(200, { messages: [] }),
  });
  const intervals = new Map();
  let next = 1;
  const realSet = globalThis.setInterval;
  const realClear = globalThis.clearInterval;
  globalThis.setInterval = (fn) => { const id = next++; intervals.set(id, fn); return id; };
  globalThis.clearInterval = (id) => { intervals.delete(id); };
  t.after(() => {
    globalThis.setInterval = realSet;
    globalThis.clearInterval = realClear;
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });
  // eval indiretto del file vero: e' il meccanismo del test (vedi sopra).
  // eslint-disable-next-line no-eval -- vedi commento sopra
  (0, eval)(readFileSync(CHAT_MAIN, 'utf8'));
  await settle();
  const runIntervals = async () => {
    /* Una copia: un giro che ne fa partire un altro (il ricordo smentito
       rimette in moto i consumi) non deve scattare nello stesso giro. */
    const alive = Array.from(intervals.values());
    for (const fn of alive) fn();
    await settle();
  };
  return { ...ctx, calls, runIntervals };
}

function usageWidget(doc) { return doc.getElementById('usage-widget'); }
function configureLink(doc) {
  return [...doc.querySelectorAll('#sidebar a')].find((a) => a.textContent.trim() === 'Configurazione');
}
/* Si vede? Nessun antenato (ne' lui) porta `hidden`, e -- dove la cascata
   si sa risolvere -- il foglio vero non lo spegne. `[hidden]` vince su tutto
   per `hiris-theme.css` (`display: none !important`), caricato da entrambi i
   gusci; le etichette della barra hanno regole dentro @media che
   `displayRisolto` rifiuta di indovinare, e li' basta l'attributo. */
function shown(el) {
  if (el.closest('[hidden]')) return false;
  try { return displayRisolto(el) !== 'none'; } catch { return true; }
}

test('PIN chat: un amministratore vede i consumi e «Configurazione», e il giro dei consumi gira', async (t) => {
  const { document, calls, runIntervals } = await bootChat(t, { canConfigure: true });

  assert.ok(shown(usageWidget(document)), 'il riquadro dei consumi si vede');
  assert.ok(shown(configureLink(document)), 'il link «Configurazione» si vede');
  assert.equal(document.getElementById('u-requests').textContent, '3', 'i numeri arrivano da api/usage');
  const before = calls.filter((c) => c.url.includes('api/usage')).length;
  await runIntervals();
  assert.ok(calls.filter((c) => c.url.includes('api/usage')).length > before,
    'il giro dei consumi chiede ancora api/usage');
});

/* ── Il guscio /config ───────────────────────────────────────────────── */

async function bootConfig(t, { canConfigure, hash = '', remembered, answers = {}, pending }) {
  const ctx = loadScripts(shellScripts('config.html'), { html: read('config.html') });
  installaFogli(ctx.document, 'config.html');
  if (remembered !== undefined) ctx.window.localStorage.setItem('hiris.can_configure', remembered);
  if (hash) ctx.window.history.replaceState(null, '', hash);
  const calls = fakeFetch(ctx.window, {
    'api/pending': pending || json(200, pendingBody(canConfigure)),
    'api/health': json(404, {}),
    'api/memories': json(200, {
      available: true, total: 1, shown: 1,
      memories: [{ id: 'm1', testo: 'Mi piace il caffè', detto_il: '2026-09-27T08:00:00Z' }],
    }),
    ...answers,
  });
  t.after(() => ctx.dom.window.close());
  /* `DOMContentLoaded` lo manda jsdom da se', un giro dopo il parse: un
     secondo evento a mano rimonterebbe la cornice sopra la pagina gia'
     risolta (misurato: la briciola tornava a «…»). Si aspetta il suo. */
  if (ctx.document.readyState === 'loading') {
    await new Promise((resolve) => ctx.document.addEventListener('DOMContentLoaded', resolve));
  }
  await settle();
  return { ...ctx, calls };
}

function navItem(doc, route) { return doc.querySelector('#side-nav .nav-item[data-route="' + route + '"]'); }
function sectionLabels(doc) {
  return [...doc.querySelectorAll('#side-nav .nav-section-label')];
}

const CONFIGURE_ROUTES = ['knowledge', 'tree', 'watcher', 'settings', 'models', 'services', 'usage'];

test('PIN /config: un amministratore trova tutte le voci e atterra su «Cosa HIRIS sa»', async (t) => {
  const { document, calls } = await bootConfig(t, { canConfigure: true });

  for (const route of [...CONFIGURE_ROUTES, 'agenda', 'memory', 'constructions']) {
    assert.ok(shown(navItem(document, route)), `la voce ${route} si vede`);
  }
  for (const label of sectionLabels(document)) assert.ok(shown(label), label.textContent);
  assert.equal(document.getElementById('chrome-here').textContent, 'Cosa HIRIS sa');
  assert.ok(asked(calls, 'api/home-space'), 'la home legge api/home-space');
  assert.ok(asked(calls, 'api/briefing'), 'la home legge api/briefing');
});

test('PIN /config: un amministratore apre #/models per indirizzo e trova la pagina', async (t) => {
  const { document, calls } = await bootConfig(t, { canConfigure: true, hash: '#/models' });

  assert.equal(document.getElementById('chrome-here').textContent, 'Modelli');
  assert.ok(asked(calls, 'api/models/config'), 'la pagina Modelli legge la sua configurazione');
});

/* ── La Memoria ──────────────────────────────────────────────────────── */

function button(doc, label) {
  return [...doc.querySelectorAll('#route-outlet button')].find((b) => b.textContent.trim() === label);
}

test('PIN Memoria: un amministratore vede «Correggi» e «Dimentica»', async (t) => {
  const { document } = await bootConfig(t, { canConfigure: true, hash: '#/memory' });

  assert.equal(document.getElementById('chrome-here').textContent, 'Memoria');
  for (const label of ['Correggi', 'Dimentica']) {
    const b = button(document, label);
    assert.ok(b, `il pulsante «${label}» c'e'`);
    let node = b;
    while (node && node.id !== 'route-outlet') {
      assert.ok(shown(node), `«${label}» e i suoi contenitori si vedono`);
      node = node.parentElement;
    }
  }
  assert.match(visibleText(document.querySelector('#route-outlet .page-subtitle')), /Puoi correggere/);
});

/* ════════════════════════════════════════════════════════════════════════
   Chi non configura (`can_configure: false`).
   ════════════════════════════════════════════════════════════════════════ */

/* Il testo del rifiuto e' quello del SERVER, e arriva come testo: la forma
   di `api/admission.py::_refusal` per le rotte `/api/` e' `{"errore": ...}`.
   Qui porta un pezzo di markup, perche' la prova e' che resti testo
   (security-constraints 4.3). */
const HOSTILE = '<img src=x onerror=alert(1)>';
const REFUSED = json(403, { errore: HOSTILE });

/* Le rotte che per un amministratore portano dati di configurazione e che
   chi non configura non deve nemmeno chiedere (security-constraints 4.5). */
const ADMIN_DATA = ['api/usage', 'api/home-space', 'api/briefing'];

function assertNoAdminData(calls) {
  for (const frag of ADMIN_DATA) {
    assert.ok(!asked(calls, frag), `nessuna richiesta a ${frag}: ` + calls.map((c) => c.url).join(', '));
  }
}

function rememberedConfigure(doc) { return doc.defaultView.localStorage.getItem('hiris.can_configure'); }

test('chat: chi non configura non vede consumi ne\' «Configurazione», e il giro dei consumi non parte', async (t) => {
  const { document, calls, runIntervals } = await bootChat(t, { canConfigure: false });

  assert.equal(shown(usageWidget(document)), false, 'il riquadro dei consumi non si vede');
  assert.equal(shown(configureLink(document)), false, 'il link «Configurazione» non si vede');
  await runIntervals();
  assertNoAdminData(calls);
});

test('chat: un «configura» ricordato e poi smentito dal server ferma il giro dei consumi', async (t) => {
  const { document, calls, runIntervals } = await bootChat(t, { canConfigure: false, remembered: '1' });

  assert.equal(shown(usageWidget(document)), false);
  assert.equal(shown(configureLink(document)), false);
  const before = calls.filter((c) => c.url.includes('api/usage')).length;
  await runIntervals();
  assert.equal(calls.filter((c) => c.url.includes('api/usage')).length, before,
    'dopo il «no» del server il giro non chiede piu\' api/usage');
  assert.equal(rememberedConfigure(document), '0', 'e il ricordo diventa il «no» del server');
});

test('chat: senza ricordo e senza risposta, consumi e «Configurazione» restano spenti', async (t) => {
  const { document, calls } = await bootChat(t, { pending: () => new Promise(() => {}) });

  assert.equal(shown(usageWidget(document)), false);
  assert.equal(shown(configureLink(document)), false);
  assertNoAdminData(calls);
});

test('chat: un «configura» ricordato mostra i consumi SUBITO, prima della risposta', async (t) => {
  const { document, calls } = await bootChat(t, { remembered: '1', pending: () => new Promise(() => {}) });

  assert.ok(shown(usageWidget(document)));
  assert.ok(shown(configureLink(document)));
  assert.ok(asked(calls, 'api/usage'), 'il giro dei consumi parte dal ricordo');
});

test('/config: chi non configura trova solo Chat, Impegni e Memoria, e atterra sugli Impegni', async (t) => {
  const { window, document, calls } = await bootConfig(t, { canConfigure: false });

  assert.equal(window.location.hash, '#/agenda');
  assert.equal(document.getElementById('chrome-here').textContent, 'Impegni');
  const visible = [...document.querySelectorAll('#side-nav .nav-item')].filter(shown)
    .map((a) => a.textContent.trim());
  assert.deepEqual(visible, ['Chat', 'Impegni', 'Memoria']);
  const labels = sectionLabels(document).filter(shown).map((l) => l.textContent.trim());
  assert.deepEqual(labels, ['Da fare', 'La casa']);
  assertNoAdminData(calls);
});

for (const [hash, title] of [
  ['#/tree', 'Albero della casa'], ['#/watcher', 'L’osservatore'], ['#/watcher/sapere', 'L’osservatore'],
  ['#/settings', 'Impostazioni chat'], ['#/models', 'Modelli'], ['#/services', 'Servizi'],
  ['#/usage', 'Consumi'],
]) {
  test(`/config: ${hash} per indirizzo dice il rifiuto del server, come testo`, async (t) => {
    const { document, calls } = await bootConfig(t, {
      canConfigure: false, hash, answers: { 'api/models/config': REFUSED },
    });

    const outlet = document.getElementById('route-outlet');
    assert.equal(document.getElementById('chrome-here').textContent, title);
    assert.equal(outlet.querySelector('h1.page-title').textContent, title);
    assert.equal(outlet.querySelector('p.page-subtitle').textContent, HOSTILE);
    assert.equal(outlet.querySelector('img'), null, 'il testo del server non diventa markup');
    assertNoAdminData(calls);
    /* La pagina non si monta: nessuna delle sue letture parte, tranne la
       domanda del rifiuto. */
    const reads = calls.map((c) => c.url).filter((u) => !/^api\/(pending|health|models\/config)$/.test(u));
    assert.deepEqual(reads, []);
  });
}

test('/config: un «configura» ricordato e smentito dal server riporta sugli Impegni', async (t) => {
  const { window, document } = await bootConfig(t, { canConfigure: false, remembered: '1' });

  assert.equal(window.location.hash, '#/agenda');
  assert.equal(document.getElementById('chrome-here').textContent, 'Impegni');
  assert.equal(shown(navItem(document, 'models')), false);
});

test('/config: un «non configura» ricordato e smentito dal server apre la pagina chiesta', async (t) => {
  const { document } = await bootConfig(t, {
    canConfigure: true, remembered: '0', hash: '#/models',
    answers: { 'api/models/config': json(200, {}) },
  });

  assert.equal(document.getElementById('chrome-here').textContent, 'Modelli');
  assert.match(document.getElementById('route-outlet').textContent, /La catena/,
    'dopo il «si\'» del server si monta la pagina vera');
  assert.ok(shown(navItem(document, 'models')));
});

test('Memoria: chi non configura la legge senza «Correggi» ne\' «Dimentica»', async (t) => {
  const { document } = await bootConfig(t, { canConfigure: false, hash: '#/memory' });

  assert.match(document.getElementById('route-outlet').textContent, /Mi piace il caffè/);
  for (const label of ['Correggi', 'Dimentica']) {
    const b = button(document, label);
    assert.ok(!b || !shown(b), `«${label}» non si offre`);
  }
  assert.doesNotMatch(visibleText(document.querySelector('#route-outlet .page-subtitle')), /correggere|cancellare/,
    'il sottotitolo non promette cio\' che la pagina non fa');
});

/* Il testo che si LEGGE: quello dei nodi che nessun antenato spegne. */
function visibleText(root) {
  const walker = root.ownerDocument.createTreeWalker(root, 4);
  let out = '';
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!n.parentElement.closest('[hidden]')) out += n.textContent;
  }
  return out;
}

test('Memoria: i pulsanti disegnati con un ricordo vecchio si spengono alla risposta del server', async (t) => {
  /* La risposta arriva DOPO le card, e la si lascia partire a mano: con un
     ritardo a tempo arrivava prima (misurato con 30 ms: l'avvio del guscio
     in jsdom se li mangia da solo). */
  let answer;
  const late = () => new Promise((resolve) => { answer = () => resolve(json(200, pendingBody(false))); });
  const { document } = await bootConfig(t, { remembered: '1', hash: '#/memory', pending: late });
  assert.ok(shown(button(document, 'Correggi')), 'precondizione: col ricordo i pulsanti nascono accesi');
  answer();
  await settle();

  for (const label of ['Correggi', 'Dimentica']) {
    const b = button(document, label);
    assert.ok(!b || !shown(b), `«${label}» non si offre piu'`);
  }
});

test('pallino: `can_configure` si ricorda come `can_build`, e la risposta del server vince', async (t) => {
  const { document } = await bootConfig(t, { canConfigure: true, remembered: '0' });

  assert.equal(rememberedConfigure(document), '1');
});
