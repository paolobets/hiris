/* HIRIS · Configurazione · «Albero della casa» (route #/albero)

   Chiude il reperto 26: `GET /api/casa` manda gia' l'albero completo che
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
      deve sembrare un'area vuota.
   3) `non_disponibili` e `sistema_di_riferimento`, con la stessa
      disciplina a tre stati di `dashboard.js`: un `null` non e' un `[]`,
      e una casa letta a meta' non deve sembrare una casa piccola.

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati
   server -- stessa disciplina di dashboard.js/memoria-route.js. */
window.HirisAlberoRoute = (function () {
  'use strict';

  var TONO_IGNOTO = 'color:var(--warn-ink)';
  var TONO_PROBLEMA = 'color:var(--err-ink)';
  var TONO_QUIETO = 'color:var(--text-3)';

  /* Gli stessi id letterali che `anagrafe.py` usa per le pseudo-aree e i
     due piani-contenitore (`_ID_*`). Non sono un'API pubblica dichiarata,
     ma sono stringhe stabili: `gerarchia()` le costruisce a mano, non le
     genera, e un test di mutazione su questo file prova che restano
     allineate (vedi tests/js/albero-route.test.mjs). */
  var ID_SENZA_AREA = '__senza_area__';
  var ID_AREE_NON_LETTE = '__aree_non_lette__';
  var ID_AREA_SCONOSCIUTA = '__area_sconosciuta__';
  var ID_DISPOSITIVI_NON_LETTI = '__dispositivi_non_letti__';
  var ID_SENZA_PIANO = '__senza_piano__';
  var ID_PIANI_NON_LETTI = '__piani_non_letti__';
  var ID_FUORI_DALLE_AREE = '__fuori_dalle_aree__';

  var SPIEGAZIONE_PIANO = {};
  SPIEGAZIONE_PIANO[ID_SENZA_PIANO] = {
    testo: 'Aree vere di Home Assistant, che l’utente non ha assegnato a nessun piano.',
    tono: TONO_QUIETO
  };
  SPIEGAZIONE_PIANO[ID_PIANI_NON_LETTI] = {
    testo: 'Il registro dei piani non ha risposto: queste aree potrebbero avere un piano che ' +
      'HIRIS non ha potuto leggere — non è detto che non ne abbiano uno.',
    tono: TONO_IGNOTO
  };
  SPIEGAZIONE_PIANO[ID_FUORI_DALLE_AREE] = {
    testo: 'Entità che non stanno in nessuna area nota, per quattro ragioni diverse — una per ' +
      'ciascun gruppo qui sotto.',
    tono: TONO_IGNOTO
  };

  var SPIEGAZIONE_AREA = {};
  SPIEGAZIONE_AREA[ID_SENZA_AREA] = {
    testo: 'Il registro delle aree ha risposto: queste entità davvero non sono assegnate a ' +
      'nessuna stanza.',
    tono: TONO_QUIETO
  };
  SPIEGAZIONE_AREA[ID_AREE_NON_LETTE] = {
    testo: 'Il registro delle aree non ha risposto: non si può sapere se queste entità abbiano ' +
      'un’area o no.',
    tono: TONO_IGNOTO
  };
  SPIEGAZIONE_AREA[ID_AREA_SCONOSCIUTA] = {
    testo: 'Queste entità puntano a un’area che non esiste più nel registro — un riferimento ' +
      'rotto, non un’assenza.',
    tono: TONO_PROBLEMA
  };
  SPIEGAZIONE_AREA[ID_DISPOSITIVI_NON_LETTI] = {
    testo: 'Il registro dei dispositivi non ha risposto: queste entità erediterebbero l’area ' +
      'dal proprio dispositivo, ma HIRIS non ha potuto leggere quale.',
    tono: TONO_IGNOTO
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
    return voci.map(function (voce) {
      var pezzi = String(voce).split(':');
      var nome = NOMI_REGISTRI[pezzi[0]] || pezzi[0];
      var ambito = pezzi.slice(1).join(':');
      return ambito ? nome + ' (ambito «' + ambito + '»)' : nome;
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

  function misureCasa(unita) {
    if (!unita) return [];
    var chiavi = CHIAVI_MISURA_NOTE.slice();
    Object.keys(unita).forEach(function (k) { if (chiavi.indexOf(k) === -1) chiavi.push(k); });
    return chiavi
      .filter(function (k) { return unita[k]; })
      .map(function (k) { return (NOMI_MISURA[k] || k) + ' ' + unita[k]; });
  }

  /* I NOMI delle etichette (`casa.etichette`, `GET /api/casa`): mappa
     id -> nome, risolta una volta sola dal backend -- vedi
     `handlers_casa.handle_get_casa`. `gerarchia()` mette su aree ed
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
  function nomeEtichetta(id, mappa) {
    if (mappa && Object.prototype.hasOwnProperty.call(mappa, id)) return mappa[id];
    return id;
  }

  function el(tag, cls, testo) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo != null) e.textContent = testo;
    return e;
  }

  function riga(padre, testo, stile) {
    var p = el('p', 'sc-desc', testo);
    if (stile) p.style.cssText = stile;
    padre.appendChild(p);
    return p;
  }

  function elenco(padre, voci) {
    var ul = el('ul');
    ul.style.cssText = 'margin:4px 0 0;padding-left:20px;color:var(--text-2);font-size:var(--fs-13)';
    voci.forEach(function (v) { ul.appendChild(el('li', null, v)); });
    padre.appendChild(ul);
    return ul;
  }

  function sezione(outlet, titolo, sottotitolo) {
    var card = el('section', 'section-card');
    var testa = el('div', 'sc-header');
    testa.appendChild(el('div', 'sc-title', titolo));
    if (sottotitolo) testa.appendChild(el('div', 'sc-desc', sottotitolo));
    card.appendChild(testa);
    var corpo = el('div', 'sc-body');
    card.appendChild(corpo);
    outlet.appendChild(card);
    return corpo;
  }

  /* --------------------------------------------------------- sistema di riferimento */

  function rendiSistema(corpo, sistema) {
    var titolo = el('div', null, 'Sistema di riferimento');
    titolo.style.cssText = 'font-weight:500;margin-top:14px';
    corpo.appendChild(titolo);

    if (!sistema || !Object.keys(sistema).length) {
      riga(corpo, 'Non letto: fuso, unità, valuta e lingua della casa non sono disponibili.', TONO_IGNOTO);
      return;
    }

    var identita = [];
    if (sistema.nome) identita.push('casa «' + sistema.nome + '»');
    if (sistema.fuso) identita.push('fuso ' + sistema.fuso);
    if (sistema.lingua) identita.push('lingua ' + sistema.lingua);
    if (sistema.valuta) identita.push('valuta ' + sistema.valuta);
    if (sistema.paese) identita.push('paese ' + sistema.paese);
    if (sistema.versione_ha) identita.push('Home Assistant ' + sistema.versione_ha);
    riga(corpo, identita.length ? identita.join(', ') + '.' : 'Nessun dettaglio d’identità dichiarato.', TONO_QUIETO);

    var misure = misureCasa(sistema.unita);
    if (misure.length) {
      riga(corpo, 'Unità con cui ragiona la casa: ' + misure.join(', ') +
        ' (ogni entità porta la propria: se manca, manca — non è questa).', TONO_QUIETO);
    }
  }

  /* --------------------------------------------------------------------- entità */

  function rigaEntita(ul, e, disabilitata, mappaEtichette) {
    var li = el('li');
    li.style.cssText = 'margin-bottom:8px;font-size:var(--fs-13)';

    var testa = el('span', null, (e.nome || e.id || '?') + ' ');
    testa.style.fontWeight = '500';
    li.appendChild(testa);

    if (e.id) {
      var idSpan = el('span', null, '(' + e.id + ')');
      idSpan.style.cssText = 'color:var(--text-3);font-size:var(--fs-12)';
      li.appendChild(idSpan);
    }

    /* Le due marcature non si nascondono l'un l'altra e non si nascondono
       l'entità: "disabilitata" (registro) e "nascosta" (Home Assistant)
       sono fatti diversi, e un'entità puo' portarli entrambi. */
    if (disabilitata) {
      var d = el('span', null, ' [disabilitata]');
      d.style.cssText = TONO_IGNOTO + ';font-size:var(--fs-12)';
      li.appendChild(d);
    }
    if (e.nascosta) {
      var n = el('span', null, ' [nascosta in Home Assistant]');
      n.style.cssText = TONO_IGNOTO + ';font-size:var(--fs-12)';
      li.appendChild(n);
    }

    var dettagli = [];
    if (e.piattaforma) dettagli.push('piattaforma ' + e.piattaforma);
    if (e.categoria) dettagli.push('categoria ' + e.categoria);
    if (e.classe) dettagli.push('classe ' + e.classe);
    if (e.unita) dettagli.push('unità ' + e.unita);
    if (dettagli.length) {
      var dl = el('div', null, dettagli.join(' · '));
      dl.style.cssText = 'font-size:var(--fs-12);color:var(--text-2)';
      li.appendChild(dl);
    }

    if (e.alias && e.alias.length) {
      var a = el('div', null, 'alias: ' + e.alias.join(', '));
      a.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
      li.appendChild(a);
    }
    if (e.etichette && e.etichette.length) {
      var nomiEtichette = e.etichette.map(function (id) { return nomeEtichetta(id, mappaEtichette); });
      var et = el('div', null, 'etichette: ' + nomiEtichette.join(', '));
      et.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
      li.appendChild(et);
    }

    ul.appendChild(li);
  }

  /* ------------------------------------------------------------------------ aree */

  function etichettaConteggioEntita(area) {
    var attive = (area.entita || []).length;
    var disabilitate = (area.entita_disabilitate || []).length;
    var base = attive + ' entità';
    return disabilitate ? base + ', ' + disabilitate + ' disabilitata'.concat(disabilitate === 1 ? '' : 'e') : base;
  }

  function rendiArea(container, area, mappaEtichette) {
    var det = el('details');
    det.open = true;

    var sommario = el('summary', null, area.nome + ' — ' + etichettaConteggioEntita(area));
    sommario.style.cssText = 'cursor:pointer;font-weight:500';
    det.appendChild(sommario);

    var corpo = el('div');
    corpo.style.cssText = 'padding:6px 0 10px 18px;border-left:2px solid var(--border);margin-left:4px';

    var spiegazione = SPIEGAZIONE_AREA[area.id];
    if (spiegazione) riga(corpo, spiegazione.testo, spiegazione.tono + ';font-size:var(--fs-13)');

    if (area.entita_temperatura) {
      riga(corpo, 'Temperatura di quest’area: ' + area.entita_temperatura, 'font-size:var(--fs-12);color:var(--text-3)');
    }
    if (area.entita_umidita) {
      riga(corpo, 'Umidità di quest’area: ' + area.entita_umidita, 'font-size:var(--fs-12);color:var(--text-3)');
    }

    var attive = area.entita || [];
    var disabilitate = area.entita_disabilitate || [];

    if (!attive.length && !disabilitate.length) {
      riga(corpo, 'Nessuna entità.', TONO_QUIETO);
    }
    if (attive.length) {
      var ul = el('ul');
      ul.style.cssText = 'margin:4px 0;padding-left:18px';
      attive.forEach(function (e) { rigaEntita(ul, e, false, mappaEtichette); });
      corpo.appendChild(ul);
    }
    if (disabilitate.length) {
      /* Presenti e marcate, MAI nascoste: questo titolo compare SEMPRE che
         ce ne sia almeno una, anche se `attive` è vuoto -- un'area con tre
         luci disabilitate e zero attive non deve leggersi come vuota. */
      var titoloDis = el('div', null,
        disabilitate.length === 1 ? 'Entità disabilitata' : 'Entità disabilitate (' + disabilitate.length + ')');
      titoloDis.style.cssText = 'font-weight:500;margin-top:8px;font-size:var(--fs-13)';
      corpo.appendChild(titoloDis);
      var ulD = el('ul');
      ulD.style.cssText = 'margin:4px 0;padding-left:18px';
      disabilitate.forEach(function (e) { rigaEntita(ulD, e, true, mappaEtichette); });
      corpo.appendChild(ulD);
    }

    det.appendChild(corpo);
    container.appendChild(det);
  }

  /* ----------------------------------------------------------------------- piani */

  function etichettaConteggioAree(piano) {
    var n = (piano.aree || []).length;
    var parola = piano.id === ID_FUORI_DALLE_AREE ? (n === 1 ? 'gruppo' : 'gruppi') : (n === 1 ? 'area' : 'aree');
    return n + ' ' + parola;
  }

  function rendiPiano(container, piano, mappaEtichette) {
    var det = el('details');
    det.open = true;

    var titoloPiano = piano.nome + (piano.livello != null ? ' (livello ' + piano.livello + ')' : '');
    var sommario = el('summary', null, titoloPiano + ' — ' + etichettaConteggioAree(piano));
    sommario.style.cssText = 'cursor:pointer;font-weight:600;font-size:var(--fs-15)';
    det.appendChild(sommario);

    var corpo = el('div');
    corpo.style.cssText = 'padding:8px 0 12px 12px';

    var spiegazione = SPIEGAZIONE_PIANO[piano.id];
    if (spiegazione) riga(corpo, spiegazione.testo, spiegazione.tono + ';font-size:var(--fs-13)');

    (piano.aree || []).forEach(function (area) { rendiArea(corpo, area, mappaEtichette); });

    det.appendChild(corpo);
    container.appendChild(det);
  }

  /* --------------------------------------------------------------------- albero */

  function rendiAlbero(outlet, casa) {
    var corpo = sezione(outlet, 'Albero della casa',
      'Piani, aree ed entità come HIRIS li ha ricostruiti — con ogni silenzio dichiarato per nome, ' +
      'non appiattito in un unico «non si sa».');

    /* Regola non negoziabile: una casa non letta non è una casa vuota.
       Niente albero (nemmeno vuoto) su una lettura mai avvenuta -- lo
       stesso principio di dashboard.js applicato qui. */
    if (casa.anagrafe_letta_il == null) {
      riga(corpo,
        'L’anagrafe non è ancora stata letta: qui non c’è un albero vuoto, c’è una casa che HIRIS non ha ancora guardato.',
        TONO_IGNOTO);
      return;
    }

    riga(corpo, 'Letta il ' + casa.anagrafe_letta_il + '.', TONO_QUIETO);

    /* `non_disponibili` a tre stati: null = non si sa quali registri hanno
       risposto; [] = tutti hanno risposto; pieno = una lettura a metà, che
       NON deve sembrare una casa piccola. */
    if (casa.non_disponibili == null) {
      riga(corpo,
        'Non si sa quali registri abbiano risposto: HIRIS non ha potuto controllarlo. ' +
        'L’albero qui sotto potrebbe essere letto solo in parte.', TONO_IGNOTO);
    } else if (casa.non_disponibili.length) {
      riga(corpo,
        'Registri che non hanno risposto all’ultima lettura — una casa letta a metà, non una casa piccola:',
        TONO_PROBLEMA);
      elenco(corpo, nomiRegistriInItaliano(casa.non_disponibili));
    } else {
      riga(corpo, 'Tutti i registri hanno risposto.', TONO_QUIETO);
    }

    rendiSistema(corpo, casa.sistema_di_riferimento);

    /* `etichette` (`casa.etichette`) e' a tre stati come `non_disponibili`:
       `null` = l'archivio manca, nessun nome risolvibile (nella pratica
       coincide col ramo `anagrafe_letta_il == null` qui sopra, che e' gia'
       uscito prima di arrivare qui -- ma questa funzione non lo presume: se
       un domani i due campi divergessero, l'albero continuerebbe a mostrare
       gli id grezzi invece di un nome inventato, e lo DICHIAREREBBE, non lo
       tacerebbe); `{}` = il registro ha risposto senza etichette; pieno = la
       mappa che `nomeEtichetta()` usa per tradurre gli slug sotto. */
    var mappaEtichette = casa.etichette;
    if (mappaEtichette == null) {
      riga(corpo,
        'I nomi delle etichette non sono stati letti: dove un’entità o un’area ne porta una, ' +
        'resta visibile il solo identificativo grezzo.', TONO_IGNOTO);
    }

    var titoloAlbero = el('div', null, 'L’albero');
    titoloAlbero.style.cssText = 'font-weight:600;margin-top:16px;font-size:var(--fs-15)';
    corpo.appendChild(titoloAlbero);

    var piani = casa.piani || [];
    if (!piani.length) {
      riga(corpo, 'La lettura non ha prodotto nessun piano né area.', TONO_QUIETO);
      return;
    }
    piani.forEach(function (piano) { rendiPiano(corpo, piano, mappaEtichette); });
  }

  function rendiErrore(outlet, err) {
    console.error('[albero-della-casa] lettura fallita', err);
    var corpo = sezione(outlet, 'Albero della casa', null);
    riga(corpo,
      'Non è stato possibile leggere l’albero della casa. Questo non significa che la casa sia vuota: ' +
      'la richiesta non è andata a buon fine.', TONO_PROBLEMA);
  }

  function leggi(percorso) {
    return fetch(percorso).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';

    var testa = el('div');
    testa.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap';
    var intro = el('div');
    intro.appendChild(el('div', 'page-title', 'Albero della casa'));
    intro.appendChild(el('p', 'page-subtitle',
      'Come HIRIS vede piani, aree ed entità — non la dashboard di Home Assistant: la sua conoscenza.'));
    testa.appendChild(intro);
    var indietro = el('a', 'btn', 'Cosa HIRIS sa');
    indietro.href = '#/';
    testa.appendChild(indietro);
    outlet.appendChild(testa);

    var caricamento = el('p', 'page-subtitle', 'Caricamento…');
    outlet.appendChild(caricamento);

    return leggi('api/casa').then(function (casa) {
      if (caricamento.parentNode) caricamento.parentNode.removeChild(caricamento);
      rendiAlbero(outlet, casa);
    }, function (err) {
      if (caricamento.parentNode) caricamento.parentNode.removeChild(caricamento);
      rendiErrore(outlet, err);
    });
  }

  return {
    mount: mount,
    /* Seam di test: la resa è pura DOM + dati, va pinnata senza passare da fetch. */
    _rendi: rendiAlbero
  };
})();
