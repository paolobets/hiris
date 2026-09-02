import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { JSDOM } from 'jsdom';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Giro di correzioni sulla pagina «L'osservatore» (config/watcher-route.js),
   guida-ux-osservatore in .superpowers/sdd/2026-08-26-l-osservatore/pagina-brief.md.

   E' anche il primo file di test di questa pagina: fino a qui `_rendiOsservate`
   e `_rendiOggetti` erano una seam PROMESSA da un commento ("seam di test: la
   resa va pinnata senza passare da fetch") e mai usata da nessun test -- oltre
   quattrocento righe di resa senza nessuna rete. Le sezioni "seam:" qui sotto
   chiudono quel buco usando esattamente quelle due funzioni. */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'config');
const SORGENTE = readFileSync(join(CONFIG_DIR, 'watcher-route.js'), 'utf8');

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/watcher-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* Il finto server: distingue le due rotte per prefisso, come fa la pagina
   vera (`api/mind/watching`, `api/mind/facts[?day=...]`). */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url) => {
    const u = String(url);
    chiamate.push(u);
    if (u.indexOf('api/mind/watching') === 0) {
      if (opts.osservateRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.watching !== undefined ? opts.watching : { watching: [] },
        opts.osservateStatus);
    }
    if (u.indexOf('api/mind/facts') === 0) {
      if (opts.oggettiRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.facts !== undefined ? opts.facts : { facts: [] },
        opts.oggettiStatus);
    }
    throw new Error('url inatteso: ' + u);
  };
  return Object.assign(ctx, { chiamate });
}

function bottone(document, testo, entro) {
  const scope = entro || document;
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent === testo);
}

// Rilievo 2 del brief «css-morto»: il messaggio "nessun episodio" (sezione
// 02, «Cosa è successo») va letto sul SUO nodo, non su tutto il contenitore
// -- la descrizione statica della sezione 02 contiene ANCH'ESSA "00:20"
// ("scritti alle 00:20, sul fuso della CASA"), quindi cercare `/00:20/` su
// tutto `#route-outlet` resta sempre soddisfatta, a prescindere dal testo
// del messaggio vero e proprio (mutazione provata: cambiando il messaggio in
// "prima o poi" i vecchi test restavano verdi). Il messaggio è l'unico
// `.sc-desc` dentro il `.sc-body` della seconda `.section-card`.
function testoMessaggioOggetti(document) {
  const card2 = document.querySelectorAll('.section-card')[1];
  const msg = card2 && card2.querySelector('.sc-body .sc-desc');
  assert.ok(msg, 'non trovo il nodo del messaggio dentro la sezione 02 (struttura pagina cambiata?)');
  return msg.textContent;
}

// -- date locali, calcolate come le calcola la pagina (fuso del browser di
//    chi fa girare il test), MAI hardcoded: una data fissa scritta nel test
//    diventerebbe falsa il giorno dopo. --
function pad2(n) { return n < 10 ? '0' + n : String(n); }
function isoLocale(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
function giornoFa(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoLocale(d);
}
function ggmmaaaa(iso) {
  const [y, m, g] = iso.split('-');
  return g + '/' + m + '/' + y;
}

const OGGI = giornoFa(0);
const IERI = giornoFa(1);
const VECCHIO = giornoFa(40); // sicuramente né oggi né ieri, qualunque sia la data di corsa

// ---------------------------------------------------------------------------
// Ortografia: «è» non «e’»/«E’» (rilievo 2, e rilievo 3 del brief «css-morto»)
// — sulle stringhe VISIBILI
// ---------------------------------------------------------------------------

// Rileva il refuso "e’ "/"E’ " al posto di "è "/"È ", ovunque compaia.
// Rilievo 3 del brief «css-morto»: la vecchia guardia escludeva i casi
// "preceduti da una lettera" per difendersi da una parola tipo "che’ " che
// NON esiste in italiano -- e con quella difesa saltava esattamente
// "perche’ " e "cioe’ ", che sono la forma in cui il refuso compare più
// spesso, e non copriva affatto la maiuscola "E’ ". Nessuna esclusione:
// verificato (grep) che oggi nessun modulo di config/ contiene "e’ "
// preceduto da una lettera, quindi togliere il filtro non introduce falsi
// positivi sul codice reale.
function trovaRefusiApostrofo(testo) {
  const trovati = [];
  for (const m of testo.matchAll(/[eE]’ /g)) trovati.push(m.index);
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

test('mount: "Non sto guardando ancora niente" usa è, non e’', async () => {
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /HIRIS è appena partito/);
  assert.match(testo, /è normale/);
});

test('mount: il sottotitolo usa è, non e’, e chiama il materiale "episodi"', async () => {
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const sottotitolo = document.querySelector('.page-subtitle').textContent;
  assert.match(sottotitolo, /è il materiale/);
  assert.match(sottotitolo, /ricava episodi/);
});

// ---------------------------------------------------------------------------
// Il badge di provenienza: «di serie», non «Pavimento — non si toglie»
// (rilievo 6b) — l'etichetta cambia, il valore interno no
// ---------------------------------------------------------------------------

test('seam _rendiOsservate: la voce "pavimento" porta il badge «Di serie», non «Pavimento»', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOsservate(corpo, [
    { soggetto: 'light.cucina', gamba: 'comfort', provenienza: 'pavimento' },
  ]);
  const badge = corpo.querySelector('.agent-badge');
  assert.equal(badge.textContent, 'Di serie');
  assert.doesNotMatch(corpo.textContent, /Pavimento/,
    'la parola "pavimento" non deve comparire nel testo utente (resta un valore interno)');
});

