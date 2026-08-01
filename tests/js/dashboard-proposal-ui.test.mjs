import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Plance a proposta: la card deve dire a chiare lettere quando una proposta
   SOSTITUISCE interamente una plancia esistente, e deve esistere un modo per
   tornare indietro (ripristino dell'ultimo snapshot).

   L'affordance di ripristino NON vive piu' nella memoria della pagina: e'
   derivata da GET /api/dashboards/backups, cosi' un replace approvato da
   un'altra schermata la mostra lo stesso e un refresh del browser non la perde.
   Due livelli, decisi guardando `saved_at`:
     - meno di 24 ore  -> undo prominente (striscia .pp-undo-bar, "Annulla");
     - piu' vecchio o `saved_at: null` -> ripristino storico discreto
       (.pp-undo-old), con l'indicazione di QUANDO. */

const DAY_MS = 24 * 60 * 60 * 1000;

/* Istanti calcolati rispetto ad "adesso": una data fissa, invecchiando,
   passerebbe da "recente" a "storico" e cambierebbe l'esito del test. */
function isoAgo(ms) {
  // Il server emette ISO 8601 UTC con offset esplicito "+00:00".
  return new Date(Date.now() - ms).toISOString().replace('Z', '+00:00');
}

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

const okJson = (body) => ({ ok: true, status: 200, json: async () => body });

/* Stub di rete a tre rotte: elenco proposte, elenco snapshot, azioni.
   `state` e' letto a ogni chiamata, cosi' un test puo' far cambiare al server
   la propria risposta a meta' scenario (come fa un apply reale). */
function wireFetch(window, state) {
  const calls = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    calls.push({ url: u, opts: opts || {} });
    if (u.indexOf('/apply') !== -1) {
      if (state.onApply) state.onApply();
      return okJson({ ok: true });
    }
    if (u.indexOf('/restore') !== -1) {
      if (state.onRestore) state.onRestore();
      return okJson({ ok: true });
    }
    if (u.indexOf('dashboards/backups') !== -1) {
      if (state.failBackups) throw new Error('rete giu');
      return okJson({ backups: state.backups || [] });
    }
    if (state.failProposals) throw new Error('rete giu');
    return okJson({ proposals: state.pending || [] });
  };
  return calls;
}

/* init() senza il polling periodico: il setInterval reale terrebbe vivo il
   processo di test e ricaricherebbe a sorpresa durante le asserzioni. */
function initNoPolling(window) {
  const realSI = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  window.HirisChatProposals.init();
  globalThis.setInterval = realSI;
}

test('la card di una sostituzione avvisa che sostituisce interamente', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, { pending: [dashProposal('replace')], backups: [] });

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
  wireFetch(window, { pending: [dashProposal('create')], backups: [] });

  await window.HirisChatProposals.load();
  assert.equal(document.querySelector('#chat-proposals-list .pp-warn'), null);
});

