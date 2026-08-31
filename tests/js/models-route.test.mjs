import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La pagina #/models (config/models-route.js). Fino alla 2.4.1 rispondeva a
   «com'è configurato?»; la domanda che l'utente ha davvero è «chi risponderà
   al mio prossimo messaggio, e quanto mi costa?». Questi test guardano quella
   risposta, e i gesti con cui si cambia. */

const SCRIPTS = ['config/models-route.js'];

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* IL PAYLOAD È IN DISACCORDO CON SE STESSO, DI PROPOSITO.
   `chain_order` dice claude-poi-openrouter; `catena[]` e `adesso.chi` dicono
   openrouter per primo. In produzione questo non succede (li compone lo stesso
   backend); qui succede perché è l'unico modo di distinguere «la pagina disegna
   ciò che riceve» da «la pagina ricalcola e per fortuna coincide». Se un giorno
   un `buildDisplayChain` tornasse in questo file, questi test cadono. */
const CONFIG = {
  chain_order: ['claude', 'openrouter'],
  provider_models: { claude: 'claude-opus-4-7', openai: '', openrouter: '' },
  ponte: { attivo: false, scadenza_min: 5, tetto_giornaliero: 50, modello: 'sonnet' },
  ollama: { modello: '', timeout_s: 120 },
  nascondi_gratuiti: false,
  strategia_ultima: 'balanced',
  seminato: true,
  fine_catena: 'ultimo della catena: se non risponde, la chat dà errore',
  catena: [
    { id: 'openrouter', nome: 'OpenRouter', modello: 'anthropic/claude-sonnet-4-6',
      modello_alias: false,
      natura: 'a consumo', manca: '', nota: '', connettore: 'se rifiuta, subito',
      connettore_nota: '', ha_credenziale: true, posizione: 1, riordinabile: true },
    { id: 'claude', nome: 'Claude API', modello: 'claude-opus-4-7',
      modello_alias: false,
      natura: 'a consumo', manca: '', nota: '', connettore: 'se rifiuta, subito',
      connettore_nota: '', ha_credenziale: true, posizione: 2, riordinabile: true },
  ],
  fuori_catena: [
    { id: 'subscription', nome: 'Piano Claude Max', modello: 'opus',
      modello_alias: true, natura: 'nel piano', manca: '',
      nota: 'Entra in catena quando il ponte è acceso, e il ponte si accende in Configurazione add-on.',
      ha_credenziale: true, posizione: null, riordinabile: false },
    { id: 'openai', nome: 'OpenAI', modello: 'gpt-4o', natura: 'a consumo',
      manca: 'manca la chiave', nota: '', ha_credenziale: false,
      posizione: null, riordinabile: true },
    { id: 'ollama', nome: 'Ollama (in casa)', modello: '', natura: 'in casa',
      manca: 'manca l\'indirizzo', nota: '', ha_credenziale: false,
      posizione: null, riordinabile: true },
  ],
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

/* LA FINTA E' SCOMODA anche qui: `api/models` non risponde mai per un provider
   che il test non ha dichiarato, esattamente come il backend vero non risponde
   per uno che non ha un elenco. Una finta che restituisse sempre qualcosa
   nasconderebbe il caso in cui il pannello si apre e non ha niente da dire --
   che e' il caso da cui dipende «nascondere e' crudele». */
function pannelloFinto(url, pannelli) {
  const id = decodeURIComponent(String(url).split('provider=')[1] || '');
  const voce = (pannelli || {})[id];
  return { providers: voce ? [voce] : [] };
}

function monta(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    chiamate.push({ url: u, opts: options || {} });
    if (u.indexOf('api/models?') === 0) {
      return opts.modelliRotto ? jsonResponse({ error: 'boom' }, 503)
        : jsonResponse(pannelloFinto(u, opts.pannelli));
    }
    if (u === 'api/models/config') {
      /* LA FINTA È SCOMODA DI PROPOSITO: dopo una PUT il server NON ricalcola
         la topologia, restituisce la stessa risposta di prima. Un frontend che
         si affidasse a un ricalcolo del server per aggiornare le posizioni
         sembrerebbe funzionare in un test generoso; qui passa solo chi
         aggiorna il proprio stato e si riordina i numeri da sé. */
      if ((options || {}).method === 'PUT') {
        return opts.putRotto ? jsonResponse({ error: 'boom' }, 503)
          : jsonResponse({ ok: true });
      }
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

/* ── Le righe della catena: i dati del payload, non una ricostruzione ─────── */

const CATENA = [
  { id: 'claude', nome: 'Claude API', modello: 'claude-opus-4-7',
    modello_alias: false, natura: 'a consumo', manca: '', nota: '', connettore: 'se rifiuta, subito',
    connettore_nota: '', ha_credenziale: true, posizione: 1, riordinabile: true },
  { id: 'openrouter', nome: 'OpenRouter', modello: 'anthropic/claude-sonnet-4-6',
    modello_alias: false, natura: 'a consumo', manca: '', nota: '',
    connettore: 'se rifiuta, subito',
    connettore_nota: '', ha_credenziale: true, posizione: 2, riordinabile: true },
];
const PIANO_FUORI = {
  id: 'subscription', nome: 'Piano Claude Max', modello: 'opus',
  modello_alias: true, natura: 'nel piano', manca: '',
  nota: 'Entra in catena quando il ponte è acceso, e il ponte si accende in Configurazione add-on.',
  connettore: '', connettore_nota: '',
  ha_credenziale: true, posizione: null, riordinabile: false,
};
/* Col ponte acceso il piano è la riga 1 e porta le due frasi del backend: la
   nota dice perché non si sposta, il connettore dice cosa succede se non
   risponde -- e OGGI dice che il messaggio va perso, perché il ponte non
   ripiega. Il giorno del ripiego cambia quella stringa, in Python. */
const PIANO_DENTRO = Object.assign({}, PIANO_FUORI, {
  posizione: 1,
  nota: 'In testa o fuori: ci sta perché il ponte è acceso, e il ponte si spegne in Configurazione add-on.',
  connettore: 'il ponte non ripiega: se non risponde entro 7 min il messaggio va perso',
  connettore_nota: 'sopra i 5 minuti la chat smette di aspettare prima: la risposta la trovi ricaricando',
});
const FUORI = [
  PIANO_FUORI,
  { id: 'openai', nome: 'OpenAI', modello: 'gpt-4o', modello_alias: false,
    natura: 'a consumo',
    manca: 'manca la chiave', nota: '', connettore: '', connettore_nota: '',
    ha_credenziale: false, posizione: null, riordinabile: true },
  { id: 'ollama', nome: 'Ollama (in casa)', modello: '', natura: 'in casa',
    manca: 'manca l\'indirizzo', nota: '', connettore: '', connettore_nota: '',
    ha_credenziale: false, posizione: null, riordinabile: true },
];

function righeCatena(document) {
  return Array.from(document.querySelectorAll('#catena-card .riga-provider'));
}

function righeFuori(document) {
  return Array.from(document.querySelectorAll('#fuori-card .riga-provider'));
}

/* I bottoni di una riga MENO quello del modello. Dal Task 9 il modello e' un
   bottone -- si clicca e apre il pannello -- quindi «questa riga non offre
   nessun gesto» non si scrive piu' come «non c'e' nessun bottone»: si scrive
   nominando quello che c'e'. Restituisce le classi, cosi' un bottone nuovo si
   vede nel messaggio d'errore invece di far leggere «1 !== 0». */
function gestiDellaRiga(row) {
  return Array.from(row.querySelectorAll('button'))
    .filter((b) => !b.classList.contains('riga-modello'))
    .map((b) => b.className);
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

test('il riquadro «Adesso» è una regione viva che esiste PRIMA della risposta', async () => {
  /* `aria-live` annuncia le mutazioni di CONTENUTO di una regione, non la
     comparsa della regione stessa: un riquadro costruito già pieno e poi
     inserito non verrebbe letto da nessuno. Chi usa uno screen reader
     scoprirebbe la cosa più importante della pagina solo andandosela a cercare.
     Il guscio nasce vuoto al mount e viene riempito quando la risposta arriva. */
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  const guscio = adesso(document);
  assert.ok(guscio, 'il guscio deve esistere prima che la fetch risponda');
  assert.equal(guscio.getAttribute('aria-live'), 'polite');
  assert.equal(guscio.textContent, '', 'vuoto: non c\'è ancora niente da dire');
  await tick(20);
  assert.match(adesso(document).textContent, /Il prossimo messaggio va a OpenRouter/);
});

test('la pagina NON ricostruisce la catena: se il backend dice openrouter, dice openrouter', async () => {
  /* `chain_order` in questo payload dice claude per primo, `catena[]` dice
     openrouter. Una pagina che ricalcolasse la topologia scriverebbe «Claude
     API» in cima -- nella frase e nella prima riga. */
  const { window, document } = monta();
  window.HirisModelsRoute.mount();
  await tick(20);
  const testo = adesso(document).textContent;
  assert.match(testo, /OpenRouter/);
  assert.doesNotMatch(adesso(document).querySelector('.adesso-frase').textContent,
    /Claude API/,
    'la frase deve venire da adesso.frase, non da una ricostruzione di chain_order');
  assert.deepEqual(righeCatena(document).map((r) => r.querySelector('.riga-nome').textContent),
    ['OpenRouter', 'Claude API'],
    'anche il disegno della catena viene dal payload, non da chain_order');
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

/* ── C1 della revisione finale: dopo un GET fallito non si scrive ───────────
   I tre preset «Rifai la catena» stanno nell'INTESTAZIONE della sezione 01, e
   `renderErrore` ridisegna solo `#catena-body` e `#fuori-body`: dopo un GET
   fallito restavano a schermo, e insieme a «Riprova» erano l'unica cosa
   cliccabile della pagina. `rifaiCatena` non aveva nessuna guardia sul
   caricamento: con `state.catena` e `state.fuoriCatena` vuote, `credenziati`
   e' `{}`, l'ordine filtrato e' `[]`, e `scriviCatena([])` mandava una PUT con
   lo `state.cfg` DI DEFAULT DEL MODULO -- catena vuota, nessun modello per
   provider, ponte e Ollama ai predefiniti, e `seminato: false`.

   Il backend applicava tutto (erano tutte in `_OUR_KEYS`). Da quel
   momento la chat rispondeva «Nessun provider utilizzabile in catena», e al
   riavvio successivo la semina rigirava. Un click. */

test('dopo un GET fallito i preset non possono scrivere', async () => {
  const ctx = monta({ configRotta: true });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);

  const preset = Array.from(ctx.document.querySelectorAll('.sc-actions button'));
  assert.equal(preset.length, 3,
    'i tre preset restano a schermo: stanno nell\'intestazione della sezione, '
    + 'e renderErrore ridisegna solo il corpo');
  assert.ok(preset.every((b) => b.disabled),
    'e sono spenti, perché un preset RIFÀ la catena e rifarla su uno stato mai '
    + 'letto vuol dire cancellarla');

  /* La guardia non è solo l'attributo: `state.caricato` rifiuta la scrittura
     anche a chi il bottone lo attiva da fuori (un `disabled = false` da
     console, un click sintetico). L'attributo è la metà che si vede. */
  preset.forEach((b) => { b.disabled = false; });
  preset[0].dispatchEvent(new ctx.window.Event('click'));
  await tick(20);

  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT');
  assert.equal(put.length, 0,
    'un click su un preset dopo un GET fallito ha mandato una PUT: quel corpo '
    + 'è lo `state.cfg` di default del modulo, e azzera l\'intero archivio');
});

test('dopo un GET riuscito i preset tornano vivi', async () => {
  /* Il gemello obbligatorio: una guardia che non si riapre mai è un bottone
     rotto, e sarebbe verde allo stesso modo. */
  const ctx = monta();
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const preset = Array.from(ctx.document.querySelectorAll('.sc-actions button'));
  assert.equal(preset.length, 3);
  assert.ok(preset.every((b) => !b.disabled));
  preset[0].dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  assert.equal(ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').length, 1);
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
  const { window, document } = monta({ config: { ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 }, adesso: {
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

/* ── Il gesto dentro la diagnosi ──────────────────────────────────────────
   Il bottone che il Task 14 non poteva costruire: `ponte.attivo` veniva
   dall'ambiente, e una PUT su un valore letto dall'ambiente torna 200 e viene
   buttata via al riavvio. Con la versione B vive nell'archivio, e il gesto
   arriva dal backend come ETICHETTA + PERCORSO + VALORE: la pagina non sa che
   cosa sta accendendo, applica un valore a una posizione e rilegge. */

function diagnosiConGesto(valore) {
  return { config: { adesso: {
    chi: 'claude', nome: 'Claude API', modello: 'claude-opus-4-7',
    natura: 'a consumo', via: 'catena',
    frase: 'Il prossimo messaggio va a Claude API, con claude-opus-4-7, a consumo.',
    diagnosi: [{
      gravita: 'spreco',
      testo: 'Il Piano Claude Max ha il token, lo paghi, ed è fuori dalla catena.',
      azione: { etichetta: 'Mettilo primo', dove: ['ponte', 'attivo'], valore: valore },
    }],
  } } };
}

test('la diagnosi che porta un gesto lo disegna, con le parole del backend', async () => {
  const ctx = monta(diagnosiConGesto(true));
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const bottone = adesso(ctx.document).querySelector('.diagnosi-azione');
  assert.ok(bottone, 'la diagnosi porta un\'azione e la pagina non la disegna');
  assert.equal(bottone.textContent, 'Mettilo primo');
  assert.ok(bottone.closest('.diagnosi-spreco'),
    'il gesto sta DENTRO la voce che lo motiva: staccato, non si sa perché cliccarlo');
});

test('una diagnosi senza gesto non disegna nessun bottone', async () => {
  /* Il gemello obbligatorio. Un bottone che compare sempre sarebbe verde allo
     stesso modo del test qui sopra, e offrirebbe un gesto anche dove non c'è
     niente da fare. */
  const ctx = monta();
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(adesso(ctx.document).querySelectorAll('.diagnosi-azione').length, 0);
});

test('il gesto scrive il PERCORSO che ha ricevuto, e poi rilegge', async () => {
  /* La pagina non ricompone la topologia da sé: ciò che cambia non è una
     posizione già determinata dal gesto (le frecce), è CHI RISPONDE -- la
     frase in cima, la presenza del piano in testa, il connettore. Ricomporlo
     qui vorrebbe dire calcolarlo, cioè rimettere la topologia nel frontend. */
  const ctx = monta(diagnosiConGesto(true));
  const letture = () => ctx.chiamate.filter(
    (c) => c.url === 'api/models/config' && (c.opts || {}).method !== 'PUT').length;
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const prima = letture();

  adesso(ctx.document).querySelector('.diagnosi-azione')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);

  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT');
  assert.equal(put.length, 1);
  assert.equal(JSON.parse(put[0].opts.body).ponte.attivo, true);
  assert.equal(letture(), prima + 1,
    'dopo il gesto la pagina deve RILEGGERE: chi risponde adesso, il piano in '
    + 'testa e il connettore li decide il backend, e ricomporli qui vorrebbe '
    + 'dire calcolarli');
});

test('il gesto sa portare anche il valore falso, senza saperlo', async () => {
  /* L'altra direzione passa dallo STESSO codice: se la pagina conoscesse il
     caso «accendi», spegnere richiederebbe un secondo ramo -- e sarebbe una
     regola del prodotto scritta in JavaScript. */
  const ctx = monta(diagnosiConGesto(false));
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  adesso(ctx.document).querySelector('.diagnosi-azione')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT');
  assert.equal(JSON.parse(put[0].opts.body).ponte.attivo, false);
});

test('un gesto che il disco rifiuta non resta a schermo come se fosse passato', async () => {
  /* Il valore va RIMESSO com'era, e non basta guardarlo nella PUT fallita:
     `state.cfg` viaggia INTERO a ogni scrittura successiva. Se il gesto
     rifiutato restasse dentro, il primo preset cliccato dopo lo porterebbe sul
     disco di straforo -- accendendo il ponte senza che nessuno lo abbia
     chiesto e senza che nessuna riga a schermo lo dica. Si guarda quindi il
     corpo della SCRITTURA SUCCESSIVA, che è dove il difetto arriverebbe. */
  const ctx = monta(Object.assign({ putRotto: true }, diagnosiConGesto(true)));
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  adesso(ctx.document).querySelector('.diagnosi-azione')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  assert.match(ctx.document.getElementById('catena-stato').textContent,
    /Salvataggio non riuscito/);

  ctx.document.querySelectorAll('.sc-actions button')[0]
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT');
  assert.equal(put.length, 2);
  assert.equal(JSON.parse(put[1].opts.body).ponte.attivo, false,
    'il valore rifiutato dal disco è rimasto in `state.cfg` e la scrittura '
    + 'successiva se lo porta dietro');
});

/* ── 01 LA CATENA e 02 FUORI DALLA CATENA ────────────────────────────────── */

test('la catena mostra posizione, nome, modello e natura di ogni riga', async () => {
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const righe = righeCatena(document);
  assert.equal(righe.length, 2);
  assert.equal(righe[0].querySelector('.riga-pos').textContent, '1');
  assert.equal(righe[0].querySelector('.riga-nome').textContent, 'Claude API');
  assert.equal(righe[0].querySelector('.riga-modello').textContent, 'claude-opus-4-7');
  assert.equal(righe[0].querySelector('.riga-natura').textContent, 'a consumo');
});

test('fra due righe c\'è il connettore, e l\'ultimo dice cosa succede se non risponde nessuno', async () => {
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const conn = Array.from(document.querySelectorAll('#catena-card .connettore'))
    .map((c) => c.textContent);
  assert.equal(conn.length, 2, 'un connettore fra le righe, e uno in fondo');
  assert.equal(conn[0], 'se rifiuta, subito');
  assert.equal(conn[1], 'ultimo della catena: se non risponde, la chat dà errore');
});

test('il connettore del piano dichiara i minuti, e non promette un ripiego che non esiste', async () => {
  /* Il numero è una decisione di qualcuno e si mostra. Ma la frase intorno al
     numero è quella del backend, ed è la sola affermazione di questa pagina
     che, scritta bene per domani, sarebbe falsa oggi: oggi il ponte NON
     ripiega, alla scadenza il messaggio va perso. Se la pagina componesse qui
     un «se non risponde, si passa al successivo», prometterebbe un ripiego che
     il prodotto non fa -- il difetto 3, ricomparso come didascalia. */
  const catena = [PIANO_DENTRO, Object.assign({}, CATENA[0], { posizione: 2 })];
  const { window, document } = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 }, catena: catena, fuori_catena: [] } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const conn = document.querySelectorAll('#catena-card .connettore')[0];
  assert.equal(conn.textContent,
    'il ponte non ripiega: se non risponde entro 7 min il messaggio va perso');
});

test('sopra i 5 minuti la riga in più sta SOTTO il connettore, non dentro', async () => {
  /* `scadenza_min` accetta 1..120, ma la chat smette di aspettare a
     CHAT_POLL_MAX_MS (5 minuti): sopra i cinque, la risposta arriva quando il
     browser non guarda più. Questa fetta DICHIARA e non risolve -- è un fatto,
     non un divieto. Il testo sta in un nodo suo: il connettore è la frase, e la
     frase è il numero. */
  const catena = [PIANO_DENTRO, Object.assign({}, CATENA[0], { posizione: 2 })];
  const sopra = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 }, catena: catena, fuori_catena: [] } });
  sopra.window.HirisModelsRoute.mount();
  await tick(20);
  const nota = sopra.document.querySelector('#catena-card .connettore-nota');
  assert.ok(nota, 'la riga in più deve esistere');
  assert.match(nota.textContent, /sopra i 5 minuti la chat smette di aspettare prima/);
  assert.doesNotMatch(
    sopra.document.querySelectorAll('#catena-card .connettore')[0].textContent,
    /sopra i 5 minuti/, "dentro il connettore no: li' c'e' la frase con il numero");

  const senza = [Object.assign({}, PIANO_DENTRO, { connettore_nota: '' }),
    Object.assign({}, CATENA[0], { posizione: 2 })];
  const sotto = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 }, catena: senza, fuori_catena: [] } });
  sotto.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(sotto.document.querySelector('#catena-card .connettore-nota'), null,
    'sotto il tetto il backend non manda niente, e la pagina non inventa una riga');
});