test('seam _rendiOsservate: una voce "obiettivo" resta distinguibile e dice che si può togliere', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOsservate(corpo, [
    { soggetto: 'light.cucina', gamba: 'comfort', provenienza: 'obiettivo' },
  ]);
  assert.match(corpo.textContent, /si può togliere/);
});

test('mount: la descrizione della sezione 01 spiega «di serie» invece di ripeterlo su ogni riga', async () => {
  const { window, document } = montaConServer({
    watching: { watching: [{ soggetto: 'light.cucina', gamba: 'comfort', provenienza: 'pavimento' }] },
  });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const desc = document.querySelector('.sc-desc').textContent;
  assert.match(desc, /di serie/);
  assert.match(desc, /non si tolgono/);
  assert.match(desc, /obiettivo/);
});

// ---------------------------------------------------------------------------
// Le gambe: etichette leggibili, non chiavi grezze (rilievo 8a)
// ---------------------------------------------------------------------------

test('seam _rendiOsservate: l\'intestazione di gamba mostra un\'etichetta leggibile, non la chiave grezza', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOsservate(corpo, [
    { soggetto: 'device_tracker.paolo', gamba: "chi c'e'", provenienza: 'pavimento' },
  ]);
  const sommario = corpo.querySelector('summary').textContent;
  assert.match(sommario, /Chi c’è/, 'la chiave grezza "chi c\'e\'" deve diventare l\'etichetta "Chi c’è"');
  assert.doesNotMatch(sommario, /chi c'e'/);
});

test('seam _rendiOsservate: una gamba sconosciuta finisce in coda col suo nome grezzo, e non sparisce', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOsservate(corpo, [
    { soggetto: 'sensor.nuovo', gamba: 'una gamba mai vista', provenienza: 'pavimento' },
    { soggetto: 'lock.porta', gamba: 'sicurezza', provenienza: 'pavimento' },
  ]);
  const sommari = Array.from(corpo.querySelectorAll('summary')).map((s) => s.textContent);
  assert.equal(sommari.length, 2);
  assert.match(sommari[0], /Sicurezza/, 'l\'ordine noto (pavimento.GAMBE) viene prima della coda');
  assert.match(sommari[1], /una gamba mai vista/, 'una gamba ignota non sparisce: va in coda col nome grezzo');
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
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
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
// «Riprova»: unica pagina di lettura che ne era priva (rilievo 4)
// ---------------------------------------------------------------------------

test('un errore nel leggere "cosa sto guardando" (503) offre Riprova, e il testo del messaggio non cambia', async () => {
  const { window, document } = montaConServer({ osservateStatus: 503, watching: {} });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è una lista vuota — è l’osservatore stesso ad essere fermo/,
    'il testo d\'errore a tre stati non si tocca (è dichiarato il migliore del pannello)');
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare, come nelle pagine sorelle');
});

test('un guasto di rete su "cosa sto guardando" offre Riprova, e il bottone rilancia la richiesta', async () => {
  const { window, document, chiamate } = montaConServer({ osservateRotto: true });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const primaDelClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  const retry = bottone(document, 'Riprova');
  assert.ok(retry, 'deve esserci un modo di riprovare');
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const dopoIlClick = chiamate.filter((u) => u.indexOf('watching') !== -1).length;
  assert.equal(dopoIlClick, primaDelClick + 1, 'il bottone deve rilanciare la stessa richiesta');
});

test('un errore nel leggere "cosa è successo" (503) offre Riprova', async () => {
  const { window, document } = montaConServer({ oggettiStatus: 503, facts: {} });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è una lista vuota — è l’archivio stesso ad essere fermo/);
  assert.ok(bottone(document, 'Riprova'), 'deve esserci un modo di riprovare anche per gli episodi');
});

test('un guasto di rete su "cosa è successo" offre Riprova, e il bottone rilancia la richiesta con lo stesso giorno', async () => {
  const { window, document, chiamate } = montaConServer({ oggettiRotto: true });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const chiamateOggettiPrima = chiamate.filter((u) => u.indexOf('facts') !== -1);
  const retry = bottone(document, 'Riprova');
  assert.ok(retry);
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const chiamateOggettiDopo = chiamate.filter((u) => u.indexOf('facts') !== -1);
  assert.equal(chiamateOggettiDopo.length, chiamateOggettiPrima.length + 1);
  assert.equal(chiamateOggettiDopo[chiamateOggettiDopo.length - 1], chiamateOggettiPrima[0],
    'il retry deve rilanciare la stessa richiesta (stesso giorno), non perdere il filtro');
});

// ---------------------------------------------------------------------------
// Il primo giorno: quando comparirà qualcosa (rilievo 5) — «episodi» (6a)
// ---------------------------------------------------------------------------

