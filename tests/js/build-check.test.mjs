import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* Task B8: `build-check.js` e' la meta' che mancava a `app["build_stamp"]`
   (server.py) -- il guscio dichiara da quale build e' nato con una
   `<meta name="hiris-build">` (server._inject_version), e questo modulo la
   confronta col `build` che GET api/health restituisce (gia' mostrato a
   schermo da chat/main.js, mai confrontato con niente prima di questo task).

   Il fatto misurato che ha aperto il task: un service worker di HA puo'
   servire un guscio HTML vecchio nonostante gli asset siano fingerprintati
   e mai in cache HTTP -- il guscio e' l'unico file che CONTIENE quegli hash,
   e chiede gli script vecchi per nome. Qui si prova, PRIMA di ogni altra
   cosa, che un guscio rimasto vecchio non possa ricaricare all'infinito: un
   anello di ricaricamenti sarebbe un guasto peggiore di quello che si sta
   chiudendo.

   `window.location.reload()` non e' overridabile in jsdom (proprieta' non
   scrivibile sul prototipo di Location -- verificato: un'assegnazione diretta
   fallisce in silenzio e la vera navigazione jsdom "Not implemented" parte
   comunque). Per questo il verificatore vero non chiama mai
   `window.location.reload` direttamente: passa da `_internal_reload`,
   esposto "for test only" come `_internal_routes` in config/router.js. */

function fixtureHtml(buildMeta) {
  const meta = buildMeta ? `<meta name="hiris-build" content="${buildMeta}">` : '';
  return `<!doctype html><head>${meta}</head><body></body>`;
}

function avvia(buildMeta) {
  const ctx = loadScripts(['build-check.js'], { html: fixtureHtml(buildMeta) });
  const reloadCalls = [];
  ctx.window.HirisBuildCheck._internal_reload = () => { reloadCalls.push(true); };
  try { ctx.window.sessionStorage.clear(); } catch {}
  return { ...ctx, reloadCalls };
}

