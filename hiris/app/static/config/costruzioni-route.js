/* HIRIS · Configurazione · «Costruzioni» (route #/costruzioni)

   Il posto dove il proprietario approva o rifiuta cio' che HIRIS propone di
   scrivere in Home Assistant, legge il confronto prima/dopo, e rimette
   com'era un oggetto. Senza questa pagina l'archivio delle versioni
   (`hiris/app/azione/costruzione/versioni.py`) sarebbe uno stato che solo un
   curl puo' vedere -- la fondamenta 4 violata.

   Guida di disegno: `.superpowers/sdd/2026-08-23-costruire/
   guida-ux-costruzioni.md`, prodotta da ux-ui-specialist dopo aver letto il
   codice vero (`handlers_costruzioni.py`, `versioni.py`, `officina.py`), non
   solo lo scheletro del brief. Cio' che segue e' la sua sostanza.

   -- Due scostamenti che la guida ha trovato leggendo il codice --
   1. Manca(va) la rotta per rifiutare nello scheletro del brief: e' stata
      chiusa dal Task 10-bis (`POST /api/costruzioni/{id}/rifiuta`), quindi la
      card «in attesa» ha DUE bottoni, Approva e Rifiuta, non uno.
   2. `gesto` non vale MAI letteralmente "ripristina": l'elenco vero e'
      ("crea","modifica","cancella"). Un ripristino crea una riga NUOVA con
      gesto="cancella" (se disfa una creazione) o "modifica" (tutti gli altri
      casi), e `frase="ripristino di {id}"`. Il segnale che una riga e' frutto
      di un ripristino e' quel PREFISSO di `frase`, non un valore di `gesto`
      che non arriva mai -- un ramo su quel valore sarebbe codice morto.

   -- Cosa fa gia' il backend, cosa deve fare la pagina (guida §0) --
   `anteprima` e' prosa italiana gia' composta da `Officina._anteprima()`, e
   porta gia' dentro la distinzione fra "creato" e "modificato": per una
   `modifica`/`cancella` la prima riga dice sempre, testualmente, che
   l'oggetto "esiste gia' in casa tua". Il backend ha gia' fatto il lavoro
   semantico -- la pagina non lo inventa, non lo seppellisce dentro un
   paragrafo uguale agli altri. Lo stesso vale per il confronto: `anteprima`
   include gia' righe «Prima: …» / «Dopo: …» compattate. I dizionari grezzi
   `prima`/`dopo` sono un livello SECONDARIO per chi vuole guardare piu' a
   fondo, non il livello primario di lettura.

   -- Gerarchia (guida §1) --
   UNA sola `GET /api/costruzioni`, filtrata qui per `stato` -- non due
   richieste, non due mondi. Due sezioni: «In attesa» (in_attesa + in_corso
   insieme, stesso concetto "non ancora concluso", ordinate per `creata_ts`
   crescente -- chi aspetta da piu' tempo sta in cima) e «Storico» (tutto il
   resto, `creata_ts` decrescente, piu' recente in cima).

   -- Il prima/dopo: cosa mostrare, cosa NON inventare (guida §3) --
   Livello primario SEMPRE visibile: `anteprima`, per intero, mai riassunta.
   Livello secondario dietro un rivelatore SINCRONO (`prima`/`dopo` arrivano
   gia' nel payload dell'elenco: nasconderli dietro un fetch sarebbe la
   trappola che la guida delle Promesse vieta) che mostra solo: il nome
   (alias/name), quante voci per trigger/condizioni/azioni/entita' -- come
   transizione "azioni: 2 -> 3" quando cambia, non due numeri separati -- e
   gli entity_id in monospazio. Il codice qui sotto tratta anche `sequence`
   (il corpo di uno script) come sinonimo di "azioni": e' l'adattamento che il
   rapporto di questo task registra, la guida non lo nominava esplicitamente
   ma il backend (`officina.py::_compatta`) conta anche quella chiave, e uno
   script senza mai un numero di "azioni" sarebbe un buco silenzioso proprio
   sul dominio meno controllato lato Home Assistant.
   NON si ricostruisce mai una frase semantica leggendo dentro `actions`:
   interpretare azioni arbitrarie di Home Assistant e' il lavoro che
   `_anteprima()` fa gia' lato server con conoscenza di dominio. Un contatore
   sbagliato e' innocuo; una frase di senso sbagliato su un'automazione che
   aziona una sirena antincendio no.

   -- Creato contro modificato (guida §4) --
   Il sistema non sa quale dei diciotto oggetti scritti a mano dal
   proprietario sia critico: nessun campo di criticita' esiste. Percio' OGNI
   `modifica` e `cancella` porta lo stesso trattamento massimo, sempre --
   generalizzare, non selezionare: badge neutro per `crea`, ambra
   (badge-warn) per `modifica`, rosso (badge-err) per `cancella`, e la frase
   "esiste gia' in casa tua" accanto al nome per modifica/cancella -- SEMPRE,
   anche se `anteprima` la contiene gia': e' l'unica ripetizione voluta di
   questa pagina, perche' e' l'unico fatto per cui "non vista una volta" ha un
   costo reale.

   -- `frase` (guida §5) --
   Presente ma non protagonista: piu' piccola, piu' quieta, stile
   suggerimento. Quando comincia con "ripristino di " non e' una frase
   dell'utente (e' generata dal server, scostamento 2 sopra): si mostra come
   nota di sistema con un'etichetta propria, mai fra virgolette come le altre.

   -- Vocabolario degli stati (guida §6) --
   in_attesa "In attesa" (neutro) · in_corso "In corso" (acceso, nessuna
   azione: la guarigione e' gia' lato server) · applicata "Applicata"
   (acceso, e' qui che compare Ripristina) · rifiutata "Non riuscita" (rosso:
   HIRIS ha provato e non ce l'ha fatta, `motivo` verbatim) · scaduta
   "Scaduta" (ambra, non rosso: tempo passato senza decisione, non un
   fallimento) · disdetta -- il «no» del proprietario, badge NEUTRO come
   `in_attesa`, mai la faccia di `rifiutata`.
   ADATTAMENTO rispetto al testo letterale della guida (da riportare nel
   rapporto): la guida propone l'etichetta "Rifiutata da te" per `disdetta`.
   Ma un test pinnato vieta che il token "rifiutata" (parola intera,
   maiuscole/minuscole indifferenti) compaia OVUNQUE nel testo della pagina --
   ed e' lo stesso principio della guida, applicato alla lettera: se il
   proprietario legge la parola "rifiutata" su UNA riga che e' invece il suo
   "no", la distinzione per cui questa tabella esiste e' gia' persa, non
   importa quanto sia neutro il colore attorno. L'etichetta usata qui e' "Hai
   detto no" -- stesso significato, nessuna parola in comune con "rifiutata".
   SCOPERTA VERA, non solo del test: `versioni.py::segna_disdetta` scrive
   *letteralmente* `motivo="rifiutata dal proprietario"` su OGNI riga
   `disdetta` -- se la pagina mostrasse `motivo` verbatim anche li' (come fa
   per `rifiutata`), la parola tornerebbe dentro dalla porta sul retro. Questa
   pagina non mostra mai `motivo` quando `stato === 'disdetta'`.

   -- Comportamenti (guida §7) --
   Approva: nessuna conferma, la card e' gia' la revisione completa.
   Rifiuta: nessun confirm(), non distrugge niente, passa allo storico.
   Ripristina: SI', conferma esplicita -- a differenza di "applica", chiamato
   con origine umana `ripristina` SCRIVE SUBITO (crea la proposta e la
   applica nella stessa chiamata): non c'e' il passaggio intermedio che rende
   sicuro "Approva" senza conferma. Stessa famiglia del `window.confirm()` di
   «Dimentica» in memoria-route.js (azione distruttiva senza coda d'attesa).
   Testo composto solo da campi reali (mai una frase generica).
   Errori: 404/409/503 portano gia' un testo corretto dal server -- si legge
   `errore` e si mostra verbatim, mai un messaggio sintetico per casi che il
   server ha gia' separato. Solo un vero fallimento di rete usa il messaggio
   generico. Un fallimento della GET (rete giu', o il 503 che porta gia'
   `costruzioni: []` e sembra una lista vuota senza esserlo) mostra un
   messaggio distinto con "Riprova", mai lo stesso testo di "non c'e' niente
   qui".

   -- Sicurezza -- testi via textContent/createElement, MAI scrivendo markup
   HTML grezzo nel DOM: alias e anteprime nascono in una chat, e una chat puo'
   contenere markup (stessa disciplina di memoria-route.js/promesse-route.js).
   Le tre POST portano `X-Requested-With`, o il middleware CSRF le rifiuta con
   403 (`hiris/app/api/middleware_csrf.py`). */