test('nessun episodio per IERI: dice quando tornare (00:20), niente data ISO, niente ipotesi debole', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisOsservatoreRoute.mount();
  await tick(20); // il campo nasce su "ieri" di default

  const messaggio = testoMessaggioOggetti(document);
  assert.match(messaggio, /episodio/, 'parola utente: episodio, non oggetto');
  assert.match(messaggio, /00:20/, 'deve dire quando tornare (nel messaggio, non altrove nella pagina)');
  assert.match(messaggio, new RegExp(ggmmaaaa(IERI).replace(/\//g, '\\/')), 'la data va in gg/mm/aaaa');
  assert.doesNotMatch(messaggio, /\d{4}-\d{2}-\d{2}/, 'nessuna data in formato ISO nel testo');
  assert.doesNotMatch(messaggio, /potrebbe non aver fatto niente di osservabile/,
    'il primo giorno non deve seminare il dubbio che la casa non abbia fatto niente: è quasi impossibile');
});

test('nessun episodio per OGGI: stesso trattamento del primo giorno (ieri/oggi sono lo stesso caso)', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const input = document.querySelector('input[type=date]');
  input.value = OGGI;
  input.dispatchEvent(new window.Event('change'));
  await tick(20);

  const messaggio = testoMessaggioOggetti(document);
  assert.match(messaggio, /00:20/, 'deve dire quando tornare (nel messaggio, non altrove nella pagina)');
  assert.doesNotMatch(messaggio, /potrebbe non aver fatto niente di osservabile/);
});

test('nessun episodio per un giorno VECCHIO: l\'ipotesi doppia resta, ma la data è in gg/mm/aaaa', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const input = document.querySelector('input[type=date]');
  input.value = VECCHIO;
  input.dispatchEvent(new window.Event('change'));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /potrebbe non aver fatto niente di osservabile/,
    'per un giorno vecchio l\'ipotesi doppia attuale va bene, il brief lo dice esplicitamente');
  assert.match(testo, new RegExp(ggmmaaaa(VECCHIO).replace(/\//g, '\\/')));
  assert.doesNotMatch(testo, /\d{4}-\d{2}-\d{2}/);
});

test('nessun episodio SENZA filtro (bottone "più recenti"): parla di episodi', async () => {
  const { window, document } = montaConServer({ facts: { facts: [] } });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const btnRecenti = bottone(document, 'Vedi i più recenti, senza filtro');
  btnRecenti.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /episodio/);
  assert.doesNotMatch(testo, /\boggetto\b/);
});

// ---------------------------------------------------------------------------
// Il fuso senza numero inventato (rilievo 12)
// ---------------------------------------------------------------------------

test('mount: la sezione 02 non dichiara una differenza di fuso in ore', async () => {
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const descrizioni = Array.from(document.querySelectorAll('.sc-desc')).map((p) => p.textContent);
  const desc02 = descrizioni.find((d) => /fuso della CASA/.test(d) || /fuso di/.test(d));
  assert.ok(desc02, 'deve esserci la descrizione della sezione 02');
  assert.doesNotMatch(desc02, /un'ora|un’ora/, 'la cifra "un\'ora" non è misurata: il caso reale (stesso fuso) ha errore zero');
});

// ---------------------------------------------------------------------------
// La gerarchia della riga: il fatto prima dell'identificatore (rilievo 7)
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: l\'identificatore è in monospazio attenuato, il contenuto è il testo prominente', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'climate.riscaldamento_camera',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { stato: 'acceso' },
  }], null);

  const identificatore = corpo.querySelector('.text-mono');
  assert.ok(identificatore, 'l\'identificatore deve portare la classe text-mono (rottura + tipografia attenuata)');
  assert.equal(identificatore.textContent, 'climate.riscaldamento_camera');
  assert.doesNotMatch(identificatore.className, /\bagent-badge\b/,
    'l\'identificatore non è il badge del genere: sono due elementi distinti nella stessa riga');

  // Il paragrafo col fatto (orario + stato) non deve più essere una nota a
  // margine (`field-hint`): deve leggersi come contenuto.
  const paragrafi = Array.from(corpo.querySelectorAll('p'));
  const rigaFatto = paragrafi.find((p) => /acceso/.test(p.textContent) && /→/.test(p.textContent));
  assert.ok(rigaFatto, 'deve esserci un paragrafo col periodo e lo stato');
  assert.doesNotMatch(rigaFatto.className, /\bfield-hint\b/,
    'il fatto non deve avere la classe attenuata riservata prima a lui: ora è il contenuto principale');
});

// ---------------------------------------------------------------------------
// Seam _rendiOggetti: i sei generi, i comprimari, le misure — senza rete
// (rilievo 9: la resa era priva di qualunque test)
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: un oggetto di energia mostra da/a e la differenza col segno', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_forno',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { valore_iniziale: 12.5, valore_finale: 15.0, differenza: 2.5 },
  }], null);
  assert.match(corpo.textContent, /da 12\.5 a 15/);
  assert.match(corpo.textContent, /\+2\.5/);
});

test('seam _rendiOggetti: un oggetto di energia con differenza non calcolabile lo dichiara, mai un NaN silenzioso', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.contatore',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 5, valore_finale: 'unavailable', differenza: null },
  }], null);
  assert.match(corpo.textContent, /non calcolabile/);
  assert.doesNotMatch(corpo.textContent, /NaN/);
});

test('seam _rendiOggetti: un episodio di energia con direzione DICHIARATA la mostra in italiano e distingue la provenienza', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_prodotta',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { valore_iniziale: 10, valore_finale: 25, differenza: 15,
            direzione: 'produzione', provenienza: 'dichiarata' },
  }], null);
  assert.match(corpo.textContent, /[Pp]roduzione/,
    'la direzione va mostrata in italiano leggibile, non il valore grezzo');
  assert.match(corpo.textContent, /[Dd]ichiarat/,
    'la provenienza "dichiarata" deve comparire nel testo');
});

test('seam _rendiOggetti: un episodio di energia con direzione DEDOTTA si distingue visibilmente dalla dichiarata', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const dichiarato = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(dichiarato, [{
    id: 1, genere: 'energia', protagonista: 'sensor.a',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1,
            direzione: 'prelievo', provenienza: 'dichiarata' },
  }], null);
  const dedotto = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(dedotto, [{
    id: 2, genere: 'energia', protagonista: 'sensor.b',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1,
            direzione: 'prelievo', provenienza: 'dedotta' },
  }], null);
  assert.match(dedotto.textContent, /[Dd]edott/);
  // Le due provenienze non devono rendersi con lo stesso badge: e' il
  // requisito del mandato, «distingue visibilmente le due provenienze».
  const badgeDichiarato = Array.from(dichiarato.querySelectorAll('.agent-badge')).pop();
  const badgeDedotto = Array.from(dedotto.querySelectorAll('.agent-badge')).pop();
  assert.ok(badgeDichiarato && badgeDedotto, 'entrambi gli episodi devono avere un badge di provenienza');
  assert.notEqual(badgeDichiarato.className, badgeDedotto.className,
    'la classe del badge deve differire fra dichiarata e dedotta');
});

