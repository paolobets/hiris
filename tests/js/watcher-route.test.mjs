import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { JSDOM } from 'jsdom';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Il GUSCIO della pagina «L'osservatore» (config/watcher-route.js): le quattro
   schede, il carico pigro, gli indirizzi, la freschezza.

   Fino al 18/09/2026 questo file portava tutte le prove della pagina, perche'
   la pagina era un file solo da 2.243 righe. Col taglio della spec
   `docs/design/2026-09-18-la-pagina-dell-osservatore.md` la resa di ogni
   scheda e' andata nel file della sua scheda (`watcher-giorno.test.mjs`,
   `watcher-cosa-fare.test.mjs`, `watcher-sapere.test.mjs`,
   `watcher-lavoro.test.mjs`) e qui resta cio' che e' del guscio: la cornice,
   i cancelli che scandiscono TUTTA la cartella `config/` (il refuso, nessun
   `innerHTML`), il campo data dentro il tema, e le rotte contro il README. */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'config');

/* I SEI file della pagina, letti insieme: i due cancelli di pulizia qui sotto
   («niente `innerHTML`», «nessun tono morto») valevano su un file solo perche'
   la pagina era un file solo. Dopo il taglio, guardarne uno sarebbe guardare
   un sesto del codice e chiamarlo cancello. */
const SEI_FILE = ['watcher-shared.js', 'watcher-giorno.js', 'watcher-cosa-fare.js',
  'watcher-sapere.js', 'watcher-lavoro.js', 'watcher-route.js'];
const SORGENTI = SEI_FILE.map((f) => [f, readFileSync(join(CONFIG_DIR, f), 'utf8')]);
const SORGENTE = SORGENTI.map(([, t]) => t).join('\n');

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

/* Il finto server del guscio: risponde a TUTTE e quattro le rotte delle
   schede, perche' qui si monta la cornice e non una scheda sola. `monta()`
   conta le chiamate: e' con quel conto che si misura il carico pigro. */
function monta(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url) => {
    chiamate.push(String(url));
    return jsonResponse(opts.corpo || {});
  };
  return Object.assign(ctx, { chiamate });
}

// Le date locali («oggi», «ieri», calcolate come le calcola la pagina) sono
// uscite con le prove del resoconto: vivono in `watcher-giorno.test.mjs`, che
// e' l'unica scheda che guarda un giorno.
const TRONCAMENTI_LEGITTIMI = new Set(['po', 'mo', 'be', 'da', 'di', 'fa', 'sta', 'va']);
const REFUSO_ACCENTO = /([A-Za-zÀ-ÿ]*[aeiouAEIOU])’(?=[\s.,;:)\]!?»"]|$)/g;

function trovaRefusiApostrofo(testo) {
  const trovati = [];
  for (const m of testo.matchAll(REFUSO_ACCENTO)) {
    if (TRONCAMENTI_LEGITTIMI.has(m[1].toLowerCase())) continue;
    trovati.push(m.index);
  }
  return trovati;
}

test('nessun modulo di config/ contiene il refuso "e’ "/"E’ " al posto di "è "/"È " (rilievo 2)', () => {
  // Guardia a livello di prodotto, non solo di questa pagina: scansiona TUTTI
  // i moduli di config/, cosi' il refuso non puo' tornare silenzioso da
  // nessun'altra parte della SPA di configurazione -- il brief lo chiede
  // esplicitamente ("e' un refuso che tornera'").
  const file = readdirSync(CONFIG_DIR).filter((f) => f.endsWith('.js'));
  assert.ok(file.length > 5, 'la cartella config/ deve contenere piu\' di 5 script (verifica del percorso)');
  const trovati = [];
  for (const f of file) {
    const testo = readFileSync(join(CONFIG_DIR, f), 'utf8');
    for (const start of trovaRefusiApostrofo(testo)) {
      const riga = testo.slice(0, start).split('\n').length;
      trovati.push(f + ':' + riga);
    }
  }
  assert.deepEqual(trovati, [], 'refuso "e’ "/"E’ " (invece di "è "/"È ") trovato in: ' + trovati.join(', '));
});

