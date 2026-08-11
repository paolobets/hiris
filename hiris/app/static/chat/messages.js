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
    fermaAttesa(row);
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
         cambia DENTRO la regione, senza altro codice. Subito dopo i due
         attributi escono, perche' una bolla di risposta che resta live
         farebbe riannunciare qualunque cosa la tocchi in seguito. La
         rimozione e' rimandata di un giro dell'event loop: toglierli nello
         stesso istante in cui cambia il testo significa toglierli prima che
         l'annuncio parta. */
      if (bubble.getAttribute('role') === 'status') {
        setTimeout(function () {
          bubble.removeAttribute('role');
          bubble.removeAttribute('aria-live');
        }, 0);
      }
    }
    var timeEl = row.querySelector('.msg-time');
    if (timeEl && !timeEl.textContent) timeEl.textContent = nowHHMM();
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
  }

  function appendDebug(tools) {
    var row = document.createElement('div');
    row.className = 'debug-row';
    /* Render tool calls as inline mono chips. Click to expand/collapse the args. */
    var chips = tools.map(function(t) {
      // Defensive: never let a malformed debug payload throw here -- an
      // exception would be swallowed by sendMessage()'s catch and
      // mislabeled as a connection error, AFTER the answer already rendered.
      if (!t || typeof t !== 'object') return '';
      var inp = JSON.stringify(t.input !== undefined && t.input !== null ? t.input : {});
      return '<button class="tool-chip" data-args="' + esc(inp) + '" type="button">'
           + '<svg viewBox="0 0 24 24" class="tc-ic" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
           + '<span class="tc-name">' + esc(t.tool || '') + '</span>'
           + '</button>';
    }).filter(Boolean).join('');
    row.innerHTML = '<div class="tool-chips">' + chips + '</div><div class="tool-args" style="display:none"></div>';
    /* Toggle args panel on chip click */
    row.querySelectorAll('.tool-chip').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var panel = row.querySelector('.tool-args');
        var args = btn.getAttribute('data-args');
        var name = btn.querySelector('.tc-name').textContent;
        var open = panel.dataset.openName === name && panel.style.display !== 'none';
        if (open) {
          panel.style.display = 'none';
          panel.dataset.openName = '';
        } else {
          panel.innerHTML = '<code><b>' + esc(name) + '</b>(' + esc(args) + ')</code>';
          panel.style.display = '';
          panel.dataset.openName = name;
        }
      });
    });
    state.els.messages.appendChild(row);
  }

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

  /* Le soglie dell'attesa, in millisecondi, in un posto solo. Sono calibrate
     sulla letteratura (i 10 secondi oltre i quali l'attenzione si stacca) e
     NON su tempi di risposta misurati su questo prodotto: nessuno li ha
     ancora raccolti. Dopo l'UAT, con la distribuzione vera in mano, cambiarle
     e' una riga qui dentro e nient'altro. */
  var SOGLIE_ATTESA = {
    /* compare il cronometro */
    timer: 10000,
    /* l'etichetta ammette che ci sta mettendo troppo */
    lenta: 30000,
    /* compare la riga che dice che fine fa il turno */
    servizio: 120000,
    /* avvisa che sta per arrendersi (CHAT_POLL_MAX_MS meno mezzo minuto) */
    quasiResa: 270000
  };

  var ETICHETTA_ATTESA = 'HIRIS sta elaborando';
  var ETICHETTA_LENTA = 'Ci sto mettendo più del solito';
  var ETICHETTA_QUASI_RESA = 'Ancora niente: fra poco smetto di aspettare';

  /* Le due frasi dei due minuti dicono cose OPPOSTE su che fine fa il turno se
     l'utente se ne va, e la differenza non e' di stile: e' verificata sul
     server.
       - Turno servito dal ponte (HTTP 202 + job_id): `_enqueue_chat_job`
         scrive il messaggio dell'utente in chat_store PRIMA di accodare, e la
         risposta ci finisce quando il runner la consegna
         (`server.py::_submit_chat_reply`), senza che la pagina c'entri.
         Chiudere non perde niente: al caricamento dopo, `restore()` la rilegge
         da `GET api/chat/cronologia`.
       - Turno servito direttamente: l'intero scambio viene scritto
         (`handlers_chat.handle_chat`) solo alla fine, sulla stessa richiesta
         HTTP che la pagina sta aspettando. Se la pagina se ne va, quella
         richiesta cade e non c'e' nessuno a raccogliere la risposta.
     Promettere «puoi chiudere» su un turno diretto sarebbe una bugia;
     promettere «non chiudere» su un turno del ponte sarebbe una paura
     inventata. L'aspetto dell'indicatore resta identico nei due casi: cambia
     una frase, e cambia perche' il fatto e' diverso. */
  var SERVIZIO_TIENI_APERTO = 'Le risposte lunghe possono richiedere qualche minuto. Tieni aperta questa pagina: se la chiudi, questa risposta si perde.';
  var SERVIZIO_AL_SICURO = 'Le risposte lunghe possono richiedere qualche minuto. Puoi anche chiudere: la risposta finisce nella cronologia e la ritrovi qui.';

  /* Tutte le attese vive, per poterle fermare anche quando la riga che le
     ospita viene buttata via senza passare da updateBubble(). */
  var attese = [];

  function fermaAttesa(row) {
    if (!row || !row._attesa) return;
    var a = row._attesa;
    if (a.intervallo) clearInterval(a.intervallo);
    for (var i = 0; i < a.timeout.length; i++) clearTimeout(a.timeout[i]);
    row._attesa = null;
    var pos = attese.indexOf(row);
    if (pos >= 0) attese.splice(pos, 1);
  }

  /* Chiamata da chi svuota la conversazione: senza, i cronometri delle righe
     appena cancellate continuavano a girare su nodi che non esistono piu'. */
  function fermaTutteLeAttese() {
    while (attese.length) fermaAttesa(attese[attese.length - 1]);
  }

  /* Dichiara che QUESTO turno e' gia' al sicuro sul server: lo chiama
     chat/send.js quando il backend risponde 202 con un job_id. Cambia solo la
     frase di servizio dei due minuti (vedi sopra), niente altro. */
  function attesaAlSicuroSulServer(row) {
    if (row && row._attesa) row._attesa.alSicuro = true;
  }

  function testoCronometro(ms) {
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
            '<span class="tl-label">' + ETICHETTA_ATTESA + '</span>' +
            '<span class="tl-dots" aria-hidden="true"><i></i><i></i><i></i></span>' +
          '</div>' +
        '</div>' +
        '<div class="msg-time"></div>' +
      '</div>';
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;

    var avvio = Date.now();
    var bolla = row.querySelector('.bubble');
    var etichetta = row.querySelector('.tl-label');
    row._attesa = { avvio: avvio, timeout: [], intervallo: null, alSicuro: false };
    attese.push(row);

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
      el.textContent = testoCronometro(Date.now() - avvio);
      bolla.appendChild(el);
      state.els.messages.scrollTop = state.els.messages.scrollHeight;
      row._attesa.intervallo = setInterval(function () {
        el.textContent = testoCronometro(Date.now() - avvio);
      }, 1000);
    }, SOGLIE_ATTESA.timer));

    /* Dichiarare l'anomalia invece di far finta di niente. Nessuna barra di
       avanzamento: non c'e' nessun avanzamento da mostrare, e inventarlo
       sarebbe esattamente la bugia che questo prodotto non racconta. */
    row._attesa.timeout.push(setTimeout(function () {
      if (row._attesa) etichetta.textContent = ETICHETTA_LENTA;
    }, SOGLIE_ATTESA.lenta));

    row._attesa.timeout.push(setTimeout(function () {
      if (!row._attesa) return;
      var riga = document.createElement('div');
      riga.className = 'tl-servizio';
      riga.textContent = row._attesa.alSicuro ? SERVIZIO_AL_SICURO : SERVIZIO_TIENI_APERTO;
      bolla.appendChild(riga);
      state.els.messages.scrollTop = state.els.messages.scrollHeight;
    }, SOGLIE_ATTESA.servizio));

    /* Un fallimento annunciato non e' un fallimento improvviso. */
    row._attesa.timeout.push(setTimeout(function () {
      if (row._attesa) etichetta.textContent = ETICHETTA_QUASI_RESA;
    }, SOGLIE_ATTESA.quasiResa));

    return row;
  }

  window.HirisChatMessages = {
    appendMsg: appendMsg,
    updateBubble: updateBubble,
    appendDebug: appendDebug,
    showThinking: showThinking,
    attesaAlSicuroSulServer: attesaAlSicuroSulServer,
    fermaTutteLeAttese: fermaTutteLeAttese,
    SOGLIE_ATTESA: SOGLIE_ATTESA,
  };
})();