test('seam _rendiOggetti: un episodio di energia SENZA direzione nota non mostra nessun badge di provenienza in piu', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'energia', protagonista: 'sensor.energia_ignota',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 1, valore_finale: 2, differenza: 1 },
  }], null);
  // Un solo badge: quello del genere ("Energia"). Nessun secondo badge di
  // provenienza quando il campo `direzione` non c'e' affatto -- il mandato
  // vieta esplicitamente una "sconosciuta" travestita da dato.
  assert.equal(corpo.querySelectorAll('.agent-badge').length, 1);
});

test('seam _rendiOggetti: un guasto ancora aperto lo dice esplicitamente', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'guasto', protagonista: 'problema:hue.bridge_offline',
    inizio_ts: 1, fine_ts: null,
    corpo: { stato: 'aperto' },
  }], null);
  assert.match(corpo.textContent, /ancora aperto/);
  assert.match(corpo.textContent, /in corso a fine giornata/,
    'un fine_ts nullo si dichiara come "in corso a fine giornata", non "ancora in corso" ' +
    '(cancello-rilascio-brief.md, punto 2): l\'aggregazione e\' per giornata, e non puo\' ' +
    'promettere una continuita\' che non tiene oltre la mezzanotte');
  assert.match(corpo.textContent, /Problema Home Assistant: hue\.bridge_offline/,
    'un protagonista "problema:" diventa un nome leggibile, come in tree-route.js');
});

test('seam _rendiOggetti: comprimari e misure stanno dietro un rivelatore sincrono, chiuso di default', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  document.body.appendChild(corpo);

  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'funzionamento', protagonista: 'light.lampadario',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: {
      stato: 'acceso',
      comprimari: ['light.lampadario_gruppo', 'switch.lampadario_interruttore'],
      misure: { 'sensor.temp_soggiorno': { da: 18.2, a: 21.0 } },
    },
  }], null);

  const btn = Array.from(corpo.querySelectorAll('button'))
    .find((b) => /c’era intorno/.test(b.textContent));
  assert.ok(btn, 'il rivelatore deve esserci quando ci sono comprimari o misure');
  const pannello = btn.nextElementSibling;
  assert.ok(pannello, 'deve esserci il pannello dei dettagli');
  assert.equal(pannello.hidden, true, 'il pannello nasce chiuso (`hidden`, non solo un CSS display)');

  btn.dispatchEvent(new window.Event('click', { bubbles: true }));

  assert.equal(pannello.hidden, false, 'il click deve aprire il pannello, e i dati sono già nel payload');
  assert.match(corpo.textContent, /light\.lampadario_gruppo/);
  assert.match(corpo.textContent, /switch\.lampadario_interruttore/);
  assert.match(corpo.textContent, /sensor\.temp_soggiorno.*da 18\.2 a 21/s);

  // rilievo 8c: «Nascondi» da solo perde il referente con più righe aperte.
  assert.notEqual(btn.textContent, 'Nascondi', 'il testo del rivelatore aperto deve avere un referente');
  assert.match(btn.textContent, /c’era intorno/);
});

test('seam _rendiOggetti: senza comprimari e senza misure non c\'è nessun rivelatore', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'presenza', protagonista: 'person.paolo',
    inizio_ts: 1, fine_ts: 2, corpo: { stato: 'a casa' },
  }], null);
  assert.equal(corpo.querySelectorAll('button').length, 0);
});

// ---------------------------------------------------------------------------
// Il bilancio dell'energia (mandato «il bilancio dell'energia», 27/08/2026):
// un oggetto al giorno per dispositivo, una QUANTITA' CON UNA FORMA, non un
// episodio. La forma reale del corpo è quella di `build_balance_body`
// (hiris/app/cervello/oggetti.py): {totali:{dimensione:{valore,provenienza}},
// forma:{dimensione:[{ora,valore}...]}, momenti:{...}}, più `dispositivo`/`entita`
// aggiunti da `aggregate_day`. Prima di questa fetta il genere "bilancio"
// cadeva nel ramo di default di `mainPhrase` e mostrava «(nessun
// dettaglio)» — questi test bloccano quella regressione E vietano lo stampo
// dell'episodio («da X a Y», la freccia di `period()`).
// ---------------------------------------------------------------------------

// `forma[dimensione]` porta l'ORA VERA di ogni punto dal 27/08/2026 (mandato
// «la pagina del bilancio -- le correzioni», punto 6): non piu' una lista
// posizionale nuda, ma `[{"ora","valore"}, ...]` -- vedi `costruisci_corpo_
// bilancio` in `hiris/app/cervello/oggetti.py`. Questo helper costruisce un
// ISO alla stessa ora LOCALE di questa macchina (stesso principio TZ-agnostico
// di `giornoFa` sopra): `new Date(iso).getHours()`, nel codice sotto test,
// torna esattamente `h`, qualunque sia il fuso di chi fa girare il test.
function oraIsoLocale(h, m) {
  var d = new Date();
  d.setHours(h, m || 0, 0, 0);
  return d.toISOString();
}

function puntoOra(h, valore) { return { ora: oraIsoLocale(h), valore: valore }; }