test('uno snapshot recente (< 24h) mostra l\'undo prominente, senza averlo applicato qui', async () => {
  /* Nessun apply in questa pagina: lo snapshot esiste sul server (l\'ha creato
     un\'approvazione fatta altrove, o una sessione precedente del browser).
     L\'affordance deve comparire lo stesso. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, {
    pending: [],
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(5 * 60 * 1000), count: 1 }],
  });

  await window.HirisChatProposals.load();

  const bar = document.querySelector('#chat-proposals-list .pp-undo-bar');
  assert.ok(bar, 'uno snapshot recente deve dare la striscia prominente');
  assert.match(bar.textContent, /casa-mia/);
  const btn = bar.querySelector('[data-pp-undo]');
  assert.ok(btn, 'la striscia deve avere il pulsante di ripristino');
  assert.match(btn.textContent, /Annulla/);
  assert.equal(document.querySelector('.pp-undo-old'), null,
    'uno snapshot recente non e\' un ripristino storico');
});

test('con piu\' versioni la striscia non dichiara la plancia "sostituita"', async () => {
  /* Dopo un primo Annulla la striscia riappare: ma quella plancia e' appena
     stata RIPRISTINATA, non sostituita, e il pulsante porta a una versione
     ancora piu' vecchia. `count > 1` e' il segnale che distingue i due casi:
     il testo deve seguirlo, o promette un annullamento che non e' tale. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, {
    pending: [],
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(5 * 60 * 1000), count: 2 }],
  });

  await window.HirisChatProposals.load();

  const bar = document.querySelector('#chat-proposals-list .pp-undo-bar');
  assert.ok(bar, 'l\'azione resta disponibile e prominente');
  assert.match(bar.textContent, /casa-mia/);
  assert.ok(!/sostituit/i.test(bar.textContent),
    'con piu\' di uno snapshot non si puo\' affermare che la plancia sia stata sostituita');
  assert.match(bar.textContent, /ancora precedente/,
    'va detto che si torna a una versione ancora anteriore');
  assert.ok(bar.querySelector('[data-pp-undo]'), 'il ripristino resta un click');
});

test('uno snapshot piu\' vecchio di 24h e\' storico, discreto e con la data leggibile', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const treGiorniFa = new Date(Date.now() - 3 * DAY_MS);
  wireFetch(window, {
    pending: [],
    backups: [{ url_path: 'vecchia', saved_at: isoAgo(3 * DAY_MS), count: 2 }],
  });

  await window.HirisChatProposals.load();

  assert.equal(document.querySelector('.pp-undo-bar'), null,
    'uno snapshot vecchio non deve avere il peso visivo dell\'undo recente');
  const row = document.querySelector('#chat-proposals-list .pp-undo-old');
  assert.ok(row, 'uno snapshot vecchio deve comparire come ripristino storico');
  assert.match(row.textContent, /vecchia/);
  assert.ok(row.querySelector('[data-pp-undo]'), 'da li\' si deve poter comunque ripristinare');

  // Deve dire QUANDO, in forma leggibile: mai l'ISO grezzo.
  assert.ok(row.textContent.indexOf(String(treGiorniFa.getFullYear())) !== -1,
    'la data deve indicare l\'anno');
  assert.ok(row.textContent.indexOf(String(treGiorniFa.getDate()).padStart(2, '0')) !== -1,
    'la data deve indicare il giorno');
  assert.ok(!/\d{4}-\d{2}-\d{2}T/.test(row.textContent), 'mai l\'ISO grezzo in interfaccia');
});

test('saved_at null dichiara che la data non e\' disponibile, senza inventarla', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, {
    pending: [],
    backups: [{ url_path: 'antica', saved_at: null, count: 1 }],
  });

  await window.HirisChatProposals.load();

  const row = document.querySelector('#chat-proposals-list .pp-undo-old');
  assert.ok(row, 'senza istante lo snapshot vale come il piu\' vecchio: storico');
  assert.match(row.textContent, /non disponibile/i,
    'deve dirlo, non lasciare il vuoto');
  assert.ok(!/\d{4}/.test(row.textContent), 'nessuna data inventata');
  assert.ok(!/Invalid|NaN|null|undefined/.test(row.textContent), 'niente valori tecnici a schermo');
});

test('il ripristino chiama l\'endpoint giusto e fa sparire la voce', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const state = {
    pending: [],
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(60 * 1000), count: 1 }],
  };
  // Come il server reale: un ripristino riuscito consuma lo snapshot, che da
  // quel momento e' lo stato corrente della plancia e non e' piu' elencato.
  state.onRestore = () => { state.backups = []; };
  const calls = wireFetch(window, state);
  window.confirm = () => true;
  window.alert = () => {};

  initNoPolling(window);
  await tick(20);

  const btn = document.querySelector('.pp-undo-bar [data-pp-undo]');
  assert.ok(btn, 'la striscia di undo deve esserci');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const restore = calls.find((c) => c.url.indexOf('/restore') !== -1);
  assert.ok(restore, 'il ripristino deve chiamare l\'endpoint di restore');
  assert.match(restore.url, /api\/dashboards\/casa-mia\/restore$/);
  assert.equal(restore.opts.method, 'POST');

  assert.equal(document.querySelector('[data-pp-undo]'), null,
    'dopo il ripristino la voce sparisce');
  await window.HirisChatProposals.load();
  assert.equal(document.querySelector('[data-pp-undo]'), null,
    'e non torna al ricaricamento: il server non elenca piu\' quello snapshot');
});

test('la voce sparisce perche\' il server non la elenca piu\', non perche\' la pagina se lo ricorda', async () => {
  /* Nessuna memoria di sessione lato pagina: se lo snapshot restasse elencato
     dal server, l'affordance dovrebbe tornare visibile appena l'elenco viene
     riletto. E' il contrario del vecchio comportamento (voce nascosta in
     locale e ricordata per sempre), che dopo un refresh riproponeva di
     annullare cio' che era gia' stato annullato: una sola fonte di verita',
     quella del server.
     La cache locale viene sfoltita subito dopo un ripristino riuscito, ma solo
     per recepire cio' che il server ha appena confermato: se poi il server
     smentisce continuando a elencare la voce, vince il server. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  // Server che NON consuma (caso degenere): l'elenco resta popolato.
  wireFetch(window, {
    pending: [],
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(60 * 1000), count: 1 }],
  });
  window.confirm = () => true;
  window.alert = () => {};

  initNoPolling(window);
  await tick(20);

  document.querySelector('.pp-undo-bar [data-pp-undo]').dispatchEvent(
    new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.ok(document.querySelector('[data-pp-undo]'),
    'la pagina non deve nascondere per conto suo cio\' che il server continua a elencare');

  // E non se lo ricorda nemmeno piu' avanti: nessuna lista di "gia' annullati"
  // che sopravviva ai ricaricamenti successivi.
  await window.HirisChatProposals.load();
  assert.ok(document.querySelector('[data-pp-undo]'),
    'a ogni ricaricamento l\'affordance va riderivata dall\'elenco del server');
});

test('dopo un ripristino riuscito la voce non ricompare se l\'aggiornamento fallisce', async () => {
  /* Il server ha consumato lo snapshot: e' un fatto acquisito. Se la richiesta
     di aggiornamento dell'elenco fallisce, `loadBackups` tiene l'ultimo elenco
     noto (giusto: un'azione ancora possibile non deve sparire per un errore di
     rete) - ma quella voce non e' piu' possibile. Lasciarla a schermo farebbe
     credere che il click non abbia funzionato: si riclicca e, se esiste uno
     snapshot piu' vecchio, si scende di un'altra versione senza volerlo. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const state = {
    pending: [],
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(60 * 1000), count: 2 }],
  };
  // Il ripristino riesce, ma da li' in poi l'elenco non si carica piu'.
  state.onRestore = () => { state.failBackups = true; };
  const calls = wireFetch(window, state);
  window.confirm = () => true;
  window.alert = () => {};

  initNoPolling(window);
  await tick(20);
  assert.ok(document.querySelector('.pp-undo-bar [data-pp-undo]'), 'la striscia deve esserci');

  document.querySelector('.pp-undo-bar [data-pp-undo]').dispatchEvent(
    new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(document.querySelector('[data-pp-undo]'), null,
    'la voce appena consumata dal server non deve restare cliccabile');

  // Anche insistendo con i ricaricamenti: finche' l'elenco non torna, quella
  // voce resta fuori. E nessun secondo /restore puo' essere partito.
  await window.HirisChatProposals.load();
  assert.equal(document.querySelector('[data-pp-undo]'), null,
    'nemmeno un ricaricamento fallito la deve far ricomparire');
  assert.equal(calls.filter((c) => c.url.indexOf('/restore') !== -1).length, 1,
    'un solo ripristino: non si deve poter scendere di un\'altra versione');
});

test('il rendering delle strisce e\' idempotente: due load non duplicano nulla', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, {
    pending: [dashProposal('replace')],
    backups: [
      { url_path: 'casa-mia', saved_at: isoAgo(10 * 60 * 1000), count: 1 },
      { url_path: 'vecchia', saved_at: isoAgo(5 * DAY_MS), count: 1 },
    ],
  });

  await window.HirisChatProposals.load();
  await window.HirisChatProposals.load();

  assert.equal(document.querySelectorAll('.pp-undo-bar').length, 1);
  assert.equal(document.querySelectorAll('.pp-undo-old').length, 1);
  assert.equal(document.querySelectorAll('[data-pp-undo]').length, 2);
});

test('un errore nel caricamento delle proposte non cancella le strisce', async () => {
  /* Il ripristino resta un\'azione possibile anche se l\'elenco delle proposte
     non si carica: non deve sparire dallo schermo. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  wireFetch(window, {
    failProposals: true,
    backups: [{ url_path: 'casa-mia', saved_at: isoAgo(60 * 1000), count: 1 }],
  });

  await window.HirisChatProposals.load();
  await tick(10);

  assert.match(document.getElementById('chat-proposals-list').textContent, /Errore nel caricamento/);
  assert.ok(document.querySelector('.pp-undo-bar'),
    'l\'undo deve sopravvivere all\'errore di caricamento delle proposte');
});

test('una proposta NON di plancia con mode=replace non porta a un ripristino', async () => {
  /* Cancello di isolamento: solo una plancia realmente sostituita puo' finire
     su /api/dashboards/.../restore. Ora la verita' e' del server (l'elenco
     degli snapshot), ma la garanzia va pinnata lo stesso: un'altra proposta con
     un config omonimo (stesse chiavi, altro significato) non deve ne' essere
     trattata come sostituzione di plancia, ne' far comparire un ripristino. */
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const impostor = {
    id: 'p2', type: 'ha_automation', name: 'Luci sera', description: 'x',
    config: { kind: 'automation', mode: 'replace', slug: 'casa-mia' },
  };
  // Applicare un'automazione non crea snapshot di plancia: l'elenco resta vuoto.
  const calls = wireFetch(window, { pending: [impostor], backups: [] });
  window.confirm = () => true;
  window.alert = () => {};

  initNoPolling(window);
  await tick(10);

  const card = document.querySelector('.pp-card');
  assert.ok(card, 'la proposta deve comunque essere renderizzata');
  assert.equal(document.querySelector('.pp-warn'), null, 'niente avviso di sostituzione plancia');

  document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(document.querySelector('[data-pp-undo]'), null,
    'nessun ripristino per un tipo diverso da ha_dashboard');
  assert.equal(calls.find((c) => c.url.indexOf('/restore') !== -1), undefined,
    'nessuna chiamata a /restore');
});

