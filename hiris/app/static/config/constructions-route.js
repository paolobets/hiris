/* HIRIS · «Proposte» (route #/constructions)

   Il posto dove il proprietario approva o rifiuta cio' che HIRIS propone di
   scrivere in Home Assistant, legge il confronto prima/dopo, e rimette
   com'era un oggetto. Senza questa pagina l'archivio delle versioni
   (`hiris/app/action/construction/revisions.py`) sarebbe uno stato che solo un
   curl puo' vedere -- la fondamenta 4 violata.

   Guida di disegno: `.superpowers/sdd/2026-08-23-costruire/
   guida-ux-costruzioni.md`, prodotta da ux-ui-specialist dopo aver letto il
   codice vero (`handlers_constructions.py`, `revisions.py`, `workshop.py`), non
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
   `anteprima` e' prosa italiana gia' composta da `Workshop._preview()`, e
   porta gia' dentro la distinzione fra "creato" e "modificato": per una
   `modifica`/`cancella` la prima riga dice sempre, testualmente, che
   l'oggetto "esiste gia' in casa tua". Il backend ha gia' fatto il lavoro
   semantico -- la pagina non lo inventa, non lo seppellisce dentro un
   paragrafo uguale agli altri. Lo stesso vale per il confronto: `anteprima`
   include gia' righe «Prima: …» / «Dopo: …» compattate. I dizionari grezzi
   `prima`/`dopo` sono un livello SECONDARIO per chi vuole guardare piu' a
   fondo, non il livello primario di lettura.

   -- Gerarchia (guida §1) --
   UNA sola `GET /api/constructions`, divisa qui sul campo `sospesa` che il
   server calcola per ogni riga (C-12: la regola «non ancora concluso» delle
   due code vive in `handlers_constructions._both_queues`, non in questa
   pagina) -- non due richieste, non due mondi. Due sezioni: «In attesa» (le
   righe sospese: per le costruzioni in_attesa + in_corso, per le proposte a
   mano la loro attesa; ordinate per `creata_ts`
   crescente -- chi aspetta da piu' tempo sta in cima) e «Storico» (tutto il
   resto, `creata_ts` decrescente, piu' recente in cima).
   Lo «Storico» nasce CHIUSO, con il conteggio nel titolo (fetta «i menu
   esecutivi», gemello degli Impegni): e' un registro di consultazione, e
   lasciarlo aperto sotto la sezione che aspetta una decisione fa scorrere
   via proprio quella. Lo stato aperto/chiuso non si ricorda fra una visita e
   l'altra -- la domanda con cui si apre questa pagina e' sempre la stessa e
   deve avere sempre la stessa risposta.

   -- Il prima/dopo: cosa mostrare, cosa NON inventare (guida §3) --
   Livello primario SEMPRE visibile: `anteprima`, per intero, mai riassunta.
   Livello secondario dietro un rivelatore SINCRONO (`prima`/`dopo` arrivano
   gia' nel payload dell'elenco: nasconderli dietro un fetch sarebbe la
   trappola che la guida degli Impegni vieta) che mostra solo: il nome
   (alias/name), quante voci per trigger/condizioni/azioni/entita' -- come
   transizione "azioni: 2 -> 3" quando cambia, non due numeri separati -- e
   gli entity_id in monospazio. Il codice qui sotto tratta anche `sequence`
   (il corpo di uno script) come sinonimo di "azioni": e' l'adattamento che il
   rapporto di questo task registra, la guida non lo nominava esplicitamente
   ma il backend (`workshop.py::_compatta`) conta anche quella chiave, e uno
   script senza mai un numero di "azioni" sarebbe un buco silenzioso proprio
   sul dominio meno controllato lato Home Assistant.
   NON si ricostruisce mai una frase semantica leggendo dentro `actions`:
   interpretare azioni arbitrarie di Home Assistant e' il lavoro che
   `_preview()` fa gia' lato server con conoscenza di dominio. Un contatore
   sbagliato e' innocuo; una frase di senso sbagliato su un'automazione che
   aziona una sirena antincendio no.

   -- Creato contro modificato (guida §4) --
   Il sistema non sa quale dei diciotto oggetti scritti a mano dal
   proprietario sia critico: nessun campo di criticita' esiste. Percio' OGNI
   `modifica` e `cancella` porta lo stesso trattamento massimo, sempre --
   generalizzare, non selezionare: badge neutro per `create`, ambra
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
   SCOPERTA VERA, non solo del test: `revisions.py::mark_cancelled` scrive
   la COSTANTE `REASON_DISDETTA` ("rifiutata dalla pagina", fetta "il seguito
   delle chat divise" Task 5, 26/09/2026 -- prima era letteralmente
   `motivo="rifiutata dal proprietario"`). Fix round 1: il vecchio testo non
   resta una seconda costante a runtime che nessuno legge -- le righe scritte
   prima di questa versione si riscrivono UNA volta sola in una migrazione
   dell'archivio (`revisions.py::_migration_3`), col vecchio letterale
   dichiarato solo li', con la sua data. Se la pagina mostrasse `motivo`
   verbatim anche per `disdetta` (come fa per `rifiutata`), la parola
   "rifiutata" tornerebbe dentro dalla porta sul retro. Questa pagina non
   mostra mai `motivo` quando `stato === 'disdetta'`, guardando lo STATO e
   non il testo: e' per questo che una riga non ancora migrata (o letta da
   un archivio non aggiornato) si comporta gia' come una migrata, senza
   bisogno di distinguerle qui.

   -- Comportamenti (guida §7) --
   Approva: nessuna conferma, la card e' gia' la revisione completa.
   Rifiuta: nessun confirm(), non distrugge niente, passa allo storico.
   Ripristina: SI', conferma esplicita -- a differenza di "applica", chiamato
   con origine umana `restore` SCRIVE SUBITO (crea la proposta e la
   applica nella stessa chiamata): non c'e' il passaggio intermedio che rende
   sicuro "Approva" senza conferma. Stessa famiglia del `window.confirm()` di
   «Dimentica» in memory-route.js (azione distruttiva senza coda d'attesa).
   Testo composto solo da campi reali (mai una frase generica).
   Errori: 404/409/503 portano gia' un testo corretto dal server -- si legge
   `error` e si mostra verbatim, mai un messaggio sintetico per casi che il
   server ha gia' separato. Solo un vero fallimento di rete usa il messaggio
   generico. Un fallimento della GET (rete giu', o il 503 -- che fino al
   05/10/2026 portava anche `constructions: []`, A10) mostra un
   messaggio distinto con "Riprova", mai lo stesso testo di "non c'e' niente
   qui". Il 403 della GET (la pagina e' di chi costruisce, spec 2026-09-26
   §3) e' un terzo caso: il motivo del server, senza "Riprova".

   -- Sicurezza -- testi via textContent/createElement, MAI scrivendo markup
   HTML grezzo nel DOM: alias e anteprime nascono in una chat, e una chat puo'
   contenere markup (stessa disciplina di memory-route.js/agenda-route.js).
   Le tre POST portano `X-Requested-With`, o il middleware CSRF le rifiuta con
   403 (`hiris/app/api/middleware_csrf.py`). */
