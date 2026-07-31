import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Issue live-verify #1, increment 2 — "nuovo dall'ultima visita".
   Le notifiche portano su HIRIS ma HA non dice QUALE notifica hai toccato:
   invece di un mapping fragile notifica->item, la dashboard evidenzia ogni item
   del feed piu' recente dell'ultima apertura. Qui pinniamo la logica pura
   (DOM + confronto timestamp ISO) via il seam window.HirisDashboard._feed,
   senza montare l'intera dashboard ne' dipendere da localStorage. */

function feed() {
  const { document } = loadScripts(['config/dashboard.js']);
  return { document, api: globalThis.HirisDashboard._feed };
}

function row(document, ts) {
  const el = document.createElement('div');
  el.className = 'dl-row';
  el.setAttribute('data-ts', ts);
  document.body.appendChild(el);
  return el;
}

test("markNew evidenzia solo gli item piu' recenti dell'ultima visita", () => {
  const { document, api } = feed();
  const older = row(document, '2026-07-31T09:00:00');
  const same = row(document, '2026-07-31T10:00:00');
  const newer = row(document, '2026-07-31T11:00:00');

  api.setLastSeen('2026-07-31T10:00:00');
  api.markNew(document.body);

  assert.equal(newer.classList.contains('feed-new'), true, "il piu' recente e' nuovo");
  assert.equal(older.classList.contains('feed-new'), false, "il vecchio non e' nuovo");
  assert.equal(same.classList.contains('feed-new'), false, "uguale al last-seen NON e' nuovo (confronto stretto)");
});

test("prima visita (last-seen vuoto) non evidenzia nulla", () => {
  const { document, api } = feed();
  const a = row(document, '2026-07-31T09:00:00');
  const b = row(document, '2026-07-31T11:00:00');

  api.setLastSeen('');   // prima visita
  api.markNew(document.body);

  assert.equal(a.classList.contains('feed-new'), false);
  assert.equal(b.classList.contains('feed-new'), false);
});

test("un item senza data-ts non viene mai evidenziato", () => {
  const { document, api } = feed();
  const noTs = document.createElement('div');
  noTs.className = 'dl-row';           // niente data-ts
  document.body.appendChild(noTs);

  api.setLastSeen('2026-07-31T00:00:00');
  api.markNew(document.body);

  assert.equal(noTs.classList.contains('feed-new'), false);
});

test("finalize scrolla sull'item nuovo piu' recente, non sugli altri", () => {
  const { document, api } = feed();
  const a = row(document, '2026-07-31T09:00:00'); a.classList.add('feed-new');
  const b = row(document, '2026-07-31T12:00:00'); b.classList.add('feed-new');
  let scrolledA = 0, scrolledB = 0;
  a.scrollIntoView = () => { scrolledA++; };
  b.scrollIntoView = () => { scrolledB++; };

  api.finalize();

  assert.equal(scrolledB, 1, "scrolla sul piu' recente");
  assert.equal(scrolledA, 0, "non scrolla sul meno recente");
});
