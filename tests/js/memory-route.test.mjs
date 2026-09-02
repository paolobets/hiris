import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* fetta E5 Task 9: la pagina #/memory (config/memory-route.js). Sostituisce
   il pannello Memoria della chat (coda di approvazione, uscita con questo
   stesso task) e interroga l'archivio vero (GET/PATCH/DELETE /api/memories*).

   Tre cose non negoziabili, dettate dal brief e da handlers_memory.py:
   - `ancora.esiste === null` ("non ho potuto controllare") non si legge come
     un'ancora cancellata;
   - un PATCH rifiutato mostra la ragione che manda il server, non un errore
     generico;
   - `mostrati < total` si dichiara, cosi' un ricordo oltre il taglio non
     sembra sparito. */

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/memory-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const RICORDO = {
  id: 7,
  testo: "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa",
  detto_da: 'paolo',
  detto_il: '2026-08-02T09:00:00Z',
  forza: 'preferenza',
  grandezza: 'temperature',
  minimo: 19.0,
  massimo: 20.0,
  unita: '°C',
  corretto_da_utente: false,
  ancore: [
    { tipo: 'area', riferimento: 'sala_pranzo', nome_visto: 'sala', nome_attuale: 'Sala da pranzo', esiste: true },
    { tipo: 'area', riferimento: 'area_rimossa', nome_visto: 'veranda', nome_attuale: null, esiste: false },
    { tipo: 'entita', riferimento: 'sensor.x', nome_visto: 'sensore x', nome_attuale: null, esiste: null },
  ],
  condizioni: [{ tipo: 'stagione', valore: 'inverno' }, { tipo: 'presenza', valore: 'casa' }],
};