window.HirisConstructions = (function () {
  'use strict';

  var STATE_LABEL = {
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
  var STATE_BADGE = {
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

  function fmtData(ts) {
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear();
  }

  /* Nome dell'oggetto (guida §2.1): "lo stesso ripiego esatto che usa il
     backend" -- che per `create` legge l'alias del `dopo` (Officina._anteprima:
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

  function operationBadge(c) {
    if (c.gesto === 'cancella') return { cls: 'badge-err', testo: 'Cancellata' };
    if (c.gesto === 'modifica') return { cls: 'badge-warn', testo: 'Modificata' };
    return { cls: 'badge-off', testo: 'Creata' };
  }

  /* La `frase` prefissata "ripristino di " non e' detta dall'utente (scarto
     2 del commento di testa): e' generata dal server. */
  function isRestore(c) {
    return typeof c.frase === 'string' && c.frase.indexOf('ripristino di ') === 0;
  }

  /* Conta gli elementi di un array O di un dizionario -- serve per la
     `scene`: `entities` li' non e' un array come per automazioni/script, e'
     una mappa entity_id -> attributi (`forme.py::compose_scene`,
     Home Assistant la restituisce nella stessa forma per `prima`). In
     Python `len()` funziona uguale su liste e dict (`officina.py::
     _compatta`); in JS `{}.length` e' `undefined`, non `0` -- senza questo
     ramo il pannello mostrava letteralmente "entita': undefined" per ogni
     scena. Ritorna `null` solo quando la chiave non c'e' o non e' un
     array/oggetto -- una lista/dizionario vuoto ma PRESENTE resta `0`,
     distinzione che `comparisonLines` usa per decidere se mostrare la riga. */
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
     dizionario `entities` (stesso motivo di `countElements` sopra), non i
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

  /* I servizi che il corpo chiama, e soprattutto quelli che **compaiono**.

     Un elenco solo direbbe «chiamera' queste cose»; cio' che serve a chi
     decide e' cosa cambia. Quelli nuovi si dicono a parte e per primi: sono
     la ragione per cui questa riga esiste. */
  function servicesLines(c) {
    var prima = c.chiama_prima || [];
    var dopo = c.chiama_dopo || [];
    var nuovi = dopo.filter(function (s) { return prima.indexOf(s) < 0; });
    var righe = [];
    if (nuovi.length) righe.push('Chiamate NUOVE: ' + nuovi.join(', '));
    if (dopo.length) righe.push('Chiama: ' + dopo.join(', '));
    else if (prima.length) righe.push('Chiamava: ' + prima.join(', '));
    return righe;
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

    /* **Cosa chiamera'** (reperto B-4, 22/09/2026). Fino a oggi questo
       pannello mostrava conteggi -- «azioni: 2 -> 3» -- e in nessun punto
       dell'interfaccia il proprietario vedeva le AZIONI che stava
       approvando. Uno `shell_command` dentro il corpo passa la validazione di
       Home Assistant, e' valido, e crea un oggetto permanente che chiama un
       servizio che la porta diretta non avrebbe potuto chiamare.

       Non e' una restrizione: il si' c'era gia', era disinformato.

       I nomi arrivano dal server (`chiama_prima`/`chiama_dopo`): camminare i
       corpi anche qui sarebbe lo stesso cammino in due linguaggi, libero di
       divergere. */
    servicesLines(c).forEach(function (line) {
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
    var panelId = 'construction-details-' + c.id;
    var panel = detailsPanel(c);
    panel.id = panelId;
    btn.setAttribute('aria-controls', panelId);
    setDisclosure(btn, panel, false);

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') !== 'true';
      setDisclosure(btn, panel, open);
      btn.textContent = open ? openText : closedText;
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
        /* guida §7: si legge `error` verbatim, mai un messaggio sintetico
           per casi che il server ha gia' separato (403/404/409/503): dalla
           Tappa 4 (D2) ogni errore HTTP porta quella chiave sola. */
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
  /* Le proposte DA FARE A MANO (spec 2026-09-21 §3): non hanno gesto, ne'
     dominio, ne' un diff -- hanno un testo, un perche', e tre esiti di cui
     uno solo e' un «no». **«Crea» non c'e'**: qui non c'e' niente da scrivere
     in Home Assistant, e quella strada e' l'officina.

     Vivono in un archivio gemello e si leggono in questo elenco: «un posto
     solo dove si decide» e' una promessa sulla PAGINA, non sulla tabella. */
  /* Chi l'ha chiesta (spec 2026-09-26 §3): il NOME che il server legge da
     Home Assistant o dall'archivio dei servizi, mai la chiave. `null` -- una
     proposta dell'osservatore, una orfana -- non scrive niente: «chiesta da
     nessuno» direbbe un fatto che non si sa. Testo di fuori: textContent. */
  function requesterLine(c) {
    return c.chiesta_da ? el('div', 'field-hint', 'Chiesta da ' + c.chiesta_da) : null;
  }

  function lineAMano(c, statusEl, reload) {
    var box = el('div', 'construction construction--' + c.stato);
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-4) 0;' +
      'display:flex;flex-direction:column;gap:var(--sp-2)';

    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap';
    var testo = el('span', null, c.testo || '');
    /* Il fuoco ci arriva dopo un «Rifalla» riuscito (attori, Task 4.4). */
    testo.setAttribute('data-proposta', c.id);
    testo.tabIndex = -1;
    head.appendChild(testo);
    head.appendChild(el('span', 'agent-badge badge-off', 'la fai tu'));
    if (c.in_preparazione) head.appendChild(preparingBadge(c));
    box.appendChild(head);
    var chiA = requesterLine(c);
    if (chiA) box.appendChild(chiA);
    if (c.perche) box.appendChild(el('div', 'field-hint', c.perche));

    /* Il filo dei giri: cosa hai gia' scartato, e cosa avevi chiesto. Al
       terzo giro nessuno si ricorda piu' cosa aveva chiesto al primo. Un
       giro chiude con uno degli esiti del proponente (attori, Task 4.4): una
       frase nuova, niente, o una proposta costruibile. */
    (c.giri || []).forEach(function (giro) {
      var riga = el('div', 'field-hint');
      riga.appendChild(el('div', null, 'Avevi chiesto: ' + (giro.richiesta || '')));
      riga.appendChild(el('div', null, roundOutcome(giro)));
      box.appendChild(riga);
    });

    if (c.stato !== 'attesa') {
      box.appendChild(el('div', 'field-hint', CLOSED_TEXT[c.stato] ? CLOSED_TEXT[c.stato](c)
        : 'Rifiutata.'));
      return box;
    }

    var attesa = redoWaiting(c);
    if (attesa) {
      box.setAttribute('aria-busy', 'true');
      box.appendChild(waitBlock(attesa));
    }

    if (c.in_preparazione) {
      box.appendChild(el('div', 'field-hint',
        'HIRIS sta preparando l’automazione. Può volerci qualche minuto.'));
    } else if (c.non_automatizzabile) {
      box.appendChild(el('div', 'field-hint',
        'Non si può rendere automatica: ' + c.non_automatizzabile));
    }

    /* Mentre un'automazione si prepara resta solo «Rifiuta»: un secondo
       giro sulla stessa proposta (o un «L'ho fatta io» che la chiude sotto
       al turno) farebbe nascere una costruzione senza piu' nessuno a cui
       legarla. */
    var actions = el('div');
    actions.style.cssText = 'display:flex;gap:var(--sp-2);flex-wrap:wrap;margin-top:var(--sp-1)';
    var done = proposalButton(c, 'done', 'L’ho fatta io', 'btn btn-primary', statusEl, reload);
    actions.appendChild(done);
    var hint = null;
    if (c.automatizzabile) {
      hint = el('div', 'field-hint',
        'HIRIS prepara un’automazione di Home Assistant: la vedrai qui, e decidi tu se crearla.');
      hint.id = 'automatica-' + c.id;
      actions.appendChild(automateButton(c, hint.id, statusEl, reload));
    }
    /* Mentre il rifacimento e' in volo «Rifalla» non c'e': un secondo giro
       lo rifiuterebbe il server (409). «Rifiuta» e «L'ho fatta io» restano:
       la risposta che arriva dopo si scarta (scelta del proprietario,
       06/10/2026). */
    var redo = attesa ? null : redoControl(c, statusEl, reload);
    if (redo) actions.appendChild(redo);
    actions.appendChild(proposalButton(c, 'reject', 'Rifiuta', 'btn', statusEl, reload));
    if (c.in_preparazione) {
      [done, redo && redo.querySelector('button')].filter(Boolean).forEach(function (b) {
        b.disabled = true;
        b.setAttribute('aria-disabled', 'true');
      });
    }
    box.appendChild(actions);
    if (hint) box.appendChild(hint);
    return box;
  }

  /* Come si chiude una proposta a mano, per esito. «automatizzata» (attori,
     Task 4.5): ne e' nata una proposta di automazione, che sta in questa
     stessa pagina col suo «Nata da». */
  var CLOSED_TEXT = {
    fatta_fuori: function (c) {
      return 'L’hai fatta tu, fuori da Home Assistant.' + (c.esito_nota ? ' ' + c.esito_nota : '');
    },
    superata: function () {
      return 'Superata: ora c’è una proposta che HIRIS può costruire.';
    },
    automatizzata: function () {
      return 'Ne è nata un’automazione: la trovi tra le proposte.';
    }
  };

  function preparingBadge(c) {
    var b = el('span', 'agent-badge badge-warn', 'in preparazione');
    b.setAttribute('aria-label', 'Automazione in preparazione');
    b.setAttribute('data-preparazione', c.id);
    b.tabIndex = -1;
    return b;
  }

  /* «Rendila automatica» (attori, Task 4.5; parere di ux-ui-specialist e
     scelte del proprietario del 06/10/2026). Non crea niente: fa preparare
     al proponente un'automazione, che arriva in questa pagina con anteprima
     e conferma. Niente finestra di conferma, per la stessa ragione. Il
     bottone c'e' solo se il server dice `automatizzabile` -- la regola e'
     una, `automate_turn.refusal`, e per `alto` il bottone non esiste.
     Dopo il clic la riga si ridisegna «in preparazione», e il fuoco torna
     sul suo segno: il ridisegno ricrea la riga, e lo perderebbe. */
  function automateButton(c, hintId, statusEl, reload) {
    /* Lo stesso nome dell'azione di `proposalButton`: `proposta-` e il verbo
       della rotta. */
    var verbo = 'automate';
    var b = el('button', 'btn', 'Rendila automatica');
    b.type = 'button';
    b.setAttribute('data-azione', 'proposta-' + verbo);
    b.setAttribute('data-id', c.id);
    b.setAttribute('aria-describedby', hintId);
    b.addEventListener('click', function () {
      b.disabled = true;
      api('api/proposals/' + encodeURIComponent(c.id) + '/' + verbo,
          { method: 'POST', body: JSON.stringify({}) })
        .then(function (r) {
          if (r.ok) {
            return Promise.resolve(reload()).then(function () {
              var segno = document.querySelector('[data-preparazione="' + c.id + '"]');
              if (segno) segno.focus();
            });
          }
          /* Il motivo e' del server (gia' decisa, un'altra in preparazione,
             nessun modello): si mostra com'e', via textContent. */
          return r.json().catch(function () { return {}; }).then(function (corpo) {
            b.disabled = false;
            if (statusEl) {
              statusEl.textContent = (corpo && corpo.error) || 'Non è stato possibile prepararla: riprova.';
            }
          });
        }, function () {
          b.disabled = false;
          if (statusEl) statusEl.textContent = 'Non è stato possibile prepararla: riprova.';
        });
    });
    return b;
  }

  /* Cosa e' uscito da un giro del filo. Un giro scritto prima del 06/10/2026
     non porta `esito`: era sempre una frase nuova. */
  function roundOutcome(giro) {
    if (giro.esito === 'niente') {
      return 'Nessuna proposta: ' + (giro.perche || '');
    }
    if (giro.esito === 'costruita') {
      return 'Ne è nata una proposta da approvare.';
    }
    return 'Scartata: ' + (giro.scartata || '');
  }

  /* I due esiti che chiudono: stessa forma dei bottoni dell'officina, **altra
     porta**. Chiamare `/api/constructions/...` con l'id di una proposta a mano
     darebbe un 404, e la pagina direbbe «non esiste» su una riga che sta
     guardando. */
  function proposalButton(c, verbo, etichetta, cls, statusEl, reload) {
    var b = el('button', cls, etichetta);
    b.type = 'button';
    b.setAttribute('data-azione', 'proposta-' + verbo);
    b.setAttribute('data-id', c.id);
    b.addEventListener('click', function () {
      b.disabled = true;
      api('api/proposals/' + encodeURIComponent(c.id) + '/' + verbo,
          { method: 'POST', body: JSON.stringify({}) })
        .then(function () { reload(); }, function () {
          b.disabled = false;
          if (statusEl) statusEl.textContent = 'Non è stato possibile: riprova.';
        });
    });
    return b;
  }

  /* -- «Rifalla» (attori, Task 4.4; D16) -------------------------------

     Il rifacimento e' un turno del proponente. Sulla catena la richiesta
     torna con l'esito; sul ponte torna 202, e la risposta arriva minuti dopo
     da un altro processo: la riga porta allora `rifacimento`, che il server
     legge dalla coda, e la pagina rilegge l'elenco finche' nessuna riga e'
     piu' in corso. Lo stato sta nella riga e non nella pagina: sopravvive a
     `reload()` e a una ricarica. Parere di ux-ui-specialist del 06/10/2026
     (/mnt/project-files/attori/2026-10-06-task-4-4-rifalla-proposta.md). */

  /* I rifacimenti di questa pagina: quelli sulla catena, che aspettano la
     loro richiesta (`{id: {avvio, richiesta}}`); quelli di cui la pagina
     aspetta l'esito per dirlo (`{id: true}`); le richieste scritte, che non
     si perdono finche' il rifacimento non riesce (`lasciate`); la nota del
     backend sul giro; il giro di riletture e l'orologio; l'ultima risposta
     letta, per non ridisegnare quando niente e' cambiato. */
  var redo = { catena: {}, attesi: {}, lasciate: {}, nota: '', giro: null,
               orologio: null, ultima: '' };

  var REDO_WAIT_LABEL = 'Sto rifacendo la proposta';
  /* Le due frasi dei due minuti, come quelle della chat (chat/messages.js):
     sul ponte il turno e' al sicuro sul server, sulla catena muore con la
     richiesta. */
  var REDO_SAFE_ON_SERVER = 'Il rifacimento può richiedere qualche minuto. Puoi anche ' +
    'chiudere: se arriva, la nuova proposta la trovi qui.';
  var REDO_KEEP_OPEN = 'Il rifacimento può richiedere qualche minuto. Tieni aperta ' +
    'questa pagina: se la chiudi, questo rifacimento si perde.';

  /* L'attesa di una riga, o `null`: dal server (ponte) o dalla richiesta
     ancora aperta (catena). `scadenza` e' un istante in ms, 0 se non c'e'. */
  function redoWaiting(c) {
    var r = c.rifacimento;
    if (r && r.stato === 'in_corso') {
      return { avvio: (r.avvio_ts || 0) * 1000, scadenza: (r.scadenza_ts || 0) * 1000,
               richiesta: r.richiesta || '', ponte: true };
    }
    var locale = redo.catena[c.id];
    if (locale) {
      return { avvio: locale.avvio, scadenza: 0, richiesta: locale.richiesta, ponte: false };
    }
    return null;
  }

  /* La frase dell'attesa a un dato istante: una funzione del tempo, non una
     catena di timer, perche' la riga si ridisegna a ogni rilettura. Le
     soglie e le frasi sono quelle della chat (common.js). */
  function waitLabel(attesa, adesso) {
    var passato = adesso - attesa.avvio;
    if (attesa.scadenza && adesso >= attesa.scadenza - SOGLIE_ATTESA.margineResa) {
      return FRASI_ATTESA.quasiResa;
    }
    if (!attesa.scadenza && passato >= SOGLIE_ATTESA.senzaScadenza) {
      return FRASI_ATTESA.senzaScadenza;
    }
    if (passato >= SOGLIE_ATTESA.lenta) return FRASI_ATTESA.lenta;
    return REDO_WAIT_LABEL;
  }

  function paintWait(node, attesa, adesso) {
    var passato = adesso - attesa.avvio;
    node.querySelector('.redo-label').textContent = waitLabel(attesa, adesso);
    var timer = node.querySelector('.redo-timer');
    timer.textContent = passato >= SOGLIE_ATTESA.timer ? stopwatchText(passato) : '';
    node.querySelector('.redo-service').textContent = passato >= SOGLIE_ATTESA.servizio
      ? (attesa.ponte ? REDO_SAFE_ON_SERVER : REDO_KEEP_OPEN) : '';
  }

  /* Il blocco d'attesa. NON e' una regione live: si ricrea a ogni rilettura
     e verrebbe riletto ogni pochi secondi. Annuncia la riga di stato, una
     volta all'avvio e una all'esito. Il cronometro e' per l'occhio. */
  function waitBlock(attesa) {
    var node = el('div', 'field-hint redo-wait');
    node.setAttribute('data-avvio', String(attesa.avvio));
    node.setAttribute('data-scadenza', String(attesa.scadenza));
    node.setAttribute('data-ponte', attesa.ponte ? '1' : '');
    var top = el('div');
    top.appendChild(el('span', 'redo-label', REDO_WAIT_LABEL));
    var timer = el('span', 'redo-timer');
    timer.setAttribute('aria-hidden', 'true');
    top.appendChild(timer);
    node.appendChild(top);
    node.appendChild(el('div', null, 'Avevi chiesto: ' + attesa.richiesta));
    node.appendChild(el('div', 'redo-service'));
    paintWait(node, attesa, Date.now());
    return node;
  }

  /* L'orologio della pagina: aggiorna il cronometro e le frasi dei blocchi
     d'attesa una volta al secondo, senza ridisegnare le righe. */
  function tick(outlet) {
    var blocchi = outlet.querySelectorAll('.redo-wait');
    if (!blocchi.length || !stillHere()) {
      if (redo.orologio != null) { clearInterval(redo.orologio); redo.orologio = null; }
      return;
    }
    Array.prototype.forEach.call(blocchi, function (node) {
      paintWait(node, {
        avvio: Number(node.getAttribute('data-avvio')),
        scadenza: Number(node.getAttribute('data-scadenza')),
        ponte: !!node.getAttribute('data-ponte')
      }, Date.now());
    });
  }

  /* Siamo ancora su questa pagina? Il router non avvisa quando una route esce
     di scena (lo stesso giro di config/services-route.js). */
  function stillHere() {
    return String(window.location.hash || '').indexOf('#/constructions') === 0;
  }

  /* Cosa dire quando un rifacimento atteso non e' piu' in corso, guardando la
     riga com'e' adesso. `null` se c'e' ancora da aspettare. */
  function redoOutcome(c, all) {
    if (!c) return { testo: '' };
    if (redoWaiting(c)) return null;
    var r = c.rifacimento;
    var rifalla = '[data-rifalla="' + c.id + '"]';
    if (r && r.stato === 'scaduto') {
      return { testo: 'Ho smesso di aspettare. La proposta di prima resta com’era.',
               fuoco: rifalla, tieni: true };
    }
    if (r && (r.stato === 'fallito' || r.stato === 'illeggibile')) {
      return { testo: 'Non è stato possibile rifarla: riprova.', fuoco: rifalla, tieni: true };
    }
    if (c.stato === 'superata') {
      var giro = (c.giri || [])[(c.giri || []).length - 1] || {};
      var nata = all.filter(function (x) { return x.id === giro.proposta_id; })[0];
      return {
        testo: nata
          ? 'Al posto di questa ti propongo ' + domainName(nata).toLowerCase() + ' «' +
            objectName(nata) + '»: si può creare direttamente in Home Assistant. ' +
            'Guardala e approvala qui sotto.'
          : 'Al posto di questa c’è una proposta che HIRIS può costruire. Guardala e ' +
            'approvala qui sotto.',
        /* Sull'intestazione della nuova, non su «Approva»: prima di
           confermare va letta l'anteprima. */
        fuoco: nata ? '[data-proposta="' + nata.id + '"]' : null
      };
    }
    var ultimo = (c.giri || [])[(c.giri || []).length - 1] || {};
    if (ultimo.esito === 'niente') {
      return { testo: 'Con questa richiesta non ho trovato niente di sensato da proporre. ' +
                      'La proposta di prima resta com’era.', fuoco: rifalla, tieni: true };
    }
    return { testo: 'Ho rifatto la proposta.', fuoco: '[data-proposta="' + c.id + '"]' };
  }

  /* Dopo ogni disegno: chi aspettavo ha un esito? E serve rileggere? */
  function afterDraw(outlet, all, statusEl, reload) {
    Object.keys(redo.attesi).forEach(function (id) {
      var c = all.filter(function (x) { return x.id === id; })[0];
      var esito = redoOutcome(c, all);
      if (!esito) return;
      delete redo.attesi[id];
      if (!esito.tieni) delete redo.lasciate[id];
      if (statusEl && esito.testo) {
        statusEl.textContent = esito.testo + (redo.nota ? ' ' + redo.nota : '');
      }
      redo.nota = '';
      var bersaglio = esito.fuoco ? outlet.querySelector(esito.fuoco) : null;
      if (bersaglio) bersaglio.focus();
    });
    /* Una rilettura sola per le due attese della riga: il «Rifalla» sul
       ponte e l'automazione in preparazione (attori, Task 4.4 e 4.5; giro di
       revisione 68, G68-2). Tutte e due arrivano minuti dopo, e senza
       rileggere la riga resterebbe ferma finche' qualcuno non ricarica. */
    var inCorso = all.some(function (c) {
      return (c.rifacimento && c.rifacimento.stato === 'in_corso') ||
        c.in_preparazione === true;
    });
    all.forEach(function (c) {
      if (c.rifacimento && c.rifacimento.stato === 'in_corso') redo.attesi[c.id] = true;
    });
    if (inCorso && stillHere() && redo.giro == null) {
      redo.giro = setInterval(function () {
        if (!stillHere()) { stopPolling(); return; }
        reload({ seCambia: true });
      }, SOGLIE_ATTESA.rilettura);
    } else if (!inCorso && redo.giro != null) {
      stopPolling();
    }
    if (outlet.querySelector('.redo-wait') && redo.orologio == null) {
      redo.orologio = setInterval(function () { tick(outlet); }, 1000);
    }
  }

  function stopPolling() {
    if (redo.giro != null) { clearInterval(redo.giro); redo.giro = null; }
  }

  /* «Rifalla» apre un campo di testo con le richieste di modifica, e ripete
     il turno **senza limiti**: la si puo' far rifare finche' va bene
     (decisione del proprietario, 21/09/2026). Una richiesta che non e'
     andata a buon fine non si perde: il campo si riapre gia' compilato. */
  function redoControl(c, statusEl, reload) {
    var wrap = el('div');
    wrap.style.cssText = 'display:flex;flex-direction:column;gap:var(--sp-2)';
    var apri = el('button', 'btn btn-ghost', 'Rifalla');
    apri.type = 'button';
    apri.setAttribute('aria-expanded', 'false');
    apri.setAttribute('data-rifalla', c.id);
    wrap.appendChild(apri);
    apri.addEventListener('click', function () {
      if (apri.getAttribute('aria-expanded') === 'true') return;
      apri.setAttribute('aria-expanded', 'true');
      var campoId = 'rifalla-' + c.id;
      var etichetta = el('label', 'field-hint', 'Cosa cambiare');
      etichetta.setAttribute('for', campoId);
      var campo = el('textarea');
      campo.id = campoId;
      campo.rows = 3;
      campo.style.cssText = 'width:100%;max-width:420px';
      campo.value = (c.rifacimento && c.rifacimento.richiesta) || redo.lasciate[c.id] || '';
      var manda = el('button', 'btn btn-primary', 'Rifalla adesso');
      manda.type = 'button';
      manda.addEventListener('click', function () {
        var richiesta = (campo.value || '').trim();
        if (!richiesta) {
          if (statusEl) statusEl.textContent = 'Scrivi cosa vuoi cambiare.';
          return;
        }
        sendRedo(c, richiesta, statusEl, reload);
      });
      wrap.appendChild(etichetta);
      wrap.appendChild(campo);
      wrap.appendChild(manda);
      campo.focus();
    });
    return wrap;
  }

  function sendRedo(c, richiesta, statusEl, reload) {
    redo.catena[c.id] = { avvio: Date.now(), richiesta: richiesta };
    redo.attesi[c.id] = true;
    redo.lasciate[c.id] = richiesta;
    redo.nota = '';
    if (statusEl) statusEl.textContent = 'Rifacimento avviato.';
    reload();
    api('api/proposals/' + encodeURIComponent(c.id) + '/redo',
        { method: 'POST', body: JSON.stringify({ richiesta: richiesta }) })
      .then(function (r) {
        return r.json().then(function (b) { return { ok: r.ok, corpo: b }; },
                            function () { return { ok: r.ok, corpo: {} }; });
      }, function () { return { ok: false, corpo: {} }; })
      .then(function (esito) {
        delete redo.catena[c.id];
        if (!esito.ok) {
          /* Il motivo del server, alla lettera; il ripiego se non ne ha. */
          delete redo.attesi[c.id];
          reload();
          if (statusEl) {
            statusEl.textContent = (esito.corpo && esito.corpo.error) ||
              'Non è stato possibile rifarla: riprova.';
          }
          return;
        }
        /* Da quale porta e' passato questo giro (reperto C-5, 23/09/2026):
           sulla catena, quando il piano non ha potuto rispondere, il giro si
           e' pagato a consumo, e la frase arriva dal backend. */
        redo.nota = (esito.corpo && esito.corpo.nota) || '';
        reload();
      });
  }

  function line(c, statusEl, reload) {
    if (c.a_mano) return lineAMano(c, statusEl, reload);
    var box = el('div', 'construction construction--' + c.stato);
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-4) 0;' +
      'display:flex;flex-direction:column;gap:var(--sp-2)';

    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap';
    var nome = el('span', null, domainName(c) + ' «' + objectName(c) + '»');
    /* Il fuoco ci arriva quando un «Rifalla» la fa nascere (attori, Task 4.4). */
    nome.setAttribute('data-proposta', c.id);
    nome.tabIndex = -1;
    head.appendChild(nome);
    var bOperation = operationBadge(c);
    head.appendChild(el('span', 'agent-badge ' + bOperation.cls, bOperation.testo));
    head.appendChild(el('span', 'agent-badge ' + (STATE_BADGE[c.stato] || 'badge-off'),
      STATE_LABEL[c.stato] || c.stato));
    box.appendChild(head);
    var chi = requesterLine(c);
    if (chi) box.appendChild(chi);
    /* Nata da una proposta a mano con «Rendila automatica»: il legame lo dice
       il server, per id (`nata_da`). Testo di fuori: textContent. */
    if (c.nata_da) {
      box.appendChild(el('div', 'field-hint', 'Nata da: “' + (c.nata_da.testo || '') + '”'));
    }

    if (eraGiaLi(c)) {
      box.appendChild(el('div', 'field-hint', 'Questo oggetto esiste già in casa tua.'));
    }

    if (c.frase) {
      var phrase;
      if (isRestore(c)) {
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
      var helperName = (h.dati && h.dati.name) || '(senza nome)';
      box.appendChild(el('div', 'field-hint',
        'Nasce anche: ' + (h.dominio || '') + ' «' + helperName + '»'));
    });

    if (c.prima || c.dopo) box.appendChild(detailsDisclosure(c));

    /* motivo: MAI per `disdetta` -- vedi il commento di testa, `revisions.py`
       scrive la costante `REASON_DISDETTA` ("rifiutata dalla pagina") su ogni
       riga disdetta; le righe scritte prima del fix round 1 (col vecchio
       testo "rifiutata dal proprietario") si migrano una volta sola
       all'apertura dell'archivio (`_migration_3`), ma anche una non ancora
       migrata mostrerebbe la stessa faccia: mostrare `motivo` tornerebbe a
       far leggere la parola "rifiutata" su una riga che e' il "no" di chi
       costruisce. */
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
      var bConfirm = actionButton('confirm', 'Approva', 'btn btn-primary', c, statusEl, reload, pendingGroup);
      var bReject = actionButton('reject', 'Rifiuta', 'btn', c, statusEl, reload, pendingGroup);
      pendingGroup.push(bConfirm, bReject);
      actions.appendChild(bConfirm);
      actions.appendChild(bReject);
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

  /* Il 403 della pagina (spec 2026-09-26 §3): chi non costruisce ci arriva
     solo scrivendo l'indirizzo -- la voce di menu non c'e' -- e legge il
     motivo del SERVER, verbatim e via textContent, non un «riprova» che non
     servirebbe a niente. Lo storico non si mostra: e' la stessa coda. */
  function renderDenied(outlet, openBody, historyBody, reason) {
    clearEl(openBody);
    clearEl(historyBody);
    setHistoryCount(outlet, null);
    openBody.appendChild(el('p', 'proposals-error',
      reason || 'Questa pagina è di chi può costruire.'));
  }

  /* Il titolo di una sezione richiudibile: il bottone sta DENTRO l'`<h2>`,
     non al suo posto. Chi naviga per intestazioni continua a trovare la
     sezione, e un `<h2>` dentro un `<button>` sarebbe comunque HTML non
     valido (un bottone accetta solo contenuto di frase). L'etichetta non
     cambia fra aperto e chiuso -- porta il conteggio, che e' l'unica cosa
     visibile quando la sezione e' chiusa: lo stato lo dicono `aria-expanded`
     per chi ascolta e il triangolo di `.sc-toggle` per chi guarda. */
  function buildDisclosureTitle(toggleId, title, panel) {
    var btn = el('button', 'sc-toggle', title);
    btn.type = 'button';
    btn.id = toggleId;
    btn.setAttribute('aria-controls', panel.id);
    setDisclosure(btn, panel, false);
    /* Nasce chiusa a ogni montaggio, e lo stato non si ricorda fra una
       visita e l'altra: la domanda con cui si apre questa pagina e' «cosa
       aspetta una mia risposta», e deve avere la stessa risposta tutte le
       volte. */
    btn.addEventListener('click', function () {
      setDisclosure(btn, panel, btn.getAttribute('aria-expanded') !== 'true');
    });
    var heading = el('h2', 'sc-title');
    heading.appendChild(btn);
    return heading;
  }

  function buildSectionShell(num, idPrefix, title, toggleId) {
    var section = el('section', 'section-card');
    var body = el('div', 'sc-body');
    body.id = 'constructions-' + idPrefix + '-body';
    body.setAttribute('data-sezione', idPrefix);

    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(toggleId ? buildDisclosureTitle(toggleId, title, body)
      : el('h2', 'sc-title', title));
    section.appendChild(head);
    section.appendChild(body);
    return section;
  }

  /* Il conteggio dello storico vive nel titolo, e si sa solo DOPO la fetch:
     si scrive al render, non al montaggio -- da quando lo storico nasce
     chiuso, il titolo e' l'unica riga che si vede sempre. `null` quando non
     lo sappiamo (la lettura e' fallita): un numero vecchio lasciato li'
     direbbe una cosa falsa sul quando. */
  function setHistoryCount(outlet, n) {
    var btn = outlet.querySelector('#constructions-history-toggle');
    if (btn) btn.textContent = n == null ? 'Storico' : ('Storico (' + n + ')');
  }

  function draw(outlet, opts) {
    function reload(o) { return draw(outlet, o); }
    /* Una rilettura del giro del «Rifalla» non mostra «Caricamento…» e non
       ridisegna se niente e' cambiato: chi sta scrivendo nel campo di
       un'altra riga non deve perderlo ogni pochi secondi. */
    var quieta = !!(opts && opts.seCambia);

    var openBody = outlet.querySelector('#constructions-open-body');
    var historyBody = outlet.querySelector('#constructions-history-body');
    var statusEl = outlet.querySelector('#constructions-status');

    if (!openBody || !historyBody) {
      clearEl(outlet);
      outlet.appendChild(el('h1', 'page-title', 'Proposte'));
      outlet.appendChild(el('p', 'page-subtitle',
        'Le proposte di HIRIS per creare, modificare o cancellare automazioni, script e ' +
        'scene di questa casa — e cosa ne hai deciso.'));
      /* Una regione live, creata vuota prima di scriverci: senza, nessuna
         delle frasi che riceve -- esiti, errori, la nota sui soldi -- veniva
         annunciata (parere di ux-ui-specialist, 06/10/2026). */
      var status = el('p', 'sc-desc', '');
      status.id = 'constructions-status';
      /* Gli esiti dei comandi si annunciano qui, senza spostare il fuoco. */
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      outlet.appendChild(status);
      outlet.appendChild(buildSectionShell('01', 'open', 'In attesa'));
      /* Lo storico nasce chiuso: e' un registro di consultazione, non
         l'atterraggio -- la domanda con cui si apre questa pagina e' «cosa
         aspetta una mia risposta», ed e' la sezione 01. */
      outlet.appendChild(buildSectionShell('02', 'history', 'Storico',
        'constructions-history-toggle'));
      openBody = outlet.querySelector('#constructions-open-body');
      historyBody = outlet.querySelector('#constructions-history-body');
      statusEl = outlet.querySelector('#constructions-status');
    }

    if (!quieta) {
      clearEl(openBody); openBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
      clearEl(historyBody); historyBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    }

    return fetch('api/constructions').then(function (r) {
      if (r.status === 403) {
        return r.json().catch(function () { return {}; }).then(function (corpo) {
          return { negato: (corpo && corpo.error) || '' };
        });
      }
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      if (data && data.negato !== undefined) {
        renderDenied(outlet, openBody, historyBody, data.negato);
        return;
      }
      var all = (data && data.constructions) || [];
      var firma = JSON.stringify(all);
      if (quieta && firma === redo.ultima) return;
      redo.ultima = firma;
      var open = all.filter(function (c) { return c.sospesa === true; });
      var history = all.filter(function (c) { return c.sospesa !== true; });
      renderSection(openBody, open,
        'Nessuna proposta in attesa. Quando chiedi a HIRIS di creare, modificare o cancellare ' +
        'un’automazione, uno script o una scena, la trovi qui prima che diventi reale.',
        statusEl, reload, sortOpen);
      renderSection(historyBody, history, 'Nessuna costruzione nello storico.',
        statusEl, reload, sortHistory);
      setHistoryCount(outlet, history.length);
      afterDraw(outlet, all, statusEl, reload);
    }).catch(function () {
      /* Una rilettura persa non e' un guasto: al prossimo giro. */
      if (quieta) return;
      setHistoryCount(outlet, null);
      [openBody, historyBody].forEach(function (node) {
        renderError(node, 'Non è stato possibile leggere le costruzioni. Riprova più tardi.', reload);
      });
    });
  }

  function mount(outlet) {
    if (!outlet) return Promise.resolve();
    clearEl(outlet);
    return draw(outlet);
  }

  return { mount: mount };
})();
