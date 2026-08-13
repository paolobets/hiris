import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* fetta E5 Task 2: la pagina #/impostazioni (config/impostazioni-route.js).
   E' la prima interfaccia che i campi di ImpostazioniChat abbiano mai avuto:
   fino a quel task si cambiavano solo scrivendo a mano
   /data/impostazioni_chat.json. Qui si verifica cio' che un tester UAT fa
   davvero -- apre la pagina, vede i valori in vigore, ne cambia uno, salva, e
   capisce se e' andata bene o male.

   fetta "la catena diventa l'unica verita'" (Task 4): i campi sono SEI. Il
   selettore del modello e' uscito -- era uno scavalco della catena della
   pagina Modelli -- e con lui la lettura di GET api/models, che questa pagina
   non fa piu'. */

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
  response_mode: 'compact',
  thinking_budget: 2048,
  max_chat_turns: 4,
  restrict_to_home: true,
  modi_risposta: ['auto', 'compact', 'minimal'],
  default_system_prompt: 'IL PROMPT PREDEFINITO NEL CODICE.',
};

/* Il finto server: risponde all'unica rotta che la pagina usa. Le opzioni
   permettono a ogni test di rompere solo il pezzo che gli interessa.

   La finta e' SCOMODA proprio dove serve a questo task: `api/models` non e'
   piu' prevista da nessun ramo, quindi se la pagina tornasse a chiederla si
   prenderebbe la risposta delle impostazioni -- un oggetto senza `providers`
   -- invece di una finta compiacente costruita apposta per accoglierla. Il
   test «mount: la pagina non chiede piu' l'elenco dei modelli» lo pinna
   direttamente sulle chiamate, cosi' il ritorno dello scavalco non puo'
   passare in silenzio. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    chiamate.push({ url: u, opts: options || {} });
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

/* I controlli si cercano per il titolo del loro campo, non per posizione:
   cercarli per tipo o per indice li legherebbe all'ordine in cui `render` li
   costruisce, che non e' cio' che questi test vogliono dire. */
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

test('mount: il GET popola tutti e sei i campi', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  assert.equal(controllo(document, 'Nome').value, 'HIRIS');
  assert.equal(controllo(document, 'Prompt di sistema').value, 'Il prompt salvato dall\'utente.');
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
    'max_chat_turns', 'nome', 'response_mode', 'restrict_to_home',
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
// fetta «la catena diventa l'unica verita'» (Task 4): il modello non si
// sceglie piu' qui. Qui vivevano i tre test del selettore -- la tenda coi
// modelli dei provider credenziati, il modello salvato che resta
// selezionabile, il ripiego a campo di testo quando GET api/models non
// risponde. Sono usciti col loro SOGGETTO, non perche' davano fastidio: non
// c'e' piu' un selettore da provare, e nessuna delle tre situazioni e'
// rappresentabile.
// ---------------------------------------------------------------------------

test('il modello non si sceglie più qui, e la pagina dice dove', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);
  const outlet = document.getElementById('route-outlet');
  /* Si cerca il TITOLO di un campo, con la stessa regola di `controllo()`, non
     la parola «Modello» nel testo della pagina: quella parola vive anche nel
     sottotitolo qui sotto («nella pagina Modelli») e nella descrizione del
     budget di ragionamento, quindi un assert sul testo resterebbe verde
     mentre il selettore torna. Il brief proponeva
     /Forma della risposta[\s\S]*Modello\b/: non poteva fallire, perche' il
     selettore stava PRIMA di «Forma della risposta», non dopo. */
  const titoli = Array.from(outlet.querySelectorAll('div'))
    .filter((d) => d.style.fontWeight === '500')
    .map((d) => d.textContent);
  assert.deepEqual(titoli, [
    'Nome', 'Prompt di sistema', 'Forma della risposta',
    'Budget di ragionamento (token)', 'Tetto di turni per sessione',
  ], 'nessun campo «Modello» nella pagina');
  assert.match(outlet.textContent, /si sceglie per provider, nella pagina Modelli/);
});

test('mount: la pagina non chiede più l\'elenco dei modelli', async () => {
  const { window, chiamate } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);
  assert.deepEqual(chiamate.map((c) => c.url), ['api/impostazioni-chat'],
    'questa pagina non ha piu\' nessuna ragione di conoscere i provider');
});

// ---------------------------------------------------------------------------
// Fix round 1 (I-2): la descrizione di thinking_budget non promette piu' un
// log che su due percorsi su tre non esisteva.
// ---------------------------------------------------------------------------

test('la descrizione di thinking_budget dice DOVE vale, e non promette effetto ovunque', async () => {
  const { window, document } = montaConServer();
  window.HirisImpostazioniRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Vale solo con i modelli Claude sul percorso diretto/,
    'il tester deve sapere prima di scrivere il valore che altrove non ha effetto');
  assert.match(testo, /OpenAI, OpenRouter, Ollama/);
  assert.match(testo, /modalità abbonamento/);
  assert.doesNotMatch(testo, /viene disattivato comunque e il log lo dice/,
    'la vecchia frase era vera su un percorso su tre: era una dichiarazione falsa al presente');
});
