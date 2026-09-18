/* HIRIS · Configurazione · «L'osservatore» (route #/watcher)

   La faccia dei tre attori (docs/design/2026-09-10-i-tre-attori.md). Tre
   sezioni, e ognuna e' un attore:

     01  cosa si guarda, da quando, perche' -- e **l'obiettivo**, che si
         scrive da qui: e' la sola manopola del prodotto, e da quella frase
         dipendono cosa l'osservatore guarda, quali ricette il modello
         propone e cosa l'analista va a cercare;
     02  il resoconto di un giorno: le misure, le forme, la cronaca;
     03  cosa l'analista ha visto, e cosa si potrebbe fare.

   -- Trasparenza al posto del permesso (spec §7, §5.1 e §11) --
   L'osservatore non chiede il permesso di guardare qualcosa: si deve poter
   vedere in ogni momento COSA sta guardando, DA QUANDO e PERCHE'.

   -- Il giorno --
   L'aggregazione notturna scrive «ieri» alle 00:20 (`server.py::
   _aggrega_ieri`): il giorno di oggi, quasi sempre, non ha ancora un
   resoconto. Il selettore nasce su ieri, calcolato nel fuso del BROWSER e
   non in quello della casa -- i due possono differire di un GIORNO intero
   (non "un'ora", cifra non misurata) vicino alla mezzanotte, se si guarda da
   un fuso diverso; nel caso reale, casa e utente nello stesso fuso, l'errore
   e' zero a qualunque ora.

   -- Cosa e' uscito, e quando (15/09/2026) --
   La sezione «cosa e' successo» e le sue cinquecento righe di resa per
   genere sono uscite con lo strato degli `oggetti` (spec §13): gli episodi
   vivono nella cronaca del resoconto, che la 02 mostra. Con loro e' uscita
   la rotta `api/mind/facts`.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server -- stessa disciplina di tree-route.js/memory-route.js. L'unica POST
   e' quella dell'obiettivo, e porta `X-Requested-With` perche' passa dal
   `csrf_middleware`. */
