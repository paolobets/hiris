import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 2: prova comportamentale del difetto che
   rewireLegacyAfterMount() mascherava. Prima di questo task, ensureLegacy()
   iniettava i 7 script legacy UNA SOLA VOLTA per l'intera vita della pagina
   (dedupe su script[data-legacy]); ogni mount successivo dell'editor
   sostituiva l'innerHTML dei sc-body con nodi NUOVI, ma i listener IIFE-time
   dei file legacy restavano agganciati ai nodi VECCHI (detached) — solo il
   rewire manuale (6 comportamenti reimplementati a mano) teneva in vita
   l'interazione al secondo mount. Ora non c'è più iniezione: i file sono
   <script src> statici, e populatePermessi() crea una nuova istanza di
   HirisEntityPicker (con i propri listener) a ogni mount — quindi il secondo
   mount deve funzionare SENZA alcun rewire. */

// Frammento minimo di config.html sufficiente per HirisChatbotEditor.mount():
// route-outlet + tpl-agent-editor (stessa struttura/id del file reale) +
// chrome-here (breadcrumb, letto ma non richiesto).
const HTML = `<!doctype html><body>
  <div id="chrome-here"></div>
  <div id="route-outlet"></div>
  <template id="tpl-agent-editor">
    <div class="editor-grid">
      <div class="editor-content">
        <section class="section-card" id="sec-identita"><div class="sc-body" id="sc-body-identita"></div></section>
        <section class="section-card" id="sec-istruzioni"><div class="sc-body" id="sc-body-istruzioni"></div></section>
        <section class="section-card" id="sec-modello"><div class="sc-body" id="sc-body-modello"></div></section>
        <section class="section-card" id="sec-permessi"><div class="sc-body" id="sc-body-permessi"></div></section>
        <section class="section-card" id="sec-stato"><div class="sc-body" id="sc-body-stato"></div></section>
        <section class="section-card" id="sec-log"><div class="sc-body" id="sc-body-log"></div></section>
        <section class="section-card" id="sec-run"><div class="sc-body" id="sc-body-run"></div></section>
        <section class="section-card" id="sec-consumi"><div class="sc-body" id="sc-body-consumi"></div></section>
        <div class="sticky-actions-wrap" id="sticky-actions-wrap">
          <div class="sticky-actions" id="sticky-actions">
            <button class="btn btn-ghost" id="btn-cancel">Annulla</button>
            <button class="btn" id="btn-test-run">Test Run</button>
            <button class="btn btn-danger" id="btn-delete" style="display:none">Elimina</button>
            <button class="btn btn-primary" id="btn-save" disabled>Salva</button>
          </div>
        </div>
      </div>
      <aside class="anchor-nav" id="anchor-nav"></aside>
    </div>
  </template>
</body>`;

const SCRIPTS = [
  'config/state.js',
  'config/api.js',
  'config/entity-picker.js',
  'config/templates.js',
  'config/permessi.js',
  'config/log-row.js',
  'config/logs.js',
  'config/usage.js',
  'config/proposals.js',
  'config/chatbot-form.js',
  'config/chatbot-editor.js',
];

function setup(fetchRoutes) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  stubFetch(ctx.window, Object.assign({ 'api/models': { providers: [] } }, fetchRoutes || {}));
  return ctx;
}

test('nessuno script[data-legacy] viene mai creato a runtime', async () => {
  const { window, document } = setup();
  window.HirisChatbotEditor.mount(null);
  await tick(20);
  assert.equal(document.querySelector('script[data-legacy]'), null);
  // e nemmeno nel <head>, dove il vecchio loadScript() li appendeva
  assert.equal(document.head.querySelector('script[data-legacy]'), null);
});

