import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { fintoFetch, risposta, maiRisposta, svuotaSconosciuti } from './helpers/fetch.mjs';

/* Il finto `fetch` condiviso (T-03): le sue regole, e il cancello che lo
   rende l'unico. */

const QUI = dirname(fileURLToPath(import.meta.url));

test('una rotta e\' un percorso: combacia con la query e coi sotto-percorsi, non coi vicini di nome', async () => {
  const window = {};
  fintoFetch(window, { 'api/chat': { chi: 'chat' }, 'api/chat-settings': { chi: 'impostazioni' } });

  assert.equal((await (await window.fetch('api/chat?x=1')).json()).chi, 'chat');
  assert.equal((await (await window.fetch('api/chat/reply/7')).json()).chi, 'chat');
  assert.equal((await (await window.fetch('api/chat-settings')).json()).chi, 'impostazioni');
});

/* Il vicino di nome NON e' la rotta (N160-1, revisione giro 160): con la
   sola `api/chat` mappata, `api/chat-settings` si rifiuta come sconosciuto.
   Nella prova sopra le due rotte sono mappate entrambe, e vince la piu'
   lunga: li' un confronto per prefisso di stringa restava verde. Mutazione
   ESEGUITA (14/10/2026): `combacia` ridotto a `p.startsWith(rotta)` -- rossa
   qui, e solo qui. Si svuota a mano l'elenco degli sconosciuti (con
   `svuotaSconosciuti`), perche' qui lo sconosciuto e' voluto. */
test('una rotta non risponde al vicino di nome: con la sola api/chat, api/chat-settings e\' sconosciuto', async () => {
  const window = {};
  fintoFetch(window, { 'api/chat': { chi: 'chat' } });

  await assert.rejects(window.fetch('api/chat-settings'), /indirizzo sconosciuto GET api\/chat-settings/);
  assert.deepEqual(svuotaSconosciuti(), ['GET api/chat-settings']);
});

test('vince la rotta piu\' lunga, e quella col metodo su quella senza', async () => {
  const window = {};
  const chiamate = fintoFetch(window, {
    'api/chat': 'corta',
    'api/chat/reply': 'lunga',
    'POST api/chat': risposta('scritta', 201),
  });

  assert.equal(await (await window.fetch('api/chat/reply/1')).json(), 'lunga');
  assert.equal(await (await window.fetch('api/chat')).json(), 'corta');
  const scritta = await window.fetch('api/chat', { method: 'POST', body: '{}' });
  assert.equal(scritta.status, 201);
  assert.equal(await scritta.json(), 'scritta');
  assert.deepEqual(chiamate.map((c) => c.metodo + ' ' + c.url),
    ['GET api/chat/reply/1', 'GET api/chat', 'POST api/chat']);
  assert.equal(chiamate[2].corpo, '{}');
});

test('ok segue lo stato come nel fetch vero; una funzione puo\' sollevare o non rispondere mai', async () => {
  const window = {};
  let risolta = false;
  fintoFetch(window, {
    'api/rotta': () => risposta({ error: 'no' }, 503),
    'api/giu': () => { throw new Error('rete giu'); },
    'api/attesa': maiRisposta,
  });

  const rotta = await window.fetch('api/rotta');
  assert.equal(rotta.ok, false);
  assert.equal(rotta.status, 503);
  await assert.rejects(window.fetch('api/giu'), /rete giu/);
  window.fetch('api/attesa').then(() => { risolta = true; });
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(risolta, false);
});

/* La proprieta' che giustifica l'aiuto: un indirizzo sconosciuto fa fallire
   la prova che lo chiede. Si prova in un processo a parte, perche' qui
   farebbe fallire questa. La pagina finta INGHIOTTE l'errore della richiesta
   (`catch`), come fanno le pagine vere: e' il caso che il vecchio `stubFetch`
   non poteva vedere. Mutazione ESEGUITA (14/10/2026): tolto
   `afterEach(controlla)` da `helpers/fetch.mjs` -- rossa qui (la prova figlia
   passava). */
test('un indirizzo che nessuna rotta conosce fa fallire la prova, anche se la pagina inghiotte l\'errore', () => {
  const cartella = mkdtempSync(join(tmpdir(), 'hiris-fetch-finto-'));
  try {
    const aiuto = pathToFileURL(join(QUI, 'helpers', 'fetch.mjs')).href;
    const file = join(cartella, 'figlia.test.mjs');
    writeFileSync(file, [
      "import test from 'node:test';",
      `import { fintoFetch } from '${aiuto}';`,
      "test('chiede un indirizzo sbagliato', async () => {",
      "  const window = {};",
      "  fintoFetch(window, { 'api/giusta': {} });",
      "  await window.fetch('api/sbagliata').catch(() => null);",
      "});",
      "test('la sorella non ne risente', () => {});",
    ].join('\n'));
    // Il processo figlio non deve sapere di girare dentro `node --test`:
    // altrimenti salta i file (avviso «run() is being called recursively»).
    const ambiente = { ...process.env };
    delete ambiente.NODE_TEST_CONTEXT;
    const esito = spawnSync(process.execPath, ['--test', '--test-reporter=tap', file],
      { encoding: 'utf8', env: ambiente });
    const uscita = esito.stdout + esito.stderr;

    assert.notEqual(esito.status, 0, uscita);
    assert.match(uscita, /not ok \d+ - chiede un indirizzo sbagliato/);
    assert.match(uscita, /GET api\/sbagliata/);
    assert.match(uscita, /^ok \d+ - la sorella non ne risente/m);
  } finally {
    rmSync(cartella, { recursive: true, force: true });
  }
});

/* Il cancello: nessun file di prova si scrive il suo `fetch`. L'elenco dei
   file si chiede alla cartella, non si ricopia (I-0). Mutazione ESEGUITA
   (14/10/2026): un finto scritto a mano (assegnazione a `ctx.window.fetch`) rimesso in
   `tree-route.test.mjs` -- rossa, col file e la riga. */
test('nessuna prova assegna fetch da se\': passano tutte dal finto condiviso', () => {
  const assegna = /(?:globalThis|window|global)\.fetch\s*=[^=]|(?<![.\w])fetch\s*=[^=]/;
  const file = readdirSync(QUI).filter((n) => n.endsWith('.test.mjs'));
  const trovate = [];
  for (const nome of file) {
    readFileSync(join(QUI, nome), 'utf8').split('\n').forEach((riga, i) => {
      if (assegna.test(riga)) trovate.push(`${nome}:${i + 1}: ${riga.trim()}`);
    });
  }

  assert.ok(file.length >= 20, `solo ${file.length} file di prova: la derivazione si e' rotta`);
  assert.deepEqual(trovate, [], 'fetch scritto a mano:\n' + trovate.join('\n'));
});
