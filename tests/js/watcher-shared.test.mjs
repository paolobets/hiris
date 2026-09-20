import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadScripts } from './helpers/dom.mjs';

/* La forma condivisa degli ELENCHI LUNGHI (spec
   `docs/design/2026-09-18-la-pagina-dell-osservatore.md` §6).

   Una forma sola per misure, forme, cronaca, giudizi, sapere, soggetti
   guardati e lasciati fuori: riassunto coi numeri, i pochi che contano con il
   loro criterio dichiarato, e il resto dietro un bottone.

   **Misurato il 18/09/2026, ed e' la ragione per cui esiste**: la pagina
   scaricava 110 KB e disegnava piu' di 500 righe in una colonna sola. Il
   19/09 la sola cronaca ne aveva 93, i giudizi 121, i soggetti guardati 153,
   i lasciati fuori 280.

   Le prove stanno in un file loro perche' il pezzo e' di `watcher-shared.js`:
   quattro schede lo useranno, e provarlo dentro una sola direbbe che
   funziona li'. */

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..',
  'hiris', 'app', 'static', 'config');

function monta() {
  const ctx = loadScripts(['config/watcher-shared.js'],
    { html: '<!doctype html><body><div id="x"></div></body>' });
  return { ctx, corpo: ctx.document.getElementById('x') };
}

function dati(quanti, prefisso) {
  const righe = [];
  for (let i = 0; i < quanti; i++) righe.push({ testo: (prefisso || 'riga') + ' ' + i });
  return righe;
}

function elenco(ctx, corpo, extra) {
  const S = ctx.window.HirisWatcherShared;
  const rese = [];
  const opzioni = Object.assign({
    titolo: 'La cronaca',
    riassunto: '93 voci · 5 fuori dal solito',
    didascalia: 'le 5 più recenti',
    pochi: dati(5, 'poco'),
    tutti: dati(93),
    etichetta: 'Vedi tutte',
    rendi: function (d) { rese.push(d.testo); return S.el('div', 'sc-row', d.testo); }
  }, extra || {});
  S.elencoLungo(corpo, opzioni);
  return rese;
}

function bottone(corpo, testo) {
  return [...corpo.querySelectorAll('button')]
    .filter((b) => b.textContent.indexOf(testo) >= 0)[0];
}

test('elencoLungo: prima del clic disegna SOLO i pochi che contano', () => {
  /* **Il punto della fetta**: 93 righe costruite subito sono 93 righe che
     nessuno ha chiesto. Mutazione che la uccide: costruire l'elenco intero e
     nasconderlo con `hidden`. */
  const { ctx, corpo } = monta();
  const rese = elenco(ctx, corpo);

  assert.equal(rese.length, 5, '`rendi` è stata chiamata per righe che nessuno vede');
  assert.equal(corpo.querySelectorAll('.sc-row').length, 5);
});

test('elencoLungo: il riassunto e il criterio dei pochi si leggono, sempre', () => {
  /* «I pochi che contano hanno un criterio dichiarato in didascalia, mai
     l'ordine di arrivo» (spec §6): senza la frase, cinque righe scelte da noi
     sembrerebbero le uniche cinque.

     Mutazione che la uccide: disegnare i pochi senza la didascalia. */
  const { ctx, corpo } = monta();
  elenco(ctx, corpo);

  assert.match(corpo.textContent, /93 voci · 5 fuori dal solito/);
  assert.match(corpo.textContent, /le 5 più recenti/);
});

test('elencoLungo: il bottone dice QUANTE sono in tutto', () => {
  // Mutazione che la uccide: un'etichetta senza numero («Vedi tutte»).
  const { ctx, corpo } = monta();
  elenco(ctx, corpo);

  assert.ok(bottone(corpo, 'Vedi tutte (93)'), 'il numero è la misura di cosa si sta aprendo');
});

