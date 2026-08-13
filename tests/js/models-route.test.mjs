import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La pagina #/models (config/models-route.js). Fino alla 2.4.1 rispondeva a
   «com'è configurato?»; la domanda che l'utente ha davvero è «chi risponderà
   al mio prossimo messaggio, e quanto mi costa?». Questi test guardano quella
   risposta. */

const SCRIPTS = ['config/models-route.js'];

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* IL PAYLOAD È IN DISACCORDO CON SE STESSO, DI PROPOSITO.
   `chain_order` dice claude-poi-openrouter; `adesso.chi` dice openrouter. In
   produzione questo non succede (li compone lo stesso backend); qui succede
   perché è l'unico modo di distinguere «la pagina disegna ciò che riceve» da
   «la pagina ricalcola e per fortuna coincide». Se un giorno un
   `buildDisplayChain` tornasse in questo file, questi test cadono. */
const CONFIG = {
  chain_order: ['claude', 'openrouter'],
  provider_models: { claude: 'claude-opus-4-7', openai: '', openrouter: '' },
  providers: [
    { id: 'subscription', label: 'Piano Claude Max', active: false, has_credential: true, toggle: false },
    { id: 'claude', label: 'Claude API', active: true, has_credential: true, toggle: true },
    { id: 'openai', label: 'OpenAI', active: false, has_credential: false, toggle: false },
    { id: 'openrouter', label: 'OpenRouter', active: true, has_credential: true, toggle: true },
    { id: 'ollama', label: 'Ollama (in casa)', active: false, has_credential: false, toggle: false },
  ],
  llm_strategy: 'balanced',
  embeddings: { provider: '', model: '' },
  ollama_model: '',
  ponte_attivo: false,
  adesso: {
    chi: 'openrouter',
    nome: 'OpenRouter',
    modello: 'anthropic/claude-sonnet-4-6',
    natura: 'a consumo',
    via: 'catena',
    frase: 'Il prossimo messaggio va a OpenRouter, con anthropic/claude-sonnet-4-6, a consumo.',
    diagnosi: [
      { gravita: 'spreco',
        testo: 'Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.',
        azione: null },
    ],
  },
};

const MODELLI = { providers: [] };

function monta(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    chiamate.push({ url: u, opts: options || {} });
    if (u === 'api/models') return jsonResponse(opts.modelli || MODELLI);
    if (u === 'api/models/config') {
      if (opts.configRotta) return jsonResponse({ error: 'boom' }, 503);
      /* `configRaw` consegna il payload TALE E QUALE, senza fonderlo con
         CONFIG: e' l'unico modo di esprimere una CHIAVE ASSENTE. Con la sola
         `config` (fusione) un payload a cui il test toglie `adesso` se lo
         ritrova rimesso dalla base CONFIG -- la finta sarebbe piu' generosa
         del server, che quella chiave puo' davvero non mandarla. */
      if (opts.configRaw) return jsonResponse(opts.configRaw);
      return jsonResponse(Object.assign({}, CONFIG, opts.config || {}));
    }
    return jsonResponse({ ok: true });
  };
  return Object.assign(ctx, { chiamate });
}

function adesso(document) {
  return document.getElementById('adesso-card');
}

test('la prima cosa della pagina è la frase, e viene dal backend', async () => {
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  await tick(20);

  const card = adesso(document);
  assert.ok(card, 'il riquadro «Adesso» deve esistere');
  assert.equal(card.querySelector('.adesso-frase').textContent,
    'Il prossimo messaggio va a OpenRouter, con anthropic/claude-sonnet-4-6, a consumo.');
});

test('la pagina NON ricostruisce la catena: se il backend dice openrouter, dice openrouter', async () => {
  /* `chain_order` in questo payload dice claude per primo. Una pagina che
     ricalcolasse la topologia scriverebbe «Claude API» qui. */
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  await tick(20);
  const testo = adesso(document).textContent;
  assert.match(testo, /OpenRouter/);
  assert.doesNotMatch(adesso(document).querySelector('.adesso-frase').textContent,
    /Claude API/,
    'la frase deve venire da adesso.frase, non da una ricostruzione di chain_order');
});

