/* HIRIS · Configurazione · «L'osservatore» (route #/osservatore)

   La prima fetta del cervello nuovo (docs/design/2026-08-26-l-osservatore.md).
   Guarda la casa e ne ricava oggetti -- non conclude niente, non parla, non
   tocca niente. Questa pagina e' la sola faccia che ha oggi: due GET,
   `api/cervello/osservate` e `api/cervello/oggetti?giorno=...`
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
   «Cosa sto guardando» (l'elenco vivo, `Osservatore.osservate()`) e «Cosa e'
   successo» (gli oggetti che l'aggregazione notturna ha scritto,
   `ArchivioOsservazioni.oggetti()`) rispondono a due domande diverse -- la
   prima e' lo stato di un cablaggio, la seconda e' la memoria che ne esce --
   e la spec le tiene separate apposta (§7 e' la pagina, §1-6 sono gli
   oggetti).

   -- I sei gambe dell'obiettivo, non un elenco a caso (`pavimento.GAMBE`) --
   Le voci di «cosa sto guardando» si raggruppano per gamba, nello stesso
   ordine in cui il pavimento le dichiara: chi c'e', comfort, dispersione,
   consumo, buono stato, sicurezza. Duplicato qui (non importato: questa SPA
   non porta build step, ogni route e' autonoma come le sue sorelle) --
   stringhe letterali IDENTICHE a `pavimento.GAMBE`, apostrofo compreso
   («chi c'e'»).

   -- I cinque generi di oggetto (`cervello/oggetti.py::GENERI`) --
   funzionamento, presenza, consumo, guasto, sicurezza. Ogni genere porta un
   `corpo` di forma diversa (`aggrega_giorno`): funzionamento/presenza/
   sicurezza/guasto portano `stato` (il valore che ha aperto l'episodio);
   consumo porta `valore_iniziale`/`valore_finale`/`differenza`. Tutti e
   cinque portano `comprimari` (chi altro c'era, dal caso del lampadario) e
   `misure` (cosa hanno fatto le grandezze collegate mentre l'episodio
   durava) -- mostrati dietro un rivelatore SINCRONO (stesso principio di
   costruzioni-route.js §3: sono gia' nel payload, nasconderli dietro un
   fetch sarebbe la trappola che la guida delle Promesse vieta).

   -- Il giorno di default (mandato Task 7, verifiche dal vivo #1) --
   L'aggregazione notturna scrive «ieri» alle 00:20 (`server.py::
   _aggrega_ieri`): il giorno di oggi, quasi sempre, non ha ancora nessun
   oggetto. Il selettore nasce sul giorno di ieri (calcolato nel fuso del
   BROWSER, non quello della casa -- e' scritto nel testo accanto al campo,
   perche' i due possono differire di un'ora vicino al cambio di data). Un
   bottone accanto toglie il filtro e mostra i più recenti, senza indovinare
   quale giorno guardare.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server -- stessa disciplina di albero-route.js/memoria-route.js. Nessuna
   POST in questa pagina: le due rotte sono GET, quindi nessun
   `X-Requested-With` da portare (non passano dal `csrf_middleware`). */
