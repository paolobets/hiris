/* HIRIS · Config · Servizi (route #/services)
   Fetta «l'accoppiamento» (spec 2026-09-21 §7, rifatta il 22/09/2026).

   Chi, oltre al proprietario, puo' parlare con HIRIS. Fino al 22/09 si
   dichiarava in un campo di testo nelle opzioni dell'add-on, e quel campo
   aveva tre difetti che nessuna riscrittura poteva togliergli: ogni modifica
   riavvia l'add-on, revocare significava editare un blob, e **non si vedeva
   mai il momento in cui un servizio si presenta la prima volta** --
   l'autorizzazione era gia' data prima che il servizio esistesse.

   Questa pagina esiste per quel terzo punto: e' il posto in cui il primo
   contatto diventa un evento che si guarda e si approva.

   TRE SEZIONI E NON UN ELENCO UNICO, perche' i tre stati sono tre lavori
   diversi: «in attesa» e' una decisione da prendere adesso (e scade da sola
   in 24 ore), «accoppiato» e' un registro con un'azione sola, «revocato» e'
   una memoria. In un elenco unico la decisione sparirebbe fra le righe di
   registro, che col tempo sono la maggioranza -- stessa scelta gia' fatta in
   Impegni («In sospeso» / «Storico») e in Modelli.

   IL CODICE A QUATTRO CIFRE non e' un ornamento della riga: e' il solo fatto
   verificabile di tutta la pagina. Il nome se lo sceglie chi si presenta,
   quindi la riga dice «si presenta come ...» e non lo afferma; il codice
   invece si deriva dalla chiave pubblica, e chi si e' messo in mezzo non puo'
   farlo coincidere con quello che il servizio vero mostra sul proprio schermo.
   Per questo e' in monospazio e grande: chi lo legge ha il telefono in mano e
   sta guardando un pannello a due metri.

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati del
   server -- stesso vincolo di models-route.js e settings-route.js. */