function bilancioFixture(extra) {
  return Object.assign({
    id: 1, genere: 'bilancio', protagonista: 'a1b2c3d4e5f6',
    inizio_ts: 1755990000, fine_ts: 1756076400,
    corpo: {
      totali: {
        produzione: { valore: 24.5, provenienza: null },
        autoconsumo: { valore: 14.2, provenienza: null },
        immissione: { valore: 10.3, provenienza: 'dichiarata' },
        prelievo: { valore: 3.1, provenienza: 'dedotta' },
      },
      forma: {
        produzione: [4, 5, 6, 7, 8, 9, 10, 11].map((h, i) =>
          puntoOra(h, [0, 0, 1.2, 2.3, 4.8, 3.1, 0.4, 0][i])),
        prelievo: [4, 5, 6, 7, 8, 9, 10, 11].map((h, i) =>
          puntoOra(h, [0.5, 0.4, 0.2, 0.1, 0, 0, 0.3, 0.6][i])),
      },
      momenti: {
        prima_ora_produzione: '2026-08-23T04:00:00+00:00',
        ultima_ora_produzione: '2026-08-23T18:00:00+00:00',
        picco_produzione: { valore: 4.8, ora: '2026-08-23T11:00:00+00:00' },
        quota_autoconsumo: 0.712,
      },
      dispositivo: 'Inverter con accumulo',
      entita: ['sensor.energia_prodotta_oggi', 'sensor.energia_immessa_oggi'],
    },
  }, extra || {});
}

test('seam _rendiOggetti: un bilancio mostra i totali in kWh, non «(nessun dettaglio)»', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /nessun dettaglio/);
  assert.match(corpo.textContent, /24,5\s*kWh/, 'il totale di produzione deve leggersi in kWh, virgola italiana');
  assert.match(corpo.textContent, /Inverter con accumulo/, 'il nome leggibile del dispositivo deve comparire');
  const badgeGenere = corpo.querySelector('.agent-badge');
  assert.equal(badgeGenere.textContent, 'Bilancio');
});

test('seam _rendiOggetti: un bilancio NON si legge come un episodio (niente "da X a Y", niente freccia di periodo)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /→/,
    'un bilancio è una quantità con una forma, non un "da → a": niente freccia di periodo()');
  assert.doesNotMatch(corpo.textContent, /\bda 24[,.]5\b/,
    'il totale non deve essere presentato come "da X a Y" (lo stampo dell\'episodio)');
});

test('seam _rendiOggetti: la provenienza di un totale riusa lo stesso badge dichiarata/dedotta degli episodi di energia', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.match(corpo.textContent, /[Dd]ichiarat/, 'la provenienza "dichiarata" (immissione) deve comparire');
  assert.match(corpo.textContent, /[Dd]edott/, 'la provenienza "dedotta" (prelievo) deve comparire');

  const badgeDichiarato = Array.from(corpo.querySelectorAll('.agent-badge'))
    .find((b) => /[Dd]ichiarat/.test(b.textContent));
  const badgeDedotto = Array.from(corpo.querySelectorAll('.agent-badge'))
    .find((b) => /[Dd]edott/.test(b.textContent));
  assert.ok(badgeDichiarato && badgeDedotto, 'entrambi i badge di provenienza devono esserci');
  assert.notEqual(badgeDichiarato.className, badgeDedotto.className,
    'le due provenienze devono distinguersi visibilmente, come per gli episodi di energia');
});

test('seam _rendiOggetti: un totale senza provenienza nota (produzione) non porta un badge di provenienza in più', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  // Un solo badge non porta ne' "dichiarat" ne' "dedott": e' il genere ("Bilancio").
  const badgeGenerici = Array.from(corpo.querySelectorAll('.agent-badge'))
    .filter((b) => !/[Dd]ichiarat|[Dd]edott/.test(b.textContent));
  assert.equal(badgeGenerici.length, 1, 'un solo badge senza provenienza: quello del genere');
});

test('seam _rendiOggetti: una dimensione assente (es. batteria) non compare come totale a zero', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  assert.doesNotMatch(corpo.textContent, /[Cc]arica della batteria/,
    'nessuna entità batteria in questa fixture: "carica" non deve comparire');
  assert.doesNotMatch(corpo.textContent, /[Ss]carica della batteria/);
  assert.doesNotMatch(corpo.textContent, /\b0\s*kWh\b/,
    'mai uno zero inventato per una dimensione senza dati (mandato, "cosa NON si salva")');
});

test('seam _rendiOggetti: la curva mostra produzione e prelievo sovrapposti, come barre SVG', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci un grafico SVG per la forma della giornata');
  const rects = svg.querySelectorAll('rect');
  assert.ok(rects.length > 0, 'il grafico deve avere almeno una barra');
  const riempimenti = new Set(Array.from(rects).map((r) => r.getAttribute('fill')));
  assert.ok(riempimenti.size >= 2, 'produzione e prelievo devono avere un colore diverso l\'una dall\'altra');
});

test('seam _rendiOggetti: senza `forma` non compare nessun grafico', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.forma;
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [fx], null);

  assert.equal(corpo.querySelectorAll('svg').length, 0,
    'senza la forma della giornata non c\'è niente da disegnare');
});

