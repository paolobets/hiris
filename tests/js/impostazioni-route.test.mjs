import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* fetta E5 Task 2: la pagina #/impostazioni (config/impostazioni-route.js).
   E' la prima interfaccia che i sette campi di ImpostazioniChat abbiano mai
   avuto: fino a questo task si cambiavano solo scrivendo a mano
   /data/impostazioni_chat.json. Qui si verifica cio' che un tester UAT fa
   davvero -- apre la pagina, vede i valori in vigore, ne cambia uno, salva, e
   capisce se e' andata bene o male. */

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/impostazioni-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const IMPOSTAZIONI = {
  nome: 'HIRIS',
  system_prompt: 'Il prompt salvato dall\'utente.',
  model: 'claude-opus-4-7',
  response_mode: 'compact',
  thinking_budget: 2048,
  max_chat_turns: 4,
  restrict_to_home: true,
  modi_risposta: ['auto', 'compact', 'minimal'],
  default_system_prompt: 'IL PROMPT PREDEFINITO NEL CODICE.',
};

const MODELLI = {
  providers: [
    { id: 'anthropic', label: 'Claude', models: ['auto', 'claude-haiku-4-5-20251001', 'claude-opus-4-7'] },
    { id: 'openai', label: 'OpenAI', models: ['gpt-4o'] },
  ],
};

/* Il finto server: risponde alle due rotte che la pagina usa. Le opzioni
   permettono a ogni test di rompere solo il pezzo che gli interessa. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    chiamate.push({ url: u, opts: options || {} });
    if (u.indexOf('api/models') === 0) {
      if (opts.modelliRotti) throw new Error('rete giu\'');
      return jsonResponse(opts.modelli === undefined ? MODELLI : opts.modelli,
        opts.modelliStatus);
    }
    if ((options || {}).method === 'PUT') {
      if (opts.putRotto) throw new Error('rete giu\'');
      return jsonResponse(opts.putBody || Object.assign({ ok: true }, IMPOSTAZIONI),
        opts.putStatus);
    }
    if (opts.getRotto) return jsonResponse({ error: 'boom' }, 503);
    return jsonResponse(opts.impostazioni || IMPOSTAZIONI);
  };
  return Object.assign(ctx, { chiamate });
}

/* I controlli si cercano per il titolo del loro campo, non per posizione: il
   selettore del modello puo' essere una <select> o un <input type=text>
   (fallback dichiarato), e cercare "la prima select" nasconderebbe proprio la
   differenza che alcuni di questi test verificano. */
function controllo(document, titolo) {
  const titoli = Array.from(document.querySelectorAll('div'))
    .filter((d) => d.textContent === titolo && d.style.fontWeight === '500');
  assert.ok(titoli.length, 'campo non trovato: ' + titolo);
  return titoli[0].parentNode.querySelector('input, select, textarea');
}

function bottone(document, testo) {
  return Array.from(document.querySelectorAll('button')).find((b) => b.textContent === testo);
}

// ---------------------------------------------------------------------------
// La pagina monta e mostra cio' che e' in vigore
// ---------------------------------------------------------------------------

test('mount: il GET popola tutti e sette i campi', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  assert.equal(controllo(document, 'Nome').value, 'HIRIS');
  assert.equal(controllo(document, 'Prompt di sistema').value, 'Il prompt salvato dall\'utente.');
  assert.equal(controllo(document, 'Modello').value, 'claude-opus-4-7');
  assert.equal(controllo(document, 'Forma della risposta').value, 'compact');
  assert.equal(controllo(document, 'Budget di ragionamento (token)').value, '2048');
  assert.equal(controllo(document, 'Tetto di turni per sessione').value, '4');
  assert.equal(document.querySelector('input[type=checkbox]').checked, true);
});

test('mount: la pagina dichiara che il salvataggio vale subito, senza riavvio', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);
  assert.match(document.getElementById('route-outlet').textContent,
    /non serve riavviare/,
    'l\'utente deve sapere se deve riavviare l\'add-on: qui non serve, e va detto');
});

test('un GET fallito lo dice, invece di lasciare una pagina vuota', async () => {
  const { window, document } = montaConServer({ getRotto: true });
  window.HirisImpostazioniRoute.mount();
  await tick(20);
  const outlet = document.getElementById('route-outlet');
  assert.match(outlet.textContent, /Non è stato possibile leggere le impostazioni/);
  assert.equal(outlet.querySelectorAll('input').length, 0,
    'niente form a meta\' su dati che non sono arrivati');
});

// ---------------------------------------------------------------------------
// Il salvataggio
// ---------------------------------------------------------------------------

