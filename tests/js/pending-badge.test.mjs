import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Il pallino delle due voci esecutive.
 *
 * Le due prove che portano peso sono «su errore non compare» e «zero non
 * compare», ed esistono perche' un pallino qui c'e' gia' stato ed e' morto.
 * Quello contava le segnalazioni del Brain leggendo una rotta uscita con la
 * fetta E3, e mostrava `0` quando quella rotta rispondeva 404: la lapide
 * sta in `hiris-config.css`, dove vivevano le sue quattro regole
 * `.nav-badge`. Non era inutile -- era peggio: diceva «non c'e' niente da
 * guardare» quando la verita' era «non lo so».
 *
 * Mutazioni che queste prove devono uccidere:
 *   1. un `catch` che scrive `0` invece di nascondere il pallino;
 *   2. un ramo che lo dipinge anche quando il numero e' zero;
 *   3. un secondo giro fallito che lascia acceso il numero del giro prima --
 *      il caso vero del ritorno sulla finestra con la rete caduta.
 *
 * L'HTML qui sotto e' ridotto alle due voci di menu: al pallino non serve
 * altro, e un finto piu' grande nasconderebbe che il suo unico aggancio
 * sono i due `data-badge`. */

const HTML = '<!doctype html><body>'
  + '<a id="v-agenda" data-badge="agenda"><span>Impegni</span></a>'
  + '<a id="v-cost" data-badge="constructions"><span>Proposte</span></a>'
  + '</body>';

function rispostaCon(corpo) {
  return () => Promise.resolve({
    ok: true, status: 200, json: () => Promise.resolve(corpo),
  });
}

async function monta(fetchFinto) {
  const ctx = loadScripts(['pending-badge.js'], { html: HTML });
  ctx.window.fetch = fetchFinto;
  await ctx.window.HirisPendingBadge.mount();
  await tick(0);
  return ctx;
}

function pallino(ctx, voce) {
  const host = ctx.document.querySelector('[data-badge="' + voce + '"]');
  return host && host.querySelector('.nav-badge');
}

test('dipinge i due numeri sulle due voci', async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 2, constructions_pending: 4 }));

  assert.equal(pallino(ctx, 'agenda').textContent, '2');
  assert.equal(pallino(ctx, 'constructions').textContent, '4');
});

test('il numero ha un nome: sotto i 1024px le etichette spariscono', async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 3, constructions_pending: 1 }));

  /* La side-nav si stringe a 64px e resta la sola icona: un numero nudo, li',
     non si capirebbe ne' col mouse ne' con uno screen reader. */
  const p = pallino(ctx, 'agenda');
  assert.equal(p.getAttribute('title'), '3 in attesa');
  assert.equal(p.getAttribute('aria-label'), '3 in attesa');
});

test("su 503 il pallino non compare -- «non lo so» non e' «non c'e' niente»", async () => {
  const ctx = await monta(() => Promise.resolve({
    ok: false, status: 503, json: () => Promise.resolve({ error: 'archivio non disponibile' }),
  }));

  assert.equal(pallino(ctx, 'agenda'), null);
  assert.equal(pallino(ctx, 'constructions'), null);
});

test('su errore di rete il pallino non compare', async () => {
  const ctx = await monta(() => Promise.reject(new Error('rete giu')));

  assert.equal(pallino(ctx, 'agenda'), null);
  assert.equal(pallino(ctx, 'constructions'), null);
});

test("zero non compare: zero non e' una notizia", async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 0, constructions_pending: 0 }));

  assert.equal(pallino(ctx, 'agenda'), null);
  assert.equal(pallino(ctx, 'constructions'), null);
});

test('una chiave che manca si comporta come un errore, non come uno zero', async () => {
  /* Se la rotta cambiasse sotto e smettesse di mandare `agenda_unread`, un
     controllo scritto come `n > 0` lo leggerebbe `undefined > 0` = falso e
     spegnerebbe il pallino in silenzio -- cioe' direbbe «non c'e' niente».
     E' lo stesso difetto del badge morto con un'altra provenienza. */
  const ctx = await monta(rispostaCon({ constructions_pending: 4 }));

  assert.equal(pallino(ctx, 'agenda'), null);
  assert.equal(pallino(ctx, 'constructions').textContent, '4');
});

test('un secondo giro fallito SPEGNE il numero acceso prima', async () => {
  /* Il caso vero: il pallino e' acceso, l'utente torna sulla finestra, la
     rete e' caduta. Un numero vecchio lasciato li' e' di nuovo un numero che
     mente -- stavolta sul quando. */
  let giro = 0;
  const ctx = await monta(() => {
    giro += 1;
    return giro === 1
      ? Promise.resolve({ ok: true, status: 200,
                          json: () => Promise.resolve({ agenda_unread: 7, constructions_pending: 1 }) })
      : Promise.reject(new Error('rete giu'));
  });
  assert.equal(pallino(ctx, 'agenda').textContent, '7');

  await ctx.window.HirisPendingBadge.refresh();
  await tick(0);

  assert.equal(pallino(ctx, 'agenda'), null);
  assert.equal(pallino(ctx, 'constructions'), null);
});

test('due giri di seguito non lasciano due pallini sulla stessa voce', async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 2, constructions_pending: 1 }));
  await ctx.window.HirisPendingBadge.refresh();
  await tick(0);

  const host = ctx.document.querySelector('[data-badge="agenda"]');
  assert.equal(host.querySelectorAll('.nav-badge').length, 1);
});