// ---------------------------------------------------------------------------
// Punto 1 (ALTO) del brief-correzioni, riaperto e reso PIÙ severo dal punto 6:
// «la pagina non deve mai affermare un'ora falsa». Prima della correzione del
// 27/08 (mandato punto 6) la forma era un segnaposto posizionale ("punto N"),
// e il vecchio test si limitava a VIETARE qualunque HH:MM nell'SVG. Ora che
// il Python porta l'ora vera per ogni punto (`forma[dimensione] = [{"ora",
// "valore"}, ...]`), vietare non basta più: il test deve PRETENDERE l'ora
// giusta, e arrossire se la resa tornasse a leggere la POSIZIONE nell'array
// al posto della chiave `ora` (la mutazione che il mandato chiede di
// eseguire, non dedurre).
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: la curva del bilancio porta l\'ORA VERA di ogni barra, non la posizione nell\'array', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      // Le due ore sono deliberatamente NON in posizione 0/1 e distanti fra
      // loro: una resa che leggesse la posizione nell'array (0, 1, ...)
      // invece della chiave `ora` produrrebbe un'etichetta diversa dalla
      // vera per ENTRAMBI i punti, e questo test la coglierebbe.
      forma: { produzione: [puntoOra(7, 1.2), puntoOra(13, 4.8)] },
    }),
  })], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci il grafico');
  const titoliBarre = Array.from(svg.querySelectorAll('rect > title')).map((t) => t.textContent);

  assert.ok(titoliBarre.some((t) => /\b07:00\b/.test(t)),
    'la barra da 1,2 kWh deve portare la SUA ora vera (07:00): ' + titoliBarre.join(' | '));
  assert.ok(titoliBarre.some((t) => /\b13:00\b/.test(t)),
    'la barra da 4,8 kWh deve portare la SUA ora vera (13:00): ' + titoliBarre.join(' | '));
  assert.ok(!titoliBarre.some((t) => /\bpunto\s*\d/.test(t)),
    'nessun segnaposto posizionale ("punto N") deve restare nel testo delle barre: ' + titoliBarre.join(' | '));
});

test('seam _rendiOggetti: due punti lontani nel tempo restano distanti nel grafico -- i buchi si vedono', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [puntoOra(4, 1), puntoOra(5, 1), puntoOra(18, 1)] },
    }),
  })], null);

  const rects = Array.from(corpo.querySelectorAll('svg rect'));
  assert.equal(rects.length, 3);
  const xs = rects.map((r) => parseFloat(r.getAttribute('x'))).sort((a, b) => a - b);
  const scartoRavvicinato = xs[1] - xs[0]; // 4:00 -> 5:00, un'ora
  const scartoLontano = xs[2] - xs[1]; // 5:00 -> 18:00, tredici ore
  assert.ok(scartoLontano > scartoRavvicinato * 5,
    'un buco di 13 ore deve restare visibilmente più largo di uno di 1 ora: ' +
    scartoRavvicinato + ' vs ' + scartoLontano);
});

test('seam _rendiOggetti: l\'ora mostrata è quella LOCALE (convertita con Date), mai le cifre grezze della stringa ISO', () => {
  // `ora` arriva in UTC (`HAClient._instant_from_ha`): mostrare le prime
  // cifre della stringa ("13" da "...T13:00:00Z") sarebbe il difetto in
  // forma peggiore -- non più "non so l'ora", ma "affermo l'ora sbagliata"
  // (fino a due ore, con l'ora legale). Un fuso ESPLICITO e lontano da UTC
  // rende la prova indipendente dal fuso di chi fa girare il test: se la
  // resa leggesse le cifre grezze mostrerebbe "13:00" anche qui; la resa
  // corretta converte con `new Date(iso)`, come fa già `fmtIsoHour` per i
  // momenti -- la STESSA strada, non una nuova.
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const isoConFusoEsplicito = '2026-08-23T13:00:00+05:00';
  const d = new Date(isoConFusoEsplicito);
  const pad2 = (n) => (n < 10 ? '0' + n : String(n));
  const oraLocaleAttesa = pad2(d.getHours()) + ':' + pad2(d.getMinutes());

  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [{ ora: isoConFusoEsplicito, valore: 2.5 }] },
    }),
  })], null);

  const titoloBarra = corpo.querySelector('svg rect > title').textContent;
  assert.ok(titoloBarra.indexOf(oraLocaleAttesa) !== -1,
    'la barra deve mostrare l\'ora LOCALE vera (' + oraLocaleAttesa + ', convertita con Date): ' + titoloBarra);
  if (oraLocaleAttesa !== '13:00') {
    assert.ok(titoloBarra.indexOf('13:00') === -1,
      'non deve mostrare la cifra GREZZA "13:00" letta dalla stringa ISO quando l\'ora locale vera è diversa: ' + titoloBarra);
  }
});

test('seam _rendiOggetti: un punto senza `ora` valida non si disegna (mai un\'ora inventata)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [{ ora: null, valore: 9.9 }] },
    }),
  })], null);

  const rects = corpo.querySelectorAll('svg rect');
  assert.equal(rects.length, 0, 'un punto senza ora non deve produrre una barra posizionata a caso');
});

