import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Task B8: build-check.test.mjs prova il modulo condiviso ISOLATO, chiamando
   `verifica()` a mano. Non basta -- il difetto n.1 ripetuto in questa
   campagna è una classe perfettamente testata ma MAI collegata. Qui si fa
   girare `chat/main.js` per davvero (stesso schema di
   chat-usage-non-misurata.test.mjs: eval indiretto del file vero, non un
   frammento riscritto a mano) e si prova che il SUO `checkHealth()` passa
   davvero `d.build` a `HirisBuildCheck.verifica()` -- non solo che, chiamata
   a mano, la funzione si comporti bene. */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const STATIC = join(ROOT, 'hiris', 'app', 'static');
const MAIN = join(STATIC, 'chat', 'main.js');

const MODULI = [
  'config/api.js', 'chat/state.js', 'chat/messages.js', 'chat/agents.js',
  'chat/send.js', 'chat/theme.js', 'chat/sidebar.js', 'chat/keyboard.js',
  'build-check.js',
];

function fixtureHtml(buildLocale) {
  return `<!doctype html><head><meta name="hiris-build" content="${buildLocale}"></head><body>
    <div id="app">
      <div id="sidebar-overlay" style="display:none"></div>
      <aside id="sidebar">
        <div id="usage-widget">
          <span class="usage-val" id="u-requests">—</span>
          <span class="usage-val" id="u-input">—</span>
          <span class="usage-val" id="u-output">—</span>
          <span class="usage-val" id="u-cost">—</span>
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

function jsonResponse(body) {
  return { ok: true, status: 200, json: async () => body };
}

/* Carica tutto TRANNE chat/main.js, stubba fetch/matchMedia/setInterval, poi
   esegue chat/main.js con eval indiretto: e' un IIFE che chiama boot() (e
   quindi checkHealth()) al load, quindi caricarlo E' farlo partire -- prima
   di questo punto fetch deve gia' essere stubbato, o boot() lo trova
   undefined (jsdom non implementa fetch). */
async function avvia(t, { buildLocale, buildRemoto }) {
  const ctx = loadScripts(MODULI, { html: fixtureHtml(buildLocale) });
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  const reloadCalls = [];
  ctx.window.HirisBuildCheck._internal_reload = () => { reloadCalls.push(true); };
  try { ctx.window.sessionStorage.clear(); } catch (e) {}
  ctx.window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('api/health')) return jsonResponse({ status: 'ok', version: '3.0.0', build: buildRemoto });
    return jsonResponse({});
  };

  const veroSet = globalThis.setInterval;
  globalThis.setInterval = () => 0; // non serve osservare i timer qui, solo evitare che restino pendenti
  try {
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
  }
  if (t) t.after(() => {
    ctx.window.HirisChatMessages.fermaTutteLeAttese();
    ctx.dom.window.close();
  });
  return { ...ctx, reloadCalls };
}

test('boot della chat: build locale e remoto combaciano -- chat/main.js reale non ricarica mai', async (t) => {
  const { reloadCalls, document } = await avvia(t, { buildLocale: 'stampX', buildRemoto: 'stampX' });
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('boot della chat: build locale diverso dal remoto -- chat/main.js reale lo scopre da solo e tenta il ricaricamento', async (t) => {
  const { reloadCalls } = await avvia(t, { buildLocale: 'vecchio-nella-pagina', buildRemoto: 'nuovo-sul-server' });
  assert.equal(reloadCalls.length, 1,
    'chat/main.js deve passare d.build da GET api/health a HirisBuildCheck.verifica() -- ' +
    'se questa riga manca o passa un valore sbagliato, il modulo isolato (testato a parte) non si accorge di nulla');
});
