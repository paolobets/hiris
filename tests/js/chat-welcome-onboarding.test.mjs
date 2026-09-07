import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, STATIC_VIVO } from './helpers/dom.mjs';

/* Collaudo usabilita' 3.22.1, rilievo 1: le quattro pastiglie dello stato
 * vuoto della chat («Stato casa», «Temperatura camere», «Cosa fa la casa da
 * sola», «Cosa ricordi di me») non erano le domande che il proprietario fa
 * davvero -- misurato la stessa mattina del collaudo: «Quali sono i miei
 * prossimi appuntamenti?», «Quante luci ho in casa e quante sono accese
 * adesso?», «Cosa non va in casa in questo momento?». Nessuna delle tre era
 * una pastiglia.
 *
 * Si legge il guscio VERO (`STATIC_VIVO/index.html`), non un finto: il fatto
 * sorvegliato e' com'e' scritto quel file (stesso principio di
 * nav-esecutiva.test.mjs). Un finto direbbe solo che il test sa copiarsi.
 *
 * Mutazione che questi test devono uccidere: ripristinare le due pastiglie
 * vecchie («Stato casa», «Temperatura camere») al posto delle due nuove, e
 * togliere il rigo di onboarding -- cioe' esattamente lo stato da cui si
 * parte. */

function welcomeDom() {
  const html = readFileSync(join(STATIC_VIVO, 'index.html'), 'utf8');
  return loadScripts([], { html });
}

function chipTexts(document) {
  return Array.from(document.querySelectorAll('#welcome .quick-chips .chip'))
    .map((b) => b.getAttribute('data-quick'));
}

test('le pastiglie sono le domande misurate, non quelle vecchie', () => {
  const { document } = welcomeDom();
  const testi = chipTexts(document);

  assert.equal(testi.length, 4, 'restano quattro pastiglie');
  assert.ok(testi.includes('Cosa non va in casa?'),
    'manca la pastiglia sulla sezione che il nucleo gia\' scrive (briefing.py, "Cosa non va in casa")');
  assert.ok(testi.includes('Cosa ho in agenda?'),
    'manca la pastiglia sui calendari (mcp__hiris__calendar)');
  assert.ok(!testi.includes('Stato casa'),
    'la vecchia pastiglia "Stato casa" doveva sparire: non era una domanda misurata');
  assert.ok(!testi.includes('Temperatura camere'),
    'la vecchia pastiglia "Temperatura camere" doveva sparire: non era una domanda misurata');
});

test('le due pastiglie che funzionavano gia\' restano', () => {
  const { document } = welcomeDom();
  const testi = chipTexts(document);
  assert.ok(testi.includes('Cosa fa la casa da sola'),
    'mappa sulle automazioni vere -- va tenuta');
  assert.ok(testi.includes('Cosa ricordi di me'),
    'mappa sulla Memoria vera -- va tenuta');
});

test('ogni pastiglia manda in chat esattamente il testo che mostra (data-quick == testo visibile, glifo escluso)', () => {
  const { document } = welcomeDom();
  document.querySelectorAll('#welcome .quick-chips .chip').forEach((b) => {
    const glifo = b.querySelector('.chip-glyph');
    const visibile = (glifo ? b.textContent.replace(glifo.textContent, '') : b.textContent).trim();
    assert.equal(visibile, b.getAttribute('data-quick'),
      'chat/send.js manda data-quick in chat: se diverge dal testo mostrato, chi clicca non sa cosa sta chiedendo davvero');
  });
});

test('la pagina di partenza dice anche cosa sa fare, non solo "come posso aiutarti?"', () => {
  const { document } = welcomeDom();
  const p = document.querySelector('#welcome > p');
  assert.ok(p, 'manca il rigo di onboarding sotto il saluto -- le pastiglie restano l\'unica spiegazione');
  const testo = p.textContent.trim();
  assert.ok(testo.length > 0, 'il rigo di onboarding non puo\' essere vuoto');
  // Non promette cio' che il prodotto non fa (catalogo strumenti vero,
  // agent/prompts.py::_GUIDE_WITH_TOOLS): legge la casa e i calendari,
  // sa delle automazioni, accende/spegne, ricorda.
  assert.match(testo, /calendari/i, 'il catalogo include mcp__hiris__calendar: il rigo deve nominarlo');
  assert.match(testo, /automazion/i, 'il catalogo include related/automation_trace: il rigo deve nominarle');
  assert.match(testo, /ricord/i, 'il catalogo include remember/fetch: il rigo deve nominare la memoria');
});
