import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { JSDOM } from 'jsdom';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Giro di correzioni sulla pagina «L'osservatore» (config/osservatore-route.js),
   guida-ux-osservatore in .superpowers/sdd/2026-08-26-l-osservatore/pagina-brief.md.

   E' anche il primo file di test di questa pagina: fino a qui `_rendiOsservate`
   e `_rendiOggetti` erano una seam PROMESSA da un commento ("seam di test: la
   resa va pinnata senza passare da fetch") e mai usata da nessun test -- oltre
   quattrocento righe di resa senza nessuna rete. Le sezioni "seam:" qui sotto
   chiudono quel buco usando esattamente quelle due funzioni. */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'hiris', 'app', 'static', 'config');
const SORGENTE = readFileSync(join(CONFIG_DIR, 'osservatore-route.js'), 'utf8');

function fixtureHtml() {
  return '<!doctype html><body><div id="route-outlet"></div></body>';
}

const SCRIPTS = ['config/osservatore-route.js'];

function jsonResponse(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

/* Il finto server: distingue le due rotte per prefisso, come fa la pagina
   vera (`api/cervello/osservate`, `api/cervello/oggetti[?giorno=...]`). */
function montaConServer(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const chiamate = [];
  ctx.window.fetch = async (url) => {
    const u = String(url);
    chiamate.push(u);
    if (u.indexOf('api/cervello/osservate') === 0) {
      if (opts.osservateRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.osservate !== undefined ? opts.osservate : { osservate: [] },
        opts.osservateStatus);
    }
    if (u.indexOf('api/cervello/oggetti') === 0) {
      if (opts.oggettiRotto) throw new Error('rete giu\'');
      return jsonResponse(
        opts.oggetti !== undefined ? opts.oggetti : { oggetti: [] },
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
    osservate: { osservate: [{ soggetto: 'light.cucina', gamba: 'comfort', provenienza: 'pavimento' }] },
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

  // Stessa struttura di rigaOggetto() in osservatore-route.js: uno span
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
  const { window, document } = montaConServer({ osservateStatus: 503, osservate: {} });
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

  const primaDelClick = chiamate.filter((u) => u.indexOf('osservate') !== -1).length;
  const retry = bottone(document, 'Riprova');
  assert.ok(retry, 'deve esserci un modo di riprovare');
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const dopoIlClick = chiamate.filter((u) => u.indexOf('osservate') !== -1).length;
  assert.equal(dopoIlClick, primaDelClick + 1, 'il bottone deve rilanciare la stessa richiesta');
});

test('un errore nel leggere "cosa è successo" (503) offre Riprova', async () => {
  const { window, document } = montaConServer({ oggettiStatus: 503, oggetti: {} });
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

  const chiamateOggettiPrima = chiamate.filter((u) => u.indexOf('oggetti') !== -1);
  const retry = bottone(document, 'Riprova');
  assert.ok(retry);
  retry.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(20);

  const chiamateOggettiDopo = chiamate.filter((u) => u.indexOf('oggetti') !== -1);
  assert.equal(chiamateOggettiDopo.length, chiamateOggettiPrima.length + 1);
  assert.equal(chiamateOggettiDopo[chiamateOggettiDopo.length - 1], chiamateOggettiPrima[0],
    'il retry deve rilanciare la stessa richiesta (stesso giorno), non perdere il filtro');
});

// ---------------------------------------------------------------------------
// Il primo giorno: quando comparirà qualcosa (rilievo 5) — «episodi» (6a)
// ---------------------------------------------------------------------------

test('nessun episodio per IERI: dice quando tornare (00:20), niente data ISO, niente ipotesi debole', async () => {
  const { window, document } = montaConServer({ oggetti: { oggetti: [] } });
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
  const { window, document } = montaConServer({ oggetti: { oggetti: [] } });
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
  const { window, document } = montaConServer({ oggetti: { oggetti: [] } });
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
  const { window, document } = montaConServer({ oggetti: { oggetti: [] } });
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
// Seam _rendiOggetti: i cinque generi, i comprimari, le misure — senza rete
// (rilievo 9: la resa era priva di qualunque test)
// ---------------------------------------------------------------------------

test('seam _rendiOggetti: un consumo mostra da/a e la differenza col segno', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'consumo', protagonista: 'sensor.energia_forno',
    inizio_ts: 1755270600, fine_ts: 1755277500,
    corpo: { valore_iniziale: 12.5, valore_finale: 15.0, differenza: 2.5 },
  }], null);
  assert.match(corpo.textContent, /da 12\.5 a 15/);
  assert.match(corpo.textContent, /\+2\.5/);
});

test('seam _rendiOggetti: un consumo con differenza non calcolabile lo dichiara, mai un NaN silenzioso', () => {
  const { window, document } = loadScripts(SCRIPTS, { html: fixtureHtml() });
  const corpo = document.createElement('div');
  window.HirisOsservatoreRoute._rendiOggetti(corpo, [{
    id: 1, genere: 'consumo', protagonista: 'sensor.contatore',
    inizio_ts: 1, fine_ts: 2,
    corpo: { valore_iniziale: 5, valore_finale: 'unavailable', differenza: null },
  }], null);
  assert.match(corpo.textContent, /non calcolabile/);
  assert.doesNotMatch(corpo.textContent, /NaN/);
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
  assert.match(corpo.textContent, /ancora in corso/, 'un fine_ts nullo si dichiara come "ancora in corso"');
  assert.match(corpo.textContent, /Problema Home Assistant: hue\.bridge_offline/,
    'un protagonista "problema:" diventa un nome leggibile, come in albero-route.js');
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
// Corsa sul cambio giorno (rilievo 8b): un contatore di generazione
// ---------------------------------------------------------------------------

test('due cambi rapidi di giorno: la risposta più lenta e superata non deve vincere su quella giusta', async () => {
  const { window, document } = montaConServer();
  window.HirisOsservatoreRoute.mount();
  await tick(20);

  const risposte = {};
  risposte[IERI] = { oggetti: [{ id: 1, genere: 'funzionamento', protagonista: 'light.vecchio_giorno', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };
  risposte[OGGI] = { oggetti: [{ id: 2, genere: 'funzionamento', protagonista: 'light.giorno_giusto', inizio_ts: 1, fine_ts: 2, corpo: { stato: 'on' } }] };

  window.fetch = (url) => {
    const u = String(url);
    if (u.indexOf('api/cervello/osservate') === 0) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ osservate: [] }) });
    }
    const m = u.match(/giorno=([\d-]+)/);
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
// Pulizia: nessun `TONO_IGNOTO` morto, nessun innerHTML (rilievo 8d + disciplina generale)
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