test('«Salva» manda un PUT con X-Requested-With e i nomi italiani dei campi', async () => {
  const { window, document, chiamate } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  controllo(document, 'Nome').value = 'Casa';
  controllo(document, 'Tetto di turni per sessione').value = '9';
  bottone(document, 'Salva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const put = chiamate.find((c) => c.opts.method === 'PUT');
  assert.ok(put, 'il click su Salva deve mandare un PUT');
  assert.equal(put.url, 'api/impostazioni-chat');
  assert.equal(put.opts.headers['X-Requested-With'], 'fetch',
    'senza questo header csrf_middleware risponde 403');
  const corpo = JSON.parse(put.opts.body);
  assert.deepEqual(Object.keys(corpo).sort(), [
    'max_chat_turns', 'model', 'nome', 'response_mode', 'restrict_to_home',
    'system_prompt', 'thinking_budget',
  ]);
  assert.equal(corpo.nome, 'Casa');
  assert.equal(corpo.max_chat_turns, 9);
  assert.equal(corpo.restrict_to_home, true);
});

test('un esito riuscito si vede, e la pagina si riallinea a cio\' che il server ha davvero salvato', async () => {
  const { window, document } = montaConServer({
    putBody: Object.assign({ ok: true }, IMPOSTAZIONI, {
      system_prompt: 'IL PROMPT PREDEFINITO NEL CODICE.',
    }),
  });
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  controllo(document, 'Prompt di sistema').value = '   ';
  bottone(document, 'Salva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent, /Salvato/);
  assert.equal(controllo(document, 'Prompt di sistema').value,
    'IL PROMPT PREDEFINITO NEL CODICE.',
    'il server ha rimesso il default: la pagina deve mostrare quello, non cio\' che era stato digitato');
});

test('un 400 del server si vede, col messaggio che dice quale campo non va', async () => {
  const { window, document } = montaConServer({
    putStatus: 400,
    putBody: { error: '«thinking_budget» non può essere negativo (ricevuto -1).', campo: 'thinking_budget' },
  });
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  controllo(document, 'Budget di ragionamento (token)').value = '-1';
  bottone(document, 'Salva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /thinking_budget/, 'il messaggio del server deve arrivare all\'utente');
  assert.doesNotMatch(testo, /Salvato\./, 'un rifiuto non deve mai dire "Salvato"');
  assert.equal(bottone(document, 'Salva').disabled, false,
    'dopo un errore il bottone deve tornare cliccabile, non restare bloccato');
});

test('un errore di rete sul PUT si vede: mai un catch vuoto', async () => {
  const { window, document } = montaConServer({ putRotto: true });
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  bottone(document, 'Salva').dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  assert.match(document.getElementById('route-outlet').textContent,
    /non ha risposto/);
  assert.equal(bottone(document, 'Salva').disabled, false);
});

// ---------------------------------------------------------------------------
// Il prompt di sistema: la via di ritorno
// ---------------------------------------------------------------------------

test('«Ripristina il prompt predefinito» rimette il default che arriva dal server', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  const prompt = controllo(document, 'Prompt di sistema');
  prompt.value = 'una sciocchezza';
  bottone(document, 'Ripristina il prompt predefinito')
    .dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(prompt.value, 'IL PROMPT PREDEFINITO NEL CODICE.',
    'il default arriva dal payload del server, non da una copia tenuta nel frontend');
});

// ---------------------------------------------------------------------------
// Il selettore del modello: tenda quando si puo', campo di testo quando no
// ---------------------------------------------------------------------------

test('il modello e\' una tenda coi modelli dei provider credenziati', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  const sel = controllo(document, 'Modello');
  assert.equal(sel.tagName, 'SELECT');
  const valori = Array.from(sel.options).map((o) => o.value);
  assert.equal(valori[0], 'auto', 'auto per primo: e\' il default nel codice');
  assert.ok(valori.includes('gpt-4o'), 'i modelli di ogni provider devono esserci');
  assert.equal(valori.filter((v) => v === 'claude-opus-4-7').length, 1,
    'nessun duplicato quando il modello corrente e\' gia\' offerto da un provider');
});

test('il modello gia\' salvato resta selezionabile anche se nessun provider lo offre piu\'', async () => {
  const { window, document } = montaConServer({
    impostazioni: Object.assign({}, IMPOSTAZIONI, { model: 'openrouter:vendor/modello' }),
  });
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  const sel = controllo(document, 'Modello');
  assert.ok(Array.from(sel.options).map((o) => o.value).includes('openrouter:vendor/modello'),
    'aprire la pagina e salvare non deve perdere in silenzio il modello configurato');
  assert.equal(sel.value, 'openrouter:vendor/modello');
});

test('se l\'elenco dei modelli non arriva si ricade su un campo di testo, e lo si dice', async () => {
  const { window, document } = montaConServer({ modelliRotti: true });
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  const campo = controllo(document, 'Modello');
  assert.equal(campo.tagName, 'INPUT',
    'una tenda con la sola voce "auto" non permetterebbe di scrivere il modello che si vuole');
  assert.equal(campo.value, 'claude-opus-4-7');
  assert.match(document.getElementById('route-outlet').textContent,
    /Non è stato possibile leggere l'elenco dei modelli/,
    'il degrado si dichiara, non si subisce in silenzio');
});
