import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { copiaIstantanea, staticSnapshotDir, STATIC_VIVO } from './helpers/dom.mjs';

/* m5 (review finale): `loadScripts()` (helpers/dom.mjs) e i test di
   cablaggio di B8 (chat-build-check-wiring.test.mjs) leggevano i sorgenti
   di PRODUZIONE dal filesystem al momento della corsa -- senza istantanea,
   una scrittura concorrente in `static/` durante l'esecuzione della suite
   (un editor aperto, un altro agente, un `git checkout`) puo' colorare
   quella corsa e non la successiva: esattamente la causa piu' probabile del
   fallimento transitorio di B8 discusso nella review finale.

   `copiaIstantanea()` e' il rimedio: una copia vera, non un riferimento
   allo stesso percorso. Qui si prova la proprieta' che conta -- una
   scrittura sulla SORGENTE dopo la copia non deve mai toccare la copia --
   su un albero finto in tmp_path, MAI sul repo vero: non e' accettabile
   scrivere nell'albero reale solo per provare un test. */
test('copiaIstantanea produce una copia indipendente: una scrittura sulla sorgente dopo non tocca la copia', (t) => {
  const vivo = mkdtempSync(join(tmpdir(), 'hiris-m5-vivo-'));
  // m1 (ri-review): `copiaIstantanea(vivo)` sotto e' tracciata e ripulita
  // dall'exit handler di dom.mjs, ma questo `vivo` e' creato con
  // mkdtempSync DIRETTAMENTE dal test (non passa da copiaIstantanea): senza
  // questo t.after(), resterebbe anche lui in %TEMP% per sempre.
  t.after(() => rmSync(vivo, { recursive: true, force: true }));
  mkdirSync(join(vivo, 'chat'));
  writeFileSync(join(vivo, 'chat', 'main.js'), "console.log('v1')");

  const istantanea = copiaIstantanea(vivo);
  const primaLettura = readFileSync(join(istantanea, 'chat', 'main.js'), 'utf8');
  assert.equal(primaLettura, "console.log('v1')", 'precondizione: la copia riflette la sorgente al momento della copia');

  // La scrittura concorrente: qualcosa cambia l'albero VIVO dopo la copia --
  // esattamente lo scenario che ha reso instabili i test di B8.
  writeFileSync(join(vivo, 'chat', 'main.js'), "console.log('v2 -- scrittura concorrente')");

  const dopoLaScritturaConcorrente = readFileSync(join(istantanea, 'chat', 'main.js'), 'utf8');
  assert.equal(dopoLaScritturaConcorrente, "console.log('v1')",
    "l'istantanea deve restare quella di quando e' stata presa, indipendente da cio' che succede " +
    "alla sorgente dopo -- se questo fallisce, copiaIstantanea() non sta copiando davvero " +
    "(es. restituisce lo stesso percorso della sorgente invece di una copia)");
});

/* m8 (ri-review): il test sopra prova solo che `copiaIstantanea()` SAPPIA
   copiare -- mai che `staticSnapshotDir()` (il singleton per-processo che
   `loadScripts()` e i test di cablaggio di B8 usano DAVVERO) sia collegato
   a quella proprieta'. Misurato: `staticSnapshotDir()` ridotta a
   `return STATIC` (il difetto che m5 esisteva per togliere, rimesso
   identico) lasciava 171/171 verdi -- nessun test se ne accorgeva. Qui si
   pinza il cablaggio dal lato che conta: il valore che `staticSnapshotDir()`
   restituisce DEVE essere una copia (percorso diverso da static/ vivo), non
   solo la funzione pura isolata saperlo fare. */
test("staticSnapshotDir() e' una copia isolata di static/, non l'albero vivo (m8, ri-review)", () => {
  const dir = staticSnapshotDir();
  assert.notEqual(dir, STATIC_VIVO,
    "staticSnapshotDir() deve restituire una COPIA (mkdtempSync), mai il percorso di static/ stesso " +
    "-- altrimenti loadScripts() e i test di cablaggio di B8 perdono la protezione da scritture " +
    "concorrenti che m5 esisteva per dare. Mutazione che uccide: ridurre staticSnapshotDir() a " +
    "`return STATIC`.");
  // La copia deve riflettere davvero il contenuto reale, non essere una
  // cartella vuota qualunque che per caso non e' STATIC_VIVO.
  const vivo = readFileSync(join(STATIC_VIVO, 'chat', 'main.js'), 'utf8');
  const copia = readFileSync(join(dir, 'chat', 'main.js'), 'utf8');
  assert.equal(copia, vivo, "la copia deve avere lo stesso contenuto dell'albero vivo");
});