test('rilievo 3: la guardia del refuso cattura "perche’ " e "cioe’ ", non solo le forme isolate', () => {
  // Provato iniettando entrambe le varianti (nella stringa del test, non in
  // un file vero): con la vecchia esclusione "preceduto da una lettera"
  // questo assert falliva (0 trovati, non 1) per entrambe.
  assert.equal(trovaRefusiApostrofo('lo dico perche’ serve davvero').length, 1,
    '"perche’ " deve essere rilevato');
  assert.equal(trovaRefusiApostrofo('cioe’ questo è il punto').length, 1,
    '"cioe’ " deve essere rilevato');
});

test('rilievo 3: la guardia del refuso cattura anche la maiuscola "E’ "', () => {
  assert.equal(trovaRefusiApostrofo('E’ vero, non funzionava.').length, 1);
});

test('la guardia cattura la CLASSE del refuso, non solo "e’": «sara’», «perche’», «piu’»', () => {
  // Il caso vero, pagato il 14/09/2026: «il grezzo di quel giorno sara’
  // scaduto» nel cappello della sezione 03. La vecchia guardia cercava
  // `[eE]’ ` e non poteva vederlo.
  // Mutazione che la uccide: rimettere la vecchia espressione.
  assert.equal(trovaRefusiApostrofo('il grezzo sara’ scaduto').length, 1, '«sara’»');
  assert.equal(trovaRefusiApostrofo('piu’ tardi').length, 1, '«piu’»');
  assert.equal(trovaRefusiApostrofo('a fine riga: cosi’').length, 1, 'anche a fine stringa');
  assert.equal(trovaRefusiApostrofo('la citta’, e poi').length, 1, 'anche prima di una virgola');
});

test("la guardia NON grida sull’elisione vera né sui troncamenti dell’italiano", () => {
  // Se gridasse su `l’indice` il cancello diventerebbe rumore, e un cancello
  // che grida sempre si spegne. Mutazione che la uccide: togliere il
  // lookahead, o svuotare TRONCAMENTI_LEGITTIMI.
  assert.deepEqual(trovaRefusiApostrofo('l’indice di un’integrazione'), []);
  assert.deepEqual(trovaRefusiApostrofo('ci vuole un po’ di tempo'), []);
  assert.deepEqual(trovaRefusiApostrofo('a mo’ di esempio, va’ avanti'), []);
});

test('mount: "Non sto guardando ancora niente" usa è, non e’', async () => {
  // La frase vive nella scheda «L'osservatore», e dal 18/09/2026 una scheda si
  // legge solo se la si apre: il nome non e' un ornamento, senza quello questa
  // prova guarderebbe un pannello mai caricato.
  const { window, document } = monta();
  window.HirisWatcherRoute.mount('lavoro');
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /HIRIS è appena partito/);
  assert.match(testo, /è normale/);
});

test('mount: il sottotitolo dice i TRE attori, e non rimanda l’analista a domani', async () => {
  const { window, document } = monta();
  window.HirisWatcherRoute.mount('giorno');
  await tick(20);

  const sottotitolo = document.querySelector('.page-subtitle').textContent;
  assert.equal(trovaRefusiApostrofo(sottotitolo).length, 0,
    'nessun accento scritto con l’apostrofo');
  assert.match(sottotitolo, /cosa si potrebbe fare/,
    'il terzo attore c’è: la pagina non lo rimanda più a domani');
  assert.doesNotMatch(sottotitolo, /domani/,
    'l’analista ha gia’ parlato: prometterlo per domani sarebbe falso');
});

// ---------------------------------------------------------------------------
// Il campo Giorno: dentro il tema, con l'etichetta associata (rilievo 3)
// ---------------------------------------------------------------------------

