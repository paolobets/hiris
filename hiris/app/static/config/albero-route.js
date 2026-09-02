/* HIRIS · Configurazione · «Albero della casa» (route #/albero)

   Chiude il reperto 26: `GET /api/home-space` manda gia' l'albero completo che
   `anagrafe.gerarchia()` costruisce -- piani -> aree -> entita', col
   comportamento, la piattaforma, la categoria, la classe, l'unita', se
   un'entita' e' nascosta, i suoi alias e le sue etichette -- ed e' il
   payload piu' ricco che HIRIS produce. Prima usciva verso nessuno:
   `dashboard.js` (`#/`, «Cosa HIRIS sa») legge la stessa risposta e ne
   mostra solo i CONTEGGI (`casa.conteggi`), mai `casa.piani`. Questa pagina
   e' la faccia di quel campo.

   Non e' una copia della dashboard di Home Assistant: il punto non e'
   "arreda la stanza", e' "mostra cosa HIRIS crede di sapere della stanza",
   cosi' l'utente si accorge quando HIRIS sbaglia.

   Tre distinzioni che la pagina DEVE rendere visibili, perche' sono la
   parte che conta (vedi il docstring di `anagrafe.gerarchia()`, che resta
   la spiegazione migliore che esista):

   1) Le pseudo-aree/pseudo-piani che `gerarchia()` crea per dichiarare i
      SILENZI -- «Senza area», «Area sconosciuta», «Aree non lette»,
      «Dispositivi non letti», «Senza piano», «Piani non letti». Sono SEI
      cause diverse, non varianti di un unico "non si sa": "Senza area" e
      "Senza piano" sono un FATTO confermato (il registro ha risposto, e
      quelle entita' davvero non hanno casa); "Area sconosciuta" e'
      un'INCOERENZA vera (un riferimento che punta a un'area sparita);
      "Aree/Piani/Dispositivi non letti" sono un BUCO di lettura (non si
      puo' sapere). Appiattirle in un'unica frase sarebbe il difetto
      esatto che questa pagina esiste per chiudere -- vedi
      `SPIEGAZIONE_PIANO`/`SPIEGAZIONE_AREA` sotto, un tono diverso per
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
   server -- stessa disciplina di dashboard.js/memoria-route.js. */
