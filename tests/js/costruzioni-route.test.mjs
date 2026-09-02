import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const SORGENTE = fs.readFileSync(
  new URL('../../hiris/app/static/config/constructions-route.js', import.meta.url), 'utf8');

function montaCon(risposta) {
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  const chiamate = [];
  dom.window.fetch = async (url, opzioni) => {
    chiamate.push([url, opzioni]);
    return { ok: true, status: 200, json: async () => risposta };
  };
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();
  return { dom, chiamate };
}

test('le proposte in attesa hanno il bottone di conferma, le applicate no', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1771', anteprima: 'Creo un automazione', prima: null,
      dopo: { alias: 'Tapparelle' }, creata_ts: 1756000000 },
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'vecchio' },
      dopo: { alias: 'nuovo' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.match(testo, /Tapparelle/);
  const conferme = dom.window.document.querySelectorAll('[data-azione="confirm"]');
  assert.equal(conferme.length, 1);
});

test('una modifica a un oggetto non creato da HIRIS lo dichiara', async () => {
  // La regola l'ha posta il proprietario con parole sue -- "se tocca
  // qualcosa lo deve dire" -- ed e' il testo esatto sotto, non il badge
  // "Modificata" (`/modificat/i`): quel badge compare per OGNI gesto di
  // modifica, riuscita o no, e cancellando `eraGiaLi()` insieme alla riga
  // "Questo oggetto esiste già in casa tua" la vecchia asserzione restava
  // verde (ondata finale, punto 4 -- il difetto n.1: un test che non puo'
  // fallire). Una `create`, per contrasto, non deve MAI portare questa
  // dichiarazione: non ha toccato niente che esistesse gia'.
  const { dom } = montaCon({ constructions: [
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'la tua automazione' },
      dopo: { alias: 'modificata' }, creata_ts: 1756000000 },
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1773', anteprima: '', prima: null,
      dopo: { alias: 'nuova' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  const storico = document.getElementById('costruzioni-storico-body');
  const aperte = document.getElementById('costruzioni-aperte-body');
  assert.match(storico.textContent, /Questo oggetto esiste già in casa tua\./);
  assert.doesNotMatch(aperte.textContent, /esiste già/);
});

test('il sorgente non usa innerHTML, in nessuna forma', () => {
  // RULING 3 della scansione pre-volo: la versione precedente di questo test
  // cercava una regex cosi' specifica da non poter fallire su nessuna
  // scrittura realistica -- il difetto n.1 di questo progetto.
  // Un divieto netto e' piu' forte di un'ipotesi: alias e anteprime nascono da
  // una chat, e una chat puo' contenere markup. Se un giorno servira'
  // `innerHTML` su una costante nostra, questo test si cambia CON un motivo
  // scritto accanto -- che e' esattamente la conversazione che deve avvenire.
  assert.doesNotMatch(SORGENTE, /innerHTML/);
});

test('una proposta in attesa offre sia Approva sia Rifiuta', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="confirm"]').length, 1);
  assert.equal(dom.window.document.querySelectorAll('[data-azione="reject"]').length, 1);
});

test('il no del proprietario non si mostra come un fallimento', async () => {
  // `disdetta` e `rifiutata` sono due cose diverse e non devono leggersi
  // uguali: la prima e' l'utente che ha deciso, la seconda e' HIRIS che non
  // ce l'ha fatta. Se il vocabolario le confondesse, la pagina punirebbe
  // l'unica cosa che deve essere facile fare.
  const { dom } = montaCon({ constructions: [
    { id: 'd1', stato: 'disdetta', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'rifiutata dal proprietario' },
    { id: 'r1', stato: 'rifiutata', gesto: 'crea', dominio: 'automation',
      chiave: '2', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'Home Assistant ha rifiutato' },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.doesNotMatch(testo, /disdetta|rifiutata\b/i,
    'gli stati interni non devono uscire come token grezzi');
  const righe = dom.window.document.querySelectorAll('.costruzione');
  assert.notEqual(righe[0].className, righe[1].className,
    'il no dell utente e il fallimento di HIRIS non possono avere la stessa faccia');
});

test('solo le costruzioni applicate offrono il ripristino', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="restore"]').length, 0);
});

test('una scena mostra il conteggio e gli entity_id anche se `entities` è un dizionario', async () => {
  // Rilievo della review: `forme.py::compose_scene` (e Home Assistant per
  // `prima`) rappresentano `entities` di una scena come un DIZIONARIO
  // entity_id -> attributi, non un array come per automazioni/script.
  // `{}.length` in JS è `undefined`, non `0`: senza gestire questa forma il
  // pannello mostrava "entità: undefined" e gli entity_id non comparivano
  // mai -- proprio per il dominio in cui quella lista è tutto il contenuto
  // dell'oggetto (guida §3).
  const { dom } = montaCon({ constructions: [
    { id: 's1', stato: 'applicata', gesto: 'modifica', dominio: 'scene',
      chiave: 'scena_sera', anteprima: '',
      prima: { alias: 'Scena sera', entities: { 'light.cucina': { state: 'on' } } },
      dopo: { alias: 'Scena sera', entities: {
        'light.cucina': { state: 'on' }, 'light.salotto': { state: 'off' } } },
      creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  const dettagli = Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent === 'Dettagli tecnici');
  assert.ok(dettagli, 'la card deve avere il rivelatore dei dettagli tecnici');
  dettagli.dispatchEvent(new dom.window.Event('click', { bubbles: true }));

  const testo = document.body.textContent;
  assert.doesNotMatch(testo, /undefined/,
    '{}.length e\' undefined in JS, non 0: un dizionario non trattato come tale lo fa trapelare');
  assert.match(testo, /entità: 1 → 2/,
    'il conteggio deve leggere le CHIAVI del dizionario, non .length su un dizionario');
  assert.match(testo, /light\.cucina/);
  assert.match(testo, /light\.salotto/);
});

test('durante una richiesta in volo Approva e Rifiuta si disabilitano insieme', async () => {
  // Rilievo della review: il backend regge un doppio clic (la UPDATE e'
  // atomica), ma restava un'incoerenza visibile -- premuto Approva, Rifiuta
  // rimaneva cliccabile mentre la richiesta girava ancora. La `fetch` per la
  // conferma qui NON si risolve mai (`new Promise(() => {})`): e' l'unico
  // modo di osservare lo stato "in volo", non quello dopo -- lo stub di
  // `montaCon`, che risponde subito, non lo permetterebbe.
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.fetch = async (url, _opzioni) => {
    if (String(url).indexOf('/confirm') !== -1) return new Promise(() => {});
    return { ok: true, status: 200, json: async () => ({ constructions: [
      { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
        chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
    ] }) };
  };
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();

  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const conferma = dom.window.document.querySelector('[data-azione="confirm"]');
  const rifiuta = dom.window.document.querySelector('[data-azione="reject"]');
  conferma.dispatchEvent(new dom.window.Event('click', { bubbles: true }));

  // Nessun await qui: la disabilitazione avviene sincrona dentro il
  // gestore del click (`executeAction` disabilita PRIMA di chiamare fetch),
  // quindi si asserisce subito, prima di qualunque flush di microtask.
  assert.equal(conferma.disabled, true, 'il bottone premuto si disabilita');
  assert.equal(rifiuta.disabled, true,
    'il gemello deve disabilitarsi insieme, non restare cliccabile mentre la richiesta è in volo');
});
