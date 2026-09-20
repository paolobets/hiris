/* HIRIS · Configurazione · «L'osservatore» / scheda «L'osservatore» (spec
   2026-09-18 §4D).

   *Sta lavorando bene?* E' la sezione 01 di ieri: cosa si guarda, da quando,
   perche' -- e **l'obiettivo**, che si scrive da qui, unica manopola del
   prodotto: da quella frase dipendono cosa l'osservatore guarda, quali ricette
   il modello propone e cosa l'analista va a cercare.

   -- Trasparenza al posto del permesso (spec «i tre attori» §7, §5.1 e §11) --
   L'osservatore non chiede il permesso di guardare qualcosa: si deve poter
   vedere in ogni momento COSA sta guardando, DA QUANDO e PERCHE'.

   `GET /api/mind/watching` (`handle_watching`, hiris/app/api/handlers_mind.py)
   porta cinque parti in una risposta sola -- l'elenco di cio' che si guarda e'
   anche la prova che l'obiettivo e' stato capito, e «non sono due pagine» --
   e questa scheda le rende nell'ordine in cui si leggono:

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
   gruppo, col valore grezzo -- non sparisce mai.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server. L'unica POST e' quella dell'obiettivo, e porta `X-Requested-With`
   perche' passa dal `csrf_middleware`. */
window.HirisWatcherLavoro = (function () {
  'use strict';

  var S = HirisWatcherShared;
  var el = S.el;
  var clearEl = S.clearEl;
  var line = S.line;
  var subheading = S.subheading;
  var read = S.read;
  var write = S.write;
  var retryButton = S.retryButton;
  var createDisclosure = S.createDisclosure;
  var describeWatchedSubject = S.describeWatchedSubject;
  var ggMmAaaa = S.ggMmAaaa;
  var fmtWhenFull = S.fmtWhenFull;
  var fmtDays = S.fmtDays;
  var fmtHours = S.fmtHours;
  var fmtCount = S.fmtCount;
  var fmtDuration = S.fmtDuration;
  var fmtAgo = S.fmtAgo;
  var TONE_PROBLEM = S.TONE_PROBLEM;
  var TONE_CALM = S.TONE_CALM;
  var TONE_UNKNOWN = S.TONE_UNKNOWN;
  var SUBJECT_IS_ID = S.SUBJECT_IS_ID;
  var SUBJECT_IS_ID_PLURAL = S.SUBJECT_IS_ID_PLURAL;

  /* I tre autori possibili di una decisione dello scope (`author` in
     `mind/store.py`, `scope()`), nell'ordine in cui interessano a chi legge:
     prima cio' che ha deciso LUI, poi l'analista, poi l'osservatore (che e' la
     massa). Le condizioni di sistema (`autore: null`) chiudono, sempre. Solo
     ETICHETTE: la chiave resta quella del payload. Sono complementi («da te»,
     «dall'analista») perche' le due intestazioni che li usano hanno verbi
     diversi -- «Deciso ...» sopra, «Lasciato fuori ...» sotto -- e un'unica
     mappa serve entrambe. */
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
          /* **Il campo NON si svuota e la scheda non si ricarica.** Il
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
        /* Scritto: la scheda si rilegge intera, perche' l'obiettivo nuovo
           cambia anche «da quando» e la riconsiderazione. */
        carica(body);
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
     lasciarlo passare per un nome; `describeWatchedSubject` (condivisa con le
     altre schede, watcher-shared.js) separa i soggetti grezzi
     (`log:...@file:riga`, `integrazione:<id opaco>`) in nome leggibile +
     riferimento tecnico secondario, mai buttato ma in secondo piano
     (`.field-hint`). */
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
     scheda si legge a colpo d'occhio senza aprire niente.

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
     `.stat-tile`, lo stesso componente condiviso gia' usato dalla Dashboard. */
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
      // la tessera di un numero corto non ha questo problema, questa si'.
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
      // tutte e sei le parti della scheda: la pagina che deve dire «sta
      // funzionando?» moriva. Basta un esito nuovo, e `scaduta` e' arrivato
      // con quella stessa fetta.
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

  /* La scheda intera, dal payload di `GET /api/mind/watching` (vedi il
     commento di testa per le cinque cose e i tre stati). */
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

  function carica(corpo) {
    clearEl(corpo);
    line(corpo, 'Caricamento…', TONE_CALM);
    function reload() { return carica(corpo); }
    return read('api/mind/watching').then(function (occurrence) {
      clearEl(corpo);
      if (!occurrence.ok) { renderWatchingError(corpo, occurrence.status, reload); return; }
      renderScope(corpo, occurrence.corpo);
    }, function () {
      clearEl(corpo);
      renderWatchingError(corpo, null, reload);
    });
  }

  return {
    carica: carica,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiScope: renderScope
  };
})();
