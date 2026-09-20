import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La scheda «Cosa ho capito» (config/watcher-sapere.js): il sapere, i giudizi
   sui tipi, le domande aperte e le correzioni del proprietario.

   Queste prove erano in `watcher-route.test.mjs` fino al taglio del
   18/09/2026 (spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md`).
   Sono le stesse: cambia il namespace della seam
   (`HirisWatcherSapere._rendiSapere`), la lista `SCRIPTS`, e il fatto che
   `mount` voglia il nome della scheda. Dove una prova cercava
   `.section-card[3]` ora cerca il pannello della scheda. */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'config');

/* IMPORTANT 2 (revisione Fable, giro di correzioni 1): `JUDGMENT_FIELD_GROUPS`
   qui sotto ripete -- di proposito, forma approvata task 9 -- l'elenco dei
   campi che `home_space/type_judgments.py::JUDGMENT_FIELD_NAMES` dichiara.
   E' esattamente il vocabolario a due lati di `agenda-route-vocabulary.test.mjs`
   (Python di un lato, JavaScript dell'altro, legati SOLO da una prova che
   legge entrambi i sorgenti): senza una prova cosi', un campo nuovo in Python
   (come `da_sapere_subito`, Task 1) puo' non comparire mai qui, ed e' successo
   davvero -- il giro 1 lo ha trovato a mano, non con una prova. */
const TYPE_JUDGMENTS_PY = readFileSync(
  join(CONFIG_DIR, '..', '..', 'home_space', 'type_judgments.py'), 'utf8');
const SORGENTE = readFileSync(join(CONFIG_DIR, 'watcher-sapere.js'), 'utf8');

const SCRIPTS = ['config/watcher-shared.js', 'config/watcher-giorno.js',
  'config/watcher-cosa-fare.js', 'config/watcher-sapere.js',
  'config/watcher-lavoro.js', 'config/state.js', 'config/router.js',
  'config/watcher-route.js'];

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* Il finto server della SOLA scheda «Cosa ho capito»: la sua lettura
   (`api/mind/knowledge`) e la sua scrittura (`api/mind/judgment`, con la
   chiave vera di `handlers_mind.handle_set_judgment` -- `riga`/`impronta`/
   `da`, o `errore` sul 400/409). Un altro indirizzo solleva. */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  const corpiInviati = [];
  ctx.window.fetch = async (url, init) => {
    const u = String(url);
    chiamate.push(u);
    if (init && init.body) corpiInviati.push(String(init.body));
    if (u.indexOf('api/mind/judgment') === 0) {
      if (opts.giudizioRotto) throw new Error('rete interrotta');
      return jsonResponse(
        opts.giudizio !== undefined ? opts.giudizio : { riga: null, impronta: 'x', da: 'sapere' },
        opts.giudizioStatus);
    }
    if (u.indexOf('api/mind/knowledge') === 0) {
      if (opts.sapereRotto) throw new Error('rete interrotta');
      return jsonResponse(
        opts.sapere !== undefined ? opts.sapere
          : { conteggi: { totale: 0, righe: [] }, non_capito: [] },
        opts.sapereStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate, corpiInviati });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
}

/* -------------------------------------------- il sapere sulla pagina (§8)

   «Se un dato c'è e nessuno può chiederlo, non esiste»: il sapere si leggeva
   da tre punti del codice e da nessuna pagina. E le righe che il modello non
   ha capito sono precisamente quelle che il proprietario risolverebbe in
   dieci secondi. */

function sapereFinto(extra) {
  return Object.assign({
    conteggi: { totale: 180, righe: [
      { specie: 'tipo', campo: 'significato', provenienza: 'importato', quante: 177 },
      { specie: 'dispositivo', campo: 'ricetta', provenienza: 'dedotto', quante: 3 },
    ] },
    non_capito: [],
    // Task 9 (sezione 04): le due chiavi nuove di `handle_knowledge`, sempre
    // presenti (anche vuote) cosi' i test che non le toccano non fanno
    // scoppiare `renderCorrections`/`renderSeedGroups`/`renderOpenQuestions`.
    giudizi: [],
    domande_aperte: [],
  }, extra || {});
}

/* Una riga di `judgment_listing` (mind/judgments.py), forma vera di
   `handle_knowledge`: `{soggetto_genere, soggetto, campo, valore, da, chi,
   quando_ts}`. Di proposito il default e' un'entita' con `da: "seme"` --
   ogni prova sovrascrive solo cio' che le serve. */
function giudizio(extra) {
  return Object.assign({
    soggetto_genere: 'entita', soggetto: 'binary_sensor.occupancy', campo: 'genere',
    valore: 'presenza', da: 'seme', chi: 'seme del repo', quando_ts: 1787000000,
  }, extra || {});
}

// Una `OpenQuestion` cosi' come la rende `handle_knowledge`
// (`{chiavi, domanda}` — spec 2026-09-16 §7).
function domandaAperta(extra) {
  return Object.assign({
    chiavi: ['stato:lock:jammed'],
    domanda: 'Una serratura `jammed`: è un **guasto**?',
  }, extra || {});
}

// Percorre gli antenati fino a `root` (escluso): vero se uno qualunque porta
// `hidden` -- serve a provare il flusso a DUE PASSI di «Torna al seme» senza
// indovinare la profondita' del DOM che lo costruisce.
function isHiddenAncestor(nodo, root) {
  for (var n = nodo; n && n !== root; n = n.parentElement) {
    if (n.hidden) return true;
  }
  return false;
}

// La riga `.jr-row` di un dato soggetto, dentro la sezione 04 -- serve a
// scoprire IL bottone giusto quando la sezione ne porta piu' di uno con lo
// stesso testo (es. «Scrivi» del modulo di aggiunta e «Scrivi» di un
// editor aperto).
function trovaRigaGiudizio(card, soggetto) {
  return Array.from(card.querySelectorAll('.jr-row')).find((r) => {
    var s = r.querySelector('.jr-subject');
    return s && s.textContent === soggetto;
  });
}

// I titoli veri (`h3`) di una scheda, nell'ordine in cui la resa li scrive.
function titoli(corpo) {
  return Array.from(corpo.querySelectorAll('h3')).map((h) => h.textContent);
}

function rendiSapere(payload) {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisWatcherSapere._rendiSapere(corpo, payload);
  return { window, document, corpo };
}

test('seam _rendiSapere: dice cosa ha capito, per specie e provenienza', () => {
  // «177 significati importati» e «tre ricette dedotte dal modello» sono due
  // fatti diversi. Mutazione che la uccide: stampare il solo totale.
  const { corpo } = rendiSapere(sapereFinto());
  const testo = corpo.textContent;
  assert.match(testo, /177/);
  assert.match(testo, /significati/);
  assert.match(testo, /importato/);
  assert.match(testo, /ricette/);
});

test('seam _rendiSapere: ciò che NON ha capito viene prima, con chi e quando', () => {
  // È l’unica parte su cui il proprietario può fare qualcosa: in fondo a un
  // elenco di conteggi non salterebbe all’occhio — stessa regola di «cosa non
  // si sa» nel resoconto.
  // Mutazione che la uccide: metterlo dopo i conteggi.
  const { corpo } = rendiSapere(sapereFinto({ non_capito: [
    { specie: 'dispositivo', soggetto: 'dev1', campo: 'ricetta_non_capita',
      valore: 'non ho capito cosa misura', provenienza: 'dedotto',
      chi: 'modello (ponte)', quando_ts: 1787000000 },
  ] }));
  const testo = corpo.textContent;
  assert.ok(testo.indexOf('non ho capito cosa misura') < testo.indexOf('177'),
    'ciò su cui si può agire viene prima');
  assert.match(testo, /modello \(ponte\)/);
});

test('seam _rendiSapere: se ha capito tutto lo DICE, e non tace', () => {
  // Un elenco vuoto senza una parola sembrerebbe una sezione rotta.
  // Mutazione che la uccide: non scrivere niente quando non c’è niente.
  const { corpo } = rendiSapere(sapereFinto());
  assert.match(corpo.textContent, /niente che non abbia capito/);
});

test('seam _rendiSapere: «non serve una ricetta» si legge in italiano, non in nome di colonna', () => {
  // Sulla casa vera sono 18 dispositivi su 52: la piastrella più grossa della
  // sezione. `ricetta_non_serve · dispositivo` si legge come un guasto, ed è
  // il contrario — è il modello che ha guardato e ha detto che non c'è niente
  // da misurare. La traduzione avviene al confine, che è questa pagina.
  // Mutazione che la uccide: stampare il nome del campo così com'è.
  const { corpo } = rendiSapere(sapereFinto({ conteggi: { totale: 18, righe: [
    { specie: 'dispositivo', campo: 'ricetta_non_serve', provenienza: 'dedotto',
      quante: 18 },
  ] } }));
  assert.match(corpo.textContent, /niente da misurare/);
  assert.doesNotMatch(corpo.textContent, /ricetta_non_serve/);
});

test('mount: la sezione 04 legge il sapere dalla sua rotta', () => {
  // Mutazione che la uccide: leggere `corpo.sapere` invece della busta vera.
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount('sapere');
  return tick(20).then(function () {
    const card4 = ctx.document.getElementById('watcher-panel-sapere');
    assert.ok(card4, 'la sezione 04 deve esistere');
    assert.match(card4.textContent, /177/);
  });
});

/* --------------------------------------------------- i giudizi sui tipi (Task 9)

   Forma approvata dal proprietario il 17/09/2026
   (.superpowers/sdd/2026-09-16-il-giudizio-dei-tipi/task-9-ux-approvata.md):
   «Cosa non ha capito» -> «Le tue correzioni» (righe `proprietario`+`altro`,
   modulo di aggiunta in testa) -> «I giudizi del seme» (sette gruppi chiusi:
   i sei approvati il 17/09/2026 piu' `da_sapere_subito`, 3.50.0)
   -> «Le domande aperte» (sei, chiuse) -> «Cosa ha capito». */

test('seam _rendiSapere: con solo giudizi «dal seme» non c’è «Torna al seme»', () => {
  // Mutazione che la uccide: mostrare il comando anche per `da: "seme"`.
  const { corpo } = rendiSapere(sapereFinto({ giudizi: [giudizio({ da: 'seme' })] }));
  assert.equal(bottone(corpo, 'Torna al seme'), undefined);
});

test('mount: una riga «da: proprietario» mostra la data e il comando a due passi «Torna al seme», che manda valore: null', async () => {
  // Mutazione che la uccide: non mostrare la data con l'anno, o mandare un
  // valore diverso da null, o saltare il secondo passo.
  const g = giudizio({
    da: 'proprietario', chi: 'proprietario', quando_ts: 1787000000,
    campo: 'notevole', valore: 'true',
  });
  const ctx = montaConServer({ sapere: sapereFinto({ giudizi: [g] }) });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  assert.match(card4.textContent, /Corretto da te il \d{2}\/\d{2}\/\d{4}/);

  const start = bottone(ctx.document, 'Torna al seme', card4);
  assert.ok(start, 'il comando esiste per una riga corretta dal proprietario');
  const yes = bottone(ctx.document, 'Sì, torna al seme', card4);
  assert.ok(yes, 'il secondo passo esiste nel DOM (nascosto)');
  assert.equal(isHiddenAncestor(yes, card4), true,
    'il secondo passo resta nascosto finché non si preme il primo — niente confirm()');

  start.click();
  assert.equal(isHiddenAncestor(yes, card4), false,
    'il secondo passo compare dopo aver premuto il primo');
  yes.click();
  await tick(20);

  const scritte = ctx.chiamate.filter((u) => u.indexOf('api/mind/judgment') === 0);
  assert.equal(scritte.length, 1, JSON.stringify(ctx.chiamate));
  const inviato = JSON.parse(ctx.corpiInviati[ctx.corpiInviati.length - 1]);
  assert.deepEqual(inviato, {
    soggetto_genere: g.soggetto_genere, soggetto: g.soggetto, campo: g.campo, valore: null,
  });
});

test('seam _rendiSapere: una riga «da: altro» mostra il badge di avviso, giorno/mese SENZA anno, e chi', () => {
  // Mutazione che la uccide: usare `badge-on` anche per «altro», o scrivere
  // l'anno (la forma approvata lo vuole SOLO per «proprietario»).
  const g = giudizio({ da: 'altro', chi: 'qualcun altro', quando_ts: 1787000000, campo: 'riposo' });
  const { corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const badge = corpo.querySelector('.agent-badge.badge-warn');
  assert.ok(badge, 'la riga «altro» porta il badge di avviso');
  assert.match(badge.textContent, /Modificata a mano il \d{2}\/\d{2} da qualcun altro/);
  assert.doesNotMatch(badge.textContent, /\d{4}/, 'niente anno per «altro» (forma approvata, punto 4)');
});

test('mount: correggere il genere manda {soggetto_genere, soggetto, campo: "genere", valore}, e un 400 mostra l’errore mantenendo la scelta', async () => {
  // Mutazione che la uccide: mandare un corpo diverso, o svuotare/resettare
  // la select dopo il rifiuto.
  const g = giudizio({
    da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'binary_sensor.motion',
    valore: 'presenza',
  });
  const ctx = montaConServer({
    sapere: sapereFinto({ giudizi: [g] }),
    giudizioStatus: 400,
    giudizio: { errore: 'questo soggetto non si può correggere qui' },
  });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  assert.ok(riga, 'la riga del seme esiste (dentro il gruppo «Genere»)');
  bottone(ctx.document, 'Correggi', riga).click();
  // Fix round 1 (IMPORTANT 2): il select non porta più `aria-label` -- ha
  // un'etichetta VERA (`for`/`id`, `judgmentField`) invece di un doppione
  // che l'avrebbe zittita per chi naviga per etichette.
  const select = riga.querySelector('select');
  assert.ok(select, 'l’editor del genere si apre dentro la riga');
  assert.equal(select.labels[0].textContent, 'Genere', 'l’etichetta è associata, non solo aria-label');
  select.value = 'sicurezza';
  bottone(ctx.document, 'Scrivi', riga).click();
  await tick(20);

  assert.match(card4.textContent, /questo soggetto non si può correggere qui/);
  assert.equal(select.value, 'sicurezza',
    'il valore scelto resta: il proprietario non deve riscegliere dopo un rifiuto');

  const inviato = JSON.parse(ctx.corpiInviati[ctx.corpiInviati.length - 1]);
  assert.deepEqual(inviato, {
    soggetto_genere: 'tipo', soggetto: 'binary_sensor.motion', campo: 'genere', valore: 'sicurezza',
  });
});

test('mount: un 409 dice che la correzione è scritta ma non è in vigore, col motivo del server', async () => {
  // Mutazione che la uccide: trattare il 409 come un successo silenzioso, o
  // come un 400 qualunque (senza dire che l'istantanea è tornata al seme).
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.dimmable' });
  const ctx = montaConServer({
    sapere: sapereFinto({ giudizi: [g] }),
    giudizioStatus: 409,
    giudizio: { errore: 'righe del sapere che non si interpretano: x', riga: null, impronta: 'y', da: 'solo seme' },
  });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  let card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  bottone(ctx.document, 'Scrivi', riga).click();
  await tick(30);

  card4 = ctx.document.getElementById('watcher-panel-sapere');
  assert.match(card4.textContent, /non è in vigore/);
  assert.match(card4.textContent, /righe del sapere che non si interpretano/);
  assert.match(card4.textContent, /Il sapere legge solo il seme/);
});

test('seam _rendiSapere: le domande aperte compaiono con la domanda e il conteggio delle chiavi, i backtick diventano <code> e i "**" si tolgono', () => {
  // Mutazione che la uccide: innerHTML col testo grezzo del server (i
  // backtick/`**` restano testo invece di diventare <code>/sparire).
  const domande = [domandaAperta({ domanda: 'Una serratura `jammed`: **è un guasto**?', chiavi: ['a', 'b', 'c'] })];
  const { corpo } = rendiSapere(sapereFinto({ domande_aperte: domande }));
  assert.match(corpo.textContent, /3 chiavi/);
  const code = corpo.querySelector('code');
  assert.ok(code, 'il backtick diventa un elemento <code>, non testo grezzo');
  assert.equal(code.textContent, 'jammed');
  assert.doesNotMatch(corpo.textContent, /\*\*/, 'i "**" si tolgono dal testo reso');
});

test('seam _rendiSapere: i gruppi del seme mostrano il conteggio calcolato dai dati, non scritto a mano', () => {
  // Mutazione che la uccide: un numero letterale al posto del conteggio, o
  // sommare le correzioni al totale invece di separarle col " · ".
  const giudizi = [
    giudizio({ campo: 'genere', da: 'seme', soggetto: 'light', soggetto_genere: 'tipo' }),
    giudizio({ campo: 'genere', da: 'seme', soggetto: 'light.dimmable', soggetto_genere: 'tipo' }),
    giudizio({ campo: 'genere', da: 'proprietario', soggetto: 'light.cucina', soggetto_genere: 'entita' }),
    giudizio({ campo: 'riposo', da: 'seme', soggetto: 'switch', soggetto_genere: 'tipo' }),
  ];
  const { corpo } = rendiSapere(sapereFinto({ giudizi }));
  const bottoni = Array.from(corpo.querySelectorAll('button'));
  const genere = bottoni.find((b) => b.textContent.indexOf('Genere ·') === 0);
  assert.ok(genere, 'il gruppo «Genere» esiste');
  assert.match(genere.textContent, /2 dal seme/, 'due righe restano nel seme (la terza vive in «Le tue correzioni»)');
  assert.match(genere.textContent, /1 corretta da te/);

  const riposo = bottoni.find((b) => b.textContent.indexOf('Riposo ·') === 0);
  assert.ok(riposo);
  assert.equal(riposo.textContent, 'Riposo · 1', 'senza correzioni il gruppo mostra solo il totale');
});

/* Giro di correzioni 1, punto 7: erano UNA prova sola, e le sue due metà non
   provavano la stessa cosa. Premere «Scrivi» senza radio scelto non arriva mai
   alla guardia JS: i radio sono `required`, e la validazione nativa del form
   (che jsdom implementa) ferma l'invio prima. Quella metà sorvegliava dunque
   l'attributo `required`, non il codice di questo modulo -- e il nome della
   prova diceva un'altra cosa. Due fatti, due prove. */

test('mount: senza tipo/entità il modulo di aggiunta non manda niente -- lo ferma `required` (validazione nativa del form)', async () => {
  // Mutazione che la uccide: togliere `input.required = true` da `radioOption`.
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const subjectInput = card4.querySelector('input[type=text]');
  subjectInput.value = 'binary_sensor.occupancy';
  assert.ok(Array.from(card4.querySelectorAll('input[type=radio]')).every((r) => r.required),
    'i radio sono `required`: è lui a fermare l\'invio, e va detto qui');
  bottone(ctx.document, 'Scrivi', card4).click();
  await tick(20);

  assert.equal(ctx.chiamate.filter((u) => u.indexOf('api/mind/judgment') === 0).length, 0,
    'senza scegliere tipo/entità non si manda niente: soggetto_genere non esiste');
  // E il messaggio della guardia JS NON compare: prova che l'invio si è
  // fermato PRIMA del gestore 'submit', cioè nella validazione nativa. È
  // questo che separa le due prove.
  assert.doesNotMatch(card4.textContent, /Scegli se è un tipo o un’entità/);
});

/* La GUARDIA JS -- quella che ferma un `submit` che la validazione nativa non
   ha visto -- è provata più sotto, «il modulo di aggiunta come <form> NON
   manda niente se si invia senza scegliere tipo/entità»: non se ne scrive una
   seconda qui. */

test('mount: scelto tipo/entità, la scelta guida soggetto_genere', async () => {
  // Mutazione che la uccide: ignorare quale dei due radio è stato scelto.
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const subjectInput = card4.querySelector('input[type=text]');
  subjectInput.value = 'binary_sensor.occupancy';
  const radioEntita = Array.from(card4.querySelectorAll('input[type=radio]')).find((r) => r.value === 'entita');
  assert.ok(radioEntita, 'il radio «un\'entità» esiste');
  radioEntita.checked = true;
  bottone(ctx.document, 'Scrivi', card4).click();
  await tick(20);

  const scritte = ctx.chiamate.filter((u) => u.indexOf('api/mind/judgment') === 0);
  assert.equal(scritte.length, 1, JSON.stringify(ctx.chiamate));
  const inviato = JSON.parse(ctx.corpiInviati[ctx.corpiInviati.length - 1]);
  assert.equal(inviato.soggetto_genere, 'entita');
  assert.equal(inviato.soggetto, 'binary_sensor.occupancy');
  assert.equal(inviato.campo, 'genere');
});

/* ============================================================================
   Fix round 1 (revisione Fable, task-9-report.md): IMPORTANT 1/2/3, MINOR
   4/5/6/7/8. Ogni prova qui sotto è stata scritta e vista ROSSA sul codice
   PRIMA della correzione corrispondente (vedi task-9-report.md, sezione
   «Fix round 1» per l'output di ogni corsa rossa).
   ========================================================================= */

// -- IMPORTANT 1: manca «la cronaca dei giorni passati si rifà da sola» -----

test('seam _rendiSapere: una riga «da: proprietario» dice anche che la cronaca dei giorni passati si rifà da sola (forma approvata, punto 3)', () => {
  // Mutazione che la uccide: non scrivere questa frase, o scriverla solo
  // come notifica transitoria invece che accanto al badge della riga.
  const g = giudizio({ da: 'proprietario', quando_ts: 1787000000 });
  const { corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const badge = corpo.querySelector('.agent-badge.badge-on');
  assert.ok(badge, 'il badge «corretto da te» esiste');
  assert.match(corpo.textContent, /La cronaca dei giorni passati si rifà da sola/);
});

test('seam _rendiSapere: la frase sulla cronaca NON compare per righe «seme» o «altro» (solo «proprietario» l’ha appena cambiata)', () => {
  const giudizi = [giudizio({ da: 'seme', soggetto: 'light.a' }), giudizio({ da: 'altro', soggetto: 'light.b', chi: 'x' })];
  const { corpo } = rendiSapere(sapereFinto({ giudizi }));
  assert.doesNotMatch(corpo.textContent, /La cronaca dei giorni passati si rifà da sola/);
});

// -- IMPORTANT 2: label non associate (for/id), non solo aria-label ---------

test('seam _rendiSapere: «Soggetto» e «Genere» del modulo di aggiunta hanno un’etichetta VERA (for/id), non solo aria-label', () => {
  // Mutazione che la uccide: lasciare `judgmentField` senza `id`/`htmlFor`.
  const { document, corpo } = rendiSapere(sapereFinto());
  const subjectInput = corpo.querySelector('.jr-add-form input[type=text]');
  assert.ok(subjectInput, 'il campo soggetto esiste');
  assert.equal(subjectInput.labels && subjectInput.labels.length, 1,
    'un’etichetta è associata al campo (non solo un placeholder)');
  assert.equal(subjectInput.labels[0].textContent, 'Soggetto');

  const select = corpo.querySelector('.jr-add-form select');
  assert.ok(select, 'il select del genere esiste');
  assert.equal(select.labels && select.labels.length, 1, 'un’etichetta è associata al select');
  assert.equal(select.labels[0].textContent, 'Genere');
  void document;
});

test('seam _rendiSapere: il select dell’editor del genere (dentro una riga) ha anch’esso un’etichetta associata', () => {
  const g = giudizio({ campo: 'genere', da: 'seme', soggetto: 'light.editor_label' });
  const { document, corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const riga = trovaRigaGiudizio(corpo, g.soggetto);
  bottone(document, 'Correggi', riga).click();
  const select = riga.querySelector('select');
  assert.ok(select, 'l’editor è aperto');
  assert.equal(select.labels && select.labels.length, 1);
  assert.equal(select.labels[0].textContent, 'Genere');
});

// -- IMPORTANT 3: il focus si perde su <body> in «Torna al seme» -----------

test('mount: «Torna al seme» sposta il focus ad ogni passo — niente focus perso su <body>', async () => {
  // Mutazione che la uccide: nascondere il bottone che ha il focus senza
  // spostarlo altrove (start.hidden/confirmBox.hidden senza .focus()).
  const g = giudizio({ da: 'proprietario', campo: 'notevole', soggetto: 'light.focus_revert' });
  const ctx = montaConServer({ sapere: sapereFinto({ giudizi: [g] }) });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  const start = bottone(ctx.document, 'Torna al seme', riga);
  const yes = bottone(ctx.document, 'Sì, torna al seme', riga);
  const cancel = bottone(ctx.document, 'Annulla', riga);

  start.click();
  assert.equal(ctx.document.activeElement, yes,
    'il focus passa al bottone di conferma quando si apre il secondo passo');

  cancel.click();
  assert.equal(ctx.document.activeElement, start,
    '«Annulla» riporta il focus sul comando che aveva aperto il passo');
});

// -- MINOR 4: manca il punto dopo {errore} nel messaggio del 409 -----------

test('mount: il messaggio del 409 mette un punto dopo {errore}, senza raddoppiarlo se l’errore lo porta già', async () => {
  const g1 = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.p1' });
  const ctx1 = montaConServer({
    sapere: sapereFinto({ giudizi: [g1] }),
    giudizioStatus: 409,
    giudizio: { errore: 'righe del sapere che non si interpretano: x', riga: null, impronta: 'y', da: 'solo seme' },
  });
  ctx1.window.HirisWatcherRoute.mount('sapere');
  await tick(20);
  let card4 = ctx1.document.getElementById('watcher-panel-sapere');
  bottone(ctx1.document, 'Correggi', trovaRigaGiudizio(card4, g1.soggetto)).click();
  bottone(ctx1.document, 'Scrivi', trovaRigaGiudizio(card4, g1.soggetto)).click();
  await tick(30);
  card4 = ctx1.document.getElementById('watcher-panel-sapere');
  assert.match(card4.textContent, /non si interpretano: x\. Il sapere legge solo il seme\./,
    'un punto separa {errore} dalla frase successiva');
  assert.doesNotMatch(card4.textContent, /x\.\. Il sapere/, 'niente punto raddoppiato');

  const g2 = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.p2' });
  const ctx2 = montaConServer({
    sapere: sapereFinto({ giudizi: [g2] }),
    giudizioStatus: 409,
    giudizio: { errore: 'il seme non ce l’ha.', riga: null, impronta: 'y', da: 'solo seme' },
  });
  ctx2.window.HirisWatcherRoute.mount('sapere');
  await tick(20);
  let card4b = ctx2.document.getElementById('watcher-panel-sapere');
  bottone(ctx2.document, 'Correggi', trovaRigaGiudizio(card4b, g2.soggetto)).click();
  bottone(ctx2.document, 'Scrivi', trovaRigaGiudizio(card4b, g2.soggetto)).click();
  await tick(30);
  card4b = ctx2.document.getElementById('watcher-panel-sapere');
  assert.match(card4b.textContent, /il seme non ce l’ha\. Il sapere legge solo il seme\./);
  assert.doesNotMatch(card4b.textContent, /ha\.\. Il sapere/, 'errore già puntato non raddoppia il punto');
});

// -- MINOR 5: le righe «altro» non entrano nel conteggio del gruppo del seme

test('seam _rendiSapere: il gruppo del seme conta anche le righe «altro» (modificate a mano)', () => {
  // Mutazione che la uccide: contare solo `da === 'proprietario'`.
  const giudizi = [
    giudizio({ campo: 'riposo', da: 'seme', soggetto: 'switch' }),
    giudizio({ campo: 'riposo', da: 'seme', soggetto: 'switch.x' }),
    giudizio({ campo: 'riposo', da: 'altro', chi: 'qualcun altro', soggetto: 'switch.y' }),
  ];
  const { corpo } = rendiSapere(sapereFinto({ giudizi }));
  const riposo = Array.from(corpo.querySelectorAll('button')).find((b) => b.textContent.indexOf('Riposo ·') === 0);
  assert.ok(riposo);
  assert.match(riposo.textContent, /2 dal seme/);
  assert.match(riposo.textContent, /1 modificata a mano/);
  assert.doesNotMatch(riposo.textContent, /corretta da te/, 'nessuna correzione del proprietario in questo gruppo');
});

test('seam _rendiSapere: il gruppo del seme mostra tutte e tre le parti quando ci sono sia correzioni che modifiche a mano', () => {
  const giudizi = [
    giudizio({ campo: 'lavoro', da: 'seme', soggetto: 'climate' }),
    giudizio({ campo: 'lavoro', da: 'proprietario', soggetto: 'climate.x' }),
    giudizio({ campo: 'lavoro', da: 'altro', chi: 'qualcun altro', soggetto: 'climate.y' }),
  ];
  const { corpo } = rendiSapere(sapereFinto({ giudizi }));
  const lavoro = Array.from(corpo.querySelectorAll('button')).find((b) => b.textContent.indexOf('Lavoro ·') === 0);
  assert.equal(lavoro.textContent, 'Lavoro · 1 dal seme · 1 corretta da te · 1 modificata a mano');
});

// -- MINOR 6: dopo un 200/409 il focus resta su <body> ----------------------

test('mount: dopo un 200 il focus si sposta sul titolo «Le tue correzioni», non si perde su <body>', async () => {
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.focus200' });
  const ctx = montaConServer({ sapere: sapereFinto({ giudizi: [g] }) });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  let card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  bottone(ctx.document, 'Scrivi', riga).click();
  await tick(30);

  card4 = ctx.document.getElementById('watcher-panel-sapere');
  const titolo = Array.from(card4.querySelectorAll('h3')).find((h) => h.textContent === 'Le tue correzioni');
  assert.ok(titolo, 'il titolo esiste dopo il ricaricamento');
  assert.equal(ctx.document.activeElement, titolo, 'il focus non torna su <body> dopo il ricaricamento');
});

test('mount: dopo un 409 il focus si sposta comunque sul titolo «Le tue correzioni»', async () => {
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.focus409' });
  const ctx = montaConServer({
    sapere: sapereFinto({ giudizi: [g] }),
    giudizioStatus: 409,
    giudizio: { errore: 'x', riga: null, impronta: 'y', da: 'solo seme' },
  });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  let card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  bottone(ctx.document, 'Scrivi', riga).click();
  await tick(30);

  card4 = ctx.document.getElementById('watcher-panel-sapere');
  const titolo = Array.from(card4.querySelectorAll('h3')).find((h) => h.textContent === 'Le tue correzioni');
  assert.equal(ctx.document.activeElement, titolo);
});

// -- MINOR 7: buchi nelle prove -----------------------------------------

test('seam _rendiSapere: il select del genere porta ESATTAMENTE le 4 opzioni approvate (mai guasto/energia/bilancio)', () => {
  const { corpo } = rendiSapere(sapereFinto());
  const select = corpo.querySelector('.jr-add-form select');
  const valori = Array.from(select.options).map((o) => o.value);
  assert.deepEqual(valori, ['funzionamento', 'presenza', 'sicurezza', 'nessuno']);
});

test('seam _rendiSapere: «Correggi» non compare su una riga che non è di campo «genere»', () => {
  const g = giudizio({ campo: 'accendibile', da: 'seme', soggetto: 'switch.no_correggi' });
  const { document, corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const riga = trovaRigaGiudizio(corpo, g.soggetto);
  assert.ok(riga, 'la riga esiste');
  assert.equal(bottone(document, 'Correggi', riga), undefined, 'niente editor per un campo che la v1 non tocca');
});

test('mount: un 503 sulla scrittura di un giudizio lo dice (il sapere non è collegato), e riabilita il bottone', async () => {
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.w503' });
  const ctx = montaConServer({ sapere: sapereFinto({ giudizi: [g] }), giudizioStatus: 503 });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);
  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  const scrivi = bottone(ctx.document, 'Scrivi', riga);
  scrivi.click();
  await tick(20);

  assert.match(riga.textContent, /non è collegato in questo momento/);
  assert.equal(scrivi.disabled, false, 'il bottone si riabilita dopo il guasto');
});

test('mount: un guasto di RETE sulla scrittura di un giudizio lo dice, e riabilita il bottone', async () => {
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.wnet' });
  const ctx = montaConServer({ sapere: sapereFinto({ giudizi: [g] }), giudizioRotto: true });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);
  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  const scrivi = bottone(ctx.document, 'Scrivi', riga);
  scrivi.click();
  await tick(20);

  assert.match(riga.textContent, /Non è stato possibile scrivere/);
  assert.equal(scrivi.disabled, false, 'il bottone si riabilita dopo il guasto di rete');
});

// -- MINOR 8: il modulo di aggiunta non è un <form> -------------------------

test('mount: il modulo di aggiunta è un <form>: inviarlo (evento submit) con tipo/entità scelto manda la POST', async () => {
  // Mutazione che la uccide: lasciare il modulo come <div> senza handler
  // di 'submit' (l'evento sintetico non troverebbe nessun listener).
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const form = card4.querySelector('form.jr-add-form');
  assert.ok(form, 'il modulo di aggiunta è un <form> vero (serve perché Invio nel campo testo lo invii)');

  form.querySelector('input[type=text]').value = 'binary_sensor.occupancy';
  form.querySelector('input[type=radio][value="entita"]').checked = true;
  form.dispatchEvent(new ctx.window.Event('submit', { cancelable: true, bubbles: true }));
  await tick(20);

  const scritte = ctx.chiamate.filter((u) => u.indexOf('api/mind/judgment') === 0);
  assert.equal(scritte.length, 1, JSON.stringify(ctx.chiamate));
});

test('mount: il modulo di aggiunta come <form> NON manda niente se si invia senza scegliere tipo/entità', async () => {
  /* **È QUESTA la prova della guardia JS** (giro di correzioni 1, punto 7):
     un `submit` sintetico non passa dalla validazione nativa del browser, che
     invece ferma da sola il click su «Scrivi» coi radio `required`. Senza il
     ramo `if (!scelto)` di `addJudgmentForm` partirebbe una POST con
     `soggetto_genere: null`. Si asserisce anche il MESSAGGIO: fermarsi in
     silenzio, per chi guarda, è indistinguibile da un guasto.
     Mutazione ESEGUITA: togliere il ramo `if (!scelto)` -- rossa
     (`1 !== 0`); ripristinata con l'editor, sha256 identico. */
  const ctx = montaConServer({ sapere: sapereFinto() });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);

  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const form = card4.querySelector('form.jr-add-form');
  form.querySelector('input[type=text]').value = 'binary_sensor.occupancy';
  form.dispatchEvent(new ctx.window.Event('submit', { cancelable: true, bubbles: true }));
  await tick(20);

  assert.equal(ctx.chiamate.filter((u) => u.indexOf('api/mind/judgment') === 0).length, 0);
  assert.match(form.textContent, /Scegli se è un tipo o un’entità/);
});

/* Giro di correzioni 1, punto 8: il 503 sulla scrittura ha DUE ragioni. */

test('mount: un 503 che porta la sua ragione mostra QUELLA, non il testo di riserva', async () => {
  // Mutazione ESEGUITA: `judgmentWriteErrorText` che ignora `corpo` -- rossa
  // (compare «non è collegato in questo momento» invece del disco pieno).
  const g = giudizio({ da: 'seme', campo: 'genere', soggetto_genere: 'tipo', soggetto: 'light.wdisk' });
  const ctx = montaConServer({
    sapere: sapereFinto({ giudizi: [g] }),
    giudizio: { errore: 'il sapere non ha potuto scrivere (OperationalError: disco pieno)' },
    giudizioStatus: 503,
  });
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(20);
  const card4 = ctx.document.getElementById('watcher-panel-sapere');
  const riga = trovaRigaGiudizio(card4, g.soggetto);
  bottone(ctx.document, 'Correggi', riga).click();
  const scrivi = bottone(ctx.document, 'Scrivi', riga);
  scrivi.click();
  await tick(20);

  assert.match(riga.textContent, /disco pieno/);
  assert.doesNotMatch(riga.textContent, /non è collegato in questo momento/);
  assert.equal(scrivi.disabled, false, 'il bottone si riabilita dopo il guasto');
});

/* Giro di correzioni 1, punto 8 (BASSO x2): due invarianti della sezione 04
   che nessuna prova fissava. */

test('seam _rendiSapere: i cinque titoli della sezione 04 sono h3 veri, nell\'ordine della forma approvata', () => {
  /* La sorella `_rendiScope` ha la sua da sempre; questa no, e uno scambio di
     due chiamate in `renderKnowledge` -- «Cosa ha capito» prima delle
     correzioni, per dire -- sarebbe rimasto verde. L'ordine È la forma
     approvata: ciò su cui il proprietario può fare qualcosa viene prima dei
     conteggi.
     Mutazione ESEGUITA: scambiare `renderCorrections(...)` e
     `renderSeedGroups(...)` in `renderKnowledge` -- rossa (i due titoli di
     mezzo si invertono); ripristinata con l'editor, sha256 identico. */
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [giudizio({ da: 'proprietario', chi: 'proprietario' })],
    domande_aperte: [domandaAperta()],
  }));
  assert.deepEqual(titoli(corpo), [
    'Cosa non ha capito', 'Le tue correzioni', 'I giudizi del seme',
    'Le domande aperte', 'Cosa ha capito']);
});

test('seam _rendiSapere: «Torna al seme» c\'è anche sulle righe «da: altro», non solo «proprietario»', () => {
  /* Forma approvata: una riga modificata a mano fuori dalla porta è
     esattamente quella che il proprietario vuole poter rimettere a posto, e
     una mutazione che restringesse il controllo a `proprietario` sarebbe
     rimasta verde.
     Mutazione ESEGUITA: `if (g.da === 'proprietario')` al posto di
     `if (g.da === 'proprietario' || g.da === 'altro')` -- rossa (il bottone
     non c'è); ripristinata con l'editor, sha256 identico. */
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [giudizio({ da: 'altro', soggetto: 'light.a_mano', chi: 'ignoto' })],
  }));
  const riga = Array.from(corpo.querySelectorAll('.jr-row')).find((r) => {
    const s = r.querySelector('.jr-subject');
    return s && s.textContent === 'light.a_mano';
  });
  assert.ok(riga, 'la riga «altro» compare in «Le tue correzioni»');
  assert.ok(Array.from(riga.querySelectorAll('button')).some((b) => b.textContent === 'Torna al seme'),
    'anche una riga modificata a mano si può rimettere al seme');
});

/* Giro di correzioni 1 (revisione Fable, IMPORTANT 2): i due elenchi dei
   campi dei giudizi, Python e JavaScript, legati da una prova sola --
   stesso pattern di `agenda-route-vocabulary.test.mjs`. Mutazione che deve
   far diventare rosso questo file: aggiungere un settimo... ottavo campo a
   `JUDGMENT_FIELD_NAMES` (`type_judgments.py`) senza il suo gruppo in
   `JUDGMENT_FIELD_GROUPS` (`watcher-route.js`) -- o il contrario. */

// `NOME_FIELD = "valore"`: costruisce nome-costante -> valore-stringa, per
// risolvere gli identificatori che `JUDGMENT_FIELD_NAMES` elenca (il
// frozenset porta nomi di costanti Python, non i valori).
function costantiCampoPython(sorgente) {
  const mappa = {};
  for (const m of sorgente.matchAll(/^(\w+_FIELD) = "([a-z_]+)"$/gm)) {
    mappa[m[1]] = m[2];
  }
  return mappa;
}

test('i campi dei giudizi: lo stesso insieme in type_judgments.py (JUDGMENT_FIELD_NAMES) e in watcher-route.js (JUDGMENT_FIELD_GROUPS)', () => {
  const mappa = costantiCampoPython(TYPE_JUDGMENTS_PY);

  const blocco = TYPE_JUDGMENTS_PY.match(/JUDGMENT_FIELD_NAMES = frozenset\(\{([\s\S]*?)\}\)/);
  assert.ok(blocco, 'JUDGMENT_FIELD_NAMES non trovata in type_judgments.py '
    + '(e\' cambiata forma sotto questo test?)');
  const nomiCostanti = blocco[1].split(',').map((s) => s.trim()).filter(Boolean);
  assert.ok(nomiCostanti.length >= 7, 'attesi almeno sette campi (erano sei prima '
    + 'del Task 1 di «da sapere subito»): ' + nomiCostanti.join(', '));

  const python = new Set(nomiCostanti.map((nome) => {
    assert.ok(mappa[nome], 'costante non risolta: ' + nome
      + ' (manca una riga `' + nome + ' = "..."` in type_judgments.py?)');
    return mappa[nome];
  }));

  const m = SORGENTE.match(/var JUDGMENT_FIELD_GROUPS = \[([\s\S]*?)\];/);
  assert.ok(m, 'JUDGMENT_FIELD_GROUPS non trovata in watcher-route.js');
  const js = new Set(Array.from(m[1].matchAll(/campo:\s*'([a-z_]+)'/g)).map((mm) => mm[1]));

  assert.deepEqual(js, python,
    'JUDGMENT_FIELD_GROUPS (JavaScript) deve elencare esattamente gli stessi campi di '
    + 'JUDGMENT_FIELD_NAMES (Python): un campo nuovo da un lato solo sparisce dalla pagina '
    + 'del sapere in silenzio -- e\' successo davvero a `da_sapere_subito` (Task 1, giro 1)');
});

test('JUDGMENT_FIELD_GROUPS: ogni gruppo porta un\'etichetta italiana non vuota', () => {
  // Un campo che compare nell'insieme (prova sopra) ma con un'etichetta vuota
  // renderebbe una riga muta in «I giudizi del seme» -- distinto di proposito
  // dalla prova sull'insieme, cosi' chi legge il rosso sa subito quale delle
  // due cose e' storta.
  const m = SORGENTE.match(/var JUDGMENT_FIELD_GROUPS = \[([\s\S]*?)\];/);
  assert.ok(m, 'JUDGMENT_FIELD_GROUPS non trovata in watcher-route.js');
  const gruppi = Array.from(m[1].matchAll(/\{\s*campo:\s*'([a-z_]+)',\s*etichetta:\s*'([^']*)'\s*\}/g));
  assert.ok(gruppi.length >= 7, 'attesi almeno sette gruppi');
  for (const [, campo, etichetta] of gruppi) {
    assert.ok(etichetta.trim().length > 0, 'etichetta vuota per il campo: ' + campo);
  }
});

/* Revisione finale, I-3: le due prove qui sopra leggono i SORGENTI -- nessuna
   DISEGNA la sezione e cerca il campo nuovo. Il revisore ha disegnato solo i
   primi sei gruppi (`JUDGMENT_FIELD_GROUPS.slice(0, 6)` in `renderSeedGroups`)
   e **nessuna prova e' arrossita**: i due elenchi restavano identici, e la
   pagina non mostrava «Da sapere subito». Questa prova monta la sezione e
   guarda il DOM. */

test('seam _rendiSapere: la sezione DISEGNA un gruppo per OGNI campo dichiarato, «Da sapere subito» compreso', () => {
  /* Mutazione ESEGUITA: `JUDGMENT_FIELD_GROUPS.slice(0, 6).forEach(...)` in
     `renderSeedGroups` -- rossa qui («gruppo del seme non disegnato:
     da_sapere_subito»), verde su tutto il resto del file; ripristinata con
     l'editor.

     Si asserisce la PROPRIETA' (ogni gruppo dichiarato e' disegnato), non il
     solo fatto del settimo campo: cosi' anche l'ottavo, il giorno che
     arrivera', non potra' restare fuori dalla pagina in silenzio. */
  const m = SORGENTE.match(/var JUDGMENT_FIELD_GROUPS = \[([\s\S]*?)\];/);
  assert.ok(m, 'JUDGMENT_FIELD_GROUPS non trovata in watcher-route.js');
  const dichiarati = Array.from(m[1].matchAll(/\{\s*campo:\s*'([a-z_]+)',\s*etichetta:\s*'([^']*)'\s*\}/g))
    .map(([, campo, etichetta]) => ({ campo, etichetta }));
  assert.ok(dichiarati.some((g) => g.campo === 'da_sapere_subito'),
    'il campo di questa fetta deve essere fra i gruppi dichiarati');

  // Una riga di seme per ogni campo dichiarato: cosi' nessun gruppo puo'
  // mancare dal DOM per mancanza di dati invece che per un difetto di resa.
  const giudizi = dichiarati.map((g) => giudizio({
    campo: g.campo, da: 'seme', soggetto_genere: 'tipo', soggetto: 'binary_sensor.' + g.campo,
  }));
  const { corpo } = rendiSapere(sapereFinto({ giudizi }));
  const bottoni = Array.from(corpo.querySelectorAll('button')).map((b) => b.textContent);
  for (const g of dichiarati) {
    assert.ok(bottoni.some((t) => t.indexOf(g.etichetta + ' ·') === 0),
      'gruppo del seme non disegnato: ' + g.campo + ' («' + g.etichetta + '»). '
      + 'Bottoni trovati: ' + JSON.stringify(bottoni));
  }

  // E il gruppo nuovo porta davvero la sua riga dentro, non solo il titolo.
  const gruppoNuovo = Array.from(corpo.querySelectorAll('.field-group')).find((w) => {
    const b = w.querySelector('button');
    return b && b.textContent.indexOf('Da sapere subito ·') === 0;
  });
  assert.ok(gruppoNuovo, 'il gruppo «Da sapere subito» esiste nel DOM');
  const riga = gruppoNuovo.querySelector('.jr-row .jr-subject');
  assert.ok(riga, 'il gruppo «Da sapere subito» disegna la sua riga');
  assert.equal(riga.textContent, 'binary_sensor.da_sapere_subito');
});

/* Revisione finale, I-4: la pagina diceva il FALSO a chi corregge
   `da_sapere_subito`. Due frasi promettono che la cronaca si rifa' -- «La
   cronaca dei giorni passati si rifà da sola» accanto al badge, e «Anche questo
   rifà la cronaca degli ultimi 22 giorni» dentro «Torna al seme» -- ma la
   cronaca si rifa' solo per i campi che entrano nell'IMPRONTA
   (`type_judgments.CHRONICLE_FIELDS`: `genere` e `riposo`). Per `notevole`,
   `accendibile`, `lavoro`, `limiti_parametri` e `da_sapere_subito` quelle due
   frasi erano una promessa che nessuno mantiene. */

/* I due elenchi si leggono dal SORGENTE e diventano il dato della prova: i
   campi dichiarati (`JUDGMENT_FIELD_GROUPS`) e quelli dell'impronta
   (`CHRONICLE_JUDGMENT_FIELDS`). **Non si elencano a mano qui.** Una prova che
   scrivesse «genere e riposo si', da_sapere_subito no» asserirebbe il FATTO di
   oggi; queste asseriscono la PROPRIETA' -- la frase compare per tutti e soli
   i campi dell'impronta -- e restano vere il giorno in cui l'impronta cambia. */
function campiDichiarati() {
  const m = SORGENTE.match(/var JUDGMENT_FIELD_GROUPS = \[([\s\S]*?)\];/);
  assert.ok(m, 'JUDGMENT_FIELD_GROUPS non trovata in watcher-route.js');
  return Array.from(m[1].matchAll(/campo:\s*'([a-z_]+)'/g)).map((mm) => mm[1]);
}

function campiDellImpronta() {
  const m = SORGENTE.match(/var CHRONICLE_JUDGMENT_FIELDS = \{([^}]*)\};/);
  assert.ok(m, 'CHRONICLE_JUDGMENT_FIELDS non trovata in watcher-route.js');
  return new Set(Array.from(m[1].matchAll(/([a-z_]+):\s*true/g)).map((mm) => mm[1]));
}

// Un valore che la riga di QUEL campo sa mostrare, cosi' che la prova giri su
// tutti i campi senza inventare forme che il server non manderebbe mai.
const VALORE_PER_CAMPO = {
  genere: 'presenza',
  riposo: '["off"]',
  lavoro: '{"on": "acceso"}',
  limiti_parametri: '{"brightness": {"min": "a", "max": "b"}}',
  notevole: 'si',
  accendibile: 'si',
  da_sapere_subito: 'no',
};

test('seam _rendiSapere: la frase sulla cronaca compare per TUTTI e SOLI i campi dell\'impronta', () => {
  /* Mutazione ESEGUITA (la stessa del revisore): `rifaLaCronaca` riscritta
     come `return campo !== 'da_sapere_subito'`, che ignora del tutto la
     costante. **Con la stesura precedente di questa prova restava verde su
     417 prove**, perche' quella asseriva i due casi di oggi invece della
     proprieta' che li produce -- il difetto n. 1 del progetto, in casa nostra.
     Ora e' rossa su `notevole`. Ripristinata con l'editor.

     Cosa lasciava passare: il giorno in cui qualcuno corregge `notevole`, la
     pagina gli rimostrerebbe la frase falsa e nessuna prova lo direbbe. */
  const impronta = campiDellImpronta();
  assert.ok(impronta.size > 0, 'l\'impronta ha almeno un campo');
  const fuori = campiDichiarati().filter((c) => !impronta.has(c));
  assert.ok(fuori.length > 0,
    'servono campi FUORI dall\'impronta, o questa prova non avrebbe un lato negativo');

  const frase = /La cronaca dei giorni passati si rifà da sola/;
  for (const campo of campiDichiarati()) {
    const { corpo } = rendiSapere(sapereFinto({
      giudizi: [giudizio({
        da: 'proprietario', campo, soggetto: 'light.a', soggetto_genere: 'entita',
        valore: VALORE_PER_CAMPO[campo] || 'x',
      })],
    }));
    assert.match(corpo.textContent, /Corretto da te il/, 'il badge c\'e\' per ogni campo: ' + campo);
    if (impronta.has(campo)) {
      assert.match(corpo.textContent, frase,
        '`' + campo + '` entra nell\'impronta: la cronaca si rifa\' davvero, e va detto');
    } else {
      assert.doesNotMatch(corpo.textContent, frase,
        '`' + campo + '` NON entra nell\'impronta: promettere che la cronaca si rifa\' e\' falso');
    }
  }
});

test('seam _rendiSapere: «Torna al seme» avvisa del costo della cronaca per TUTTI e SOLI i campi dell\'impronta', () => {
  /* Stessa correzione della prova qui sopra, e per la stessa ragione: le due
     frasi escono dalla STESSA funzione (`rifaLaCronaca`), quindi una mutazione
     su quella deve arrossire tutt'e due. Mutazione ESEGUITA: la stessa
     (`campo !== 'da_sapere_subito'`) -- rossa su `notevole`; ripristinata con
     l'editor. */
  const impronta = campiDellImpronta();
  const costo = /rifà la cronaca degli ultimi/;
  for (const campo of campiDichiarati()) {
    const { corpo } = rendiSapere(sapereFinto({
      giudizi: [giudizio({
        da: 'proprietario', campo, soggetto: 'light.a', soggetto_genere: 'entita',
        valore: VALORE_PER_CAMPO[campo] || 'x',
      })],
    }));
    assert.match(corpo.textContent, /il sapere riprende il valore del seme/,
      'il resto dell\'avviso c\'e\' sempre: tornare al seme cancella comunque la correzione ('
      + campo + ')');
    if (impronta.has(campo)) {
      assert.match(corpo.textContent, costo, '`' + campo + '` fa rifare i giorni: va avvisato');
    } else {
      assert.doesNotMatch(corpo.textContent, costo,
        '`' + campo + '` non fa rifare nessun giorno: annunciare due ore di lavoro e\' falso');
    }
  }
});

test('seam _rendiSapere: in «Le tue correzioni» ogni riga dice QUALE campo è', () => {
  /* Senza, due righe dello stesso soggetto sono indistinguibili: «lock · no ·
     Corretto da te» vale identica per `notevole` e per `da_sapere_subito`.
     Mutazione che la uccide: togliere il campo dalla riga. */
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [
      giudizio({ da: 'proprietario', campo: 'notevole', soggetto: 'lock', soggetto_genere: 'tipo', valore: 'no' }),
      giudizio({ da: 'proprietario', campo: 'da_sapere_subito', soggetto: 'lock', soggetto_genere: 'tipo', valore: 'no' }),
    ],
  }));
  const campi = Array.from(corpo.querySelectorAll('.jr-row .jr-field')).map((n) => n.textContent);
  assert.deepEqual(campi.slice().sort(), ['Da sapere subito', 'Notevole'],
    'le due righe dello stesso soggetto si distinguono per campo');
});

/* I due elenchi dei campi che rifanno la cronaca, Python e JavaScript, legati
   da una prova sola -- stesso pattern di `JUDGMENT_FIELD_GROUPS` qui sopra.
   Senza, il giorno che un campo entra (o esce) da `CHRONICLE_FIELDS` la pagina
   continuerebbe a promettere -- o a tacere -- la cosa sbagliata, e nessuno se
   ne accorgerebbe. */
test('i campi che rifanno la cronaca: gli stessi in type_judgments.py (CHRONICLE_FIELDS) e in watcher-route.js (CHRONICLE_JUDGMENT_FIELDS)', () => {
  const mappa = costantiCampoPython(TYPE_JUDGMENTS_PY);
  const blocco = TYPE_JUDGMENTS_PY.match(/^CHRONICLE_FIELDS = \(([^)]*)\)$/m);
  assert.ok(blocco, 'CHRONICLE_FIELDS non trovata in type_judgments.py');
  const python = new Set(blocco[1].split(',').map((s) => s.trim()).filter(Boolean).map((nome) => {
    assert.ok(mappa[nome], 'costante non risolta: ' + nome);
    return mappa[nome];
  }));

  const m = SORGENTE.match(/var CHRONICLE_JUDGMENT_FIELDS = \{([^}]*)\};/);
  assert.ok(m, 'CHRONICLE_JUDGMENT_FIELDS non trovata in watcher-route.js');
  const js = new Set(Array.from(m[1].matchAll(/([a-z_]+):\s*true/g)).map((mm) => mm[1]));

  assert.deepEqual(js, python,
    'CHRONICLE_JUDGMENT_FIELDS (JavaScript) deve elencare esattamente i campi di CHRONICLE_FIELDS '
    + '(Python): sono i soli per cui «la cronaca dei giorni passati si rifà da sola» è vero');
});

/* La TERZA forma del valore di `da_sapere_subito` (decisione del proprietario,
   18/09/2026): `si`, `no`, oppure l'elenco JSON degli stati che contano --
   `lock` porta `["jammed"]`. Reso in pagina come «solo: jammed», con lo stato
   CITATO e non tradotto: finche' non esiste la fetta che rende gli stati nella
   lingua della casa, «inceppata» sarebbe una traduzione decisa qui, in un file
   di resa, cioe' esattamente dove non si decide il vocabolario. */

test('seam _rendiSapere: un `da_sapere_subito` a ELENCO si legge «solo: jammed», non come JSON grezzo', () => {
  /* Mutazione ESEGUITA: tolto il ramo dell'elenco da `judgmentValueNode` --
     rossa (il valore resta il testo `["jammed"]`); ripristinata con l'editor. */
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [giudizio({
      campo: 'da_sapere_subito', da: 'seme', soggetto_genere: 'tipo', soggetto: 'lock',
      valore: '["jammed"]',
    })],
  }));
  const riga = Array.from(corpo.querySelectorAll('.jr-row')).find((r) => {
    const s = r.querySelector('.jr-subject');
    return s && s.textContent === 'lock';
  });
  assert.ok(riga, 'la riga di `lock` esiste');
  assert.match(riga.textContent, /solo: jammed/);
  assert.doesNotMatch(riga.textContent, /\[/, 'niente JSON grezzo in pagina');
  // Lo stato si CITA: sta in un nodo monospazio, come gli altri valori tecnici.
  assert.ok(riga.querySelector('.jr-value-states'),
    'gli stati stanno in un nodo loro, citati e non tradotti');
});

test('seam _rendiSapere: un elenco di PIÙ stati li separa con la virgola', () => {
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [giudizio({
      campo: 'da_sapere_subito', da: 'seme', soggetto_genere: 'tipo', soggetto: 'vacuum',
      valore: '["error", "stuck"]',
    })],
  }));
  assert.match(corpo.textContent, /solo: error, stuck/);
});

test('seam _rendiSapere: `si` e `no` restano quello che sono', () => {
  /* Il ramo nuovo non deve mangiarsi le altre due forme del valore.

     **Si guarda il NODO DEL VALORE, non tutto il corpo.** La prima stesura
     faceva `assert.match(corpo.textContent, /si/)`, che combacia con «**si**ren»
     -- cioe' col nome del soggetto della riga stessa: la mutazione che svuota
     il valore di `da_sapere_subito` non la arrossiva. Era una prova che non
     poteva fallire.

     Mutazione ESEGUITA: `judgmentValueNode` che torna un valore vuoto per
     `da_sapere_subito` -- rossa qui (`'' != 'si'`); ripristinata con l'editor. */
  const { corpo } = rendiSapere(sapereFinto({
    giudizi: [
      giudizio({
        campo: 'da_sapere_subito', da: 'seme', soggetto_genere: 'tipo', soggetto: 'siren',
        valore: 'si',
      }),
      giudizio({
        campo: 'da_sapere_subito', da: 'seme', soggetto_genere: 'tipo', soggetto: 'update',
        valore: 'no',
      }),
    ],
  }));
  assert.doesNotMatch(corpo.textContent, /solo:/, 'niente «solo:» dove il valore non e\' un elenco');
  const valori = {};
  for (const riga of corpo.querySelectorAll('.jr-row')) {
    valori[riga.querySelector('.jr-subject').textContent] =
      riga.querySelector('.jr-value').textContent;
  }
  assert.deepEqual(valori, { siren: 'si', update: 'no' });
});


/* -------------------------------------------------------------------------
   L'IMPALCATURA (20/09/2026): il giudizio che dice «questa integrazione e'
   Home Assistant che parla di se'». E' l'unico giudizio il cui soggetto non
   e' una cosa di casa, e l'unico che il proprietario corregge per zittire il
   primo piano invece che per correggere un tipo.
   ------------------------------------------------------------------------- */

test('seam _rendiSapere: una riga di IMPALCATURA si corregge, con si/no', () => {
  /* Il proprietario ha deciso il 20/09 che hacs non si monitora, e la stessa
     decisione deve poter tornare indietro senza un rilascio: e' tutta la
     ragione per cui il criterio vive nel sapere.

     Mutazione che la uccide: lasciare `genere` come unico campo correggibile. */
  const g = giudizio({ campo: 'impalcatura', valore: 'si', da: 'seme',
    soggetto_genere: 'integrazione', soggetto: 'hacs' });
  const { document, corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const riga = trovaRigaGiudizio(corpo, g.soggetto);

  const correggi = bottone(document, 'Correggi', riga);
  assert.ok(correggi, 'senza questo bottone la decisione sarebbe cablata nel seme');
  correggi.click();
  const opzioni = [...riga.querySelectorAll('option')].map((o) => o.value);
  assert.deepEqual(opzioni, ['si', 'no'], 'un giudizio si/no non ha altre forme');
});

test("seam _rendiSapere: correggere l'impalcatura NON avvisa del costo della cronaca", () => {
  /* `impalcatura` non sta nell'impronta: si legge quando la pagina legge, e
     cambiarla non fa rifare nessun giorno. Dirlo lo stesso sarebbe un avviso
     falso -- e il proprietario imparerebbe a ignorarli.

     Mutazione che la uccide: la frase del costo su ogni campo. */
  const g = giudizio({ campo: 'impalcatura', valore: 'si', da: 'seme',
    soggetto_genere: 'integrazione', soggetto: 'hassio' });
  const { document, corpo } = rendiSapere(sapereFinto({ giudizi: [g] }));
  const riga = trovaRigaGiudizio(corpo, g.soggetto);
  bottone(document, 'Correggi', riga).click();

  assert.doesNotMatch(riga.textContent, /cronaca dei giorni/i);
});