test('una riga senza credenziale non sta in catena: sta fuori, e dice cosa manca', async () => {
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const fuori = righeFuori(document);
  assert.deepEqual(fuori.map((r) => r.querySelector('.riga-nome').textContent),
    ['Piano Claude Max', 'OpenAI', 'Ollama (in casa)']);
  const openai = fuori[1];
  assert.match(openai.textContent, /manca la chiave/);
  assert.deepEqual(gestiDellaRiga(openai), [],
    'senza credenziale non si offre «Usa»: sarebbe un bottone che non può funzionare');
  assert.equal(openai.querySelector('a'), null,
    'e nemmeno un collegamento che non naviga da nessuna parte');
  assert.match(document.getElementById('fuori-card').textContent,
    /Le chiavi si mettono in Configurazione add-on/,
    'dove si mette la credenziale si dice una volta, non su cinque righe');
});

test('«Usa» mette il provider in fondo alla catena, e salva l\'oggetto intero', async () => {
  const fuori = [PIANO_FUORI,
    Object.assign({}, FUORI[1], { ha_credenziale: true, manca: '' }),
    FUORI[2]];
  const ctx = monta({ config: { catena: CATENA, fuori_catena: fuori } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const usa = Array.from(ctx.document.querySelectorAll('#fuori-card button'))
    .find((b) => b.textContent === 'Usa');
  usa.dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop();
  assert.ok(put, 'un click deve produrre una PUT');
  const corpo = JSON.parse(put.opts.body);
  assert.deepEqual(corpo.chain_order, ['claude', 'openrouter', 'openai']);
  assert.deepEqual(Object.keys(corpo).sort(),
    ['chain_order', 'nascondi_gratuiti', 'ollama', 'ponte', 'provider_models',
      'strategia_ultima'],
    'sempre l\'oggetto intero: una PUT parziale su un corpo di sei chiavi '
    + 'perderebbe le altre cinque. `seminato` NON è una di esse: è il segno '
    + 'della migrazione (versione A), non una decisione, e un client HTTP non '
    + 'deve poterlo riscrivere');
  assert.equal(righeCatena(ctx.document).length, 3, 'la riga si sposta subito');
  assert.equal(righeCatena(ctx.document)[2].querySelector('.riga-pos').textContent, '3');
});

test('il piano NON offre «Usa», perché quella PUT il server la butta via', async () => {
  /* La prova che vale il doppio delle altre. `save_models_config` scarta
     `subscription` da `chain_order` (`_VALID_BACKENDS` sono quattro nomi) e la
     presenza del piano in catena discende da `ponte.attivo`, che questa pagina
     non scrive e che nessuno legge dall'archivio finché il Task 13 non lo
     cabla. Un «Usa» sul piano manderebbe una PUT accettata con 200 e buttata
     via: la riga entrerebbe in catena a schermo e sarebbe di nuovo fuori alla
     prima ricarica -- cioè la pagina tornerebbe a mentire, con un bottone
     nuovo. Al suo posto la riga dice COME ci si entra, e la parola arriva dal
     backend. */
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const piano = righeFuori(document)[0];
  assert.equal(piano.querySelector('.riga-nome').textContent, 'Piano Claude Max');
  assert.deepEqual(gestiDellaRiga(piano), []);
  assert.match(piano.textContent, /Entra in catena quando il ponte è acceso/);
});

test('«(x)» toglie dalla catena, e se il salvataggio fallisce si torna esattamente com\'era', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI }, putRotto: true });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const via = righeCatena(ctx.document)[0].querySelector('.riga-esci');
  via.dispatchEvent(new ctx.window.Event('click'));
  await tick(30);
  const righe = righeCatena(ctx.document);
  assert.equal(righe.length, 2);
  assert.equal(righe[0].querySelector('.riga-nome').textContent, 'Claude API');
  assert.equal(righe[0].querySelector('.riga-pos').textContent, '1',
    'anche i numeri di posizione devono tornare quelli di prima');
  assert.equal(righeFuori(ctx.document).length, 3,
    'e la riga non deve restare anche fuori: sarebbe in due posti insieme');
  assert.match(ctx.document.getElementById('catena-card').textContent,
    /Salvataggio non riuscito/);
});

