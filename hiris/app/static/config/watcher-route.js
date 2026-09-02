/* HIRIS · Configurazione · «L'osservatore» (route #/osservatore)

   La prima fetta del cervello nuovo (docs/design/2026-08-26-l-osservatore.md).
   Guarda la casa e ne ricava oggetti -- non conclude niente, non parla, non
   tocca niente. Questa pagina e' la sola faccia che ha oggi: due GET,
   `api/mind/watching` e `api/mind/facts?day=...`
   (`hiris/app/api/handlers_cervello.py`).

   -- Trasparenza al posto del permesso (spec §7) --
   L'osservatore non chiede il permesso di guardare qualcosa: si deve poter
   vedere in ogni momento COSA sta guardando e PERCHE'. Ogni voce porta
   `provenienza`: oggi e' sempre `"pavimento"` (derivata da cio' che Home
   Assistant dichiara, mai una lista scritta a mano) e NON si toglie -- la
   terza provenienza, «me l'ha chiesto l'analista», e la seconda, «lo ha
   aggiunto l'obiettivo» (rimovibile), arrivano con le fette successive. Per
   questo qui c'e' solo un'etichetta che dice da dove viene ogni voce, MAI un
   bottone "togli": costruirne uno oggi, quando ogni singola voce e'
   `pavimento`, sarebbe un controllo che non controlla niente -- peggio di
   nessun controllo, perche' sembrerebbe funzionare.

   -- Due sezioni separate, mai una dentro l'altra (mandato Task 7) --
   «Cosa sto guardando» (l'elenco vivo, `Watcher.osservate()`) e «Cosa e'
   successo» (gli oggetti che l'aggregazione notturna ha scritto,
   `ObservationsStore.oggetti()`) rispondono a due domande diverse -- la
   prima e' lo stato di un cablaggio, la seconda e' la memoria che ne esce --
   e la spec le tiene separate apposta (§7 e' la pagina, §1-6 sono gli
   oggetti).

   -- I sei gambe dell'obiettivo, non un elenco a caso (`pavimento.ASPECTS`) --
   Le voci di «cosa sto guardando» si raggruppano per gamba, nello stesso
   ordine in cui il pavimento le dichiara: chi c'e', comfort, dispersione,
   energia, buono stato, sicurezza. Duplicato qui (non importato: questa SPA
   non porta build step, ogni route e' autonoma come le sue sorelle) --
   stringhe letterali IDENTICHE a `pavimento.ASPECTS`, apostrofo compreso
   («chi c'e'»).

   -- I SEI generi (`cervello/oggetti.py::GENRES`, contati nel sorgente
      Python, non ricopiati -- correzione del giro «la pagina del bilancio»,
      punto 7, 27/08/2026: questa riga diceva "cinque", e da quando
      `bilancio` e' entrato in GENERI sono sei) --
   Cinque sono EPISODIO: funzionamento, presenza, energia, guasto, sicurezza.
   Ogni genere di episodio porta un
   `corpo` di forma diversa (`aggregate_day`): funzionamento/presenza/
   sicurezza/guasto portano `stato` (il valore che ha aperto l'episodio);
   energia porta `valore_iniziale`/`valore_finale`/`differenza` -- una
   VARIAZIONE fra due letture, mai presentata come un consumo da sola: il
   genere copre anche l'energia PRODOTTA da un impianto fotovoltaico.
   **Dal 27/08/2026 (mandato «le direzioni dell'energia») un episodio di
   energia porta anche `direzione`/`provenienza`, QUANDO si conoscono**
   (`HAClient.energy_directions`, `energy/get_prefs` + `translation_key`):
   il campo manca del tutto se non si conosce, mai una "sconosciuta"
   travestita da dato -- `mainPhrase`/`provenanceDirectionBadge` sotto
   lo mostrano solo quando c'e'. La gamba resta "energia" (vedi
   `cervello/pavimento.py::_ENERGIA`): la direzione vive nell'EPISODIO, non
   e' una gamba nuova. Tutti e
   cinque portano `comprimari` (chi altro c'era, dal caso del lampadario) e
   `misure` (cosa hanno fatto le grandezze collegate mentre l'episodio
   durava) -- mostrati dietro un rivelatore SINCRONO (stesso principio di
   constructions-route.js §3: sono gia' nel payload, nasconderli dietro un
   fetch sarebbe la trappola che la guida delle Promesse vieta).

   -- Il SESTO genere, `bilancio`, e' un'ALTRA FORMA (mandato «il bilancio
      dell'energia», 27/08/2026 -- docs/design/2026-08-27-il-bilancio-dell-
      energia.md §3, .superpowers/sdd/2026-08-27-il-bilancio/brief-pagina.md) --
   un bilancio non e' una cosa accaduta fra due istanti, e' una QUANTITA' CON
   UNA FORMA, un giorno intero: renderlo con lo stampo dell'episodio («da X a
   Y», la freccia di `period()`) rifarebbe in pagina esattamente l'errore
   che il giro dei dati ha appena tolto dall'archivio (undici frammenti di
   energia per lo stesso dispositivo). Il suo `corpo` (`costruisci_corpo_
   bilancio` in cervello/oggetti.py) non ha ne' `stato` ne' `valore_iniziale`/
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
   `build_balance_body`, cervello/oggetti.py), `momenti` (fatti
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
window.HirisOsservatoreRoute = (function () {
  'use strict';

  var TONE_PROBLEM = 'color:var(--err-ink)';
  var TONE_CALM = 'color:var(--text-3)';

  /* Letterale, identico a `pavimento.ASPECTS` (vedi il commento di testa): sei
     gambe, quest'ordine. Una gamba che l'archivio manda e questa lista non
     conosce finisce comunque in coda, col suo nome grezzo -- non sparisce
     mai, stessa regola di `NOMI_REGISTRI` in tree-route.js. I VALORI
     restano quelli letterali (identici a `pavimento.ASPECTS`): solo la resa
     (`ASPECT_LABEL` sotto) traduce la chiave in un'etichetta leggibile. */
  var ASPECT_ORDER = ["chi c'e'", 'comfort', 'dispersione', 'energia', 'buono stato', 'sicurezza'];

  /* Rilievo 8a della review: le intestazioni di gamba erano chiavi grezze
     ("chi c'e' — 95 voci", apostrofo ASCII e minuscola) in una pagina con
     tipografia curata altrove. Stessa idea di `GENRE_LABEL` qui sotto:
     una mappa di sole ETICHETTE, la chiave (`ASPECT_ORDER`, il payload)
     resta quella che il pavimento dichiara. Una gamba non in questa mappa
     (coda di `groupByAspect`) mostra comunque il suo nome grezzo, mai
     "undefined". */
  var ASPECT_LABEL = {
    "chi c'e'": 'Chi c’è', comfort: 'Comfort', dispersione: 'Dispersione',
    energia: 'Energia', 'buono stato': 'Buono stato', sicurezza: 'Sicurezza'
  };

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
     mai "undefined" -- stessa regola di `ASPECT_LABEL`/`GENRE_LABEL`. */
  var DIRECTION_LABEL = {
    produzione: 'Produzione', prelievo: 'Prelievo dalla rete',
    immissione: 'Immissione in rete', carica: 'Carica della batteria',
    scarica: 'Scarica della batteria', consumo: 'Consumo della casa',
    autoconsumo: 'Autoconsumo (prodotto e consumato sul posto)'
  };

  /* Le SETTE dimensioni di un bilancio, in quest'ordine -- letterale,
     identico a `BALANCE_DIRECTIONS` in `cervello/oggetti.py` (contato nel
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

  /* --------------------------------------------------------- «cosa sto guardando» */

  function provenanceBadge(provenance) {
    /* Oggi e' sempre "pavimento": la mappa resta comunque a tre voci (la
       spec ne prevede tre, §7) perche' una voce "obiettivo" o "analista" che
       arrivasse domani non deve leggersi come "pavimento" per un buco qui.
       Rilievo 6b della review: l'etichetta era "Pavimento — non si toglie"
       stampata su tutte le righe (oggi ~88 su 88) -- non distingueva niente,
       e "pavimento" per un utente freddo suona come il pavimento di casa.
       "Di serie" e' la parola nuova; il VALORE interno resta `pavimento`
       (spec, API, codice) -- la spiegazione completa vive ora nella
       descrizione della sezione 01, dove c'e' gia' spazio. */
    if (provenance === 'pavimento') {
      return { cls: 'badge-off', testo: 'Di serie' };
    }
    if (provenance === 'obiettivo') {
      return { cls: 'badge-on', testo: 'Obiettivo — si può togliere' };
    }
    return { cls: 'badge-warn', testo: provenance || 'provenienza sconosciuta' };
  }

  function groupByAspect(voci) {
    var groups = {};
    voci.forEach(function (v) {
      var g = v.gamba || '(senza gamba)';
      (groups[g] = groups[g] || []).push(v);
    });
    var order = ASPECT_ORDER.slice();
    Object.keys(groups).forEach(function (g) {
      if (order.indexOf(g) === -1) order.push(g);
    });
    return order.filter(function (g) { return groups[g]; })
      .map(function (g) { return { gamba: g, voci: groups[g] }; });
  }

  function renderAspectGroup(body, group) {
    var det = el('details');
    det.open = false;
    var label = ASPECT_LABEL[group.gamba] || group.gamba;
    var summary = el('summary', null,
      label + ' — ' + group.voci.length + (group.voci.length === 1 ? ' voce' : ' voci'));
    summary.style.cssText = 'cursor:pointer;font-weight:500';
    det.appendChild(summary);

    var ul = el('ul');
    ul.style.cssText = 'margin:6px 0 4px;padding-left:18px';
    group.voci.forEach(function (v) {
      var li = el('li');
      li.style.cssText = 'margin-bottom:6px;font-size:var(--fs-13);overflow-wrap:anywhere;' +
        'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
      li.appendChild(el('span', 'text-mono', v.soggetto));
      var b = provenanceBadge(v.provenienza);
      li.appendChild(el('span', 'agent-badge ' + b.cls, b.testo));
      ul.appendChild(li);
    });
    det.appendChild(ul);
    body.appendChild(det);
  }

  function renderWatching(body, osservate) {
    if (!osservate.length) {
      line(body,
        'Non sto guardando ancora niente. Se HIRIS è appena partito e' +
        ' Home Assistant non ha ancora mandato nessun cambio, è normale — torna fra poco.',
        TONE_CALM);
      return;
    }
    groupByAspect(osservate).forEach(function (g) { renderAspectGroup(body, g); });
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
       promettere una continuita' che il pavimento non tiene. */
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
      return c.stato === 'aperto' ? 'ancora aperto' : 'stato: ' + (c.stato || '?');
    }
    return c.stato != null ? 'stato: ' + c.stato : '(nessun dettaglio)';
  }

  /* La provenienza della direzione -- non e' la stessa domanda della
     provenienza di «cosa sto guardando» (`provenanceBadge`, sezione 01:
     pavimento/obiettivo). Qui i due valori possibili sono "dichiarata" (la
     dashboard Energia dell'utente, che vince sempre) e "dedotta"
     (`translation_key` dell'integrazione, un arricchimento specifico).
     **Le due provenienze si distinguono visibilmente apposta** (mandato,
     punto 4): il giorno in cui una dedotta sbagliasse, saperlo e' la
     differenza fra un dubbio e una caccia. Stessi due stili di badge gia'
     usati da `provenanceBadge` (`badge-off` per l'autorevole, `badge-warn`
     per l'arricchimento) -- non un componente nuovo. */
  function provenanceDirectionBadge(provenance) {
    if (provenance === 'dichiarata') {
      return { cls: 'badge-off', testo: 'Dichiarata — dalla dashboard Energia' };
    }
    if (provenance === 'dedotta') {
      return { cls: 'badge-warn', testo: 'Dedotta — dall’integrazione' };
    }
    return { cls: 'badge-warn', testo: provenance || 'provenienza sconosciuta' };
  }

  /* `problema:dominio.id` / `integrazione:entry_id` -> un nome leggibile.
     Stessa idea di `nomiRegistriInItaliano` in tree-route.js: un prefisso
     tecnico non deve restare tale e quale sulla pagina. */
  function protagonistName(o) {
    var s = o.protagonista || '';
    if (s.indexOf('problema:') === 0) return 'Problema Home Assistant: ' + s.slice('problema:'.length);
    if (s.indexOf('integrazione:') === 0) return 'Integrazione non caricata: ' + s.slice('integrazione:'.length);
    return s;
  }

  /* Il rivelatore sincrono, estratto (correzione di questo giro): era
     duplicato letterale fra `detailsDisclosure` (comprimari/misure) e il
     rivelatore delle entita' di un bilancio, sotto -- STESSO bottone,
     STESSA logica open/close, STESSA disciplina "chiuso di default, i dati
     sono gia' nel payload" (mandato Task 7). Un secondo copia-incolla qui
     sarebbe il doppione che le fondamenta di questo prodotto vietano.
     `fillPanel(pannello)` scrive il contenuto specifico di ogni
     chiamante dentro il pannello gia' creato, chiuso, con lo stile giusto. */
  function createDisclosure(closedText, openText, fillPanel) {
    var wrap = el('div', 'field-group');
    var btn = el('button', 'btn btn-ghost btn-sm', closedText);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');

    var panel = el('div');
    panel.hidden = true;
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
     -- vedi il docstring di `build_balance_body` in cervello/
     oggetti.py, letto per intero prima di questa correzione): le barre si
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
      class: 'bil-grafico', viewBox: '0 0 ' + L + ' ' + A, role: 'img',
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

    var legend = el('div', 'bil-legenda');
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
     curva, non come frasi.» -- una lista etichetta/valore (`.bil-momenti`,
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

    var dl = el('dl', 'bil-momenti');
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
      // vedi il rapporto). `.bil-momento` in hiris-config.css.
      var pair = el('div', 'bil-momento');
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
    head.appendChild(el('span', 'text-mono field-hint', protagonistName(o)));
    box.appendChild(head);

    var content = el('p', null, period(o) + ' · ' + mainPhrase(o));
    content.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:0;overflow-wrap:anywhere';
    box.appendChild(content);

    var details = detailsDisclosure(o);
    if (details) box.appendChild(details);

    return box;
  }

  function renderFacts(body, fact, dayFilter) {
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
      renderWatching(body, occurrence.corpo.watching || []);
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
      renderFacts(body, occurrence.corpo.facts || [], day);
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

    outlet.appendChild(el('div', 'page-title', 'L’osservatore'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Guarda la casa e ne ricava episodi. Non conclude niente, non parla, non tocca niente — ' +
      'è il materiale su cui domani ragionerà l’analista.'));

    /* Rilievo 6b: la spiegazione di «Di serie» (prima ripetuta identica su
       ogni riga come "Pavimento — non si toglie", ~88 volte) vive qui, dove
       c'e' gia' spazio -- una volta sola, non su ogni voce. */
    var watchingBody = section(outlet, '01', 'Cosa sto guardando',
      'Ogni voce dice da dove viene. Le voci «di serie» sono ciò che HIRIS osserva sempre, comunque, ' +
      'per capire se la casa è confortevole, efficiente e sicura, e non si tolgono; quelle aggiunte ' +
      'dall’obiettivo, quando arriveranno, si potranno togliere.');

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
    dayInput.id = 'osservatore-giorno';
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
    _rendiOsservate: renderWatching,
    _rendiOggetti: renderFacts
  };
})();
