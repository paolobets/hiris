/* L'ora della casa (C-17, Tappa 4, Task 4, passi 4-6): la famiglia di formati
   di `common.js` mostra le CIFRE dell'istante che il server manda con l'offset
   della casa, e non le converte mai nel fuso del browser.

   Il browser di queste prove sta a New York (`process.env.TZ`, che Node
   rilegge a ogni cambio), la casa a Roma: e' lo scenario del difetto, Paolo
   in viaggio che apre la pagina e legge le ore di un altro fuso. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

process.env.TZ = 'America/New_York';

const HTML = '<!doctype html><body><div id="route-outlet"><div>' +
  '<h1 class="page-title">Pagina</h1><p class="page-subtitle">sotto</p></div></div></body>';

/* 14/10/2026 alle 01:00 di Roma: a New York e' ancora il 13, alle 19:00. */
const OROLOGIO = { fuso: 'Europe/Rome', adesso: '2026-10-14T01:00:00+02:00' };

function carica() {
  loadScripts(['common.js'], { html: HTML });
  return globalThis;
}

test('la precondizione: il browser di questa prova sta davvero in un altro fuso', () => {
  assert.equal(new Date('2026-10-14T01:00:00+02:00').getHours(), 19,
    'se il browser fosse a Roma, ogni prova qui sotto passerebbe per caso');
});

test('si mostrano le cifre della casa, non quelle del browser', () => {
  const g = carica();
  assert.equal(g.fmtHour('2026-10-14T00:30:00+02:00'), '00:30');
  assert.equal(g.fmtInstant('2026-10-14T00:30:00+02:00', OROLOGIO), 'oggi alle 00:30',
    'oggi e\' il 14 della casa, anche se il browser e\' ancora al 13');
  assert.equal(g.fmtInstant('2026-10-13T23:30:00+02:00', OROLOGIO), 'ieri alle 23:30');
});

test('le quattro forme del parere UX: oggi, ieri, quest’anno, un altro anno', () => {
  const g = carica();
  assert.equal(g.fmtInstant('2026-10-14T00:30:00+02:00', OROLOGIO), 'oggi alle 00:30');
  assert.equal(g.fmtInstant('2026-10-13T14:30:00+02:00', OROLOGIO), 'ieri alle 14:30');
  assert.equal(g.fmtInstant('2026-10-12T14:30:00+02:00', OROLOGIO), '12/10, 14:30');
  assert.equal(g.fmtInstant('2025-10-12T14:30:00+02:00', OROLOGIO), '12/10/2025, 14:30');
});

test('l’anno e’ quello della casa, non del browser', () => {
  const g = carica();
  // A Roma e' gia' il 2027, a New York ancora il 2026: un istante del 2026
  // e' «un altro anno», e porta l'anno.
  const capodanno = { fuso: 'Europe/Rome', adesso: '2027-01-01T00:30:00+01:00' };
  assert.equal(g.fmtInstant('2026-12-30T10:00:00+01:00', capodanno), '30/12/2026, 10:00');
  assert.equal(g.fmtInstant('2026-12-31T10:00:00+01:00', capodanno), 'ieri alle 10:00',
    'il giorno prima attraversa l’anno');
});

test('ieri attraversa il mese e il cambio d’ora senza toccare un fuso', () => {
  const g = carica();
  assert.equal(g.fmtInstant('2026-02-28T09:00:00+01:00',
    { fuso: 'Europe/Rome', adesso: '2026-03-01T09:00:00+01:00' }), 'ieri alle 09:00');
  assert.equal(g.fmtInstant('2026-10-24T09:00:00+02:00',
    { fuso: 'Europe/Rome', adesso: '2026-10-25T09:00:00+01:00' }), 'ieri alle 09:00');
});

test('l’articolo si accorda, e davanti a oggi e ieri cade', () => {
  const g = carica();
  const oggi = '2026-10-14T00:30:00+02:00';
  const prima = '2026-10-02T08:05:00+02:00';
  assert.equal(g.fmtInstant(oggi, OROLOGIO, 'il'), 'oggi alle 00:30');
  assert.equal(g.fmtInstant(prima, OROLOGIO, 'il'), 'il 02/10, 08:05');
  assert.equal(g.fmtInstant(oggi, OROLOGIO, 'del'), 'di oggi alle 00:30');
  assert.equal(g.fmtInstant(prima, OROLOGIO, 'del'), 'del 02/10, 08:05');
  assert.equal(g.fmtInstant(oggi, OROLOGIO, 'dal'), 'da oggi alle 00:30');
  assert.equal(g.fmtInstant(prima, OROLOGIO, 'dal'), 'dal 02/10, 08:05');
});

test('senza orologio l’istante esce intero, con l’anno: non sa che giorno e’ oggi', () => {
  const g = carica();
  assert.equal(g.fmtInstant('2026-10-14T00:30:00+02:00', null), '14/10/2026, 00:30');
});

test('cio’ che non e’ un istante con l’offset non si mostra: niente Invalid Date', () => {
  const g = carica();
  for (const v of [null, undefined, '', 1791000000, '2026-10-14T00:30:00', 'mai']) {
    assert.equal(g.fmtInstant(v, OROLOGIO), '', String(v));
    assert.equal(g.fmtHour(v), '', String(v));
    assert.equal(g.fmtDay(v, true), '', String(v));
  }
});

test('le due date senza ora dell’osservatore', () => {
  const g = carica();
  assert.equal(g.fmtDay('2026-10-14T00:30:00+02:00', true), '14/10/2026');
  assert.equal(g.fmtDay('2026-10-14T00:30:00+02:00'), '14/10');
});

test('il browser in un altro fuso: una riga sola sotto il titolo, col nome del fuso', () => {
  const g = carica();
  const titolo = document.querySelector('.page-title');
  g.clockHint(titolo, OROLOGIO, ['2026-10-12T14:30:00+02:00']);
  g.clockHint(titolo, OROLOGIO, ['2026-10-12T14:30:00+02:00']);
  const righe = document.querySelectorAll('#clock-hint');
  assert.equal(righe.length, 1, 'una pagina che ridisegna non la scrive due volte');
  assert.equal(righe[0].textContent,
    'Gli orari sono quelli della casa (Europe/Rome), non del tuo dispositivo.');
  assert.equal(righe[0].className, 'field-hint', 'testo secondario, non un banner');
  assert.equal(titolo.nextSibling, righe[0], 'sotto il titolo');
});

test('il browser nello stesso fuso della casa: nessuna riga', () => {
  const g = carica();
  const newYork = { fuso: 'America/New_York', adesso: '2026-10-13T19:00:00-04:00' };
  g.clockHint(document.querySelector('.page-title'), newYork, ['2026-07-01T10:00:00-04:00']);
  assert.equal(document.querySelector('#clock-hint'), null);
});

test('si confronta l’offset nell’istante mostrato, non il nome del fuso', () => {
  const g = carica();
  // Il 03/11/2026 New York e' gia' tornata all'ora solare (-05:00), e un
  // istante scritto con l'offset estivo -04:00 non e' piu' l'ora del browser:
  // stesso nome di fuso, offset diverso in quell'istante.
  const casa = { fuso: 'America/New_York', adesso: '2026-10-13T19:00:00-04:00' };
  g.clockHint(document.querySelector('.page-title'), casa, ['2026-11-03T10:00:00-04:00']);
  assert.ok(document.querySelector('#clock-hint'),
    'un offset diverso in un istante mostrato basta, anche se adesso coincide');
});