test('le frecce riordinano, e i numeri seguono senza aspettare il server', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  righeCatena(ctx.document)[1].querySelector('.riga-su')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.deepEqual(righe.map((r) => r.querySelector('.riga-nome').textContent),
    ['OpenRouter', 'Claude API']);
  assert.deepEqual(righe.map((r) => r.querySelector('.riga-pos').textContent), ['1', '2']);
});

test('la freccia che non ha niente da scambiare è spenta, non finta', async () => {
  /* Un bottone abilitato che non fa niente è la versione piccola del difetto
     di questa fetta. La prima riga non può salire e l'ultima non può scendere:
     lo dicono le frecce, prima del click. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.equal(righe[0].querySelector('.riga-su').disabled, true);
  assert.equal(righe[0].querySelector('.riga-giu').disabled, false);
  assert.equal(righe[1].querySelector('.riga-su').disabled, false);
  assert.equal(righe[1].querySelector('.riga-giu').disabled, true);
});

test('col ponte acceso la catena resta visibile e riordinabile, e si dice scavalcata', async () => {
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 },
    catena: [PIANO_DENTRO].concat(
      CATENA.map((r, i) => Object.assign({}, r, { posizione: i + 2 }))),
    fuori_catena: FUORI.slice(1) } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(righeCatena(ctx.document).length, 3);
  assert.equal(righeCatena(ctx.document)[2].querySelector('.riga-su').disabled, false,
    'la catena si prepara anche mentre è scavalcata');
  assert.ok(ctx.document.getElementById('catena-card').classList.contains('catena-inerte'),
    'disegnata come ciò che è: inerte, adesso -- ma non tolta');
  assert.match(ctx.document.querySelectorAll('#catena-card .connettore')[0].textContent,
    /il ponte non ripiega/,
    'e a dirlo è il connettore del backend, che cambierà con la regola');
});

test('un gesto col ponte acceso non fa sparire il piano dalla catena', async () => {
  /* La pagina si riordina da sé fra il gesto e la risposta del server, e quel
     riordino nasce da `chain_order` -- dove il piano NON c'è. Se ricomponesse
     solo da lì, il primo click su una freccia farebbe sparire la riga del piano
     fino alla ricarica: una riga che c'è, che risponde a tutti i messaggi, e che
     scompare perché hai spostato un'altra. Le righe che non si governano da
     `chain_order` restano dove il backend le ha messe. */
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 },
    catena: [PIANO_DENTRO].concat(
      CATENA.map((r, i) => Object.assign({}, r, { posizione: i + 2 }))),
    fuori_catena: FUORI.slice(1) } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  righeCatena(ctx.document)[2].querySelector('.riga-su')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.deepEqual(righe.map((r) => r.querySelector('.riga-nome').textContent),
    ['Piano Claude Max', 'OpenRouter', 'Claude API']);
  assert.deepEqual(righe.map((r) => r.querySelector('.riga-pos').textContent),
    ['1', '2', '3']);
});

