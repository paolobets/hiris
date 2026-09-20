/* HIRIS · Configurazione · «L'osservatore» — cio' che le quattro schede
   condividono.

   Nasce dalla spec 2026-09-18: la pagina era un file solo da 2.243 righe e
   quattro sezioni in colonna. Qui vivono le cose che TUTTE e quattro usano --
   i tre toni, la costruzione del DOM, le due chiamate, i formati, il
   rivelatore, la dichiarazione di un riferimento tecnico e la riga «Letto
   alle ... · Aggiorna» (spec §2) -- perche' una seconda copia in due schede
   divergerebbe al primo ritocco (fondamenta 2).

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server -- stessa disciplina di tree-route.js/memory-route.js. L'unica cosa
   che scrive e' `write`, che porta `X-Requested-With` perche' passa dal
   `csrf_middleware`. */
window.HirisWatcherShared = (function () {
  'use strict';

  var TONE_PROBLEM = 'color:var(--err-ink)';
  var TONE_CALM = 'color:var(--text-3)';

  /* Il tono del terzo stato -- «non si puo' sapere» -- distinto sia dal calmo
     (un'assenza vera) sia dal problema (un guasto): lo stesso `TONE_UNKNOWN`
     di tree-route.js, per la stessa ragione (un `null` non e' un `[]`). */
  var TONE_UNKNOWN = 'color:var(--warn-ink)';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function clearEl(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function line(parent, text, style) {
    var p = el('p', 'sc-desc', text);
    if (style) p.style.cssText = style;
    parent.appendChild(p);
    return p;
  }

  /* Una scrittura: stessa forma di `read`, piu' l'intestazione che il
     prodotto usa gia' per le sue POST (`X-Requested-With`). Torna sempre
     l'esito letto, anche su un 400: e' li' che vive la ragione del rifiuto,
     e chi ha premuto salva deve leggerla. */
  function write(path, payload) {
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        return { ok: r.ok, status: r.status, corpo: body };
      });
    });
  }

  function read(path) {
    return fetch(path).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        return { ok: r.ok, status: r.status, corpo: body };
      });
    });
  }

  /* Ogni scheda ha piu' parti, e ciascuna una domanda diversa: un elenco di
     400 righe seguito da tre numeri senza un titolo in mezzo non si legge.
     Stesso stile di `.st-label` (hiris-config.css), che pero' vive solo dentro
     una `.stat-tile`: qui e' un `h3` vero, cosi' un lettore di schermo salta
     di parte in parte. */
  function subheading(body, text) {
    var h = el('h3', null, text);
    h.style.cssText = 'font-size:var(--fs-12);text-transform:uppercase;letter-spacing:0.06em;' +
      'color:var(--text-3);font-weight:600;margin:var(--sp-4) 0 var(--sp-2)';
    body.appendChild(h);
    return h;
  }

  /* Bottone «Riprova» (rilievo 4): era l'unica pagina di lettura senza,
     mentre l'errore piu' comune -- il riavvio dell'add-on -- e' esattamente
     transitorio. Stesso bottone delle sorelle (memory-/agenda-/
     constructions-route.js): `btn btn-ghost btn-sm`, rilancia `reload`. Il
     TESTO dei messaggi d'errore delle quattro schede non cambia (rilievo 4:
     "il migliore del pannello", non si riscrive). */
  function retryButton(body, reload) {
    var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
    retry.type = 'button';
    retry.addEventListener('click', reload);
    body.appendChild(retry);
  }

  /* ------------------------------------------------------------- i formati */

  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function isoData(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function ieriLocale() {
    var d = new Date();
    d.setDate(d.getDate() - 1);
    return isoData(d);
  }

  /* L'analisi e' di OGGI, non di ieri: legge i resoconti fino a ieri e parla
     adesso. Il selettore del giorno governa il resoconto, non lei. */
  function localOggi() { return isoData(new Date()); }

  /* Date sempre in gg/mm/aaaa nel testo (rilievo 5): `isoDay` arriva dal
     valore di `<input type=date>`, sempre `AAAA-MM-GG` per specifica HTML. */
  function ggMmAaaa(isoDay) {
    var parts = isoDay.split('-');
    if (parts.length !== 3) return isoDay;
    return parts[2] + '/' + parts[1] + '/' + parts[0];
  }

  function fmtTime(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + ' ' +
      pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  /* Data CON l'anno, a differenza di `fmtTime` («gg/mm hh:mm»): un episodio
     vive dentro il giorno che si sta guardando, una decisione dello scope o un
     obiettivo possono essere di mesi fa -- «e' datato, e la sua storia conta»
     (spec §11, conseguenza 1). Fuso del BROWSER, come tutto il resto della
     pagina. */
  function fmtWhenFull(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' +
      pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  /* Solo la DATA (senza l'ora): `proprietario` la vuole con l'anno
     («Corretto da te il gg/mm/aaaa», forma approvata punto 4) -- `fmtWhenFull`
     porta anche l'ora, che li' e' un dato in piu' da leggere. */
  function fmtDateOnly(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear();
  }

  /* Solo giorno/mese, SENZA anno: `altro` la vuole cosi' («Modificata a mano
     il gg/mm da {chi}», forma approvata punto 4) -- un'asimmetria scritta
     apposta nella forma approvata, non un refuso. */
  function fmtDayMonth(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1);
  }

  /* Secondi -> «7 giorni» / «84 ore», virgola italiana, al massimo un
     decimale: la finestra e la cadenza arrivano in secondi float
     (`finestra_s`/`cadenza_s`, `store.last_reconsideration`) e in secondi
     nessuno le legge. Si FORMATTA, non si arrotonda una seconda volta:
     `maximumFractionDigits: 1` e' un tetto, come in `fmtKwh`. */
  function fmtDays(seconds) {
    var days = seconds / 86400;
    return days.toLocaleString('it-IT', { maximumFractionDigits: 1 }) + (days === 1 ? ' giorno' : ' giorni');
  }

  function fmtHours(seconds) {
    var hours = seconds / 3600;
    return hours.toLocaleString('it-IT', { maximumFractionDigits: 1 }) + (hours === 1 ? ' ora' : ' ore');
  }

  /* Cifre intere, MAI abbreviate: `fmtNum` di config/api.js scrive «5.0k», e
     qui il numero esatto e' il punto (la promessa del -83% si verifica con
     «4.951», non con «5.0k»). `useGrouping: 'always'` perche' l'ICU
     dell'`it-IT` raggruppa solo da cinque cifre in su (misurato: 4951 ->
     «4951», 29227 -> «29.227»): sette barre una sopra l'altra devono
     leggersi con lo stesso separatore, e la spec stessa scrive «4.951». Un
     motore vecchio che non conosce 'always' lo legge come `true` (ToBoolean)
     e raggruppa comunque: nessun errore, al peggio «4951». */
  function fmtCount(n) {
    return n.toLocaleString('it-IT', { useGrouping: 'always' });
  }

  /* Una quota 0..1 (`_share`, 3 decimali nel backend) -> percentuale con un
     decimale e virgola italiana: "71,2%". */
  function fmtPercent(v) {
    if (v == null) return null;
    return (v * 100).toLocaleString('it-IT', { maximumFractionDigits: 1 }) + '%';
  }

  /* Secondi -> «3 minuti» / «2 ore» / «35 giorni». E' una DURATA, non un
     istante: `fmtWhenFull` risponde a «che giorno era», qui la domanda e' «da
     quanto». Stessa famiglia di `fmtHours`/`fmtDays` qui sopra, stessa virgola
     italiana.

     **Arriva fino ai giorni, e non e' zelo** (correzione della review
     indipendente, 11/09/2026): questo commento diceva che i tentativi «per
     costruzione sono recenti -- al massimo dieci, e il turno scade in dieci
     minuti», ed era falso due volte. La scadenza del piano e' configurabile
     fino a **120 minuti** (`api/handlers_models.py`), e soprattutto su una
     casa SANA un tentativo avviene a ogni CADENZA -- 84 ore su questa casa --
     quindi dieci righe sono piu' di un mese. Senza la soglia, la pagina
     scriveva «840 ore fa». */
  function fmtDuration(seconds) {
    if (seconds < 60) return 'meno di un minuto';
    if (seconds < 3600) {
      var minutes = Math.round(seconds / 60);
      return minutes + (minutes === 1 ? ' minuto' : ' minuti');
    }
    if (seconds < 48 * 3600) return fmtHours(seconds);
    return fmtDays(seconds);
  }

  function fmtAgo(ts) {
    return fmtDuration(Math.max(0, Date.now() / 1000 - ts)) + ' fa';
  }

  /* ------------------------------------------- i soggetti grezzi, letti */

  /* Il riconoscimento dei quattro prefissi tecnici (`problema:`/
     `integrazione:`/`log:`/`automazione:`) SEPARATO dalla resa: questa
     funzione dice solo COSA porta un soggetto grezzo, mai come scriverlo a
     schermo -- quello lo decide chi la chiama. E' la base condivisa fra le
     schede che rendono un soggetto (BACKLOG.md, collaudo del 07/09/2026: due
     elenchi sulla stessa pagina rendevano lo stesso soggetto in due modi, e
     uno stampava l'identificatore grezzo perche' nessuno gli aveva mai
     insegnato questi quattro prefissi). Un solo posto che li conosce, non due
     che potrebbero divergere al primo caso strano.

     Per `log:`, il soggetto porta DUE informazioni cucite con `@`
     (`<logger>@<file>:<riga>`): il logger e' il nome utile, il resto e' il
     riferimento tecnico che distingue due errori dello stesso logger --
     nessuno dei due si butta, li separa chi chiama. */
  function parseSubjectPrefix(s) {
    s = s || '';
    if (s.indexOf('problema:') === 0) {
      return { kind: 'problema', rest: s.slice('problema:'.length) };
    }
    if (s.indexOf('integrazione:') === 0) {
      return { kind: 'integrazione', rest: s.slice('integrazione:'.length) };
    }
    if (s.indexOf('log:') === 0) {
      var rest = s.slice('log:'.length);
      var at = rest.indexOf('@');
      return {
        kind: 'log',
        logger: at === -1 ? rest : rest.slice(0, at),
        location: at === -1 ? '' : rest.slice(at + 1),
      };
    }
    if (s.indexOf('automazione:') === 0) {
      return { kind: 'automazione', rest: s.slice('automazione:'.length) };
    }
    return { kind: null, rest: s };
  }

  /* Il gemello di `protagonistName` per «cosa sto guardando» (rilievo del
     collaudo E2, 07/09/2026): una voce li' non ha MAI un `corpo.titolo` da
     preferire (il tipo che arriva da `/api/mind/watching` e'
     `{soggetto, motivo, autore, da_quando_ts}`, punto), quindi non si puo' riusare
     `protagonistName` cosi' com'e' -- ma la legge resta la stessa: non
     inventare un nome che non c'e'. Se dal soggetto non si ricava altro
     (un'entita' dello scope, es. `light.cucina`), il soggetto STESSO
     resta intatto e si mostra -- **corretto il 07/09/2026 dalla fetta «il
     nome»**: prima questa riga diceva che era «gia' il nome leggibile», ed
     era falso. Un `entity_id` non e' un nome: e' un identificatore, e si
     mostra DICENDO che lo e' (`technical`, sotto).

     Ritorna `{primary, secondary, technical}`: `primary` e' cio' che una
     persona legge per primo, `secondary` (puo' essere vuoto) e' il
     riferimento tecnico che NON si butta -- e' cio' che distingue due voci
     altrimenti identiche (due errori dello stesso logger, due integrazioni
     non caricate) -- ma va reso in secondo piano, mai come unico contenuto
     della riga.

     `nome` (facoltativo) e' il nome amichevole SALVATO al momento del
     cambio (`corpo.nome`, da `mind/facts.py`; la colonna e'
     `friendly_name`, `mind/store.py::_migration_5`). Quando c'e' e' lui il
     nome primario, e l'`entity_id` scivola nel riferimento secondario --
     la stessa gerarchia contenuto/riferimento gia' usata da `balanceLine`
     con `corpo.dispositivo`.

     **`technical: true` significa che `primary` NON e' un nome: e' un
     identificatore.** E' la meta' che mancava (fetta «il nome»,
     07/09/2026): il soggetto grezzo resta intatto -- non si inventa mai un
     nome dall'id, `light.cucina_1` non diventa «Cucina 1» -- ma chi legge
     deve DIRLO, invece di lasciarlo passare per un nome. Chi rende decide
     come (`SUBJECT_IS_ID`, sotto), questa funzione decide soltanto se. Le
     righe scritte prima della colonna cadono qui, ed e' voluto: riempirle
     dall’anagrafe di oggi vorrebbe dire attribuire a ieri il nome di
     oggi. */
  function describeWatchedSubject(soggetto, nome) {
    var p = parseSubjectPrefix(soggetto);
    if (p.kind === 'problema') return { primary: 'Problema Home Assistant: ' + p.rest, secondary: '', technical: false };
    if (p.kind === 'integrazione') return { primary: 'Un’integrazione non caricata', secondary: p.rest, technical: false };
    if (p.kind === 'log') return { primary: 'Registro: ' + p.logger, secondary: p.location, technical: false };
    if (p.kind === 'automazione') return { primary: 'Automazione: ' + p.rest, secondary: '', technical: false };
    if (nome) return { primary: nome, secondary: p.rest, technical: false };
    return { primary: p.rest, secondary: '', technical: true };
  }

  /* La parola che DICHIARA un riferimento tecnico. Sta qui, in un posto
     solo, perche' le schede che rendono un soggetto devono dire la stessa
     cosa con le stesse parole: due letterali in due punti diversi
     divergerebbero al primo ritocco. Corta apposta -- e' un'etichetta accanto
     all'identificatore, non una frase: la riga deve restare leggibile anche
     quando si ripete su ogni voce di un elenco lungo. */
  var SUBJECT_IS_ID = 'identificatore:';

  /* R4 (revisione del tratto v3.22.2..HEAD): la stessa dichiarazione, detta
     UNA volta per un intero gruppo di «Cosa sto guardando» invece che su
     ogni riga (`renderDecisionGroup`, watcher-lavoro.js) -- stessa parola
     («identificatore») delle due forme qui sopra, cosi' chi legge non impara
     un terzo vocabolario per lo stesso fatto. */
  var SUBJECT_IS_ID_PLURAL = 'identificatori tecnici, non nomi';

  /* ------------------------------------------------ gli elenchi LUNGHI */

  /* Una forma sola per ogni elenco lungo della pagina (spec §6): riassunto coi
     numeri, i pochi che contano col loro criterio dichiarato, il resto dietro
     un bottone che lo costruisce **al clic**.

     **Misurato il 18/09/2026, ed e' la ragione per cui questo pezzo esiste**:
     la pagina scaricava 110 KB e disegnava oltre 500 righe in una colonna
     sola. Il 19/09 la sola cronaca ne aveva 93, i giudizi 121, i soggetti
     guardati 153, i lasciati fuori 280.

     Tre regole che non si vedono guardando una pagina corta:

     1. **si costruisce al clic**, non si nasconde: 280 righe disegnate e
        messe `hidden` costano lo stesso a chi le disegna;
     2. **a blocchi di cinquanta oltre le cento**, col fuoco sulla prima riga
        nuova -- altrimenti chi legge da tastiera torna in cima ogni volta;
     3. **bottone, non `summary`**: i `summary` di questa pagina sono alti
        21-23 px, sotto la soglia del tocco.

     Chi chiama porta i DATI e sa disegnarne uno (`rendi`); questo pezzo non
     sa cosa sia una riga, e non deve saperlo. */

  //: Quante righe nel primo blocco, e da quante in poi si va a blocchi
  //: (spec §6). Cinquanta e' quanto sta in una schermata scorrendo una volta.
  var BLOCCO = 50;
  var SOGLIA_BLOCCHI = 100;
  //: Sotto questa soglia un elenco senza «pochi» si disegna invece di
  //: chiudersi: un bottone «Vedi tutte (1)» e' un clic per niente, e il
  //: meccanismo e' per gli elenchi LUNGHI.
  var SOGLIA_CHIUSURA = 3;

  function elencoLungo(corpo, opzioni) {
    var tutti = opzioni.tutti || [];
    var pochi = opzioni.pochi || [];
    if (opzioni.riassunto) line(corpo, opzioni.riassunto, TONE_CALM);
    if (pochi.length) {
      /* Il criterio PRIMA delle righe: cinque righe scelte da noi, senza la
         frase che dice come, sembrerebbero le uniche cinque che esistono. */
      if (opzioni.didascalia) corpo.appendChild(el('div', 'field-hint', opzioni.didascalia));
      /* **La forma la decide chi chiama** (`classe`): le misure sono
         piastrelle in griglia, la cronaca righe in colonna. Questo pezzo
         governa il meccanismo -- riassunto, pochi, vedi tutti, blocchi -- non
         il vestito; cablarci una colonna vorrebbe dire che chi ha una griglia
         sceglie di non usarlo. */
      var cesto = opzioni.classe ? el('div', opzioni.classe) : corpo;
      pochi.forEach(function (d) { cesto.appendChild(opzioni.rendi(d)); });
      if (cesto !== corpo) corpo.appendChild(cesto);
    }
    if (tutti.length <= pochi.length) return;
    if (!pochi.length && tutti.length <= SOGLIA_CHIUSURA) {
      tutti.forEach(function (d) { corpo.appendChild(opzioni.rendi(d)); });
      return;
    }

    var etichetta = (opzioni.etichetta || 'Vedi tutti') + ' (' + fmtCount(tutti.length) + ')';
    var apri = el('button', 'btn btn-ghost long-list-btn', etichetta);
    apri.type = 'button';
    apri.setAttribute('aria-expanded', 'false');
    var elenco = el('div', 'long-list' + (opzioni.classe ? ' ' + opzioni.classe : ''));
    elenco.hidden = true;
    var disegnate = 0;

    /* Il titolo dell'elenco aperto: e' li' che va il fuoco, e non sulla prima
       riga -- chi usa uno screen reader deve sapere COSA si e' aperto prima
       di sentirne il contenuto. `tabindex=-1` perche' il fuoco ce lo mettiamo
       noi: non entra nella sequenza di tabulazione. */
    var titolo = el('h4', 'long-list-title', opzioni.titolo || etichetta);
    titolo.setAttribute('tabindex', '-1');

    function altre() {
      var fino = Math.min(disegnate + BLOCCO, tutti.length);
      var primaNuova = null;
      for (var i = disegnate; i < fino; i++) {
        var riga = opzioni.rendi(tutti[i]);
        if (primaNuova === null) primaNuova = riga;
        elenco.appendChild(riga);
      }
      disegnate = fino;
      return primaNuova;
    }

    var ancora = el('button', 'btn btn-ghost long-list-btn', '');
    ancora.type = 'button';
    function aggiornaAncora() {
      var restano = tutti.length - disegnate;
      ancora.hidden = restano <= 0;
      ancora.textContent = 'Altre ' + fmtCount(Math.min(BLOCCO, restano))
        + ' (ne restano ' + fmtCount(restano) + ')';
    }
    ancora.addEventListener('click', function () {
      var prima = altre();
      aggiornaAncora();
      /* Il fuoco sulla prima riga NUOVA: e' la riga da cui si riprende a
         leggere. Ha bisogno di `tabindex=-1` per poterlo ricevere. */
      if (prima) {
        prima.setAttribute('tabindex', '-1');
        prima.focus();
      }
    });

    apri.addEventListener('click', function () {
      var aperto = apri.getAttribute('aria-expanded') === 'true';
      if (aperto) {
        /* **Si svuota, non si nasconde**: cio' che si e' costruito al clic si
           disfa alla chiusura, o la seconda apertura di un elenco da 280
           righe le disegnerebbe una seconda volta sopra le prime. */
        clearEl(elenco);
        disegnate = 0;
        elenco.hidden = true;
        ancora.hidden = true;
        apri.setAttribute('aria-expanded', 'false');
        apri.focus();
        return;
      }
      elenco.appendChild(titolo);
      altre();
      if (tutti.length > SOGLIA_BLOCCHI) aggiornaAncora();
      else ancora.hidden = true;
      elenco.hidden = false;
      apri.setAttribute('aria-expanded', 'true');
      titolo.focus();
    });

    corpo.appendChild(apri);
    corpo.appendChild(elenco);
    corpo.appendChild(ancora);
  }

  /* ------------------------------------------------ gli elenchi che si aprono */

  /* Il rivelatore sincrono, estratto (correzione del giro del 07/09/2026):
     era duplicato letterale fra `detailsDisclosure` (comprimari/misure) e il
     rivelatore delle entita' di un bilancio -- STESSO bottone, STESSA logica
     open/close, STESSA disciplina "chiuso di default, i dati sono gia' nel
     payload" (mandato Task 7). Un secondo copia-incolla sarebbe il doppione
     che le fondamenta di questo prodotto vietano.
     `fillPanel(pannello)` scrive il contenuto specifico di ogni
     chiamante dentro il pannello gia' creato, chiuso, con lo stile giusto.

     `openByDefault` (11/09/2026) e' l'eccezione, e porta la sua ragione. La
     disciplina qui sopra -- «chiuso di default, i dati sono gia' nel payload»
     -- risponde alla domanda «questo va mostrato subito?» con «no, e' un
     dettaglio che chi vuole apre». Per i tentativi la risposta cambia, e non
     per capriccio: una serie di fallimenti e' un guasto IN CORSO che costa
     dati veri e per sempre (il cancello di cio' che HIRIS registra e' lo
     scope), e chi apre la pagina non deve andarselo a cercare. Resta chiuso
     in tutti gli altri casi, dove e' davvero un dettaglio. Un secondo
     rivelatore scritto apposta sarebbe il doppione che questa funzione esiste
     per togliere. */
  function createDisclosure(closedText, openText, fillPanel, openByDefault) {
    var wrap = el('div', 'field-group');
    var aperto = openByDefault === true;
    var btn = el('button', 'btn btn-ghost btn-sm', aperto ? openText : closedText);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', aperto ? 'true' : 'false');

    var panel = el('div');
    panel.hidden = !aperto;
    panel.style.cssText = 'margin-top:6px';
    fillPanel(panel);

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

  /* -------------------------------------------------- i campi di un modulo */

  /* Etichetta + campo, stessa forma micro del modulo di correzione di
     memory-route.js (`costruisciModuloCorrezione::field`) -- non condivisa
     fra i due file (non c'e' un modulo comune per questi helper di UI), ma
     la stessa disciplina visiva.

     **Fix round 1 (revisione Fable, IMPORTANT 2)**: l'etichetta non era
     ASSOCIATA al campo -- solo testo accanto, `for`/`id` mancanti. Un
     lettore di schermo su `select[aria-label]` la legge, ma un click
     sull'etichetta (o `input.labels[0]`) non trovava niente: il contratto
     HTML dell'etichetta era rotto anche se il nome accessibile "sembrava"
     esserci. Un contatore di modulo basta -- ogni chiamata di
     `judgmentField` in pagina (editor del genere per riga, modulo di
     aggiunta) ne apre uno nuovo, quindi gli `id` non collidono mai. */
  var judgmentFieldSeq = 0;

  function judgmentField(label, input) {
    var f = el('div');
    f.style.cssText = 'display:flex;flex-direction:column;gap:2px';
    if (!input.id) input.id = 'jr-field-' + (++judgmentFieldSeq);
    var l = el('label', null, label);
    l.htmlFor = input.id;
    l.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
    f.appendChild(l);
    f.appendChild(input);
    return f;
  }

  /* Testo del server -> DOM, MAI innerHTML: `**` si toglie, i backtick
     diventano `<code>` (forma approvata: «Le domande aperte»). */
  function appendMarkedText(parent, testo) {
    var pulito = String(testo || '').replace(/\*\*/g, '');
    var parti = pulito.split(/(`[^`]*`)/g);
    parti.forEach(function (parte) {
      if (parte.length >= 2 && parte.charAt(0) === '`' && parte.charAt(parte.length - 1) === '`') {
        parent.appendChild(el('code', null, parte.slice(1, -1)));
      } else if (parte) {
        parent.appendChild(document.createTextNode(parte));
      }
    });
  }

  function firstSentenceTruncated(testo, max) {
    var piano = String(testo || '').replace(/\*\*/g, '').replace(/`/g, '');
    var idx = piano.search(/[.!?]/);
    var frase = idx === -1 ? piano : piano.slice(0, idx + 1);
    if (frase.length > max) frase = frase.slice(0, max).replace(/\s+\S*$/, '') + '…';
    return frase;
  }

  /* ------------------------------------------------ la freschezza di un pannello */

  /* La riga di freschezza di un pannello (spec §2): «Letto alle 14:32 ·
     Aggiorna». Vive FUORI dal corpo che ogni scheda ripulisce a ogni lettura,
     altrimenti sparirebbe a ogni ricaricamento -- e' del pannello, non del
     contenuto. E' l'unico modo di rileggere: niente ricariche automatiche,
     cosi' cio' che si guarda non cambia sotto gli occhi.

     Nessun `aria-live` (spec §2): tre pannelli su quattro sono `hidden`, e una
     riga viva li' dentro verrebbe letta per una scheda che nessuno guarda. */
  function intestazioneFresca(pannello, ricarica) {
    var riga = el('div', 'watcher-fresh');
    var quando = el('span', 'field-hint', '');
    var aggiorna = el('button', 'btn btn-ghost btn-sm', 'Aggiorna');
    aggiorna.type = 'button';
    aggiorna.addEventListener('click', function () { ricarica(); });
    riga.appendChild(quando);
    riga.appendChild(aggiorna);
    pannello.appendChild(riga);
    return {
      riga: riga,
      segna: function (adesso) {
        var d = adesso || new Date();
        quando.textContent = 'Letto alle ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
      }
    };
  }

  return {
    TONE_PROBLEM: TONE_PROBLEM, TONE_CALM: TONE_CALM, TONE_UNKNOWN: TONE_UNKNOWN,
    SUBJECT_IS_ID: SUBJECT_IS_ID, SUBJECT_IS_ID_PLURAL: SUBJECT_IS_ID_PLURAL,
    el: el, clearEl: clearEl, line: line, subheading: subheading,
    read: read, write: write, retryButton: retryButton,
    createDisclosure: createDisclosure, intestazioneFresca: intestazioneFresca,
    elencoLungo: elencoLungo,
    describeWatchedSubject: describeWatchedSubject, parseSubjectPrefix: parseSubjectPrefix,
    judgmentField: judgmentField, appendMarkedText: appendMarkedText,
    firstSentenceTruncated: firstSentenceTruncated,
    pad2: pad2, isoData: isoData, ieriLocale: ieriLocale, localOggi: localOggi,
    ggMmAaaa: ggMmAaaa, fmtTime: fmtTime, fmtWhenFull: fmtWhenFull,
    fmtDays: fmtDays, fmtHours: fmtHours, fmtCount: fmtCount, fmtPercent: fmtPercent,
    fmtDuration: fmtDuration, fmtAgo: fmtAgo,
    fmtDateOnly: fmtDateOnly, fmtDayMonth: fmtDayMonth
  };
})();
