import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, STATIC_VIVO, tick } from './helpers/dom.mjs';

/* Collaudo usabilita' 3.22.3, rilievo C: tre parole nostre erano visibili
 * al proprietario -- misurate in
 * .superpowers/sdd/collaudo-3.22/misure-del-controllore.md (U4):
 *   - `nucleo`: cinque stringhe in dashboard.js;
 *   - «Forza»: etichetta di campo, memory-route.js:208;
 *   - «Grandezza»: etichetta di campo, memory-route.js:209.
 * Il nome interno (`nucleo`/`forza`/`grandezza`, in docs/GLOSSARIO.md e
 * nelle chiavi del PATCH/REMEMBER_TOOL_DEF) NON cambia -- cambia solo cio'
 * che si legge sullo schermo. «Categorie» resta com'era: sta accanto a
 * «Etichette»/«Integrazioni» (il vocabolario di Home Assistant), non e'
 * parola nostra -- questo file lo pinna anche in negativo, cosi' un domani
 * che la cambiasse per errore diventa visibile.
 *
 * Mutazione che questa prova deve uccidere: rimettere «Forza»/«Grandezza»/
 * «nucleo» al posto delle parole nuove -- lo stato di partenza. */

test('dashboard.js: "nucleo" non compare piu\' in nessuna stringa visibile', async () => {
  const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';
  const ctx = loadScripts(['config/dashboard.js'], { html: HTML });

  const NUCLEO_VUOTO = { text: '', summary: { chars: 0, truncated: false, excluded_memories: 0, notices: [] } };
  const CASA_VUOTA = {
    anagrafe_letta_il: null, non_disponibili: null, conteggi: {}, piani: [],
    comportamento: { letto_il: null, conteggi: {}, senza_corpo: 0, problemi: [], corpi_non_letti: {}, voci: [] },
    plance: { lette_il: null, non_disponibili: null, voci: [] },
  };
  ctx.window.fetch = (url) => Promise.resolve({
    ok: true, status: 200,
    json: () => Promise.resolve(String(url).indexOf('api/briefing') !== -1 ? NUCLEO_VUOTO : CASA_VUOTA),
  });

  await ctx.window.HirisDashboard.mount();
  await tick(0);
  const testo = ctx.document.getElementById('route-outlet').textContent;

  assert.doesNotMatch(testo, /nucleo/i,
    'nessuna parola "nucleo" deve restare visibile sullo schermo (il nome interno resta nel codice)');
});

test('dashboard.js: le cinque stringhe misurate non dicono piu\' "nucleo"', () => {
  // Le cinque stringhe VISIBILI misurate dal controllore (righe 371, 379,
  // 393, 395, 457-458 di prima della cura): si controllano per il testo
  // esatto che le sostituisce, non con un parser di stringhe generico --
  // i commenti di questo file usano l'apostrofo dritto anche in prosa
  // ("usabilita'"), che confonderebbe un `matchAll(/'([^']*)'/g)` ingenuo.
  const src = readFileSync(join(STATIC_VIVO, 'config', 'dashboard.js'), 'utf8');

  assert.match(src, /'Cosa vede il modello a ogni turno'/g);
  assert.match(src, /'Nessuna lacuna dichiarata\.'/);
  assert.match(src, /'di questo testo'/);
  assert.match(src, /'fuori da questo testo'/);
  assert.match(src, /'Non è stato possibile leggere ciò che il modello vede\./);

  assert.doesNotMatch(src, /'Il nucleo, come lo vede il modello'/);
  assert.doesNotMatch(src, /'Il nucleo non dichiara nessuna lacuna\.'/);
  assert.doesNotMatch(src, /'del nucleo'/);
  assert.doesNotMatch(src, /'fuori dal nucleo'/);
  assert.doesNotMatch(src, /'Non è stato possibile leggere il nucleo\./);
});

test('memory-route.js: le etichette di campo sono "Natura" e "Cosa misura", non piu\' "Forza"/"Grandezza"', () => {
  const src = readFileSync(join(STATIC_VIVO, 'config', 'memory-route.js'), 'utf8');

  assert.match(src, /field\('Natura', modalitySelect\)/,
    'l\'etichetta del campo forza deve leggersi «Natura»');
  assert.match(src, /field\('Cosa misura \(es\. temperature, humidity/,
    'l\'etichetta del campo grandezza deve leggersi «Cosa misura», con l\'esempio HA che gia\' c\'era');
  assert.doesNotMatch(src, /field\('Forza'/, 'la vecchia etichetta «Forza» non deve restare');
  assert.doesNotMatch(src, /field\('Grandezza /, 'la vecchia etichetta «Grandezza» non deve restare');
});

test('memory-route.js: la chiave interna `forza`/`grandezza` (PATCH, docs/GLOSSARIO.md) non cambia', () => {
  // Il capitolato vieta di rinominare identificatori/chiavi API: solo il
  // testo sullo schermo cambia. Le chiavi del corpo PATCH restano intatte.
  const src = readFileSync(join(STATIC_VIVO, 'config', 'memory-route.js'), 'utf8');
  assert.match(src, /body\.forza = nModality/);
  assert.match(src, /body\.grandezza = nGrandezza/);
  assert.match(src, /r\.forza/);
  assert.match(src, /r\.grandezza/);
});

test('«Categorie» resta com\'era: e\' il vocabolario di Home Assistant, non una parola nostra', () => {
  const dashboard = readFileSync(join(STATIC_VIVO, 'config', 'dashboard.js'), 'utf8');
  const tree = readFileSync(join(STATIC_VIVO, 'config', 'tree-route.js'), 'utf8');

  assert.match(dashboard, /categorie: 'Categorie'/);
  assert.match(tree, /categorie: 'Categorie'/);
  // Sta ACCANTO a Etichette/Integrazioni nella stessa riga -- e' la stessa
  // terna del vocabolario di HA, non un'invenzione del prodotto.
  assert.match(tree, /etichette: 'Etichette', categorie: 'Categorie', integrazioni: 'Integrazioni'/);
});