test('elencoLungo: al clic l\'elenco si COSTRUISCE, e il fuoco va sul titolo', () => {
  /* Il fuoco sul titolo e non sulla prima riga: chi usa uno screen reader
     deve sapere **cosa** si è aperto prima di sentirne il contenuto.

     Mutazione che la uccide: non spostare il fuoco (resta sul bottone, e
     l'elenco nuovo passa inosservato). */
  const { ctx, corpo } = monta();
  const rese = elenco(ctx, corpo);
  const apri = bottone(corpo, 'Vedi tutte (93)');
  apri.click();

  assert.equal(rese.length, 5 + 50, 'il primo blocco è di 50 righe (spec §6)');
  assert.equal(apri.getAttribute('aria-expanded'), 'true');
  const titolo = corpo.querySelector('.long-list-title');
  assert.ok(titolo, 'l’elenco aperto non ha un titolo su cui posare il fuoco');
  assert.equal(titolo.getAttribute('tabindex'), '-1');
  assert.equal(ctx.document.activeElement, titolo);
});

test('elencoLungo: chiudendo, il fuoco TORNA al bottone', () => {
  /* Altrimenti il fuoco resta su un nodo che non c'è più e cade su <body>:
     chi naviga da tastiera riparte dall'inizio della pagina.

     Mutazione che la uccide: togliere il `focus()` sulla chiusura. */
  const { ctx, corpo } = monta();
  elenco(ctx, corpo);
  const apri = bottone(corpo, 'Vedi tutte (93)');
  apri.click();
  apri.click();

  assert.equal(apri.getAttribute('aria-expanded'), 'false');
  assert.equal(ctx.document.activeElement, apri);
  assert.equal(corpo.querySelectorAll('.sc-row').length, 5, 'chiudendo restano i soli pochi');
});

test('elencoLungo: oltre le cento righe si va a blocchi di cinquanta', () => {
  /* Misurato: i lasciati fuori sono 280. Disegnarli in un colpo e' la
     colonna infinita che questa fetta toglie.

     Mutazione che la uccide: un blocco solo con tutte le righe. */
  const { ctx, corpo } = monta();
  const rese = elenco(ctx, corpo, { tutti: dati(280), etichetta: 'Vedi tutti' });
  bottone(corpo, 'Vedi tutti (280)').click();

  assert.equal(rese.length, 5 + 50);
  const ancora = bottone(corpo, 'Altre');
  assert.ok(ancora, 'senza questo bottone le altre 230 righe sarebbero perdute');
  assert.match(ancora.textContent, /230/, 'il bottone dice quante ne restano');
});

test('elencoLungo: il blocco successivo mette il fuoco sulla PRIMA riga nuova', () => {
  /* Spec §6. Senza, chi legge da tastiera torna in cima all'elenco ogni
     volta che chiede altre cinquanta righe.

     Mutazione che la uccide: lasciare il fuoco sul bottone «Altre». */
  const { ctx, corpo } = monta();
  elenco(ctx, corpo, { tutti: dati(280), etichetta: 'Vedi tutti' });
  bottone(corpo, 'Vedi tutti (280)').click();
  bottone(corpo, 'Altre').click();

  const righe = [...corpo.querySelectorAll('.sc-row')];
  const prima = righe[5 + 50];
  assert.ok(prima, 'il secondo blocco non è stato disegnato');
  assert.equal(ctx.document.activeElement, prima);
});

test('elencoLungo: finite le righe, il bottone «Altre» non si vede più', () => {
  /* 120 righe sono tre blocchi: 50, 50, 20. Il bottone dice ogni volta
     quante ne restano, e all'ultimo giro esce di scena invece di offrire un
     blocco vuoto.

     Mutazione che la uccide: tenerlo visibile a zero. */
  const { ctx, corpo } = monta();
  elenco(ctx, corpo, { tutti: dati(120), etichetta: 'Vedi tutti' });
  bottone(corpo, 'Vedi tutti (120)').click();
  bottone(corpo, 'Altre').click();
  assert.match(bottone(corpo, 'Altre').textContent, /ne restano 20/);
  bottone(corpo, 'Altre').click();

  assert.equal(corpo.querySelectorAll('.sc-row').length, 5 + 120);
  assert.equal(bottone(corpo, 'Altre').hidden, true);
});

