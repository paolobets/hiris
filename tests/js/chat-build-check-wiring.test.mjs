import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, tick, staticSnapshotDir } from './helpers/dom.mjs';

/* Task B8: build-check.test.mjs prova il modulo condiviso ISOLATO, chiamando
   `verifica()` a mano. Non basta -- il difetto n.1 ripetuto in questa
   campagna è una classe perfettamente testata ma MAI collegata. Qui si fa
   girare `chat/main.js` per davvero (stesso schema di
   chat-usage-non-misurata.test.mjs: eval indiretto del file vero, non un
   frammento riscritto a mano) e si prova che il SUO `checkHealth()` passa
   davvero `d.build` a `HirisBuildCheck.verifica()` -- non solo che, chiamata
   a mano, la funzione si comporti bene.

   m5 (review finale): `MAIN` legge dall'ISTANTANEA di `staticSnapshotDir()`
   (copiata una sola volta per processo), non dall'albero `static/` vivo --
   stessa ragione per cui `loadScripts()` (usata sotto per gli altri moduli)
   e' passata alla stessa istantanea: una scrittura concorrente sui sorgenti
   veri durante la corsa non deve poter colorare questo test. */
const MAIN = join(staticSnapshotDir(), 'chat', 'main.js');

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
  try { ctx.window.sessionStorage.clear(); } catch {}
  ctx.window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('api/health')) return jsonResponse({ status: 'ok', version: '3.0.0', build: buildRemoto });
    return jsonResponse({});
  };

  const veroSet = globalThis.setInterval;
  globalThis.setInterval = () => 0; // non serve osservare i timer qui, solo evitare che restino pendenti
  try {
    // eval indiretto del file vero (vedi il commento in testa al file): e' il
    // meccanismo del test, non una svista.
    // eslint-disable-next-line no-eval -- vedi commento sopra
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
  }
  if (t) t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
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

/* C1 (review finale): un guscio index.html nato PRIMA del Task B8 non contiene
   <script src="static/build-check.js">, ma il server serve comunque il
   chat/main.js ATTUALE (la query ?v=... e' ignorata). window.HirisBuildCheck
   e' quindi undefined -- lo stesso guscio vecchio che B8 dovrebbe aiutare.
   Se checkHealth() chiama HirisBuildCheck.verifica() senza guardia, la
   TypeError sale nel .then, il .catch la raccoglie e il pallino dice
   "offline" -- con api/health che ha risposto 200. Qui si carica DAVVERO
   chat/main.js (eval indiretto, non un frammento riscritto a mano) con
   TUTTI i moduli del guscio TRANNE build-check.js: e' il caso mai pensato
   dal banco esistente, dove build-check.js e' in MODULI in ogni test. */
/* N1 (ri-review): il `try` attorno a HirisBuildCheck.verifica() NON e'
   ridondante con la guardia `if (window.HirisBuildCheck)` -- copre il caso
   che la guardia NON copre, cioe' `verifica()` che ESISTE e SOLLEVA dentro.
   Non e' teorico: `verifica()` chiama `_internal_reload()` ->
   `window.location.reload()`, che in un iframe sandboxed (HIRIS gira sempre
   dentro un iframe di Home Assistant) puo' sollevare SecurityError. Senza
   il `try`, quell'eccezione risalirebbe fuori dal `.then()` di
   checkHealth(): il `.catch()` della catena la prenderebbe per un
   fallimento di rete e scriverebbe "offline" -- con `api/health` che ha
   appena risposto 200 e "connesso" gia' scritto un attimo prima. Qui si
   prova ESATTAMENTE quel percorso: il modulo c'e' (guardia vera), la
   chiamata solleva -- il pallino deve restare "connesso". Mutazione che
   uccide: togliere il `try` (lasciando la guardia) -- vedi il rapporto
   ri-review per la controprova che la guardia, da sola, NON e' pinnabile
   allo stesso modo: con questo `try` presente, un TypeError da
   `window.HirisBuildCheck` assente e' comunque ingoiato, quindi nessuna
   asserzione sul pallino puo' distinguere "guardia tolta" da "guardia
   presente" -- e' l'aritmetica dichiarata dalla ri-review, non un test
   nuovo che la nasconde. */
test('boot della chat: HirisBuildCheck presente ma verifica() solleva dentro -- il pallino resta connesso (N1, ri-review)', async (t) => {
  const ctx = loadScripts(MODULI, { html: fixtureHtml('stampX') });
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  ctx.window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('api/health')) return jsonResponse({ status: 'ok', version: '3.0.0', build: 'stamp-nuovo' });
    return jsonResponse({});
  };
  ctx.window.HirisBuildCheck.verifica = () => {
    throw new Error('SecurityError simulato -- window.location.reload() in un iframe sandboxed');
  };

  const veroSet = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  try {
    assert.equal(typeof ctx.window.HirisBuildCheck, 'object',
      'precondizione del test: HirisBuildCheck E\' caricato (a differenza del test del guscio vecchio sotto)');
    // eval indiretto del file vero (vedi il commento in testa al file): e' il
    // meccanismo del test, non una svista.
    // eslint-disable-next-line no-eval -- vedi commento sopra
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
  }
  t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });

  const connDot = ctx.document.getElementById('conn-dot');
  assert.equal(connDot.textContent, 'connesso',
    'verifica() che solleva non deve mai far leggere "offline" -- e\' il caso che il `try` esiste per coprire');
  assert.equal(connDot.classList.contains('offline'), false);
});

test('boot della chat: guscio precedente a B8 (senza build-check.js) -- il pallino resta connesso, non offline', async (t) => {
  const MODULI_GUSCIO_VECCHIO = MODULI.filter((m) => m !== 'build-check.js');
  const ctx = loadScripts(MODULI_GUSCIO_VECCHIO, { html: fixtureHtml('stampX') });
  ctx.window.matchMedia = () => ({
    matches: false, media: '', addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {},
  });
  ctx.window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('api/health')) return jsonResponse({ status: 'ok', version: '3.0.0', build: 'stamp-nuovo' });
    return jsonResponse({});
  };

  const veroSet = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  try {
    assert.equal(typeof ctx.window.HirisBuildCheck, 'undefined',
      'precondizione del test: il guscio vecchio non carica build-check.js');
    // eval indiretto del file vero (vedi il commento in testa al file): e' il
    // meccanismo del test, non una svista.
    // eslint-disable-next-line no-eval -- vedi commento sopra
    (0, eval)(readFileSync(MAIN, 'utf8'));
    await tick(0);
    await tick(0);
  } finally {
    globalThis.setInterval = veroSet;
  }
  t.after(() => {
    ctx.window.HirisChatMessages.stopAllWaits();
    ctx.dom.window.close();
  });

  const connDot = ctx.document.getElementById('conn-dot');
  assert.equal(connDot.textContent, 'connesso',
    'HirisBuildCheck assente non deve mai far leggere "offline" -- e\' il limite gia\' dichiarato di B8, non un guasto da propagare');
  assert.equal(connDot.classList.contains('offline'), false);
});
