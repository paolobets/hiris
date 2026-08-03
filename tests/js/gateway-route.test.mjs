import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Sprint coerenza, lotto A, task 5 (A8+A10): la pagina Accessi Gateway
   (#/gateway, config/gateway-route.js) approvava/rifiutava un comando in
   coda senza chiedere conferma -- un comando su casa propria arrivato in
   coda proprio perche' il semaforo l'ha giudicato giallo o rosso -- taceva
   su un fallimento della singola approvazione/rifiuto E su un fallimento di
   lettura dell'intera coda (che spariva esattamente come una coda vuota), e
   offriva "verde" per domini che il semaforo nega SEMPRE (denylist
   DANGEROUS_DOMAINS in security/semaphore.py) senza dirlo. */

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/gateway-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const BASE_POLICY = {
  levels: {}, settings: {},
  categories: [
    { id: 'light', label: 'Luci', count: 3 },
    { id: 'lock', label: 'Serrature', count: 1 },
  ],
  entities: {},
};

function findButton(document, text) {
  return Array.from(document.querySelectorAll('button')).find((b) => b.textContent === text);
}

// ---------------------------------------------------------------------------
// A8.1 -- resolve() chiede conferma prima di approvare/rifiutare
// ---------------------------------------------------------------------------

test('Approva chiede conferma: con window.confirm=false nessuna POST parte', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).includes('/pending/')) return jsonResponse({ ok: true });
    if (String(url).includes('/pending')) {
      return jsonResponse({ pending: [{ id: 'p1', tier: 'yellow', label: 'light.turn_on', origin: 'gateway' }] });
    }
    return jsonResponse(BASE_POLICY);
  };
  let confirmMsg = null;
  window.confirm = (msg) => { confirmMsg = msg; return false; };

  window.HirisGatewayRoute.mount();
  await tick(20);

  const btn = findButton(document, 'Approva');
  assert.ok(btn, 'deve esserci il bottone Approva per il comando in coda');
  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.ok(confirmMsg, 'window.confirm deve essere invocato');
  assert.match(confirmMsg, /[Aa]pprovare/, 'il testo deve parlare di approvare questo comando');
  assert.equal(calls.some((c) => c.opts.method === 'POST'), false,
    'con la conferma negata nessuna POST di approvazione deve partire');
});

test('Approva confermato: POST parte verso il nonce giusto', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const calls = [];
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).includes('/pending/p1/approve')) return jsonResponse({ ok: true, result: { status: 'ok' } });
    if (String(url).endsWith('/pending')) {
      return jsonResponse({ pending: [{ id: 'p1', tier: 'yellow', label: 'light.turn_on', origin: 'gateway' }] });
    }
    return jsonResponse(BASE_POLICY);
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  window.HirisGatewayRoute.mount();
  await tick(20);
  findButton(document, 'Approva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const approveCall = calls.find((c) => c.url.includes('/pending/p1/approve'));
  assert.ok(approveCall, 'la POST di approvazione deve partire');
  assert.equal(approveCall.opts.method, 'POST');
  assert.deepEqual(alerts, [], 'un esito riuscito non deve mostrare alert');
});

// ---------------------------------------------------------------------------
// A8.2 -- resolve() non tace piu' su un fallimento (ne' di rete ne' applicativo)
// ---------------------------------------------------------------------------

test('un comando gia\' scaduto/gestito lo dice in italiano, e la coda si ricarica comunque', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const calls = [];
  let pendingCallCount = 0;
  window.fetch = async (url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).includes('/pending/p1/approve')) {
      return jsonResponse({ ok: false, error: 'richiesta non trovata, scaduta o già gestita' });
    }
    if (String(url).endsWith('/pending')) {
      pendingCallCount += 1;
      return jsonResponse({ pending: pendingCallCount === 1
        ? [{ id: 'p1', tier: 'yellow', label: 'light.turn_on', origin: 'gateway' }] : [] });
    }
    return jsonResponse(BASE_POLICY);
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  window.HirisGatewayRoute.mount();
  await tick(20);
  findButton(document, 'Approva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(alerts.length, 1, 'un fallimento applicativo deve produrre un alert, non silenzio');
  assert.doesNotMatch(alerts[0], /richiesta non trovata/, 'niente stringa tecnica del backend');
  assert.match(alerts[0], /scaduto|gestito/, 'il messaggio in italiano deve spiegare cosa e\' successo');
  assert.equal(pendingCallCount, 2, 'la coda deve essere ricaricata dopo l\'esito, riuscito o no');
});