/* Il finto server: risponde a GET/PATCH/DELETE api/memories*. Ogni test rompe
   solo il pezzo che gli interessa, come in settings-route.test.mjs. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  let getCount = 0;
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    const method = (options || {}).method || 'GET';
    chiamate.push({ url: u, method, opts: options || {} });
    if (method === 'GET') {
      getCount += 1;
      if (opts.getRotto) throw new Error('rete giu\'');
      const corpo = getCount === 1 || !opts.getSuccessivo ? opts.get : opts.getSuccessivo;
      return jsonResponse(corpo !== undefined ? corpo : {
        available: true, memories: [RICORDO], total: 1, shown: 1,
      });
    }
    if (method === 'PATCH') {
      if (opts.patchRotto) throw new Error('rete giu\'');
      return jsonResponse(opts.patchBody !== undefined ? opts.patchBody : { ok: true }, opts.patchStatus);
    }
    if (method === 'DELETE') {
      if (opts.deleteRotto) throw new Error('rete giu\'');
      return jsonResponse(opts.deleteBody || {}, opts.deleteStatus !== undefined ? opts.deleteStatus : 204);
    }
    throw new Error('metodo inatteso: ' + method);
  };
  return Object.assign(ctx, { chiamate, getCount: () => getCount });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
}

// ---------------------------------------------------------------------------
// Mostrare: la frase, l'interpretazione, le ancore nei loro tre stati
// ---------------------------------------------------------------------------

test('mount: mostra la frase e cosa HIRIS ha capito', async () => {
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /d'inverno la sala da pranzo/, 'la frase esatta deve comparire');
  assert.match(testo, /temperature/, 'la grandezza deve comparire');
  assert.match(testo, /19.*20.*°C|fra 19 e 20 °C/, 'l\'intervallo con unità deve comparire');
  assert.match(testo, /stagione: inverno/);
  assert.match(testo, /presenza: casa/);
});

test('un\'ancora viva mostra il nome che l\'anagrafe conosce OGGI, non quello congelato', async () => {
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Sala da pranzo/, 'il nome attuale deve comparire');
  assert.doesNotMatch(testo, /\bsala\b(?!.*Sala da pranzo)/, 'non il solo nome congelato');
});

test('un\'ancora sparita dall\'anagrafe (esiste: false) lo dice', async () => {
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /veranda.*non esiste più nell.anagrafe/s);
});

test('«esiste: null» non si legge come un\'ancora cancellata (non ho potuto controllare vs non c\'è più)', async () => {
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  // Ogni ancora e' un <li> a se': si confronta il testo di QUELLA riga, non
  // l'intera pagina (dove "non esiste più" compare comunque, detto della
  // veranda) -- altrimenti i due stati si confonderebbero nel test come si
  // vuole che non si confondano nella pagina.
  const righe = Array.from(document.querySelectorAll('li')).map((li) => li.textContent);
  const rigaSensoreX = righe.find((r) => r.indexOf('sensore x') !== -1);
  assert.ok(rigaSensoreX, 'deve esserci una riga per l\'ancora non verificabile');
  assert.match(rigaSensoreX, /non è stato possibile verificarlo/,
    '"non ho potuto controllare" deve essere il testo per esiste:null');
  assert.doesNotMatch(rigaSensoreX, /non esiste più/,
    'un\'ancora mai verificata non deve dire "non esiste più"');
});

// ---------------------------------------------------------------------------
// Il taglio a 200 (qui: a `mostrati`) si dichiara
// ---------------------------------------------------------------------------

test('quando mostrati < totale, la pagina lo dichiara', async () => {
  const { window, document } = montaConServer({
    get: { available: true, memories: [RICORDO], total: 5, shown: 1 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent,
    /1 ricordi? più recenti su 5/);
});

test('quando mostrati === totale, non si inventa un taglio che non c\'è', async () => {
  const { window, document } = montaConServer({
    get: { available: true, memories: [RICORDO], total: 1, shown: 1 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.doesNotMatch(testo, /più recenti su/);
  assert.match(testo, /1 ricordo\./);
});

// ---------------------------------------------------------------------------
// Vuoto, non disponibile, illeggibile: tre cose diverse
// ---------------------------------------------------------------------------

test('nessun ricordo: lo dice, distinto da "non disponibile" e da "errore"', async () => {
  const { window, document } = montaConServer({
    get: { available: true, memories: [], total: 0, shown: 0 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent, /Nessun ricordo salvato/);
});

test('archivio non available: non si afferma "zero ricordi" come un fatto accertato', async () => {
  const { window, document } = montaConServer({
    get: { available: false, memories: [] },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /non è disponibile/);
  assert.doesNotMatch(testo, /Nessun ricordo salvato/,
    'l\'archivio assente non deve sembrare una memoria vuota');
});

test('un errore di rete si dichiara, e offre un modo di riprovare', async () => {
  const { window, document } = montaConServer({ getRotto: true });
  window.HirisMemoryRoute.mount();
  await tick(20);

  const outlet = document.getElementById('route-outlet');
  assert.match(outlet.textContent, /Non è stato possibile leggere i ricordi/);
  assert.doesNotMatch(outlet.textContent, /Nessun ricordo salvato/);
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare');
});

// ---------------------------------------------------------------------------
// La correzione: solo l'interpretazione, mai il testo
// ---------------------------------------------------------------------------

test('«Correggi» apre un modulo senza campo per il testo, e Salva manda un PATCH con solo i campi cambiati', async () => {
  const { window, document, chiamate } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);

  const outlet = document.getElementById('route-outlet');
  assert.equal(outlet.querySelectorAll('textarea').length, 0, 'nessun campo per il testo');
  const selForza = outlet.querySelector('select');
  assert.ok(selForza, 'la forza si corregge da una tenda chiusa (vocabolario)');
  selForza.value = 'divieto';

  bottone(document, 'Salva correzione').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const patch = chiamate.find((c) => c.method === 'PATCH');
  assert.ok(patch, 'il click deve mandare un PATCH');
  assert.equal(patch.url, 'api/memories/7');
  assert.equal(patch.opts.headers['X-Requested-With'], 'fetch',
    'senza questo header csrf_middleware risponde 403');
  const corpo = JSON.parse(patch.opts.body);
  assert.deepEqual(corpo, { forza: 'divieto' }, 'solo il campo toccato entra nel corpo');
});

test('un PATCH rifiutato (400) mostra la ragione del server, non un errore generico', async () => {
  const { window, document } = montaConServer({
    patchStatus: 400,
    patchBody: { error: 'ancora area «veranda» non esiste nell\'anagrafe -- scartata', problemi: ['x'] },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);
  document.querySelector('select').value = 'divieto';
  bottone(document, 'Salva correzione').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /non esiste nell'anagrafe/, 'la ragione del server deve arrivare all\'utente');
  assert.doesNotMatch(testo, /Correzione salvata/, 'un rifiuto non deve mai sembrare un successo');
});

test('un PATCH su un ricordo sparito (404) lo dice e ricarica la lista', async () => {
  const { window, document } = montaConServer({
    patchStatus: 404,
    patchBody: { error: 'nessun ricordo con id 7' },
    getSuccessivo: { available: true, memories: [], total: 0, shown: 0 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);
  document.querySelector('select').value = 'divieto';
  bottone(document, 'Salva correzione').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /non c.è più/, 'deve dire che il ricordo non c\'è più');
  assert.match(testo, /Nessun ricordo salvato/, 'e ricaricare: la lista ora e\' vuota davvero');
});

test('una correzione accettata con un raddrizzamento lo dichiara, invece di tacerlo', async () => {
  const { window, document } = montaConServer({
    patchBody: { ok: true, correzioni: ['minimo (25.0) maggiore di massimo (20.0): intervallo invertito -- raddrizzato'] },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);
  document.querySelector('select').value = 'divieto';
  bottone(document, 'Salva correzione').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent, /intervallo invertito/);
});

// ---------------------------------------------------------------------------
// La cancellazione: distruttiva, quindi esplicita e mai accidentale
// ---------------------------------------------------------------------------

test('«Dimentica» chiede conferma mostrando la frase esatta, e annullare non manda nulla', async () => {
  const { window, document, chiamate } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  let messaggioConferma = null;
  window.confirm = (m) => { messaggioConferma = m; return false; };

  bottone(document, 'Dimentica').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(10);

  assert.ok(messaggioConferma, 'deve chiedere conferma esplicita');
  assert.match(messaggioConferma, /d'inverno la sala da pranzo/,
    'la conferma deve mostrare cosa si sta per cancellare, non un generico "sei sicuro?"');
  assert.equal(chiamate.some((c) => c.method === 'DELETE'), false,
    'annullare la conferma non deve mandare nessuna richiesta');
});

test('confermare la cancellazione manda una DELETE con X-Requested-With, e ricarica', async () => {
  const { window, document, chiamate } = montaConServer({
    getSuccessivo: { available: true, memories: [], total: 0, shown: 0 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  window.confirm = () => true;
  bottone(document, 'Dimentica').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const del = chiamate.find((c) => c.method === 'DELETE');
  assert.ok(del, 'confermare deve mandare la DELETE');
  assert.equal(del.url, 'api/memories/7');
  assert.equal(del.opts.headers['X-Requested-With'], 'fetch');
  assert.match(document.getElementById('route-outlet').textContent, /Nessun ricordo salvato/,
    'dopo la cancellazione la lista si ricarica dal server');
});

test('un errore di rete sulla DELETE si vede, mai un catch vuoto', async () => {
  const { window, document } = montaConServer({ deleteRotto: true });
  window.HirisMemoryRoute.mount();
  await tick(20);

  window.confirm = () => true;
  bottone(document, 'Dimentica').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent, /non ha risposto/);
});
