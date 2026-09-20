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
  var el = S.el;
  var clearEl = S.clearEl;
  var line = S.line;
  var read = S.read;
  var retryButton = S.retryButton;
  var fmtCount = S.fmtCount;
  var fmtPercent = S.fmtPercent;
  var localOggi = S.localOggi;
  var TONE_PROBLEM = S.TONE_PROBLEM;
  var TONE_CALM = S.TONE_CALM;

  /* I tre inneschi, **a parole**. «1» non vuol dire niente per chi legge: la
     spec da' a ciascuno un nome, ed e' quello che va in pagina. Vivono qui in
     un posto solo perche' il numero arriva dal modello e la parola e' nostra:
     due elenchi divergerebbero al primo ritocco. */
  var TRIGGER_WORDS = {
    1: 'è cambiato, e non è spiegato',
    2: 'è stabile e costa',
    3: 'non c’è più',
  };

  function renderAnalysis(body, analysis) {
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

      riga.appendChild(el('div', 'sc-row-why', o.cosa || ''));

      var coda = [];
      var parola = TRIGGER_WORDS[o.innesco];
      if (parola) coda.push('Perché lo dice: ' + parola + '.');
      /* **Cio' che e' spiegato si distingue da cio' che non lo e'**: e' la
         differenza fra una scoperta e una conferma, e la spec la chiede. */
      if (o.spiegato) coda.push('È spiegato: ' + o.spiegato + '.');
      if (o.cosa_cambierebbe) coda.push('Cosa cambierebbe: ' + o.cosa_cambierebbe);
      if (coda.length) riga.appendChild(el('div', 'sc-row-why', coda.join(' ')));
      body.appendChild(riga);
    });
  }

  function renderAnalysisError(body, status, reload) {
    if (status === 404) {
      /* «Non ho guardato» non e' «ho guardato e non c'era niente»: la prima
         e' questa, la seconda e' un elenco vuoto. */
      line(body, 'L’analista non ha ancora guardato questo giorno. Gira una volta ' +
        'all’ora, e un giorno ha una analisi sola.', TONE_CALM);
      return;
    }
    line(body, 'Non è stato possibile leggere l’analisi. Riprova più tardi.', TONE_PROBLEM);
    retryButton(body, reload);
  }

  function carica(corpo, day) {
    clearEl(corpo);
    line(corpo, 'Caricamento…', TONE_CALM);
    function reload() { return carica(corpo, day); }
    var giorno = day || localOggi();
    return read('api/mind/analysis?day=' + encodeURIComponent(giorno)).then(function (occurrence) {
      clearEl(corpo);
      if (!occurrence.ok) { renderAnalysisError(corpo, occurrence.status, reload); return; }
      renderAnalysis(corpo, occurrence.corpo.analisi || {});
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