window.HirisCostruzioni = (function () {
  'use strict';

  var STATO_APERTI = ['in_attesa', 'in_corso'];

  var STATO_LABEL = {
    in_attesa: 'In attesa',
    in_corso: 'In corso',
    applicata: 'Applicata',
    /* Vedi il commento di testa: ADATTAMENTO deliberato rispetto al testo
       letterale della guida ("Rifiutata da te"), per non far comparire la
       parola "rifiutata" su una riga che e' il "no" del proprietario. */
    disdetta: 'Hai detto no',
    rifiutata: 'Non riuscita',
    scaduta: 'Scaduta'
  };
  var STATO_BADGE = {
    in_attesa: 'badge-off',
    in_corso: 'badge-on',
    applicata: 'badge-on',
    disdetta: 'badge-off',
    rifiutata: 'badge-err',
    scaduta: 'badge-warn'
  };

  var NOME_DOMINIO = { automation: 'Automazione', script: 'Script', scene: 'Scena' };
  var ARTICOLO_DOMINIO = { automation: 'l’automazione', script: 'lo script', scene: 'la scena' };

  var CHIAVI_CONFRONTO = [
    { chiave: 'triggers', etichetta: 'trigger' },
    { chiave: 'conditions', etichetta: 'condizioni' },
    /* `actions`/`sequence`: un'automazione porta `actions`, uno script porta
       `sequence` -- stesso concetto (§3 del commento di testa). */
    { chiave: 'actions', chiaveAlt: 'sequence', etichetta: 'azioni' },
    { chiave: 'entities', etichetta: 'entità' }
  ];

  function el(tag, cls, testo) {
    var nodo = document.createElement(tag);
    if (cls) nodo.className = cls;
    if (testo !== undefined && testo !== null) nodo.textContent = String(testo);
    return nodo;
  }

  function clearEl(nodo) {
    while (nodo && nodo.firstChild) nodo.removeChild(nodo.firstChild);
    return nodo;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(path, opts);
  }

  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function fmtData(ts) {
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear();
  }

  /* Nome dell'oggetto (guida §2.1): "lo stesso ripiego esatto che usa il
     backend" -- che per `crea` legge l'alias del `dopo` (Officina._anteprima:
     `intento.get('alias')`, non c'e' nessun `prima`) e per `modifica`/
     `cancella` legge l'alias del `prima` (l'oggetto che gia' esisteva). Una
     sola catena di ripiego riproduce entrambi i casi senza duplicare logica:
     prima.alias quando c'e' (l'oggetto esisteva), altrimenti dopo.alias
     (l'oggetto nuovo), altrimenti la chiave tecnica. */
  function nomeOggetto(c) {
    return (c.prima && c.prima.alias) || (c.dopo && c.dopo.alias) || c.chiave;
  }

  function nomeDominio(c) {
    return NOME_DOMINIO[c.dominio] || c.dominio;
  }

  function articoloOggetto(c) {
    return ARTICOLO_DOMINIO[c.dominio] || ('l’oggetto ' + c.dominio);
  }

  /* guida §4: dare a OGNI modifica e cancellazione lo stesso trattamento
     massimo -- non selezionare, generalizzare. Un `modifica`/`cancella` con
     `prima` valorizzato tocca qualcosa che esisteva gia'. */
  function eraGiaLi(c) {
    return c.gesto !== 'crea' && !!c.prima;
  }

  function badgeGesto(c) {
    if (c.gesto === 'cancella') return { cls: 'badge-err', testo: 'Cancellata' };
    if (c.gesto === 'modifica') return { cls: 'badge-warn', testo: 'Modificata' };
    return { cls: 'badge-off', testo: 'Creata' };
  }

  /* La `frase` prefissata "ripristino di " non e' detta dall'utente (scarto
     2 del commento di testa): e' generata dal server. */
  function eRipristino(c) {
    return typeof c.frase === 'string' && c.frase.indexOf('ripristino di ') === 0;
  }

  function contaChiave(corpo, def) {
    if (!corpo) return null;
    var lista = corpo[def.chiave];
    if ((!lista || !lista.length) && def.chiaveAlt) lista = corpo[def.chiaveAlt];
    if (!lista) return null;
    return lista.length;
  }

  /* guida §3: la transizione "azioni: 2 -> 3", non due numeri separati da
     confrontare a mente. Un solo lato presente mostra solo quel numero. */
  function righeConfronto(prima, dopo) {
    var righe = [];
    CHIAVI_CONFRONTO.forEach(function (def) {
      var n1 = contaChiave(prima, def);
      var n2 = contaChiave(dopo, def);
      if (n1 === null && n2 === null) return;
      var testo = def.etichetta + ': ';
      if (n1 !== null && n2 !== null && n1 !== n2) testo += n1 + ' → ' + n2;
      else testo += (n1 !== null ? n1 : n2);
      righe.push(testo);
    });
    return righe;
  }

  function entitaToccate(c) {
    var lista = (c.dopo && c.dopo.entities) || (c.prima && c.prima.entities);
    return (lista && lista.length) ? lista : null;
  }

  /* guida §3: il rivelatore e' SINCRONO -- niente rete, `prima`/`dopo`
     arrivano gia' nel payload dell'elenco. */
  function pannelloDettagli(c) {
    var box = el('div');

    ['prima', 'dopo'].forEach(function (lato) {
      var corpo = c[lato];
      var etichetta = lato === 'prima' ? 'Prima' : 'Dopo';
      var nome = corpo ? (corpo.alias || corpo.name || '(senza nome)') : '(niente)';
      box.appendChild(el('div', 'field-hint', etichetta + ': ' + nome));
    });

    righeConfronto(c.prima, c.dopo).forEach(function (riga) {
      box.appendChild(el('div', 'field-hint', riga));
    });

    var entita = entitaToccate(c);
    if (entita) box.appendChild(el('div', 'text-mono', entita.join(', ')));

    return box;
  }

  function rivelatoreDettagli(c) {
    var wrap = el('div', 'field-group');
    var testoChiuso = 'Dettagli tecnici';
    var testoAperto = 'Nascondi i dettagli tecnici';
    var btn = el('button', 'btn btn-ghost btn-sm', testoChiuso);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');
    var idPannello = 'costruzione-dettagli-' + c.id;
    var pannello = pannelloDettagli(c);
    pannello.id = idPannello;
    pannello.hidden = true;
    btn.setAttribute('aria-controls', idPannello);

    btn.addEventListener('click', function () {
      var aperto = btn.getAttribute('aria-expanded') === 'true';
      pannello.hidden = aperto;
      btn.setAttribute('aria-expanded', aperto ? 'false' : 'true');
      btn.textContent = aperto ? testoChiuso : testoAperto;
    });

    wrap.appendChild(btn);
    wrap.appendChild(pannello);
    return wrap;
  }

  /* guida §7: il testo del confirm() composto solo da campi reali. */
  function messaggioRipristino(c) {
    return 'Rimetto ' + articoloOggetto(c) + ' «' + nomeOggetto(c) + '» com’era il ' +
      fmtData(c.creata_ts) + '. Le modifiche fatte dopo vengono sovrascritte. Procedo?';
  }

  function eseguiAzione(azione, id, bottoni, statusEl, ricarica) {
    bottoni.forEach(function (b) { b.disabled = true; });
    statusEl.textContent = '';
    api('api/costruzioni/' + encodeURIComponent(id) + '/' + azione, { method: 'POST' })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (corpo) {
          return { res: res, corpo: corpo };
        });
      })
      .then(function (esito) {
        if (esito.res.ok) { ricarica(); return; }
        /* guida §7: si legge `errore` verbatim, mai un messaggio sintetico
           per casi che il server ha gia' separato (404/409/503). */
        statusEl.textContent = (esito.corpo && esito.corpo.errore) ||
          ('Errore HTTP ' + esito.res.status);
        bottoni.forEach(function (b) { b.disabled = false; });
      }, function () {
        statusEl.textContent = 'HIRIS non ha risposto. Riprova più tardi.';
        bottoni.forEach(function (b) { b.disabled = false; });
      });
  }

  function bottoneAzione(azione, etichetta, cls, c, statusEl, ricarica) {
    var b = el('button', cls, etichetta);
    b.type = 'button';
    b.setAttribute('data-azione', azione);
    b.setAttribute('data-id', c.id);
    b.addEventListener('click', function () {
      if (azione === 'ripristina' && !window.confirm(messaggioRipristino(c))) return;
      eseguiAzione(azione, c.id, [b], statusEl, ricarica);
    });
    return b;
  }

  /* guida §2: dall'alto in basso -- etichetta strutturale (+ badge gesto, +
     "esiste gia'" quando serve), frase subordinata, anteprima per intero,
     helper, rivelatore dei dettagli tecnici, bottoni. */
  function riga(c, statusEl, ricarica) {
    var box = el('div', 'costruzione costruzione--' + c.stato);
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-4) 0;' +
      'display:flex;flex-direction:column;gap:var(--sp-2)';

    var testa = el('div');
    testa.style.cssText = 'display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap';
    testa.appendChild(el('span', null, nomeDominio(c) + ' «' + nomeOggetto(c) + '»'));
    var bGesto = badgeGesto(c);
    testa.appendChild(el('span', 'agent-badge ' + bGesto.cls, bGesto.testo));
    testa.appendChild(el('span', 'agent-badge ' + (STATO_BADGE[c.stato] || 'badge-off'),
      STATO_LABEL[c.stato] || c.stato));
    box.appendChild(testa);

    if (eraGiaLi(c)) {
      box.appendChild(el('div', 'field-hint', 'Questo oggetto esiste già in casa tua.'));
    }

    if (c.frase) {
      var frase;
      if (eRipristino(c)) {
        frase = el('p', 'field-hint', 'Ripristino di una versione precedente');
      } else {
        frase = el('p', 'field-hint', '«' + c.frase + '»');
      }
      frase.style.fontStyle = 'italic';
      box.appendChild(frase);
    }

    if (c.anteprima) {
      var pre = el('pre', null, c.anteprima);
      pre.style.cssText = 'white-space:pre-wrap;font-family:inherit;font-size:var(--fs-14);' +
        'color:var(--text);margin:0';
      box.appendChild(pre);
    }

    (c.helper || []).forEach(function (h) {
      var nomeHelper = (h.dati && h.dati.name) || '(senza nome)';
      box.appendChild(el('div', 'field-hint',
        'Nasce anche: ' + (h.dominio || '') + ' «' + nomeHelper + '»'));
    });

    if (c.prima || c.dopo) box.appendChild(rivelatoreDettagli(c));

    /* motivo: MAI per `disdetta` -- vedi il commento di testa, `versioni.py`
       scrive letteralmente "rifiutata dal proprietario" su ogni riga
       disdetta, e mostrarlo tornerebbe a far leggere quella parola su una
       riga che e' il "no" dell'utente. */
    if (c.motivo && c.stato !== 'disdetta') {
      var motivo = el('p', null, c.motivo);
      motivo.style.cssText = 'font-size:var(--fs-13);margin:0;color:' +
        (c.stato === 'rifiutata' ? 'var(--err-ink)' : 'var(--warn-ink)');
      box.appendChild(motivo);
    }

    var azioni = el('div');
    azioni.style.cssText = 'display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:var(--sp-1)';
    /* Condizione ESATTA `stato === 'in_attesa'`, non "sta nella sezione in
       attesa": `in_corso` ci sta ma non e' azionabile (guida §6, nessuna UI
       di recupero, la guarigione e' gia' lato server). */
    if (c.stato === 'in_attesa') {
      azioni.appendChild(bottoneAzione('conferma', 'Approva', 'btn btn-primary', c, statusEl, ricarica));
      azioni.appendChild(bottoneAzione('rifiuta', 'Rifiuta', 'btn', c, statusEl, ricarica));
    }
    if (c.stato === 'applicata') {
      azioni.appendChild(bottoneAzione('ripristina', 'Rimetti com’era',
        'btn btn-ghost btn-ghost-danger', c, statusEl, ricarica));
    }
    if (azioni.childNodes.length) box.appendChild(azioni);

    return box;
  }

  function ordinaAperte(lista) {
    return lista.slice().sort(function (a, b) { return a.creata_ts - b.creata_ts; });
  }
  function ordinaStorico(lista) {
    return lista.slice().sort(function (a, b) { return b.creata_ts - a.creata_ts; });
  }

  function rendiSezione(corpo, lista, vuoto, statusEl, ricarica, ordina) {
    clearEl(corpo);
    if (!lista.length) {
      corpo.appendChild(el('p', 'field-hint', vuoto));
      return;
    }
    ordina(lista).forEach(function (c) { corpo.appendChild(riga(c, statusEl, ricarica)); });
  }

  function rendiErrore(apertaCorpo, storicoCorpo, ricarica) {
    [apertaCorpo, storicoCorpo].forEach(function (nodo) {
      clearEl(nodo);
      nodo.appendChild(el('p', 'proposals-error',
        'Non è stato possibile leggere le costruzioni. Riprova più tardi.'));
      var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      retry.type = 'button';
      retry.addEventListener('click', ricarica);
      nodo.appendChild(retry);
    });
  }

  function buildSectionShell(num, idPrefix, titolo) {
    var section = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', titolo));
    section.appendChild(head);
    var body = el('div', 'sc-body');
    body.id = 'costruzioni-' + idPrefix + '-body';
    body.setAttribute('data-sezione', idPrefix);
    section.appendChild(body);
    return section;
  }

  function disegna(outlet) {
    function ricarica() { return disegna(outlet); }

    var apertaCorpo = outlet.querySelector('#costruzioni-aperte-body');
    var storicoCorpo = outlet.querySelector('#costruzioni-storico-body');
    var statusEl = outlet.querySelector('#costruzioni-status');

    if (!apertaCorpo || !storicoCorpo) {
      clearEl(outlet);
      outlet.appendChild(el('div', 'page-title', 'Costruzioni'));
      outlet.appendChild(el('p', 'page-subtitle',
        'Le proposte di HIRIS per creare, modificare o cancellare automazioni, script e ' +
        'scene di questa casa — e cosa ne hai deciso.'));
      var status = el('p', 'sc-desc', '');
      status.id = 'costruzioni-status';
      outlet.appendChild(status);
      outlet.appendChild(buildSectionShell('01', 'aperte', 'In attesa'));
      outlet.appendChild(buildSectionShell('02', 'storico', 'Storico'));
      apertaCorpo = outlet.querySelector('#costruzioni-aperte-body');
      storicoCorpo = outlet.querySelector('#costruzioni-storico-body');
      statusEl = outlet.querySelector('#costruzioni-status');
    }

    clearEl(apertaCorpo); apertaCorpo.appendChild(el('p', 'field-hint', 'Caricamento…'));
    clearEl(storicoCorpo); storicoCorpo.appendChild(el('p', 'field-hint', 'Caricamento…'));

    return fetch('api/costruzioni').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (dati) {
      var tutte = (dati && dati.costruzioni) || [];
      var aperte = tutte.filter(function (c) { return STATO_APERTI.indexOf(c.stato) !== -1; });
      var storico = tutte.filter(function (c) { return STATO_APERTI.indexOf(c.stato) === -1; });
      rendiSezione(apertaCorpo, aperte,
        'Nessuna proposta in attesa. Quando chiedi a HIRIS di creare, modificare o cancellare ' +
        'un’automazione, uno script o una scena, la trovi qui prima che diventi reale.',
        statusEl, ricarica, ordinaAperte);
      rendiSezione(storicoCorpo, storico, 'Nessuna costruzione nello storico.',
        statusEl, ricarica, ordinaStorico);
    }).catch(function () {
      rendiErrore(apertaCorpo, storicoCorpo, ricarica);
    });
  }

  function mount(outlet) {
    if (!outlet) return Promise.resolve();
    clearEl(outlet);
    return disegna(outlet);
  }

  return { mount: mount };
})();
