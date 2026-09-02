import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La pagina `#/usage` («Consumi globali»), fetta «fix pre-UAT» voce C-1.

   Prima, su una configurazione ad abbonamento — quella dell'UAT: abbonamento
   acceso, nessuna chiave API, nessun Ollama — `GET /api/usage` rispondeva
   503, il `!r.ok` qui dentro lo trasformava in un `throw`, e il `catch`
   finale scriveva «Errore caricamento consumi.». Una delle sei pagine
   superstiti ridotta a un vicolo cieco su un add-on perfettamente sano.

   Il fatto è legittimo — in abbonamento i consumi non si misurano — e adesso
   arriva come 200 con `measured: false` più la frase che lo spiega. Questi
   test pinnano che la pagina lo DICA, e che continui a distinguere quel
   fatto da un guasto vero. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

const MESSAGGIO = "Sul percorso abbonamento i consumi non si misurano: la chat gira sull'abbonamento Claude.";

async function monta(risposta) {
  /* `config/api.js` prima non serviva: questa pagina aveva una copia privata
     delle sue funzioni di formattazione, e per lo stesso numero scriveva
     `1.3M` dove il riquadro della chat scriveva `1.28M`. Le copie sono uscite,
     restano le funzioni condivise -- che nella pagina vera arrivano dallo
     <script> che config.html carica PRIMA di questo (vedi l'ordine li'). La
     lista qui sotto adesso dice la verita' su cosa serve alla pagina. */
  const ctx = loadScripts(['config/api.js', 'config/usage-route.js'], { html: HTML });
  ctx.window.fetch = () => Promise.resolve(risposta());
  ctx.window.HirisUsageRoute.mount();
  await tick(0);
  await tick(0);
  const outlet = ctx.document.getElementById('route-outlet');
  return { ...ctx, outlet, testo: outlet.textContent };
}

test('C-1: in abbonamento la pagina Consumi DICE perché non ci sono numeri, invece di dire «errore»', async () => {
  const { testo } = await monta(() => ({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ measured: false, reason: 'abbonamento', message: MESSAGGIO }),
  }));

  assert.ok(testo.includes(MESSAGGIO), 'la frase del server deve comparire per intero');
  assert.doesNotMatch(testo, /Errore caricamento consumi/,
    'non è un errore: è una proprietà della configurazione');
});

test('C-1: senza contatori non si offre di azzerarli', async () => {
  const { outlet } = await monta(() => ({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ measured: false, reason: 'nessun_provider', message: MESSAGGIO }),
  }));

  /* Dalla fetta «i consumi, per modello» il pulsante non si nasconde: non
     viene disegnato affatto. Il fatto difeso e' lo stesso -- offrire di
     azzerare cio' che non esiste e' un pulsante che mente -- e l'assenza e'
     un modo piu' forte di dirlo di un `display:none`. */
  assert.equal(outlet.querySelector('#usage-reset'), null,
    'non c\'è nessuna ancora da spostare');
});

test('C-1: un guasto vero resta un guasto — la pagina non si confonde', async () => {
  const { testo } = await monta(() => ({ ok: false, status: 500, json: () => Promise.resolve({}) }));
  assert.match(testo, /Errore caricamento consumi/,
    'un 500 non è una dichiarazione di non-misurabilità: va detto come errore');
});

test('C-1: con i consumi misurati la pagina mostra i numeri e il pulsante', async () => {
  const { outlet, testo } = await monta(() => ({
    ok: true,
    status: 200,
    json: () => Promise.resolve({
      measured: true, total_requests: 42, input_tokens: 1200,
      output_tokens: 800, cost_eur: 1.5, last_reset: '2026-07-01T00:00:00Z',
      partial_cost: false, sections: [],
    }),
  }));

  assert.match(testo, /42/);
  assert.match(testo, /1\.2k/, 'i token si abbreviano, ma ci sono');
  assert.ok(outlet.querySelector('#usage-reset'), 'il pulsante c\'è');
});

