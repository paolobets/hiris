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
   arriva come 200 con `misurata: false` più la frase che lo spiega. Questi
   test pinnano che la pagina lo DICA, e che continui a distinguere quel
   fatto da un guasto vero. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

const MESSAGGIO = "Sul percorso abbonamento i consumi non si misurano: la chat gira sull'abbonamento Claude.";

async function monta(risposta) {
  const ctx = loadScripts(['config/usage-route.js'], { html: HTML });
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
    json: () => Promise.resolve({ misurata: false, motivo: 'abbonamento', messaggio: MESSAGGIO }),
  }));

  assert.ok(testo.includes(MESSAGGIO), 'la frase del server deve comparire per intero');
  assert.doesNotMatch(testo, /Errore caricamento consumi/,
    'non è un errore: è una proprietà della configurazione');
});

test('C-1: senza contatori non si offre di azzerarli', async () => {
  const { outlet } = await monta(() => ({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ misurata: false, motivo: 'abbonamento', messaggio: MESSAGGIO }),
  }));

  const azioni = outlet.querySelector('#usage-azioni');
  assert.ok(azioni, 'la barra delle azioni esiste nel markup');
  assert.equal(azioni.style.display, 'none',
    '«Azzera contatori globali» su contatori che non esistono è un pulsante che mente');
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
      misurata: true, total_requests: 42, input_tokens: 1200,
      output_tokens: 800, cost_eur: 1.5, last_reset: '2026-07-01T00:00:00Z',
    }),
  }));

  assert.match(testo, /42/);
  assert.match(testo, /1\.2k/, 'i token si abbreviano, ma ci sono');
  assert.notEqual(outlet.querySelector('#usage-azioni').style.display, 'none');
});

test('la pagina non chiama più «Chatbot» ciò che il prodotto non ha più', async () => {
  const { testo } = await monta(() => ({
    ok: true, status: 200, json: () => Promise.resolve({ misurata: true, total_requests: 0 }),
  }));
  assert.doesNotMatch(testo, /Chatbot/,
    'la 2.0 ha una chat sola: «Chatbot» è il vocabolario del prodotto vecchio');
});