// La dodicesima (brief-dodicesima.md, punto 1 -- MEDIO, "il cuore"): nessun
// test qui sopra lega la POSIZIONE della barra all'ora che dichiara. Un test
// guarda le distanze RELATIVE fra le barre ("i buchi si vedono", sopra), un
// altro guarda l'ETICHETTA (il titolo del `<title>`, sopra) -- nessuno lega
// le due cose. Mutazione ESEGUITA dal revisore per provarlo: spostare OGNI
// barra di un'ora nel solo piazzamento (x), lasciando l'etichetta corretta
// -> i 56 test allora esistenti restavano tutti verdi. Il riquadro al
// passaggio del mouse direbbe «le 13», e la barra starebbe alle 14 -- e la
// POSIZIONE e' cio' che si guarda per decidere, non l'etichetta.
// Serve un ancoraggio ASSOLUTO: la coordinata x attesa, calcolata dalla SUA
// ora con lo stesso contratto geometrico di `renderBalanceCurve`
// (watcher-route.js: viewBox 640x140, margine sinistro 4, 24 ore fisse
// -- `L`/`sinistra`/`ORE_DEL_GIORNO` nel sorgente, non ricopiati per caso:
// e' lo stesso disegno che la pagina dichiara nel suo `viewBox`, verificato
// sotto). Una sola serie (produzione) rende l'indice di serie ininfluente
// (`si * barWidth` = 0), cosi' la formula attesa non dipende da un
// dettaglio che non e' oggetto di questo test.
test('seam _rendiOggetti: la barra sta alla coordinata ASSOLUTA della sua ora, non solo in un ordine relativo alle altre (mutazione: un piazzamento spostato di un\'ora resta verde per tutti gli altri test)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture({
    corpo: Object.assign({}, bilancioFixture().corpo, {
      forma: { produzione: [puntoOra(13, 4.8)] },
    }),
  })], null);

  const svg = corpo.querySelector('svg');
  assert.ok(svg, 'deve esserci il grafico');
  // Precondizione: il viewBox deve davvero essere 640x140 (altrimenti la
  // formula sotto misurerebbe il contratto sbagliato).
  assert.equal(svg.getAttribute('viewBox'), '0 0 640 140',
    'il viewBox del grafico non è più 640x140: aggiorna la costante di questo test insieme al sorgente');

  const rect = svg.querySelector('rect');
  assert.ok(rect, 'deve esserci la barra delle 13');

  const L = 640, sinistra = 4, ORE_DEL_GIORNO = 24;
  const passo = (L - sinistra * 2) / ORE_DEL_GIORNO;
  const xAttesa = sinistra + 13 * passo; // ora=13, una sola serie -> nessuno scarto di serie
  const xReale = parseFloat(rect.getAttribute('x'));
  assert.ok(Math.abs(xReale - xAttesa) < 0.15,
    'la barra delle 13 deve stare alla coordinata assoluta x=' + xAttesa.toFixed(1) +
    ' (sinistra + ora*passo), non a x=' + xReale +
    ' -- una traslazione uniforme del solo piazzamento (la mutazione del brief) sposta questo numero');
});

// ---------------------------------------------------------------------------
// Punto 3 (MEDIO): la descrizione dell'SVG non deve affermare «gli stessi
// numeri» -- falso nel caso generale (i momenti portano orari e percentuali,
// non gli stessi kWh della curva) -- e deve sparire quando i momenti mancano.
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: la descrizione dell\'SVG non dichiara "gli stessi numeri" dei momenti', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const desc = corpo.querySelector('svg desc').textContent;
  assert.doesNotMatch(desc, /stessi numeri/i,
    'i momenti non ripetono "gli stessi numeri" della curva (percentuali, orari): falso nel caso generale');
});

test('seam _rendiOggetti: senza `momenti`, la descrizione dell\'SVG non rimanda a una sezione che non c\'è', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.momenti;
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [fx], null);

  const desc = corpo.querySelector('svg desc').textContent;
  assert.doesNotMatch(desc, /momenti/, 'orfana se i momenti mancano: la frase non deve più nominarli');
});

test('seam _rendiOggetti: i momenti si leggono come dati secchi (orario HH:MM, percentuale con la virgola)', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  // Sul NODO giusto (rilievo 2 del brief «css-morto»: un assert sul testo di
  // TUTTA la pagina/riga può essere soddisfatto da un'altra sezione).
  // `<dt>`/`<dd>` non hanno separatore visivo nel textContent concatenato,
  // quindi si legge la coppia esatta, non l'intera riga.
  const momenti = corpo.querySelector('.bil-momenti');
  assert.ok(momenti, 'deve esserci la sezione dei momenti derivati');
  const etichette = Array.from(momenti.querySelectorAll('dt')).map((n) => n.textContent);
  const valori = Array.from(momenti.querySelectorAll('dd')).map((n) => n.textContent);
  assert.ok(etichette.includes('Prima ora di produzione'));

  const primaOra = valori[etichette.indexOf('Prima ora di produzione')];
  assert.match(primaOra, /^\d{2}:\d{2}$/, 'l\'orario si legge HH:MM, non un timestamp ISO grezzo: ' + primaOra);
  assert.doesNotMatch(corpo.textContent, /2026-08-23T/, 'nessun ISO grezzo in pagina');

  const quota = valori[etichette.indexOf('Quota di autoconsumo')];
  assert.match(quota, /^71,2\s*%$/, 'la quota di autoconsumo è una percentuale con la virgola italiana: ' + quota);

  const picco = valori[etichette.indexOf('Picco di produzione')];
  assert.match(picco, /4,8\s*kWh/, 'il picco di produzione porta il suo valore in kWh: ' + picco);
  assert.match(picco, /\d{2}:\d{2}/, 'il picco di produzione porta anche l\'ora: ' + picco);
});

test('seam _rendiOggetti: senza `momenti` non compare la sezione dei momenti derivati', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  delete fx.corpo.momenti;
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [fx], null);

  assert.doesNotMatch(corpo.textContent, /Prima ora di produzione/);
  assert.doesNotMatch(corpo.textContent, /Quota di autoconsumo/);
});

