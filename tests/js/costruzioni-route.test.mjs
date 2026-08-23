import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';

const SORGENTE = fs.readFileSync(
  new URL('../../hiris/app/static/config/costruzioni-route.js', import.meta.url), 'utf8');

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
  const { dom } = montaCon({ costruzioni: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1771', anteprima: 'Creo un automazione', prima: null,
      dopo: { alias: 'Tapparelle' }, creata_ts: 1756000000 },
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'vecchio' },
      dopo: { alias: 'nuovo' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisCostruzioni.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.match(testo, /Tapparelle/);
  const conferme = dom.window.document.querySelectorAll('[data-azione="conferma"]');
  assert.equal(conferme.length, 1);
});

test('una modifica a un oggetto non creato da HIRIS lo dichiara', async () => {
  const { dom } = montaCon({ costruzioni: [
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'la tua automazione' },
      dopo: { alias: 'modificata' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisCostruzioni.mount(dom.window.document.getElementById('route-outlet'));
  assert.match(dom.window.document.body.textContent, /modificat/i);
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
  const { dom } = montaCon({ costruzioni: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisCostruzioni.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="conferma"]').length, 1);
  assert.equal(dom.window.document.querySelectorAll('[data-azione="rifiuta"]').length, 1);
});

test('il no del proprietario non si mostra come un fallimento', async () => {
  // `disdetta` e `rifiutata` sono due cose diverse e non devono leggersi
  // uguali: la prima e' l'utente che ha deciso, la seconda e' HIRIS che non
  // ce l'ha fatta. Se il vocabolario le confondesse, la pagina punirebbe
  // l'unica cosa che deve essere facile fare.
  const { dom } = montaCon({ costruzioni: [
    { id: 'd1', stato: 'disdetta', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'rifiutata dal proprietario' },
    { id: 'r1', stato: 'rifiutata', gesto: 'crea', dominio: 'automation',
      chiave: '2', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'Home Assistant ha rifiutato' },
  ] });
  await dom.window.HirisCostruzioni.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.doesNotMatch(testo, /disdetta|rifiutata\b/i,
    'gli stati interni non devono uscire come token grezzi');
  const righe = dom.window.document.querySelectorAll('.costruzione');
  assert.notEqual(righe[0].className, righe[1].className,
    'il no dell utente e il fallimento di HIRIS non possono avere la stessa faccia');
});

test('solo le costruzioni applicate offrono il ripristino', async () => {
  const { dom } = montaCon({ costruzioni: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisCostruzioni.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="ripristina"]').length, 0);
});