test('la freccia scambia con la riga che si VEDE, non con una invisibile', async () => {
  /* `chain_order` può contenere un provider senza credenziale: resta salvato ma
     non si disegna. Scambiare con lui produrrebbe una freccia che si clicca e
     non muove niente -- e il provider invisibile cambierebbe posto di
     nascosto. Qui OpenAI sta in mezzo a `chain_order` senza credenziale: il
     click su «giù» di Claude deve scavalcarlo, e lasciarlo dov'è. */
  const ctx = monta({ config: {
    chain_order: ['claude', 'openai', 'openrouter'],
    catena: CATENA,
    fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  righeCatena(ctx.document)[0].querySelector('.riga-giu')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop();
  assert.deepEqual(JSON.parse(put.opts.body).chain_order,
    ['openrouter', 'openai', 'claude']);
  assert.deepEqual(righeCatena(ctx.document).map((r) => r.querySelector('.riga-nome').textContent),
    ['OpenRouter', 'Claude API']);
});

test('la riga del piano non porta frecce né «(x)», e dice perché', async () => {
  /* Il piano sta in testa o fuori. Una freccia che promettesse di spostarlo al
     secondo posto -- o una «(x)» che promettesse di toglierlo -- offrirebbe una
     cosa che il backend rifiuta: la sua presenza in catena discende dal ponte,
     e `chain_order` non lo contiene nemmeno. È il difetto che questa fetta
     esiste per chiudere, ricomparso nell'interfaccia. */
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 },
    catena: [PIANO_DENTRO].concat(
      CATENA.map((r, i) => Object.assign({}, r, { posizione: i + 2 }))),
    fuori_catena: FUORI.slice(1) } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const piano = righeCatena(ctx.document)[0];
  assert.equal(piano.querySelector('.riga-su'), null);
  assert.equal(piano.querySelector('.riga-giu'), null);
  assert.equal(piano.querySelector('.riga-esci'), null);
  assert.match(piano.textContent, /in testa o fuori/i);
});

test('la pagina non inventa gesti per una riga che il backend dice non riordinabile', async () => {
  /* La prova gemella, e la sola che distingue «la pagina obbedisce» da «la
     pagina conosce il caso del piano»: qui è OpenRouter a non essere
     riordinabile, e la pagina non ha nessuna ragione di saperlo. */
  const ctx = monta({ config: {
    catena: [CATENA[0], Object.assign({}, CATENA[1], { riordinabile: false })],
    fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(righeCatena(ctx.document)[1].querySelector('.riga-su'), null);
  assert.equal(righeCatena(ctx.document)[1].querySelector('.riga-esci'), null);
  assert.ok(righeCatena(ctx.document)[0].querySelector('.riga-su'));
});

test('nemmeno «Usa» si inventa: fuori catena, non riordinabile, niente bottone', async () => {
  /* Il gemello del gemello, sul gesto d'ingresso: un provider qualunque con la
     credenziale e `riordinabile: false` non deve ricevere «Usa». Senza questo,
     l'assenza del bottone sul piano potrebbe essere scritta con un
     `if (id === 'subscription')` e nessun test se ne accorgerebbe. */
  const ctx = monta({ config: {
    catena: CATENA,
    fuori_catena: [Object.assign({}, FUORI[1], {
      ha_credenziale: true, manca: '', riordinabile: false })] } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.deepEqual(gestiDellaRiga(righeFuori(ctx.document)[0]), []);
});

test('«Risparmio» rifà la catena, e ci mette solo chi ha una credenziale', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  Array.from(ctx.document.querySelectorAll('#catena-card button'))
    .find((b) => b.textContent === 'Risparmio')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop();
  assert.deepEqual(JSON.parse(put.opts.body).chain_order, ['openrouter', 'claude'],
    'ollama e openai non hanno credenziale: non entrano');
  assert.deepEqual(righeCatena(ctx.document).map((r) => r.querySelector('.riga-nome').textContent),
    ['OpenRouter', 'Claude API']);
});

test('la parola «Attivo» non compare da nessuna parte nella pagina', async () => {
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const testo = document.getElementById('route-outlet').textContent;
  for (const parola of ['Attivo', 'Disattivato', 'Disponibile', 'Funzionante']) {
    assert.ok(testo.indexOf(parola) === -1,
      'la pagina non deve affermare più di ciò che il sistema sa: trovato «' + parola + '»');
  }
});

test('la pagina non ha più niente da confessare sull\'ordine', async () => {
  /* Qui viveva la confessione: «L'ordine si applica al riavvio dell'add-on:
     fino ad allora la chat usa quello di prima, e ricaricando questa pagina lo
     rivedi». Era vera -- `handle_save_models_config` aggiornava l'archivio, ma
     la catena del router si costruiva all'avvio -- ed è uscita col difetto che
     la rendeva necessaria (la PUT chiama `app["ricalcola_catena"]`).

     Non è stata sostituita da un «vale subito»: l'assenza di didascalia È
     l'affermazione. Quindi si guarda l'ASSENZA, su tutta la pagina e non solo
     sulla card della catena, perché una didascalia di riavvio rimessa altrove
     sarebbe la stessa pagina che torna a mentire da un'altra riga. */
  const { window, document } = monta({ config: { catena: CATENA, fuori_catena: FUORI } });
  window.HirisModelsRoute.mount();
  await tick(20);
  const testo = document.getElementById('route-outlet').textContent;
  assert.ok(!/riavvi/i.test(testo),
    'la pagina dichiara un riavvio che non serve più: ' + testo);
  assert.equal(document.querySelector('.model-boot-hint'), null);
});

/* ── Il pannello del modello (Task 9) ─────────────────────────────────────
   La domanda del proprietario, quella che ha aperto tutta la fetta: «attivo
   Claude Max, ma poi come faccio a dire di utilizzare Haiku piuttosto che
   Sonnet o Opus? Stessa cosa per le API o OpenRouter: che modello scelgo fra
   quelli disponibili?».

   Il pannello NON compone nessuna frase e non sa niente dei casi particolari:
   la provenienza dell'elenco, la spiegazione, da quando la scelta ha effetto e
   DOVE va scritta arrivano dal payload. I test qui sotto guardano proprio
   questo -- che una parola a schermo sia quella ricevuta, e che cambiando il
   payload cambi lo schermo. */

const PANNELLO_OR = {
  id: 'openrouter', nome: 'OpenRouter', alias: false, elenco_completo: false,
  fonte: 'viva',
  provenienza: 'Letti da openrouter.ai adesso.',
  spiegazione: 'Solo modelli che sanno usare gli strumenti.',
  quando: 'Una frase qualsiasi del backend.',
  dove: ['provider_models', 'openrouter'],
  scelto: 'openrouter:anthropic/claude-sonnet-4-6',
  casella: { etichetta: 'nascondi i gratuiti', dove: ['nascondi_gratuiti'] },
  modelli: [
    { valore: 'openrouter:openai/gpt-4.1', nota: '' },
    { valore: 'openrouter:anthropic/claude-sonnet-4-6', nota: '' },
    { valore: 'openrouter:google/gemma-3-27b-it:free', nota: 'gratuito' },
  ],
};

const PANNELLO_PIANO = {
  id: 'subscription', nome: 'Piano Claude Max', alias: true,
  /* `elenco_completo` e `alias` coincidono qui, e sono due domande diverse:
     la prima dice che non c'è un quarto valore da cercare altrove, la
     seconda che il valore è un alias e non un identificatore. */
  elenco_completo: true, fonte: 'fissa',
  provenienza: 'Sono tutti quelli che esistono: il ponte parla con la CLI del piano.',
  spiegazione: 'Sono alias, non nomi di modello: qui la scelta non cambia '
    + 'quanto spendi, è compresa nel piano.',
  quando: '', dove: ['ponte', 'modello'], scelto: 'sonnet', casella: null,
  modelli: [
    { valore: 'haiku', nota: 'il più rapido' },
    { valore: 'sonnet', nota: 'l\'equilibrato' },
    { valore: 'opus', nota: 'il più capace' },
  ],
};

const PANNELLO_OLLAMA = {
  id: 'ollama', nome: 'Ollama (in casa)', alias: false, elenco_completo: false,
  fonte: 'viva',
  provenienza: 'Scaricati su http://192.168.1.42:11434 — letti adesso.',
  spiegazione: '', quando: '',
  dove: ['ollama', 'modello'], scelto: 'llama3.1:8b', casella: null,
  modelli: [
    { valore: 'llama3.1:8b', nota: '' },
    { valore: 'qwen2.5:14b', nota: '' },
  ],
};

function apriIlModello(ctx, riga) {
  riga.querySelector('.riga-modello').dispatchEvent(new ctx.window.Event('click'));
}

function pannello(document) {
  return document.querySelector('.pannello-modello');
}

test('l\'elenco dei modelli si legge SOLO quando il pannello si apre', async () => {
  /* Quella rotta interroga davvero OpenAI, OpenRouter e Ollama, con cinque
     secondi di pazienza ciascuno. Fino al Task 8 la pagina la leggeva a ogni
     caricamento per un risultato che nessuno guardava, e «letti adesso» detto
     su una lettura fatta all'apertura della pagina sarebbe più largo del
     fatto. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(ctx.chiamate.filter((c) => c.url.indexOf('api/models?') === 0).length, 0,
    'al caricamento non si interroga nessun provider');

  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const letture = ctx.chiamate.filter((c) => c.url.indexOf('api/models?') === 0);
  assert.deepEqual(letture.map((c) => c.url), ['api/models?provider=openrouter'],
    'e si chiede UN provider, non tutti e cinque');
});

test('il modello è cliccabile e apre un pannello che dichiara da dove viene l\'elenco', async () => {
  const riserva = Object.assign({}, PANNELLO_OR, { fonte: 'riserva',
    provenienza: 'Elenco di riserva: non ho potuto leggere openrouter.ai '
      + '(chiave rifiutata? rete?). Quello che vedi qui potrebbe non esistere più.' });
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: riserva } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const p = pannello(ctx.document);
  assert.ok(p);
  assert.match(p.textContent, /Elenco di riserva/);
  assert.match(p.textContent, /potrebbe non esistere più/);
  /* Il FATTO va nella classe, le parole nella frase: la stessa divisione di
     `diagnosi[].gravita` e `diagnosi[].testo` nel riquadro «Adesso». */
  assert.ok(p.querySelector('.pannello-provenienza').classList.contains('fonte-riserva'));
});

test('la provenienza è quella ricevuta, non una composta qui', async () => {
  /* La prova che distingue «la pagina disegna» da «la pagina conosce i due
     casi»: la frase è inventata, e deve comparire tale e quale. */
  const strana = Object.assign({}, PANNELLO_OR,
    { fonte: 'viva', provenienza: 'Frase che nessun codice di questa pagina saprebbe comporre.' });
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: strana } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  assert.equal(pannello(ctx.document).querySelector('.pannello-provenienza').textContent,
    'Frase che nessun codice di questa pagina saprebbe comporre.');
});

test('il pannello del piano offre tre alias e nessun identificatore', async () => {
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50, modello: 'sonnet' },
    catena: [Object.assign({}, PIANO_DENTRO, { posizione: 1 })], fuori_catena: [] },
    pannelli: { subscription: PANNELLO_PIANO } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[0]);
  await tick(20);
  const voci = Array.from(ctx.document.querySelectorAll('.pannello-modello label'))
    .map((l) => l.textContent.trim().split(' ')[0]);
  assert.deepEqual(voci, ['haiku', 'sonnet', 'opus']);
  assert.match(pannello(ctx.document).textContent, /compresa nel piano/);
});

test('il pannello del piano SCRIVE, e scrive dove gli viene detto', async () => {
  /* Fino alla 3.1.0 questo test asseriva il CONTRARIO -- «il pannello del piano
     MOSTRA e non scrive» -- e la ragione scritta accanto era vera: `dove` era
     vuoto perché il modello del piano era un effetto di quello di Claude API, e
     un controllo abilitato che non salva sarebbe stato peggio di uno spento.
     Era vera, ed era il difetto: un campo solo per due economie opposte, e il
     piano del proprietario girava con haiku. */
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 150, modello: 'haiku' },
    catena: [Object.assign({}, PIANO_DENTRO, { posizione: 1 })], fuori_catena: [] },
    pannelli: { subscription: PANNELLO_PIANO } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[0]);
  await tick(20);
  const radio = Array.from(ctx.document.querySelectorAll('.pannello-modello input[type=radio]'));
  assert.equal(radio.length, 3);
  assert.deepEqual(radio.map((r) => r.disabled), [false, false, false],
    'i tre alias si scelgono: il campo esiste');
  radio[2].checked = true;
  radio[2].dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT');
  assert.equal(put.length, 1);
  assert.equal(JSON.parse(put[0].opts.body).ponte.modello, 'opus',
    'e finisce nel percorso che il backend ha mandato, non in uno noto alla pagina');
});

