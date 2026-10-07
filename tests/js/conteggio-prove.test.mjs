/* Il confronto del conteggio delle prove JS (BACKLOG, «Il conteggio instabile
 * di `npm test`», 07/10/2026): il reporter in helpers/conteggio-prove.mjs. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { contaPerFile, registra, resoconto, scese } from './helpers/conteggio-prove.mjs';

const QUI = dirname(fileURLToPath(import.meta.url));
const evento = (type, file, nesting = 0) => ({ type, data: { file: join(QUI, file), nesting } });

test('contaPerFile: conta per file le prove di primo livello, rosse comprese', () => {
  const conto = contaPerFile([
    evento('test:pass', 'a.test.mjs'),
    evento('test:fail', 'a.test.mjs'),
    evento('test:pass', 'a.test.mjs', 1),
    evento('test:pass', 'b.test.mjs'),
    evento('test:diagnostic', 'b.test.mjs'),
  ]);
  assert.deepEqual(conto, { 'tests/js/a.test.mjs': 2, 'tests/js/b.test.mjs': 1 });
});

test('resoconto: senza giro prima dice il totale e non ferma', () => {
  const r = resoconto(null, { 'tests/js/a.test.mjs': 3 });
  assert.equal(r.ferma, false);
  assert.match(r.testo, /prove JS raccolte: 3 \(nessun giro prima/);
});

test('resoconto: lo stesso conto, o di piu\', non ferma', () => {
  const prima = { 'tests/js/a.test.mjs': 3 };
  assert.equal(resoconto(prima, { 'tests/js/a.test.mjs': 3 }).ferma, false);
  assert.equal(resoconto(prima, { 'tests/js/a.test.mjs': 4, 'tests/js/b.test.mjs': 1 }).ferma, false);
});

test('resoconto: un file che porta meno prove ferma la corsa e si nomina', () => {
  const r = resoconto(
    { 'tests/js/a.test.mjs': 15, 'tests/js/b.test.mjs': 2 },
    { 'tests/js/a.test.mjs': 2, 'tests/js/b.test.mjs': 2 },
  );
  assert.equal(r.ferma, true);
  assert.match(r.testo, /tests\/js\/a\.test\.mjs: 2 invece di 15/);
  assert.doesNotMatch(r.testo, /b\.test\.mjs/);
});

test('scese: un file sparito dal giro conta come zero, anche se il totale sale', () => {
  const giu = scese(
    { 'tests/js/a.test.mjs': 2, 'tests/js/b.test.mjs': 1 },
    { 'tests/js/a.test.mjs': 9 },
  );
  assert.deepEqual(giu, [{ file: 'tests/js/b.test.mjs', prima: 1, adesso: 0 }]);
});

/* N75-1 (revisore, giro 75): se il conto che scende si salvasse, un
 * rilancio automatico spegnerebbe il confronto -- il secondo giro
 * confronterebbe con il conto gia' sceso e direbbe di si'. */
test('resoconto: un conto che scende non si salva, e il testo dice come accettarlo', () => {
  const r = resoconto({ 'tests/js/a.test.mjs': 15 }, { 'tests/js/a.test.mjs': 2 });
  assert.equal(r.salva, false);
  assert.equal(r.ferma, true);
  assert.match(r.testo, /HIRIS_PROVE_JS_OK=1/);
});

test('resoconto: con HIRIS_PROVE_JS_OK il conto che scende si accetta, si salva e non ferma', () => {
  const r = resoconto({ 'tests/js/a.test.mjs': 15 }, { 'tests/js/a.test.mjs': 2 }, { accetta: true });
  assert.equal(r.salva, true);
  assert.equal(r.ferma, false);
  assert.match(r.testo, /accettato/);
});

test('resoconto: un conto che non scende si salva sempre', () => {
  assert.equal(resoconto(null, { 'tests/js/a.test.mjs': 1 }).salva, true);
  assert.equal(resoconto({ 'tests/js/a.test.mjs': 1 }, { 'tests/js/a.test.mjs': 3 }).salva, true);
});

test('registra: il conto sceso non tocca la memoria, e il giro dopo lo segnala ancora', (t) => {
  const cartella = mkdtempSync(join(tmpdir(), 'hiris-conteggio-'));
  t.after(() => rmSync(cartella, { recursive: true, force: true }));
  const memoria = join(cartella, 'memoria.json');
  const intero = { 'tests/js/a.test.mjs': 15 };
  const sceso = { 'tests/js/a.test.mjs': 2 };
  assert.equal(registra(intero, { memoria }).ferma, false);
  assert.equal(registra(sceso, { memoria }).ferma, true);
  assert.equal(registra(sceso, { memoria }).ferma, true, 'il rilancio deve segnalarlo di nuovo');
  assert.deepEqual(JSON.parse(readFileSync(memoria, 'utf8')).per_file, intero);
  assert.equal(registra(sceso, { memoria, accetta: true }).ferma, false);
  assert.deepEqual(JSON.parse(readFileSync(memoria, 'utf8')).per_file, sceso);
  assert.equal(registra(sceso, { memoria }).ferma, false);
});
