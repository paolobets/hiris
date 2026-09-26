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
  + '<a id="v-cost" data-badge="constructions" data-builder-only hidden><span>Proposte</span></a>'
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
  /* La versione precedente di questa prova uccideva ZERO mutazioni: passava
     identica con e senza la guardia `typeof`, perche' pretendeva soltanto che
     il pallino degli Impegni fosse spento -- cosa che accade in entrambi i
     casi -- e per di piu' pretendeva `constructions` ACCESO, che e' il
     contrario di «si comporta come un errore».
     «Come un errore» ha due segni osservabili, e li si chiedono tutti e due:
     TUTTI E DUE i pallini spenti (non uno spento e l'altro acceso, che
     racconterebbe una risposta capita a meta') e la riga nel log, perche' una
     rotta che ha smesso di mandare una chiave e' un guasto da leggere, non un
     silenzio. Senza il `throw` in `pending-badge.js` questa prova e' rossa su
     entrambi. */
  const avvisi = [];
  const warnVero = console.warn;
  console.warn = function () { avvisi.push([].slice.call(arguments)); };
  try {
    const ctx = await monta(rispostaCon({ constructions_pending: 4 }));

    assert.equal(pallino(ctx, 'agenda'), null);
    assert.equal(pallino(ctx, 'constructions'), null,
      "anche la voce la cui chiave e' arrivata resta spenta: la risposta non si e' capita");
  } finally {
    console.warn = warnVero;
  }
  assert.equal(avvisi.length, 1, 'il guasto lascia una riga nel log, non un silenzio');
  assert.match(String(avvisi[0][0]), /pallino/);
  assert.match(String(avvisi[0][1]), /agenda_unread/,
    'e la riga dice QUALE chiave mancava, altrimenti non serve a chi la legge');
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

test('PIN: una terza chiave nella risposta non fa scattare il controllo stretto', async () => {
  /* security-constraints «NOT pinned» 13: il controllo delle chiavi di
     `refresh` e' stretto su cio' che MANCA, e una chiave in piu' -- quella
     che dice se chi guarda puo' costruire, fetta «il seguito delle chat
     divise» -- non deve spegnere i pallini come se fosse un guasto. */
  const ctx = await monta(rispostaCon({ agenda_unread: 2, constructions_pending: 4, can_build: true }));

  assert.equal(pallino(ctx, 'agenda').textContent, '2');
  assert.equal(pallino(ctx, 'constructions').textContent, '4');
});

/* ── La voce «Proposte» e' di chi costruisce (spec 2026-09-26 §3) ──────
   La decide il server a ogni risposta di `GET /api/pending` (`can_build`),
   non un ruolo indovinato dal browser. Mutazioni ESEGUITE: svuotare il
   ciclo di `applyBuilder` -- rosse quattro prove di questo file;
   `dati.can_build !== false` al posto di `=== true` -- rossa la terza. */

function voceProposte(ctx) {
  return ctx.document.querySelector('[data-badge="constructions"]');
}

test('chi non costruisce non vede la voce «Proposte»', async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 1, constructions_pending: 0, can_build: false }));

  assert.equal(voceProposte(ctx).hidden, true);
  assert.equal(pallino(ctx, 'agenda').textContent, '1', 'gli Impegni restano di tutti');
});

test('la voce si decide a OGNI risposta, non una volta sola', async () => {
  let giro = 0;
  const ctx = await monta(() => {
    giro += 1;
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(
      { agenda_unread: 0, constructions_pending: giro === 1 ? 3 : 0, can_build: giro === 1 }) });
  });
  assert.equal(voceProposte(ctx).hidden, false, 'al primo giro chi guarda costruisce');

  await ctx.window.HirisPendingBadge.refresh();
  await tick(0);

  assert.equal(voceProposte(ctx).hidden, true, 'al secondo non piu\': la voce sparisce');
});

test('una risposta che non dice can_build non e\' un permesso', async () => {
  const ctx = await monta(rispostaCon({ agenda_unread: 0, constructions_pending: 2 }));

  assert.equal(voceProposte(ctx).hidden, true);
});

test('un errore non tocca la voce: non e\' una risposta', async () => {
  let giro = 0;
  const ctx = await monta(() => {
    giro += 1;
    return giro === 1
      ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(
        { agenda_unread: 0, constructions_pending: 1, can_build: true }) })
      : Promise.reject(new Error('rete giu'));
  });

  await ctx.window.HirisPendingBadge.refresh();
  await tick(0);

  assert.equal(voceProposte(ctx).hidden, false);
});

/* ── Il ricordo dell'ultima risposta (fix round 1 del Task 4) ─────────
   Senza, la voce compariva a un amministratore un giro di rete dopo ogni
   apertura, e mai se la prima risposta falliva. Mutazioni ESEGUITE: togliere
   `applyBuilder(remembered())` da `mount` -- rossa la prima; togliere
   `remember(puo)` -- rossa la seconda; togliere il try/catch di
   `remembered` -- rossa la terza. */

function montaSenzaRisposta(prima) {
  const ctx = loadScripts(['pending-badge.js'], { html: HTML });
  if (prima) prima(ctx);
  ctx.window.fetch = () => new Promise(() => {});
  ctx.window.HirisPendingBadge.mount();
  return ctx;
}

test('un «può costruire» ricordato mostra la voce SUBITO, prima della risposta', () => {
  const ctx = montaSenzaRisposta((c) => c.window.localStorage.setItem('hiris.can_build', '1'));

  assert.equal(voceProposte(ctx).hidden, false);
  assert.equal(ctx.window.HirisPendingBadge.canBuild(), true);
});

test('la risposta del server vince sul ricordo, e diventa il ricordo', async () => {
  const ctx = loadScripts(['pending-badge.js'], { html: HTML });
  ctx.window.localStorage.setItem('hiris.can_build', '1');
  ctx.window.fetch = rispostaCon({ agenda_unread: 0, constructions_pending: 0, can_build: false });
  await ctx.window.HirisPendingBadge.mount();
  await tick(0);

  assert.equal(voceProposte(ctx).hidden, true);
  assert.equal(ctx.window.localStorage.getItem('hiris.can_build'), '0');
});

test('uno storage che solleva non rompe niente: si parte nascosti e la risposta decide', async () => {
  const ctx = loadScripts(['pending-badge.js'], { html: HTML });
  Object.defineProperty(ctx.window, 'localStorage', {
    configurable: true, get() { throw new Error('SecurityError'); },
  });
  ctx.window.fetch = rispostaCon({ agenda_unread: 0, constructions_pending: 2, can_build: true });
  const montaggio = ctx.window.HirisPendingBadge.mount();
  assert.equal(voceProposte(ctx).hidden, true, 'senza ricordo si parte nascosti');
  await montaggio;
  await tick(0);

  assert.equal(voceProposte(ctx).hidden, false);
  assert.equal(pallino(ctx, 'constructions').textContent, '2');
});

test('senza ricordo si parte nascosti', () => {
  const ctx = montaSenzaRisposta();

  assert.equal(voceProposte(ctx).hidden, true);
});