test('elencoLungo: un elenco corto non ha nessun bottone', () => {
  /* Cinque righe dietro «Vedi tutte (5)» sarebbero un clic per niente.

     Mutazione che la uccide: il bottone sempre. */
  const { ctx, corpo } = monta();
  elenco(ctx, corpo, { pochi: dati(3, 'poco'), tutti: dati(3, 'poco') });

  assert.equal(bottone(corpo, 'Vedi'), undefined);
  assert.equal(corpo.querySelectorAll('.sc-row').length, 3);
});

test('CSS: il bottone di un elenco è alto almeno 44 px, e l\'elenco non ha un\'altezza fissa', () => {
  /* I due vincoli della spec §6 che vivono nel foglio e non nel codice: il
     bersaglio del tocco (i `summary` di questa pagina sono alti 21-23 px, ed
     è la misura per cui non si usano) e **nessuno scroll dentro lo scroll**
     su telefono.

     Mutazioni che la uccidono: portare `min-height` a 32px; aggiungere
     `max-height` + `overflow: auto` a `.long-list`. */
  const css = readFileSync(join(CONFIG_DIR, '..', 'hiris-config.css'), 'utf8');

  const bottoneRegola = css.match(/\.long-list-btn \{([^}]*)\}/);
  assert.ok(bottoneRegola, 'manca la regola `.long-list-btn` in hiris-config.css');
  const alta = bottoneRegola[1].match(/min-height:\s*(\d+)px/);
  assert.ok(alta, '`.long-list-btn` non dichiara min-height');
  assert.ok(Number(alta[1]) >= 44, 'il bersaglio dichiara ' + alta[1] + 'px');

  const elencoRegola = css.match(/\.long-list \{([^}]*)\}/);
  assert.ok(elencoRegola, 'manca la regola `.long-list`');
  assert.doesNotMatch(elencoRegola[1], /max-height/,
    'un elenco con altezza fissa è uno scroll dentro lo scroll');
});


test("elencoLungo: l'elenco può avere la forma di chi lo usa (una griglia, non una colonna)", () => {
  /* Le misure sono piastrelle in griglia, la cronaca righe in colonna: una
     forma sola per il MECCANISMO -- riassunto, pochi, «vedi tutti», blocchi --
     non per il vestito. Senza questo, applicare il pezzo alle misure vorrebbe
     dire perdere la griglia, e chi lo applica sceglierebbe di non applicarlo.

     Mutazione che la uccide: la classe fissa dentro il pezzo. */
  const { ctx, corpo } = monta();
  const S = ctx.window.HirisWatcherShared;
  S.elencoLungo(corpo, {
    titolo: 'Le misure', riassunto: '67 misure', classe: 'stat-grid',
    pochi: dati(2, 'poco'), tutti: dati(67), etichetta: 'Vedi tutte',
    rendi: function (d) { return S.el('div', 'stat-tile', d.testo); }
  });

  const pochi = corpo.querySelector('.stat-grid');
  assert.ok(pochi, 'i pochi che contano hanno perso la griglia');
  assert.equal(pochi.querySelectorAll('.stat-tile').length, 2);
  bottone(corpo, 'Vedi tutte (67)').click();
  assert.equal(corpo.querySelectorAll('.stat-grid').length, 2, 'anche l’elenco aperto è una griglia');
});


test('elencoLungo: tre righe non si chiudono dietro un bottone', () => {
  /* Un elenco «chiuso» da una riga sola e' un clic per niente -- e il giorno
     in cui la casa ha una forma oraria sola la pagina direbbe «Vedi tutte
     (1)». Sotto la soglia si disegnano, sopra si chiudono: il meccanismo e'
     per gli elenchi LUNGHI.

     Mutazione che la uccide: il bottone appena `tutti.length > pochi.length`. */
  const { ctx, corpo } = monta();
  const rese = elenco(ctx, corpo, { pochi: [], didascalia: '', tutti: dati(3) });

  assert.equal(rese.length, 3, 'tre righe si disegnano e basta');
  assert.equal(bottone(corpo, 'Vedi'), undefined);

  const secondo = monta();
  elenco(secondo.ctx, secondo.corpo, { pochi: [], didascalia: '', tutti: dati(4) });
  assert.ok(bottone(secondo.corpo, 'Vedi tutte (4)'), 'sopra la soglia si chiude');
});