test('un fallimento di rete su approva/rifiuta produce un alert e ricarica comunque la coda', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  let pendingCallCount = 0;
  window.fetch = async (url) => {
    if (String(url).includes('/pending/p1/reject')) throw new Error('network down');
    if (String(url).endsWith('/pending')) {
      pendingCallCount += 1;
      return jsonResponse({ pending: pendingCallCount === 1
        ? [{ id: 'p1', tier: 'red', label: 'climate.set_temperature', origin: 'chat', user: 'paolo' }] : [] });
    }
    return jsonResponse(BASE_POLICY);
  };
  window.confirm = () => true;
  const alerts = [];
  window.alert = (m) => alerts.push(m);

  window.HirisGatewayRoute.mount();
  await tick(20);
  findButton(document, 'Rifiuta').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.equal(alerts.length, 1, 'un errore di rete deve essere segnalato');
  assert.match(alerts[0], /rete/i);
  assert.equal(pendingCallCount, 2, 'la coda va ricaricata anche dopo un errore di rete');
});

// ---------------------------------------------------------------------------
// A8.3 -- coda vuota e coda illeggibile sono due stati distinti e visibili
// ---------------------------------------------------------------------------

test('coda vuota: lo dice esplicitamente, non sparisce senza testo', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  window.fetch = async (url) => {
    if (String(url).includes('/pending')) return jsonResponse({ pending: [] });
    return jsonResponse(BASE_POLICY);
  };
  window.HirisGatewayRoute.mount();
  await tick(20);

  const outlet = document.getElementById('route-outlet');
  assert.match(outlet.textContent, /[Nn]essun comando in attesa/,
    'una coda vuota deve dichiararsi tale');
});

test('coda illeggibile: dice di non essere riuscita a leggerla, testo diverso dalla coda vuota', async () => {
  const vuota = loadScripts(SCRIPTS, { html: fixtureHtml() });
  vuota.window.fetch = async (url) => {
    if (String(url).includes('/pending')) return jsonResponse({ pending: [] });
    return jsonResponse(BASE_POLICY);
  };
  vuota.window.HirisGatewayRoute.mount();
  await tick(20);
  const testoVuoto = vuota.document.getElementById('route-outlet').textContent;
  vuota.dispose();

  const rotta = loadScripts(SCRIPTS, { html: fixtureHtml() });
  rotta.window.fetch = async (url) => {
    if (String(url).includes('/pending')) return jsonResponse({ error: 'boom' }, 503);
    return jsonResponse(BASE_POLICY);
  };
  rotta.window.HirisGatewayRoute.mount();
  await tick(20);
  const testoRotto = rotta.document.getElementById('route-outlet').textContent;

  assert.match(testoRotto, /[Nn]on è stato possibile leggere/,
    'un guasto di lettura deve dichiararsi tale, non sembrare una coda vuota');
  assert.doesNotMatch(testoRotto, /[Nn]essun comando in attesa/);
  assert.notEqual(testoRotto, testoVuoto, 'i due stati devono essere testualmente distinguibili');
});

// ---------------------------------------------------------------------------
// A10 -- il verde su un dominio pericoloso e' segnalato come sempre bloccato
// ---------------------------------------------------------------------------

test('un dominio pericoloso (lock) mostra l\'avviso "sempre bloccato"; uno normale no', async () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  window.fetch = async (url) => {
    if (String(url).includes('/pending')) return jsonResponse({ pending: [] });
    return jsonResponse(BASE_POLICY);
  };
  window.HirisGatewayRoute.mount();
  await tick(20);

  const rows = Array.from(document.querySelectorAll('.gw-row'));
  const lockRow = rows.find((r) => r.textContent.includes('Serrature'));
  const lightRow = rows.find((r) => r.textContent.includes('Luci'));
  assert.ok(lockRow, 'deve esserci la riga Serrature');
  assert.ok(lightRow, 'deve esserci la riga Luci');
  assert.match(lockRow.textContent, /sempre bloccato \(dominio pericoloso\)/,
    'il dominio pericoloso deve avvisare che il verde non ha mai effetto');
  assert.doesNotMatch(lightRow.textContent, /sempre bloccato/,
    'un dominio normale non deve mostrare l\'avviso');

  const outlet = document.getElementById('route-outlet');
  assert.match(outlet.textContent, /scavalcare il blocco/,
    'la pagina deve spiegare che un\'approvazione esplicita puo\' scavalcare il blocco (verificato in dispatcher.py/handlers_gateway_pending.py)');
});