window.HirisAlberoRoute = (function () {
  'use strict';

  var TONE_UNKNOWN = 'color:var(--warn-ink)';
  var TONE_PROBLEM = 'color:var(--err-ink)';
  var TONE_CALM = 'color:var(--text-3)';

  /* Gli stessi id letterali che `anagrafe.py` usa per le pseudo-aree e i
     due piani-contenitore (`_ID_*`). Non sono un'API pubblica dichiarata,
     ma sono stringhe stabili: `gerarchia()` le costruisce a mano, non le
     genera, e un test di mutazione su questo file prova che restano
     allineate (vedi tests/js/albero-route.test.mjs). */
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

  /* Nomi italiani dei registri di `non_disponibili` -- stessa mappa di
     dashboard.js. Duplicata (non importata) di proposito: ogni route di
     questa SPA e' autonoma, stesso pattern di memoria-route.js e
     usage-route.js, che duplicano a loro volta i toni qui sopra invece di
     dipendere l'una dall'altra. */
  var NOMI_REGISTRI = {
    piani: 'Piani', aree: 'Aree', dispositivi: 'Dispositivi', entita: 'Entità',
    etichette: 'Etichette', categorie: 'Categorie', integrazioni: 'Integrazioni'
  };

  function nomiRegistriInItaliano(voci) {
    return voci.map(function (entry) {
      var pezzi = String(entry).split(':');
      var name = NOMI_REGISTRI[pezzi[0]] || pezzi[0];
      var scope = pezzi.slice(1).join(':');
      return scope ? name + ' (ambito «' + scope + '»)' : name;
    });
  }

  /* Le unità del sistema di riferimento, stessa mappa e stesso ordine di
     `nucleo._NOMI_MISURA` -- cosi' la stessa casa si legge uguale sul
     nucleo del modello e su questa pagina. Una chiave che HA manda e che
     questa mappa non conosce ancora NON sparisce: compare col suo nome
     grezzo, stessa regola di `NOMI_REGISTRI` sopra e delle "chiavi
     sconosciute" di dashboard.js. */
  var CHIAVI_MISURA_NOTE = ['temperature', 'length', 'mass', 'pressure', 'volume',
    'wind_speed', 'accumulated_precipitation', 'area'];
  var NOMI_MISURA = {
    temperature: 'temperatura', length: 'lunghezza', mass: 'massa', pressure: 'pressione',
    volume: 'volume', wind_speed: 'vento', accumulated_precipitation: 'pioggia', area: 'area'
  };

  function homeMeasurements(unit) {
    if (!unit) return [];
    var chiavi = CHIAVI_MISURA_NOTE.slice();
    Object.keys(unit).forEach(function (k) { if (chiavi.indexOf(k) === -1) chiavi.push(k); });
    return chiavi
      .filter(function (k) { return unit[k]; })
      .map(function (k) { return (NOMI_MISURA[k] || k) + ' ' + unit[k]; });
  }

  /* I NOMI delle etichette (`casa.etichette`, `GET /api/home-space`): mappa
     id -> nome, risolta una volta sola dal backend -- vedi
     `handlers_casa.handle_get_home_space`. `gerarchia()` mette su aree ed
     entita' i soli `label_id` (cosi' li manda Home Assistant): senza
     questa funzione l'albero mostrerebbe lo slug («da_controllare»)
     invece del nome che l'utente ha scritto («Da controllare»).

     Un id che la mappa non conosce NON sparisce e non diventa un nome
     inventato: resta l'id cosi' com'e'. E' un riferimento penzolante --
     un'etichetta cancellata dopo che l'entita' l'ha ricevuta, o una
     mappa letta solo in parte -- e "questa cosa ha un'etichetta che non
     so nominare" e' piu' vero di "questa cosa non ha etichette". Vale
     anche quando `mappa` e' `null` (l'archivio manca, stessa disciplina
     a tre stati di `non_disponibili`): un lookup su `null` non trova
     niente, e la stessa riga sotto ripiega sull'id grezzo. */
  function labelName(id, map) {
    if (map && Object.prototype.hasOwnProperty.call(map, id)) return map[id];
    return id;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

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
    head.appendChild(el('div', 'sc-title', title));
    if (subtitle) head.appendChild(el('div', 'sc-desc', subtitle));
    card.appendChild(head);
    var body = el('div', 'sc-body');
    card.appendChild(body);
    outlet.appendChild(card);
    return body;
  }

  /* --------------------------------------------------------- sistema di riferimento */

  function renderSystem(body, system) {
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

    var measurements = homeMeasurements(system.unita);
    if (measurements.length) {
      line(body, 'Unità con cui ragiona la casa: ' + measurements.join(', ') +
        ' (ogni entità porta la propria: se manca, manca — non è questa).', TONE_CALM);
    }
  }

  /* --------------------------------------------------------------------- entità */

  function entityLine(ul, e, disabled, labelMap) {
    var li = el('li');
    /* `overflow-wrap:anywhere` anche qui (non solo sull'id): alias ed
       etichette penzolanti sono a loro volta slug senza spazi, stesso
       rischio di sfondare la larghezza. */
    li.style.cssText = 'margin-bottom:8px;font-size:var(--fs-13);overflow-wrap:anywhere';

    var head = el('span', null, (e.nome || e.id || '?') + ' ');
    head.style.fontWeight = '500';
    li.appendChild(head);

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

    /* Le due marcature non si nascondono l'un l'altra e non si nascondono
       l'entità: "disabilitata" (registro) e "nascosta" (Home Assistant)
       sono fatti diversi, e un'entità puo' portarli entrambi. */
    if (disabled) {
      var d = el('span', null, ' [disabilitata]');
      d.style.cssText = TONE_UNKNOWN + ';font-size:var(--fs-12)';
      li.appendChild(d);
    }
    if (e.nascosta) {
      var n = el('span', null, ' [nascosta in Home Assistant]');
      n.style.cssText = TONE_UNKNOWN + ';font-size:var(--fs-12)';
      li.appendChild(n);
    }

    var details = [];
    if (e.piattaforma) details.push('piattaforma ' + e.piattaforma);
    if (e.categoria) details.push('categoria ' + e.categoria);
    if (e.classe) details.push('classe ' + e.classe);
    if (e.unita) details.push('unità ' + e.unita);
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
    if (e.etichette && e.etichette.length) {
      var nomiEtichette = e.etichette.map(function (id) { return labelName(id, labelMap); });
      var et = el('div', null, 'etichette: ' + nomiEtichette.join(', '));
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
    if (disabled) base += ', ' + disabled + ' disabilitata'.concat(disabled === 1 ? '' : 'e');
    /* Stessa disciplina delle disabilitate (fetta "nascoste fuori dagli
       elenchi", 2026-08-25): questa pagina esiste per non far sparire
       niente -- un'area con quattro luci nascoste e tre attive deve
       leggersi come "3 entità, 4 nascoste", non come "3 entità" secco. */
    if (hidden) base += ', ' + hidden + ' nascosta'.concat(hidden === 1 ? '' : 'e');
    return base;
  }

  function renderArea(container, area, labelMap) {
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
       da quando `gerarchia()` le toglie da `entita` per STRUTTURA (la stessa
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
      active.forEach(function (e) { entityLine(ul, e, false, labelMap); });
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
      disabled.forEach(function (e) { entityLine(ulD, e, true, labelMap); });
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
      hidden.forEach(function (e) { entityLine(ulN, e, false, labelMap); });
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

  function renderFloor(container, floor, labelMap) {
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

    (floor.aree || []).forEach(function (area) { renderArea(body, area, labelMap); });

    det.appendChild(body);
    container.appendChild(det);
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

    line(body, 'Letta il ' + home_space.anagrafe_letta_il + '.', TONE_CALM);

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
      list(body, nomiRegistriInItaliano(home_space.non_disponibili));
    } else {
      line(body, 'Tutti i registri hanno risposto.', TONE_CALM);
    }

    renderSystem(body, home_space.sistema_di_riferimento);

    /* `etichette` (`casa.etichette`) e' a tre stati come `non_disponibili`:
       `null` = l'archivio manca, nessun nome risolvibile (nella pratica
       coincide col ramo `anagrafe_letta_il == null` qui sopra, che e' gia'
       uscito prima di arrivare qui -- ma questa funzione non lo presume: se
       un domani i due campi divergessero, l'albero continuerebbe a mostrare
       gli id grezzi invece di un nome inventato, e lo DICHIAREREBBE, non lo
       tacerebbe); `{}` = il registro ha risposto senza etichette; pieno = la
       mappa che `nomeEtichetta()` usa per tradurre gli slug sotto. */
    var labelMap = home_space.etichette;
    if (labelMap == null) {
      line(body,
        'I nomi delle etichette non sono stati letti: dove un’entità o un’area ne porta una, ' +
        'resta visibile il solo identificativo grezzo.', TONE_UNKNOWN);
    }

    var treeTitle = el('div', null, 'L’albero');
    treeTitle.style.cssText = 'font-weight:600;margin-top:16px;font-size:var(--fs-15)';
    body.appendChild(treeTitle);

    var floor = home_space.piani || [];
    if (!floor.length) {
      line(body, 'La lettura non ha prodotto nessun piano né area.', TONE_CALM);
      return;
    }
    floor.forEach(function (floor) { renderFloor(body, floor, labelMap); });
  }

  function renderError(outlet, err) {
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
    intro.appendChild(el('div', 'page-title', 'Albero della casa'));
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
      renderError(outlet, err);
    });
  }

  return {
    mount: mount,
    /* Seam di test: la resa è pura DOM + dati, va pinnata senza passare da fetch. */
    _rendi: renderTree
  };
})();