test('dove l\'elenco è completo non c\'è niente da incollare', async () => {
  /* Accendendo `dove` si accende anche il campo di testo libero: nel pannello
     filtro e campo sono la stessa cosa. Sul piano vorrebbe dire incollare
     `gpt-4o`, salvarlo, e vederselo ridurre a `sonnet` dal validatore con un
     log che nessuno legge -- un controllo abilitato che non fa quello che dice,
     cioè la cosa che i tre radio spenti dichiaravano di voler evitare,
     rientrata dalla porta opposta. */
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 150, modello: 'haiku' },
    catena: [Object.assign({}, PIANO_DENTRO, { posizione: 1 })], fuori_catena: [] },
    pannelli: { subscription: PANNELLO_PIANO } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[0]);
  await tick(20);
  assert.equal(ctx.document.querySelector('.pannello-filtro'), null,
    'nessun campo dove non c\'è niente da cercare altrove');
});

test('dove l\'elenco è un pezzo di catalogo il campo c\'è', async () => {
  /* La polarità opposta, nello stesso file: senza questo test una guardia che
     togliesse il filtro a TUTTI lascerebbe la suite verde. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  assert.ok(ctx.document.querySelector('.pannello-filtro'),
    'duecento modelli senza un filtro sarebbero illeggibili');
});

test('scegliere un modello di OpenRouter salva l\'oggetto intero, e la pagina rilegge', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const radio = ctx.document.querySelectorAll('.pannello-modello input[type=radio]')[0];
  radio.checked = true;
  radio.dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  const put = ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop();
  const corpo = JSON.parse(put.opts.body);
  assert.equal(corpo.provider_models.openrouter, 'openrouter:openai/gpt-4.1');
  assert.deepEqual(Object.keys(corpo).sort(),
    ['chain_order', 'nascondi_gratuiti', 'ollama', 'ponte', 'provider_models',
      'strategia_ultima'],
    'sempre l\'oggetto intero, come ogni altra scrittura di questa pagina '
    + '-- e senza `seminato`, che è un segno di migrazione e non una decisione');
  /* E poi si RILEGGE. Le altre scritture si ridisegnano da sole perché ciò che
     cambiano -- le posizioni -- è già determinato dal gesto; qui no: il
     modello che una riga mostra è quello che il runtime userebbe, «auto» si
     risolve in un nome che solo il backend conosce, e la PRIMA FRASE della
     pagina nomina il modello. Lasciarla ferma la farebbe mentire in corpo 20. */
  const letture = ctx.chiamate.filter((c) => c.url === 'api/models/config'
    && (c.opts || {}).method !== 'PUT');
  assert.equal(letture.length, 2, 'una al mount, una dopo il salvataggio');
  assert.equal(pannello(ctx.document), null, 'e il pannello si chiude');
});