window.HirisServicesRoute = (function () {
  'use strict';

  var SERVICES_URL = 'api/services';

  /* Ogni quanto la pagina si rilegge MENTRE la finestra e' aperta. Le righe in
     attesa arrivano da un'altra macchina: chi dovesse ricaricare per vederle
     penserebbe che l'accoppiamento non funziona. A finestra chiusa non c'e'
     niente da aspettare e il giro si ferma. */
  var RILETTURA_MS = 5000;

  /* Cosa concede ogni ruolo, detto a chi sta decidendo. Le CHIAVI ammesse
     arrivano dal server (`ruoli`, `specie`): qui c'e' solo la spiegazione, e
     un ruolo che il server aggiungesse senza che questa mappa lo conosca si
     mostra col proprio nome invece di sparire dall'elenco. */
  var RUOLI = {
    utente: 'Comanda la casa: accende, spegne, regola.',
    lettore: 'Legge lo stato della casa e basta.',
    amministratore: 'Costruisce automazioni e cambia come si comporta la casa. ' +
      'Solo per una macchina che gestisci tu.'
  };
  var SPECIE = {
    integrazione: 'Un programma su un’altra macchina.',
    luogo: 'Un pannello appeso in un punto della casa: HIRIS saprà da dove gli si parla.'
  };
  /* Il primo di ognuno dei due e' quello preselezionato: `utente` e' il caso
     comune, e `amministratore` sta in fondo perche' e' la decisione seria. */
  var ORDINE_RUOLI = ['utente', 'lettore', 'amministratore'];
  var ORDINE_SPECIE = ['integrazione', 'luogo'];

  var stato = { dati: null, giro: null, aperto: null, messaggio: '',
              revocatiAperti: false };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* Stesso involucro di settings-route.js e models-route.js: l'intestazione
     `X-Requested-With` non e' facoltativa -- `csrf_middleware` risponde 403 a
     ogni POST su /api/ che non la porta. Sta in un punto solo perche'
     dimenticarla su una chiamata sola e' il modo esatto in cui questa pagina
     smetterebbe di funzionare. */
  function api(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(url, opts);
  }

  /* Minuti arrotondati PER ECCESSO, mai secondi. Un cronometro al secondo su
     dieci minuti e' una gara; qui i dieci minuti sono il tempo per fare una
     cosa sull'altra macchina. E il numero arriva dal server a ogni rilettura,
     non da un orologio locale che inventerebbe un'ora sua. */
  function quantoResta(secondi) {
    if (secondi > 60) return 'ancora per circa ' + Math.ceil(secondi / 60) + ' minuti';
    return 'per meno di un minuto';
  }

  function quando(ts) {
    return ts ? fmtDateTime(ts * 1000) : '';
  }

  function righe(stati) {
    var tutte = (stato.dati && stato.dati.servizi) || [];
    return tutte.filter(function (r) { return stati.indexOf(r.stato) >= 0; });
  }

  // --- le chiamate che cambiano qualcosa ------------------------------------

  function chiedi(url, corpo) {
    return api(url, { method: 'POST', body: JSON.stringify(corpo || {}) })
      .then(function (r) {
        return r.json().catch(function () { return {}; })
          .then(function (j) { return { ok: r.ok, corpo: j }; });
      });
  }

  /* Legge lo stato intero. Una GET sola: chi aspetta, chi e' vivo, chi e'
     stato revocato e la finestra sono la stessa domanda vista in quattro
     momenti, e chiederli separatamente li farebbe divergere fra una risposta
     e l'altra. */
  function rileggi() {
    return api(SERVICES_URL, { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (d) { stato.dati = d; disegna(); ritmo(); });
  }

  /* Siamo ancora su questa pagina? Il router di questa SPA non avvisa nessuno
     quando una route esce di scena, e un giro di riletture che sopravvivesse
     continuerebbe a interrogare il server da una pagina che non si vede piu',
     per sempre. Si guarda l'indirizzo perche' e' l'unico fatto che il router
     espone senza doverlo cambiare. */
  function ancoraQui() {
    return String(window.location.hash || '').indexOf('#/services') === 0;
  }

  /* Il giro di riletture vive quanto la finestra, e non un minuto di piu'. */
  function ritmo() {
    var aperta = !!(stato.dati && stato.dati.finestra && stato.dati.finestra.aperta);
    if (aperta && ancoraQui() && stato.giro == null) {
      stato.giro = setInterval(function () {
        if (!ancoraQui()) { unmount(); return; }
        api(SERVICES_URL, { method: 'GET' })
          .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
          .then(function (d) { stato.dati = d; disegna(); ritmo(); })
          .catch(function () { /* un giro perso non e' un guasto: al prossimo */ });
      }, RILETTURA_MS);
    } else if ((!aperta || !ancoraQui()) && stato.giro != null) {
      unmount();
    }
  }

  function agisci(url, corpo, messaggio) {
    chiedi(url, corpo).then(function (esito) {
      if (esito.ok) {
        if (esito.corpo.servizi) stato.dati.servizi = esito.corpo.servizi;
        if (esito.corpo.aperta !== undefined) {
          stato.dati.finestra = { aperta: esito.corpo.aperta, resta_s: esito.corpo.resta_s };
        }
        stato.messaggio = messaggio;
        stato.aperto = null;
        disegna();
        ritmo();
        return;
      }
      /* Mai un catch muto: il rifiuto del server dice cosa manca, ed e'
         scritto per essere letto da chi sta decidendo. */
      stato.messaggio = esito.corpo.errore || 'Non è riuscito. Controlla il log dell’add-on.';
      disegna();
    }).catch(function () {
      stato.messaggio = 'Il server non ha risposto.';
      disegna();
    });
  }

  // --- la sezione 01: la finestra e chi aspetta -----------------------------

  function sezione(numero, titolo) {
    var card = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', numero));
    head.appendChild(el('h2', 'sc-title', titolo));
    card.appendChild(head);
    return { card: card, head: head };
  }

  function accoppiamento() {
    var finestra = (stato.dati && stato.dati.finestra) || { aperta: false, resta_s: 0 };
    var s = sezione('01', 'Accoppiamento');
    var badge = el('span', 'agent-badge ' + (finestra.aperta ? 'badge-on' : 'badge-off'),
      finestra.aperta ? 'Aperta' : 'Chiusa');
    s.head.appendChild(badge);

    var desc = el('p', 'sc-desc', finestra.aperta
      ? 'Finestra aperta ' + quantoResta(finestra.resta_s) + '. Avvia l’accoppiamento ' +
        'sulla macchina del servizio: comparirà qui sotto con un codice di quattro ' +
        'cifre da confrontare.'
      : 'Finestra chiusa: nessun servizio nuovo può presentarsi. Aprila quando stai ' +
        'per avviare l’accoppiamento sull’altra macchina.');
    s.card.appendChild(desc);

    var body = el('div', 'sc-body');
    var comando = el('button', 'btn ' + (finestra.aperta ? 'btn-ghost' : 'btn-primary'),
      finestra.aperta ? 'Chiudi adesso' : 'Apri la finestra per 10 minuti');
    comando.type = 'button';
    comando.addEventListener('click', function () {
      if (finestra.aperta) {
        agisci('api/services/window/close', {}, 'Finestra chiusa.');
      } else {
        agisci('api/services/window/open', {},
          'Finestra aperta per dieci minuti. Avvia l’accoppiamento sull’altra macchina.');
      }
    });
    body.appendChild(comando);

    /* Le righe in attesa arrivate PRIMA che la finestra si chiudesse restano
       qui e restano approvabili: la finestra governa chi puo' presentarsi, non
       chi puo' essere approvato. */
    righe(['in_attesa']).forEach(function (r) { body.appendChild(rigaInAttesa(r)); });
    s.card.appendChild(body);
    return s.card;
  }

  function rigaInAttesa(r) {
    var riga = el('div', 'sc-row');
    /* «si presenta come», non il nome asciutto: il nome se lo sceglie chi si
       presenta, quindi non e' un fatto. Il fatto e' il codice. */
    riga.appendChild(el('div', 'sc-row-title', 'Si presenta come «' + r.nome + '»'));
    riga.appendChild(el('div', 'sc-row-why',
      'da ' + r.indirizzo + ' · arrivato il ' + quando(r.visto_ts)));

    var codice = el('div', 'service-code', r.codice);
    riga.appendChild(codice);
    riga.appendChild(el('div', 'sc-row-why',
      'Lo stesso numero deve comparire sullo schermo del servizio.'));

    if (stato.aperto === r.chiave) {
      riga.appendChild(pannello(r));
      return riga;
    }

    var azioni = el('div', 'jr-actions');
    var approva = el('button', 'btn btn-primary', 'Approva…');
    approva.type = 'button';
    approva.addEventListener('click', function () { stato.aperto = r.chiave; disegna(); });
    var rifiuta = el('button', 'btn btn-ghost btn-ghost-danger', 'Rifiuta');
    rifiuta.type = 'button';
    /* «Rifiuta» E' la revoca, e non e' un riuso pigro: rifiutare chi si e'
       messo in mezzo deve impedirgli di tornare in coda ribussando, ed e'
       esattamente cio' che la revoca garantisce. Senza questo bottone
       l'unica risposta a un codice che non coincide sarebbe aspettare
       ventiquattro ore con uno sconosciuto sotto gli occhi. */
    rifiuta.addEventListener('click', function () {
      agisci('api/services/revoke', { chiave: r.chiave },
        '«' + r.nome + '» è stato rifiutato: non può più presentarsi.');
    });
    azioni.appendChild(approva);
    azioni.appendChild(rifiuta);
    riga.appendChild(azioni);
    return riga;
  }

  /* Il pannello dell'approvazione, DENTRO la riga: due menu a tendina
     nasconderebbero che si sta decidendo qualcosa, e su un telefono
     sembrerebbero un modulo qualunque. Stesso gesto del pannello di Modelli.

     Non c'e' un `window.confirm` sopra `amministratore`: la frase che dice
     cosa succede dopo E' la conferma, e la revoca immediata rende l'errore
     reversibile. Un secondo cancello sulla stessa porta si impara a
     scavalcare, non a leggere. */
  function pannello(r) {
    var p = el('div', 'service-panel');
    p.setAttribute('role', 'group');
    p.appendChild(el('div', 'sc-row-why',
      'Approva solo se sullo schermo di «' + r.nome + '» c’è ' + r.codice +
      '. Se è diverso, rifiuta: qualcuno si sta presentando al posto suo.'));

    var scelte = { ruolo: ORDINE_RUOLI[0], specie: ORDINE_SPECIE[0] };
    var conferma = el('button', 'btn btn-primary', '');
    conferma.type = 'button';
    var effetto = el('p', 'sc-row-why', '');

    function aggiorna() {
      conferma.textContent = 'Accoppia come ' + scelte.ruolo;
      effetto.textContent = 'Da adesso «' + r.nome + '» ' + (
        scelte.ruolo === 'lettore' ? 'potrà leggere lo stato della casa.'
        : scelte.ruolo === 'amministratore'
          ? 'potrà comandare la casa e costruire automazioni.'
          : 'potrà comandare la casa.');
    }

    p.appendChild(gruppo('Cosa può fare', 'ruolo-' + r.codice,
      ordinati(ORDINE_RUOLI, (stato.dati && stato.dati.ruoli) || []), RUOLI,
      function (v) { scelte.ruolo = v; aggiorna(); }));
    p.appendChild(gruppo('Cos’è', 'specie-' + r.codice,
      ordinati(ORDINE_SPECIE, (stato.dati && stato.dati.specie) || []), SPECIE,
      function (v) { scelte.specie = v; aggiorna(); }));

    aggiorna();
    conferma.addEventListener('click', function () {
      agisci('api/services/approve',
        { chiave: r.chiave, ruolo: scelte.ruolo, specie: scelte.specie },
        '«' + r.nome + '» è accoppiato come ' + scelte.ruolo + '.');
    });
    var annulla = el('button', 'btn btn-ghost', 'Annulla');
    annulla.type = 'button';
    annulla.addEventListener('click', function () { stato.aperto = null; disegna(); });

    p.appendChild(effetto);
    var azioni = el('div', 'jr-actions');
    azioni.appendChild(conferma);
    azioni.appendChild(annulla);
    p.appendChild(azioni);
    return p;
  }

  /* L'insieme dei valori lo possiede il SERVER (`ruoli`, `specie` nella
     risposta); l'ordine in cui si mostrano e' una decisione di questa pagina.
     Cio' che il server manda e questa pagina non conosce si mostra comunque,
     in fondo: una scelta che sparisce e' peggio di una senza spiegazione. */
  function ordinati(preferito, dalServer) {
    var fuori = dalServer.filter(function (v) { return preferito.indexOf(v) < 0; });
    return preferito.filter(function (v) { return dalServer.indexOf(v) >= 0; }).concat(fuori);
  }

  function gruppo(titolo, nome, valori, spiegazioni, scelto) {
    var g = el('fieldset', 'service-choice');
    g.appendChild(el('legend', null, titolo));
    valori.forEach(function (v, i) {
      var riga = el('label', 'service-option');
      var radio = el('input');
      radio.type = 'radio';
      radio.name = nome;
      radio.value = v;
      if (i === 0) radio.checked = true;
      radio.addEventListener('change', function () { scelto(v); });
      var testo = el('span');
      testo.appendChild(el('span', 'sc-row-title', v));
      testo.appendChild(el('span', 'sc-row-why', spiegazioni[v] || ''));
      riga.appendChild(radio);
      riga.appendChild(testo);
      g.appendChild(riga);
    });
    return g;
  }

  // --- 02 gli accoppiati, 03 i revocati -------------------------------------

  function accoppiati() {
    var s = sezione('02', 'Servizi accoppiati');
    var vivi = righe(['autorizzato']).sort(function (a, b) {
      return String(a.nome).localeCompare(String(b.nome), 'it');
    });
    if (!vivi.length) {
      s.card.appendChild(el('p', 'sc-desc',
        'Nessun servizio accoppiato. Il primo lo aggiungi aprendo la finestra qui sopra.'));
      return s.card;
    }
    var body = el('div', 'sc-body');
    vivi.forEach(function (r) {
      var riga = el('div', 'sc-row');
      var testa = el('div', 'jr-meta');
      testa.appendChild(el('span', 'sc-row-title', r.nome));
      /* `amministratore` porta un badge, gli altri due no: cio' che serve a
         colpo d'occhio e' chi puo' costruire automazioni, non l'elenco dei
         ruoli. Il badge non e' l'unico segnale -- la riga sotto lo dice a
         parole (WCAG 1.4.1). */
      if (r.ruolo === 'amministratore') {
        testa.appendChild(el('span', 'agent-badge badge-paused', 'amministratore'));
      }
      riga.appendChild(testa);
      riga.appendChild(el('div', 'sc-row-why',
        ruoloDetto(r.ruolo) + ' · ' + (SPECIE[r.specie] ? r.specie : r.specie || '') +
        ' · accoppiato il ' + quando(r.deciso_ts)));
      var azioni = el('div', 'jr-actions');
      var revoca = el('button', 'btn btn-ghost btn-ghost-danger', 'Revoca');
      revoca.type = 'button';
      /* Nessuna conferma: la riga non sparisce -- passa in «Revocati», dove
         resta leggibile -- e l'effetto immediato e' proprio cio' che si vuole
         quando si revoca. Si conferma cio' che distrugge senza coda. */
      revoca.addEventListener('click', function () {
        agisci('api/services/revoke', { chiave: r.chiave },
          '«' + r.nome + '» non può più parlare con HIRIS.');
      });
      azioni.appendChild(revoca);
      riga.appendChild(azioni);
      body.appendChild(riga);
    });
    s.card.appendChild(body);
    return s.card;
  }

  function ruoloDetto(ruolo) {
    return RUOLI[ruolo] ? ruolo : (ruolo || 'senza ruolo');
  }

  function revocati() {
    var fuori = righe(['revocato']);
    if (!fuori.length) return null;
    var card = el('section', 'section-card');
    var head = el('div', 'sc-header');
    var toggle = el('button', 'sc-toggle', 'Revocati (' + fuori.length + ')');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', stato.revocatiAperti ? 'true' : 'false');
    head.appendChild(el('span', 'sc-num', '03'));
    head.appendChild(toggle);
    card.appendChild(head);

    var body = el('div', 'sc-body');
    body.hidden = !stato.revocatiAperti;
    toggle.addEventListener('click', function () {
      stato.revocatiAperti = !stato.revocatiAperti;
      disegna();
    });
    fuori.forEach(function (r) {
      var riga = el('div', 'sc-row');
      var testa = el('div', 'jr-meta');
      testa.appendChild(el('span', 'sc-row-title', r.nome));
      /* `badge-off` e non una rossa: e' un ordine del proprietario, non un
         guasto -- stessa regola di «Disdetta» in Impegni. */
      testa.appendChild(el('span', 'agent-badge badge-off', 'Revocato'));
      riga.appendChild(testa);
      riga.appendChild(el('div', 'sc-row-why',
        (r.ruolo ? 'aveva il ruolo ' + r.ruolo + ' · ' : 'mai approvato · ') +
        'revocato il ' + quando(r.deciso_ts)));
      if (stato.aperto === r.chiave) {
        riga.appendChild(pannello(r));
      } else {
        var azioni = el('div', 'jr-actions');
        /* La revoca resta reversibile DA QUI: senza questo bottone un servizio
           revocato non potrebbe piu' tornare in nessun modo -- ripresentarsi
           non lo rimette in coda, per disegno -- e il proprietario dovrebbe
           fargli rifare le chiavi per un click sbagliato. */
        var riammetti = el('button', 'btn btn-ghost', 'Riammetti…');
        riammetti.type = 'button';
        riammetti.addEventListener('click', function () {
          stato.revocatiAperti = true;
          stato.aperto = r.chiave;
          disegna();
        });
        azioni.appendChild(riammetti);
        riga.appendChild(azioni);
      }
      body.appendChild(riga);
    });
    card.appendChild(body);
    return card;
  }

  // --- il disegno -----------------------------------------------------------

  function intestazione(outlet) {
    outlet.appendChild(el('h1', 'page-title', 'Servizi'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Chi, oltre a te, può parlare con HIRIS: pannelli e integrazioni su altre ' +
      'macchine. Ognuno entra con una chiave sua e con il ruolo che decidi tu, e ' +
      'puoi revocarlo in qualsiasi momento con effetto immediato.'));
  }

  function disegna() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    intestazione(outlet);

    var avviso = el('p', 'sc-desc', stato.messaggio || '');
    avviso.setAttribute('aria-live', 'polite');
    outlet.appendChild(avviso);

    outlet.appendChild(accoppiamento());
    outlet.appendChild(accoppiati());
    var storia = revocati();
    if (storia) outlet.appendChild(storia);
  }

  function errore(outlet, testo) {
    outlet.innerHTML = '';
    intestazione(outlet);
    outlet.appendChild(el('p', 'sc-desc', testo));
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    stato.dati = null;
    stato.aperto = null;
    stato.messaggio = '';
    outlet.innerHTML = '';
    intestazione(outlet);
    outlet.appendChild(el('p', 'sc-desc', 'Caricamento…'));

    rileggi().catch(function () {
      errore(outlet, 'Non è stato possibile leggere i servizi. Controlla il log ' +
        'dell’add-on e ricarica la pagina. Se non sei amministratore di Home ' +
        'Assistant, questa pagina non è per te: accoppiare un servizio è un gesto ' +
        'da amministratore.');
    });
  }

  /* Il giro di riletture si ferma quando si lascia la pagina: senza questa
     riga continuerebbe a interrogare il server da una route che non si vede
     piu', per sempre. */
  function unmount() {
    if (stato.giro != null) { clearInterval(stato.giro); stato.giro = null; }
  }

  return { mount: mount, unmount: unmount };
})();