test('le diagnosi compaiono sotto la frase, una per riga', async () => {
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  await tick(20);
  const righe = adesso(document).querySelectorAll('.adesso-diagnosi li');
  assert.equal(righe.length, 1);
  assert.equal(righe[0].textContent,
    'Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.');
});

test('nessuna diagnosi = nessun elenco vuoto a schermo', async () => {
  const { window, document } = monta({ config: {
    adesso: Object.assign({}, CONFIG.adesso, { diagnosi: [] }) } });
  window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(adesso(document).querySelectorAll('.adesso-diagnosi').length, 0,
    'lo stato buono è quello in cui la pagina è noiosa: niente lista vuota');
});

test('un payload senza «adesso» non stampa «undefined» in cima alla pagina', async () => {
  /* Difesa contro il caso in cui la pagina giri contro un backend più
     vecchio di lei (un browser con il JS in cache dopo un downgrade). */
  const cfg = Object.assign({}, CONFIG);
  delete cfg.adesso;
  const { window, document } = monta({ configRaw: cfg });
  window.HirisModelsRoute.mount();
  await tick(20);
  const card = adesso(document);
  assert.equal(card, null, 'senza dati non si disegna il riquadro');
  assert.doesNotMatch(document.getElementById('route-outlet').textContent, /undefined/);
});

test('un GET fallito lo dice, e non lascia il riquadro a metà', async () => {
  const { window, document } = monta({ configRotta: true });
  window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(adesso(document), null);
  assert.match(document.getElementById('route-outlet').textContent,
    /Errore caricamento provider/);
});

test('la risposta sta SOPRA le ragioni: il riquadro precede la prima sezione', async () => {
  /* Non e' un dettaglio estetico: e' il titolo del task. Una pagina che
     disegnasse la stessa frase IN FONDO sarebbe letteralmente conforme a
     tutti i test qui sopra e continuerebbe a far dedurre all'utente cio' che
     ora gli viene detto. Senza questa riga, spostare l'`insertBefore` in un
     `appendChild` non rompe niente. */
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  await tick(20);

  const outlet = document.getElementById('route-outlet');
  const figli = Array.from(outlet.children);
  const posCard = figli.indexOf(adesso(document));
  const posPrimaSezione = figli.indexOf(outlet.querySelector('.section-card'));
  assert.ok(posCard > -1 && posPrimaSezione > -1);
  assert.ok(posCard < posPrimaSezione,
    'il riquadro «Adesso» deve precedere la sezione 01');
  /* ...e dopo titolo e sottotitolo, che restano i primi due figli. */
  assert.ok(figli[0].classList.contains('page-title'));
  assert.ok(figli[1].classList.contains('page-subtitle'));
  assert.equal(posCard, 2);
});

test('ponte acceso senza token: la pagina lo dice in cima, in rosso', async () => {
  /* Lo stato dell'invariante 5, visto dalla pagina. `chi` e' null e non c'e'
     nessun nome da scrivere: se il riquadro sapesse comporre una frase da
     solo, qui scriverebbe «Il prossimo messaggio va a .» -- disegna invece
     `adesso.frase`, e la gravita' «guasto» diventa la classe che la CSS
     colora di --err-ink invece che di --warn-ink. */
  const { window, document } = monta({ config: { ponte_attivo: true, adesso: {
    chi: null, nome: '', modello: '', natura: '', via: '',
    frase: 'HIRIS non può rispondere: il ponte è acceso e manca il token del Piano Claude Max.',
    diagnosi: [{ gravita: 'guasto',
      testo: 'Il ponte è acceso ma manca il token: ogni messaggio viene accodato e scade dopo 5 minuti senza risposta.',
      azione: null }],
  } } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const card = adesso(document);
  assert.match(card.querySelector('.adesso-frase').textContent, /manca il token/);
  assert.equal(card.querySelectorAll('.diagnosi-guasto').length, 1);
});
