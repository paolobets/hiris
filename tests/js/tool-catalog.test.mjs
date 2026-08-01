import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Il catalogo TOOLS di config/templates.js alimenta le checkbox dei permessi
   (HirisEditorKit.checkGroup): un tool assente qui non e' concedibile a nessun
   bot dalla UI, quindi resta irraggiungibile anche se registrato ovunque
   altrove nel backend. La registrazione di un tool tocca nove punti diversi:
   asserire il NOME in ciascuno e' l'unica difesa contro la rimozione
   silenziosa (il gemello Python e' tests/test_advisory_tool_registered.py). */

test('il catalogo TOOLS espone get_advisories con etichetta e descrizione', () => {
  loadScripts(['config/templates.js']);

  const voci = globalThis.TOOLS;
  assert.ok(Array.isArray(voci), 'templates.js deve esporre il catalogo TOOLS');

  const voce = voci.find((t) => t.id === 'get_advisories');
  assert.ok(voce, 'get_advisories manca dal catalogo TOOLS della UI');
  assert.equal(voce.label, 'get_advisories');
  assert.ok(voce.desc && voce.desc.length > 0, 'la checkbox va etichettata per l\'utente');

  // Gli id devono essere unici: un duplicato produrrebbe due checkbox per lo
  // stesso permesso, con la seconda che sovrascrive la prima.
  const ids = voci.map((t) => t.id);
  assert.equal(new Set(ids).size, ids.length);
});
