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

test('il catalogo TOOLS espone i due tool di diagnosi', () => {
  loadScripts(['config/templates.js']);

  const voci = globalThis.TOOLS;
  for (const id of ['get_logbook', 'render_template']) {
    const voce = voci.find((t) => t.id === id);
    assert.ok(voce, `${id} manca dal catalogo TOOLS della UI`);
    assert.equal(voce.label, id);
    assert.ok(voce.desc && voce.desc.length > 0, 'la checkbox va etichettata per l\'utente');
  }

  // render_template e' concedibile SOLO da qui, esplicitamente, a un bot di
  // chat: non e' fra i tool degli agenti autonomi (EVALUATION_ONLY_TOOLS) ne'
  // fra quelli del gateway MCP. Se sparisse da questo catalogo diventerebbe
  // irraggiungibile del tutto.
  const tpl = voci.find((t) => t.id === 'render_template');
  assert.ok(/chat/i.test(tpl.desc), 'la descrizione deve dire che è per i bot di chat');
});