test('build combaciano: nessun ricaricamento, nessuna striscia', () => {
  const { window, document, reloadCalls } = avvia('abc123');
  window.HirisBuildCheck.verifica('abc123');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('build diversi, prima volta: UN ricaricamento', () => {
  const { window, document, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222');
  assert.equal(reloadCalls.length, 1, 'deve ricaricare esattamente una volta');
  assert.equal(document.getElementById('hiris-build-mismatch'), null,
    'al primo disallineamento non si dichiara ancora nulla: si tenta il ricaricamento');
});

test('anti-anello: build ancora diversi dopo il ricaricamento (guscio rimasto vecchio) -- niente secondo ricaricamento, si dichiara', () => {
  const { window, document, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222'); // 1a chiamata: ricarica (simulata)
  window.HirisBuildCheck.verifica('nuovo222'); // 2a chiamata: il SW ha riservito lo stesso guscio vecchio

  assert.equal(reloadCalls.length, 1,
    'la guardia deve impedire un secondo ricaricamento: un anello sarebbe un guasto peggiore');
  const striscia = document.getElementById('hiris-build-mismatch');
  assert.notEqual(striscia, null, 'dopo il secondo disallineamento la striscia deve comparire');
  assert.equal(
    striscia.textContent,
    'questa interfaccia viene da un build diverso da quello in esecuzione ' +
    '(vecchio111 invece di nuovo222): svuota i dati del sito di Home Assistant',
    'la striscia deve avere il testo esatto, coi due valori dentro'
  );
});

test('la guardia si libera quando i build tornano a combaciare: un disallineamento futuro puo' + ' di nuovo ricaricare', () => {
  const { window, reloadCalls } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222'); // tentativo di ricaricamento, guardia impostata
  window.HirisBuildCheck.verifica('vecchio111'); // combaciano ora (es. server tornato indietro)
  assert.equal(reloadCalls.length, 1);

  const reloadCalls2 = [];
  window.HirisBuildCheck._internal_reload = () => { reloadCalls2.push(true); };
  window.HirisBuildCheck.verifica('build-nuovissimo'); // un NUOVO disallineamento
  assert.equal(reloadCalls2.length, 1, 'la guardia libera deve permettere un nuovo tentativo');
});

test('senza <meta name="hiris-build"> (guscio precedente a questo task): nessun ricaricamento, nessuna striscia -- non si puo\' confrontare', () => {
  const { window, document, reloadCalls } = avvia(null);
  window.HirisBuildCheck.verifica('qualsiasi');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('senza build remoto (es. api/health fallita): nessun ricaricamento, nessuna striscia', () => {
  const { window, document, reloadCalls } = avvia('abc123');
  window.HirisBuildCheck.verifica('');
  assert.equal(reloadCalls.length, 0);
  assert.equal(document.getElementById('hiris-build-mismatch'), null);
});

test('la striscia non duplica se verifica() la richiama con la guardia gia\' scattata', () => {
  const { window, document } = avvia('vecchio111');
  window.HirisBuildCheck.verifica('nuovo222');
  window.HirisBuildCheck.verifica('nuovo222');
  window.HirisBuildCheck.verifica('nuovo222');
  const strisce = document.querySelectorAll('#hiris-build-mismatch');
  assert.equal(strisce.length, 1);
});

// ---------------------------------------------------------------------------
// Review indipendente, rilievo Critico: la guardia deve REGGERE quando il
// Web Storage e' rotto, non degradare verso "nessuna guardia" (che vuol dire
// ricaricare a ogni chiamata, senza limite -- l'anello che il task doveva
// chiudere). L'invariante: non ricaricare mai se non si puo' provare di non
// averlo gia' fatto. Se la guardia non e' verificabile, si salta il
// ricaricamento e si mostra la striscia direttamente -- la striscia da sola
// e' comunque utile, un anello infinito non dice niente.
//
// I tre modi in cui la realta' rompe sessionStorage, tutti riprodotti:
//   1) setItem solleva mentre getItem funziona (quota superata, o policy);
//   2) l'accesso a `sessionStorage` STESSO solleva (Safari in navigazione
//      privata piu' vecchia, iframe con sandbox senza allow-storage-access-
//      by-user-activation -- e HIRIS gira DENTRO un iframe di Home Assistant);
//   3) la scrittura "sembra" riuscire (nessun throw) ma la rilettura torna
//      null o un valore diverso -- il piu' insidioso, perche' un try/catch
//      da solo non lo vede.
// In ognuno: zero ricaricamenti, striscia mostrata. E' l'inverso di quello
// che verrebbe istintivo (favorire il ricaricamento quando non si sa).
// ---------------------------------------------------------------------------

function avviaConStorageRotto(t, buildMeta, modo) {
  const ctx = loadScripts(['build-check.js'], { html: fixtureHtml(buildMeta) });
  const reloadCalls = [];
  ctx.window.HirisBuildCheck._internal_reload = () => { reloadCalls.push(true); };

  // m3 (review finale): i tre modi qui sotto avvelenano `globalThis.sessionStorage`
  // (`Object.defineProperty` con un getter che solleva, o una riassegnazione a un
  // oggetto finto) -- MAI attraverso `windowProxy`, quindi `mirroredKeys` di
  // `loadScripts` non lo traccia e il `dispose()`/cleanup automatico fra un test e
  // l'altro non lo tocca. Senza ripristino esplicito, solo una `loadScripts()`
  // SUCCESSIVA lo ripara (`define()` lo riscrive sempre) -- oggi innocuo perche'
  // questi sono gli ultimi test del file e `node --test` isola ogni file in un
  // processo, ma un test aggiunto in fondo erediterebbe lo storage rotto e
  // sembrerebbe un fallimento transitorio invece del difetto vero che e'.
  const sessionStorageVero = ctx.window.sessionStorage;
  t.after(() => {
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true, writable: true, value: sessionStorageVero,
    });
  });

  if (modo === 'setItem-solleva') {
    // getItem funziona (sempre null, nessuna guardia scritta finora);
    // setItem solleva -- comportamento documentato di Safari privato.
    const vero = ctx.window.sessionStorage;
    globalThis.sessionStorage = {
      getItem: vero.getItem.bind(vero),
      setItem() { throw new Error('QuotaExceededError (simulato)'); },
      removeItem: vero.removeItem.bind(vero),
      clear: vero.clear.bind(vero),
    };
  } else if (modo === 'accesso-solleva') {
    // L'identificatore `sessionStorage` stesso solleva alla lettura --
    // NESSUN metodo e' mai raggiungibile, nemmeno getItem.
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      get() { throw new Error('Web Storage bloccato (simulato, es. iframe sandboxed)'); },
    });
  } else if (modo === 'scrittura-fantasma') {
    // Ne' getItem ne' setItem sollevano MAI -- ma quello che si rilegge non
    // e' MAI quello che si e' appena scritto (torna sempre null).
    globalThis.sessionStorage = {
      getItem() { return null; },
      setItem() { /* "riesce" in silenzio, non persiste davvero */ },
      removeItem() {},
      clear() {},
    };
  } else {
    throw new Error('modo sconosciuto: ' + modo);
  }

  return { ...ctx, reloadCalls };
}

for (const modo of ['setItem-solleva', 'accesso-solleva', 'scrittura-fantasma']) {
  test(`Web Storage rotto (${modo}): zero ricaricamenti, striscia mostrata subito -- non si puo' provare che la guardia regga`, (t) => {
    const { document, reloadCalls } = avviaConStorageRotto(t, 'vecchio111', modo);

    // Nessuna guardia scritta con successo verificabile: MAI ricaricare,
    // quante volte si chiami verifica() -- e' esattamente lo scenario del
    // rilievo Critico (5 chiamate, 5 ricaricamenti, prima del fix).
    globalThis.HirisBuildCheck.verifica('nuovo222');
    globalThis.HirisBuildCheck.verifica('nuovo222');
    globalThis.HirisBuildCheck.verifica('nuovo222');

    assert.equal(reloadCalls.length, 0,
      'con lo storage rotto non si deve MAI ricaricare, nemmeno una volta: ' +
      'non si puo\' dimostrare che il tentativo precedente sia stato registrato');

    const striscia = document.getElementById('hiris-build-mismatch');
    assert.notEqual(striscia, null,
      'la striscia deve comparire SUBITO, al primo disallineamento, quando la guardia non e\' verificabile');
    assert.equal(
      striscia.textContent,
      'questa interfaccia viene da un build diverso da quello in esecuzione ' +
      '(vecchio111 invece di nuovo222): svuota i dati del sito di Home Assistant'
    );
  });
}

/* m3 (review finale): prova che il ripristino nel t.after() di
   `avviaConStorageRotto` funziona davvero. Deve girare DOPO il loop qui
   sopra: prima del fix, 'accesso-solleva' lasciava su `globalThis` un
   getter di `sessionStorage` che solleva, mai rimesso a posto -- salvato
   solo dal fatto che quei test erano gli ultimi del file e da node --test
   che isola ogni file in un processo separato. Un test aggiunto dopo (come
   questo) avrebbe ereditato lo storage rotto. */
test('dopo ogni modo di Web Storage rotto, sessionStorage torna sano per il test successivo', () => {
  assert.doesNotThrow(() => {
    globalThis.sessionStorage.setItem('sonda-m3', 'ok');
    assert.equal(globalThis.sessionStorage.getItem('sonda-m3'), 'ok');
    globalThis.sessionStorage.removeItem('sonda-m3');
  }, 'sessionStorage deve essere di nuovo leggibile e scrivibile normalmente');
});