test('la didascalia del pannello è quella del backend, e sparisce quando il backend tace', async () => {
  /* La promessa che il Task 9 aveva scritto, e che il Task 10 ha riscosso:
     la didascalia non è scritta qui, quindi il giorno in cui il backend
     smette di avere un tempo da dichiarare la riga sparisce da sé, senza che
     nessuno tocchi il frontend. È successo -- `decisione_modelli` manda ""
     per tutti e cinque i provider, perché ogni valore di questa pagina vale
     dal prossimo messaggio -- e la coppia di prove resta: il canale è ancora
     lì, e non inventa niente quando è vuoto. */
  const parlante = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  parlante.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(parlante, righeCatena(parlante.document)[1]);
  await tick(20);
  assert.equal(pannello(parlante.document).querySelector('.pannello-quando').textContent,
    'Una frase qualsiasi del backend.');

  const muto = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: Object.assign({}, PANNELLO_OR, { quando: '' }) } });
  muto.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(muto, righeCatena(muto.document)[1]);
  await tick(20);
  assert.equal(pannello(muto.document).querySelector('.pannello-quando'), null,
    'senza la frase la pagina non ne inventa una');
});

test('il pannello scrive DOVE gli viene detto, e non sa dove sia', async () => {
  /* Il modello di Ollama non vive in `provider_models` (`_PROVIDER_MODEL_KEYS`
     non lo contiene: quella chiave è un fantasma, scartata in lettura e in
     scrittura). Senza il percorso nel payload, questa pagina avrebbe bisogno di
     un `if (id === 'ollama')` -- cioè di una regola del prodotto scritta una
     seconda volta, in un altro linguaggio, libera di divergere. */
  const fuori = [PIANO_FUORI, FUORI[1],
    Object.assign({}, FUORI[2], { ha_credenziale: true, manca: '',
      modello: 'llama3.1:8b' })];
  const ctx = monta({ config: { catena: CATENA, fuori_catena: fuori },
    pannelli: { ollama: PANNELLO_OLLAMA } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeFuori(ctx.document)[2]);
  await tick(20);
  const radio = ctx.document.querySelectorAll('.pannello-modello input[type=radio]')[1];
  radio.checked = true;
  radio.dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  const corpo = JSON.parse(ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop().opts.body);
  assert.equal(corpo.ollama.modello, 'qwen2.5:14b');
  assert.equal(corpo.provider_models.ollama, undefined,
    'il fantasma resta un fantasma: non lo si fa rivivere per sbaglio');
  assert.equal(corpo.ollama.timeout_s, 120, 'e il resto dell\'oggetto non si perde');
});

test('il campo in cima filtra la lista vera, e ciò che si digita resta salvabile', async () => {
  /* Il problema dei duecento: il pannello non è un catalogo. Digitando si
     filtra; e ciò che si digita compare in fondo come voce sua, perché il
     backend accetta qualunque stringa e chiudere quella porta toglierebbe una
     capacità in cambio di niente. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const campo = ctx.document.querySelector('.pannello-filtro');
  assert.ok(campo, 'il campo c\'è dove si può scrivere');
  campo.value = 'gpt';
  campo.dispatchEvent(new ctx.window.Event('input'));
  await tick(20);
  let valori = Array.from(ctx.document.querySelectorAll('.pannello-modello input[type=radio]'))
    .map((r) => r.value);
  assert.deepEqual(valori, ['openrouter:openai/gpt-4.1'],
    'la lista si stringe: le altre due non contengono «gpt»');

  campo.value = 'openrouter:x-ai/grok-4';
  campo.dispatchEvent(new ctx.window.Event('input'));
  await tick(20);
  valori = Array.from(ctx.document.querySelectorAll('.pannello-modello input[type=radio]'))
    .map((r) => r.value);
  assert.deepEqual(valori, ['openrouter:x-ai/grok-4'],
    'un identificatore che la lista non contiene resta scegliibile');
  const scelta = ctx.document.querySelectorAll('.pannello-modello input[type=radio]')[0];
  scelta.checked = true;
  scelta.dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  const corpo = JSON.parse(ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop().opts.body);
  assert.equal(corpo.provider_models.openrouter, 'openrouter:x-ai/grok-4');
});

test('«nascondi i gratuiti» salva e RILEGGE l\'elenco, senza chiudere il pannello', async () => {
  /* La casella agisce sulla lista che si sta guardando: il filtro è del
     backend (il ripiego lo dichiara nella riga di provenienza), quindi
     spuntarla senza rileggere lascerebbe a schermo l'elenco di prima. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const casella = ctx.document.querySelector('.pannello-casella input');
  assert.ok(casella);
  assert.equal(casella.checked, false, 'lo stato viene da state.cfg, non dal nulla');
  casella.checked = true;
  casella.dispatchEvent(new ctx.window.Event('change'));
  await tick(20);
  const corpo = JSON.parse(ctx.chiamate.filter((c) => (c.opts || {}).method === 'PUT').pop().opts.body);
  assert.equal(corpo.nascondi_gratuiti, true);
  assert.equal(ctx.chiamate.filter((c) => c.url.indexOf('api/models?') === 0).length, 2,
    'l\'elenco si rilegge: il filtro lo applica il backend');
  assert.ok(pannello(ctx.document), 'e il pannello resta aperto: stai guardando quello');
});

test('un pannello alla volta, e il secondo click su quello aperto lo chiude', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR, claude: Object.assign({}, PANNELLO_OR,
      { id: 'claude', nome: 'Claude API', dove: ['provider_models', 'claude'] }) } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[0]);
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  assert.equal(ctx.document.querySelectorAll('.pannello-modello').length, 1);
  assert.equal(righeCatena(ctx.document)[0].querySelector('.riga-modello')
    .getAttribute('aria-expanded'), 'false');
  assert.equal(righeCatena(ctx.document)[1].querySelector('.riga-modello')
    .getAttribute('aria-expanded'), 'true');

  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  assert.equal(pannello(ctx.document), null, 'il secondo click chiude');
});

test('un pannello che non si può leggere lo dice, e offre di riprovare', async () => {
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    modelliRotto: true });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  assert.match(pannello(ctx.document).textContent, /Non riesco a leggere/);
  assert.ok(Array.from(pannello(ctx.document).querySelectorAll('button'))
    .some((b) => b.textContent === 'Riprova'));
});

test('un alias si vede che è un alias, prima che qualcuno lo spieghi', async () => {
  /* Progetto §6.2: un identificatore ha l'aspetto di un identificatore, un
     alias ha l'aspetto di una parola. La differenza la porta il carattere, e
     il carattere lo decide un campo del payload -- non un `if` su un id. */
  const ctx = monta({ config: {
    ponte: { attivo: true, scadenza_min: 5, tetto_giornaliero: 50 },
    catena: [Object.assign({}, PIANO_DENTRO, { posizione: 1 })].concat(
      CATENA.map((r, i) => Object.assign({}, r, { posizione: i + 2 }))),
    fuori_catena: [] } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.ok(righe[0].querySelector('.riga-modello').classList.contains('modello-alias'));
  assert.ok(!righe[1].querySelector('.riga-modello').classList.contains('modello-alias'));
});

test('il pannello segue la sua riga quando la riga si sposta', async () => {
  /* Un dettaglio che si chiude perché hai spostato la riga che stavi
     guardando è una perdita senza ragione. */
  const ctx = monta({ config: { catena: CATENA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  righeCatena(ctx.document)[1].querySelector('.riga-su')
    .dispatchEvent(new ctx.window.Event('click'));
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.equal(righe[0].querySelector('.riga-nome').textContent, 'OpenRouter');
  assert.ok(righe[0].querySelector('.pannello-modello'),
    'il pannello è dentro la riga che si è mossa');
  assert.equal(ctx.document.querySelectorAll('.pannello-modello').length, 1);
});

/* ── La riga di stato: l'ultimo esito osservato ───────────────────────────
   È ciò che chiude il caso del proprietario: la pagina sapeva dire «Claude è
   primo in catena» e non «e sta rifiutando da quaranta richieste», mentre una
   chiave a credito zero veniva mostrata come funzionante.

   La frase arriva dal backend. Questi test guardano che la pagina la DISEGNI
   e non la componga: nessun conteggio, nessuna età, nessun codice calcolato
   qui -- se un giorno comparisse un `+ ' fa'` in questo file, cadono. */

const RIFIUTA = {
  tipo: 'rifiutato', famiglia: 'credenziale', codice: 400,
  messaggio: 'credit balance too low', quando: 9820, da_quante: 40, durata_s: 0.4,
};
const RISPONDE = {
  tipo: 'risposto', famiglia: '', codice: null, messaggio: '',
  quando: 9820, da_quante: 1, durata_s: 0,
};

/* IL PAYLOAD È IN DISACCORDO CON SE STESSO, DI PROPOSITO: la frase di Claude
   parla di 40 richieste e il suo `esito.da_quante` pure, ma la frase di
   OpenRouter dice una cosa che il suo `esito` non basterebbe a comporre
   («un'ora fa» contro un `quando` identico a quello di Claude). Una pagina che
   ricomponesse la frase dai campi scriverebbe la stessa età sulle due righe. */
const CATENA_OSSERVATA = [
  Object.assign({}, CATENA[0], {
    esito: RIFIUTA,
    stato_testo: 'ha rifiutato le ultime 40 richieste — credito esaurito (400), 3 min fa',
  }),
  Object.assign({}, CATENA[1], {
    esito: RISPONDE, stato_testo: 'ha risposto un\'ora fa',
  }),
];

function statoDi(row) {
  const n = row.querySelector('.riga-stato');
  return n ? n.textContent : null;
}

test('ogni riga porta la frase del backend, parola per parola', async () => {
  const ctx = monta({ config: { catena: CATENA_OSSERVATA, fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.equal(statoDi(righe[0]),
    'ha rifiutato le ultime 40 richieste — credito esaurito (400), 3 min fa');
  assert.equal(statoDi(righe[1]), 'ha risposto un\'ora fa',
    'la seconda frase non si ricompone dai campi: viene dal payload');
});

test('chi ha rifiutato smette di sembrare attivo, e non diventa un allarme', async () => {
  /* Non una riga rossa: il pallino diventa grigio-ambra e il nome perde peso.
     È la traduzione grafica del ritiro della parola «Attivo» -- una riga che
     non risponde deve smettere di sembrare attiva, non gridare. */
  const ctx = monta({ config: { catena: CATENA_OSSERVATA, fuori_catena: FUORI } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const righe = righeCatena(ctx.document);
  assert.ok(righe[0].classList.contains('riga-muta'));
  assert.equal(righe[0].querySelector('.dot').className, 'dot muto');
  assert.ok(righe[0].querySelector('.riga-stato').classList.contains('stato-rifiutato'));

  assert.ok(!righe[1].classList.contains('riga-muta'),
    'chi ha risposto resta com\'era');
  assert.equal(righe[1].querySelector('.dot').className, 'dot on');
  assert.ok(!righe[1].querySelector('.riga-stato').classList.contains('stato-rifiutato'));
});

test('l\'aspetto segue il FATTO, non la frase', async () => {
  /* La riga si spegne perché `esito.tipo` dice «rifiutato», non perché la
     frase contenga la parola «rifiutato». Qui la frase parla di un successo e
     il fatto dice il contrario: se la pagina leggesse il testo, sbaglierebbe.
     Dedurre una regola da una frase è come ricostruirla. */
  const bugiarda = [Object.assign({}, CATENA[0], {
    esito: RIFIUTA, stato_testo: 'ha risposto poco fa',
  })];
  const ctx = monta({ config: { catena: bugiarda, fuori_catena: [] } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  const riga = righeCatena(ctx.document)[0];
  assert.ok(riga.classList.contains('riga-muta'));
  assert.equal(riga.querySelector('.dot').className, 'dot muto');
});

test('niente da dire, nessuna riga vuota a schermo', async () => {
  /* `stato_testo` vuoto è ciò che il backend manda per una riga senza
     credenziale e senza osservazioni: lì la riga dice già «manca la chiave».
     Un div vuoto sotto ogni riga sarebbe rumore che allontana le altre. */
  const ctx = monta({ config: {
    catena: [Object.assign({}, CATENA[0], { esito: null, stato_testo: '' })],
    fuori_catena: [] } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(ctx.document.querySelectorAll('.riga-stato').length, 0);
});

test('anche chi sta fuori dalla catena dice cosa gli è successo', async () => {
  /* «Non l'hai ancora usato» su un provider credenziato e fuori dalla catena è
     un'informazione: quella chiave la paghi e non l'hai mai messa alla prova. */
  const fuori = [Object.assign({}, FUORI[0], {
    esito: null, stato_testo: 'non l\'hai ancora usato',
  })].concat(FUORI.slice(1));
  const ctx = monta({ config: { catena: CATENA, fuori_catena: fuori } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  assert.equal(statoDi(righeFuori(ctx.document)[0]), 'non l\'hai ancora usato');
});

test('la riga di stato non finisce dentro il pannello del modello', async () => {
  /* Il pannello si apre DENTRO la riga (grid-column 1/-1, come la nota e lo
     stato): tre blocchi a tutta larghezza nello stesso contenitore, e l'ordine
     conta -- lo stato appartiene alla riga, non al pannello che ci si apre
     dentro. */
  const ctx = monta({ config: { catena: CATENA_OSSERVATA, fuori_catena: FUORI },
    pannelli: { openrouter: PANNELLO_OR } });
  ctx.window.HirisModelsRoute.mount();
  await tick(20);
  apriIlModello(ctx, righeCatena(ctx.document)[1]);
  await tick(20);
  const riga = righeCatena(ctx.document)[1];
  assert.equal(riga.querySelectorAll('.riga-stato').length, 1);
  assert.equal(riga.querySelector('.pannello-modello .riga-stato'), null);
});