test('al SECONDO mount (remount dopo navigazione) i controlli rispondono ancora', async () => {
  const { window, document } = setup();

  // Primo mount ("Nuovo Chatbot").
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  let pill = document.querySelector('#sc-body-permessi .domain-pill');
  assert.ok(pill, 'la pillola di dominio deve esistere al primo mount');
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(
    window.HirisAgentEntityPicker.getValue(),
    ['light.*'],
    'il click sulla pillola aggiunge il pattern al primo mount'
  );

  // Simula la navigazione via da #/chatbots/new (router che monta un'altra
  // route, sostituendo il contenuto di #route-outlet con qualcos'altro).
  document.getElementById('route-outlet').innerHTML = '<div class="page-title">Altra pagina</div>';

  // Secondo mount: prima di questo task, i listener IIFE-time dei file
  // legacy sarebbero rimasti agganciati ai nodi del PRIMO mount (mai
  // ricaricati — ensureLegacy() era one-shot) e rewireLegacyAfterMount()
  // avrebbe dovuto reimplementare a mano il comportamento della pillola.
  // Ora populatePermessi() crea una nuova istanza HirisEntityPicker con i
  // propri listener freschi: deve funzionare senza alcun rewire.
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  pill = document.querySelector('#sc-body-permessi .domain-pill');
  assert.ok(pill, 'la pillola di dominio deve esistere anche al secondo mount');
  assert.deepEqual(
    window.HirisAgentEntityPicker.getValue(),
    [],
    'la nuova istanza al remount parte pulita (non eredita la selezione del mount precedente)'
  );
  pill.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(
    window.HirisAgentEntityPicker.getValue(),
    ['light.*'],
    'il click sulla pillola funziona ANCHE dopo un remount, senza alcun rewire manuale'
  );

  // Anche la ricerca testuale (Enter per aggiungere) deve rispondere al
  // secondo mount — altro comportamento prima reimplementato a mano in
  // rewireLegacyAfterMount().
  const search = document.querySelector('#sc-body-permessi .ep-search');
  assert.ok(search, 'il campo di ricerca entità deve esistere al secondo mount');
  search.value = 'switch.cucina';
  search.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  assert.ok(
    window.HirisAgentEntityPicker.getValue().indexOf('switch.cucina') !== -1,
    'Enter nel campo di ricerca aggiunge il pattern anche dopo il remount'
  );
});

test('il token counter (Istruzioni) risponde anche al secondo mount', async () => {
  const { window, document } = setup();

  window.HirisChatbotEditor.mount(null);
  await tick(20);
  let promptField = document.getElementById('f-prompt');
  promptField.value = 'una istruzione di prova';
  promptField.dispatchEvent(new window.Event('input', { bubbles: true }));
  const firstTotal = document.getElementById('tc-total').textContent;
  assert.notEqual(firstTotal, '—', 'il contatore token si aggiorna al primo mount');

  document.getElementById('route-outlet').innerHTML = '<div>altra pagina</div>';
  window.HirisChatbotEditor.mount(null);
  await tick(20);

  // initNewAgent() richiama updateTokenCounter() sui campi vuoti del nuovo
  // mount (base cost soltanto) — non e' '—' per design, e' il valore di
  // riferimento PRIMA di digitare qualunque cosa nel secondo mount.
  promptField = document.getElementById('f-prompt');
  const baselineSecondMount = document.getElementById('tc-total').textContent;
  // Testo lungo apposta: il totale è arrotondato a un decimale di k-token
  // (fmtTok), quindi una manciata di caratteri in più non sposterebbe la
  // cifra mostrata pur essendo l'handler chiamato correttamente — qui serve
  // un salto grande abbastanza da rendere il confronto testuale affidabile.
  promptField.value = 'x'.repeat(4000);
  promptField.dispatchEvent(new window.Event('input', { bubbles: true }));
  assert.notEqual(
    document.getElementById('tc-total').textContent,
    baselineSecondMount,
    'il token counter risponde anche al secondo mount (era wired via rewireLegacyAfterMount)'
  );
});
