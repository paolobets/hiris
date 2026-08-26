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
   BROWSER, non quello della casa -- e' scritto nel testo accanto al campo).
   Rilievo 12 della review: i due fusi possono differire di un GIORNO intero
   (non "un'ora", cifra non misurata) vicino alla mezzanotte, se si guarda da
   un fuso diverso da quello della casa -- nel caso reale (casa e utente
   nello stesso fuso) l'errore e' zero a qualunque ora. Un bottone accanto
   toglie il filtro e mostra i più recenti, senza indovinare quale giorno
   guardare.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server -- stessa disciplina di albero-route.js/memoria-route.js. Nessuna
   POST in questa pagina: le due rotte sono GET, quindi nessun
   `X-Requested-With` da portare (non passano dal `csrf_middleware`). */
window.HirisOsservatoreRoute = (function () {
  'use strict';

  var TONO_PROBLEMA = 'color:var(--err-ink)';
  var TONO_QUIETO = 'color:var(--text-3)';

  /* Letterale, identico a `pavimento.GAMBE` (vedi il commento di testa): sei
     gambe, quest'ordine. Una gamba che l'archivio manda e questa lista non
     conosce finisce comunque in coda, col suo nome grezzo -- non sparisce
     mai, stessa regola di `NOMI_REGISTRI` in albero-route.js. I VALORI
     restano quelli letterali (identici a `pavimento.GAMBE`): solo la resa
     (`ETICHETTA_GAMBA` sotto) traduce la chiave in un'etichetta leggibile. */
  var ORDINE_GAMBE = ["chi c'e'", 'comfort', 'dispersione', 'consumo', 'buono stato', 'sicurezza'];

  /* Rilievo 8a della review: le intestazioni di gamba erano chiavi grezze
     ("chi c'e' — 95 voci", apostrofo ASCII e minuscola) in una pagina con
     tipografia curata altrove. Stessa idea di `ETICHETTA_GENERE` qui sotto:
     una mappa di sole ETICHETTE, la chiave (`ORDINE_GAMBE`, il payload)
     resta quella che il pavimento dichiara. Una gamba non in questa mappa
     (coda di `raggruppaPerGamba`) mostra comunque il suo nome grezzo, mai
     "undefined". */
  var ETICHETTA_GAMBA = {
    "chi c'e'": 'Chi c’è', comfort: 'Comfort', dispersione: 'Dispersione',
    consumo: 'Consumo', 'buono stato': 'Buono stato', sicurezza: 'Sicurezza'
  };

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
       arrivasse domani non deve leggersi come "pavimento" per un buco qui.
       Rilievo 6b della review: l'etichetta era "Pavimento — non si toglie"
       stampata su tutte le righe (oggi ~88 su 88) -- non distingueva niente,
       e "pavimento" per un utente freddo suona come il pavimento di casa.
       "Di serie" e' la parola nuova; il VALORE interno resta `pavimento`
       (spec, API, codice) -- la spiegazione completa vive ora nella
       descrizione della sezione 01, dove c'e' gia' spazio. */
    if (provenienza === 'pavimento') {
      return { cls: 'badge-off', testo: 'Di serie' };
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
    var etichetta = ETICHETTA_GAMBA[gruppo.gamba] || gruppo.gamba;
    var sommario = el('summary', null,
      etichetta + ' — ' + gruppo.voci.length + (gruppo.voci.length === 1 ? ' voce' : ' voci'));
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
        'Non sto guardando ancora niente. Se HIRIS è appena partito e' +
        ' Home Assistant non ha ancora mandato nessun cambio, è normale — torna fra poco.',
        TONO_QUIETO);
      return;
    }
    raggruppaPerGamba(osservate).forEach(function (g) { rendiGruppoGamba(corpo, g); });
  }

  /* Bottone «Riprova» (rilievo 4): era l'unica pagina di lettura senza,
     mentre l'errore piu' comune -- il riavvio dell'add-on -- e' esattamente
     transitorio. Stesso bottone delle sorelle (memoria-/promesse-/
     costruzioni-route.js): `btn btn-ghost btn-sm`, rilancia `ricarica`. Il
     TESTO dei tre messaggi sotto non cambia (rilievo 4: "il migliore del
     pannello", non si riscrive). */
  function bottoneRiprova(corpo, ricarica) {
    var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
    retry.type = 'button';
    retry.addEventListener('click', ricarica);
    corpo.appendChild(retry);
  }

  function rendiOsservateErrore(corpo, status, ricarica) {
    if (status === 503) {
      riga(corpo,
        'L’osservatore non è disponibile: HIRIS non sta guardando niente in questo momento. ' +
        'Non è una lista vuota — è l’osservatore stesso ad essere fermo (riprova dopo un riavvio dell’add-on).',
        TONO_PROBLEMA);
    } else {
      riga(corpo, 'Non è stato possibile leggere cosa sta guardando l’osservatore. Riprova più tardi.',
        TONO_PROBLEMA);
    }
    bottoneRiprova(corpo, ricarica);
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

  function oggiLocale() { return isoData(new Date()); }

  /* Date sempre in gg/mm/aaaa nel testo (rilievo 5): `giornoIso` arriva dal
     valore di `<input type=date>`, sempre `AAAA-MM-GG` per specifica HTML. */
  function ggMmAaaa(giornoIso) {
    var parti = giornoIso.split('-');
    if (parti.length !== 3) return giornoIso;
    return parti[2] + '/' + parti[1] + '/' + parti[0];
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
    /* «in corso a fine giornata», non «ancora in corso» (cancello-rilascio-
       brief.md, punto 2): l'aggregazione e' per giornata, e un oggetto senza
       fine non e' un oggetto che questo istante sa ancora essere aperto --
       e' un oggetto che NON HA MAI RIVISTO una chiusura da quando la
       giornata in cui e' nato e' stata aggregata. Se l'episodio attraversa
       la mezzanotte, la sua vera fine (se c'e') e' scartata in silenzio
       dall'aggregazione del giorno dopo (spec §6): questa pagina non deve
       promettere una continuita' che il pavimento non tiene. */
    if (fine == null) return 'dalle ' + inizio + ', in corso a fine giornata';
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
    /* Rilievo 8c: «Nascondi» da solo perde il referente quando piu' righe
       sono aperte insieme -- lo stesso principio di "Nascondi i dettagli
       tecnici" in costruzioni-route.js e "Nascondi il dettaglio" in
       promesse-route.js. */
    var testoAperto = 'Nascondi chi c’era intorno';
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

  /* Rilievo 7 della review: la gerarchia era rovesciata -- l'identificatore
     era il testo piu' in evidenza, il fatto («25/08 15:30 → 17:05 · da 18,2
     a 21,0») stava nella classe delle note a margine. L'occhio cerca il
     contrario: il COSA E' SUCCESSO e' il contenuto, l'identificatore e' il
     riferimento -- stessa gerarchia gia' in albero-route.js, il metro. */
  function rigaOggetto(o) {
    var box = el('div');
    box.style.cssText = 'border-top:1px solid var(--border);padding:var(--sp-3) 0;' +
      'display:flex;flex-direction:column;gap:4px';

    var testa = el('div');
    testa.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap';
    testa.appendChild(el('span', 'agent-badge badge-off', ETICHETTA_GENERE[o.genere] || o.genere));
    // Identificatore: monospaziato, piccolo, attenuato -- il riferimento, non
    // il contenuto. `.text-mono`/`.field-hint` portano gia' `overflow-wrap:
    // anywhere` (hiris-config.css) e lo span e' protetto da `.section-card
    // span { min-width: 0 }` (hiris-config.css, rilievo 1): senza, un
    // identificatore da 93 caratteri dentro questa riga flessibile
    // sfonderebbe lo schermo di un telefono.
    testa.appendChild(el('span', 'text-mono field-hint', nomeProtagonista(o)));
    box.appendChild(testa);

    var contenuto = el('p', null, periodo(o) + ' · ' + frasePrincipale(o));
    contenuto.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:0;overflow-wrap:anywhere';
    box.appendChild(contenuto);

    var dettagli = rivelatoreDettagli(o);
    if (dettagli) box.appendChild(dettagli);

    return box;
  }

  function rendiOggetti(corpo, oggetti, giornoFiltro) {
    if (!oggetti.length) {
      if (!giornoFiltro) {
        riga(corpo, 'Non c’è ancora nessun episodio: l’aggregazione notturna gira una volta al giorno, alle 00:20.',
          TONO_QUIETO);
        return;
      }
      /* Rilievo 5: il giorno dell'aggiornamento (e ogni "ieri"/"oggi") e' lo
         STATO NORMALE, non un caso limite -- il messaggio deve dire QUANDO
         tornare, non seminare il dubbio che la casa non abbia fatto niente
         (con ~14.600 cambi al giorno misurati, quasi impossibile). Per un
         giorno piu' vecchio l'ipotesi doppia attuale resta corretta. */
      var dataItaliana = ggMmAaaa(giornoFiltro);
      var testo = (giornoFiltro === oggiLocale() || giornoFiltro === ieriLocale())
        ? 'Nessun episodio per il ' + dataItaliana + '. Non è un errore: gli episodi di ogni giornata ' +
          'vengono scritti la notte successiva, alle 00:20 — nel frattempo guarda «Cosa sto guardando» ' +
          'qui sopra.'
        : 'Nessun episodio per il ' + dataItaliana + '. Non è un errore: quel giorno la casa potrebbe ' +
          'non aver fatto niente di osservabile, oppure l’aggregazione notturna non è ancora passata.';
      riga(corpo, testo, TONO_QUIETO);
      return;
    }
    oggetti.forEach(function (o) { corpo.appendChild(rigaOggetto(o)); });
  }

  function rendiOggettiErrore(corpo, status, ricarica) {
    if (status === 503) {
      riga(corpo,
        'L’archivio degli episodi non è disponibile in questo momento. Non è una lista vuota — è l’archivio stesso ad essere fermo.',
        TONO_PROBLEMA);
    } else {
      riga(corpo, 'Non è stato possibile leggere gli episodi. Riprova più tardi.', TONO_PROBLEMA);
    }
    bottoneRiprova(corpo, ricarica);
  }

  /* ------------------------------------------------------------------------ mount */

  function caricaOsservate(corpo) {
    clearEl(corpo);
    riga(corpo, 'Caricamento…', TONO_QUIETO);
    function ricarica() { return caricaOsservate(corpo); }
    return leggi('api/cervello/osservate').then(function (esito) {
      clearEl(corpo);
      if (!esito.ok) { rendiOsservateErrore(corpo, esito.status, ricarica); return; }
      rendiOsservate(corpo, esito.corpo.osservate || []);
    }, function () {
      clearEl(corpo);
      rendiOsservateErrore(corpo, null, ricarica);
    });
  }

  /* Rilievo 8b: due cambi rapidi di giorno lanciavano due richieste senza
     guardia -- se la piu' lenta arrivava dopo, la pagina mostrava il giorno
     sbagliato. Un contatore di generazione, incrementato ad ogni chiamata:
     solo l'ultima "vince" la resa, qualunque ordine di arrivo prendano le
     risposte. */
  var generazioneOggetti = 0;

  function caricaOggetti(corpo, giorno) {
    var miaGenerazione = ++generazioneOggetti;
    clearEl(corpo);
    riga(corpo, 'Caricamento…', TONO_QUIETO);
    function ricarica() { return caricaOggetti(corpo, giorno); }
    var percorso = 'api/cervello/oggetti' + (giorno ? '?giorno=' + encodeURIComponent(giorno) : '');
    return leggi(percorso).then(function (esito) {
      if (miaGenerazione !== generazioneOggetti) return; // superata da un cambio di giorno più recente
      clearEl(corpo);
      if (!esito.ok) { rendiOggettiErrore(corpo, esito.status, ricarica); return; }
      rendiOggetti(corpo, esito.corpo.oggetti || [], giorno);
    }, function () {
      if (miaGenerazione !== generazioneOggetti) return;
      clearEl(corpo);
      rendiOggettiErrore(corpo, null, ricarica);
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
    var corpoOsservate = sezione(outlet, '01', 'Cosa sto guardando',
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

    var controlli = el('div');
    controlli.style.cssText = 'display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:12px';
    var campoGiorno = el('div');
    var labelGiorno = el('label', 'field-hint', 'Giorno');
    var inputGiorno = el('input');
    inputGiorno.type = 'date';
    // Rilievo 3: l'etichetta era muta -- nessun for/id -- e per un lettore
    // di schermo il campo era una data anonima.
    inputGiorno.id = 'osservatore-giorno';
    labelGiorno.setAttribute('for', inputGiorno.id);
    campoGiorno.appendChild(labelGiorno);
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
