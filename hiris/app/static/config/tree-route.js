/* HIRIS · Configurazione · «Albero della casa» (route #/tree)

   Chiude il reperto 26: `GET /api/home-space` manda gia' l'albero completo che
   `topology.hierarchy()` costruisce -- piani -> aree -> entita'. Dalla Tappa 9
   (F5, 12/10/2026) ogni entita' e' la resa media della chat
   (`render.render_entity`), senza l'area (e' il ramo) e senza gli attributi:
   lo stato, l'integrazione, il `fuori`, le etichette col nome, gli alias, il
   `translation_key` -- ed e' il payload piu' ricco che HIRIS produce. Prima usciva verso nessuno:
   `dashboard.js` (`#/`, «Cosa HIRIS sa») legge la stessa risposta e ne
   mostra solo i CONTEGGI (`casa.conteggi`), mai `casa.piani`. Questa pagina
   e' la faccia di quel campo.

   Non e' una copia della dashboard di Home Assistant: il punto non e'
   "arreda la stanza", e' "mostra cosa HIRIS crede di sapere della stanza",
   cosi' l'utente si accorge quando HIRIS sbaglia.

   Tre distinzioni che la pagina DEVE rendere visibili, perche' sono la
   parte che conta (vedi il docstring di `topology.hierarchy()`, che resta
   la spiegazione migliore che esista):

   1) Le pseudo-aree/pseudo-piani che `hierarchy()` crea per dichiarare i
      SILENZI -- «Senza area», «Area sconosciuta», «Aree non lette»,
      «Dispositivi non letti», «Senza piano», «Piani non letti». Sono SEI
      cause diverse, non varianti di un unico "non si sa": "Senza area" e
      "Senza piano" sono un FATTO confermato (il registro ha risposto, e
      quelle entita' davvero non hanno casa); "Area sconosciuta" e'
      un'INCOERENZA vera (un riferimento che punta a un'area sparita);
      "Aree/Piani/Dispositivi non letti" sono un BUCO di lettura (non si
      puo' sapere). Appiattirle in un'unica frase sarebbe il difetto
      esatto che questa pagina esiste per chiudere -- vedi
      `FLOOR_EXPLANATION`/`AREA_EXPLANATION` sotto, un tono diverso per
      ciascuna delle tre famiglie.
   2) Le entita' DISABILITATE -- `entita_disabilitate`, la chiave
      parallela a `entita` che ogni area vera porta. Presenti e marcate,
      MAI nascoste: un'area con tre luci disabilitate e zero attive non
      deve sembrare un'area vuota. Dalla fetta "nascoste fuori dagli
      elenchi" (2026-08-25) vale la STESSA cosa per `entita_nascoste`: la
      chat non le nomina piu' di sua iniziativa (struttura, non istruzione),
      ma questa pagina esiste apposta per non far sparire niente, e le
      mostra in una sezione propria -- stesso trattamento, stessa ragione.
   3) `non_disponibili` e `sistema_di_riferimento`, con la stessa
      disciplina a tre stati di `dashboard.js`: un `null` non e' un `[]`,
      e una casa letta a meta' non deve sembrare una casa piccola.

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati
   server -- stessa disciplina di dashboard.js/memory-route.js. */
