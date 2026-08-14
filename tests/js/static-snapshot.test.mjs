import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { copiaIstantanea } from './helpers/dom.mjs';

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
test('copiaIstantanea produce una copia indipendente: una scrittura sulla sorgente dopo non tocca la copia', () => {
  const vivo = mkdtempSync(join(tmpdir(), 'hiris-m5-vivo-'));
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
