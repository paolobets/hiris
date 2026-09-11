/* HIRIS · Configurazione · «L'osservatore» (route #/watcher)

   La prima fetta del cervello nuovo (docs/design/2026-08-26-l-osservatore.md).
   Guarda la casa e ne ricava oggetti -- non conclude niente, non parla, non
   tocca niente. Questa pagina e' la sola faccia che ha oggi: due GET,
   `api/mind/watching` e `api/mind/facts?day=...`
   (`hiris/app/api/handlers_mind.py`).

   -- Trasparenza al posto del permesso (spec §7; poi «i tre attori»,
      docs/design/2026-09-10-i-tre-attori.md §5.1 e §11) --
   L'osservatore non chiede il permesso di guardare qualcosa: si deve poter
   vedere in ogni momento COSA sta guardando, DA QUANDO e PERCHE'. **Dal
   11/09/2026 il pavimento non esiste piu'** (`mind/baseline.py` cancellato
   insieme alle sei «gambe» e al badge di provenienza che valeva sempre
   «Di serie»): l'osservatore guarda tutta la casa con l'obiettivo davanti e
   decide SOGGETTO PER SOGGETTO, col perche' scritto e chi l'ha deciso
   (`Watcher.watching()`, che legge lo scope di `ObservationsStore.scope()`).
   La sezione 01 rende quindi cinque cose in una risposta sola
   (`handle_watching`, `hiris/app/api/handlers_mind.py`): l'obiettivo,
   cosa si guarda, cosa e' stato lasciato fuori, la riconsiderazione e il
   volume scritto al giorno -- vedi il commento sopra `renderScope` per il
   perche' di ciascuna e per i tre stati (assente / vuoto / non leggibile)
   che ognuna distingue. Nessun bottone «togli» ancora: le due rotte di
   `handlers_mind.py` sono GET, e un controllo senza rotta dietro sarebbe un
   controllo che non controlla niente -- arrivera' con la sua rotta.

   -- Due sezioni separate, mai una dentro l'altra (mandato Task 7) --
   «Cosa sto guardando» (lo scope vivo, `Watcher.watching()`) e «Cosa e'
   successo» (gli episodi che l'aggregazione notturna ha scritto,
   `ObservationsStore.facts()`) rispondono a due domande diverse -- la
   prima e' una decisione, la seconda e' la memoria che ne esce -- e la spec
   le tiene separate apposta (§7 e' la pagina, §1-6 sono gli episodi).

   -- I SEI generi (`mind/facts.py::GENRES`, contati nel sorgente
      Python, non ricopiati -- correzione del giro «la pagina del bilancio»,
      punto 7, 27/08/2026: questa riga diceva "cinque", e da quando
      `bilancio` e' entrato in GENERI sono sei) --
   Cinque sono EPISODIO: funzionamento, presenza, energia, guasto, sicurezza.
   Ogni genere di episodio porta un
   `corpo` di forma diversa (`aggregate_day`): funzionamento/presenza/
   sicurezza/guasto portano `stato` (il valore che ha aperto l'episodio);
   **e, dal 07/09/2026 (fetta «lo stato»), `stato_reso` accanto ad esso
   QUANDO una resa esiste** -- lo stato GREZZO resta `stato`, la resa e' una
   chiave in piu' aggiunta al confine dell'API (`api/handlers_mind.py`), mai
   sopra il grezzo. Manca del tutto quando resa non ce n'e', come
   `direzione`: e le due ragioni per cui puo' mancare le distingue
   `corpo.traduzioni` della risposta, non questa chiave. Un episodio di
   `guasto` non ne ha mai una (il suo `stato` non e' uno stato di Home
   Assistant: e' `aperto`, `setup_retry`, parole nostre e della
   configurazione);
   energia porta `valore_iniziale`/`valore_finale`/`differenza` -- una
   VARIAZIONE fra due letture, mai presentata come un consumo da sola: il
   genere copre anche l'energia PRODOTTA da un impianto fotovoltaico.
   **Dal 27/08/2026 (mandato «le direzioni dell'energia») un episodio di
   energia porta anche `direzione`/`provenienza`, QUANDO si conoscono**
   (`HAClient.energy_directions`, `energy/get_prefs` + `translation_key`):
   il campo manca del tutto se non si conosce, mai una "sconosciuta"
   travestita da dato -- `mainPhrase`/`provenanceDirectionBadge` sotto
   lo mostrano solo quando c'e'. Il genere resta "energia": la direzione
   vive nell'EPISODIO, non e' un genere nuovo. Tutti e
   cinque portano `comprimari` (chi altro c'era, dal caso del lampadario) e
   `misure` (cosa hanno fatto le grandezze collegate mentre l'episodio
   durava) -- mostrati dietro un rivelatore SINCRONO (stesso principio di
   constructions-route.js §3: sono gia' nel payload, nasconderli dietro un
   fetch sarebbe la trappola che la guida degli Impegni vieta).

   -- Il SESTO genere, `bilancio`, e' un'ALTRA FORMA (mandato «il bilancio
      dell'energia», 27/08/2026 -- docs/design/2026-08-27-il-bilancio-dell-
      energia.md §3, .superpowers/sdd/2026-08-27-il-bilancio/brief-pagina.md) --
   un bilancio non e' una cosa accaduta fra due istanti, e' una QUANTITA' CON
   UNA FORMA, un giorno intero: renderlo con lo stampo dell'episodio («da X a
   Y», la freccia di `period()`) rifarebbe in pagina esattamente l'errore
   che il giro dei dati ha appena tolto dall'archivio (undici frammenti di
   energia per lo stesso dispositivo). Il suo `corpo` (`costruisci_corpo_
   bilancio` in mind/facts.py) non ha ne' `stato` ne' `valore_iniziale`/
   `valore_finale`: ha `totali` (SETTE dimensioni al massimo -- il consumo e'
   la settima, LETTA non dedotta: correzione ALTA della review, mandato «la
   pagina del bilancio», punto 1, 27/08/2026, vedi il commento sopra
   `BALANCE_DIRECTIONS` nel sorgente Python -- ognuna `{valore,provenienza}`),
   `forma` (le stesse dimensioni, un elenco di `{"ora","valore"}` per punto --
   **l'asse orario e' ARRIVATO il 27/08/2026** (mandato «la pagina del
   bilancio», punto 6): prima di questa correzione era una lista POSIZIONALE
   NUDA (l'indice non era l'ora, perche' HA omette le ore senza dati); ora
   ogni punto porta la SUA ora, `ora` e' lo stesso nome gia' usato da
   `picco_produzione` sotto -- vedi il contratto completo nel docstring di
   `build_balance_body`, mind/facts.py), `momenti` (fatti
   derivati -- prima/ultima ora di produzione, il picco, le quote, tutti con
   l'istante VERO), piu' `dispositivo` (nome leggibile) ed `entita` (i
   sensori che lo compongono, aggiunti da `aggregate_day`). `balanceLine`
   sotto lo rende per conto suo, SENZA passare da `mainPhrase`/
   `period()`: sono funzioni che presuppongono la forma dell'episodio, e
   usarle per un bilancio le forzerebbe fuori dal loro contratto.

   -- Il giorno di default (mandato Task 7, verifiche dal vivo #1) --
   L'aggregazione notturna scrive «ieri» alle 00:20 (`server.py::
   _aggrega_ieri`): il giorno di oggi, quasi sempre, non ha ancora nessun
   oggetto. Il selettore nasce sul giorno di ieri (calcolato nel fuso del
   BROWSER, non quello della casa -- e' scritto nel testo accanto al campo).
   Rilievo 12 della review: i due fusi possono differire di un GIORNO intero
   (non "un'ora", cifra non misurata) vicino alla mezzanotte, se si guarda da
   un fuso diverso da quello della casa -- nel caso reale (casa e utente
   nello stesso fuso) l'errore e' zero a qualunque ora. Un bottone accanto
   toglie il filtro e mostra i più recenti, senza indovinare quale giorno
   guardare.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server -- stessa disciplina di tree-route.js/memory-route.js. Nessuna
   POST in questa pagina: le due rotte sono GET, quindi nessun
   `X-Requested-With` da portare (non passano dal `csrf_middleware`). */
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
  var GENRE_LABEL = {
    funzionamento: 'Funzionamento', presenza: 'Presenza / assenza',
    energia: 'Energia', guasto: 'Guasto', sicurezza: 'Sicurezza',
    bilancio: 'Bilancio'
  };

  /* Le sette direzioni dell'energia (mandato «le direzioni dell'energia»,
     27/08/2026) -- letterali, identiche a quelle che
     `HAClient.energy_directions()` scrive in `corpo.direzione`. Una
     direzione non in questa mappa (un genere futuro che il backend sapesse
     dire e questa pagina non ancora) mostra comunque la sua parola grezza,
     mai "undefined" -- stessa regola di `GENRE_LABEL`/`AUTHOR_LABEL`. */
  var DIRECTION_LABEL = {
    produzione: 'Produzione', prelievo: 'Prelievo dalla rete',
    immissione: 'Immissione in rete', carica: 'Carica della batteria',
    scarica: 'Scarica della batteria', consumo: 'Consumo della casa',
    autoconsumo: 'Autoconsumo (prodotto e consumato sul posto)'
  };

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
  var BALANCE_DIRECTION_ORDER = ['produzione', 'autoconsumo', 'immissione', 'prelievo', 'carica', 'scarica', 'consumo'];

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

  function localToday() { return isoData(new Date()); }

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

  function period(o) {
    var start = fmtTime(o.inizio_ts);
    var fine = fmtTime(o.fine_ts);
    /* «in corso a fine giornata», non «ancora in corso» (cancello-rilascio-
       brief.md, punto 2): l'aggregazione e' per giornata, e un oggetto senza
       fine non e' un oggetto che questo istante sa ancora essere aperto --
       e' un oggetto che NON HA MAI RIVISTO una chiusura da quando la
       giornata in cui e' nato e' stata aggregata. Se l'episodio attraversa
       la mezzanotte, la sua vera fine (se c'e') e' scartata in silenzio
       dall'aggregazione del giorno dopo (spec §6): questa pagina non deve
       promettere una continuita' che l'aggregazione non tiene. */
    if (fine == null) return 'dalle ' + start + ', in corso a fine giornata';
    return start + ' → ' + fine;
  }

  /* La frase che apre la riga: cosa e' successo, per genere -- il corpo ha
     forma diversa per ciascuno (vedi il commento di testa). Nessuna frase
     generica: campi reali o niente. */
  function mainPhrase(o) {
    var c = o.corpo || {};
    if (o.genere === 'energia') {
      var base;
      if (c.differenza == null) {
        base = 'da ' + c.valore_iniziale + ' a ' + c.valore_finale + ' (non calcolabile: una sola lettura, o un valore non numerico)';
      } else {
        var flag = c.differenza >= 0 ? '+' : '';
        base = 'da ' + c.valore_iniziale + ' a ' + c.valore_finale + ' (' + flag + c.differenza + ')';
      }
      /* La direzione (mandato «le direzioni dell'energia», 27/08/2026): il
         campo non c'e' affatto quando non si conosce (ne' la dichiarata ne'
         la dedotta la sanno dire) -- niente "sconosciuta" nel testo. */
      if (c.direzione) {
        base += ' · ' + (DIRECTION_LABEL[c.direzione] || c.direzione);
      }
      return base;
    }
    if (o.genere === 'guasto') {
      /* Correzione onda finale, rilievo 1: "in corso" si decide da
         `fine_ts` (come gia' fa `period()` qui sopra), non da `c.stato`.
         Dal Task 2 `stato` porta la condizione VERA (`setup_retry`,
         `setup_error`, ...), che per un'integrazione non vale mai
         "aperto" nemmeno a episodio aperto -- e per un `problema:` resta
         "aperto" anche a episodio chiuso (spec §2.3). Le due domande sono
         indipendenti: questa riga risponde alla prima con `fine_ts`, poi
         mostra sempre la condizione come tale, mai come sinonimo di
         aperto/chiuso. */
      var aperto = o.fine_ts == null ? 'ancora aperto' : 'chiuso';
      /* Collaudo usabilita' 3.22, rilievo 2: un `problema:` porta
         `corpo.stato === 'aperto'` per costruzione (spec §2.3), a episodio
         aperto E a episodio chiuso -- e' la STESSA parola che questa riga ha
         appena scritto sotto un'altra forma («chiuso»/«ancora aperto»), mai
         un'informazione in piu'. Misurato: «chiuso · stato: aperto», due
         parole opposte a tre centimetri di distanza -- non e' l'episodio ad
         essere ambiguo, e' la ripetizione letterale di "aperto" a leggersi
         come una contraddizione quando l'episodio e' chiuso. Si toglie SOLO
         quando `stato` vale letteralmente "aperto": gli altri valori
         (`setup_retry`, `ERROR`, ...) restano, perche' sono condizioni vere
         e non sinonimi di aperto/chiuso -- il nome dell'episodio ("Guasto")
         insieme ad "ancora aperto"/"chiuso" dice gia' tutto cio' che
         "stato: aperto" ripeteva. */
      if (c.stato === 'aperto') return aperto;
      return c.stato != null ? aperto + ' · stato: ' + c.stato : aperto;
    }
    /* Fetta «lo stato» (07/09/2026): `stato_reso` e' la resa che il confine
       dell'API ha aggiunto ACCANTO al grezzo, mai al posto suo. Si legge la
       resa se c'e', il grezzo se no -- e quando non c'e' non si inventa
       niente: e' esattamente cio' che Home Assistant stesso mostra quando
       nessuno dei suoi quattro gradini risponde. Il PERCHE' manchi (le
       traduzioni non lette, oppure questo stato senza traduzione) lo dice
       `translationsNote` una volta per pagina, non ogni riga. */
    var shown = c.stato_reso != null ? c.stato_reso : c.stato;
    return shown != null ? 'stato: ' + shown : '(nessun dettaglio)';
  }

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
  function provenanceDirectionBadge(provenance) {
    if (provenance === 'dichiarata') {
      return { cls: 'badge-off', testo: 'Dichiarata — dalla dashboard Energia' };
    }
    if (provenance === 'dedotta') {
      return { cls: 'badge-warn', testo: 'Dedotta — dall’integrazione' };
    }
    return { cls: 'badge-warn', testo: provenance || 'provenienza sconosciuta' };
  }

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

  function protagonistName(o) {
    var c = o.corpo || {};
    if (c.titolo) return c.dominio ? c.titolo + ' (' + c.dominio + ')' : c.titolo;
    var p = parseSubjectPrefix(o.protagonista || '');
    if (p.kind === 'problema') return 'Problema Home Assistant: ' + p.rest;
    if (p.kind === 'integrazione') return 'Integrazione non caricata: ' + p.rest;
    // `p.location` puo' essere vuoto solo se il soggetto non porta una `@`
    // (oggi non capita mai: `watcher.py` scrive sempre `<logger>@<file>:<riga>`
    // -- ma questa riga non deve dipendere da quella garanzia per essere
    // corretta). Una `@` appesa senza nulla dopo sarebbe un artefatto della
    // resa, non un dato: il nit del revisore, 07/09/2026.
    if (p.kind === 'log') return 'Voce del registro di Home Assistant: ' + p.logger + (p.location ? '@' + p.location : '');
    if (p.kind === 'automazione') return 'Automazione: ' + p.rest;
    return p.rest;
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

  function detailsDisclosure(o) {
    var companions = (o.corpo && o.corpo.comprimari) || [];
    var measurements = (o.corpo && o.corpo.misure) || {};
    var chiaviMisure = Object.keys(measurements);
    if (!companions.length && !chiaviMisure.length) return null;

    /* Rilievo 8c: «Nascondi» da solo perde il referente quando piu' righe
       sono aperte insieme -- lo stesso principio di "Nascondi i dettagli
       tecnici" in constructions-route.js e "Nascondi il dettaglio" in
       agenda-route.js. */
    return createDisclosure('Chi c’era intorno', 'Nascondi chi c’era intorno', function (panel) {
      if (companions.length) {
        line(panel, 'Insieme a: ' + companions.join(', '), 'font-size:var(--fs-12);' + TONE_CALM);
      }
      chiaviMisure.forEach(function (k) {
        var m = measurements[k];
        line(panel, k + ': da ' + m.da + ' a ' + m.a, 'font-size:var(--fs-12);' + TONE_CALM);
      });
    });
  }

  /* ----------------------------------------------------- «il bilancio dell'energia»
     Mandato «il bilancio dell'energia», 27/08/2026. Vedi il commento di
     testa del file per il perche' (una quantita' con una forma, non un
     episodio) e per il contratto esatto del corpo. */

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  /* Un valore della gamba energia -> "24,5 kWh", virgola italiana. Il
     backend ha gia' arrotondato a 2 decimali (`build_balance_body`,
     mandato punto 6, il difetto misurato `+0.010000000000000009`): qui si
     FORMATTA, non si arrotonda una seconda volta -- `maximumFractionDigits:
     2` e' un tetto che non taglia nessuna cifra vera, `minimumFractionDigits:
     1` evita "24" secco per un numero che e' comunque una misura continua. */
  function fmtKwh(v) {
    if (v == null) return null;
    return v.toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 2 }) + ' kWh';
  }

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
  function localDateFromPoint(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function formatHourFromDate(d) {
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  function fmtIsoHour(iso) {
    var d = localDateFromPoint(iso);
    return d ? formatHourFromDate(d) : null;
  }

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
  function rendiTotaliBilancio(box, totali) {
    if (!totali) return;
    var present = BALANCE_DIRECTION_ORDER.filter(function (d) { return totali[d]; });
    if (!present.length) return;

    var grid = el('div', 'stat-grid');
    present.forEach(function (d) {
      var t = totali[d];
      var tile = el('div', 'stat-tile');
      tile.appendChild(el('div', 'st-label', DIRECTION_LABEL[d] || d));
      tile.appendChild(el('div', 'st-value', fmtKwh(t.valore)));
      // Punto 4 del brief: la provenienza della direzione, STESSO meccanismo
      // gia' usato dagli episodi di energia -- niente badge quando non si
      // conosce (mai una "sconosciuta" travestita da dato).
      if (t.provenienza) {
        var badge = provenanceDirectionBadge(t.provenienza);
        var delta = el('div', 'st-delta');
        delta.appendChild(el('span', 'agent-badge ' + badge.cls, badge.testo));
        tile.appendChild(delta);
      }
      grid.appendChild(tile);
    });
    box.appendChild(grid);
  }

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
  var HOURS_IN_DAY = 24;

  function renderBalanceCurve(box, form, hasMoments) {
    if (!form) return;
    var series = [];
    if (form.produzione) {
      series.push({ punti: form.produzione, colore: 'var(--bilancio-produzione)', etichetta: DIRECTION_LABEL.produzione });
    }
    if (form.prelievo) {
      series.push({ punti: form.prelievo, colore: 'var(--bilancio-prelievo)', etichetta: DIRECTION_LABEL.prelievo });
    }
    if (!series.length) return;
    var hasPoints = series.some(function (s) { return s.punti && s.punti.length; });
    if (!hasPoints) return;

    var maximum = 0;
    series.forEach(function (s) {
      s.punti.forEach(function (p) { if (p.valore != null && p.valore > maximum) maximum = p.valore; });
    });
    if (maximum <= 0) maximum = 0.000001; // niente divisione per zero: un giorno tutto a zero resta piatto, non rotto

    var L = 640, A = 140, base = A - 20, left = 4;
    var passo = (L - left * 2) / HOURS_IN_DAY;
    var barWidth = Math.max(1, (passo - 2) / series.length);

    var svg = svgEl('svg', {
      class: 'bil-chart', viewBox: '0 0 ' + L + ' ' + A, role: 'img',
      'aria-label': 'Produzione e prelievo, ora per ora'
    });
    var title = document.createElementNS(SVG_NS, 'title');
    title.textContent = 'Produzione e prelievo, ora per ora';
    svg.appendChild(title);
    var descrizione = document.createElementNS(SVG_NS, 'desc');
    // Punto 3 del brief-pagina: la vecchia frase ("gli stessi numeri, con la
    // loro ora vera, sono nei momenti qui sotto") era falsa nel caso
    // generale -- i momenti portano orari e percentuali, non gli stessi
    // kWh della curva -- e orfana quando i momenti mancano. Si dice il
    // vero (un'ora senza barra e' un'ora senza dato), e la frase sui
    // momenti compare SOLO quando i momenti ci sono.
    descrizione.textContent = 'Barre allineate all’ora del giorno: un’ora senza barra è un’ora senza dato, non uno zero.' +
      (hasMoments ? ' Il picco e gli altri momenti notevoli sono qui sotto, con la loro ora vera.' : '');
    svg.appendChild(descrizione);

    series.forEach(function (s, si) {
      s.punti.forEach(function (p) {
        var v = p.valore;
        if (v == null || v <= 0) return;
        // Un solo parsing per punto (punto 4 del brief-dodicesima): il
        // piazzamento (`ora`) e l'etichetta (`formatHourFromDate`) derivano
        // dalla STESSA `Date`, non da due `new Date(p.ora)` separate.
        var d = localDateFromPoint(p.ora);
        if (d == null) return; // mai un'ora inventata: niente ora leggibile, niente barra
        var hour = d.getHours();
        var h = (v / maximum) * (base - 6);
        var x = left + hour * passo + si * barWidth;
        var y = base - h;
        var rect = svgEl('rect', {
          x: x.toFixed(1), y: y.toFixed(1),
          width: barWidth.toFixed(1), height: h.toFixed(1),
          fill: s.colore
        });
        var barTitle = document.createElementNS(SVG_NS, 'title');
        barTitle.textContent = s.etichetta + ' — ' + formatHourFromDate(d) + ': ' + fmtKwh(v);
        rect.appendChild(barTitle);
        svg.appendChild(rect);
      });
    });
    svg.appendChild(svgEl('line', { x1: 0, y1: base, x2: L, y2: base, stroke: 'var(--border)' }));
    box.appendChild(svg);

    var legend = el('div', 'bil-legend');
    series.forEach(function (s) {
      var entry = el('span', 'ulg');
      var dot = el('i');
      dot.style.background = s.colore;
      entry.appendChild(dot);
      entry.appendChild(document.createTextNode(s.etichetta));
      legend.appendChild(entry);
    });
    box.appendChild(legend);
  }

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
  function vociMomenti(moments) {
    var voci = [];
    if (!moments) return voci;
    if (moments.prima_ora_produzione) {
      voci.push(['Prima ora di produzione', fmtIsoHour(moments.prima_ora_produzione)]);
    }
    if (moments.ultima_ora_produzione) {
      voci.push(['Ultima ora di produzione', fmtIsoHour(moments.ultima_ora_produzione)]);
    }
    if (moments.picco_produzione) {
      voci.push(['Picco di produzione',
        fmtKwh(moments.picco_produzione.valore) + ' alle ' + fmtIsoHour(moments.picco_produzione.ora)]);
    }
    if (moments.fine_scarica_batteria) {
      voci.push(['Fine scarica della batteria', fmtIsoHour(moments.fine_scarica_batteria)]);
    }
    if (moments.quota_autoconsumo != null) {
      voci.push(['Quota di autoconsumo', fmtPercent(moments.quota_autoconsumo)]);
    }
    if (moments.quota_autosufficienza != null) {
      voci.push(['Quota di autosufficienza', fmtPercent(moments.quota_autosufficienza)]);
    }
    return voci;
  }

  function renderBalanceMoments(box, moments) {
    var voci = vociMomenti(moments);
    if (!voci.length) return;

    var dl = el('dl', 'bil-moments');
    voci.forEach(function (v) {
      // Punto 2 del brief-pagina (MEDIO): dt e dd erano celle INDIPENDENTI
      // della griglia -- a 1200px `auto-fit` puo' calcolare un numero
      // DISPARI di colonne, e con dt/dd alternati piatti una coppia si
      // spezza a fine riga (misurato dal revisore: «Picco di produzione»
      // chiudeva una riga, il suo valore ne apriva un'altra accanto a
      // «Fine scarica della batteria»). Un `<div>` che raggruppa dt+dd e'
      // contenuto valido dentro un `<dl>` (HTML5: i gruppi nome/valore
      // possono stare avvolti in un div) e diventa l'UNICO elemento di
      // griglia per quella coppia -- una coppia non puo' piu' spezzarsi, a
      // nessuna larghezza (verificato dal vivo a 1200px con Playwright,
      // vedi il rapporto). `.bil-moment` in hiris-config.css.
      var pair = el('div', 'bil-moment');
      pair.appendChild(el('dt', null, v[0]));
      pair.appendChild(el('dd', null, v[1]));
      dl.appendChild(pair);
    });
    box.appendChild(dl);
  }

  /* Le entita' che compongono il bilancio (trasparenza, spec §7): STESSO
     rivelatore sincrono di `detailsDisclosure`, riusato via `createDisclosure`
     -- non un secondo componente. */
  function balanceEntityDisclosure(entity) {
    if (!entity || !entity.length) return null;
    return createDisclosure('Quali sensori', 'Nascondi quali sensori', function (panel) {
      line(panel, entity.join(', '), 'font-size:var(--fs-12);' + TONE_CALM);
    });
  }

  /* Il bilancio NON passa da `period()`/`mainPhrase()`: quelle due
     funzioni presuppongono la forma dell'episodio (un `inizio_ts`/`fine_ts`
     che apre e chiude una cosa accaduta, un `corpo.stato`), e il bilancio non
     ce l'ha -- e' il punto per cui questa fetta esiste (vedi il commento di
     testa del file). `inizio_ts`/`fine_ts` restano i confini del GIORNO
     (sempre chiuso, mai `fine_ts: None`: `aggregate_day`), non l'apertura e
     la chiusura di un evento: mostrarli con la freccia di `period()`
     rifarebbe esattamente lo stampo sbagliato che il mandato vieta. */
  function balanceLine(o) {
    var c = o.corpo || {};
    var box = el('div');
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-3) 0;' +
      'display:flex;flex-direction:column;gap:8px';

    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
    head.appendChild(el('span', 'agent-badge badge-off', GENRE_LABEL.bilancio));
    head.appendChild(el('span', 'text-mono field-hint', o.protagonista || ''));
    box.appendChild(head);

    // Il nome leggibile del dispositivo (`corpo.dispositivo`) e' il
    // CONTENUTO, non l'identificatore tecnico (`protagonista`, il
    // `dispositivo_id` opaco di HA, gia' nel monospazio sopra) -- stessa
    // gerarchia contenuto/riferimento del rilievo 7 (vedi `factLine`).
    var title = el('p', null, c.dispositivo || protagonistName(o));
    title.style.cssText = 'font-size:var(--fs-15);font-weight:600;margin:0;overflow-wrap:anywhere';
    box.appendChild(title);

    rendiTotaliBilancio(box, c.totali);
    // `vociMomenti(c.momenti).length` (non `!!c.momenti`): la frase
    // accessibile della curva deve sapere se la sezione dei momenti
    // renderà davvero qualcosa, non solo se il campo esiste (punto 4 del
    // brief-dodicesima, vedi il commento sopra `vociMomenti`).
    renderBalanceCurve(box, c.forma, vociMomenti(c.momenti).length > 0);
    renderBalanceMoments(box, c.momenti);

    // Difensivo: l'invariante di scrittura garantisce sempre almeno un
    // totale (`aggregate_day`: "un bilancio senza nemmeno un totale ...
    // NON si scrive"), ma un payload malformato non deve tornare a
    // "(nessun dettaglio)" -- lo stesso buco che questa fetta chiude.
    if (!c.totali && !c.forma && !c.momenti) {
      line(box, '(nessun dato per questo bilancio)', TONE_CALM);
    }

    var entityDisclosure = balanceEntityDisclosure(c.entita);
    if (entityDisclosure) box.appendChild(entityDisclosure);

    return box;
  }

  /* Rilievo 7 della review: la gerarchia era rovesciata -- l'identificatore
     era il testo piu' in evidenza, il fatto («25/08 15:30 → 17:05 · da 18,2
     a 21,0») stava nella classe delle note a margine. L'occhio cerca il
     contrario: il COSA E' SUCCESSO e' il contenuto, l'identificatore e' il
     riferimento -- stessa gerarchia gia' in tree-route.js, il metro. */
  function factLine(o) {
    // Il bilancio e' un genere a parte, con una forma diversa dall'episodio
    // (vedi il commento di testa del file): esce subito verso `balanceLine`,
    // che NON riusa `period()`/`mainPhrase()` -- quelle presuppongono
    // un "da → a" che il bilancio non ha.
    if (o.genere === 'bilancio') return balanceLine(o);

    var c = o.corpo || {};
    var box = el('div');
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-3) 0;' +
      'display:flex;flex-direction:column;gap:4px';

    var head = el('div');
    head.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
    head.appendChild(el('span', 'agent-badge badge-off', GENRE_LABEL[o.genere] || o.genere));
    // La provenienza della direzione (mandato, punto 4): un secondo badge,
    // SOLO quando `corpo.direzione` c'e' -- niente badge per un episodio di
    // energia la cui direzione non si conosce, che e' l'esito onesto, non
    // un guasto della resa.
    if (o.genere === 'energia' && o.corpo && o.corpo.direzione) {
      var directionBadge = provenanceDirectionBadge(o.corpo.provenienza);
      head.appendChild(el('span', 'agent-badge ' + directionBadge.cls, directionBadge.testo));
    }
    // Identificatore: monospaziato, piccolo, attenuato -- il riferimento, non
    // il contenuto. `.text-mono`/`.field-hint` portano gia' `overflow-wrap:
    // anywhere` (hiris-config.css) e lo span e' protetto da `.section-card
    // span { min-width: 0 }` (hiris-config.css, rilievo 1): senza, un
    // identificatore da 93 caratteri dentro questa riga flessibile
    // sfonderebbe lo schermo di un telefono.
    // Fetta «il nome» (07/09/2026): `describeWatchedSubject` e' il posto
    // unico che decide se cio' che segue e' un nome o un identificatore --
    // `protagonistName` sa gia' rendere un titolo di guasto e i quattro
    // prefissi tecnici, ma non sa DIRE quando quello che restituisce e' un
    // `entity_id` nudo. Le righe scritte prima della colonna
    // `friendly_name` cadono qui, ed e' voluto (`mind/store.py::
    // _migration_5`): non si riempiono a posteriori dall'anagrafe di oggi.
    var d = describeWatchedSubject(o.protagonista || '', c.nome);
    if (d.technical) head.appendChild(el('span', 'field-hint', SUBJECT_IS_ID));
    head.appendChild(el('span', 'text-mono field-hint', protagonistName(o)));
    box.appendChild(head);

    // Il nome amichevole e' il CONTENUTO, l'identificatore il riferimento
    // (gia' nel monospazio attenuato sopra) -- stessa gerarchia di
    // `balanceLine` con `corpo.dispositivo`, e stesso stile. Non quando
    // c'e' un `titolo`: li' `protagonistName` ha gia' scritto il nome
    // leggibile, e ripeterlo sarebbe la stessa cosa due volte.
    if (c.nome && !c.titolo) {
      var nameLine = el('p', null, c.nome);
      nameLine.style.cssText = 'font-size:var(--fs-15);font-weight:600;margin:0;overflow-wrap:anywhere';
      box.appendChild(nameLine);
    }

    var content = el('p', null, period(o) + ' · ' + mainPhrase(o));
    content.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:0;overflow-wrap:anywhere';
    box.appendChild(content);

    var details = detailsDisclosure(o);
    if (details) box.appendChild(details);

    return box;
  }

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
  function translationsNote(body, translations) {
    var t = translations || {};
    if (t.lette === false) {
      line(body, 'Gli stati qui sotto sono quelli grezzi di Home Assistant: le sue traduzioni ' +
        'non si sono potute leggere' + (t.motivo ? ' (' + t.motivo + ')' : '') + '.', TONE_CALM);
      return;
    }
    /* Nessun `t.lette === true` qui: il ramo di sopra e' gia' uscito per il
       guasto, e ripeterlo sarebbe una condizione che nessuna mutazione puo'
       vedere rossa (provata: toglierla lascia tutto verde). */
    if (t.lingua && t.lingua !== 'it') {
      line(body, 'Gli stati qui sotto sono resi nella lingua della casa (' + t.lingua +
        '), quella scelta in Home Assistant; il resto della pagina è in italiano.', TONE_CALM);
    }
  }

  function renderFacts(body, fact, dayFilter, translations) {
    if (!fact.length) {
      if (!dayFilter) {
        line(body, 'Non c’è ancora nessun episodio: l’aggregazione notturna gira una volta al giorno, alle 00:20.',
          TONE_CALM);
        return;
      }
      /* Rilievo 5: il giorno dell'aggiornamento (e ogni "ieri"/"oggi") e' lo
         STATO NORMALE, non un caso limite -- il messaggio deve dire QUANDO
         tornare, non seminare il dubbio che la casa non abbia fatto niente
         (con ~14.600 cambi al giorno misurati, quasi impossibile). Per un
         giorno piu' vecchio l'ipotesi doppia attuale resta corretta. */
      var dataItaliana = ggMmAaaa(dayFilter);
      var text = (dayFilter === localToday() || dayFilter === ieriLocale())
        ? 'Nessun episodio per il ' + dataItaliana + '. Non è un errore: gli episodi di ogni giornata ' +
          'vengono scritti la notte successiva, alle 00:20 — nel frattempo guarda «Cosa sto guardando» ' +
          'qui sopra.'
        : 'Nessun episodio per il ' + dataItaliana + '. Non è un errore: quel giorno la casa potrebbe ' +
          'non aver fatto niente di osservabile, oppure l’aggregazione notturna non è ancora passata.';
      line(body, text, TONE_CALM);
      return;
    }
    translationsNote(body, translations);
    fact.forEach(function (o) { body.appendChild(factLine(o)); });
  }

  function renderFactsError(body, status, reload) {
    if (status === 503) {
      line(body,
        'L’archivio degli episodi non è disponibile in questo momento. Non è una lista vuota — è l’archivio stesso ad essere fermo.',
        TONE_PROBLEM);
    } else {
      line(body, 'Non è stato possibile leggere gli episodi. Riprova più tardi.', TONE_PROBLEM);
    }
    retryButton(body, reload);
  }

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
  var factsGeneration = 0;

  function loadFacts(body, day) {
    var myGeneration = ++factsGeneration;
    clearEl(body);
    line(body, 'Caricamento…', TONE_CALM);
    function reload() { return loadFacts(body, day); }
    var path = 'api/mind/facts' + (day ? '?day=' + encodeURIComponent(day) : '');
    return read(path).then(function (occurrence) {
      if (myGeneration !== factsGeneration) return; // superata da un cambio di giorno più recente
      clearEl(body);
      if (!occurrence.ok) { renderFactsError(body, occurrence.status, reload); return; }
      renderFacts(body, occurrence.corpo.facts || [], day, occurrence.corpo.traduzioni);
    }, function () {
      if (myGeneration !== factsGeneration) return;
      clearEl(body);
      renderFactsError(body, null, reload);
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);

    outlet.appendChild(el('h1', 'page-title', 'L’osservatore'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Guarda la casa e ne ricava episodi. Non conclude niente, non parla, non tocca niente — ' +
      'è il materiale su cui domani ragionerà l’analista.'));

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

    /* Sezione 02 costruita a mano (non con `sezione()`): a differenza della
       01, questa porta un blocco di controlli (data + bottone) fra il
       sottotitolo e il corpo, e `sezione()` non lo prevede. */
    var card2 = el('section', 'section-card');
    var head2 = el('div', 'sc-header');
    head2.appendChild(el('span', 'sc-num', '02'));
    head2.appendChild(el('h2', 'sc-title', 'Cosa è successo'));
    card2.appendChild(head2);
    /* Rilievo 12: la vecchia frase dichiarava "un'ora" di differenza fra i
       due fusi -- una cifra non misurata (e' quella FRA I DUE FUSI, non
       fissa: zero a Roma, sei ore da New York). Il caso peggiore e' vicino
       alla mezzanotte, non "un'ora": si dice il vero senza inventare un
       numero. */
    card2.appendChild(el('p', 'sc-desc',
      'Gli episodi che l’aggregazione notturna ha costruito dai cambi grezzi di un giorno — ' +
      'scritti alle 00:20, sul fuso della CASA. Il giorno qui sotto è calcolato sul fuso di ' +
      'questo browser: possono differire di un giorno, vicino alla mezzanotte, se guardi da un altro ' +
      'fuso orario.'));

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

    var recentBtn = el('button', 'btn btn-ghost btn-sm', 'Vedi i più recenti, senza filtro');
    recentBtn.type = 'button';
    controls.appendChild(recentBtn);
    card2.appendChild(controls);

    var factsBody = el('div', 'sc-body');
    card2.appendChild(factsBody);
    outlet.appendChild(card2);

    dayInput.addEventListener('change', function () {
      loadFacts(factsBody, dayInput.value || null);
    });
    recentBtn.addEventListener('click', function () {
      dayInput.value = '';
      loadFacts(factsBody, null);
    });

    loadWatching(watchingBody);
    loadFacts(factsBody, dayInput.value);
  }

  return {
    mount: mount,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiScope: renderScope,
    _rendiOggetti: renderFacts
  };
})();