test('l\'undo sopravvive al ricaricamento della lista e sparisce dopo il ripristino', async () => {
  const { window, document } = loadScripts(
    ['config/api.js', 'config/proposals-core.js', 'chat/proposals.js'],
    { html: fixtureHtml() },
  );
  const state = { pending: [dashProposal('replace')], backups: [] };
  state.onApply = () => {
    // Come il server reale: l'apply in mode replace salva lo snapshot e
    // la proposta non e' piu' in attesa.
    state.pending = [];
    state.backups = [{ url_path: 'casa-mia', saved_at: isoAgo(0), count: 1 }];
  };
  // ...e un ripristino riuscito lo consuma: torna a essere lo stato corrente.
  state.onRestore = () => { state.backups = []; };
  wireFetch(window, state);
  window.confirm = () => true;
  window.alert = () => {};

  initNoPolling(window);
  await tick(10);

  document.querySelector('.pp-apply').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.ok(document.querySelector('.pp-undo-bar'),
    'subito dopo l\'apply l\'undo deve comparire, senza aspettare il polling');

  // Il polling periodico (o il rientro nel pannello) ricarica la lista: la
  // proposta applicata sparisce, l'azione di ripristino no.
  await window.HirisChatProposals.load();
  assert.ok(document.querySelector('.pp-undo-bar'), 'l\'undo deve sopravvivere a un load()');
  assert.equal(document.querySelector('.pp-card'), null, 'la proposta applicata non e\' piu\' in attesa');
  assert.equal(document.getElementById('proposals-badge').dataset.count, '0', 'il badge deve aggiornarsi');

  document.querySelector('.pp-undo-bar [data-pp-undo]').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.equal(document.querySelector('[data-pp-undo]'), null, 'dopo il ripristino l\'undo sparisce');
});