window.HirisTreeRoute = (function () {
  'use strict';

  var TONE_UNKNOWN = 'color:var(--warn-ink)';
  var TONE_PROBLEM = 'color:var(--err-ink)';
  var TONE_CALM = 'color:var(--text-3)';

  /* Gli stessi id letterali che `topology.py` usa per le pseudo-aree e i
     due piani-contenitore (`_ID_*`). Non sono un'API pubblica dichiarata,
     ma sono stringhe stabili: `hierarchy()` le costruisce a mano, non le
     genera, e un test di mutazione su questo file prova che restano
     allineate (vedi tests/js/tree-route.test.mjs). */
  var ID_WITHOUT_AREA = '__senza_area__';
  var ID_AREAS_NOT_LOADED = '__aree_non_lette__';
  var ID_UNKNOWN_AREA = '__area_sconosciuta__';
  var ID_DEVICES_NOT_LOADED = '__dispositivi_non_letti__';
  var ID_WITHOUT_FLOOR = '__senza_piano__';
  var ID_FLOORS_NOT_LOADED = '__piani_non_letti__';
  var ID_OUTSIDE_AREAS = '__fuori_dalle_aree__';

  var FLOOR_EXPLANATION = {};
  FLOOR_EXPLANATION[ID_WITHOUT_FLOOR] = {
    testo: 'Aree vere di Home Assistant, che l’utente non ha assegnato a nessun piano.',
    tono: TONE_CALM
  };
  FLOOR_EXPLANATION[ID_FLOORS_NOT_LOADED] = {
    testo: 'Il registro dei piani non ha risposto: queste aree potrebbero avere un piano che ' +
      'HIRIS non ha potuto leggere — non è detto che non ne abbiano uno.',
    tono: TONE_UNKNOWN
  };
  FLOOR_EXPLANATION[ID_OUTSIDE_AREAS] = {
    testo: 'Entità che non stanno in nessuna area nota, per quattro ragioni diverse — una per ' +
      'ciascun gruppo qui sotto.',
    tono: TONE_UNKNOWN
  };

  var AREA_EXPLANATION = {};
  AREA_EXPLANATION[ID_WITHOUT_AREA] = {
    testo: 'Il registro delle aree ha risposto: queste entità davvero non sono assegnate a ' +
      'nessuna stanza.',
    tono: TONE_CALM
  };
  AREA_EXPLANATION[ID_AREAS_NOT_LOADED] = {
    testo: 'Il registro delle aree non ha risposto: non si può sapere se queste entità abbiano ' +
      'un’area o no.',
    tono: TONE_UNKNOWN
  };
  AREA_EXPLANATION[ID_UNKNOWN_AREA] = {
    testo: 'Queste entità puntano a un’area che non esiste più nel registro — un riferimento ' +
      'rotto, non un’assenza.',
    tono: TONE_PROBLEM
  };
  AREA_EXPLANATION[ID_DEVICES_NOT_LOADED] = {
    testo: 'Il registro dei dispositivi non ha risposto: queste entità erediterebbero l’area ' +
      'dal proprio dispositivo, ma HIRIS non ha potuto leggere quale.',
    tono: TONE_UNKNOWN
  };

  /* Le unità del sistema di riferimento, coi NOMI che manda il server
     (`casa.nomi_misure`, `GET /api/home-space`): e' la tabella del nucleo,
     `briefing._MEASUREMENT_NAMES`, e il suo ordine e' quello in cui la casa
     si legge -- cosi' la stessa casa si legge uguale sul nucleo del modello e
     su questa pagina, e la pagina non ne tiene una copia (C-09). Una chiave
     che HA manda e che la mappa non conosce ancora NON sparisce: compare
     col suo nome grezzo, stessa regola di `NOMI_REGISTRI` (common.js) e
     delle "chiavi sconosciute" di dashboard.js. */
  function homeMeasurements(unit, names) {
    if (!unit) return [];
    names = names || {};
    var chiavi = Object.keys(names);
    Object.keys(unit).forEach(function (k) { if (chiavi.indexOf(k) === -1) chiavi.push(k); });
    return chiavi
      .filter(function (k) { return unit[k]; })
      .map(function (k) { return (names[k] || k) + ' ' + unit[k]; });
  }

  /* Il segno di un'entita' fuori dai visibili (`fuori.classe`, la regola di
     `topology.visibility_classes`), con le parole che questa pagina usava
     gia' (scelta del proprietario, 12/10/2026: «Parole di oggi», nessun
     termine nuovo). Una classe che la mappa non conosce compare col suo
     nome, non sparisce. */
  var OUTSIDE_MARK = {
    disabilitata: '[disabilitata]',
    nascosta: '[nascosta in Home Assistant]',
    servizio: '[di servizio]'
  };

  /* Quante voci di un elenco si nominano prima di «e altre N». */
  var NAMED_AT_MOST = 10;

  function line(parent, text, style) {
    var p = el('p', 'sc-desc', text);
    if (style) p.style.cssText = style;
    parent.appendChild(p);
    return p;
  }

  function list(parent, voci) {
    var ul = el('ul');
    ul.style.cssText = 'margin:4px 0 0;padding-left:20px;color:var(--text-2);font-size:var(--fs-13)';
    voci.forEach(function (v) { ul.appendChild(el('li', null, v)); });
    parent.appendChild(ul);
    return ul;
  }

  function section(outlet, title, subtitle) {
    var card = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('h2', 'sc-title', title));
    if (subtitle) head.appendChild(el('div', 'sc-desc', subtitle));
    card.appendChild(head);
    var body = el('div', 'sc-body');
    card.appendChild(body);
    outlet.appendChild(card);
    return body;
  }

  /* --------------------------------------------------------- sistema di riferimento */

  function renderSystem(body, system, measurementNames) {
    var title = el('div', null, 'Sistema di riferimento');
    title.style.cssText = 'font-weight:500;margin-top:14px';
    body.appendChild(title);

    if (!system || !Object.keys(system).length) {
      line(body, 'Non letto: fuso, unità, valuta e lingua della casa non sono disponibili.', TONE_UNKNOWN);
      return;
    }

    var identity = [];
    if (system.nome) identity.push('casa «' + system.nome + '»');
    if (system.fuso) identity.push('fuso ' + system.fuso);
    if (system.lingua) identity.push('lingua ' + system.lingua);
    if (system.valuta) identity.push('valuta ' + system.valuta);
    if (system.paese) identity.push('paese ' + system.paese);
    if (system.versione_ha) identity.push('Home Assistant ' + system.versione_ha);
    line(body, identity.length ? identity.join(', ') + '.' : 'Nessun dettaglio d’identità dichiarato.', TONE_CALM);

    var measurements = homeMeasurements(system.sistema_unita, measurementNames);
    if (measurements.length) {
      line(body, 'Unità con cui ragiona la casa: ' + measurements.join(', ') +
        ' (ogni entità porta la propria: se manca, manca — non è questa).', TONE_CALM);
    }
  }

  /* --------------------------------------------------------------------- entità */

  /* Lo stato da scrivere accanto al nome: le parole di Home Assistant
     (`stato_leggibile`) quando ci sono, altrimenti il valore grezzo con la
     sua unita'. Le parole di `unavailable`/`unknown` non arrivano dal comando
     che HIRIS legge (`frontend/get_translations`, vedi
     `proxy/state_translations.state_translation`): Home Assistant le tiene
     nel pacchetto di traduzioni del suo frontend (misurato dallo Sprint
     l'11/10/2026). Restano grezze, come nella chat. Senza stato non si
     scrive niente. */
  function stateText(e) {
    if (e.stato_leggibile) return e.stato_leggibile;
    if (e.stato == null) return '';
    return e.unita ? e.stato + ' ' + e.unita : String(e.stato);
  }

  function entityLine(ul, e) {
    var li = el('li');
    /* `overflow-wrap:anywhere` anche qui (non solo sull'id): alias ed
       etichette sono a loro volta slug senza spazi, stesso rischio di
       sfondare la larghezza. */
    li.style.cssText = 'margin-bottom:8px;font-size:var(--fs-13);overflow-wrap:anywhere';

    var head = el('span', null, (e.nome || e.id || '?') + ' ');
    head.style.fontWeight = '500';
    li.appendChild(head);

    var state = stateText(e);
    if (state) {
      var st = el('span', null, '· ' + state + ' ');
      st.style.cssText = 'font-size:var(--fs-13);color:var(--text-2)';
      li.appendChild(st);
    }

    if (e.id) {
      /* C2 (audit 2026-08-24): gli entity_id lunghi (es.
         "binary_sensor.presence_sensor_fp2_2763_presence_sensor_1") sono
         una parola sola, senza spazi -- senza `overflow-wrap` il browser non
         ha un punto dove andare a capo e allarga tutta la pagina in
         orizzontale (misurato: scrollWidth 669px su un viewport di 390).
         Va a capo, non troncato: e' proprio l'id per intero che questa
         pagina serve a far leggere. */
      var idSpan = el('span', null, '(' + e.id + ')');
      idSpan.style.cssText = 'color:var(--text-3);font-size:var(--fs-12);overflow-wrap:anywhere';
      li.appendChild(idSpan);
    }

    /* Il segno del `fuori`: una classe sola, la prima per precedenza
       (disabilitata > nascosta > di servizio), come la legge la chat. */
    var outside = e.fuori && e.fuori.classe;
    if (outside) {
      var mark = el('span', null, ' ' + (OUTSIDE_MARK[outside] || '[' + outside + ']'));
      mark.style.cssText = TONE_UNKNOWN + ';font-size:var(--fs-12)';
      li.appendChild(mark);
    }

    /* `translation_key` su una riga SUA, e non dentro la riga a «·» qui
       sotto. Quella riga raccoglie fatti di CLASSIFICAZIONE -- integrazione,
       categoria, classe, unita': vocabolari chiusi, valori di poche lettere,
       che dicono COME l'entita' e' cablata. Questo e' un fatto di genere
       diverso: e' l'AUTODICHIARAZIONE dell'integrazione, cosa l'entita' E'.
       Impastarli sarebbe due cose diverse col medesimo trattamento visivo --
       e ci sono due tell pratici: fino a 37 caratteri misurati contro i 5-8
       degli altri (spezzerebbe il ritmo della riga), ed e' l'unico valore che
       varia vistosamente in lunghezza da un'entita' all'altra.

       Sta SOTTO l'id e SOPRA alias/etichette: lo dichiara il fornitore (Home
       Assistant), con lo stesso peso d'autorita' dell'id -- gli alias e le
       etichette invece li scrive il proprietario.

       Monospazio come l'id, e per la stessa ragione: dice con la forma, non
       con una spiegazione, che e' un nome tecnico e non un giudizio.

       **Nome non tradotto**: e' un identificatore nativo di Home Assistant, e
       il suo VALORE resta inglese comunque (`energy_generating_today`).
       Vestirlo di italiano lo farebbe sembrare contenuto leggibile.

       E dove non c'e', **non si scrive niente**: su questa casa manca su 331
       entita' su 1.229, e un «translation_key: —» ripetuto trecento volte
       coprirebbe le 898 che dicono qualcosa. E' la legge che questa pagina
       gia' applica ad alias ed etichette. */
    if (e.translation_key) {
      var tk = el('div', null, 'translation_key ' + e.translation_key);
      tk.style.cssText = 'font-size:var(--fs-12);color:var(--text-3);'
        + 'font-family:var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace);'
        + 'overflow-wrap:anywhere';
      li.appendChild(tk);
    }

    var details = [];
    if (e.integrazione && e.integrazione.nome) details.push('integrazione ' + e.integrazione.nome);
    /* La categoria di Home Assistant (`entity_category`) e' la causa del
       `fuori` di servizio: un fatto solo, letto li'. */
    if (outside === 'servizio' && e.fuori.causa) details.push('categoria ' + e.fuori.causa);
    if (e.classe) details.push('classe ' + e.classe);
    /* L'unita' accanto allo stato grezzo non si ripete qui. */
    if (e.unita && !(state && !e.stato_leggibile)) details.push('unità ' + e.unita);
    if (details.length) {
      var dl = el('div', null, details.join(' · '));
      dl.style.cssText = 'font-size:var(--fs-12);color:var(--text-2)';
      li.appendChild(dl);
    }

    if (e.alias && e.alias.length) {
      var a = el('div', null, 'alias: ' + e.alias.join(', '));
      a.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
      li.appendChild(a);
    }
    /* Le etichette arrivano col nome, nella forma della chat (`Nome (id:
       X)`, `topology.labels_with_id`): la pagina non le traduce piu'. */
    if (e.etichette && e.etichette.length) {
      var et = el('div', null, 'etichette: ' + e.etichette.join(', '));
      et.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
      li.appendChild(et);
    }

    ul.appendChild(li);
  }

  /* ------------------------------------------------------------------------ aree */

  function entityCountLabel(area) {
    var active = (area.entita || []).length;
    var disabled = (area.entita_disabilitate || []).length;
    var hidden = (area.entita_nascoste || []).length;
    var base = active + ' entità';
    /* Collaudo 3.22 (A9): era `' disabilitata'.concat(disabled === 1 ? '' :
       'e')`, che AGGIUNGE la "e" invece di SOSTITUIRE la "a" -- "9
       disabilitatae", non "9 disabilitate". Il ternario intero, come fa gia'
       il titolo di sezione qui sotto ("Entità disabilitate (32)"). */
    if (disabled) base += ', ' + disabled + (disabled === 1 ? ' disabilitata' : ' disabilitate');
    /* Stessa disciplina delle disabilitate (fetta "nascoste fuori dagli
       elenchi", 2026-08-25): questa pagina esiste per non far sparire
       niente -- un'area con quattro luci nascoste e tre attive deve
       leggersi come "3 entità, 4 nascoste", non come "3 entità" secco. */
    if (hidden) base += ', ' + hidden + (hidden === 1 ? ' nascosta' : ' nascoste');
    /* Le entita' di servizio stanno fra quelle contate (`hierarchy()` non le
       separa): si dice quante sono, con la parola del loro segno. */
    var service = (area.entita || []).filter(function (e) {
      return e && e.fuori && e.fuori.classe === 'servizio';
    }).length;
    if (service) base += ', ' + service + ' di servizio';
    return base;
  }

  function renderArea(container, area) {
    var det = el('details');
    /* C2 (audit 2026-08-24): con `open` sempre vero, una casa di 1224
       entità rendeva 49.282px di pagina su desktop e 70.154px su mobile --
       ogni singola entità nasceva gia' espansa. Le AREE nascono chiuse
       (un riepilogo per riga, "Cucina — 3 entità"); i PIANI (rendiPiano,
       sotto) restano aperti: e' il primo livello, la mappa della casa. Chi
       cerca un dispositivo apre l'area che gli interessa -- resta possibile
       aprire il resto, non e' un limite, solo non nasce gia' tutto steso. */
    det.open = false;

    var summary = el('summary', null, area.nome + ' — ' + entityCountLabel(area));
    summary.style.cssText = 'cursor:pointer;font-weight:500';
    det.appendChild(summary);

    var body = el('div');
    body.style.cssText = 'padding:6px 0 10px 18px;border-left:2px solid var(--border);margin-left:4px';

    var explanation = AREA_EXPLANATION[area.id];
    if (explanation) line(body, explanation.testo, explanation.tono + ';font-size:var(--fs-13)');

    if (area.entita_temperatura) {
      line(body, 'Temperatura di quest’area: ' + area.entita_temperatura, 'font-size:var(--fs-12);color:var(--text-3)');
    }
    if (area.entita_umidita) {
      line(body, 'Umidità di quest’area: ' + area.entita_umidita, 'font-size:var(--fs-12);color:var(--text-3)');
    }

    var active = area.entita || [];
    var disabled = area.entita_disabilitate || [];
    /* `entita_nascoste` (fetta "nascoste fuori dagli elenchi", 2026-08-25):
       da quando `hierarchy()` le toglie da `entita` per STRUTTURA (la stessa
       ragione per cui la chat non le nomina piu' di sua iniziativa), questa
       pagina -- che esiste apposta per non far sparire niente -- le rende in
       una sezione propria, come gia' faceva per le disabilitate. */
    var hidden = area.entita_nascoste || [];

    if (!active.length && !disabled.length && !hidden.length) {
      line(body, 'Nessuna entità.', TONE_CALM);
    }
    if (active.length) {
      var ul = el('ul');
      ul.style.cssText = 'margin:4px 0;padding-left:18px';
      active.forEach(function (e) { entityLine(ul, e); });
      body.appendChild(ul);
    }
    if (disabled.length) {
      /* Presenti e marcate, MAI nascoste: questo titolo compare SEMPRE che
         ce ne sia almeno una, anche se `attive` è vuoto -- un'area con tre
         luci disabilitate e zero attive non deve leggersi come vuota. */
      var disabledTitle = el('div', null,
        disabled.length === 1 ? 'Entità disabilitata' : 'Entità disabilitate (' + disabled.length + ')');
      disabledTitle.style.cssText = 'font-weight:500;margin-top:8px;font-size:var(--fs-13)';
      body.appendChild(disabledTitle);
      var ulD = el('ul');
      ulD.style.cssText = 'margin:4px 0;padding-left:18px';
      disabled.forEach(function (e) { entityLine(ulD, e); });
      body.appendChild(ulD);
    }
    if (hidden.length) {
      /* Stessa disciplina delle disabilitate qui sopra, per lo stesso
         motivo: "questa luce c'è ma l'hai nascosta" è informazione, non
         un'assenza -- questa pagina audita cosa HIRIS sa, non filtra cosa
         mostrare come farebbe una risposta in chat. */
      var hiddenTitle = el('div', null,
        hidden.length === 1 ? 'Entità nascosta' : 'Entità nascoste (' + hidden.length + ')');
      hiddenTitle.style.cssText = 'font-weight:500;margin-top:8px;font-size:var(--fs-13)';
      body.appendChild(hiddenTitle);
      var ulN = el('ul');
      ulN.style.cssText = 'margin:4px 0;padding-left:18px';
      hidden.forEach(function (e) { entityLine(ulN, e); });
      body.appendChild(ulN);
    }

    det.appendChild(body);
    container.appendChild(det);
  }

  /* ----------------------------------------------------------------------- piani */

  function areaCountLabel(floor) {
    var n = (floor.aree || []).length;
    var word = floor.id === ID_OUTSIDE_AREAS ? (n === 1 ? 'gruppo' : 'gruppi') : (n === 1 ? 'area' : 'aree');
    return n + ' ' + word;
  }

  function renderFloor(container, floor) {
    var det = el('details');
    /* Primo livello: resta aperto (vedi il commento in rendiArea per il
       perche' le aree, sotto, non lo sono piu'). */
    det.open = true;

    var floorTitle = floor.nome + (floor.livello != null ? ' (livello ' + floor.livello + ')' : '');
    var summary = el('summary', null, floorTitle + ' — ' + areaCountLabel(floor));
    summary.style.cssText = 'cursor:pointer;font-weight:600;font-size:var(--fs-15)';
    det.appendChild(summary);

    var body = el('div');
    body.style.cssText = 'padding:8px 0 12px 12px';

    var explanation = FLOOR_EXPLANATION[floor.id];
    if (explanation) line(body, explanation.testo, explanation.tono + ';font-size:var(--fs-13)');

    (floor.aree || []).forEach(function (area) { renderArea(body, area); });

    det.appendChild(body);
    container.appendChild(det);
  }

  /* ------------------------------------------------- registri e confronto */

  /* Per ogni registro che non ha risposto, la copia che l'anagrafe tiene al
     suo posto e di quando e' (`non_disponibili_letti_il`, S-36): `null` se
     quel registro non ha mai risposto. Senza la mappa, i soli nomi. */
  function unavailableWithCopy(unavailable, since) {
    var names = nomiRegistriInItaliano(unavailable);
    if (!since) return names;
    return unavailable.map(function (entry, i) {
      var at = since[entry];
      return names[i] + ' — ' + (at
        ? 'HIRIS usa la copia del ' + fmtDateTime(at) + '.'
        : 'nessuna copia disponibile, mai letto.');
    });
  }

  function hasServiceEntities(floors) {
    return floors.some(function (floor) {
      return (floor.aree || []).some(function (area) {
        return Object.keys(area).some(function (key) {
          return Array.isArray(area[key]) && area[key].some(function (e) {
            return e && e.fuori && e.fuori.classe === 'servizio';
          });
        });
      });
    });
  }

  /* I nomi delle entita' dell'albero, per dire le divergenze per nome: ogni
     elenco di un'area (le attive, le nascoste, le disabilitate), senza
     ricopiare qui quali sono. */
  function entityNames(floors) {
    var names = {};
    floors.forEach(function (floor) {
      (floor.aree || []).forEach(function (area) {
        Object.keys(area).forEach(function (key) {
          if (!Array.isArray(area[key])) return;
          area[key].forEach(function (e) { if (e && e.id) names[e.id] = e.nome || e.id; });
        });
      });
    });
    return names;
  }

  function namedList(ids, names) {
    var shown = ids.slice(0, NAMED_AT_MOST).map(function (id) { return names[id] || id; });
    var rest = ids.length - shown.length;
    return shown.join(', ') + (rest > 0 ? ' e altre ' + rest : '');
  }

  /* L'esito dell'ultimo confronto fra l'albero e cio' che Home Assistant
     risponde su un campione di aree (`topology.compare_with_home_assistant`).
     Ogni frase dice quante aree si sono guardate: «combacia» su un campione
     non e' «tutta la casa combacia». */
  function renderComparison(body, comparison, floors) {
    var title = el('div', null, 'Confronto con Home Assistant');
    title.style.cssText = 'font-weight:500;margin-top:14px';
    body.appendChild(title);

    if (comparison == null) {
      line(body, 'Mai confrontato: HIRIS non ha ancora verificato il suo albero contro quello di ' +
        'Home Assistant.', TONE_CALM);
      return;
    }
    if (comparison.errore) {
      line(body, 'Il confronto non si è potuto fare: ' + comparison.errore + '.', TONE_UNKNOWN);
      return;
    }
    var checked = comparison.guardate || [];
    if (!checked.length || !comparison.aree_totali) {
      line(body, 'Il confronto non ha avuto aree da controllare.', TONE_CALM);
      return;
    }
    var when = comparison.letto_il ? 'Confronto del ' + fmtDateTime(comparison.letto_il) : 'Ultimo confronto';
    line(body, when + ': ' + (checked.length === 1 ? 'controllata 1 area' : 'controllate ' + checked.length + ' aree') +
      ' su ' + comparison.aree_totali + '.', TONE_CALM);

    var names = entityNames(floors);
    var failed = checked.filter(function (g) { return g.errore; });
    var differing = checked.filter(function (g) {
      return !g.errore && (g.assente_in_ha || (g.in_piu || []).length || (g.mancanti || []).length);
    });
    if (!failed.length && !differing.length) {
      line(body, 'Tutto combacia: in queste aree l’albero di HIRIS è uguale a quello che Home ' +
        'Assistant risponde.', TONE_CALM);
    }
    if (differing.length) {
      line(body, (differing.length === 1 ? 'In 1 area' : 'In ' + differing.length + ' aree') +
        ' l’albero di HIRIS non combacia con Home Assistant:', TONE_PROBLEM);
      list(body, differing.map(function (g) {
        if (g.assente_in_ha) return g.nome + ' — non esiste più in Home Assistant.';
        var parts = [];
        if ((g.in_piu || []).length) parts.push('HIRIS ha in più: ' + namedList(g.in_piu, names));
        if ((g.mancanti || []).length) parts.push('gli manca: ' + namedList(g.mancanti, names));
        return g.nome + ' — ' + parts.join('; ') + '.';
      }));
    }
    if (failed.length) {
      line(body, 'Aree che non si sono potute controllare:', TONE_UNKNOWN);
      list(body, failed.map(function (g) { return g.nome + ' — ' + g.errore + '.'; }));
    }
  }

  /* --------------------------------------------------------------------- albero */

  function renderTree(outlet, home_space) {
    var body = section(outlet, 'Albero della casa',
      'Piani, aree ed entità come HIRIS li ha ricostruiti — con ogni silenzio dichiarato per nome, ' +
      'non appiattito in un unico «non si sa».');

    /* Regola non negoziabile: una casa non letta non è una casa vuota.
       Niente albero (nemmeno vuoto) su una lettura mai avvenuta -- lo
       stesso principio di dashboard.js applicato qui. */
    if (home_space.anagrafe_letta_il == null) {
      line(body,
        'L’anagrafe non è ancora stata letta: qui non c’è un albero vuoto, c’è una casa che HIRIS non ha ancora guardato.',
        TONE_UNKNOWN);
      return;
    }

    /* Collaudo 3.22 (A10, stessa correzione di dashboard.js::renderHomeSpace):
       ISO grezzo in UTC -> fmtDateTime (common.js), non una seconda
       funzione di formattazione. */
    line(body, 'Letta il ' + fmtDateTime(home_space.anagrafe_letta_il) + '.', TONE_CALM);
    /* Lo stato accanto a ogni entita' e' quello dello specchio quando la
       pagina si e' aperta (Tappa 9, F5): lo specchio segue gli eventi di Home
       Assistant, ma con la connessione caduta resta fermo all'ultimo
       aggiornamento -- e la pagina invecchia mentre la si guarda. */
    line(body, 'Gli stati mostrati sono quelli dell’ultimo aggiornamento, non quelli di adesso.',
      TONE_CALM);
    /* «di servizio» e' un segno, non una parola di Home Assistant: si spiega
       una volta, solo se ce n'e' almeno una. */
    if (hasServiceEntities(home_space.piani || [])) {
      line(body, 'Le entità «di servizio» sono quelle che Home Assistant tiene per la configurazione ' +
        'o la diagnostica di un dispositivo.', TONE_CALM);
    }

    /* `non_disponibili` a tre stati: null = non si sa quali registri hanno
       risposto; [] = tutti hanno risposto; pieno = una lettura a metà, che
       NON deve sembrare una casa piccola. */
    if (home_space.non_disponibili == null) {
      line(body,
        'Non si sa quali registri abbiano risposto: HIRIS non ha potuto controllarlo. ' +
        'L’albero qui sotto potrebbe essere letto solo in parte.', TONE_UNKNOWN);
    } else if (home_space.non_disponibili.length) {
      line(body,
        'Registri che non hanno risposto all’ultima lettura — una casa letta a metà, non una casa piccola:',
        TONE_PROBLEM);
      list(body, unavailableWithCopy(home_space.non_disponibili,
        home_space.non_disponibili_letti_il));
    } else {
      line(body, 'Tutti i registri hanno risposto.', TONE_CALM);
    }

    renderComparison(body, home_space.confronto, home_space.piani || []);

    renderSystem(body, home_space.sistema_di_riferimento, home_space.nomi_misure);

    var treeTitle = el('div', null, 'L’albero');
    treeTitle.style.cssText = 'font-weight:600;margin-top:16px;font-size:var(--fs-15)';
    body.appendChild(treeTitle);

    var floor = home_space.piani || [];
    if (!floor.length) {
      line(body, 'La lettura non ha prodotto nessun piano né area.', TONE_CALM);
      return;
    }
    floor.forEach(function (floor) { renderFloor(body, floor); });
  }

  function renderTreeError(outlet, err) {
    console.error('[albero-della-casa] lettura fallita', err);
    var body = section(outlet, 'Albero della casa', null);
    line(body,
      'Non è stato possibile leggere l’albero della casa. Questo non significa che la casa sia vuota: ' +
      'la richiesta non è andata a buon fine.', TONE_PROBLEM);
  }

  function read(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';

    var head = el('div');
    head.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap';
    var intro = el('div');
    intro.appendChild(el('h1', 'page-title', 'Albero della casa'));
    intro.appendChild(el('p', 'page-subtitle',
      'Come HIRIS vede piani, aree ed entità — non la dashboard di Home Assistant: la sua conoscenza.'));
    head.appendChild(intro);
    var back = el('a', 'btn', 'Cosa HIRIS sa');
    back.href = '#/';
    head.appendChild(back);
    outlet.appendChild(head);

    var loading = el('p', 'page-subtitle', 'Caricamento…');
    outlet.appendChild(loading);

    return read('api/home-space').then(function (home_space) {
      if (loading.parentNode) loading.parentNode.removeChild(loading);
      renderTree(outlet, home_space);
    }, function (err) {
      if (loading.parentNode) loading.parentNode.removeChild(loading);
      renderTreeError(outlet, err);
    });
  }

  return {
    mount: mount
  };
})();
