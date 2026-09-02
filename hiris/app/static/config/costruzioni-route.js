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
      chiusa dal Task 10-bis (`POST /api/constructions/{id}/reject`), quindi la
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
   UNA sola `GET /api/constructions`, filtrata qui per `stato` -- non due
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
   ADATTAMENTO rispetto al testo letterale della guida (confermato dalla
   review indipendente del Task 11: la guida si contraddiceva da sola,
   proponendo nella STESSA sezione l'etichetta "Rifiutata da te" per
   `disdetta` e insieme la regola che quello stato non deve mai avere la
   faccia di `rifiutata`). Un test pinnato vieta che il token "rifiutata"
   (parola intera, maiuscole/minuscole indifferenti) compaia OVUNQUE nel
   testo della pagina -- ed e' lo stesso principio della guida, applicato
   alla lettera: se il proprietario legge la parola "rifiutata" su UNA riga
   che e' invece il suo "no", la distinzione per cui questa tabella esiste e'
   gia' persa, non importa quanto sia neutro il colore attorno. L'etichetta
   usata qui e' "Declinata da te": stesso significato ("sei stato tu, non e'
   un fallimento"), nessuna parola in comune con "rifiutata", e resta nel
   registro participiale delle altre cinque etichette (In attesa, In corso,
   Applicata, Non riuscita, Scaduta) -- "Hai detto no", la prima versione,
   parlava in seconda persona e stonava nella fila dei badge (review Task 11).
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

  var OPEN_STATES = ['in_attesa', 'in_corso'];

  var STATO_LABEL = {
    in_attesa: 'In attesa',
    in_corso: 'In corso',
    applicata: 'Applicata',
    /* Vedi il commento di testa: ADATTAMENTO deliberato rispetto al testo
       letterale della guida ("Rifiutata da te"), per non far comparire la
       parola "rifiutata" su una riga che e' il "no" del proprietario. */
    disdetta: 'Declinata da te',
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

  var DOMAIN_NAME = { automation: 'Automazione', script: 'Script', scene: 'Scena' };
  var DOMAIN_ARTICLE = { automation: 'l’automazione', script: 'lo script', scene: 'la scena' };

  var CHIAVI_CONFRONTO = [
    { chiave: 'triggers', etichetta: 'trigger' },
    { chiave: 'conditions', etichetta: 'condizioni' },
    /* `actions`/`sequence`: un'automazione porta `actions`, uno script porta
       `sequence` -- stesso concetto (§3 del commento di testa). */
    { chiave: 'actions', chiaveAlt: 'sequence', etichetta: 'azioni' },
    { chiave: 'entities', etichetta: 'entità' }
  ];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clearEl(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
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
  function objectName(c) {
    return (c.prima && c.prima.alias) || (c.dopo && c.dopo.alias) || c.chiave;
  }

  function domainName(c) {
    return DOMAIN_NAME[c.dominio] || c.dominio;
  }

  function objectArticle(c) {
    return DOMAIN_ARTICLE[c.dominio] || ('l’oggetto ' + c.dominio);
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

  /* Conta gli elementi di un array O di un dizionario -- serve per la
     `scene`: `entities` li' non e' un array come per automazioni/script, e'
     una mappa entity_id -> attributi (`forme.py::componi_scena`,
     Home Assistant la restituisce nella stessa forma per `prima`). In
     Python `len()` funziona uguale su liste e dict (`officina.py::
     _compatta`); in JS `{}.length` e' `undefined`, non `0` -- senza questo
     ramo il pannello mostrava letteralmente "entita': undefined" per ogni
     scena. Ritorna `null` solo quando la chiave non c'e' o non e' un
     array/oggetto -- una lista/dizionario vuoto ma PRESENTE resta `0`,
     distinzione che `righeConfronto` usa per decidere se mostrare la riga. */
  function countElements(value) {
    if (value === undefined || value === null) return null;
    if (Array.isArray(value)) return value.length;
    if (typeof value === 'object') return Object.keys(value).length;
    return null;
  }

  function countForKey(body, def) {
    if (!body) return null;
    var n = countElements(body[def.chiave]);
    if ((n === null || n === 0) && def.chiaveAlt) {
      var alt = countElements(body[def.chiaveAlt]);
      if (alt !== null) n = alt;
    }
    return n;
  }

  /* guida §3: la transizione "azioni: 2 -> 3", non due numeri separati da
     confrontare a mente. Un solo lato presente mostra solo quel numero. */
  function comparisonLines(prima, dopo) {
    var line = [];
    CHIAVI_CONFRONTO.forEach(function (def) {
      var n1 = countForKey(prima, def);
      var n2 = countForKey(dopo, def);
      if (n1 === null && n2 === null) return;
      var text = def.etichetta + ': ';
      if (n1 !== null && n2 !== null && n1 !== n2) text += n1 + ' → ' + n2;
      else text += (n1 !== null ? n1 : n2);
      line.push(text);
    });
    return line;
  }

  /* Gli `entity_id` toccati (guida §3): per una `scene` sono le CHIAVI del
     dizionario `entities` (stesso motivo di `contaElementi` sopra), non i
     suoi valori (gli attributi) -- per automazione/script, se mai portassero
     un array, sono gia' loro. E' proprio il dominio in cui questa lista e'
     tutto il contenuto dell'oggetto (guida §3): senza questo ramo non
     compariva MAI. */
  function entityList(value) {
    if (!value) return null;
    if (Array.isArray(value)) return value.length ? value : null;
    if (typeof value === 'object') {
      var chiavi = Object.keys(value);
      return chiavi.length ? chiavi : null;
    }
    return null;
  }

  function touchedEntities(c) {
    return entityList(c.dopo && c.dopo.entities) || entityList(c.prima && c.prima.entities);
  }

  /* guida §3: il rivelatore e' SINCRONO -- niente rete, `prima`/`dopo`
     arrivano gia' nel payload dell'elenco. */
  function detailsPanel(c) {
    var box = el('div');

    ['prima', 'dopo'].forEach(function (side) {
      var body = c[side];
      var label = side === 'prima' ? 'Prima' : 'Dopo';
      var name = body ? (body.alias || body.name || '(senza nome)') : '(niente)';
      box.appendChild(el('div', 'field-hint', label + ': ' + name));
    });

    comparisonLines(c.prima, c.dopo).forEach(function (line) {
      box.appendChild(el('div', 'field-hint', line));
    });

    var entity = touchedEntities(c);
    if (entity) box.appendChild(el('div', 'text-mono', entity.join(', ')));

    return box;
  }

  function detailsDisclosure(c) {
    var wrap = el('div', 'field-group');
    var closedText = 'Dettagli tecnici';
    var openText = 'Nascondi i dettagli tecnici';
    var btn = el('button', 'btn btn-ghost btn-sm', closedText);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');
    var idPannello = 'costruzione-dettagli-' + c.id;
    var panel = detailsPanel(c);
    panel.id = idPannello;
    panel.hidden = true;
    btn.setAttribute('aria-controls', idPannello);

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      panel.hidden = open;
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      btn.textContent = open ? closedText : openText;
    });

    wrap.appendChild(btn);
    wrap.appendChild(panel);
    return wrap;
  }

  /* guida §7: il testo del confirm() composto solo da campi reali. */
  function restoreMessage(c) {
    return 'Rimetto ' + objectArticle(c) + ' «' + objectName(c) + '» com’era il ' +
      fmtData(c.creata_ts) + '. Le modifiche fatte dopo vengono sovrascritte. Procedo?';
  }

  function executeAction(action, id, button, statusEl, reload) {
    button.forEach(function (b) { b.disabled = true; });
    statusEl.textContent = '';
    api('api/constructions/' + encodeURIComponent(id) + '/' + action, { method: 'POST' })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          return { res: res, corpo: body };
        });
      })
      .then(function (occurrence) {
        if (occurrence.res.ok) { reload(); return; }
        /* guida §7: si legge `errore` verbatim, mai un messaggio sintetico
           per casi che il server ha gia' separato (404/409/503). */
        statusEl.textContent = (occurrence.corpo && occurrence.corpo.error) ||
          ('Errore HTTP ' + occurrence.res.status);
        button.forEach(function (b) { b.disabled = false; });
      }, function () {
        statusEl.textContent = 'HIRIS non ha risposto. Riprova più tardi.';
        button.forEach(function (b) { b.disabled = false; });
      });
  }

  /* `gruppo`, opzionale: l'array di bottoni SOLIDALI da disabilitare insieme
     durante la richiesta -- Approva e Rifiuta stanno sulla stessa card e la
     UPDATE atomica del backend regge comunque un doppio clic, ma lasciare
     cliccabile il gemello mentre l'altro sta gia' girando e' un'incoerenza
     visibile che due righe evitano. Riempito dal chiamante DOPO aver creato
     entrambi i bottoni (vedi `riga()`): la closure lo legge al click, non
     alla creazione, quindi vede gia' il gruppo completo. Senza `gruppo`
     (Ripristina, sola sulla propria riga) si disabilita solo se stesso. */
  function actionButton(action, label, cls, c, statusEl, reload, group) {
    var b = el('button', cls, label);
    b.type = 'button';
    b.setAttribute('data-azione', action);
    b.setAttribute('data-id', c.id);
    b.addEventListener('click', function () {
      if (action === 'restore' && !window.confirm(restoreMessage(c))) return;
      executeAction(action, c.id, group || [b], statusEl, reload);
    });
    return b;
  }

  /* guida §2: dall'alto in basso -- etichetta strutturale (+ badge gesto, +
     "esiste gia'" quando serve), frase subordinata, anteprima per intero,
     helper, rivelatore dei dettagli tecnici, bottoni. */
  function line(c, statusEl, reload) {
    var box = el('div', 'costruzione costruzione--' + c.stato);
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-4) 0;' +
      'display:flex;flex-direction:column;gap:var(--sp-2)';

    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap';
    head.appendChild(el('span', null, domainName(c) + ' «' + objectName(c) + '»'));
    var bGesto = badgeGesto(c);
    head.appendChild(el('span', 'agent-badge ' + bGesto.cls, bGesto.testo));
    head.appendChild(el('span', 'agent-badge ' + (STATO_BADGE[c.stato] || 'badge-off'),
      STATO_LABEL[c.stato] || c.stato));
    box.appendChild(head);

    if (eraGiaLi(c)) {
      box.appendChild(el('div', 'field-hint', 'Questo oggetto esiste già in casa tua.'));
    }

    if (c.frase) {
      var phrase;
      if (eRipristino(c)) {
        phrase = el('p', 'field-hint', 'Ripristino di una versione precedente');
      } else {
        phrase = el('p', 'field-hint', '«' + c.frase + '»');
      }
      phrase.style.fontStyle = 'italic';
      box.appendChild(phrase);
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

    if (c.prima || c.dopo) box.appendChild(detailsDisclosure(c));

    /* motivo: MAI per `disdetta` -- vedi il commento di testa, `versioni.py`
       scrive letteralmente "rifiutata dal proprietario" su ogni riga
       disdetta, e mostrarlo tornerebbe a far leggere quella parola su una
       riga che e' il "no" dell'utente. */
    if (c.motivo && c.stato !== 'disdetta') {
      var reason = el('p', null, c.motivo);
      reason.style.cssText = 'font-size:var(--fs-13);margin:0;color:' +
        (c.stato === 'rifiutata' ? 'var(--err-ink)' : 'var(--warn-ink)');
      box.appendChild(reason);
    }

    var actions = el('div');
    actions.style.cssText = 'display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:var(--sp-1)';
    /* Condizione ESATTA `stato === 'in_attesa'`, non "sta nella sezione in
       attesa": `in_corso` ci sta ma non e' azionabile (guida §6, nessuna UI
       di recupero, la guarigione e' gia' lato server). */
    if (c.stato === 'in_attesa') {
      var pendingGroup = [];
      var bConferma = actionButton('confirm', 'Approva', 'btn btn-primary', c, statusEl, reload, pendingGroup);
      var bRifiuta = actionButton('reject', 'Rifiuta', 'btn', c, statusEl, reload, pendingGroup);
      pendingGroup.push(bConferma, bRifiuta);
      actions.appendChild(bConferma);
      actions.appendChild(bRifiuta);
    }
    if (c.stato === 'applicata') {
      actions.appendChild(actionButton('restore', 'Rimetti com’era',
        'btn btn-ghost btn-ghost-danger', c, statusEl, reload));
    }
    if (actions.childNodes.length) box.appendChild(actions);

    return box;
  }

  function sortOpen(list) {
    return list.slice().sort(function (a, b) { return a.creata_ts - b.creata_ts; });
  }
  function sortHistory(list) {
    return list.slice().sort(function (a, b) { return b.creata_ts - a.creata_ts; });
  }

  function renderSection(body, list, empty, statusEl, reload, sort) {
    clearEl(body);
    if (!list.length) {
      body.appendChild(el('p', 'field-hint', empty));
      return;
    }
    sort(list).forEach(function (c) { body.appendChild(line(c, statusEl, reload)); });
  }

  function renderError(openBody, historyBody, reload) {
    [openBody, historyBody].forEach(function (node) {
      clearEl(node);
      node.appendChild(el('p', 'proposals-error',
        'Non è stato possibile leggere le costruzioni. Riprova più tardi.'));
      var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      retry.type = 'button';
      retry.addEventListener('click', reload);
      node.appendChild(retry);
    });
  }

  function buildSectionShell(num, idPrefix, title) {
    var section = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    section.appendChild(head);
    var body = el('div', 'sc-body');
    body.id = 'costruzioni-' + idPrefix + '-body';
    body.setAttribute('data-sezione', idPrefix);
    section.appendChild(body);
    return section;
  }

  function draw(outlet) {
    function reload() { return draw(outlet); }

    var openBody = outlet.querySelector('#costruzioni-aperte-body');
    var historyBody = outlet.querySelector('#costruzioni-storico-body');
    var statusEl = outlet.querySelector('#costruzioni-status');

    if (!openBody || !historyBody) {
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
      openBody = outlet.querySelector('#costruzioni-aperte-body');
      historyBody = outlet.querySelector('#costruzioni-storico-body');
      statusEl = outlet.querySelector('#costruzioni-status');
    }

    clearEl(openBody); openBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    clearEl(historyBody); historyBody.appendChild(el('p', 'field-hint', 'Caricamento…'));

    return fetch('api/constructions').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      var all = (data && data.constructions) || [];
      var open = all.filter(function (c) { return OPEN_STATES.indexOf(c.stato) !== -1; });
      var history = all.filter(function (c) { return OPEN_STATES.indexOf(c.stato) === -1; });
      renderSection(openBody, open,
        'Nessuna proposta in attesa. Quando chiedi a HIRIS di creare, modificare o cancellare ' +
        'un’automazione, uno script o una scena, la trovi qui prima che diventi reale.',
        statusEl, reload, sortOpen);
      renderSection(historyBody, history, 'Nessuna costruzione nello storico.',
        statusEl, reload, sortHistory);
    }).catch(function () {
      renderError(openBody, historyBody, reload);
    });
  }

  function mount(outlet) {
    if (!outlet) return Promise.resolve();
    clearEl(outlet);
    return draw(outlet);
  }

  return { mount: mount };
})();
