import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Fetta «fix pre-UAT», voce C-1.

   Nella configurazione dell'UAT — abbonamento acceso, nessuna chiave API,
   nessun Ollama — `server.py` lascia `llm_router` e `claude_runner` a `None`,
   e `GET /api/usage` rispondeva **503**. Due conseguenze viste dal vivo su due
   istanze:

     - `#/usage` diceva soltanto «Errore caricamento consumi.»: una delle sei
       pagine superstiti ridotta a un vicolo cieco su una configurazione sana;
     - il riquadro «Utilizzo» della chat restava a quattro «—» e **ripeteva la
       chiamata ogni 30 secondi**, prendendosi ogni volta un 503 e un
       `console.error`, senza mai dire perché.

   La riparazione: `api/handlers_usage.py` risponde **200** con
   `measured: false` e la frase che spiega il perché (vedi la docstring del
   modulo per la motivazione della forma scelta). Qui si pinnano i due fatti
   che ne discendono lato frontend, e che erano il difetto vero:

     1. `loadUsage()` restituisce `false` SOLO in quel caso, e `true` in ogni
        altro (numeri veri, HTTP non-200, rete caduta) — un guasto passeggero
        non deve spegnere il timer;
     2. il boot della chat usa quel `false` per fermare l'intervallo: la
        chiamata inutile ogni 30 secondi cessa.

   Il fatto 2 si verifica facendo girare `chat/main.js` per davvero, con
   `setInterval`/`clearInterval` sotto osservazione: un test sul testo del
   sorgente si accontenterebbe della presenza della parola `clearInterval`. */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const MAIN = join(ROOT, 'hiris', 'app', 'static', 'chat', 'main.js');

/* Il sottoinsieme di static/index.html che i moduli della chat toccano al
   load, più il riquadro Utilizzo completo di righe (`.usage-row`): sono
   quelle che `loadUsage()` deve togliere di scena quando non c'è niente da
   mostrarci dentro. */
function fixtureHtml() {
  return `<!doctype html><body>
    <div id="app">
      <div id="sidebar-overlay" style="display:none"></div>
      <aside id="sidebar">
        <div id="usage-widget">
          <div class="usage-row"><span class="usage-label">Richieste</span><span class="usage-val" id="u-requests">—</span></div>
          <div class="usage-row"><span class="usage-label">Token input</span><span class="usage-val" id="u-input">—</span></div>
          <div class="usage-row"><span class="usage-label">Token output</span><span class="usage-val" id="u-output">—</span></div>
          <div class="usage-row"><span class="usage-label">Costo</span><span class="usage-val" id="u-cost">—</span></div>
          <div class="usage-reset" id="usage-last-reset"></div>
        </div>
      </aside>
      <main id="main">
        <header id="header">
          <button id="menu-btn"></button>
          <div id="header-title">HIRIS <span id="header-version"></span></div>
          <button id="cancella-conv-btn"></button>
          <button id="theme-toggle"><svg class="ic-moon"></svg><svg class="ic-sun" style="display:none"></svg></button>
          <div id="agent-pill"><span id="ap-avatar"></span><span id="ap-name"></span></div>
          <div id="conn-dot"></div>
        </header>
        <div id="messages">
          <div id="welcome">
            <span id="welcome-hello">Ciao</span>
            <div class="quick-chips">
              <button class="chip" type="button" data-quick="Stato casa">Stato casa</button>
            </div>
          </div>
        </div>
        <div id="input-area"><textarea id="input"></textarea><button id="send-btn"></button></div>
        <div id="turn-counter" style="display:none"></div>
        <div id="session-ended-msg" style="display:none"></div>
      </main>
    </div>
  </body>`;
}

const MODULI = [
  'config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js',
  'chat/send.js', 'chat/theme.js', 'chat/sidebar.js', 'chat/keyboard.js',
];

const NON_MISURATA = {
  measured: false,
  reason: 'abbonamento',
  message: "Sul percorso abbonamento i consumi non si misurano: la chat gira sull'abbonamento Claude.",
};