window.HirisOsservatoreRoute = (function () {
  'use strict';

  var TONO_IGNOTO = 'color:var(--warn-ink)';
  var TONO_PROBLEMA = 'color:var(--err-ink)';
  var TONO_QUIETO = 'color:var(--text-3)';

  /* Letterale, identico a `pavimento.GAMBE` (vedi il commento di testa): sei
     gambe, quest'ordine. Una gamba che l'archivio manda e questa lista non
     conosce finisce comunque in coda, col suo nome grezzo -- non sparisce
     mai, stessa regola di `NOMI_REGISTRI` in albero-route.js. */
  var ORDINE_GAMBE = ["chi c'e'", 'comfort', 'dispersione', 'consumo', 'buono stato', 'sicurezza'];

  var ETICHETTA_GENERE = {
    funzionamento: 'Funzionamento', presenza: 'Presenza / assenza',
    consumo: 'Consumo', guasto: 'Guasto', sicurezza: 'Sicurezza'
  };

  function el(tag, cls, testo) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo != null) e.textContent = testo;
    return e;
  }

  function clearEl(nodo) {
    while (nodo && nodo.firstChild) nodo.removeChild(nodo.firstChild);
    return nodo;
  }

  function riga(padre, testo, stile) {
    var p = el('p', 'sc-desc', testo);
    if (stile) p.style.cssText = stile;
    padre.appendChild(p);
    return p;
  }

  function sezione(outlet, num, titolo, sottotitolo) {
    var card = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', titolo));
    card.appendChild(head);
    if (sottotitolo) card.appendChild(el('p', 'sc-desc', sottotitolo));
    var corpo = el('div', 'sc-body');
    card.appendChild(corpo);
    outlet.appendChild(card);
    return corpo;
  }

  function leggi(percorso) {
    return fetch(percorso).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (corpo) {
        return { ok: r.ok, status: r.status, corpo: corpo };
      });
    });
  }

  /* --------------------------------------------------------- «cosa sto guardando» */

  function badgeProvenienza(provenienza) {
    /* Oggi e' sempre "pavimento": la mappa resta comunque a tre voci (la
       spec ne prevede tre, §7) perche' una voce "obiettivo" o "analista" che
       arrivasse domani non deve leggersi come "pavimento" per un buco qui. */
    if (provenienza === 'pavimento') {
      return { cls: 'badge-off', testo: 'Pavimento — non si toglie' };
    }
    if (provenienza === 'obiettivo') {
      return { cls: 'badge-on', testo: 'Obiettivo — si può togliere' };
    }
    return { cls: 'badge-warn', testo: provenienza || 'provenienza sconosciuta' };
  }

  function raggruppaPerGamba(voci) {
    var gruppi = {};
    voci.forEach(function (v) {
      var g = v.gamba || '(senza gamba)';
      (gruppi[g] = gruppi[g] || []).push(v);
    });
    var ordine = ORDINE_GAMBE.slice();
    Object.keys(gruppi).forEach(function (g) {
      if (ordine.indexOf(g) === -1) ordine.push(g);
    });
    return ordine.filter(function (g) { return gruppi[g]; })
      .map(function (g) { return { gamba: g, voci: gruppi[g] }; });
  }

  function rendiGruppoGamba(corpo, gruppo) {
    var det = el('details');
    det.open = false;
    var sommario = el('summary', null,
      gruppo.gamba + ' — ' + gruppo.voci.length + (gruppo.voci.length === 1 ? ' voce' : ' voci'));
    sommario.style.cssText = 'cursor:pointer;font-weight:500';
    det.appendChild(sommario);

    var ul = el('ul');
    ul.style.cssText = 'margin:6px 0 4px;padding-left:18px';
    gruppo.voci.forEach(function (v) {
      var li = el('li');
      li.style.cssText = 'margin-bottom:6px;font-size:var(--fs-13);overflow-wrap:anywhere;' +
        'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
      li.appendChild(el('span', 'text-mono', v.soggetto));
      var b = badgeProvenienza(v.provenienza);
      li.appendChild(el('span', 'agent-badge ' + b.cls, b.testo));
      ul.appendChild(li);
    });
    det.appendChild(ul);
    corpo.appendChild(det);
  }

  function rendiOsservate(corpo, osservate) {
    if (!osservate.length) {
      riga(corpo,
        'Non sto guardando ancora niente. Se HIRIS e’ appena partito e' +
        ' Home Assistant non ha ancora mandato nessun cambio, e’ normale — torna fra poco.',
        TONO_QUIETO);
      return;
    }
    raggruppaPerGamba(osservate).forEach(function (g) { rendiGruppoGamba(corpo, g); });
  }

  function rendiOsservateErrore(corpo, status) {
    if (status === 503) {
      riga(corpo,
        'L’osservatore non e’ disponibile: HIRIS non sta guardando niente in questo momento. ' +
        'Non e’ una lista vuota — e’ l’osservatore stesso ad essere fermo (riprova dopo un riavvio dell’add-on).',
        TONO_PROBLEMA);
      return;
    }
    riga(corpo, 'Non e’ stato possibile leggere cosa sta guardando l’osservatore. Riprova più tardi.',
      TONO_PROBLEMA);
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

  function fmtOrario(ts) {
    if (ts == null) return null;
    var d = new Date(ts * 1000);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + ' ' +
      pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  function periodo(o) {
    var inizio = fmtOrario(o.inizio_ts);
    var fine = fmtOrario(o.fine_ts);
    if (fine == null) return 'dalle ' + inizio + ', ancora in corso';
    return inizio + ' → ' + fine;
  }

  /* La frase che apre la riga: cosa e' successo, per genere -- il corpo ha
     forma diversa per ciascuno (vedi il commento di testa). Nessuna frase
     generica: campi reali o niente. */
  function frasePrincipale(o) {
    var c = o.corpo || {};
    if (o.genere === 'consumo') {
      if (c.differenza == null) {
        return 'da ' + c.valore_iniziale + ' a ' + c.valore_finale + ' (non calcolabile: una sola lettura, o un valore non numerico)';
      }
      var segno = c.differenza >= 0 ? '+' : '';
      return 'da ' + c.valore_iniziale + ' a ' + c.valore_finale + ' (' + segno + c.differenza + ')';
    }
    if (o.genere === 'guasto') {
      return c.stato === 'aperto' ? 'ancora aperto' : 'stato: ' + (c.stato || '?');
    }
    return c.stato != null ? 'stato: ' + c.stato : '(nessun dettaglio)';
  }

  /* `problema:dominio.id` / `integrazione:entry_id` -> un nome leggibile.
     Stessa idea di `nomiRegistriInItaliano` in albero-route.js: un prefisso
     tecnico non deve restare tale e quale sulla pagina. */
  function nomeProtagonista(o) {
    var s = o.protagonista || '';
    if (s.indexOf('problema:') === 0) return 'Problema Home Assistant: ' + s.slice('problema:'.length);
    if (s.indexOf('integrazione:') === 0) return 'Integrazione non caricata: ' + s.slice('integrazione:'.length);
    return s;
  }

  function rivelatoreDettagli(o) {
    var comprimari = (o.corpo && o.corpo.comprimari) || [];
    var misure = (o.corpo && o.corpo.misure) || {};
    var chiaviMisure = Object.keys(misure);
    if (!comprimari.length && !chiaviMisure.length) return null;

    var wrap = el('div', 'field-group');
    var testoChiuso = 'Chi c’era intorno';
    var testoAperto = 'Nascondi';
    var btn = el('button', 'btn btn-ghost btn-sm', testoChiuso);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');

    var pannello = el('div');
    pannello.hidden = true;
    pannello.style.cssText = 'margin-top:6px';
    if (comprimari.length) {
      riga(pannello, 'Insieme a: ' + comprimari.join(', '), 'font-size:var(--fs-12);' + TONO_QUIETO);
    }
    chiaviMisure.forEach(function (k) {
      var m = misure[k];
      riga(pannello, k + ': da ' + m.da + ' a ' + m.a, 'font-size:var(--fs-12);' + TONO_QUIETO);
    });

    btn.addEventListener('click', function () {
      var aperto = btn.getAttribute('aria-expanded') === 'true';
      pannello.hidden = aperto;
      btn.setAttribute('aria-expanded', aperto ? 'false' : 'true');
      btn.textContent = aperto ? testoChiuso : testoAperto;
    });

    wrap.appendChild(btn);
    wrap.appendChild(pannello);
    return wrap;
  }

  function rigaOggetto(o) {
    var box = el('div');
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-3) 0;' +
      'display:flex;flex-direction:column;gap:4px';

    var testa = el('div');
    testa.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
    testa.appendChild(el('span', 'agent-badge badge-off', ETICHETTA_GENERE[o.genere] || o.genere));
    testa.appendChild(el('span', null, nomeProtagonista(o)));
    box.appendChild(testa);

    box.appendChild(el('p', 'field-hint', periodo(o) + ' · ' + frasePrincipale(o)));

    var dettagli = rivelatoreDettagli(o);
    if (dettagli) box.appendChild(dettagli);

    return box;
  }

  function rendiOggetti(corpo, oggetti, giornoFiltro) {
    if (!oggetti.length) {
      riga(corpo, giornoFiltro
        ? 'Nessun oggetto per il ' + giornoFiltro + '. Non è un errore: quel giorno la casa potrebbe non aver fatto niente di osservabile, oppure l’aggregazione notturna non è ancora passata.'
        : 'Non c’è ancora nessun oggetto: l’aggregazione notturna gira una volta al giorno, alle 00:20.',
        TONO_QUIETO);
      return;
    }
    oggetti.forEach(function (o) { corpo.appendChild(rigaOggetto(o)); });
  }

  function rendiOggettiErrore(corpo, status) {
    if (status === 503) {
      riga(corpo,
        'L’archivio degli oggetti non e’ disponibile in questo momento. Non e’ una lista vuota — e’ l’archivio stesso ad essere fermo.',
        TONO_PROBLEMA);
      return;
    }
    riga(corpo, 'Non e’ stato possibile leggere gli oggetti. Riprova più tardi.', TONO_PROBLEMA);
  }

  /* ------------------------------------------------------------------------ mount */

  function caricaOsservate(corpo) {
    clearEl(corpo);
    riga(corpo, 'Caricamento…', TONO_QUIETO);
    return leggi('api/cervello/osservate').then(function (esito) {
      clearEl(corpo);
      if (!esito.ok) { rendiOsservateErrore(corpo, esito.status); return; }
      rendiOsservate(corpo, esito.corpo.osservate || []);
    }, function () {
      clearEl(corpo);
      rendiOsservateErrore(corpo, null);
    });
  }

  function caricaOggetti(corpo, giorno) {
    clearEl(corpo);
    riga(corpo, 'Caricamento…', TONO_QUIETO);
    var percorso = 'api/cervello/oggetti' + (giorno ? '?giorno=' + encodeURIComponent(giorno) : '');
    return leggi(percorso).then(function (esito) {
      clearEl(corpo);
      if (!esito.ok) { rendiOggettiErrore(corpo, esito.status); return; }
      rendiOggetti(corpo, esito.corpo.oggetti || [], giorno);
    }, function () {
      clearEl(corpo);
      rendiOggettiErrore(corpo, null);
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);

    outlet.appendChild(el('div', 'page-title', 'L’osservatore'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Guarda la casa e ne ricava oggetti. Non conclude niente, non parla, non tocca niente — ' +
      'e’ il materiale su cui domani ragionerà l’analista.'));

    var corpoOsservate = sezione(outlet, '01', 'Cosa sto guardando',
      'Ogni voce dice da dove viene: dal pavimento non si può togliere, perché è quello che ' +
      'HIRIS osserva sempre, comunque, per capire se la casa è confortevole, efficiente e sicura.');

    /* Sezione 02 costruita a mano (non con `sezione()`): a differenza della
       01, questa porta un blocco di controlli (data + bottone) fra il
       sottotitolo e il corpo, e `sezione()` non lo prevede. */
    var card2 = el('section', 'section-card');
    var head2 = el('div', 'sc-header');
    head2.appendChild(el('span', 'sc-num', '02'));
    head2.appendChild(el('h2', 'sc-title', 'Cosa è successo'));
    card2.appendChild(head2);
    card2.appendChild(el('p', 'sc-desc',
      'Gli oggetti che l’aggregazione notturna ha costruito dai cambi grezzi di un giorno — ' +
      'scritti alle 00:20, sul fuso della CASA. Il giorno qui sotto è calcolato sul fuso di ' +
      'questo browser: vicino alla mezzanotte i due possono differire di un’ora.'));

    var controlli = el('div');
    controlli.style.cssText = 'display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:12px';
    var campoGiorno = el('div');
    campoGiorno.appendChild(el('label', 'field-hint', 'Giorno'));
    var inputGiorno = el('input');
    inputGiorno.type = 'date';
    inputGiorno.value = ieriLocale();
    inputGiorno.style.cssText = 'display:block;padding:6px 8px;border-radius:8px;min-height:38px;box-sizing:border-box';
    campoGiorno.appendChild(inputGiorno);
    controlli.appendChild(campoGiorno);

    var btnRecenti = el('button', 'btn btn-ghost btn-sm', 'Vedi i più recenti, senza filtro');
    btnRecenti.type = 'button';
    controlli.appendChild(btnRecenti);
    card2.appendChild(controlli);

    var corpoOggetti = el('div', 'sc-body');
    card2.appendChild(corpoOggetti);
    outlet.appendChild(card2);

    inputGiorno.addEventListener('change', function () {
      caricaOggetti(corpoOggetti, inputGiorno.value || null);
    });
    btnRecenti.addEventListener('click', function () {
      inputGiorno.value = '';
      caricaOggetti(corpoOggetti, null);
    });

    caricaOsservate(corpoOsservate);
    caricaOggetti(corpoOggetti, inputGiorno.value);
  }

  return {
    mount: mount,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiOsservate: rendiOsservate,
    _rendiOggetti: rendiOggetti
  };
})();
