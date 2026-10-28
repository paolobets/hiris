/* HIRIS · Configurazione · «L'osservatore» / scheda «Cosa fare» (spec
   2026-09-18 §4B).

   Le osservazioni dell'analista: cosa ha visto, perche' lo dice, se e'
   spiegato, cosa cambierebbe. E' l'unica scheda che chiede un'AZIONE, ed e' la
   ragione per cui ha una scheda sua invece di stare in fondo a una colonna
   (spec §0, decisione 10).

   L'analisi e' di OGGI, non di ieri: legge i resoconti fino a ieri e parla
   adesso. Il selettore del giorno della scheda «Il giorno» governa il
   resoconto, non lei.

   Sicurezza: testi via textContent/createElement, MAI innerHTML su dati del
   server. */
window.HirisWatcherCosaFare = (function () {
  'use strict';

  var S = HirisWatcherShared;
  var line = pageLine;
  var read = S.read;
  var retryButton = S.retryButton;
  var fmtCount = S.fmtCount;
  var fmtPercent = S.fmtPercent;
  var fmtDuration = S.fmtDuration;

  /* Cosa il proponente ha fatto di questa osservazione (attori, strato 4,
     Task 4.6).

     **L'esito arriva gia' attaccato dalla rotta** (`mind/view._with_outcomes`):
     e' il server a sapere quale esito risponde a quale domanda (la regola
     dell'impronta), e rifarla qui sarebbe il secondo posto in cui si decide
     chi risponde a chi.

     Tre esiti, tre frasi. Le proposte vivono nel loro archivio: qui c'e' il
     rimando, non la copia. Solo «niente» porta un testo, il suo perche', che
     non vive altrove. Senza esito non si dice niente: il proponente non ha
     ancora risposto, e il giro dopo la richiede. */
  var PROPONENTE_FRASE = {
    costruita: 'Ho proposto una modifica che HIRIS può fare: la trovi in Proposte.',
    a_mano: 'Ho proposto una cosa da fare a mano: la trovi in Proposte.',
    niente: 'Ho guardato e non c’è niente da proporre: '
  };

  function rigaProponente(riga, o) {
    var esito = o && o.esito;
    var frase = esito && PROPONENTE_FRASE[esito.esito];
    if (!frase) return;
    if (esito.esito === 'niente') frase += (esito.perche || '');
    riga.appendChild(el('div', 'sc-row-why', frase));
  }

  /* **Lo stato di adesso accanto a cio' che l'analista ha scritto** (rimedio
     B.2 del 23/10/2026, in pagina dalla Fase B del 28/10/2026). La rotta
     manda gia' `adesso`, una riga `corta` per soggetto (`MindView._now_of`,
     la stessa di `search`): chi legge confronta da se' cio' che fu detto con
     cio' che e', senza aprire un'altra pagina. Un'osservazione scritta prima
     dei `soggetti` non porta `adesso`, e non si inventa.

     Il disegno e' di ux-ui-specialist (28/10/2026): «adesso» invecchia,
     perche' la pagina non si rilegge da sola, quindi porta l'ora della
     lettura; un soggetto che Home Assistant non ha negli stati (`stato:
     null`) si dice, non sparisce; oltre tre soggetti il resto sta dietro un
     bottone, perche' la riga dell'osservazione resti leggibile. */
  var ADESSO_SHOWN = 3;

  function testoAdesso(e, ora) {
    var stato = e.stato === null ? 'senza stato in Home Assistant' : entityStateText(e);
    return 'Adesso' + (ora ? ' (' + ora + ')' : '') + ': ' + (e.nome || e.id) +
      (stato ? ' · ' + stato : '');
  }

  function rigaAdesso(riga, o, orologio) {
    var righe = ((o && o.adesso) || []).filter(Boolean);
    if (!righe.length) return;
    var ora = orologio && orologio.adesso ? fmtHour(orologio.adesso) : '';
    righe.slice(0, ADESSO_SHOWN).forEach(function (e) {
      riga.appendChild(el('div', 'field-hint', testoAdesso(e, ora)));
    });
    var altri = righe.slice(ADESSO_SHOWN);
    if (!altri.length) return;
    riga.appendChild(S.createDisclosure('Gli altri ' + fmtCount(altri.length), 'Chiudi',
      function (panel) {
        altri.forEach(function (e) { panel.appendChild(el('div', 'field-hint', testoAdesso(e, ora))); });
      }));
  }

  /* **La domanda e la risposta, ognuna sulla sua riga** (Fase B,
     28/10/2026). L'innesco a parole lo manda la rotta (`innesco_parole`,
     `mind/analyst.TRIGGER_WORDS`, C-11) ed e' la DOMANDA che il codice ha
     fatto; `spiegato` e' la RISPOSTA dell'analista. Messe in fila sulla
     stessa riga dicevano «è cambiato, e non è spiegato. È spiegato: …»
     (fotografia della Fase L, frase (b)). **Cio' che e' spiegato si
     distingue da cio' che non lo e'**: e' la differenza fra una scoperta e
     una conferma, e la spec la chiede; `null` vuol dire «non lo so», e si
     dice -- in peso pieno e senza colore, perche' il colore dell'ignoto
     (`TONE_UNKNOWN`) in questa pagina vuol dire un'altra cosa (ux-ui-specialist).

     Della spiegazione si vede la prima frase; il resto e «Cosa cambierebbe»
     stanno dietro «Tutta la spiegazione». */
  function rigaSpiegazione(riga, o) {
    if (o.innesco_parole) {
      riga.appendChild(el('div', 'sc-row-why', 'Perché l’ho guardata: ' + closeSentence(o.innesco_parole)));
    }
    if (!o.spiegato) {
      var ignoto = el('div', 'sc-row-why', 'Non so ancora spiegarlo.');
      ignoto.style.fontWeight = '500';
      riga.appendChild(ignoto);
    }
    var tutta = o.spiegato ? closeSentence(o.spiegato) : '';
    var prima = tutta ? S.firstSentenceTruncated(tutta, Infinity) : '';
    if (prima) riga.appendChild(el('div', 'sc-row-why', 'Si spiega con: ' + prima));
    var resto = tutta.slice(prima.length).trim();
    var cambierebbe = o.cosa_cambierebbe ? 'Cosa cambierebbe: ' + closeSentence(o.cosa_cambierebbe) : '';
    if (!resto && !cambierebbe) return;
    riga.appendChild(S.createDisclosure('Tutta la spiegazione', 'Chiudi', function (panel) {
      if (resto) panel.appendChild(el('div', 'sc-row-why', resto));
      if (cambierebbe) panel.appendChild(el('div', 'sc-row-why', cambierebbe));
    }));
  }

  function renderAnalysis(body, analysis, orologio) {
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
      /* La novita' a parole la manda la rotta (`novita_parole`, da
         `analyst.NOVELTY_WORDS`): la pagina non ne tiene una tabella. Una
         osservazione gia' detta con la stessa prova non arriva nemmeno (Fase
         B, 28/10/2026: il campo c'era e nessuno lo mostrava). Su una riga sua
         e non in un badge, che non va a capo e sul telefono uscirebbe dallo
         schermo (ux-ui-specialist). */
      if (o.novita_parole) riga.appendChild(el('div', 'field-hint', stateLabel(closeSentence(o.novita_parole))));

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
      rigaAdesso(riga, o, orologio);

      riga.appendChild(el('div', 'sc-row-why', o.cosa || ''));
      rigaSpiegazione(riga, o);
      rigaProponente(riga, o);
      body.appendChild(riga);
    });
  }

  function renderAnalysisError(body, status, reload, corpo) {
    if (status === 404) {
      /* «Non ho guardato» non e' «ho guardato e non c'era niente»: la prima
         e' questa, la seconda e' un elenco vuoto. Ogni quanto gira lo dice
         il server (`analista_ogni_s`, C-11): la pagina non lo ricopia. */
      var ogni = (corpo || {}).analista_ogni_s;
      var quando = ogni === 3600 ? 'ogni ora' : (ogni ? 'ogni ' + fmtDuration(ogni) : null);
      line(body, 'L’analista non ha ancora guardato questo giorno.' +
        (quando ? ' Gira ' + quando + ', e un giorno ha una analisi sola.' :
          ' Un giorno ha una analisi sola.'), TONE_CALM);
      return;
    }
    line(body, 'Non è stato possibile leggere l’analisi. Riprova più tardi.', TONE_PROBLEM);
    retryButton(body, reload);
  }

  function carica(corpo, day) {
    clearEl(corpo);
    line(corpo, 'Caricamento…', TONE_CALM);
    function reload() { return carica(corpo, day); }
    /* «Oggi» si chiede PER NOME, e lo risolve il server nel fuso della casa
       (C-17, passo 5): fino al 14/10/2026 era l'oggi del browser. La promessa
       si risolve con l'orologio della risposta, per il «Letto alle». */
    return read('api/mind/analysis?day=' + encodeURIComponent(day || 'oggi')).then(function (occurrence) {
      clearEl(corpo);
      var risposta = occurrence.corpo || {};
      if (!occurrence.ok) { renderAnalysisError(corpo, occurrence.status, reload, risposta); return risposta.orologio; }
      renderAnalysis(corpo, risposta.analisi || {}, risposta.orologio);
      return risposta.orologio;
    }, function () {
      clearEl(corpo);
      renderAnalysisError(corpo, null, reload);
    });
  }

  return {
    carica: carica,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiAnalisi: renderAnalysis
  };
})();
