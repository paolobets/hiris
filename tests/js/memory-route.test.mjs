import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick, asAdministrator } from './helpers/dom.mjs';
import { fintoFetch, risposta } from './helpers/fetch.mjs';

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

/* Il pallino c'e' perche' correggere e cancellare sono di chi configura
   (spec 2026-09-27 §4): queste prove guardano un amministratore. */
const SCRIPTS = ['common.js', 'pending-badge.js', 'config/memory-route.js'];

const RICORDO = {
  id: 7,
  testo: "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa",
  detto_da: 'paolo',
  // ISO con l'offset della casa, come lo rende `render_memory` per ogni
  // porta (11/10/2026): 2026-08-02T09:00:00Z.
  detto_il: '2026-08-02T11:00:00+02:00',
  forza: 'preferenza',
  grandezza: 'temperature',
  minimo: 19.0,
  massimo: 20.0,
  unita: '°C',
  corretto_da_utente: false,
  ancore: [
    { tipo: 'area', riferimento: 'sala_pranzo', nome_visto: 'sala', nome_attuale: 'Sala da pranzo', esiste: true,
      nome_mostrato: 'Sala da pranzo', nome_di: 'attuale' },
    { tipo: 'area', riferimento: 'area_rimossa', nome_visto: 'veranda', nome_attuale: null, esiste: false,
      nome_mostrato: 'veranda — non esiste più in Home Assistant. Il ricordo resta valido, ma non è più collegato a niente.',
      nome_di: 'visto' },
    { tipo: 'entita', riferimento: 'sensor.x', nome_visto: 'sensore x', nome_attuale: null, esiste: null,
      nome_mostrato: 'sensore x', nome_di: 'visto' },
  ],
  condizioni: [{ tipo: 'stagione', valore: 'inverno' }, { tipo: 'presenza', valore: 'casa' }],
};

/* Il finto server: risponde a GET/PATCH/DELETE api/memories*. Ogni test rompe
   solo il pezzo che gli interessa, come in settings-route.test.mjs. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  asAdministrator(ctx.window);
  let getCount = 0;
  const chiamate = fintoFetch(ctx.window, {
    'GET api/memories': () => {
      getCount += 1;
      if (opts.getRotto) throw new Error('rete giu\'');
      const corpo = getCount === 1 || !opts.getSuccessivo ? opts.get : opts.getSuccessivo;
      return risposta(corpo !== undefined ? corpo : {
        available: true, memories: [RICORDO], total: 1, shown: 1,
      });
    },
    'PATCH api/memories': () => {
      if (opts.patchRotto) throw new Error('rete giu\'');
      return risposta(opts.patchBody !== undefined ? opts.patchBody : { ok: true }, opts.patchStatus);
    },
    'DELETE api/memories': () => {
      if (opts.deleteRotto) throw new Error('rete giu\'');
      return risposta(opts.deleteBody || {}, opts.deleteStatus !== undefined ? opts.deleteStatus : 204);
    },
  });
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

test('detto_il arriva in ISO con l\'offset e si legge come data; un numero non si indovina', async () => {
  /* La resa del ricordo (`render_memory`) converte l'epoca dell'archivio
     (G-14) nell'ISO con l'offset della casa per ogni porta (11/10/2026).
     Mutazione ESEGUITA: `fmtWhen` di nuovo sull'epoca -- rossa, la data non
     compare e resta «data non disponibile». */
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);
  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /02\/08\/2026/, 'la data del ricordo deve comparire');
  assert.doesNotMatch(testo, /data non disponibile/);

  const altro = montaConServer({ get: {
    available: true, total: 1, shown: 1,
    memories: [Object.assign({}, RICORDO, { detto_il: 1785661200 })],
  } });
  altro.window.HirisMemoryRoute.mount();
  await tick(20);
  assert.match(altro.document.getElementById('route-outlet').textContent,
    /data non disponibile/, 'una forma che non e\' l\'ISO non diventa una data inventata');
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
  assert.match(testo, /veranda.*non esiste più in Home Assistant/s);
});

