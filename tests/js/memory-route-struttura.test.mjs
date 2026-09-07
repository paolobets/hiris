import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Collaudo usabilita' 3.22.3, rilievo B: `config/memory-route.js:317-330`.
 *
 * `interpretation` (la frase «HIRIS ha capito: ...») si riempiva SOLO da
 * `r.grandezza` e `formatInterval(r)`. Quando erano entrambi vuoti la card
 * scriveva «Nessuna struttura riconosciuta — resta solo la frase.» -- e due
 * righe piu' sotto, nella STESSA card, renderizzava `r.ancore` e
 * `r.condizioni`, che sono struttura riconosciuta a tutti gli effetti. Una
 * parola («struttura») per due insiemi diversi: quello stretto che la frase
 * misurava, e quello largo che la card mostra davvero.
 *
 * La cura si separa alla fonte (memory-route.js): la frase «Nessuna
 * struttura riconosciuta» resta vera SOLO quando la card non ha ne'
 * grandezza, ne' intervallo, ne' ancore, ne' condizioni. Quando manca solo
 * lo stretto ma il largo resta, la riga si omette -- le ancore/condizioni
 * parlano da sole, senza una riga sopra che le smentisce.
 *
 * Mutazione che questa prova deve uccidere: tornare alla vecchia condizione
 * (`interpretation.length ? ... : 'Nessuna struttura riconosciuta...'`),
 * cioe' lo stato di partenza -- verificato sotto uccidendo davvero la prova
 * con quella mutazione, poi ripristinando. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';
const SCRIPTS = ['config/memory-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const BASE_RICORDO = {
  id: 1,
  testo: 'un ricordo qualsiasi',
  detto_da: 'paolo',
  detto_il: '2026-09-01T09:00:00Z',
  forza: 'fatto',
  grandezza: null,
  minimo: null,
  massimo: null,
  unita: null,
  corretto_da_utente: false,
  ancore: [],
  condizioni: [],
};

async function montaConRicordo(ricordo) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  ctx.window.fetch = () => Promise.resolve(jsonResponse({
    available: true, memories: [ricordo], total: 1, shown: 1,
  }));
  ctx.window.HirisMemoryRoute.mount();
  await tick(0);
  await tick(0);
  const outlet = ctx.document.getElementById('route-outlet');
  return outlet;
}

test('ancore SENZA grandezza/intervallo: la card non nega la struttura che sta mostrando', async () => {
  const ricordo = Object.assign({}, BASE_RICORDO, {
    ancore: [{ tipo: 'area', riferimento: 'salotto', nome_visto: 'salotto', nome_attuale: 'Salotto', esiste: true }],
  });
  const outlet = await montaConRicordo(ricordo);
  const testo = outlet.textContent;

  assert.doesNotMatch(testo, /Nessuna struttura riconosciuta/,
    'la card mostra un\'ancora (Riguarda: Salotto): non puo\' dire nello stesso respiro che non c\'e\' struttura');
  assert.match(testo, /Riguarda:/, 'l\'ancora deve comunque comparire');
  assert.match(testo, /Salotto/);
});

test('condizioni SENZA grandezza/intervallo: stessa cura', async () => {
  const ricordo = Object.assign({}, BASE_RICORDO, {
    condizioni: [{ tipo: 'stagione', valore: 'inverno' }],
  });
  const outlet = await montaConRicordo(ricordo);
  const testo = outlet.textContent;

  assert.doesNotMatch(testo, /Nessuna struttura riconosciuta/,
    'la card mostra una condizione (Quando vale: ...): non puo\' negare la struttura due righe sopra');
  assert.match(testo, /Quando vale:/);
});

test('davvero NIENTE (ne\' grandezza, ne\' intervallo, ne\' ancore, ne\' condizioni): la frase resta, perche\' stavolta e\' vera', async () => {
  const outlet = await montaConRicordo(Object.assign({}, BASE_RICORDO));
  const testo = outlet.textContent;

  assert.match(testo, /Nessuna struttura riconosciuta — resta solo la frase\./,
    'quando la card non ha davvero nient\'altro, la frase deve poter ancora comparire');
  assert.doesNotMatch(testo, /Riguarda:/);
  assert.doesNotMatch(testo, /Quando vale:/);
});

test('grandezza/intervallo presenti: il comportamento di prima non e\' cambiato (regressione)', async () => {
  const ricordo = Object.assign({}, BASE_RICORDO, {
    grandezza: 'temperature', minimo: 19, massimo: 20, unita: '°C',
  });
  const outlet = await montaConRicordo(ricordo);
  const testo = outlet.textContent;

  assert.match(testo, /HIRIS ha capito: temperature/);
  assert.doesNotMatch(testo, /Nessuna struttura riconosciuta/);
});

test('grandezza presente E ancore presenti: nessuna riga si contraddice, e nessuna sparisce', async () => {
  const ricordo = Object.assign({}, BASE_RICORDO, {
    grandezza: 'humidity',
    ancore: [{ tipo: 'area', riferimento: 'bagno', nome_visto: 'bagno', nome_attuale: 'Bagno', esiste: true }],
  });
  const outlet = await montaConRicordo(ricordo);
  const testo = outlet.textContent;

  assert.match(testo, /HIRIS ha capito: humidity/);
  assert.match(testo, /Riguarda:/);
  assert.doesNotMatch(testo, /Nessuna struttura riconosciuta/);
});