function jsonResponse(body) {
  return { ok: true, status: 200, json: async () => body };
}

/* Carica i moduli, stubba fetch, poi esegue `chat/main.js` (che al load fa
   boot()) osservando setInterval/clearInterval. Restituisce cosa è stato
   programmato e cosa è stato fermato. */
async function avviaChat(rispostaUsage) {
  const ctx = loadScripts(MODULI, { html: fixtureHtml() });
  /* jsdom non implementa matchMedia; chat/theme.js e chat/sidebar.js lo usano
     come farebbe qualunque pagina reale. Stub minimo, sempre "non combacia". */
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  ctx.window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('api/usage')) return rispostaUsage();
    if (u.includes('api/health')) return jsonResponse({ status: 'ok', version: '2.0.0' });
    return jsonResponse({});
  };

  const veroSet = globalThis.setInterval;
  const veroClear = globalThis.clearInterval;
  const programmati = [];
  const fermati = [];
  globalThis.setInterval = (fn, ms) => { programmati.push({ fn, ms }); return programmati.length; };
  globalThis.clearInterval = (id) => { fermati.push(id); };
  try {
    // eval indiretto nel realm host, come fa loadScripts: main.js è un IIFE
    // che chiama boot() al load, quindi caricarlo È farlo partire. E' il
    // meccanismo del test, non una svista.
    // eslint-disable-next-line no-eval -- vedi commento sopra
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
    globalThis.clearInterval = veroClear;
  }
  return { ...ctx, programmati, fermati };
}

test('C-1: dichiarata la non-misurabilità, il riquadro Utilizzo SMETTE di richiamare api/usage ogni 30 secondi', async () => {
  const { programmati, fermati } = await avviaChat(() => jsonResponse(NON_MISURATA));

  const consumi = programmati.filter((p) => p.ms === 30000);
  assert.ok(consumi.length >= 1, 'il boot programma comunque i suoi intervalli da 30s');
  assert.equal(fermati.length, 1,
    'esattamente un intervallo deve essere fermato: quello dei consumi, che non produrrà mai un numero');
});

test('C-1: un guasto passeggero NON spegne il timer — la differenza fra «non si misura» e «non ha risposto»', async () => {
  const caduta = await avviaChat(() => { throw new Error('offline'); });
  assert.equal(caduta.fermati.length, 0,
    'la rete può tornare: fermare il timer qui renderebbe il riquadro morto fino al reload');

  const cinquecento = await avviaChat(() => ({ ok: false, status: 503, json: async () => ({}) }));
  assert.equal(cinquecento.fermati.length, 0,
    'un 503 è un guasto, non una dichiarazione: si riprova');
});

test('C-1: la frase del server compare sullo schermo, e le righe dei numeri escono di scena', async () => {
  const { document } = await avviaChat(() => jsonResponse(NON_MISURATA));

  assert.equal(document.getElementById('usage-last-reset').textContent, NON_MISURATA.message,
    'la frase è quella del server, non una parafrasi del frontend');
  const righe = [...document.querySelectorAll('#usage-widget .usage-row')];
  assert.ok(righe.length > 0, 'precondizione: la fixture ha le righe');
  for (const r of righe) {
    assert.equal(r.style.display, 'none',
      'quattro «—» accanto a «Richieste» e «Costo» si leggono come «sto caricando»');
  }
});

test('C-1: con i consumi misurati non cambia niente — i numeri si vedono e le righe restano', async () => {
  const { document, fermati } = await avviaChat(() => jsonResponse({
    measured: true, total_requests: 42, input_tokens: 1200, output_tokens: 800,
    cost_eur: 0.1234, last_reset: '2026-07-01T00:00:00Z',
  }));

  assert.equal(fermati.length, 0, 'qui il timer serve: i numeri cambiano');
  assert.equal(document.getElementById('u-requests').textContent, '42');
  assert.equal(document.getElementById('u-cost').textContent, '€ 0,12');
  const righe = [...document.querySelectorAll('#usage-widget .usage-row')];
  for (const r of righe) assert.notEqual(r.style.display, 'none');
});