window.HirisWatcherRoute = (function () {
  'use strict';

  var TONE_PROBLEM = 'color:var(--err-ink)';
  var TONE_CALM = 'color:var(--text-3)';

  /* Una mappa di sole ETICHETTE: la chiave resta quella del payload
     (`mind/facts.py::GENRES`), e un genere che l'archivio manda e questa
     mappa non conosce mostra comunque il suo nome grezzo, mai "undefined"
     -- non sparisce mai, stessa regola di `NOMI_REGISTRI` in tree-route.js.
     E' la regola di tutte le mappe di resa di questo file (`DIRECTION_LABEL`,
     `AUTHOR_LABEL`). */

  /* Le sette direzioni dell'energia (mandato «le direzioni dell'energia»,
     27/08/2026) -- letterali, identiche a quelle che
     `HAClient.energy_directions()` scrive in `corpo.direzione`. Una
     direzione non in questa mappa (un genere futuro che il backend sapesse
     dire e questa pagina non ancora) mostra comunque la sua parola grezza,
     mai "undefined" -- stessa regola di `GENRE_LABEL`/`AUTHOR_LABEL`. */

  /* Le SETTE dimensioni di un bilancio, in quest'ordine -- letterale,
     identico a `BALANCE_DIRECTIONS` in `mind/facts.py` (contato nel
     sorgente Python, non ricopiato). **Correzione ALTA della review**
     (mandato «la pagina del bilancio», punto 1, 27/08/2026): questa lista
     diceva "NON sette, consumo e' ridondante con autoconsumo+prelievo" --
     un'ASSUNZIONE, non un fatto misurato, e su questa integrazione e'
     FALSA (autoconsumata esclude la batteria: la somma perde la scarica,
     vedi il commento sopra `BALANCE_DIRECTIONS` nel sorgente Python). Il
     consumo e' la settima dimensione, LETTA non dedotta -- senza di lui
     `quota_autosufficienza` (in `_balance_moments`) non si scrive affatto,
     mai un numero dedotto al posto di uno letto. Stessa etichetta di
     `DIRECTION_LABEL` sopra: e' lo stesso vocabolario di "immesso in
     rete"/"prelevato dalla rete"/"consumo della casa" gia' usato dagli
     episodi di energia -- il mandato chiede di riusare le stesse parole,
     non inventarne di nuove. */

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

  function section(outlet, num, title, subtitle) {
    var card = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    card.appendChild(head);
    if (subtitle) card.appendChild(el('p', 'sc-desc', subtitle));
    var body = el('div', 'sc-body');
    card.appendChild(body);
    outlet.appendChild(card);
    return body;
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

  /* --------------------------------------------------------- «cosa sto guardando»

     Spec «i tre attori» (docs/design/2026-09-10-i-tre-attori.md), §5.1 e
     §11, che NON sono due pagine: l'elenco di cio' che si guarda e' anche la
     prova che l'obiettivo e' stato capito. Per questo `GET /api/mind/watching`
     (`handle_watching`, hiris/app/api/handlers_mind.py) porta cinque parti in
     una risposta sola, e questa sezione le rende nell'ordine in cui si
     leggono:

     1. **L'obiettivo** (`obiettivo`): la domanda rispetto a cui si e' deciso.
        Mostrare le scelte senza la domanda a cui rispondono le rende
        illeggibili -- e' la prima cosa, non un'intestazione.
     2. **Cosa si guarda** (`watching`), col MOTIVO e CHI l'ha deciso: e' da
        li' che il proprietario potra' togliere qualcosa.
     3. **Cosa e' stato lasciato fuori** (`fuori`), con la sua ragione:
        l'altra meta' della trasparenza, da cui si rimette dentro. Chi non
        e' nello scope affatto non compare ne' di qua ne' di la' (non e' stato
        escluso: non e' stato considerato -- `_left_out`, handlers_mind.py).
     4. **La riconsiderazione** (`riconsiderazione`): quando, la finestra di
        memoria di Home Assistant MISURATA, e la cadenza che ne esce. Tutti e
        tre i numeri, o «ogni 84 ore» sarebbe da credere sulla parola.
     5. **Quanto scrive al giorno** (`volume`): la contropartita onesta dello
        scope. Si guarda meno, e questo e' quanto costa cio' che si guarda --
        la spec promette -83% (da 29.227 a 4.951 righe/giorno, misurate sulla
        casa vera il 10/09/2026, §5.3), e fino a questa pagina il numero non
        era visibile da fuori. Quei due numeri NON stanno nel testo della
        pagina: sono la misura di UNA casa, e scriverli in una pagina che
        ogni casa vede sarebbe inventare un dato per tutte le altre.

     -- I tre stati, mai appiattiti (stessa disciplina di tree-route.js) --
     `obiettivo` puo' essere `null`, `fuori`/`volume` `[]`, quando l'archivio
     non e' collegato (avvio a meta', un guasto): l'osservatore c'e', il suo
     archivio no. Il segnale e' `obiettivo == null`, e non e' un'inferenza
     azzardata: `ObservationsStore.objective()` ritorna SEMPRE un dizionario
     (quello di fabbrica se nessuno l'ha scritto), quindi un `null` puo'
     venire solo dal ramo `store is None` di `handle_watching`. Con l'archivio
     scollegato un `fuori: []` NON significa «niente escluso» e un
     `riconsiderazione: null` NON significa «mai fatta»: si dichiara che non
     si puo' sapere (`TONE_UNKNOWN`), come `non_disponibili` in tree-route.js.

     -- `autore: null` non e' «sconosciuto» (`Watcher.watching`, watcher.py) --
     Le condizioni di sistema (`problema:`/`integrazione:`/`log:`/
     `automazione:`) non passano dallo scope: non sono entita', nessuno le ha
     giudicate, e si guardano finche' durano. Attribuirle all'osservatore
     sarebbe dargli una decisione che non ha preso: qui hanno un gruppo
     proprio, senza autore, e la loro riga non porta un «dal ...» perche'
     `da_quando_ts` e' `null` per costruzione -- mai una data inventata.

     -- Perche' gruppi per autore e non un badge per riga --
     Sulla casa vera sono ~380 entita' decise dall'osservatore e ~30
     condizioni di sistema: un badge «osservatore» ripetuto 380 volte non
     distinguerebbe niente (e' la stessa lezione del rilievo 6b, «Pavimento
     — non si toglie» x88, e di R4). Chi ha deciso sta nell'intestazione del
     gruppo, una volta; dentro al gruppo le voci restano nell'ordine in cui
     arrivano (per `soggetto`, `Watcher.watching` le ordina cosi'). Un autore
     che il payload manda e `AUTHOR_LABEL` non conosce ha comunque il suo
     gruppo, col valore grezzo -- non sparisce mai. */

  /* Il tono del terzo stato -- «non si puo' sapere» -- distinto sia dal calmo
     (un'assenza vera) sia dal problema (un guasto): lo stesso `TONE_UNKNOWN`
     di tree-route.js, per la stessa ragione (un `null` non e' un `[]`). */
  var TONE_UNKNOWN = 'color:var(--warn-ink)';

  /* I tre autori possibili di una decisione dello scope (`author` in
     `mind/store.py`, `scope()`), nell'ordine in cui interessano a chi legge:
     prima cio' che ha deciso LUI, poi l'analista, poi l'osservatore (che e' la
     massa). Le condizioni di sistema (`autore: null`) chiudono, sempre. Solo
     ETICHETTE: la chiave resta quella del payload, come `GENRE_LABEL`. Sono
     complementi («da te», «dall'analista») perche' le due intestazioni che li
     usano hanno verbi diversi -- «Deciso ...» sopra, «Lasciato fuori ...»
     sotto -- e un'unica mappa serve entrambe. */
  var AUTHOR_ORDER = ['owner', 'analyst', 'observer'];
  var AUTHOR_LABEL = { owner: 'da te', analyst: 'dall’analista', observer: 'dall’osservatore' };
  var SYSTEM_GROUP_TITLE = 'Condizioni di sistema aperte';

  function authorPhrase(autore) {
    return AUTHOR_LABEL[autore] || ('da «' + autore + '»');
  }

  function groupByAuthor(voci) {
    var groups = {};
    var seen = [];
    voci.forEach(function (v) {
      var k = v.autore == null ? '' : String(v.autore);
      if (!groups[k]) { groups[k] = []; seen.push(k); }
      groups[k].push(v);
    });
    var order = AUTHOR_ORDER.filter(function (k) { return groups[k]; });
    seen.forEach(function (k) { if (k !== '' && order.indexOf(k) === -1) order.push(k); });
    if (groups['']) order.push('');
    return order.map(function (k) { return { autore: k === '' ? null : k, voci: groups[k] }; });
  }

  /* Data CON l'anno, a differenza di `fmtTime` (sezione 02, «gg/mm hh:mm»):
     un episodio vive dentro il giorno che si sta guardando, una decisione
     dello scope o un obiettivo possono essere di mesi fa -- «e' datato, e la
     sua storia conta» (spec §11, conseguenza 1). Fuso del BROWSER, come
     tutto il resto della pagina. */
  function fmtWhenFull(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' +
      pad2(d.getHours()) + ':' + pad2(d.getMinutes());
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

  /* Le cinque parti della sezione hanno ciascuna un titolo interno: e' una
     sezione sola (spec: «non sono due pagine»), ma cinque domande diverse,
     e un elenco di 400 righe seguito da tre numeri senza un titolo in mezzo
     non si legge. Stesso stile di `.st-label` (hiris-config.css), che pero'
     vive solo dentro una `.stat-tile`: qui e' un `h3` vero, cosi' un lettore
     di schermo salta di parte in parte. */
  function subheading(body, text) {
    var h = el('h3', null, text);
    h.style.cssText = 'font-size:var(--fs-12);text-transform:uppercase;letter-spacing:0.06em;' +
      'color:var(--text-3);font-weight:600;margin:var(--sp-4) 0 var(--sp-2)';
    body.appendChild(h);
    return h;
  }

  /* 1. L'obiettivo. `scritto_ts: null` e' un fatto a se' (`objective()`,
     mind/store.py): «nessuno l'ha mai scritto, vale quello di fabbrica», che
     non e' la stessa cosa di «l'ha scritto qualcuno e coincide col default»
     -- si dice. Con `obiettivo: null` (archivio scollegato) NON si mostra il
     default di fabbrica: sarebbe un'affermazione che nessuno ha verificato. */
  function renderObjective(body, objective) {
    subheading(body, 'L’obiettivo');
    if (!objective) {
      line(body, 'L’obiettivo non si può leggere: l’archivio dell’osservatore non è collegato. ' +
        'Non è quello di fabbrica — è che non si sa quale sia.', TONE_UNKNOWN);
      return;
    }
    var quote = el('blockquote', null, objective.testo);
    quote.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:0 0 4px;padding-left:10px;' +
      'border-left:3px solid var(--accent);overflow-wrap:anywhere';
    body.appendChild(quote);
    body.appendChild(el('p', 'field-hint', objective.scritto_ts == null
      ? 'Obiettivo di fabbrica: nessuno l’ha ancora scritto.'
      : 'Scritto il ' + fmtWhenFull(objective.scritto_ts) + '.'));

    /* **E si può scrivere.** Fino al 14/09/2026 `set_objective` non aveva
       nessun chiamante -- né rotta, né campo, né strumento in chat -- e sulla
       casa vera l'obiettivo era ancora quello di fabbrica. È la sola manopola
       del prodotto: da questa frase l'osservatore decide cosa guardare, il
       modello propone le ricette e l'analista sceglie cosa cercare.

       Il campo parte da quello di ADESSO, non vuoto: un obiettivo si corregge,
       non si riscrive da zero, e un campo vuoto invita a cancellare la sola
       cosa che tiene in piedi il criterio. */
    var campo = el('textarea');
    campo.value = objective.testo || '';
    campo.rows = 2;
    campo.setAttribute('aria-label', 'L’obiettivo della casa');
    campo.style.cssText = 'display:block;width:100%;box-sizing:border-box;margin:10px 0 6px;' +
      'padding:8px;border-radius:8px;font:inherit;overflow-wrap:anywhere';
    body.appendChild(campo);

    var esito = el('p', 'sc-desc');
    var salva = el('button', 'btn btn-sm', 'Salva l’obiettivo');
    salva.type = 'button';
    salva.addEventListener('click', function () {
      salva.disabled = true;
      esito.textContent = 'Salvo…';
      write('api/mind/objective', { testo: campo.value }).then(function (occurrence) {
        salva.disabled = false;
        if (occurrence.status === 400) {
          /* **Il campo NON si svuota e la sezione non si ricarica.** Il
             proprietario ha appena scritto una frase: perderla sarebbe il
             danno peggiore dei due. */
          esito.textContent = (occurrence.corpo && occurrence.corpo.errore)
            || 'Questo obiettivo non si può scrivere.';
          return;
        }
        if (!occurrence.ok) {
          esito.textContent = 'Non è stato possibile salvare. Riprova.';
          return;
        }
        if (occurrence.corpo && occurrence.corpo.scritto === false) {
          /* `scritto: false` vuol dire «c'era già», non «non ha funzionato»:
             dirlo come un guasto insegnerebbe a diffidare dei guasti veri. */
          esito.textContent = 'L’obiettivo era già questo: non è cambiato niente.';
          return;
        }
        /* Scritto: la sezione si rilegge intera, perche' l'obiettivo nuovo
           cambia anche «da quando» e la riconsiderazione. */
        loadWatching(body);
      }, function () {
        salva.disabled = false;
        esito.textContent = 'Non è stato possibile salvare. Riprova.';
      });
    });
    body.appendChild(salva);
    body.appendChild(esito);
  }

  /* Una riga di decisione, per «cosa guardo» e per «lasciato fuori» insieme:
     e' la STESSA forma (soggetto, motivo, quando) e due funzioni gemelle
     divergerebbero al primo ritocco. `sayTechnical`/`sayReason` sono decisi
     dal gruppo (sotto): quando ogni voce del gruppo e' un identificatore, o
     quando ogni voce porta lo stesso motivo, la dichiarazione vive una volta
     sul gruppo e la riga non la ripete -- e' R4, esteso al motivo.

     Fetta «il nome» (07/09/2026): questo elenco NON porta nomi, mai. Un'entita'
     resta il suo `entity_id`, e la riga lo DICE (`d.technical`) invece di
     lasciarlo passare per un nome; `describeWatchedSubject` (condivisa con la
     sezione 02) separa i soggetti grezzi (`log:...@file:riga`,
     `integrazione:<id opaco>`) in nome leggibile + riferimento tecnico
     secondario, mai buttato ma in secondo piano (`.field-hint`). */
  function decisionRow(described, v, sayTechnical, sayReason, when) {
    var li = el('li');
    li.style.cssText = 'margin-bottom:8px;font-size:var(--fs-13);overflow-wrap:anywhere';
    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
    if (described.technical && sayTechnical) head.appendChild(el('span', 'field-hint', SUBJECT_IS_ID));
    head.appendChild(el('span', 'text-mono', described.primary));
    if (described.secondary) head.appendChild(el('span', 'text-mono field-hint', described.secondary));
    if (when) head.appendChild(el('span', 'field-hint', when));
    li.appendChild(head);
    if (sayReason) {
      /* Un motivo che manca si dice, non si tace: una decisione senza il suo
         perche' e' esattamente cio' che questa pagina esiste per non avere. */
      var reason = el('p', null, v.motivo ? v.motivo : '(nessun motivo scritto)');
      reason.style.cssText = 'margin:2px 0 0;color:var(--text-2)';
      li.appendChild(reason);
    }
    return li;
  }

  /* Un gruppo per autore, chiuso di default (sulla casa vera il gruppo
     dell'osservatore e' ~380 righe: aperto sarebbe un muro davanti alle altre
     quattro parti). Il sommario porta chi ha deciso e quante voci, cosi' la
     pagina si legge a colpo d'occhio senza aprire niente.

     `opts.title(autore)` da' l'intestazione («Deciso da te», «Lasciato fuori
     dall'analista»), `opts.whenKey`/`opts.whenPrefix` dicono quale istante
     mostrare e con che parola («dal 11/09/2026 14:00» per cio' che si
     guarda, «il 11/09/2026 14:00» per cio' che e' stato escluso). */
  function renderDecisionGroup(body, group, opts) {
    var det = el('details');
    det.open = false;
    var n = group.voci.length;
    var title = group.autore == null ? SYSTEM_GROUP_TITLE : opts.title(group.autore);
    var summary = el('summary', null, title + ' — ' + n + (n === 1 ? ' voce' : ' voci'));
    summary.style.cssText = 'cursor:pointer;font-weight:500';
    det.appendChild(summary);

    if (group.autore == null) {
      var systemHint = el('p', 'field-hint',
        'Nessuno le ha decise: non sono entità, e si guardano finché durano. Non c’è niente da togliere.');
      systemHint.style.cssText = 'margin:4px 0 0';
      det.appendChild(systemHint);
    }

    var described = group.voci.map(function (v) { return describeWatchedSubject(v.soggetto); });
    var allTechnical = described.length > 0 && described.every(function (d) { return d.technical; });
    if (allTechnical) {
      // Detto UNA volta per il gruppo, non tace mai: chi legge deve
      // continuare a sapere che quelle sotto non sono nomi (R4).
      var hint = el('p', 'field-hint', 'Le voci qui sotto sono ' + SUBJECT_IS_ID_PLURAL + '.');
      hint.style.cssText = 'margin:4px 0 0';
      det.appendChild(hint);
    }

    /* Lo stesso motivo su ogni riga del gruppo (le ~30 condizioni di sistema
       portano tutte `_SYSTEM_REASON`, watcher.py) si dice una volta, non
       trenta: e' un dato, non una supposizione -- si confronta la stringa,
       riga per riga, e basta una voce diversa perche' ognuna torni a
       portare il suo. */
    var firstReason = n ? group.voci[0].motivo : null;
    var sharedReason = n > 1 && group.voci.every(function (v) { return v.motivo === firstReason; });
    if (sharedReason) {
      var reasonHint = el('p', null, 'Motivo, per tutte: ' + (firstReason ? firstReason : '(nessun motivo scritto)'));
      reasonHint.style.cssText = 'margin:4px 0 0;font-size:var(--fs-13);color:var(--text-2)';
      det.appendChild(reasonHint);
    }

    var ul = el('ul');
    ul.style.cssText = 'margin:6px 0 4px;padding-left:18px';
    group.voci.forEach(function (v, i) {
      var ts = v[opts.whenKey];
      var when = ts != null ? opts.whenPrefix + ' ' + fmtWhenFull(ts) : null;
      ul.appendChild(decisionRow(described[i], v, !allTechnical, !sharedReason, when));
    });
    det.appendChild(ul);
    body.appendChild(det);
  }

  /* 2. Cosa si guarda. */
  function renderWatched(body, watching) {
    subheading(body, 'Cosa guardo');
    if (!watching.length) {
      line(body,
        'Non sto guardando ancora niente. Se HIRIS è appena partito e l’osservatore non ha ancora' +
        ' deciso cosa guardare, è normale — torna fra poco.',
        TONE_CALM);
      return;
    }
    groupByAuthor(watching).forEach(function (g) {
      renderDecisionGroup(body, g, {
        title: function (autore) { return 'Deciso ' + authorPhrase(autore); },
        whenKey: 'da_quando_ts', whenPrefix: 'dal'
      });
    });
  }

  /* 3. Lasciato fuori. Tre stati: non leggibile (archivio scollegato),
     davvero vuoto, pieno. Il secondo e il terzo portano la frase su chi non
     compare affatto -- e' l'unico modo di non far leggere «lasciato fuori»
     come «tutto il resto della casa». */
  function renderLeftOut(body, leftOut, archiveMissing) {
    subheading(body, 'Lasciato fuori');
    if (archiveMissing) {
      line(body, 'Non si può sapere cosa è stato lasciato fuori: l’archivio non è collegato. ' +
        'Non vuol dire che non sia stato escluso niente.', TONE_UNKNOWN);
      return;
    }
    line(body, 'Ciò su cui si è deciso di no, con la ragione: è l’altra metà della trasparenza, ' +
      'ed è da qui che si rimette dentro qualcosa. Chi non compare né qui né sopra non è stato ' +
      'escluso — non è stato considerato.', TONE_CALM);
    if (!leftOut.length) {
      line(body, 'Niente è stato lasciato fuori con una ragione scritta.', TONE_CALM);
      return;
    }
    groupByAuthor(leftOut).forEach(function (g) {
      renderDecisionGroup(body, g, {
        title: function (autore) { return 'Lasciato fuori ' + authorPhrase(autore); },
        whenKey: 'deciso_ts', whenPrefix: 'il'
      });
    });
  }

  /* 4. La riconsiderazione: tre numeri, tutti e tre (`quando_ts`,
     `finestra_s`, `cadenza_s`). La cadenza e' la META' della finestra
     misurata (`mind/cadence.py::cadence_from`): si dice, cosi' «ogni 84 ore»
     ha accanto il numero da cui viene. `finestra_s` puo' essere `null` anche
     dentro una riconsiderazione avvenuta (`record_reconsideration` accetta
     `None`: la misura e' fallita) e allora `cadenza_s` e' `null` con lei --
     e SENZA cadenza l'osservatore non riconsidera da solo
     (`mind/cadence.py::due` risponde di no): e' un fatto da dire, non da
     nascondere dietro una tessera vuota. Le tessere sono `.stat-grid`/
     `.stat-tile`, lo stesso componente condiviso gia' usato dal bilancio
     (sezione 02) e dalla Dashboard. */
  function renderReconsideration(body, r, archiveMissing) {
    subheading(body, 'La riconsiderazione');
    if (archiveMissing) {
      line(body, 'Non si può sapere quando la casa è stata riconsiderata: l’archivio non è collegato.',
        TONE_UNKNOWN);
      return;
    }
    if (!r) {
      // La frase si ferma qui, e fino all'11/09/2026 era l'UNICA cosa che la
      // pagina diceva mentre l'osservatore falliva ogni dieci minuti: vera
      // alla lettera, e falsa come racconto. Il rinvio non e' una cortesia --
      // e' cio' che distingue «non e' ancora successo» da «non ci si riesce».
      line(body, 'Non è mai stata fatta: al primo avvio l’osservatore non ha ancora ripensato la casa ' +
        'intera, e finché non lo fa non c’è una cadenza da dichiarare. Se ci ha già provato, lo dice ' +
        'qui sotto, in «I tentativi».', TONE_CALM);
      return;
    }
    var grid = el('div', 'stat-grid');
    var tiles = [
      ['Ultima volta', r.quando_ts != null ? fmtWhenFull(r.quando_ts) : 'data non disponibile'],
      ['Memoria di Home Assistant, misurata', r.finestra_s != null ? fmtDays(r.finestra_s) : 'non misurata'],
      ['Cadenza', r.cadenza_s != null ? 'ogni ' + fmtHours(r.cadenza_s) : 'nessuna']
    ];
    tiles.forEach(function (t) {
      var tile = el('div', 'stat-tile');
      tile.appendChild(el('div', 'st-label', t[0]));
      var value = el('div', 'st-value', t[1]);
      // Una data o «non misurata» a 24px sfonda la tessera su un telefono:
      // la tessera del bilancio porta numeri corti, questa no.
      value.style.cssText = 'font-size:var(--fs-17);overflow-wrap:anywhere';
      tile.appendChild(value);
      grid.appendChild(tile);
    });
    body.appendChild(grid);
    if (r.finestra_s == null || r.cadenza_s == null) {
      line(body, 'La memoria di Home Assistant non si è potuta misurare, e senza quella misura non ' +
        'c’è cadenza: l’osservatore non riconsidera la casa da solo finché non riesce a misurarla.',
        TONE_UNKNOWN);
      return;
    }
    line(body, 'La cadenza è la metà della memoria misurata: così tutto ciò che era stato scartato è ' +
      'ancora recuperabile quando l’osservatore ci ripensa, anche se un giro salta.', TONE_CALM);
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

  /* «da 40 minuti», oppure niente quando la serie arriva in fondo all'elenco:
     li' da quanto duri non si SA, e un numero preciso su un fatto troncato
     sarebbe un dato dedotto spacciato per uno letto. */
  function _sinceWhen(tentativi, inizio, run) {
    if (inizio + run === tentativi.length) return ' — più indietro di così non si vede';
    return ', da ' + fmtDuration(
      Math.max(0, Date.now() / 1000 - tentativi[inizio + run - 1].quando_ts));
  }

  var ATTEMPT_LABEL = {
    accodata: 'In attesa', riuscito: 'Riuscito', non_riuscito: 'Non riuscito',
    scaduta: 'Scaduta'
  };
  /* Le stesse tre pastiglie di `agenda-route.js` (`STATE_BADGE`): lo stesso
     vocabolario visivo per lo stesso genere di fatto, invece di un semaforo
     nuovo che questa pagina non ha mai avuto. */
  /* I due esiti che sono un GUASTO, e contano nella serie. «Scaduta» e' il
     piano che non ha risposto entro la scadenza; «non riuscito» e' una
     risposta che non si e' potuta usare, o un modello che non ha risposto
     affatto. Sono cause diverse e la pagina le nomina diverse, ma per la
     domanda «sta funzionando?» pesano uguale. */
  var FAILED = { non_riuscito: true, scaduta: true };

  var ATTEMPT_BADGE = {
    accodata: 'badge-off', riuscito: 'badge-on', non_riuscito: 'badge-err',
    scaduta: 'badge-err'
  };

  /* 6. I tentativi: **«sta funzionando?»**, che NON e' la domanda del blocco
     qui sopra. `riconsiderazione` dice quand'e' l'ultima volta che la casa e'
     stata ripensata DAVVERO; questo dice com'e' andata l'ultima volta che ci
     si e' provato, riuscita o no.

     Le due divergono esattamente nel caso che conta, ed e' successo:
     misurato sulla casa vera l'11/09/2026, l'osservatore ha provato e fallito
     quattro volte in quaranta minuti, HIRIS ha smesso di registrare
     qualunque cosa (il cancello di cio' che si registra **e'** lo scope) e
     questa pagina diceva soltanto «Non e' mai stata fatta» -- vero alla
     lettera, falso come racconto. Un guasto non si appiattisce su
     un'assenza.

     **La frase si calcola sulla SERIE, non sull'ultimo.** Fra un fallimento e
     il tentativo successivo l'ultimo esito torna a essere «accodata»:
     guardando solo quello, quaranta minuti di guasto sarebbero di nuovo
     invisibili. Vale per il ponte, dove il turno si accoda; sulla catena un
     fallimento resta l'ultimo esito finche' non si riprova.

     **E quando la serie arriva in fondo all'elenco si dice «almeno».** Da
     quanto duri davvero non si SA: la pagina vede solo i tentativi che la
     porta le ha mandato, e non puo' sapere se prima ce ne fossero altri. Un
     numero preciso su un fatto troncato sarebbe un dato dedotto spacciato
     per uno letto -- e per la stessa ragione la frase non nomina «dieci»: il
     tetto vive in `mind/store.ATTEMPTS_SHOWN` e ricopiarlo qui sarebbe un
     doppione destinato a mentire il giorno in cui cambia. */
  function renderAttempts(body, tentativi, archiveMissing) {
    subheading(body, 'I tentativi');
    if (archiveMissing) {
      line(body, 'Non si può sapere se l’osservatore ci stia provando: l’archivio non è collegato.',
        TONE_UNKNOWN);
      return;
    }
    if (!tentativi.length) {
      line(body, 'Nessuno ha ancora provato a ripensare la casa: non c’è alcun tentativo registrato.',
        TONE_CALM);
      return;
    }

    var last = tentativi[0];
    // **La serie si conta saltando le attese in cima, e non e' un dettaglio.**
    // Dopo un fallimento il giro riaccoda, quindi la sequenza che l'archivio
    // produce davvero ha «accodata» in testa e i fallimenti sotto: contando
    // dall'indice 0 il conto finiva a ZERO, il primo ramo vinceva, e quaranta
    // minuti di guasto tornavano ad avere la faccia di un'attesa di un minuto
    // -- calma, elenco chiuso. Cioe' esattamente il difetto da cui questa
    // fetta nasce, ricostruito dalla pagina che doveva toglierlo (trovato
    // dalla review indipendente dell'11/09/2026, eseguendo).
    var inizio = 0;
    while (inizio < tentativi.length && tentativi[inizio].esito === 'accodata') inizio += 1;
    var run = 0;
    while (inizio + run < tentativi.length
           && FAILED[tentativi[inizio + run].esito]) run += 1;
    var attesa = last.esito === 'accodata';

    if (attesa && run === 0) {
      line(body, 'In corso da ' + fmtDuration(Math.max(0, Date.now() / 1000 - last.quando_ts)) +
        ': la domanda è partita verso il piano, e la risposta non è ancora arrivata.', TONE_CALM);
    } else if (attesa) {
      line(body, 'In corso da ' + fmtDuration(Math.max(0, Date.now() / 1000 - last.quando_ts)) +
        ', ma i ' + run + ' tentativi di fila non sono riusciti' +
        _sinceWhen(tentativi, inizio, run) + '. L’ultimo fallito: ' +
        (tentativi[inizio].dettaglio || 'senza dettagli') + '.', TONE_PROBLEM);
    } else if (last.esito === 'riuscito') {
      line(body, 'L’ultimo tentativo è riuscito, ' + fmtAgo(last.quando_ts) + ': ' +
        (last.dettaglio || 'senza dettagli') + '.', TONE_CALM);
    } else if (run === 1) {
      line(body, 'L’ultimo tentativo non è riuscito, ' + fmtAgo(last.quando_ts) + ': ' +
        (last.dettaglio || 'senza dettagli') + '.', TONE_PROBLEM);
    } else if (run > 1) {
      var troncato = inizio + run === tentativi.length;
      var almeno = troncato ? 'almeno ' : '';
      line(body, 'Sta fallendo da ' + almeno +
        fmtDuration(Math.max(0, Date.now() / 1000 - tentativi[inizio + run - 1].quando_ts)) +
        ': ' + almeno + run + ' tentativi di fila non sono riusciti' +
        (troncato ? ' — più indietro di così non si vede' : '') + '. L’ultimo, ' +
        fmtAgo(last.quando_ts) + ': ' + (last.dettaglio || 'senza dettagli') + '.', TONE_PROBLEM);
    } else {
      // **Un esito che questa pagina non conosce non la fa esplodere.** Prima
      // di questa guardia si finiva nel ramo della serie con `run` a zero,
      // si leggeva `tentativi[-1]` -- `undefined` -- e l'eccezione portava via
      // tutte e sei le parti della sezione: la pagina che deve dire «sta
      // funzionando?» moriva. Basta un esito nuovo, e `scaduta` e' arrivato
      // con questa stessa fetta.
      line(body, 'L’ultimo tentativo, ' + fmtAgo(last.quando_ts) + ': ' +
        (ATTEMPT_LABEL[last.esito] || last.esito) + ' — ' +
        (last.dettaglio || 'senza dettagli') + '.', TONE_PROBLEM);
    }

    body.appendChild(createDisclosure(
      'Vedi gli ultimi tentativi', 'Nascondi gli ultimi tentativi',
      function (panel) {
        var list = el('ul');
        list.style.cssText = 'list-style:none;margin:6px 0 0;padding:0';
        tentativi.forEach(function (t) {
          var item = el('li');
          item.style.cssText = 'display:flex;align-items:baseline;gap:8px;' +
            'margin-bottom:6px;font-size:var(--fs-13);flex-wrap:wrap';
          item.appendChild(el('span', 'agent-badge ' + (ATTEMPT_BADGE[t.esito] || 'badge-off'),
            ATTEMPT_LABEL[t.esito] || t.esito));
          item.appendChild(el('span', 'field-hint',
            fmtWhenFull(t.quando_ts) + ' · ' + fmtAgo(t.quando_ts)));
          item.appendChild(el('span', null, t.dettaglio || ''));
          list.appendChild(item);
        });
        panel.appendChild(list);
      },
      run >= 2));
  }

  /* 5. Quanto scrive al giorno: barre in CSS puro (`div` con `style.width`),
     non un `<canvas>` ne' un SVG -- sette numeri non sono una curva, e una
     barra CSS non ha bisogno di misure di layout, si legge con un lettore di
     schermo (il testo porta il dato, la barra e' `aria-hidden`) e scala a
     390px senza scorrere. La larghezza e' relativa al giorno piu' alto dei
     sette: e' una tendenza (`_volume`, handlers_mind.py: «dal piu' vecchio»,
     perche' una tendenza si legge in avanti), non un confronto con una
     soglia. Un giorno a zero righe resta una barra vuota, non sparisce. */
  function renderVolume(body, volume, archiveMissing) {
    subheading(body, 'Quanto scrive al giorno');
    line(body, 'Le righe grezze scritte ogni giorno. È quanto costa ciò che si guarda: si guarda ' +
      'meno, e questo è il conto.', TONE_CALM);
    if (archiveMissing) {
      line(body, 'Non si può contare: l’archivio non è collegato.', TONE_UNKNOWN);
      return;
    }
    if (!volume.length) {
      line(body, 'Nessun conteggio disponibile.', TONE_CALM);
      return;
    }
    var max = 0;
    volume.forEach(function (r) { if (r.righe != null && r.righe > max) max = r.righe; });

    var ul = el('ul');
    ul.style.cssText = 'list-style:none;margin:0;padding:0';
    volume.forEach(function (r) {
      var li = el('li');
      li.style.cssText = 'display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;' +
        'align-items:center;margin-bottom:4px;font-size:var(--fs-13)';
      li.appendChild(el('span', 'field-hint', ggMmAaaa(String(r.giorno || ''))));
      var track = el('div');
      track.setAttribute('aria-hidden', 'true');
      track.style.cssText = 'height:8px;border-radius:4px;background:var(--surface-2);overflow:hidden';
      var bar = el('div');
      var pct = (r.righe != null && max > 0) ? (r.righe / max) * 100 : 0;
      bar.style.cssText = 'height:100%;background:var(--accent);width:' + pct.toFixed(1) + '%';
      track.appendChild(bar);
      li.appendChild(track);
      li.appendChild(el('span', 'text-mono', r.righe != null ? fmtCount(r.righe) + ' righe' : 'non contate'));
      ul.appendChild(li);
    });
    body.appendChild(ul);
  }

  /* La sezione intera, dal payload di `GET /api/mind/watching` (vedi il
     commento in testa a questa parte per le cinque cose e i tre stati). */
  function renderScope(body, payload) {
    var p = payload || {};
    var archiveMissing = p.obiettivo == null;
    renderObjective(body, p.obiettivo);
    renderWatched(body, p.watching || []);
    renderLeftOut(body, p.fuori || [], archiveMissing);
    renderReconsideration(body, p.riconsiderazione, archiveMissing);
    renderAttempts(body, p.tentativi || [], archiveMissing);
    renderVolume(body, p.volume || [], archiveMissing);
  }

  /* Bottone «Riprova» (rilievo 4): era l'unica pagina di lettura senza,
     mentre l'errore piu' comune -- il riavvio dell'add-on -- e' esattamente
     transitorio. Stesso bottone delle sorelle (memory-/agenda-/
     constructions-route.js): `btn btn-ghost btn-sm`, rilancia `reload`. Il
     TESTO dei tre messaggi sotto non cambia (rilievo 4: "il migliore del
     pannello", non si riscrive). */
  function retryButton(body, reload) {
    var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
    retry.type = 'button';
    retry.addEventListener('click', reload);
    body.appendChild(retry);
  }

  function renderWatchingError(body, status, reload) {
    if (status === 503) {
      line(body,
        'L’osservatore non è disponibile: HIRIS non sta guardando niente in questo momento. ' +
        'Non è una lista vuota — è l’osservatore stesso ad essere fermo (riprova dopo un riavvio dell’add-on).',
        TONE_PROBLEM);
    } else {
      line(body, 'Non è stato possibile leggere cosa sta guardando l’osservatore. Riprova più tardi.',
        TONE_PROBLEM);
    }
    retryButton(body, reload);
  }

  /* --------------------------------------------------------------- «cosa è successo» */

  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function isoData(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function ieriLocale() {
    var d = new Date();
    d.setDate(d.getDate() - 1);
    return isoData(d);
  }
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

  /* La frase che apre la riga: cosa e' successo, per genere -- il corpo ha
     forma diversa per ciascuno (vedi il commento di testa). Nessuna frase
     generica: campi reali o niente. */

  /* La provenienza della direzione -- non e' la stessa domanda di «chi ha
     deciso» nella sezione 01 (`AUTHOR_LABEL`: osservatore/analista/
     proprietario). Qui i due valori possibili sono "dichiarata" (la
     dashboard Energia dell'utente, che vince sempre) e "dedotta"
     (`translation_key` dell'integrazione, un arricchimento specifico).
     **Le due provenienze si distinguono visibilmente apposta** (mandato,
     punto 4): il giorno in cui una dedotta sbagliasse, saperlo e' la
     differenza fra un dubbio e una caccia. Due stili di `.agent-badge` gia'
     in hiris-config.css (`badge-off` per l'autorevole, `badge-warn` per
     l'arricchimento) -- non un componente nuovo. */

  /* `problema:dominio.id` / `integrazione:entry_id` / `log:logger@file:riga` /
     `automazione:entity_id` -> un nome leggibile. Stessa idea di
     `nomiRegistriInItaliano` in tree-route.js: un prefisso tecnico non deve
     restare tale e quale sulla pagina.

     Correzione onda finale, rilievo 1: dal Task 2 il corpo di un guasto
     porta `dominio`/`titolo` quando la riga che ha aperto l'episodio li
     portava (vedi `facts.py`, `close()`) -- un nome leggibile che questa
     funzione ignorava, mostrando l'identificativo opaco (`entry_id`) anche
     quando il dato buono era gia' li'. Quando ci sono si usano loro;
     l'identificativo resta il ripiego per le righe vecchie che non li
     hanno.

     Giro di correzioni sul Task 7: `problema:`/`integrazione:` erano gli
     unici due prefissi tradotti, ma dal Task 2 (registro di errori) e dal
     Task 4 (automazioni) l'archivio ne scrive altri due, `log:` e
     `automazione:` -- senza un ramo qui sotto ricadevano sul `return s`
     finale, cioe' l'esatto identificatore opaco che questa funzione esiste
     per non mostrare (un `automazione:` senza `titolo` dall'evento, o un
     `log:` senza `message[0]`, sono i casi che ci arrivano davvero: vedi
     `Watcher.watch_system`/`mark_automation` in watcher.py per quando
     `titolo` puo' mancare). Copriva quasi sempre perche' il titolo di
     solito c'e' -- ma «quasi sempre» e' proprio il difetto silenzioso che
     questa fetta esiste per chiudere. */
  /* Il riconoscimento dei quattro prefissi tecnici (`problema:`/
     `integrazione:`/`log:`/`automazione:`) SEPARATO dalla resa: questa
     funzione dice solo COSA porta un soggetto grezzo, mai come scriverlo a
     schermo -- quello lo decide chi la chiama. E' la base condivisa fra
     `protagonistName` (un episodio, che quando ha `corpo.titolo` lo
     preferisce sempre) e `describeWatchedSubject` (una voce di «cosa sto
     guardando», che porta SOLO `{soggetto, motivo, autore, da_quando_ts}` e non ha
     mai un `corpo` da cui prendere un titolo -- BACKLOG.md, collaudo del
     07/09/2026: due elenchi sulla stessa pagina rendevano lo stesso
     soggetto in due modi, e uno stampava l'identificatore grezzo perche'
     nessuno gli aveva mai insegnato questi quattro prefissi). Un solo posto
     che li conosce, non due che potrebbero divergere al primo caso strano.

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
     collaudo E2, 07/09/2026): una voce qui non ha MAI un `corpo.titolo` da
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
     solo, perche' le due sezioni della pagina («cosa sto guardando» e «cosa
     e' successo») devono dire la stessa cosa con le stesse parole: due
     letterali in due punti diverse divergerebbero al primo ritocco. Corta
     apposta -- e' un'etichetta accanto all'identificatore, non una frase:
     la riga deve restare leggibile anche quando si ripete su ogni voce di
     un elenco lungo. */
  var SUBJECT_IS_ID = 'identificatore:';

  /* R4 (revisione del tratto v3.22.2..HEAD): la stessa dichiarazione, detta
     UNA volta per un intero gruppo di «Cosa sto guardando» invece che su
     ogni riga (`renderDecisionGroup`, sopra) -- stessa parola («identificatore»)
     delle due forme qui sopra, cosi' chi legge non impara un terzo
     vocabolario per lo stesso fatto. */
  var SUBJECT_IS_ID_PLURAL = 'identificatori tecnici, non nomi';

  /* Il rivelatore sincrono, estratto (correzione di questo giro): era
     duplicato letterale fra `detailsDisclosure` (comprimari/misure) e il
     rivelatore delle entita' di un bilancio, sotto -- STESSO bottone,
     STESSA logica open/close, STESSA disciplina "chiuso di default, i dati
     sono gia' nel payload" (mandato Task 7). Un secondo copia-incolla qui
     sarebbe il doppione che le fondamenta di questo prodotto vietano.
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

  /* ----------------------------------------------------- «il bilancio dell'energia»
     Mandato «il bilancio dell'energia», 27/08/2026. Vedi il commento di
     testa del file per il perche' (una quantita' con una forma, non un
     episodio) e per il contratto esatto del corpo. */

  /* Un numero del bilancio dell'energia -> "24,5 kWh", virgola italiana. Il
     backend ha gia' arrotondato a 2 decimali (`build_balance_body`,
     mandato punto 6, il difetto misurato `+0.010000000000000009`): qui si
     FORMATTA, non si arrotonda una seconda volta -- `maximumFractionDigits:
     2` e' un tetto che non taglia nessuna cifra vera, `minimumFractionDigits:
     1` evita "24" secco per un numero che e' comunque una misura continua. */

  /* Una quota 0..1 (`_share`, 3 decimali nel backend) -> percentuale con un
     decimale e virgola italiana: "71,2%". */
  function fmtPercent(v) {
    if (v == null) return null;
    return (v * 100).toLocaleString('it-IT', { maximumFractionDigits: 1 }) + '%';
  }

  /* Gli istanti dentro `corpo.momenti`/`corpo.forma` sono ISO-8601 CON FUSO
     (`HAClient._instant_from_ha`: sempre UTC, mai un timestamp UNIX) --
     un'origine DIVERSA da `inizio_ts`/`fine_ts` dell'oggetto (quelli sono
     secondi UNIX, letti da `fmtTime` con `* 1000`). Confonderli
     produrrebbe un `Invalid Date` o una data nel 1970: due formati, due
     funzioni, come il resto del file distingue i formati che arrivano da
     fonti diverse. Il fuso di resa e' quello del BROWSER (`new Date`
     converte da soli) -- stessa scelta gia' fatta da `period()`/
     `fmtTime` per il resto della pagina.

     Punto 4 del brief-dodicesima (nota minore): il parsing e la validazione
     di questi ISO erano duplicati fra questa funzione e un secondo
     `oraLocaleDalPunto` usato solo dal ciclo di `renderBalanceCurve` sotto
     -- e ogni barra della curva costruiva DUE oggetti `Date` dalla STESSA
     stringa (uno per il piazzamento, uno per l'etichetta). `localDateFromPoint`
     fa l'analisi e la validazione una volta sola: `fmtIsoHour` la usa qui
     sotto per i momenti, e `renderBalanceCurve` la chiama UNA sola volta per
     punto, derivando sia l'ora (piazzamento) sia il testo (etichetta) dalla
     stessa `Date` -- il secondo `oraLocaleDalPunto` non serve piu' ed e'
     stato tolto (nessun doppione morto in giro). */

  /* Punto 1 del brief, "in ordine di importanza": la riga che risponde a
     «com'e' andata ieri», leggibile senza aprire niente. Riusa `.stat-grid`/
     `.stat-tile` (sorelle: e' lo stesso componente della pagina Consumi,
     "il metro sono le pagine sorelle" -- brief §"le regole imparate a caro
     prezzo"). Una sola tessera per DIMENSIONE PRESENTE: mai una tessera a
     zero per una dimensione che il dispositivo non ha (mandato, "cosa NON si
     salva" -- niente batteria, niente "carica"/"scarica"). L'ordine e'
     `BALANCE_DIRECTION_ORDER`: produzione/autoconsumo/immissione/prelievo
     -- le quattro del punto 1 -- vengono prima di carica/scarica, che
     compaiono solo per un dispositivo con batteria; il consumo (settima
     dimensione, letta non dedotta -- correzione ALTA della review, mandato
     «la pagina del bilancio», punto 1, 27/08/2026) chiude l'elenco. */

  /* Punto 2 del brief-pagina: «Ventiquattro valori per piu' serie non si
     leggono come tabella. Serve una curva.» -- SVG scritto a mano, STESSO
     schema di `svgBarre` in usage-route.js (nessuna libreria nuova,
     verificato: il prodotto non ne porta nessuna). Le serie che «contano
     insieme» sono produzione e prelievo (brief-pagina, punto 2: «e' il loro
     scarto ... che racconta l'efficienza») -- se ci sono entrambe si
     sovrappongono in barre affiancate; se ce n'e' una sola si disegna
     quella sola. Nessun `innerHTML`: `createElementNS` + `setAttribute`, la
     stessa disciplina "textContent/createElement ovunque" di tutto il resto
     della pagina (vedi il commento di sicurezza in testa al file) -- qui
     estesa all'SVG, che non e' un'eccezione.

     **L'asse orario e' ARRIVATO (mandato «la pagina del bilancio -- le
     correzioni», punto 6, 27/08/2026, che riapre e RENDE PIU' SEVERO il
     punto 1: «la pagina non deve mai affermare un'ora falsa», e prima
     nessun test lo sorvegliava).** Prima di questa correzione `corpo.forma`
     era una lista POSIZIONALE NUDA: l'indice non era l'ora (HA omette le
     ore senza dati), e questa funzione disegnava le barre "in ordine di
     arrivo", mai un orario specifico -- l'unico modo onesto di non mentire
     con un dato che non c'era. **Ora ogni punto porta la SUA ora**
     (`{"ora","valore"}`, la stessa chiave gia' usata da `picco_produzione`
     -- vedi il docstring di `build_balance_body` in mind/
     facts.py, letto per intero prima di questa correzione): le barre si
     posizionano sull'ORA VERA di ciascun punto, in 24 posizioni fisse (una
     per ora del giorno, fuso del BROWSER come `fmtIsoHour` sopra) invece che
     in ordine di arrivo -- cosi' **un'ora senza dato resta uno spazio
     vuoto, non una barra spostata**: i buchi (l'impianto fermo, HA che non
     manda niente per quell'ora) si vedono per quello che sono, invece di
     essere invisibilmente compattati vicino al punto precedente. Un punto
     senza `ora` leggibile non si disegna affatto: **mai un'ora inventata**,
     la stessa disciplina di `_difference` (Python) per un valore che non si
     puo' calcolare.

     -- Il dubbio aperto sul fuso (brief-dodicesima.md, punto 3, misurato dal
     revisore, non dedotto da questo commento) --
     Ogni etichetta resta VERA (nessuna frase falsa: la pagina non chiama mai
     questo orario "ora della casa", ed e' dichiarato che e' quello del
     BROWSER). Ma con un browser in un fuso diverso da quello della casa la
     giornata non SLITTA: **SI AVVOLGE**. Un punto delle 01:00 di casa,
     guardato da un fuso avanti di 18 ore o piu' (es. New York rispetto
     all'Italia), cade nello slot delle 19 di QUESTA pagina -- dopo
     mezzogiorno, non vicino alla mezzanotte com'era in casa: **la forma
     della giornata si rimescola**, non solo si sposta, ed e' peggio di uno
     scostamento per un grafico il cui unico scopo e' mostrare la forma. Nel
     caso reale (casa e chi guarda nello stesso fuso) l'errore e' zero, a
     qualunque ora. Non si corregge qui: la cura vera e' che la rotta mandi
     il fuso della CASA e che questa pagina lo usi OVUNQUE (qui e in
     `fmtIsoHour` sopra) al posto di quello del browser -- una fetta a se'. */

  /* Punto 3 del brief: «I momenti derivati ... come dati secchi accanto alla
     curva, non come frasi.» -- una lista etichetta/valore (`.bil-moments`,
     hiris-config.css), non un paragrafo discorsivo. Ogni momento e'
     opzionale (spec, "mai una chiave con un valore fittizio") e compare solo
     se c'e'.

     Punto 4 del brief-dodicesima (nota minore): estratta da `renderBalanceMoments`
     perche' la frase accessibile della curva (sotto, in `renderBalanceCurve`)
     doveva sapere se questa sezione avrebbe reso QUALCOSA -- prima lo
     decideva da sola guardando solo `!!momenti` (il campo c'e'), mentre QUI
     si rende solo per le chiavi note sotto: oggi i due insiemi coincidono
     (l'aggregazione non scrive mai un `momenti` con tutte le chiavi note
     assenti), ma una chiave nota nuova, aggiunta domani solo qui e non li',
     tornerebbe a rendere la frase orfana (lo stesso difetto del punto 3 del
     brief-pagina, chiuso sopra per la frase "gli stessi numeri"). Un solo
     elenco di chiavi note, letto da entrambi. */

  /* Le entita' che compongono il bilancio (trasparenza, spec §7): STESSO
     rivelatore sincrono di `detailsDisclosure`, riusato via `createDisclosure`
     -- non un secondo componente. */

  /* Il bilancio NON passa da `period()`/`mainPhrase()`: quelle due
     funzioni presuppongono la forma dell'episodio (un `inizio_ts`/`fine_ts`
     che apre e chiude una cosa accaduta, un `corpo.stato`), e il bilancio non
     ce l'ha -- e' il punto per cui questa fetta esiste (vedi il commento di
     testa del file). `inizio_ts`/`fine_ts` restano i confini del GIORNO
     (sempre chiuso, mai `fine_ts: None`: `aggregate_day`), non l'apertura e
     la chiusura di un evento: mostrarli con la freccia di `period()`
     rifarebbe esattamente lo stampo sbagliato che il mandato vieta. */

  /* Rilievo 7 della review: la gerarchia era rovesciata -- l'identificatore
     era il testo piu' in evidenza, il fatto («25/08 15:30 → 17:05 · da 18,2
     a 21,0») stava nella classe delle note a margine. L'occhio cerca il
     contrario: il COSA E' SUCCESSO e' il contenuto, l'identificatore e' il
     riferimento -- stessa gerarchia gia' in tree-route.js, il metro. */

  /* I due silenzi, detti e non nascosti (fetta «lo stato», 07/09/2026).

     `traduzioni` arriva da `GET /api/mind/facts` gia' ETICHETTATO da chi
     l'ha prodotto (`proxy/state_translations.py`): questa funzione lo
     TRASPORTA, non lo indovina confrontando stringhe.

     - `lette: false` -> gli stati restano in inglese perche' non si e'
       potuto chiedere a Home Assistant, e il motivo e' li' dentro. E'
       un'altra cosa da «questo stato non ha traduzione», che invece non si
       annuncia: HA stesso in quel caso mostra il grezzo, e non e' un
       difetto nostro da spiegare riga per riga.
     - `lingua` diversa da `it` -> gli stati sono resi nella lingua che il
       PROPRIETARIO ha scelto in Home Assistant, mentre il resto di questa
       pagina e' in italiano fisso. E' corretto -- e' la sua lingua -- ma le
       due cose divergono a vista, e tacerlo lascerebbe pensare a una resa
       fatta male. */


  /* ------------------------------------------------------- il resoconto (§9) */

  /* La resa del resoconto per UN UMANO.

     Il resoconto non e' fatto per un umano -- serve all'analista, e il suo
     documento markdown e' pensato per stare in un prompt. Qui si rende lo
     STESSO dato con l'idioma di questa pagina: stesso archivio, due rese, che
     e' la ragione per cui il documento si deriva invece di essere archiviato.

     **«Cosa non si sa» viene PRIMA.** In fondo a una tabella di numeri buoni
     non salterebbe all'occhio, ed e' la parte su cui il proprietario puo'
     fare qualcosa: una misura che sparisce e' il terzo innesco dell'analista,
     e sulla casa vera e' quello che ha lasciato il bilancio a zero per cinque
     giorni senza che nessuno se ne accorgesse. */
  function renderReport(body, report) {
    /* **Il giorno si DICE.** La sezione 03 mostra sempre UN giorno solo,
       mentre la 02 -- che condivide lo stesso selettore -- col bottone «vedi
       i piu' recenti» ne mostra molti insieme: senza la data scritta qui, chi
       ha appena premuto quel bottone leggerebbe dei numeri senza sapere a
       quando si riferiscono, accanto a un elenco che copre altri giorni. */
    if (report.giorno) line(body, 'Il resoconto di ' + ggMmAaaa(report.giorno) + '.', TONE_CALM);
    var misure = (report.misure || []).filter(function (m) { return 'valore' in m; });
    var ignote = (report.misure || []).filter(function (m) { return !('valore' in m); });
    var cronaca = report.cronaca || [];

    if (ignote.length) {
      subheading(body, 'Cosa non si sa');
      ignote.forEach(function (m) {
        var riga = el('div', 'sc-row');
        riga.appendChild(el('div', 'sc-row-title', (m.nome || m.soggetto) + ' · ' + m.misura));
        riga.appendChild(el('div', 'sc-row-why', m.non_calcolabile || ''));
        body.appendChild(riga);
      });
    }

    subheading(body, 'Le misure');
    if (!misure.length) {
      line(body, 'Nessuna misura per questo giorno: nessun dispositivo ha ancora una ricetta, ' +
        'oppure nessuna ha potuto calcolarsi.', TONE_CALM);
    } else {
      var grid = el('div', 'stat-grid');
      misure.forEach(function (m) {
        var tile = el('div', 'stat-tile');
        tile.appendChild(el('div', 'st-label', (m.nome || m.soggetto) + ' · ' + m.misura));
        tile.appendChild(el('div', 'st-value', m.valore + ' ' + (m.unita || '')));
        /* La copertura si dice SOLO quando non e' piena: «100%» accanto a ogni
           numero sarebbe rumore su cui l'occhio smette di fermarsi, ed e'
           proprio quando NON e' piena che deve fermarsi. */
        if (typeof m.copertura === 'number' && m.copertura < 1) {
          tile.appendChild(el('div', 'st-delta', 'su ' + fmtPercent(m.copertura) + ' del giorno'));
        }
        grid.appendChild(tile);
      });
      body.appendChild(grid);
    }

    /* **Le forme orarie si DICONO, non si stampano.** Misurato sulla casa vera
       il 14/09/2026: otto serie orarie pesavano il 75% delle misure del
       giorno, e stampate in una griglia diventavano una riga di
       «[object Object],[object Object],...» -- il contrario di leggibile. Qui
       si dice che ci sono e quanto sono fitte; il dato resta nell'archivio e
       si chiede quando serve. La sezione compare solo se c'e' qualcosa: un
       titolo sopra il vuoto e' rumore. */
    var forme = report.forme || [];
    if (forme.length) {
      subheading(body, 'Le forme del giorno');
      forme.forEach(function (f) {
        var punti = (f.valore || []).length;
        var riga = el('div', 'sc-row');
        riga.appendChild(el('div', 'sc-row-title', (f.nome || f.soggetto) + ' · ' + f.misura));
        riga.appendChild(el('div', 'sc-row-why',
          fmtCount(punti) + (punti === 1 ? ' punto orario' : ' punti orari')
          + (f.unita ? ' in ' + f.unita : '')));
        body.appendChild(riga);
      });
    }
    subheading(body, 'La cronaca');
    if (!cronaca.length) {
      line(body, 'Nessun fatto: quel giorno non è cambiato niente di ciò che si guarda.', TONE_CALM);
      return;
    }
    cronaca.forEach(function (v) { body.appendChild(chronicleLine(v)); });
  }

  /* Una riga della cronaca: quando, chi, cosa -- e quanti attributi si sono
     mossi mentre durava, che e' la meta' che rende rispondibile «il
     riscaldamento parte alle 15:30, la casa e' calda alle 16:30». */
  function chronicleLine(v) {
    var riga = el('div', 'sc-row');
    var quando = fmtTime(v.quando_ts) + (v.fine_ts ? ' → ' + fmtTime(v.fine_ts) : ' → in corso');
    /* `describeWatchedSubject` torna un OGGETTO (primary/secondary/technical),
       non una stringa: concatenarlo scriverebbe «[object Object]» nella riga.
       `technical` significa che il nome amichevole non c'era -- lo si
       DICHIARA, con la stessa etichetta della sezione 01, invece di spacciare
       un `entity_id` nudo per un nome. */
    var d = describeWatchedSubject(v.chi || '', v.nome);
    var titolo = el('div', 'sc-row-title', quando + ' · ' + d.primary);
    if (d.technical) titolo.appendChild(el('span', 'field-hint', ' ' + SUBJECT_IS_ID));
    riga.appendChild(titolo);
    var cosa = v.cosa || '';
    var attributi = v.attributi || [];
    if (attributi.length) {
      cosa += ' — ' + fmtCount(attributi.length) + (attributi.length === 1
        ? ' cambio di attributo' : ' cambi di attributo');
    }
    riga.appendChild(el('div', 'sc-row-why', cosa));
    return riga;
  }

  function renderReportError(body, status, reload) {
    if (status === 404) {
      line(body, 'Per questo giorno non c’è ancora un resoconto. Non è un errore: ' +
        'il resoconto di una giornata si scrive la notte successiva, alle 00:20.', TONE_CALM);
      return;
    }
    if (status === 503) {
      line(body, 'L’archivio dei resoconti non è disponibile in questo momento. ' +
        'Non è un resoconto vuoto — è l’archivio stesso ad essere fermo.', TONE_PROBLEM);
    } else {
      line(body, 'Non è stato possibile leggere il resoconto. Riprova più tardi.', TONE_PROBLEM);
    }
    retryButton(body, reload);
  }


  /* ---------------------------------------------------------- l'analista (§10) */

  /* I tre inneschi, **a parole**. «1» non vuol dire niente per chi legge: la
     spec da' a ciascuno un nome, ed e' quello che va in pagina. Vivono qui in
     un posto solo perche' il numero arriva dal modello e la parola e' nostra:
     due elenchi divergerebbero al primo ritocco. */
  var TRIGGER_WORDS = {
    1: 'è cambiato, e non è spiegato',
    2: 'è stabile e costa',
    3: 'non c’è più',
  };

  function renderAnalysis(body, analysis) {
    var seen = (analysis && analysis.osservazioni) || [];
    if (!seen.length) {
      /* **Il silenzio e' un esito legittimo** (spec §10), e va detto: «ho
         guardato e non c'era niente da dire» non e' un guasto, ed e' diverso
         da «non ho guardato» -- che e' il 404, gestito altrove. */
      line(body, 'Ha guardato e non c’è niente da segnalare. Se una cosa funziona ' +
        'non va detta: otto giorni al 99% non sono una notizia.', TONE_CALM);
      return;
    }
    seen.forEach(function (o) {
      var riga = el('div', 'sc-row');
      var titolo = (o.nome || o.soggetto) + ' · ' + o.misura
        + (o.chiave ? '.' + o.chiave : '');
      riga.appendChild(el('div', 'sc-row-title', titolo));

      /* Il numero e la sua storia, sulla riga sua: «non si inventa una
         soglia» vuol dire che chi legge deve vedere **contro cosa** e' stato
         misurato, e su quanti giorni. «La base e' sottile» e' un fatto da
         leggere, non una cosa che decidiamo noi. */
      var numeri = [];
      if (o.valore !== null && o.valore !== undefined) {
        numeri.push(String(o.valore) + (o.unita ? ' ' + o.unita : ''));
      }
      if (o.mediana !== null && o.mediana !== undefined) {
        numeri.push('di solito ' + o.mediana);
      }
      if (o.quanti_scarti !== null && o.quanti_scarti !== undefined) {
        numeri.push(o.quanti_scarti + ' scarti');
      }
      if (o.base !== null && o.base !== undefined) {
        numeri.push('su ' + fmtCount(o.base) + ' giorni');
      }
      if (typeof o.copertura === 'number' && o.copertura < 1) {
        numeri.push('copertura ' + fmtPercent(o.copertura));
      }
      if (numeri.length) riga.appendChild(el('div', 'field-hint', numeri.join(' · ')));

      riga.appendChild(el('div', 'sc-row-why', o.cosa || ''));

      var coda = [];
      var parola = TRIGGER_WORDS[o.innesco];
      if (parola) coda.push('Perché lo dice: ' + parola + '.');
      /* **Cio' che e' spiegato si distingue da cio' che non lo e'**: e' la
         differenza fra una scoperta e una conferma, e la spec la chiede. */
      if (o.spiegato) coda.push('È spiegato: ' + o.spiegato + '.');
      if (o.cosa_cambierebbe) coda.push('Cosa cambierebbe: ' + o.cosa_cambierebbe);
      if (coda.length) riga.appendChild(el('div', 'sc-row-why', coda.join(' ')));
      body.appendChild(riga);
    });
  }

  function renderAnalysisError(body, status, reload) {
    if (status === 404) {
      /* «Non ho guardato» non e' «ho guardato e non c'era niente»: la prima
         e' questa, la seconda e' un elenco vuoto. */
      line(body, 'L’analista non ha ancora guardato questo giorno. Gira una volta ' +
        'all’ora, e un giorno ha una analisi sola.', TONE_CALM);
      return;
    }
    line(body, 'Non è stato possibile leggere l’analisi. Riprova più tardi.', TONE_PROBLEM);
    retryButton(body, reload);
  }

  function loadAnalysis(body, day) {
    clearEl(body);
    line(body, 'Caricamento…', TONE_CALM);
    function reload() { return loadAnalysis(body, day); }
    var giorno = day || localOggi();
    return read('api/mind/analysis?day=' + encodeURIComponent(giorno)).then(function (occurrence) {
      clearEl(body);
      if (!occurrence.ok) { renderAnalysisError(body, occurrence.status, reload); return; }
      renderAnalysis(body, occurrence.corpo.analisi || {});
    }, function () {
      clearEl(body);
      renderAnalysisError(body, null, reload);
    });
  }

  /* L'analisi e' di OGGI, non di ieri: legge i resoconti fino a ieri e parla
     adesso. Il selettore del giorno governa il resoconto, non lei. */
  function localOggi() { return isoData(new Date()); }

  /* ------------------------------------------------------------------------ mount */

  function loadWatching(body) {
    clearEl(body);
    line(body, 'Caricamento…', TONE_CALM);
    function reload() { return loadWatching(body); }
    return read('api/mind/watching').then(function (occurrence) {
      clearEl(body);
      if (!occurrence.ok) { renderWatchingError(body, occurrence.status, reload); return; }
      renderScope(body, occurrence.corpo);
    }, function () {
      clearEl(body);
      renderWatchingError(body, null, reload);
    });
  }

  /* Rilievo 8b: due cambi rapidi di giorno lanciavano due richieste senza
     guardia -- se la piu' lenta arrivava dopo, la pagina mostrava il giorno
     sbagliato. Un contatore di generazione, incrementato ad ogni chiamata:
     solo l'ultima "vince" la resa, qualunque ordine di arrivo prendano le
     risposte. */

  var reportGeneration = 0;

  function loadReport(body, day) {
    var myGeneration = ++reportGeneration;
    clearEl(body);
    line(body, 'Caricamento…', TONE_CALM);
    function reload() { return loadReport(body, day); }
    var giorno = day || ieriLocale();
    return read('api/mind/report?day=' + encodeURIComponent(giorno)).then(function (occurrence) {
      if (myGeneration !== reportGeneration) return;
      clearEl(body);
      if (!occurrence.ok) { renderReportError(body, occurrence.status, reload); return; }
      renderReport(body, occurrence.corpo.resoconto || {});
    }, function () {
      if (myGeneration !== reportGeneration) return;
      clearEl(body);
      renderReportError(body, null, reload);
    });
  }


  /* ------------------------------------------------------------- il sapere (§8) */

  /* I campi del sapere, detti come li direbbe una persona.

     La traduzione avviene al confine, e il confine è questa pagina: nel
     sapere il campo si chiama `ricetta_non_serve` perché è una colonna, qui
     si legge «niente da misurare» perché è una frase. Senza, la piastrella
     più grossa della sezione -- 18 dispositivi su 52, sulla casa vera --
     sembrerebbe un guasto, mentre è il contrario: il modello ha guardato e ha
     detto che non c'è niente che valga la pena. Un campo che non è in questa
     mappa esce col suo nome: meglio una parola tecnica che una inventata. */
  var KNOWLEDGE_FIELDS = {
    ricetta: 'ricette',
    ricetta_non_serve: 'niente da misurare',
    ricetta_non_capita: 'ricette non capite',
    significato: 'significati',
    attributi: 'attributi che contano',
    direzione: 'direzioni dell’energia'
  };

  function knowledgeFieldLabel(campo) {
    return KNOWLEDGE_FIELDS[campo] || campo;
  }

  /* -------------------------------------------------------- i giudizi sui tipi (§4, §7)

     Sezione 04, gerarchia approvata dal proprietario il 17/09/2026 (task 9,
     .superpowers/sdd/2026-09-16-il-giudizio-dei-tipi/task-9-ux-approvata.md):
     «Cosa non ha capito» (sopra, invariata) -> «Le tue correzioni» (righe
     `proprietario`+`altro`, e il modulo di aggiunta in testa) -> «I giudizi
     del seme» (sei gruppi chiusi, uno per campo) -> «Le domande aperte»
     (sei, chiuse) -> «Cosa ha capito» (sotto, invariata).

     **Una riga vive in un posto solo** (fondamenta HIRIS): chi ha corretto
     un giudizio del seme sparisce dal SUO gruppo e vive solo in «Le tue
     correzioni» -- il gruppo del seme ne conta il numero rimasto, non la
     nasconde e basta.

     Sicurezza: mai innerHTML sul testo del server -- le domande aperte
     portano backtick e `**`, e si costruiscono nodo per nodo (vedi
     `appendMarkedText`). */

  /* I sei campi, nell'ordine approvato -- letterale, identico a
     GENRE_FIELD/RESTING_FIELD/NOTABLE_FIELD/OPERABLE_FIELD/
     PARAMETER_LIMITS_FIELD/WORKING_FIELD di home_space/type_judgments.py
     (contati nel sorgente Python, non ricopiati da una variabile). */
  var JUDGMENT_FIELD_GROUPS = [
    { campo: 'genere', etichetta: 'Genere' },
    { campo: 'riposo', etichetta: 'Riposo' },
    { campo: 'notevole', etichetta: 'Notevole' },
    { campo: 'accendibile', etichetta: 'Accendibile' },
    { campo: 'limiti_parametri', etichetta: 'Limiti dei parametri' },
    { campo: 'lavoro', etichetta: 'Lavoro' }
  ];

  /* Solo `genere` si corregge sul posto in v1 (forma approvata, punto 3 e
     "cosa la v1 non fa"): gli altri cinque restano in sola lettura da qui. */
  var EDITABLE_JUDGMENT_FIELD = 'genere';

  /* Valori JSON (liste/mappe), non tradotti -- `.text-mono` (forma
     approvata, punto 2). Gli altri campi portano un valore già leggibile. */
  var JSON_JUDGMENT_FIELDS = { riposo: true, lavoro: true, limiti_parametri: true };

  /* I generi che il proprietario può scegliere: CHRONICLE_GENRES meno
     `guasto` (le condizioni di sistema -- mai lo stato di un tipo o di
     un'entità, `judgments._SYSTEM_ONLY_GENRE`) più `nessuno` (`NO_GENRE`,
     "niente episodi") -- letterale da home_space/type_vocabulary.py, forma
     approvata punto 3. */
  var JUDGMENT_GENRE_OPTIONS = [
    { valore: 'funzionamento', etichetta: 'Funzionamento' },
    { valore: 'presenza', etichetta: 'Presenza' },
    { valore: 'sicurezza', etichetta: 'Sicurezza' },
    { valore: 'nessuno', etichetta: 'Nessuno (niente episodi)' }
  ];

  /* 22 giorni: la ritenzione del grezzo, `mind/store.READING_RETENTION_S`
     (server). NON arriva nel payload di `/api/mind/knowledge` -- se un
     campo un giorno la porta, questa costante si toglie e si legge da lì
     (regola del brief, task 9, sezione 04). */
  var CHRONICLE_RETENTION_DAYS = 22;

  function chronicleCostPhrase() {
    return 'rifà la cronaca degli ultimi ' + fmtDays(CHRONICLE_RETENTION_DAYS * 86400) +
      ', un giorno ogni 5 minuti: fino a circa due ore';
  }

  /* Solo la DATA (senza l'ora): `proprietario` la vuole con l'anno
     («Corretto da te il gg/mm/aaaa», forma approvata punto 4) -- `fmtWhenFull`
     porta anche l'ora, che qui è un dato in più da leggere. */
  function fmtDateOnly(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear();
  }

  /* Solo giorno/mese, SENZA anno: `altro` la vuole così («Modificata a mano
     il gg/mm da {chi}», forma approvata punto 4) -- un'asimmetria scritta
     apposta nella forma approvata, non un refuso. */
  function fmtDayMonth(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1);
  }

  /* Il livello che il soggetto occupa nelle chiavi di `TypeJudgments`
     (dominio -> coppia -> entità, mirror di `judgments._level`, letto nel
     sorgente Python il 17/09/2026): serve solo a ORDINARE le righe del
     gruppo (forma approvata, punto 2), non a validarle -- quello lo fa il
     server, sul 400. */
  function judgmentSubjectLevel(kind, subject) {
    if (kind === 'entita') return 2;
    return (String(subject || '').indexOf('.') === -1) ? 0 : 1;
  }

  function sortJudgmentRows(righe) {
    return righe.slice().sort(function (a, b) {
      var la = judgmentSubjectLevel(a.soggetto_genere, a.soggetto);
      var lb = judgmentSubjectLevel(b.soggetto_genere, b.soggetto);
      if (la !== lb) return la - lb;
      return String(a.soggetto).localeCompare(String(b.soggetto));
    });
  }

  /* Etichetta + campo, stessa forma micro del modulo di correzione di
     memory-route.js (`costruisciModuloCorrezione::field`) -- non condivisa
     fra i due file (non c'è un modulo comune per questi helper di UI), ma
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

  /* Nessun `aria-label` qui: il select passa SEMPRE da `judgmentField`
     (sopra), che ora gli lega un'etichetta VERA (`for`/`id`) -- un
     `aria-label` in più vincerebbe quel legame per il nome accessibile
     (la regola di calcolo lo preferisce) e lo renderebbe invisibile a chi
     naviga per etichette, mentre il testo visibile resterebbe un altro
     («Genere» in entrambi i casi qui, ma sarebbe un doppione fragile). */
  function genreSelect() {
    var sel = el('select');
    JUDGMENT_GENRE_OPTIONS.forEach(function (o) {
      var opt = el('option', null, o.etichetta);
      opt.value = o.valore;
      sel.appendChild(opt);
    });
    return sel;
  }

  /* Il testo da mostrare quando la SCRITTURA (non la lettura della sezione)
     fallisce per un motivo che non è 400/409 -- stesso tono di
     `renderKnowledgeError`, adattato a un verbo di scrittura invece che di
     lettura (regola del brief: "le frasi di renderKnowledgeError"). */
  /* `corpo` è quello della risposta, quando c'è: dal 17/09/2026 il 503 ha DUE
     ragioni -- il sapere non collegato, e l'archivio che c'è ma non si lascia
     scrivere (disco pieno, base occupata; vedi `handlers_mind.py`) -- e il
     server manda la sua in `errore`. Scriverne qui una sola sarebbe una
     ragione falsa accanto al codice per l'altra metà dei casi. Il testo di
     riserva resta per quando il corpo non c'è (un 503 del proxy) o per un
     guasto di rete, dove non c'è nessuna risposta da leggere. */
  function judgmentWriteErrorText(status, corpo) {
    if (corpo && corpo.errore) return corpo.errore;
    if (status === 503) {
      return 'Il sapere non è collegato in questo momento. Non è vuoto — è che non si può leggere.';
    }
    return 'Non è stato possibile scrivere. Riprova più tardi.';
  }

  /* La scrittura, condivisa dall'editor del genere, da «Torna al seme» e dal
     modulo di aggiunta -- un solo posto per i quattro esiti della spec
     (200/400/409/rete), così i tre chiamanti non li interpretano ciascuno a
     modo suo (fondamenta: nessun doppione). */
  function submitJudgment(payload, ui) {
    ui.button.disabled = true;
    ui.esito.textContent = 'Scrivo…';
    return write('api/mind/judgment', payload).then(function (occurrence) {
      if (occurrence.ok) {
        /* 200: la sezione si ricarica intera -- la riga riappare in «Le tue
           correzioni» con la sua provenienza nuova (forma approvata, punto 3).
           `true`: sposta il focus sul titolo della sezione dopo il
           ricaricamento (fix round 1, MINOR 6) -- senza, il bottone appena
           premuto sparisce col resto del corpo e il focus cade su `<body>`. */
        loadKnowledge(ui.outerBody, undefined, true);
        return;
      }
      ui.button.disabled = false;
      if (occurrence.status === 400) {
        ui.esito.textContent = (occurrence.corpo && occurrence.corpo.errore) ||
          'Questa correzione non si può scrivere.';
        return;
      }
      if (occurrence.status === 409) {
        var motivo = (occurrence.corpo && occurrence.corpo.errore) || '';
        // Fix round 1 (revisione Fable, MINOR 4): senza un punto dopo
        // `motivo` la frase successiva si leggeva attaccata («…seme non ce
        // l'ha Il sapere legge…»). Non se ne aggiunge uno se `motivo` lo
        // porta già (niente «..»).
        var motivoPuntato = motivo && !/[.!?]$/.test(motivo) ? motivo + '.' : motivo;
        loadKnowledge(ui.outerBody, 'La correzione è scritta ma non è in vigore: ' + motivoPuntato +
          ' Il sapere legge solo il seme.', true);
        return;
      }
      ui.esito.textContent = judgmentWriteErrorText(occurrence.status, occurrence.corpo);
    }, function () {
      ui.button.disabled = false;
      ui.esito.textContent = judgmentWriteErrorText(null);
    });
  }

  /* «Correggi» il genere sul posto (SOLO questo campo, forma approvata
     punto 3): apre/chiude un editor dentro la riga, senza modale. */
  function genreCorrectControl(g, outerBody) {
    var wrap = el('div');
    var toggle = el('button', 'btn btn-ghost', 'Correggi');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    var panel = el('div');
    panel.hidden = true;
    panel.style.cssText = 'margin-top:8px;display:flex;flex-direction:column;gap:6px;max-width:340px';

    toggle.addEventListener('click', function () {
      var aperto = toggle.getAttribute('aria-expanded') === 'true';
      if (aperto) { clearEl(panel); panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); return; }
      clearEl(panel);
      var sel = genreSelect();
      if (JUDGMENT_GENRE_OPTIONS.some(function (o) { return o.valore === g.valore; })) sel.value = g.valore;
      panel.appendChild(judgmentField('Genere', sel));
      panel.appendChild(el('p', 'field-hint', 'Cambiare il genere ' + chronicleCostPhrase() + '.'));
      var esito = el('p', 'sc-desc', '');
      var scrivi = el('button', 'btn btn-ghost', 'Scrivi');
      scrivi.type = 'button';
      scrivi.addEventListener('click', function () {
        submitJudgment({
          soggetto_genere: g.soggetto_genere, soggetto: g.soggetto, campo: EDITABLE_JUDGMENT_FIELD,
          valore: sel.value
        }, { button: scrivi, esito: esito, outerBody: outerBody });
      });
      panel.appendChild(scrivi);
      panel.appendChild(esito);
      panel.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
    });

    wrap.appendChild(toggle);
    wrap.appendChild(panel);
    return wrap;
  }

  /* «Torna al seme» (forma approvata, punto 5): niente `confirm()`, due
     passi in linea. Vale per righe `proprietario` E `altro`, di qualunque
     campo -- manda `valore: null`. */
  function revertToSeedControl(g, outerBody) {
    var wrap = el('div');
    var start = el('button', 'btn btn-ghost', 'Torna al seme');
    start.type = 'button';
    var confirmBox = el('div');
    confirmBox.hidden = true;
    confirmBox.style.cssText = 'margin-top:6px;display:flex;flex-direction:column;gap:6px;max-width:340px';
    var warn = el('p', 'field-hint',
      'Cancella la tua correzione: il sapere riprende il valore del seme, o nessuna riga se il ' +
      'seme non ne ha. Anche questo ' + chronicleCostPhrase() + '.');
    var actions = el('div');
    actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap';
    var yes = el('button', 'btn btn-ghost btn-ghost-danger', 'Sì, torna al seme');
    yes.type = 'button';
    var cancel = el('button', 'btn btn-ghost', 'Annulla');
    cancel.type = 'button';
    var esito = el('p', 'sc-desc', '');

    /* Fix round 1 (revisione Fable, IMPORTANT 3): nascondere il bottone che
       ha il focus lo fa cadere su `<body>` (il browser non lo sposta da
       solo) -- chi naviga da tastiera perdeva il posto ad ogni passo.
       Si sposta ESPLICITAMENTE, dopo aver reso visibile il bersaglio. */
    start.addEventListener('click', function () {
      start.hidden = true; confirmBox.hidden = false; yes.focus();
    });
    cancel.addEventListener('click', function () {
      confirmBox.hidden = true; start.hidden = false; start.focus();
    });
    yes.addEventListener('click', function () {
      submitJudgment({
        soggetto_genere: g.soggetto_genere, soggetto: g.soggetto, campo: g.campo, valore: null
      }, { button: yes, esito: esito, outerBody: outerBody });
    });

    actions.appendChild(yes);
    actions.appendChild(cancel);
    confirmBox.appendChild(warn);
    confirmBox.appendChild(actions);
    confirmBox.appendChild(esito);
    wrap.appendChild(start);
    wrap.appendChild(confirmBox);
    return wrap;
  }

  /* La provenienza di una riga (forma approvata, punto 4): `seme` è un
     testo quieto, `proprietario`/`altro` sono badge -- lo stesso linguaggio
     di `.agent-badge` già in uso nel resto della pagina, non un componente
     nuovo.

     **Fix round 1 (revisione Fable, IMPORTANT 1)**: la forma approvata dice
     che una riga corretta dal proprietario porta ANCHE «La cronaca dei
     giorni passati si rifà da sola» -- mancava del tutto. Sta qui, accanto
     al badge, perché è una proprietà della riga finché resta `proprietario`
     (non una notifica che sparisce al primo ricaricamento): chi rivede la
     pagina domani deve rileggerla, non solo chi l'ha appena scritta. */
  function provenanceNode(g) {
    if (g.da === 'proprietario') {
      var wrap = el('span', 'jr-provenance');
      wrap.appendChild(el('span', 'agent-badge badge-on', 'Corretto da te il ' + (fmtDateOnly(g.quando_ts) || '—')));
      wrap.appendChild(el('span', 'field-hint', 'La cronaca dei giorni passati si rifà da sola.'));
      return wrap;
    }
    if (g.da === 'altro') {
      return el('span', 'agent-badge badge-warn',
        'Modificata a mano il ' + (fmtDayMonth(g.quando_ts) || '—') + ' da ' + (g.chi || 'qualcun altro'));
    }
    return el('span', 'field-hint', 'dal seme');
  }

  function judgmentValueNode(g) {
    var cls = JSON_JUDGMENT_FIELDS[g.campo] ? 'text-mono' : null;
    return el('span', cls, g.valore == null ? '—' : g.valore);
  }

  /* Una riga: `soggetto | valore | provenienza | azioni` (forma approvata,
     punto 6), a griglia larga e impilata sotto i 768px -- mai una
     `<table>` (CSS: `.jr-row` in hiris-config.css). */
  function judgmentRow(g, outerBody) {
    var riga = el('div', 'sc-row jr-row');
    riga.appendChild(el('div', 'jr-subject text-mono', g.soggetto));
    var meta = el('div', 'jr-meta');
    meta.appendChild(judgmentValueNode(g));
    meta.appendChild(provenanceNode(g));
    riga.appendChild(meta);
    var actions = el('div', 'jr-actions');
    if (g.campo === EDITABLE_JUDGMENT_FIELD) actions.appendChild(genreCorrectControl(g, outerBody));
    if (g.da === 'proprietario' || g.da === 'altro') actions.appendChild(revertToSeedControl(g, outerBody));
    riga.appendChild(actions);
    return riga;
  }

  /* Il modulo di aggiunta (forma approvata, punto 7): soggetto libero,
     tipo/entità OBBLIGATORIO (guida `soggetto_genere`), genere. Nessuna
     validazione client della FORMA del soggetto -- il 400 del server la
     spiega; il tipo/entità invece si controlla qui, perché senza non c'è
     `soggetto_genere` da mandare affatto. */
  function addJudgmentForm(outerBody) {
    /* Fix round 1 (revisione Fable, MINOR 8): era un `<div>` con un bottone
       `type="button"` -- Invio nel campo Soggetto non mandava niente, e
       `required` sui radio non aveva alcun form da validare. Un `<form>`
       vero con un bottone `type="submit"` restituisce entrambi; il
       controllo JS sul radio mancante resta (vedi sotto) perché un evento
       'submit' sintetico (dispatchEvent, come nei test) NON passa dalla
       validazione nativa del browser -- solo un invio vero da tastiera/
       mouse la passa. */
    var wrap = el('form', 'field-group jr-add-form');
    wrap.style.cssText = 'border:1px solid var(--border-2);border-radius:8px;padding:10px 12px;' +
      'margin-bottom:10px;display:flex;flex-direction:column;gap:8px;max-width:420px';

    var subjectInput = el('input');
    subjectInput.type = 'text';
    subjectInput.placeholder = 'binary_sensor.occupancy';
    wrap.appendChild(judgmentField('Soggetto', subjectInput));

    var radioName = 'judgment-add-kind-' + Math.random().toString(36).slice(2);
    var radioWrap = el('div');
    radioWrap.style.cssText = 'display:flex;gap:14px;flex-wrap:wrap';
    function radioOption(value, testo) {
      var label = el('label');
      label.style.cssText = 'display:flex;align-items:center;gap:6px;min-height:28px';
      var input = el('input');
      input.type = 'radio'; input.name = radioName; input.value = value; input.required = true;
      label.appendChild(input);
      label.appendChild(document.createTextNode(testo));
      radioWrap.appendChild(label);
      return input;
    }
    var radioTipo = radioOption('tipo', 'Un tipo');
    var radioEntita = radioOption('entita', 'Un’entità');
    wrap.appendChild(radioWrap);
    wrap.appendChild(el('p', 'field-hint',
      'Un tipo vale per tutti i dispositivi di quella classe; un’entità per uno solo.'));

    var sel = genreSelect();
    wrap.appendChild(judgmentField('Genere', sel));

    var esito = el('p', 'sc-desc', '');
    var scrivi = el('button', 'btn btn-ghost', 'Scrivi');
    scrivi.type = 'submit';
    wrap.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var scelto = radioTipo.checked ? 'tipo' : (radioEntita.checked ? 'entita' : null);
      if (!scelto) {
        esito.textContent = 'Scegli se è un tipo o un’entità.';
        return;
      }
      submitJudgment({
        soggetto_genere: scelto, soggetto: subjectInput.value.trim(), campo: EDITABLE_JUDGMENT_FIELD,
        valore: sel.value
      }, { button: scrivi, esito: esito, outerBody: outerBody });
    });
    wrap.appendChild(scrivi);
    wrap.appendChild(esito);
    return wrap;
  }

  /* «Le tue correzioni» (forma approvata, gerarchia): il modulo di aggiunta
     in testa, sempre visibile, poi le righe `proprietario` e `altro` --
     ovunque vivessero nel seme, qui vivono UNA volta sola.

     Torna il titolo (`<h3>`): fix round 1 (MINOR 6) lo rende focalizzabile
     (`tabindex=-1`) e ci sposta il focus dopo un ricaricamento innescato da
     una scrittura -- senza, il bottone appena premuto sparisce col resto
     del corpo e il focus cade su `<body>`, e chi naviga da tastiera perde
     il posto. */
  function renderCorrections(body, giudizi, outerBody) {
    var heading = subheading(body, 'Le tue correzioni');
    heading.tabIndex = -1;
    body.appendChild(addJudgmentForm(outerBody));

    var corrette = sortJudgmentRows(giudizi.filter(function (g) {
      return g.da === 'proprietario' || g.da === 'altro';
    }));
    if (!corrette.length) {
      line(body, 'Nessuna correzione ancora: le righe che scrivi da qui vivono da sole.', TONE_CALM);
      return heading;
    }
    corrette.forEach(function (g) { body.appendChild(judgmentRow(g, outerBody)); });
    return heading;
  }

  /* «I giudizi del seme» (forma approvata, punto 2): sei gruppi chiusi, uno
     per campo, ordinati per soggetto dentro. Il conteggio si calcola dai
     dati -- mai scritto a mano -- e porta anche le correzioni tolte da qui
     («25 dal seme · 1 corretta da te»): la riga vive solo in «Le tue
     correzioni», ma il numero del gruppo racconta lo storico intero.

     **Fix round 1 (revisione Fable, MINOR 5)**: il conteggio contava solo
     `da === 'proprietario'` -- una riga `altro` (modificata a mano, fuori
     da questa porta) spariva dal gruppo E dal conteggio, e il commento
     sopra («racconta lo storico intero») era falso proprio per quel caso.
     Ora conta entrambe, separate: «N dal seme · M corretta/e da te · K
     modificata/e a mano» (una parte si omette se il suo numero è zero). */
  function renderSeedGroups(body, giudizi, outerBody) {
    subheading(body, 'I giudizi del seme');
    JUDGMENT_FIELD_GROUPS.forEach(function (gruppo) {
      var semeRighe = sortJudgmentRows(giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'seme';
      }));
      var correzioni = giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'proprietario';
      }).length;
      var modificheAMano = giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'altro';
      }).length;
      var parti = [];
      if (correzioni || modificheAMano) {
        parti.push(fmtCount(semeRighe.length) + ' dal seme');
        if (correzioni) parti.push(fmtCount(correzioni) + (correzioni === 1 ? ' corretta da te' : ' corrette da te'));
        if (modificheAMano) {
          parti.push(fmtCount(modificheAMano) + (modificheAMano === 1 ? ' modificata a mano' : ' modificate a mano'));
        }
      } else {
        parti.push(fmtCount(semeRighe.length));
      }
      var etichetta = gruppo.etichetta + ' · ' + parti.join(' · ');
      body.appendChild(createDisclosure(etichetta, etichetta, function (panel) {
        if (!semeRighe.length) {
          panel.appendChild(el('p', 'field-hint', 'Nessuna riga di questo campo.'));
          return;
        }
        semeRighe.forEach(function (g) { panel.appendChild(judgmentRow(g, outerBody)); });
      }, false));
    });
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

  /* «Le domande aperte» (forma approvata): 4 delle 6 non si rispondono da
     questa porta (il contratto non porta un campo di destinazione) -- in v1
     si mostrano da leggere, chiuse, senza modulo di risposta. */
  function renderOpenQuestions(body, domande) {
    subheading(body, 'Le domande aperte');
    if (!domande.length) {
      line(body, 'Il censore non ha domande aperte in questo momento.', TONE_CALM);
      return;
    }
    domande.forEach(function (q) {
      var chiavi = q.chiavi || [];
      var chiuso = firstSentenceTruncated(q.domanda, 80) + ' (' + fmtCount(chiavi.length) +
        (chiavi.length === 1 ? ' chiave)' : ' chiavi)');
      body.appendChild(createDisclosure(chiuso, chiuso, function (panel) {
        var testo = el('p', 'sc-desc');
        appendMarkedText(testo, q.domanda);
        panel.appendChild(testo);
        if (chiavi.length) panel.appendChild(el('p', 'text-mono', chiavi.join(', ')));
      }, false));
    });
  }

  function renderKnowledge(body, sapere) {
    var nonCapito = (sapere && sapere.non_capito) || [];
    var giudizi = (sapere && sapere.giudizi) || [];
    var domande = (sapere && sapere.domande_aperte) || [];

    /* **Ciò che non ha capito viene PRIMA.** È l'unica parte su cui il
       proprietario può fare qualcosa -- «quello è il contatore dell'acqua» --
       e in fondo a un elenco di conteggi non salterebbe all'occhio. Stessa
       regola di «cosa non si sa» nel resoconto. */
    subheading(body, 'Cosa non ha capito');
    if (!nonCapito.length) {
      line(body, 'Non c’è niente che non abbia capito. Quando il modello non riesce ' +
        'a leggere un dispositivo lo scrive qui, e basta una parola tua per risolverlo.',
        TONE_CALM);
    } else {
      nonCapito.forEach(function (r) {
        var riga = el('div', 'sc-row');
        riga.appendChild(el('div', 'sc-row-title',
          describeWatchedSubject(r.soggetto || '', null).primary));
        riga.appendChild(el('div', 'sc-row-why', r.valore || ''));
        var coda = [];
        if (r.chi) coda.push('L’ha scritto ' + r.chi + '.');
        if (r.quando_ts) coda.push('Il ' + fmtWhenFull(r.quando_ts) + '.');
        if (coda.length) riga.appendChild(el('div', 'field-hint', coda.join(' ')));
        body.appendChild(riga);
      });
    }

    /* «Le tue correzioni» -> «I giudizi del seme» -> «Le domande aperte»
       (forma approvata, gerarchia). `outerBody` è la sezione intera: ogni
       scrittura la ricarica per intero (spec: la correzione vale subito).
       Il titolo di «Le tue correzioni» torna indietro (fix round 1, MINOR 6):
       `loadKnowledge` lo usa per rimettere il focus dopo una scrittura. */
    var correctionsHeading = renderCorrections(body, giudizi, body);
    renderSeedGroups(body, giudizi, body);
    renderOpenQuestions(body, domande);

    subheading(body, 'Cosa ha capito');
    var righe = (sapere && sapere.conteggi && sapere.conteggi.righe) || [];
    if (!righe.length) {
      line(body, 'Il sapere è vuoto: nessuna riga, di nessuna specie.', TONE_UNKNOWN);
      return correctionsHeading;
    }
    /* **Per specie e provenienza, non un totale solo**: «177 significati
       importati da Home Assistant» e «tre ricette dedotte dal modello» sono
       due fatti diversi, e il secondo è quello che il modello ha aggiunto. */
    var grid = el('div', 'stat-grid');
    righe.forEach(function (r) {
      var tile = el('div', 'stat-tile');
      tile.appendChild(el('div', 'st-label',
        knowledgeFieldLabel(r.campo) + ' · ' + r.specie));
      tile.appendChild(el('div', 'st-value', fmtCount(r.quante)));
      tile.appendChild(el('div', 'st-delta', r.provenienza));
      grid.appendChild(tile);
    });
    body.appendChild(grid);
    return correctionsHeading;
  }

  function renderKnowledgeError(body, status, reload) {
    if (status === 503) {
      line(body, 'Il sapere non è collegato in questo momento. Non è vuoto — ' +
        'è che non si può leggere.', TONE_PROBLEM);
    } else {
      line(body, 'Non è stato possibile leggere il sapere. Riprova più tardi.', TONE_PROBLEM);
    }
    retryButton(body, reload);
  }

  /* `notice` (facoltativo): il messaggio del 409 («scritta ma non in
     vigore», `submitJudgment`) sopravvive al ricaricamento -- senza,
     ricaricare subito la sezione lo cancellerebbe prima che chi ha
     scritto la correzione faccia in tempo a leggerlo. */
  /* `focusCorrections` (fix round 1, MINOR 6): dopo una scrittura riuscita
     (200) o non in vigore (409) il corpo si ricostruisce da zero -- il
     bottone appena premuto sparisce, e senza spostarlo esplicitamente il
     focus cade su `<body>`. Il bersaglio è il titolo di «Le tue
     correzioni» (`renderKnowledge` lo torna indietro), reso focalizzabile
     con `tabindex=-1` -- non un ricaricamento generico (mount iniziale,
     «Riprova»), dove spostare il focus da solo sarebbe invadente. */
  function loadKnowledge(body, notice, focusCorrections) {
    clearEl(body);
    line(body, 'Caricamento…', TONE_CALM);
    function reload() { return loadKnowledge(body); }
    return read('api/mind/knowledge').then(function (occurrence) {
      clearEl(body);
      if (!occurrence.ok) { renderKnowledgeError(body, occurrence.status, reload); return; }
      if (notice) line(body, notice, TONE_PROBLEM);
      var heading = renderKnowledge(body, occurrence.corpo);
      if (focusCorrections && heading && typeof heading.focus === 'function') heading.focus();
    }, function () {
      clearEl(body);
      renderKnowledgeError(body, null, reload);
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);

    outlet.appendChild(el('h1', 'page-title', 'L’osservatore'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Guarda la casa, ne ricava misure, e dice cosa si potrebbe fare. ' +
      'Non tocca niente: decidi tu.'));

    /* La descrizione dice COME si e' deciso (tutta la casa, l'obiettivo
       davanti, soggetto per soggetto), una volta sola: chi ha deciso e
       perche' stanno poi su ogni gruppo e su ogni riga (`renderScope`).
       Nessuna promessa di un bottone «togli» che oggi non c'e' (vedi il
       commento di testa): la frase dice cosa la pagina PROVA, non cosa
       fara'. */
    var watchingBody = section(outlet, '01', 'Cosa sto guardando',
      'L’osservatore ha guardato tutta la casa con l’obiettivo davanti e ha deciso soggetto per ' +
      'soggetto — con il motivo scritto e chi l’ha deciso, nessuna lista nel codice. Da qui si vede ' +
      'se l’obiettivo è stato capito: le scelte stanno accanto alla domanda a cui rispondono.');

    /* **La sezione 02 e' uscita** (spec §13, 15/09/2026): gli episodi non
       vivono piu' in uno strato loro, vivono nella cronaca del resoconto, e
       la 03 li mostra. Il selettore del giorno, che era suo, resta qui: ora
       comanda la 03, che e' l'unica che legge un giorno. */
    var controls = el('div');
    controls.style.cssText = 'display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:12px';
    var dayField = el('div');
    var dayLabel = el('label', 'field-hint', 'Giorno');
    var dayInput = el('input');
    dayInput.type = 'date';
    // Rilievo 3: l'etichetta era muta -- nessun for/id -- e per un lettore
    // di schermo il campo era una data anonima.
    dayInput.id = 'watcher-day';
    dayLabel.setAttribute('for', dayInput.id);
    dayField.appendChild(dayLabel);
    dayInput.value = ieriLocale();
    dayInput.style.cssText = 'display:block;padding:6px 8px;border-radius:8px;min-height:38px;box-sizing:border-box';
    dayField.appendChild(dayInput);
    controls.appendChild(dayField);

    /* **Il bottone «senza filtro» e' uscito** (15/09/2026). Serviva alla
       sezione degli oggetti, che poteva mostrarne molti giorni insieme; un
       RESOCONTO e' per definizione di un giorno solo, e quel bottone finiva
       per rifare esattamente cio' che la pagina fa gia' aprendosi. Un
       comando che non ha un contrario non e' un comando. */

    /* Sezione 02: il resoconto del giorno (spec §9). Era la 03 finche' gli
       oggetti avevano la loro. */
    var reportBody = section(outlet, '02', 'Il resoconto del giorno',
      'Cosa si è misurato, cosa non si è potuto misurare e perché, e l’indice ' +
      'di cosa è successo. È il materiale su cui ragiona l’analista: resta anche quando ' +
      'il grezzo di quel giorno sarà scaduto.');
    reportBody.parentNode.insertBefore(controls, reportBody);

    dayInput.addEventListener('change', function () {
      loadReport(reportBody, dayInput.value || null);
    });

    /* Sezione 03: l'analista (spec §10). Non ha selettore: legge i resoconti
       fino a ieri e parla di OGGI -- il giorno qui sopra governa il resoconto,
       non lei. */
    var analysisBody = section(outlet, '03', 'Cosa si potrebbe fare',
      'Quello che l’analista ha visto leggendo le misure di trenta giorni: cosa, ' +
      'perché lo dice, se è già spiegato, e cosa cambierebbe rispetto all’obiettivo. ' +
      'Il silenzio è un esito legittimo.');

    /* Sezione 04: il sapere (spec §8). «Se un dato c'e' e nessuno puo'
       chiederlo, non esiste»: fino al 15/09/2026 si leggeva da tre punti del
       codice e da nessuna pagina. */
    var knowledgeBody = section(outlet, '04', 'Cosa ho capito della casa',
      'Le direzioni dell’energia, i significati delle classi, gli attributi che ' +
      'valgono la pena e le ricette dei dispositivi — con la loro provenienza. ' +
      'E soprattutto ciò che non si è capito: è lì che una tua parola vale di più.');

    loadWatching(watchingBody);
    loadReport(reportBody, dayInput.value);
    loadAnalysis(analysisBody, null);
    loadKnowledge(knowledgeBody);
  }

  return {
    mount: mount,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiScope: renderScope,
    _rendiResoconto: renderReport,
    _rendiAnalisi: renderAnalysis,
    _rendiSapere: renderKnowledge
  };
})();
