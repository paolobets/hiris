import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* FINAL whole-branch review, finding I3 (Important) -- l'idempotenza del
   router uccideva il retry-dopo-errore.

   router.js::resolveRoute() fa early-return su un hash INVARIATO
   (lastResolvedHash, introdotto per chiudere il bug live #2 -- vedi
   nav-guard.test.mjs) -- ma PRIMA registrava lastResolvedHash anche
   quando l'handler della route lanciava (il try/catch si limitava a
   loggare). Una route che va in errore risultava quindi "già risolta":
   ridispacciare lo stesso hash (l'unico modo che l'utente ha per
   riprovare quando la route non offre un bottone Riprova dedicato, es.
   dashboard.js/usage-route.js) diventava un no-op silenzioso -- serviva
   un hard reload.

   Fix: lastResolvedHash (e HirisState.route) si aggiornano SOLO se
   l'handler ritorna normalmente. Un handler che lancia lascia
   lastResolvedHash al valore precedente, quindi un secondo dispatch dello
   STESSO hash rientra nel match e richiama di nuovo l'handler -- qui
   simulato con un handler che fallisce una volta e poi riesce (come un
   fetch che fallisce e poi va a buon fine al retry). */

function setup() {
  return loadScripts(['config/state.js', 'config/router.js']);
}

test('I3: un handler che lancia non marca la route come risolta -- ridispacciare lo stesso hash permette il retry', () => {
  const { window } = setup();

  let attempts = 0;
  window.HirisRouter.register(/^#\/usage\/?$/, function() {
    attempts += 1;
    if (attempts === 1) throw new Error('fetch fallito (simulato)');
    // Il secondo tentativo riesce -- nessuna eccezione.
  });

  window.location.hash = '#/usage';
  window.HirisRouter.start(); // primo mount -> l'handler lancia (attempts=1)
  assert.equal(attempts, 1, 'primo mount tenta l\'handler (fallisce)');

  // L'utente "riprova" ridispacciando lo stesso hash (non c'è un bottone
  // Riprova dedicato -- vedi il commento in testa al file). Prima del
  // fix questo era un no-op: lastResolvedHash era già '#/usage' anche
  // dopo l'errore, quindi resolveRoute() faceva early-return alla prima
  // riga senza richiamare l'handler.
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(attempts, 2,
    'BUG I3: ridispacciare lo stesso hash dopo un errore deve richiamare di nuovo l\'handler (retry) -- non deve essere un no-op silenzioso');
});

test('I3 non regredisce il fix Task-3 (guard/eco): un handler che NON lancia marca comunque la route come risolta, l\'eco dell\'hashchange resta ignorato', () => {
  // Copertura di non-regressione minima -- il test completo del percorso
  // guard+eco vive in nav-guard.test.mjs (non toccato da questo fix).
  const { window } = setup();

  let mountCount = 0;
  window.HirisRouter.register(/^#\/chatbots\/([^/]+)$/, function() { mountCount += 1; });

  window.location.hash = '#/chatbots/abc';
  window.HirisRouter.start();
  assert.equal(mountCount, 1);

  // Stesso hash ridispacciato (es. l'eco del revert del guard): la route
  // NON deve rimontare, esattamente come prima di questo fix.
  window.dispatchEvent(new window.Event('hashchange'));
  assert.equal(mountCount, 1, 'un hashchange verso lo STESSO hash di una route già risolta con successo resta un no-op');
});
