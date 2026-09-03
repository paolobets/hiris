/* HIRIS · Chat page · message rendering (SP-4 Fase B Task 8)
   Bubble rendering, inline markdown-lite formatting, tool-call debug chips e
   l'UNICO indicatore d'attesa del prodotto (erano tre; vedi il blocco in
   fondo). Uses the shared esc() from config/api.js (the page's private copy
   was removed by this rebuild -- see task-8-report.md). */
(function() {
  var state = window.HirisChatState;

  function nowHHMM() {
    return new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  }

  function formatContent(text) {
    return esc(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code style="font-family:var(--font-mono);font-size:12.5px;background:var(--surface-2);padding:1px 5px;border-radius:4px;border:1px solid var(--border)">$1</code>')
      .replace(/\n/g, '<br>');
  }

  function appendMsg(role, text) {
    if (!state.hasMessages) { state.els.welcome.style.display = 'none'; state.hasMessages = true; }
    var row = document.createElement('div');
    row.className = 'msg-row ' + role;
    var time = nowHHMM();
    var content = formatContent(text);
    if (role === 'assistant') {
      row.innerHTML =
        '<div class="avatar">' + state.HIRIS_AVATAR + '</div>' +
        '<div class="msg-col"><div class="bubble">' + content + '</div><div class="msg-time">' + time + '</div></div>';
    } else {
      row.innerHTML =
        '<div class="msg-col"><div class="bubble">' + content + '</div><div class="msg-time">' + time + '</div></div>' +
        '<div class="avatar user">io</div>';
    }
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
    return row;
  }

  function updateBubble(row, text) {
    if (!row) return;
    /* Era la bolla dell'attesa: ferma cronometro e cambi d'etichetta prima di
       scriverci dentro la risposta vera. */
    stopWait(row);
    /* La riga potrebbe non essere piu' nel documento -- succedeva quando si
       svuotava la conversazione mentre HIRIS elaborava: la risposta veniva
       scritta dentro un nodo staccato dal DOM e l'utente non la vedeva mai,
       benche' fosse gia' stata pagata in token. Se e' successo, la risposta
       torna in fondo alla conversazione invece di finire nel vuoto. */
    if (!row.parentNode && state.els.messages) {
      if (!state.hasMessages && state.els.welcome) {
        state.els.welcome.style.display = 'none';
        state.hasMessages = true;
      }
      state.els.messages.appendChild(row);
    }
    var bubble = row.querySelector('.bubble');
    if (bubble) {
      bubble.classList.remove('thinking-live');
      bubble.innerHTML = formatContent(text);
      /* La bolla era una regione live (`role="status"`), ed e' cosi' che la
         risposta viene annunciata a chi usa uno screen reader: il contenuto
         cambia DENTRO la regione, senza altro codice. I due attributi poi
         escono, perche' una bolla di risposta che resta live farebbe
         riannunciare qualunque cosa la tocchi in seguito.

         Il ritardo era di un giro dell'event loop (`setTimeout(…, 0)`) e NON
         BASTAVA. Questo e' MISURATO, in Chromium con l'accessibilita' forzata:
         subito dopo il cambio di testo gli attributi c'erano ancora, ma al
         primo fotogramma erano gia' spariti e l'albero di accessibilita'
         esponeva la bolla come `generic`, con zero proprieta' live. Chrome
         smaltisce gli eventi delle regioni live durante l'aggiornamento del
         ciclo di vita del documento -- al fotogramma dopo la modifica, e
         leggendo lo stato di allora: togliere gli attributi prima uccide
         proprio l'annuncio che C6 doveva ottenere.

         Il valore, invece, e' SCELTO, e la distinzione conta. Scansione dei
         ritardi su questa macchina: fino a 33 ms la bolla resta `generic`, da
         50 ms in su e' `status` con `live: polite` -- la soglia sta fra i due,
         due o tre fotogrammi (un revisore indipendente, su un'altra macchina,
         l'ha trovata fra 16 e 33). 1200 ms non e' quella soglia: e' un margine
         largo ~24-36 volte, preso apposta perche' il bersaglio di questo
         frontend sono tablet vecchi, dove un fotogramma dura molto di piu' e
         uno screen reader smaltisce con calma. Il margine non costa niente:
         `updateBubble` gira una volta per turno, non c'e' streaming, quindi
         non esiste il rischio di riannunci -- e 1,2 s restano molto meno del
         tempo che serve a leggere una risposta. */
      if (bubble.getAttribute('role') === 'status') {
        setTimeout(function () {
          bubble.removeAttribute('role');
          bubble.removeAttribute('aria-live');
        }, WAIT_THRESHOLDS.uscitaRegioneLive);
      }
    }
    var timeEl = row.querySelector('.msg-time');
    if (timeEl && !timeEl.textContent) timeEl.textContent = nowHHMM();
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
  }

  /* La nota di una risposta: un fatto sulla risposta che si sta leggendo, non
     una riga di registro. Dichiara che il turno ha RIPIEGATO -- il Piano
     Claude Max non ha risposto, e ha risposto qualcun altro, con la sua natura
     (a consumo / in casa). Il testo arriva GIA' SCRITTO dal server
     (`model_resolution.downgrade_note`): qui non si compone niente, per la
     stessa ragione per cui la pagina Modelli non compone le sue frasi -- sono
     affermazioni sul prodotto, e due posti che le fanno prima o poi ne fanno
     due diverse.

     Sta DENTRO la riga della bolla, e precisamente dentro `.msg-col`, subito
     dopo la bolla: `.msg-row` e' un flex ORIZZONTALE (avatar | colonna), e un
     figlio diretto finirebbe accanto alla bolla invece che sotto. Non e' un
     `appendDebug`, che crea una riga propria per i chip degli strumenti: la
     nota appartiene a QUELLA risposta e a nessun'altra.

     textContent, mai innerHTML: il testo viene dal server. */
  function appendNote(row, text) {
    if (!row || !text) return;
    var note = document.createElement('div');
    note.className = 'msg-note';
    note.textContent = text;
    var col = row.querySelector('.msg-col');
    var bubble = col && col.querySelector('.bubble');
    if (bubble && bubble.nextSibling) {
      col.insertBefore(note, bubble.nextSibling);
    } else {
      (col || row).appendChild(note);
    }
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
  }

  /* `appendDebug` E' USCITA (17 agosto 2026). Disegnava una targhetta per
     ogni strumento chiamato, col nome e -- al click -- con gli ARGOMENTI, che
     per `remember` sono il testo del ricordo e per `esegui`/`cerca` sono gli id
     delle entita' di casa.

     Era nata per rendere osservabile una scrittura di `remember`, e quella
     ragione resta valida: l'osservabilita' non e' stata tolta, e' stata
     SPOSTATA nei log a livello debug del backend (`api/handlers_chat.py`).
     Toglierla senza spostarla avrebbe distrutto la capacita' per cui esisteva.

     Con lei sono uscite `.debug-row`, `.tool-chips`, `.tool-chip`, `.tc-ic`,
     `.tc-name` e `.tool-args` da `hiris-chat.css`: nessun altro le usa. */

  /* ── L'attesa ────────────────────────────────────────────────────
     C'era piu' di un indicatore, e quale vedessi dipendeva da come il server
     aveva smaltito il turno: risposta diretta -> un prompt di terminale con
     barrette monospace e la parola «elaboro»; risposta via abbonamento -> il
     logo che pulsa con «HIRIS sta elaborando». Due estetiche e due parole per
     la stessa identica domanda, su una differenza che l'utente non sceglie e
     non deve nemmeno vedere. Ne resta uno, per tutti i modelli e per tutti i
     percorsi.

     Il movimento e' tutto CSS (hiris-chat.css): da qui non esce nessun
     `setInterval` che ridipinge colori. L'unico timer di JavaScript e' quello
     che scrive `m:ss`, ed e' inevitabile -- ma parte solo dopo la prima
     soglia, e viene fermato su OGNI uscita. */

  /* Le durate dell'attesa, in millisecondi, in un posto solo. Le prime tre --
     quelle che l'utente vive come attesa -- sono calibrate sulla letteratura
     (i 10 secondi oltre i quali l'attenzione si stacca) e NON su tempi di
     risposta misurati su questo prodotto: nessuno li ha ancora raccolti. Dopo
     l'UAT, con la distribuzione vera in mano, cambiarle e' una riga qui dentro
     e nient'altro. Le ultime due hanno una provenienza diversa, dichiarata
     accanto a ciascuna. */
  var WAIT_THRESHOLDS = {
    /* compare il cronometro */
    timer: 10000,
    /* l'etichetta ammette che ci sta mettendo troppo */
    lenta: 30000,
    /* compare la riga che dice che fine fa il turno */
    servizio: 120000,
    /* Quanto PRIMA della scadenza avvisare che sta per arrendersi. La scadenza
       non e' scritta qui: la porta chi ce l'ha davvero, cioe' chat/send.js, e
       arriva insieme al fatto che il turno e' al sicuro sul server (vedi
       `waitSafeOnServer`). Qui c'era un `270000` con scritto accanto
       "CHAT_POLL_MAX_MS meno mezzo minuto": un secondo numero, in un secondo
       file, che dichiarava un legame inesistente -- bastava cambiare la
       scadenza vera perche' l'avviso mentisse in silenzio. */
    margineResa: 30000,
    /* E quando dirlo dove una scadenza non esiste proprio. Questo numero e'
       arbitrario e lo dichiara: non c'e' niente da cui derivarlo. */
    senzaScadenza: 270000,
    /* Quanto la bolla resta una regione live DOPO che ci e' stata scritta
       dentro la risposta (vedi updateBubble). Sta qui con le altre durate
       dell'attesa perche' e' l'ultimo atto della stessa vita: l'indicatore che
       diventa risposta. */
    uscitaRegioneLive: 1200
  };

  var WAIT_LABEL = 'HIRIS sta elaborando';
  var SLOW_LABEL = 'Ci sto mettendo più del solito';
  /* Due finali diversi, per la stessa ragione delle due frasi di servizio qui
     sotto: su un percorso una resa esiste, sull'altro no.
       - il ramo del ponte ha una scadenza vera (`CHAT_POLL_MAX_MS`, chat/send.js):
         il poll smette e la bolla lo dice. Annunciarlo prima e' corretto -- un
         fallimento annunciato non e' un fallimento improvviso.
       - il ramo diretto NON ha nessuna scadenza: la `fetch` di send.js non ha
         ne un `AbortController` ne un timeout, quindi la pagina aspetta finche
         la risposta arriva o la connessione cade. Dire li "fra poco smetto di
         aspettare" era una promessa che nessuno avrebbe mantenuto, scritta
         nell'istante in cui l'utente decide se abbandonare. */
  var ALMOST_GIVING_UP_LABEL = 'Ancora niente: fra poco smetto di aspettare';
  var NO_DEADLINE_LABEL = 'Ancora niente. Continuo ad aspettare: su questo turno non ho un tempo massimo.';

  /* Le due frasi dei due minuti dicono cose OPPOSTE su che fine fa il turno se
     l'utente se ne va, e la differenza non e' di stile: e' verificata sul
     server.
       - Turno servito dal ponte (HTTP 202 + job_id): `_enqueue_chat_job`
         scrive il messaggio dell'utente in chat_store PRIMA di accodare, e la
         risposta ci finisce quando il runner la consegna
         (`server.py::_submit_chat_reply`), senza che la pagina c'entri.
         Chiudere non perde niente: al caricamento dopo, `restore()` la rilegge
         da `GET api/chat/history`.
       - Turno servito direttamente: l'intero scambio viene scritto
         (`handlers_chat.handle_chat`) solo alla fine, sulla stessa richiesta
         HTTP che la pagina sta aspettando. Se la pagina se ne va, quella
         richiesta cade e non c'e' nessuno a raccogliere la risposta.
     Promettere «puoi chiudere» su un turno diretto sarebbe una bugia;
     promettere «non chiudere» su un turno del ponte sarebbe una paura
     inventata. L'aspetto dell'indicatore resta identico nei due casi: cambia
     una frase, e cambia perche' il fatto e' diverso. */
  var KEEP_OPEN_NOTICE = 'Le risposte lunghe possono richiedere qualche minuto. Tieni aperta questa pagina: se la chiudi, questa risposta si perde.';
  /* Il "se arriva" non e' timidezza: `_submit_chat_reply` (server.py) scarta in
     silenzio una risposta vuota o tossica, e il job ha una scadenza sua
     (`BRIDGE_DEADLINE_MIN`). La cronologia raccoglie la risposta se la risposta
     c'e', ed e' esattamente quel che il messaggio dei cinque minuti dice gia. */
  var SAFE_ON_SERVER_NOTICE = 'Le risposte lunghe possono richiedere qualche minuto. Puoi anche chiudere: se arriva, la risposta finisce nella cronologia e la ritrovi qui.';

  /* Tutte le attese vive, per poterle fermare anche quando la riga che le
     ospita viene buttata via senza passare da updateBubble(). */
  var waits = [];

  function stopWait(row) {
    if (!row || !row._attesa) return;
    var a = row._attesa;
    if (a.intervallo) clearInterval(a.intervallo);
    for (var i = 0; i < a.timeout.length; i++) clearTimeout(a.timeout[i]);
    row._attesa = null;
    var pos = waits.indexOf(row);
    if (pos >= 0) waits.splice(pos, 1);
  }

  /* Chiamata da chi svuota la conversazione: senza, i cronometri delle righe
     appena cancellate continuavano a girare su nodi che non esistono piu'. */
  function stopAllWaits() {
    while (waits.length) stopWait(waits[waits.length - 1]);
  }

  /* Dichiara che QUESTO turno e' gia' al sicuro sul server, e per quanto tempo
     la pagina continuera' a chiederne notizia. Lo chiama chat/send.js quando il
     backend risponde 202 con un job_id, passando la propria `CHAT_POLL_MAX_MS`:
     e' l'unico posto in cui quella scadenza esiste, e da qui in poi l'indicatore
     non ne tiene una copia da mantenere allineata. Due conseguenze, entrambe
     sul VERO: la frase dei due minuti dice che si puo' chiudere, e l'avviso di
     resa viene programmato -- perche' su questo percorso una resa c'e'. */
  function waitSafeOnServer(row, deadlineMs) {
    if (!row || !row._attesa) return;
    row._attesa.safeOnServer = true;
    if (!deadlineMs) return;
    row._attesa.scadenza = deadlineMs;
    var fraQuanto = deadlineMs - WAIT_THRESHOLDS.margineResa - (Date.now() - row._attesa.avvio);
    row._attesa.timeout.push(setTimeout(function () {
      if (!row._attesa) return;
      var label = row.querySelector('.tl-label');
      if (label) label.textContent = ALMOST_GIVING_UP_LABEL;
    }, Math.max(0, fraQuanto)));
  }

  function stopwatchText(ms) {
    var s = Math.floor(ms / 1000);
    var ss = s % 60;
    return Math.floor(s / 60) + ':' + (ss < 10 ? '0' + ss : ss);
  }

  function showThinking() {
    /* Contenuto statico (nessun input utente) -> innerHTML sicuro. */
    if (!state.hasMessages) { state.els.welcome.style.display = 'none'; state.hasMessages = true; }
    var row = document.createElement('div');
    row.className = 'msg-row assistant';
    row.innerHTML =
      /* logo e puntini sono decorazione: uno screen reader non deve leggerli */
      '<div class="avatar thinking-logo" aria-hidden="true">' + state.HIRIS_AVATAR + '</div>' +
      '<div class="msg-col">' +
        /* La bolla e' una regione live: senza, chi usa uno screen reader manda
           il messaggio e poi non riceve nessun annuncio, per minuti. E' la
           STESSA bolla in cui verra' scritta la risposta, quindi anche la
           risposta si annuncia da sola (vedi updateBubble). */
        '<div class="bubble thinking-live" role="status" aria-live="polite">' +
          '<div class="tl-top">' +
            '<span class="tl-label">' + WAIT_LABEL + '</span>' +
            '<span class="tl-dots" aria-hidden="true"><i></i><i></i><i></i></span>' +
          '</div>' +
        '</div>' +
        '<div class="msg-time"></div>' +
      '</div>';
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;

    var start = Date.now();
    var bubble = row.querySelector('.bubble');
    var label = row.querySelector('.tl-label');
    row._attesa = { avvio: start, timeout: [], intervallo: null, safeOnServer: false, scadenza: 0 };
    waits.push(row);

    /* Il cronometro NON parte subito. Sotto i dieci secondi il tempo non e'
       informazione: e' solo una risposta rapida trasformata in una risposta
       cronometrata. Quando compare, mostra i secondi VERI trascorsi dall'invio
       (0:10), non riparte da zero. */
    row._attesa.timeout.push(setTimeout(function () {
      if (!row._attesa) return;
      var el = document.createElement('div');
      el.className = 'thinking-timer';
      /* un m:ss dentro una regione live verrebbe letto ogni secondo: il tempo
         e' informazione per l'occhio, non per l'orecchio */
      el.setAttribute('aria-hidden', 'true');
      el.textContent = stopwatchText(Date.now() - start);
      bubble.appendChild(el);
      state.els.messages.scrollTop = state.els.messages.scrollHeight;
      row._attesa.intervallo = setInterval(function () {
        el.textContent = stopwatchText(Date.now() - start);
      }, 1000);
    }, WAIT_THRESHOLDS.timer));

    /* Dichiarare l'anomalia invece di far finta di niente. Nessuna barra di
       avanzamento: non c'e' nessun avanzamento da mostrare, e inventarlo
       sarebbe esattamente la bugia che questo prodotto non racconta. */
    row._attesa.timeout.push(setTimeout(function () {
      if (row._attesa) label.textContent = SLOW_LABEL;
    }, WAIT_THRESHOLDS.lenta));

    row._attesa.timeout.push(setTimeout(function () {
      if (!row._attesa) return;
      var line = document.createElement('div');
      line.className = 'tl-service';
      line.textContent = row._attesa.safeOnServer ? SAFE_ON_SERVER_NOTICE : KEEP_OPEN_NOTICE;
      bubble.appendChild(line);
      state.els.messages.scrollTop = state.els.messages.scrollHeight;
    }, WAIT_THRESHOLDS.servizio));

    /* L'avviso di resa NON si programma qui: qui non si sa ancora se una resa
       esistera'. Lo programma `waitSafeOnServer` quando il ponte porta
       la sua scadenza. Questo timer copre il caso opposto -- nessuna scadenza,
       cioe' il percorso diretto -- e dice quello, invece di promettere una fine
       che non arrivera'. Se la scadenza nel frattempo e' arrivata, tace: ne
       parla l'altro. */
    row._attesa.timeout.push(setTimeout(function () {
      if (!row._attesa || row._attesa.scadenza) return;
      label.textContent = NO_DEADLINE_LABEL;
    }, WAIT_THRESHOLDS.senzaScadenza));

    return row;
  }

  window.HirisChatMessages = {
    appendMsg: appendMsg,
    updateBubble: updateBubble,
    appendNote: appendNote,
    showThinking: showThinking,
    waitSafeOnServer: waitSafeOnServer,
    stopAllWaits: stopAllWaits,
    SOGLIE_ATTESA: WAIT_THRESHOLDS,
  };
})();