test('la riga mostra il nome che prepara il server, e l\'id solo nel title', async () => {
  // 08/10/2026 (ux-ui-specialist su Memoria): la pagina ricadeva su
  // `riferimento` e mostrava un id di registro. Il ripiego vive nel server
  // (`render._shown`); qui si mostra `nome_mostrato`. Mutazione ESEGUITA:
  // tornare a `a.nome_attuale || a.nome_visto || a.riferimento` -- rossa.
  const { window, document } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);
  const righe = Array.from(document.querySelectorAll('li'));
  const veranda = righe.find((li) => li.textContent.indexOf('veranda') !== -1);
  assert.ok(veranda, 'deve esserci la riga della veranda');
  assert.doesNotMatch(veranda.textContent, /area_rimossa/, 'l\'id non e\' un nome');
  assert.match(veranda.textContent, /Il ricordo resta valido/);
  assert.equal(veranda.title, 'area_rimossa');
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

  const patch = chiamate.find((c) => c.metodo === 'PATCH');
  assert.ok(patch, 'il click deve mandare un PATCH');
  assert.equal(patch.url, 'api/memories/7');
  assert.equal(patch.opts.headers['X-Requested-With'], 'fetch',
    'senza questo header csrf_middleware risponde 403');
  const corpo = JSON.parse(patch.opts.body);
  assert.deepEqual(corpo, { forza: 'divieto' }, 'solo il campo toccato entra nel corpo');
});

// Collaudo usabilita' 3.22, rilievo 3: il modulo si chiudeva SOLO
// ripremendo «Correggi» -- chi lo apre per sbaglio, o cambia idea, non ha
// una via d'uscita dichiarata. Mutazione ESEGUITA per provarla: togliere
// `cancel.addEventListener('click', chiudiModulo)` (il bottone «Annulla»
// resta a schermo ma non fa niente) -- il test sotto torna rosso
// sull'`assert.equal(outlet.querySelectorAll('select').length, 0, ...)`,
// perche' il modulo non si chiude piu'.
test('«Annulla» chiude il modulo senza mandare nessuna richiesta', async () => {
  const { window, document, chiamate } = montaConServer();
  window.HirisMemoryRoute.mount();
  await tick(20);

  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);

  const outlet = document.getElementById('route-outlet');
  const annulla = bottone(document, 'Annulla', outlet);
  assert.ok(annulla, 'manca il bottone «Annulla» accanto a «Salva correzione»');
  document.querySelector('select').value = 'divieto';

  annulla.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(10);

  assert.equal(outlet.querySelectorAll('select').length, 0,
    '«Annulla» deve chiudere il modulo, non solo restare a schermo inerte');
  assert.equal(chiamate.filter((c) => c.metodo !== 'GET').length, 0,
    '«Annulla» non deve mandare nessuna richiesta di scrittura (ne\' PATCH ne\' altro)');

  // Riaprendo, il modulo riparte dai valori del ricordo, non da quelli
  // scartati con «Annulla»: la modifica non e\' rimasta appesa da nessuna
  // parte fuori dall\'archivio.
  bottone(document, 'Correggi').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(5);
  assert.equal(document.querySelector('select').value, RICORDO.forza,
    'riaprendo dopo «Annulla» il modulo deve mostrare di nuovo il valore vero del ricordo');
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
  assert.equal(chiamate.some((c) => c.metodo === 'DELETE'), false,
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

  const del = chiamate.find((c) => c.metodo === 'DELETE');
  assert.ok(del, 'confermare deve mandare la DELETE');
  assert.equal(del.url, 'api/memories/7');
  assert.equal(del.opts.headers['X-Requested-With'], 'fetch');
  assert.match(document.getElementById('route-outlet').textContent, /Nessun ricordo salvato/,
    'dopo la cancellazione la lista si ricarica dal server');
});

test('una DELETE su un ricordo sparito (404) lo dice come la correzione, e ricarica', async () => {
  /* C-51: il server ora risponde 404 anche alla DELETE. Mutazione che la
     uccide: togliere il ramo 404, e la scheda mostra l'errore del server. */
  const { window, document } = montaConServer({
    deleteStatus: 404,
    deleteBody: { error: 'nessun ricordo con id 7' },
    getSuccessivo: { available: true, memories: [], total: 0, shown: 0 },
  });
  window.HirisMemoryRoute.mount();
  await tick(20);

  window.confirm = () => true;
  bottone(document, 'Dimentica').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /non c.è più: è già stato cancellato altrove/);
  assert.doesNotMatch(testo, /nessun ricordo con id/);
  assert.match(testo, /Nessun ricordo salvato/);
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