// ---------------------------------------------------------------------------
// Punto 2 (MEDIO): a 1200px `.bil-momenti` (auto-fit) può calcolare un numero
// DISPARI di colonne -- dt e dd, celle indipendenti della griglia, si
// spezzano a fine riga (misurato dal revisore: «Picco di produzione» chiude
// una riga, il suo valore ne apre un'altra accanto a un'altra etichetta).
// jsdom non fa layout, quindi non può riprodurre lo sfondamento a 1200px --
// ma può verificare la precondizione strutturale della correzione: ogni
// dt/dd deve condividere un contenitore proprio (`.bil-momento`), MAI essere
// figlio diretto di `.bil-momenti`, perché solo così un motore vero non può
// più spezzare la coppia a nessuna larghezza (verificato dal vivo, vedi il
// rapporto).
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: ogni momento (dt+dd) è una coppia atomica, mai due celle indipendenti della griglia', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const momenti = corpo.querySelector('.bil-momenti');
  const dts = Array.from(momenti.querySelectorAll('dt'));
  assert.ok(dts.length > 1, 'servono almeno due momenti per verificare che non si spezzino (fixture insufficiente?)');
  dts.forEach((dt) => {
    assert.notEqual(dt.parentElement, momenti,
      'dt non deve essere figlio diretto di `.bil-momenti`: a certe larghezze un motore vero lo separa dal suo dd (rilievo 2)');
    const dd = dt.nextElementSibling;
    assert.ok(dd && dd.tagName === 'DD', 'ogni dt deve avere il suo dd come fratello immediato: ' + dt.textContent);
    assert.equal(dt.parentElement, dd.parentElement,
      'dt e dd devono condividere lo stesso contenitore (coppia atomica)');
  });
});

// ---------------------------------------------------------------------------
// Il consumo, settima direzione del bilancio (LETTA, non dedotta -- vedi il
// commento sopra DIREZIONI_BILANCIO in cervello/oggetti.py, mandato «il
// bilancio dell'energia», punto 1, 27/08/2026): la pagina deve poterlo
// mostrare come le altre sei, con la stessa etichetta già usata dagli
// episodi di energia.
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: il totale "consumo" (settima direzione) si mostra come le altre sei', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture();
  fx.corpo.totali.consumo = { valore: 17.3, provenienza: null };
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [fx], null);

  assert.match(corpo.textContent, /Consumo della casa/);
  assert.match(corpo.textContent, /17,3\s*kWh/);
});

test('seam _rendiOggetti: le entità del bilancio stanno dietro un rivelatore sincrono, chiuso di default', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  document.body.appendChild(corpo);
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [bilancioFixture()], null);

  const btn = Array.from(corpo.querySelectorAll('button')).find((b) => /sensori/.test(b.textContent));
  assert.ok(btn, 'deve esserci un rivelatore per le entità del bilancio');
  const pannello = btn.nextElementSibling;
  // Chiuso via `hidden` (attributo DOM, non solo un display CSS), come il
  // rivelatore di comprimari/misure sopra: `textContent` include SEMPRE il
  // testo dei nodi `hidden` (in jsdom come in un motore vero), quindi non è
  // il segnale giusto per "non ancora visibile" -- lo è l'attributo.
  assert.equal(pannello.hidden, true, 'il pannello nasce chiuso');

  btn.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(pannello.hidden, false, 'il click deve aprire il pannello');
  assert.match(pannello.textContent, /sensor\.energia_prodotta_oggi/);
  assert.match(pannello.textContent, /sensor\.energia_immessa_oggi/);
});

test('seam _rendiOggetti: un bilancio senza entità non mostra nessun rivelatore di entità', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  const fx = bilancioFixture({ corpo: Object.assign({}, bilancioFixture().corpo, { entita: [] }) });
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [fx], null);

  const btn = Array.from(corpo.querySelectorAll('button')).find((b) => /sensori/.test(b.textContent));
  assert.equal(btn, undefined);
});

test('mount: un bilancio nella lista di "cosa è successo" si legge, non resta "(nessun dettaglio)"', async () => {
  const { window, document } = montaConServer({ facts: { facts: [bilancioFixture()] } });
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const testo = document.getElementById('route-outlet').textContent;
  assert.doesNotMatch(testo, /nessun dettaglio/);
  assert.match(testo, /kWh/);
  assert.match(testo, /Inverter con accumulo/);
});

// ---------------------------------------------------------------------------
// Corsa sul cambio giorno (rilievo 8b): un contatore di generazione
// ---------------------------------------------------------------------------

test('due cambi rapidi di giorno: la risposta più lenta e superata non deve vincere su quella giusta', async () => {
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const risposte = {};
  risposte[IERI] = { facts: [{ id: 1, genere: 'funzionamento', protagonista: 'light.vecchio_giorno', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };
  risposte[OGGI] = { facts: [{ id: 2, genere: 'funzionamento', protagonista: 'light.giorno_giusto', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };

  window.fetch = (url) => {
    const u = String(url);
    if (u.indexOf('api/mind/watching') === 0) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ watching: [] }) });
    }
    const m = u.match(/day=([\d-]+)/);
    const giorno = m ? decodeURIComponent(m[1]) : null;
    // La prima richiesta lanciata (IERI, poi superata da OGGI) è anche la
    // più lenta: senza guardia arriverebbe per ultima e vincerebbe.
    const ritardo = giorno === IERI ? 40 : 5;
    return new Promise((resolve) => setTimeout(() => resolve(
      { ok: true, status: 200, json: async () => risposte[giorno] }), ritardo));
  };

  const input = document.querySelector('input[type=date]');
  input.value = IERI;
  input.dispatchEvent(new window.Event('change'));
  await tick(1); // lascia partire la prima richiesta prima di cambiare di nuovo
  input.value = OGGI;
  input.dispatchEvent(new window.Event('change'));

  await tick(80); // entrambe le risposte sono arrivate ormai

  const testo = document.getElementById('route-outlet').textContent;
  assert.match(testo, /light\.giorno_giusto/, 'deve mostrare il giorno richiesto per ultimo');
  assert.doesNotMatch(testo, /light\.vecchio_giorno/,
    'la risposta più lenta e superata non deve sovrascrivere quella giusta arrivata dopo, ma per prima');
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