test('mount: il campo Giorno entra nei selettori del tema (input[type=date] condiviso)', () => {
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');
  const blocchi = Array.from(css.matchAll(/input\[type=text\][^\n]*\{/g)).map((m) => m[0]);
  assert.equal(blocchi.length, 2,
    'attesi i due blocchi di stile condiviso per gli input (legacy + v5 moderno)');
  for (const blocco of blocchi) {
    assert.match(blocco, /input\[type=date\]/,
      'il selettore condiviso deve includere anche il campo Giorno: ' + blocco);
  }
});

test('mount: l\'etichetta «Giorno» è associata al campo data (for/id)', async () => {
  const { window, document } = monta();
  window.HirisWatcherRoute.mount('giorno');
  await tick(20);

  const input = document.querySelector('input[type=date]');
  assert.ok(input, 'deve esserci un campo data');
  assert.ok(input.id, 'il campo data deve avere un id per essere raggiungibile da un\'etichetta');
  const label = Array.from(document.querySelectorAll('label')).find((l) => l.textContent === 'Giorno');
  assert.ok(label, 'deve esserci un\'etichetta «Giorno»');
  assert.equal(label.getAttribute('for'), input.id,
    'l\'etichetta deve puntare al campo con for/id, altrimenti per un lettore di schermo è anonimo');
});

test('mount: il campo Giorno entra ANCHE nel terzo blocco di stile (hiris-config-override.css, rilievo 4)', () => {
  // hiris-config.css porta due blocchi condiviso legacy+v5 (verificati sopra),
  // ma esiste un TERZO blocco -- con `!important`, quindi vince sempre --
  // in hiris-config-override.css: senza `input[type=date]` anche lì, il tema
  // scuro è a posto ma il campo Giorno resta con misure/spaziature diverse
  // da ogni altro campo del prodotto. Verificato col grep che non ce n'è un
  // quarto (`hiris-theme.css`/`hiris-chat.css` non definiscono liste di
  // `input[type=...]`): sono tre in tutto `static/`.
  const overrideCss = readFileSync(join(CONFIG_DIR, '..', 'hiris-config-override.css'), 'utf8');
  const blocco = overrideCss.match(/input\[type=text\][^\n]*\{/);
  assert.ok(blocco, 'il blocco condiviso di stile degli input in hiris-config-override.css non è più nella forma attesa');
  assert.match(blocco[0], /input\[type=date\]/,
    'il selettore condiviso in hiris-config-override.css deve includere anche il campo Giorno: ' + blocco[0]);
});

// ---------------------------------------------------------------------------
// Lo span dentro una riga flex si restringe davvero (rilievo 1 del brief
// «css-morto»): il selettore che azzera `min-width` deve corrispondere a uno
// span costruito ESATTAMENTE come lo costruisce la SPA, cioè figlio di un
// elemento il cui stile nasce da `style.cssText = 'display:flex;...'`, SENZA
// spazio dopo i due punti (letterale nel sorgente, vedi rigaOggetto() sotto).
// Il browser però RISERIALIZZA l'attributo `style` quando lo si legge,
// aggiungendo lo spazio ("display: flex;") — verificato qui con lo stesso
// comportamento di jsdom (nwsapi) e dal vivo in Chromium. Il selettore va
// estratto dal file vero, non riscritto qui: così la mutazione richiesta dal
// brief (rimettere `.section-card [style*="display:flex"] > span`, la forma
// morta) arrossisce questo test senza dover toccare altro.
// ---------------------------------------------------------------------------

test('CSS: il selettore che azzera min-width sugli span corrisponde a uno span costruito come lo costruisce la SPA (rilievo 1)', () => {
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');
  const ancora = css.indexOf('Terza recidiva');
  assert.ok(ancora > -1,
    'il commento «Terza recidiva» (che documenta il difetto) non è più nel CSS: aggiorna l\'ancora di questo test');
  const dopo = css.slice(ancora);
  const regola = dopo.match(/\*\/\s*\n([^\n{]+)\{\s*\n\s*min-width:\s*0;/);
  assert.ok(regola, 'nessuna regola `min-width: 0` subito dopo il commento «Terza recidiva»');
  const selettore = regola[1].trim();

  // Stessa struttura di rigaOggetto() in watcher-route.js: uno span
  // figlio diretto di una riga il cui style nasce da `style.cssText =
  // 'display:flex;...'`, dentro una `.section-card`.
  const dom = new JSDOM('<!doctype html><body><section class="section-card"><div class="sc-body"></div></section></body>');
  const { document } = dom.window;
  const corpo = document.querySelector('.sc-body');
  const testa = document.createElement('div');
  testa.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
  const span = document.createElement('span');
  span.className = 'text-mono field-hint';
  testa.appendChild(span);
  corpo.appendChild(testa);

  assert.equal(testa.getAttribute('style'), 'display: flex; align-items: center; gap: 8px; flex-wrap: wrap;',
    'il browser riserializza l\'attributo style CON lo spazio dopo i due punti (precondizione del difetto)');
  assert.ok(span.matches(selettore),
    'il selettore «' + selettore + '» estratto da hiris-config.css non corrisponde a uno span costruito come lo costruisce la SPA');
});

// ---------------------------------------------------------------------------
// Pulizia: nessun `TONE_UNKNOWN` morto, nessun innerHTML (rilievo 8d + disciplina generale)
// ---------------------------------------------------------------------------

test('il sorgente non definisce TONO_IGNOTO se non lo usa (o si usa, o si toglie)', () => {
  const usiTonoIgnoto = (SORGENTE.match(/TONO_IGNOTO/g) || []).length;
  assert.ok(usiTonoIgnoto === 0 || usiTonoIgnoto >= 2,
    'TONO_IGNOTO non può essere definito e mai usato: o compare almeno una volta oltre alla definizione, o non c\'è più');
});

test('il sorgente non scrive mai innerHTML su dati del server', () => {
  // Cerca l'USO (`qualcosa.innerHTML =`), non la parola nel commento di
  // sicurezza in cima al file, che la nomina apposta per vietarla.
  assert.ok(!/\.innerHTML/.test(SORGENTE), 'trovato un uso di .innerHTML nel sorgente');
});

// ---------------------------------------------------------------------------
// README: il numero di rotte dichiarato combacia con quelle registrate in
// main.js (rilievo 10) — misurato, non ricopiato
// ---------------------------------------------------------------------------

test('README: il numero di rotte "live" dichiarato è quello davvero registrato in main.js', () => {
  const README = readFileSync(join(CONFIG_DIR, '..', '..', '..', '..', 'README.md'), 'utf8');
  const MAIN_JS = readFileSync(join(CONFIG_DIR, 'main.js'), 'utf8');
  const registrate = (MAIN_JS.match(/HirisRouter\.register\(/g) || []).length;
  assert.ok(registrate > 0, 'nessuna rotta trovata in main.js: il percorso è cambiato?');

  const NUMERI = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 };
  const m = README.match(/with (\w+) live routes/);
  assert.ok(m, 'la frase "with N live routes" non è più nel README: aggiorna questo test insieme al testo');
  const dichiarate = NUMERI[m[1].toLowerCase()];
  assert.ok(dichiarate, 'numero non riconosciuto nel README: ' + m[1]);
  assert.equal(dichiarate, registrate,
    'il README dichiara ' + m[1] + ' rotte live, ma main.js ne registra ' + registrate + ' (contate, non copiate)');
});

// ---------------------------------------------------------------------------
// Cancello del collaudo A3 (07/09/2026, BACKLOG.md «Il README documenta sei
// rotte che non esistono»): il numero di rotte combaciava anche col difetto
// -- sei erano il NOME sbagliato (`#/albero` invece di `#/tree`, e simili),
// e il test sopra (che conta soltanto) non poteva vederlo. Questo confronta
// l'IDENTITA' di ogni rotta, non solo la conta.
// ---------------------------------------------------------------------------

test('README: ogni rotta della tabella "Interface" è una di quelle davvero registrate in main.js, e viceversa', () => {
  const README = readFileSync(join(CONFIG_DIR, '..', '..', '..', '..', 'README.md'), 'utf8');
  const MAIN_JS = readFileSync(join(CONFIG_DIR, 'main.js'), 'utf8');

  // Ogni riga della tabella comincia con `| \`#/xxx\` |` -- l'ancora `^` in
  // modalità multilinea la distingue da una MENZIONE di un'altra rotta
  // dentro la colonna descrizione (es. "chosen per provider in `#/models`",
  // dentro la riga di `#/settings`), che non comincia mai la riga.
  const dalReadme = new Set();
  const reReadme = /^\| `#\/(\w*)` \|/gm;
  let m;
  while ((m = reReadme.exec(README))) dalReadme.add(m[1]);
  assert.ok(dalReadme.size > 0, 'nessuna riga di rotta trovata nella tabella "Interface" del README: il formato è cambiato?');

  // Stessa forma letterale del test sopra: `HirisRouter.register(/^#\/xxx\/?$/`
  // per una rotta con nome, `HirisRouter.register(/^#\/?$/` per la radice
  // (senza segmento -- gruppo di cattura opzionale).
  //
  // **Il difetto era di questa prova** (18/09/2026): dal taglio della pagina
  // dell'osservatore una rotta puo' portare un SOTTOSEGMENTO facoltativo --
  // `/^#\/watcher(?:\/(giorno|cosa-fare|sapere|lavoro))?\/?$/` -- e
  // l'estrazione di prima, che pretendeva `\/?$` subito dopo il nome, non
  // riconosceva piu' `watcher`: la prova gridava «il README documenta una
  // rotta che main.js non registra» mentre main.js la registrava eccome.
  // La coda `\/?$/` resta obbligatoria (una rotta senza ancoraggio finale
  // resta invisibile, ed e' giusto): in mezzo si ammette UN gruppo non
  // catturante facoltativo, che e' la forma delle schede.
  const daMainJs = new Set();
  const reMainJs = /HirisRouter\.register\(\/\^#(?:\\\/([\w-]+))?(?:\(\?:.*?\)\?)?\\\/\?\$\//g;
  while ((m = reMainJs.exec(MAIN_JS))) daMainJs.add(m[1] || '');
  assert.ok(daMainJs.size > 0, 'nessuna rotta riconosciuta in main.js: la forma della regex è cambiata?');

  const soloNelReadme = [...dalReadme].filter((r) => !daMainJs.has(r));
  const soloInMainJs = [...daMainJs].filter((r) => !dalReadme.has(r));
  assert.deepEqual(soloNelReadme, [],
    'il README documenta ' + JSON.stringify(soloNelReadme) + ', rotte che main.js non registra');
  assert.deepEqual(soloInMainJs, [],
    'main.js registra ' + JSON.stringify(soloInMainJs) + ', rotte che il README non documenta');
});

// ---------------------------------------------------------------------------
// La cornice: quattro schede, carico pigro, stato che sopravvive, indirizzi
// (spec 2026-09-18 §2). Ogni prova qui sotto e' nata ROSSA prima che il
// guscio esistesse, e porta la mutazione che la ucciderebbe.
// ---------------------------------------------------------------------------

test('la cornice: quattro schede con la semantica tablist, e nessun contatore nelle etichette', async () => {
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  const tablist = ctx.document.querySelector('[role="tablist"]');
  assert.ok(tablist, 'manca il tablist');
  const tab = Array.from(ctx.document.querySelectorAll('[role="tab"]'));
  assert.deepEqual(tab.map((t) => t.textContent),
    ['Il giorno', 'Cosa fare', 'Cosa ho capito', 'L’osservatore']);
  /* **Etichette nude** (spec §2): un contatore obbligherebbe a caricare tutte
     e quattro le schede all'avvio, contro la decisione 7. La prova e' che
     nessuna etichetta contenga una cifra. */
  for (const t of tab) assert.ok(!/\d/.test(t.textContent), 'contatore nell’etichetta: ' + t.textContent);
  for (const t of tab) {
    const pannello = ctx.document.getElementById(t.getAttribute('aria-controls'));
    assert.ok(pannello, 'la scheda «' + t.textContent + '» non controlla nessun pannello');
    assert.equal(pannello.getAttribute('role'), 'tabpanel');
    assert.equal(pannello.getAttribute('aria-labelledby'), t.id);
  }
});

test('la cornice: le frecce destra/sinistra passano da una scheda all’altra, e il focus le segue', async () => {
  // Spec §2: «frecce destra-sinistra fra le schede». E' cio' che distingue un
  // `tablist` da quattro bottoni in fila: un solo bersaglio nella sequenza di
  // tabulazione, gli altri si raggiungono con le frecce.
  // Mutazione che la uccide: togliere `tablist.addEventListener('keydown', frecce)`.
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  const tab = Array.from(ctx.document.querySelectorAll('[role="tab"]'));
  assert.equal(tab[0].tabIndex, 0, 'la scheda attiva e’ l’unica nella sequenza di tabulazione');
  assert.equal(tab[1].tabIndex, -1, 'le altre si raggiungono con le frecce, non col tabulatore');
  tab[0].dispatchEvent(new ctx.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(ctx.window.location.hash, '#/watcher/cosa-fare',
    'la freccia destra non ha portato alla scheda successiva');
  assert.equal(ctx.document.activeElement, tab[1],
    'il focus resta sulla scheda di prima: chi naviga da tastiera perde il posto');
  /* Nel prodotto il `hashchange` rimonta la scheda nuova; qui lo si fa a mano,
     perche' la finta non fa girare il router. Senza, «quale scheda e' attiva»
     resterebbe la prima e la freccia sinistra girerebbe sull'ultima -- che e'
     il comportamento giusto per lo stato che avrebbe davanti, non un difetto. */
  ctx.window.HirisWatcherRoute.mount('cosa-fare');
  tab[1].dispatchEvent(new ctx.window.KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
  assert.equal(ctx.window.location.hash, '#/watcher/giorno', 'la freccia sinistra non torna indietro');
});

test('CSS: il bersaglio di una scheda è alto almeno 44 px (la soglia del tocco, spec §2)', () => {
  // Il numero si legge dal foglio vero, non si ricopia qui: i `summary` di
  // questa pagina sono alti 21-23 px, ed e' la misura per cui la spec §6 vieta
  // di usarli per aprire un elenco.
  // Mutazione che la uccide: portare `min-height` di `.watcher-tab` a 32px.
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');
  const regola = css.match(/\.watcher-tab \{([^}]*)\}/);
  assert.ok(regola, 'manca la regola `.watcher-tab` in hiris-config.css');
  const alta = regola[1].match(/min-height:\s*(\d+)px/);
  assert.ok(alta, '`.watcher-tab` non dichiara min-height: il bersaglio sarebbe alto quanto il testo');
  assert.ok(Number(alta[1]) >= 44,
    'il bersaglio di una scheda deve essere almeno 44px, dichiara ' + alta[1] + 'px');
});

test('la cornice: aprire «Il giorno» NON scarica i dati dell’osservatore (spec §7, cancello 2)', async () => {
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  assert.deepEqual(ctx.chiamate.filter((u) => u.indexOf('api/mind/watching') === 0), [],
    'aprendo «Il giorno» la pagina ha chiesto gli 86 KB dell’osservatore');
  assert.deepEqual(ctx.chiamate.filter((u) => u.indexOf('api/mind/knowledge') === 0), []);
  assert.deepEqual(ctx.chiamate.filter((u) => u.indexOf('api/mind/analysis') === 0), []);
  assert.equal(ctx.chiamate.filter((u) => u.indexOf('api/mind/report') === 0).length, 1);
});

test('la cornice: la scheda si carica alla PRIMA apertura, e una seconda volta non richiede niente', async () => {
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  ctx.window.HirisWatcherRoute.mount('lavoro');
  await tick(0);
  const dopoLaPrima = ctx.chiamate.filter((u) => u.indexOf('api/mind/watching') === 0).length;
  assert.equal(dopoLaPrima, 1);
  ctx.window.HirisWatcherRoute.mount('giorno');
  ctx.window.HirisWatcherRoute.mount('lavoro');
  await tick(0);
  assert.equal(ctx.chiamate.filter((u) => u.indexOf('api/mind/watching') === 0).length, 1,
    'tornare su una scheda gia’ aperta l’ha ricaricata: lo stato non sopravvive');
});

test('la cornice: lo stato di una scheda sopravvive al cambio di scheda', async () => {
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  const pannello = ctx.document.getElementById('watcher-panel-giorno');
  const segno = ctx.document.createElement('div');
  segno.id = 'segno-di-prova';
  pannello.appendChild(segno);
  ctx.window.HirisWatcherRoute.mount('sapere');
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  assert.ok(ctx.document.getElementById('segno-di-prova'),
    'cambiare scheda ha ricostruito il pannello: elenchi aperti e posizione andrebbero persi');
});

/* Il pannello che si vede e quelli che non si vedono. La spec §2 lo dice in una
   riga -- «cambiare scheda toglie `hidden` a uno e lo dà agli altri» -- e senza
   questa prova la pagina torna una colonna sola: quattro schede disegnate una
   sotto l'altra, che è esattamente ciò da cui questa fetta nasce. */
test('la cornice: si vede SOLO il pannello della scheda scelta, gli altri tre sono nascosti', async () => {
  const ctx = monta();
  const visibili = () => ctx.window.HirisWatcherRoute._schede
    .map((def) => def.nome)
    .filter((nome) => !ctx.document.getElementById('watcher-panel-' + nome).hidden);
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  assert.deepEqual(visibili(), ['giorno'],
    'più di un pannello è in vista: le schede tornerebbero una colonna sola');
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(0);
  assert.deepEqual(visibili(), ['sapere'],
    'cambiare scheda non ha nascosto quella di prima');
});

/* **La premessa si asserisce**: finché nessun pannello è `hidden` -- e finché
   nessuno è mai stato aperto -- `[hidden] [aria-live]` è zero qualunque cosa
   faccia il codice, e la prova direbbe di sorvegliare una regola che non sta
   guardando. Qui si aprono tutte e quattro le schede, così i tre pannelli
   nascosti hanno DENTRO qualcosa, e solo allora si conta. */
test('la cornice: un pannello nascosto non porta aria-live (spec §2)', async () => {
  const ctx = monta();
  for (const def of ctx.window.HirisWatcherRoute._schede) {
    ctx.window.HirisWatcherRoute.mount(def.nome);
    await tick(0);
  }
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  const nascosti = [...ctx.document.querySelectorAll('.watcher-panel[hidden]')];
  assert.equal(nascosti.length, 3,
    'nessun pannello nascosto: senza la premessa questa prova non potrebbe fallire');
  for (const pannello of nascosti) {
    assert.ok(pannello.textContent.trim().length > 0,
      'il pannello nascosto è vuoto: la prova non guarda nessun contenuto');
  }
  assert.equal(ctx.document.querySelectorAll('.watcher-panel[hidden] [aria-live]').length, 0,
    'una riga in un pannello nascosto sarebbe letta per una scheda che nessuno guarda');
});

test('la cornice: «#/watcher» nudo si riscrive su «giorno» SENZA aggiungere una voce di cronologia', async () => {
  const ctx = monta();
  const chiamate = [];
  ctx.window.history.replaceState = (a, b, url) => chiamate.push(url);
  ctx.window.HirisWatcherRoute.mount(undefined);
  await tick(0);
  assert.deepEqual(chiamate, ['#/watcher/giorno']);
});

test('la cornice: un errore in una scheda resta dentro la sua scheda', async () => {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  ctx.window.fetch = async (url) => {
    if (String(url).indexOf('api/mind/report') === 0) return jsonResponse({ errore: 'x' }, 503);
    return jsonResponse({ conteggi: { righe: [] }, non_capito: [], giudizi: [], domande_aperte: [] });
  };
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  ctx.window.HirisWatcherRoute.mount('sapere');
  await tick(0);

  /* La frase e' quella del 503 (`renderReportError`), non quella generica:
     scritta com'era nel brief -- «Non è stato possibile leggere il resoconto»
     -- questa prova NON POTEVA fallire, perche' con un 503 la pagina scrive
     l'altra frase. E' il difetto n.1 di questo progetto, trovato eseguendo la
     mutazione: si asserisce il FATTO, non la proprieta'. */
  const giorno = ctx.document.getElementById('watcher-panel-giorno');
  assert.match(giorno.textContent, /L’archivio dei resoconti non è disponibile/,
    'precondizione: l’errore del resoconto c’è davvero, e sta nella scheda che l’ha chiesto');
  const sapere = ctx.document.getElementById('watcher-panel-sapere');
  assert.doesNotMatch(sapere.textContent, /L’archivio dei resoconti non è disponibile/,
    'l’errore del resoconto e’ colato dentro «Cosa ho capito»');
  /* L'altra meta' della promessa della spec §2 -- «se il resoconto non si
     legge, "Cosa ho capito" continua a funzionare» -- che senza questa riga
     sarebbe vera anche per un pannello vuoto. */
  /* Il segno che la scheda ha reso davvero: la riga di peso, che c'e'
     SEMPRE (spec §4C). Fino al 20/09 questa riga cercava «Cosa non ha
     capito», che ora tace quando non c'e' niente da capire -- e avrebbe
     fatto fallire la prova per il motivo sbagliato. */
  assert.match(sapere.textContent, /0 giudizi/,
    '«Cosa ho capito» non ha reso niente: l’errore dell’altra scheda se l’è portata via');
});

test('la cornice: a dati arrivati ogni pannello dice quando li ha letti, e offre Aggiorna', async () => {
  const ctx = monta();
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(0);
  const pannello = ctx.document.getElementById('watcher-panel-giorno');
  assert.match(pannello.textContent, /Letto alle \d\d:\d\d/);
  const aggiorna = Array.from(pannello.querySelectorAll('button'))
    .find((b) => b.textContent === 'Aggiorna');
  assert.ok(aggiorna, 'manca «Aggiorna»: senza, non c’e’ nessun modo di rileggere');
  const prima = ctx.chiamate.length;
  aggiorna.dispatchEvent(new ctx.window.Event('click'));
  await tick(0);
  assert.ok(ctx.chiamate.length > prima, '«Aggiorna» non ha riletto niente');
});
