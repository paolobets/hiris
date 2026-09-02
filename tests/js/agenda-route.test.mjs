import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* fetta «lo schedulatore» Task 9: la pagina #/promesse (config/agenda-route.js).
   Chiude la terza condizione della spec (§10): «Si vede. Un posto dove guardare
   cosa e' in sospeso e annullarlo.» Legge UNA sola GET /api/agenda?all=1 e
   filtra lato client per `stato` -- lo stato e' un campo della stessa lista,
   non due mondi (progetto, guida di disegno §1).

   Tre cose non negoziabili, dettate dalla guida di disegno e da
   handlers_agenda.py/archivio.py:
   - la DELETE riuscita risponde 200 con {"promessa": {...}}, MAI 204 come
     /api/memories/{id} -- un test lo pinza sotto;
   - il vocabolario mostrato non e' quello del backend: `saltata` -> «Non
     eseguita», `fallita` -> «Non riuscita» (guida §0/§3);
   - nessun window.confirm() per disdire: e' reversibile (chiedendo di nuovo a
     voce) e la riga non sparisce, passa allo storico. */

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/agenda-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const PROMESSE = [
  {
    id: 'p1', specie: 'fai', frase: 'alle 17 accendi lo studio',
    quando_ts: 1755600000, quando_detto: 'alle 17', fuso: 'Europe/Rome',
    chiamata: { servizio: 'light.turn_on' }, domanda: null, istantanea: null,
    recapito: null, stato: 'in_attesa', motivo: null, esecuzione_id: null,
    testo: null, avvisare: null, nata_ts: 1755590000, risvegliata_ts: null, origine: null,
  },
  {
    id: 'p2', specie: 'chiedi', frase: 'verifica la temperatura',
    quando_ts: 1755500000, quando_detto: 'fra un\'ora', fuso: 'Europe/Rome',
    chiamata: null, domanda: 'com\'e\' la temperatura del salotto?', istantanea: null,
    recapito: null, stato: 'saltata',
    motivo: 'scaduta da 41 minuti quando l\'orologio l\'ha vista -- non eseguita.',
    esecuzione_id: null, testo: null, avvisare: null,
    nata_ts: 1755490000, risvegliata_ts: 1755500100, origine: null,
  },
  {
    id: 'p3', specie: 'chiedi', frase: 'posso aprire le finestre?',
    quando_ts: 1755400000, quando_detto: 'fra due ore', fuso: 'Europe/Rome',
    chiamata: null, domanda: 'la temperatura esterna e\' sotto i 25 gradi?',
    istantanea: [{ entita: 'sensor.temp_esterna', valore: 31, unita: '°C' }],
    recapito: null, stato: 'mantenuta', motivo: null, esecuzione_id: 'e1',
    testo: 'no: fuori ci sono 31 gradi', avvisare: false,
    nata_ts: 1755390000, risvegliata_ts: 1755400050, origine: null,
  },
];

/* Una riga di cronaca (`Journal.leggi`, action/journal.py::_riga), per i
   test del pannello «Cosa è cambiato». */
function esecuzione(campi) {
  return Object.assign({
    id: 'e9', quando_ts: 1755400100, origine: 'schedulatore',
    servizio: 'light.turn_on', entita: ['light.studio'], eseguito: true,
    cambiato: ['light.studio'], errore: null, avviso: null,
  }, campi || {});
}

