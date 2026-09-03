/* HIRIS · il pallino delle due voci esecutive.
 *
 * Caricato da TUTTI E DUE i gusci (index.html e config.html), come
 * `config/api.js` e `build-check.js`: il numero e' lo stesso fatto sulle due
 * superfici, e un fatto ha una sola casa.
 *
 * ── Non mostra mai `0` ─────────────────────────────────────────────────
 * Ne' per errore, ne' per zero vero, e sono due ragioni distinte.
 *
 * Per errore: un pallino qui c'e' gia' stato ed e' morto. Contava le
 * segnalazioni del Brain leggendo una rotta uscita con la fetta E3, e
 * mostrava `0` quando quella rotta rispondeva 404 -- la lapide sta in
 * `hiris-config.css`, dove vivevano le sue quattro regole `.nav-badge`. Non
 * era inutile: era peggio. Diceva «non c'e' niente da guardare» quando la
 * verita' era «non lo so». Per questo `GET /api/pending` risponde 503 e non
 * uno zero quando un archivio manca, e per questo il `catch` qui sotto
 * SPEGNE invece di scrivere.
 *
 * Per zero vero: zero non e' una notizia. Un pallino che c'e' sempre smette
 * di essere letto, e allora non serve piu' nemmeno quando il numero conta.
 *
 * ── Nessun timer ──────────────────────────────────────────────────────
 * I momenti in cui il numero cambia si vedono tutti: l'apertura di un
 * guscio, la risposta della chat (e' li' che nasce una promessa o una
 * proposta), un'azione sulle due pagine, e il ritorno del fuoco sulla
 * finestra -- che copre il solo caso che gli altri tre non vedono, lo
 * schedulatore che ha concluso una promessa mentre la scheda era in secondo
 * piano. Un poll costerebbe una richiesta al minuto, per sempre, su un
 * Raspberry, per un numero che cambia qualche volta al giorno.
 *
 * ── L'aggancio ────────────────────────────────────────────────────────
 * Due attributi `data-badge` sulle voci di menu, e nient'altro. Se le voci
 * non ci sono -- un guscio che non le monta, o una pagina in cui non
 * esistono -- lo script non trova niente e non fa niente: e' voluto, non e'
 * un guasto da segnalare.
 */
window.HirisPendingBadge = (function () {
  'use strict';

  /* La chiave della rotta -> il `data-badge` della voce. Le due chiavi sono
     asimmetriche apposta (`api/handlers_pending.py`): sugli Impegni si
     contano gli esiti che nessuno ha letto, sulle Proposte quelle in attesa
     di una risposta. Sono due attese diverse -- le Proposte aspettano
     l'utente, gli Impegni aspettano l'ora -- e due nomi uguali l'avrebbero
     nascosto. */
  var VOCI = [
    { chiave: 'agenda_unread', voce: 'agenda' },
    { chiave: 'constructions_pending', voce: 'constructions' }
  ];

  function ospite(voce) {
    return document.querySelector('[data-badge="' + voce + '"]');
  }

  function spegni(voce) {
    var host = ospite(voce);
    if (!host) return;
    var vecchi = host.querySelectorAll('.nav-badge');
    for (var i = 0; i < vecchi.length; i++) {
      vecchi[i].parentNode.removeChild(vecchi[i]);
    }
  }

  function accendi(voce, n) {
    var host = ospite(voce);
    if (!host) return;
    /* Si spegne PRIMA di riaccendere: un secondo giro che appendesse senza
       togliere lascerebbe due pallini sulla stessa voce, e il secondo
       coprirebbe il primo mostrando il numero giusto per caso. */
    spegni(voce);
    var pallino = document.createElement('span');
    pallino.className = 'nav-badge';
    pallino.textContent = String(n);
    /* Sotto i 1024 px la side-nav si stringe a 64 px e le etichette
       spariscono (hiris-config.css): un numero nudo, li', non si capirebbe
       ne' col mouse ne' con uno screen reader. Il nome sta accanto al numero
       che accompagna, come gia' fanno `title`/`aria-label` di ogni voce di
       menu, cosi' i due non possono divergere. */
    pallino.setAttribute('title', n + ' in attesa');
    pallino.setAttribute('aria-label', n + ' in attesa');
    host.appendChild(pallino);
  }

  function refresh() {
    return fetch('api/pending').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (dati) {
      for (var i = 0; i < VOCI.length; i++) {
        var n = dati[VOCI[i].chiave];
        /* `typeof n === 'number'` e non il solo `n > 0`: se la rotta
           cambiasse sotto e smettesse di mandare una chiave, `undefined > 0`
           sarebbe falso e il pallino si spegnerebbe in silenzio -- cioe'
           direbbe «non c'e' niente» sapendo niente. E' il difetto del badge
           morto con un'altra provenienza. Qui una chiave che manca finisce
           spenta come un errore, che e' cio' che e'. */
        if (typeof n === 'number' && n > 0) accendi(VOCI[i].voce, n);
        else spegni(VOCI[i].voce);
      }
    }).catch(function (err) {
      /* Il ramo che il badge morto non aveva. Spegne anche cio' che era
         acceso al giro prima: un numero vecchio lasciato li' mentre la rete
         e' caduta e' di nuovo un numero che mente, stavolta sul quando. */
      console.warn('[pallino] conteggio non disponibile', err);
      for (var j = 0; j < VOCI.length; j++) spegni(VOCI[j].voce);
    });
  }

  function mount() {
    window.addEventListener('focus', refresh);
    return refresh();
  }

  return { mount: mount, refresh: refresh };
})();
