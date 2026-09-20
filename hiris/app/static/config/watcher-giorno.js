/* HIRIS · Configurazione · «L'osservatore» / scheda «Il giorno» (spec
   2026-09-18 §4A).

   *Com'e' andata la casa?* Il resoconto di UN giorno: le misure, cio' che non
   si e' potuto misurare e perche', le forme, la cronaca.

   -- Il giorno --
   L'aggregazione notturna scrive «ieri» alle 00:20 (`server.py::
   _aggrega_ieri`): il giorno di oggi, quasi sempre, non ha ancora un
   resoconto. Il selettore nasce su ieri, calcolato nel fuso del BROWSER e
   non in quello della casa -- i due possono differire di un GIORNO intero
   (non "un'ora", cifra non misurata) vicino alla mezzanotte, se si guarda da
   un fuso diverso; nel caso reale, casa e utente nello stesso fuso, l'errore
   e' zero a qualunque ora.

   Il selettore vive FUORI dal corpo che ogni lettura ripulisce: e' della
   scheda, non del resoconto -- altrimenti il giorno scelto sparirebbe ad ogni
   «Aggiorna», che e' esattamente lo stato che la spec §2 promette di non
   perdere.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server. */
window.HirisWatcherGiorno = (function () {
  'use strict';

  var S = HirisWatcherShared;
  var el = S.el;
  var clearEl = S.clearEl;
  var line = S.line;
  var subheading = S.subheading;
  var read = S.read;
  var retryButton = S.retryButton;
  var describeWatchedSubject = S.describeWatchedSubject;
  var ggMmAaaa = S.ggMmAaaa;
  var ieriLocale = S.ieriLocale;
  var fmtTime = S.fmtTime;
  var fmtCount = S.fmtCount;
  var fmtPercent = S.fmtPercent;
  var TONE_PROBLEM = S.TONE_PROBLEM;
  var TONE_CALM = S.TONE_CALM;
  var SUBJECT_IS_ID = S.SUBJECT_IS_ID;

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
    /* **Il giorno si DICE.** La scheda mostra sempre UN giorno solo, ma il
       selettore lo cambia: senza la data scritta qui, chi lo ha appena
       cambiato leggerebbe dei numeri senza sapere a quando si riferiscono. */
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
       si chiede quando serve. La parte compare solo se c'e' qualcosa: un
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
       DICHIARA, con la stessa etichetta della scheda «L'osservatore», invece
       di spacciare un `entity_id` nudo per un nome. */
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

  /* La banda della scheda: il selettore del giorno, costruito UNA volta sola.
     Si riconosce da cio' che c'e' gia' nel DOM invece che da una variabile di
     modulo, perche' la stessa scheda puo' essere montata su un corpo diverso
     (un'altra corsa di prova, un guscio ricostruito) e una variabile di
     modulo continuerebbe a puntare al pannello di prima. */
  function bandaDi(corpo) {
    var esistente = corpo.querySelector('#watcher-giorno-corpo');
    if (esistente) {
      return { campo: corpo.querySelector('#watcher-day'), resoconto: esistente };
    }
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
    corpo.appendChild(controls);

    /* Un id e non una classe: e' un appiglio per ritrovare il corpo, non una
       cosa da vestire -- il cancello `tests/test_css_classes.py` chiede che
       ogni classe scritta dal frontend abbia una regola in un foglio, e una
       regola vuota scritta per zittirlo sarebbe il cancello aggirato. */
    var resoconto = el('div');
    resoconto.id = 'watcher-giorno-corpo';
    corpo.appendChild(resoconto);

    dayInput.addEventListener('change', function () {
      loadReport(resoconto, dayInput.value || null);
    });
    return { campo: dayInput, resoconto: resoconto };
  }

  /* `giorno` (facoltativo) e' il giorno da mostrare: quando manca, vince
     quello gia' scelto nel selettore -- cosi' «Aggiorna» rilegge il giorno
     che si sta guardando, non ieri. */
  function carica(corpo, giorno) {
    var banda = bandaDi(corpo);
    if (giorno) banda.campo.value = giorno;
    return loadReport(banda.resoconto, banda.campo.value || null);
  }

  return {
    carica: carica,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiResoconto: renderReport,
    _rendiBanda: bandaDi
  };
})();