// ---------------------------------------------------------------------------
// I9 -- lo stesso numero, scritto in due modi. Il riquadro «Utilizzo» della
// chat e questa pagina leggono LA STESSA rotta (`GET api/usage`) e mostrano gli
// stessi dati: scrivevano `1.28M` contro `1.3M`, `€3.2149` contro `€ 3,21`, e
// `da 2026-08-01` contro il formato italiano usato ovunque nel prodotto. Non e'
// un dettaglio tipografico: chi guarda le due schermate una dopo l'altra ha
// ragione di credere che una delle due stia sbagliando. Questo test tiene le
// due superfici sulla stessa grammatica facendole rendere lo STESSO payload
// nello stesso documento e confrontando quel che si legge.
// ---------------------------------------------------------------------------

test('I9: chat e pagina Consumi scrivono lo stesso numero nello stesso modo', async () => {
  const DATI = {
    measured: true, total_requests: 128,
    input_tokens: 1284000, output_tokens: 92100,
    cost_eur: 3.21492, last_reset: '2026-08-01T09:12:00Z',
  };
  const ctx = loadScripts(['config/api.js', 'config/usage-route.js'], {
    html: '<!doctype html><body><div id="route-outlet"></div>'
      + '<div id="usage-widget">'
      + '<div class="usage-row"><span class="usage-val" id="u-input">—</span></div>'
      + '<div class="usage-row"><span class="usage-val" id="u-cost">—</span></div>'
      + '</div></body>',
  });
  ctx.window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(DATI) });

  await globalThis.loadUsage();          // il riquadro della chat
  ctx.window.HirisUsageRoute.mount();    // la pagina Consumi
  await tick(0);
  await tick(0);

  const tessere = [...ctx.document.querySelectorAll('#usage-summary .stat-tile')]
    .map((t) => t.querySelector('.st-value').textContent);
  // L'ordine delle tessere e' cambiato col disegno nuovo -- il costo viene per
  // primo, perche' e' la domanda che si fa chi apre questa pagina -- ma
  // l'invariante non e' l'ordine: e' che i DUE posti scrivano lo stesso numero
  // nello stesso modo. Si cercano per etichetta, non per posizione.
  const perEtichetta = {};
  [...ctx.document.querySelectorAll('#usage-summary .stat-tile')].forEach((t) => {
    perEtichetta[t.querySelector('.st-label').textContent] = t.querySelector('.st-value').textContent;
  });
  assert.equal(ctx.document.getElementById('u-input').textContent, perEtichetta['Token IN'],
    'i token di ingresso: stessa cifra, stesse abbreviazioni');
  assert.equal(ctx.document.getElementById('u-cost').textContent, perEtichetta['Costo'],
    'il costo: stesso simbolo, stessa spaziatura, stessi due decimali');
  assert.equal(perEtichetta['Costo'], '€ 3,21',
    'due decimali, e la VIRGOLA: `toFixed` non conosce la lingua, e il '
    + 'punto stonava accanto a una data formattata it-IT');
  assert.equal(tessere.length, 4, 'le quattro tessere del riepilogo ci sono tutte');
  assert.doesNotMatch(ctx.document.getElementById('route-outlet').textContent, /2026-08-01T/,
    'la data si scrive come nel resto del prodotto, non come un ISO tagliato a metà');
  assert.match(ctx.document.getElementById('route-outlet').textContent, /01\/08\/2026/);
});

test('la pagina non chiama più «Chatbot» ciò che il prodotto non ha più', async () => {
  const { testo } = await monta(() => ({
    ok: true, status: 200, json: () => Promise.resolve({ measured: true, total_requests: 0 }),
  }));
  assert.doesNotMatch(testo, /Chatbot/,
    'la 2.0 ha una chat sola: «Chatbot» è il vocabolario del prodotto vecchio');
});