/* Il finto server: risponde a GET/DELETE api/agenda*, stesso pattern di
   montaConServer() in memory-route.test.mjs. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  let getCount = 0;
  let esecuzioneCount = 0;
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    const method = (options || {}).method || 'GET';
    chiamate.push({ url: u, method, opts: options || {} });
    if (method === 'GET' && u.indexOf('api/executions/') === 0) {
      esecuzioneCount += 1;
      if (opts.esecuzioneRotta) throw new Error('rete giu\'');
      if (opts.esecuzione404) {
        return jsonResponse({ error: 'non ho nessuna esecuzione con quell\'identificatore.' }, 404);
      }
      return jsonResponse(opts.execution !== undefined ? opts.execution : { execution: esecuzione() });
    }
    if (method === 'GET') {
      getCount += 1;
      if (opts.getRotto) throw new Error('rete giu\'');
      if (opts.get503) return jsonResponse({ agenda: [], error: 'archivio non disponibile' }, 503);
      const corpo = getCount === 1 || opts.getSuccessivo === undefined ? opts.get : opts.getSuccessivo;
      return jsonResponse(corpo !== undefined ? corpo : { agenda: PROMESSE });
    }
    if (method === 'DELETE') {
      if (opts.deleteRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.deleteBody !== undefined ? opts.deleteBody : { promessa: { ...PROMESSE[0], stato: 'disdetta' } },
        opts.deleteStatus !== undefined ? opts.deleteStatus : 200);
    }
    throw new Error('metodo inatteso: ' + method);
  };
  return Object.assign(ctx, { chiamate });
}

async function monta(opts) {
  const { window, document, chiamate } = montaConServer(opts);
  window.HirisAgendaRoute.mount();
  await tick(20);
  return { window, document, chiamate };
}

// ---------------------------------------------------------------------------
// I cinque test del brief (Task 9, step 1)
// ---------------------------------------------------------------------------

test('le in sospeso e lo storico stanno in due sezioni distinte', async () => {
  const { document } = await monta();
  const sospeso = document.querySelector('[data-sezione="in-sospeso"]');
  const storico = document.querySelector('[data-sezione="storico"]');
  assert.ok(sospeso, 'deve esistere la sezione in sospeso');
  assert.ok(storico, 'deve esistere la sezione storico');
  assert.ok(sospeso.textContent.includes('accendi lo studio'));
  assert.ok(!sospeso.textContent.includes('verifica la temperatura'));
  assert.ok(storico.textContent.includes('verifica la temperatura'));
});

test('una promessa saltata mostra il motivo, non solo lo stato', async () => {
  const { document } = await monta();
  assert.ok(document.body.textContent.includes('41 minuti'));
  assert.match(document.body.textContent, /Non eseguita/, 'il vocabolario a schermo, non "saltata"');
});

test('un chiedi concluso in silenzio mostra comunque cio\' che ha trovato', async () => {
  const { document } = await monta();
  assert.ok(document.body.textContent.includes('31 gradi'));
});

test('solo le in sospeso hanno il bottone per disdire', async () => {
  const { document } = await monta();
  const bottoni = document.querySelectorAll('[data-disdici]');
  assert.equal(bottoni.length, 1);
  assert.equal(bottoni[0].getAttribute('data-disdici'), 'p1');
});

test('senza promesse la pagina lo dice invece di restare bianca', async () => {
  const { document } = await monta({ get: { agenda: [] } });
  assert.ok(document.body.textContent.trim().length > 0);
  assert.match(document.body.textContent, /nessuna promessa/i);
});

// ---------------------------------------------------------------------------
// `in_corso`: sta in "In sospeso" come `in_attesa`, ma senza il bottone
// (review Task 9, rilievo 1 -- il commento di testa del file lo dichiara
// "non negoziabile" ma nessuna fixture lo esercitava).
// ---------------------------------------------------------------------------

test('in_corso sta in "In sospeso" insieme a in_attesa, ma senza il bottone per disdire', async () => {
  const { document } = await monta({
    get: {
      agenda: [
        PROMESSE[0], // p1, in_attesa
        { ...PROMESSE[0], id: 'p5', frase: 'sto accendendo il forno', stato: 'in_corso' },
      ],
    },
  });
  const sospeso = document.querySelector('[data-sezione="in-sospeso"]');
  assert.ok(sospeso.textContent.includes('sto accendendo il forno'),
    'in_corso non e\' ancora concluso: deve stare in "In sospeso"');
  const storico = document.querySelector('[data-sezione="storico"]');
  assert.ok(!storico.textContent.includes('sto accendendo il forno'),
    'in_corso non deve finire nello storico: sparirebbe e ricomparirebbe a ogni ricaricamento');

  const bottoni = document.querySelectorAll('[data-disdici]');
  assert.equal(bottoni.length, 1, 'solo p1 (in_attesa) deve avere il bottone');
  assert.equal(bottoni[0].getAttribute('data-disdici'), 'p1');
  assert.equal(document.querySelector('[data-disdici="p5"]'), null,
    'archivio.disdici() scrive WHERE stato=\'in_attesa\': un bottone su in_corso sarebbe piu\' ' +
    'confuso di nessun bottone');
});

// ---------------------------------------------------------------------------
// «Mantenuta con motivo»: HIRIS aveva qualcosa da dire e nessun canale per
// venire a cercarti (spec §6, guida di disegno §3) -- non e' un settimo
// stato: badge verde (e' successo davvero), motivo comunque visibile in
// ambra sotto (review Task 9, rilievo 2).
// ---------------------------------------------------------------------------

test('una promessa mantenuta con motivo resta badge verde, ma il motivo si vede comunque', async () => {
  const { document } = await monta({
    get: {
      agenda: [{
        ...PROMESSE[0], id: 'p6', specie: 'fai', frase: 'accendi le luci del giardino',
        stato: 'mantenuta',
        motivo: 'nessun modo di avvisarti: non avevi lasciato un canale per farlo.',
      }],
    },
  });
  const testo = document.body.textContent;
  assert.match(testo, /nessun modo di avvisarti/, 'il motivo deve essere visibile, non taciuto');

  const badge = Array.from(document.querySelectorAll('.agent-badge'))
    .find((b) => b.textContent === 'Mantenuta');
  assert.ok(badge, 'il badge deve restare quello del successo, "Mantenuta"');
  assert.ok(badge.classList.contains('badge-on'), 'verde: e\' successo davvero, non e\' un fallimento');
  assert.ok(!badge.classList.contains('badge-err') && !badge.classList.contains('badge-warn'),
    'il badge non diventa ne\' rosso ne\' ambra: la sfumatura sta nel colore del testo del motivo, ' +
    'non nel badge (guida §3)');
});

// ---------------------------------------------------------------------------
// Vocabolario: due parole deliberatamente diverse, non due rime
// ---------------------------------------------------------------------------

test('una promessa fallita dice «Non riuscita», mai «Non eseguita»', async () => {
  const { document } = await monta({
    get: { agenda: [{ ...PROMESSE[1], id: 'p4', stato: 'fallita', motivo: 'il servizio ha rifiutato la chiamata' }] },
  });
  const testo = document.body.textContent;
  assert.match(testo, /Non riuscita/);
  assert.doesNotMatch(testo, /Non eseguita/);
});

test('il badge di "Non eseguita" non e\' rosso: e\' una scelta del prodotto, non un guasto', async () => {
  const { document } = await monta();
  const badge = Array.from(document.querySelectorAll('.agent-badge'))
    .find((b) => b.textContent === 'Non eseguita');
  assert.ok(badge, 'deve esistere il badge "Non eseguita"');
  assert.ok(badge.classList.contains('badge-warn'), 'ambra, non rosso: classList=' + badge.className);
  assert.ok(!badge.classList.contains('badge-err'));
});

// ---------------------------------------------------------------------------
// Ordine: la prossima cosa prima nel sospeso, la piu' recente prima nello storico
// ---------------------------------------------------------------------------

test('in sospeso l\'ordine e\' per quando_ts crescente (la prossima prima)', async () => {
  const { document } = await monta({
    get: {
      agenda: [
        { ...PROMESSE[0], id: 'a', frase: 'la piu\' tardiva', quando_ts: 1755700000 },
        { ...PROMESSE[0], id: 'b', frase: 'la piu\' vicina', quando_ts: 1755600000 },
      ],
    },
  });
  const sospeso = document.querySelector('[data-sezione="in-sospeso"]');
  const idxVicina = sospeso.textContent.indexOf('la piu\' vicina');
  const idxTardiva = sospeso.textContent.indexOf('la piu\' tardiva');
  assert.ok(idxVicina >= 0 && idxTardiva >= 0);
  assert.ok(idxVicina < idxTardiva, 'la prossima a scattare deve comparire prima');
});

test('nello storico l\'ordine e\' per quando_ts decrescente (la piu\' recente prima)', async () => {
  const { document } = await monta();
  const storico = document.querySelector('[data-sezione="storico"]');
  // p2 (quando_ts 1755500000) e' piu' recente di p3 (1755400000).
  const idxP2 = storico.textContent.indexOf('verifica la temperatura');
  const idxP3 = storico.textContent.indexOf('posso aprire le finestre');
  assert.ok(idxP2 >= 0 && idxP3 >= 0);
  assert.ok(idxP2 < idxP3);
});

// ---------------------------------------------------------------------------
// Nessuna conferma per disdire
// ---------------------------------------------------------------------------

test('«Disdici» non chiede conferma: manda subito la DELETE', async () => {
  const { window, document, chiamate } = await monta();
  let confirmChiamato = false;
  window.confirm = () => { confirmChiamato = true; return true; };

  const bottone = document.querySelector('[data-disdici="p1"]');
  bottone.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(confirmChiamato, false, 'nessun window.confirm() per disdire');
  const del = chiamate.find((c) => c.method === 'DELETE');
  assert.ok(del, 'il click deve mandare subito la DELETE');
  assert.equal(del.url, 'api/agenda/p1');
  assert.equal(del.opts.headers['X-Requested-With'], 'fetch',
    'senza questo header csrf_middleware risponde 403');
});

test('la DELETE riuscita (200, non 204) ricarica l\'elenco e conferma sulla riga di stato', async () => {
  const { window, document } = await monta({
    deleteStatus: 200,
    deleteBody: { promessa: { ...PROMESSE[0], stato: 'disdetta' } },
    // Dopo la disdetta il ricaricamento vede la lista vera: p1 non e' piu'
    // fra le in sospeso (l'archivio ora la darebbe 'disdetta'). Il PRIMO
    // GET (al mount) deve invece portare ancora p1 in_attesa, altrimenti
    // il bottone da cliccare non esiste nemmeno.
    getSuccessivo: { agenda: [] },
  });
  document.querySelector('[data-disdici="p1"]').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  const testo = document.body.textContent;
  assert.match(testo, /Promessa disdetta/,
    'trappola del brief: la DELETE risponde 200 con un corpo, non 204 come /api/memories/{id} -- ' +
    'chi legge "res.status === 204" per il successo qui leggerebbe sempre un fallimento');
  assert.match(testo, /nessuna promessa/i, 'la lista si e\' ricaricata: ora e\' vuota davvero');
});

// ---------------------------------------------------------------------------
// Gli errori della DELETE: 404 e 409 dicono cose diverse
// ---------------------------------------------------------------------------

test('la DELETE 404 mostra il testo esatto del server, poi ricarica comunque', async () => {
  const { window, document, chiamate } = await monta({
    deleteStatus: 404,
    deleteBody: { error: 'non ho nessuna promessa con quell\'identificatore.' },
  });
  document.querySelector('[data-disdici="p1"]').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /non ho nessuna promessa con quell'identificatore/);
  // Il titolo del test promette "poi ricarica comunque" (review Task 9, minor):
  // senza questa riga l'asserzione non provava il ricaricamento, solo il
  // messaggio. Una seconda GET dopo la DELETE 404 e' il ricaricamento.
  assert.equal(chiamate.filter((c) => c.method === 'GET').length, 2,
    'un 404 non deve fermare il ricaricamento: la lista si aggiorna comunque');
});

test('la DELETE 409 mostra il testo esatto del server (gia\' concluso: non si disdice)', async () => {
  const { window, document } = await monta({
    deleteStatus: 409,
    deleteBody: { error: 'quella promessa e\' gia\' mantenuta: non si disdice, si legge.' },
  });
  document.querySelector('[data-disdici="p1"]').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /gia' mantenuta: non si disdice, si legge/);
});

test('la DELETE senza risposta di rete si dichiara, non un catch muto', async () => {
  const { window, document } = await monta({ deleteRotto: true });
  document.querySelector('[data-disdici="p1"]').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /non ha risposto/);
});

// ---------------------------------------------------------------------------
// Gli errori della GET: 503 con `agenda: []' nel corpo non e' una lista vuota vera
// ---------------------------------------------------------------------------

test('un GET fallito mostra un errore con "Riprova", non una lista vuota silenziosa', async () => {
  const { document } = await monta({ getRotto: true });
  assert.match(document.body.textContent, /Non è stato possibile leggere le promesse/);
  const retry = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Riprova');
  assert.ok(retry, 'deve esserci un modo di riprovare');
});

test('il 503 "archivio non disponibile" (con agenda:[] nel corpo) non si legge come lista vuota vera', async () => {
  const { document } = await monta({ get503: true });
  const testo = document.body.textContent;
  assert.match(testo, /Non è stato possibile leggere le promesse/);
  assert.doesNotMatch(testo, /nessuna promessa/i,
    'un guasto non deve sembrare "non hai promesse"');
});

// ---------------------------------------------------------------------------
// «Cosa è cambiato» (review finale, rilievo ①): un `fai` mantenuto si
// collega alla cronaca per `esecuzione_id`, caricata A RICHIESTA quando
// l'utente apre la riga -- mai all'apertura della pagina.
// ---------------------------------------------------------------------------

const FAI_MANTENUTA = {
  id: 'p7', specie: 'fai', frase: 'alle 17 accendi lo studio', quando_ts: 1755400000,
  quando_detto: 'alle 17', fuso: 'Europe/Rome', chiamata: { servizio: 'light.turn_on' },
  domanda: null, istantanea: null, recapito: null, stato: 'mantenuta', motivo: null,
  esecuzione_id: 'e9', testo: null, avvisare: null,
  nata_ts: 1755390000, risvegliata_ts: 1755400010, origine: null,
};

function contaGetEsecuzioni(chiamate) {
  return chiamate.filter((c) => c.method === 'GET' && c.url.indexOf('api/executions/') === 0).length;
}

test('il bottone "Cosa è cambiato" compare SOLO su un fai mantenuta con esecuzione_id', async () => {
  const { document } = await monta({
    get: {
      agenda: [
        FAI_MANTENUTA,
        PROMESSE[1], // chiedi, saltata: mai un fai mantenuta
        PROMESSE[2], // chiedi, mantenuta CON esecuzione_id: ha gia' la sua risposta (§6)
        { ...FAI_MANTENUTA, id: 'p8', stato: 'fallita', motivo: 'rifiutato' }, // fai FALLITA: niente bottone
      ],
    },
  });
  const bottoni = Array.from(document.querySelectorAll('button'))
    .filter((b) => b.textContent === 'Cosa è cambiato');
  assert.equal(bottoni.length, 1, 'solo p7 (fai, mantenuta, esecuzione_id) deve avere il bottone');
});

test('non si chiede la cronaca finche\' l\'utente non apre la riga (niente richiesta per riga all\'apertura pagina)', async () => {
  const { chiamate } = await monta({ get: { agenda: [FAI_MANTENUTA] } });
  assert.equal(contaGetEsecuzioni(chiamate), 0,
    'il caricamento della pagina non deve gia\' aver chiesto la cronaca');
});

test('un click sul bottone chiede la cronaca e mostra cosa è cambiato', async () => {
  const { window, document, chiamate } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    execution: { execution: esecuzione({ cambiato: ['light.studio'] }) },
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.equal(contaGetEsecuzioni(chiamate), 1);
  assert.match(document.body.textContent, /Cambiate: light\.studio/);
  assert.equal(btn.getAttribute('aria-expanded'), 'true');
  assert.equal(btn.textContent, 'Nascondi il dettaglio');
});

test('riaprire la riga non richiede una seconda GET: il dettaglio resta in cache', async () => {
  const { window, document, chiamate } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    execution: { execution: esecuzione() },
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true })); // apre
  await tick(20);
  btn.dispatchEvent(new window.Event('click', { bubbles: true })); // chiude
  await tick(20);
  assert.equal(btn.getAttribute('aria-expanded'), 'false');
  btn.dispatchEvent(new window.Event('click', { bubbles: true })); // riapre
  await tick(20);
  assert.equal(contaGetEsecuzioni(chiamate), 1, 'una sola richiesta per riga, non una per apertura');
  assert.equal(btn.getAttribute('aria-expanded'), 'true');
});

test('un "cambiato" vuoto NON diventa "niente è cambiato": si vede l\'avviso della porta, verbatim', async () => {
  const { window, document } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    execution: {
      execution: esecuzione({
        cambiato: [],
        avviso: 'la chiamata è andata a buon fine, ho aspettato 2 secondi che Home ' +
          'Assistant annunciasse un cambiamento di stato su queste entità, e in ' +
          'quel tempo Home Assistant non ha riportato nessun cambiamento.',
      }),
    },
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  const testo = document.body.textContent;
  assert.match(testo, /ho aspettato 2 secondi/, 'l\'avviso della porta deve comparire verbatim');
  assert.doesNotMatch(testo, /^niente è cambiato/i);
  assert.doesNotMatch(testo, /Cambiate:/, 'cambiato è vuoto: non deve comparire un elenco vuoto di "Cambiate"');
});

test('un\'esecuzione fallita mostra l\'errore, non un pannello silenzioso', async () => {
  const { window, document } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    execution: {
      execution: esecuzione({
        eseguito: false, cambiato: null, avviso: null,
        errore: 'Home Assistant ha rifiutato la chiamata: 500',
      }),
    },
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /Home Assistant ha rifiutato la chiamata: 500/);
});

test('un 404 sulla cronaca (riga potata, o mai esistita) si dichiara onestamente', async () => {
  const { window, document } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    esecuzione404: true,
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /Non ne ho più il dettaglio/);
  // Un 404 e' un fatto stabile (la riga non torna): non deve fingere un
  // guasto -- niente riga di stato "non ha risposto".
  assert.doesNotMatch(document.body.textContent, /non ha risposto/);
});

test('un guasto di rete sulla cronaca passa dalla riga di stato di pagina, e il bottone si può ' +
  'ricliccare per riprovare', async () => {
  const { window, document, chiamate } = await monta({
    get: { agenda: [FAI_MANTENUTA] },
    esecuzioneRotta: true,
  });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);
  assert.match(document.body.textContent, /HIRIS non ha risposto/);
  assert.equal(btn.disabled, false, 'il bottone deve tornare cliccabile dopo il guasto');
  assert.equal(btn.getAttribute('aria-expanded'), 'false',
    'torna chiuso: un nuovo click deve poter riprovare, non solo richiudere un pannello vuoto');
  assert.equal(contaGetEsecuzioni(chiamate), 1);
});

test('il bottone è raggiungibile da tastiera: un <button> vero, non un div con onclick', async () => {
  const { document } = await monta({ get: { agenda: [FAI_MANTENUTA] } });
  const btn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent === 'Cosa è cambiato');
  assert.equal(btn.tagName, 'BUTTON', 'un <button> e\' nativamente raggiungibile da tastiera e ha un focus visibile');
  assert.equal(btn.type, 'button');
});
