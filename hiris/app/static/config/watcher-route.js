/* HIRIS · Configurazione · «L'osservatore» — il guscio delle quattro schede.

   Spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md` §2. Nasce da una
   richiesta del proprietario: «e' troppo lunga, densa di informazioni non
   strutturate, e riporta anche elementi con errori». Sono TRE mestieri --
   come sta la casa, cosa ha capito, come sta lavorando -- piu' l'unico che
   chiede un'azione, e stavano a forza in una pagina sola: misurato il
   18/09/2026, oltre 110 KB scaricati e piu' di 500 righe disegnate in una
   colonna, con tutto cio' che chiede qualcosa all'utente in fondo.

   Qui dentro non si legge NESSUN dato: il guscio tiene le schede, i quattro
   pannelli, la freschezza e il carico pigro. Ogni scheda legge i suoi dati
   alla PRIMA apertura, mai prima (decisione 7): aprire «Il giorno» non deve
   scaricare gli 86 KB dell'osservatore.

   Chi disegna cosa vive accanto al suo mestiere: `config/watcher-giorno.js`,
   `config/watcher-cosa-fare.js`, `config/watcher-sapere.js`,
   `config/watcher-lavoro.js`, e cio' che tutte e quattro condividono in
   `config/watcher-shared.js`. */
window.HirisWatcherRoute = (function () {
  'use strict';

  var S = HirisWatcherShared;

  /* Le quattro schede, nell'ordine in cui si leggono. Le etichette sono NUDE:
     un contatore obbligherebbe a caricare tutte e quattro le schede all'avvio,
     contro la decisione 7 (spec §2).

     `modulo` e' il NOME del namespace, non il namespace: si risolve al momento
     dell'apertura, cosi' uno script che non ha caricato si dice invece di
     esplodere al montaggio (vedi `carica`). Che quel nome esista davvero lo
     sorveglia `scripts/sponde_js.py` -- dichiarato in `.oxlintrc.json`, e il
     cancello verifica che qualcuno in `static/` lo produca ancora. */
  var SCHEDE = [
    { nome: 'giorno', etichetta: 'Il giorno', modulo: 'HirisWatcherGiorno' },
    { nome: 'cosa-fare', etichetta: 'Cosa fare', modulo: 'HirisWatcherCosaFare' },
    { nome: 'sapere', etichetta: 'Cosa ho capito', modulo: 'HirisWatcherSapere' },
    { nome: 'lavoro', etichetta: 'L’osservatore', modulo: 'HirisWatcherLavoro' }
  ];

  var stato = null;

  function indirizzoDi(nome) { return '#/watcher/' + nome; }

  function nomeValido(nome) {
    for (var i = 0; i < SCHEDE.length; i++) if (SCHEDE[i].nome === nome) return nome;
    return SCHEDE[0].nome;
  }

  /* `#/watcher` nudo -> `#/watcher/giorno` SENZA una voce di cronologia in
     piu': `replaceState`, lo stesso meccanismo e la stessa ragione di
     `correggiHashDiPrima` (config/router.js) -- assegnare l'hash aggiungerebbe
     una voce, e «indietro» rimanderebbe avanti, cioe' nessuno potrebbe piu'
     tornare indietro. Il ripiego assegna l'hash: il `hashchange` che ne segue
     rimonta questa stessa scheda, e il guscio non si ricostruisce. */
  function correggiIndirizzo(nome) {
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', indirizzoDi(nome));
    } else {
      window.location.hash = indirizzoDi(nome);
    }
  }

  /* Il carico pigro (spec §2, cancello 2): una scheda legge i suoi dati alla
     PRIMA apertura e mai piu', finche' qualcuno non preme «Aggiorna»
     (`forza`). E' la ragione per cui i pannelli non si ricostruiscono al
     cambio scheda: ricostruirli vorrebbe dire rileggerli. */
  function carica(scheda, forza) {
    if (scheda.caricata && !forza) return;
    var modulo = window[scheda.def.modulo];
    if (!modulo) {
      /* Il degrado dichiarato: lo script della scheda non ha caricato. Si dice,
         invece di lasciare un pannello vuoto che sembra «non c'e' niente». */
      S.clearEl(scheda.corpo);
      S.line(scheda.corpo, 'Questa scheda non ha caricato. Ricarica la pagina; ' +
        'se non basta, l’aggiornamento dell’add-on è a metà.', S.TONE_PROBLEM);
      return;
    }
    scheda.caricata = true;
    var esito = modulo.carica(scheda.corpo);
    function segna() { scheda.fresca.segna(); }
    if (esito && typeof esito.then === 'function') esito.then(segna, segna);
    else segna();
  }

  function mostra(nome) {
    var scelta = null;
    stato.schede.forEach(function (s) {
      var attiva = s.def.nome === nome;
      s.tab.setAttribute('aria-selected', attiva ? 'true' : 'false');
      /* Un solo bersaglio nella sequenza di tabulazione, le frecce per gli
         altri: e' la semantica `tablist`, non un elenco di bottoni. */
      s.tab.tabIndex = attiva ? 0 : -1;
      /* **Il pannello si nasconde, non si smonta**: `hidden` e basta, cosi' lo
         stato di dentro -- elenchi aperti, giorno scelto, posizione -- e' li'
         quando la scheda torna (spec §2). Ed e' `hidden` e non una classe
         perche' e' la stessa parola che legge chi non vede la pagina: un
         pannello nascosto esce dall'albero di accessibilita' invece di restarci
         trasparente. */
      s.pannello.hidden = !attiva;
      if (attiva) scelta = s;
    });
    if (scelta) carica(scelta);
    return scelta;
  }

  function frecce(ev) {
    var indice = -1;
    for (var i = 0; i < stato.schede.length; i++) {
      if (stato.schede[i].tab.getAttribute('aria-selected') === 'true') indice = i;
    }
    if (indice === -1) return;
    var vai = null;
    if (ev.key === 'ArrowRight') vai = (indice + 1) % stato.schede.length;
    else if (ev.key === 'ArrowLeft') vai = (indice - 1 + stato.schede.length) % stato.schede.length;
    else if (ev.key === 'Home') vai = 0;
    else if (ev.key === 'End') vai = stato.schede.length - 1;
    if (vai === null) return;
    ev.preventDefault();
    HirisRouter.navigate(indirizzoDi(stato.schede[vai].def.nome));
    stato.schede[vai].tab.focus();
  }

  function costruisci(outlet) {
    S.clearEl(outlet);
    outlet.appendChild(S.el('h1', 'page-title', 'L’osservatore'));
    outlet.appendChild(S.el('p', 'page-subtitle',
      'Guarda la casa, ne ricava misure, e dice cosa si potrebbe fare. ' +
      'Non tocca niente: decidi tu.'));

    var tablist = S.el('div', 'watcher-tabs');
    tablist.setAttribute('role', 'tablist');
    tablist.setAttribute('aria-label', 'Le quattro schede dell’osservatore');
    tablist.addEventListener('keydown', frecce);
    outlet.appendChild(tablist);

    var schede = SCHEDE.map(function (def) {
      var tab = S.el('button', 'watcher-tab', def.etichetta);
      tab.type = 'button';
      tab.id = 'watcher-tab-' + def.nome;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', 'false');
      tab.setAttribute('aria-controls', 'watcher-panel-' + def.nome);
      tab.tabIndex = -1;
      /* Il clic LASCIA una voce di cronologia (spec §2): «indietro» torna alla
         scheda di prima, e un segnalibro riapre la scheda giusta. */
      tab.addEventListener('click', function () { HirisRouter.navigate(indirizzoDi(def.nome)); });
      tablist.appendChild(tab);

      /* Il pannello E' una `.section-card`, e non per abitudine: hiris-config.css
         porta 29 regole discendenti da `.section-card` -- `.sc-body` a colonna,
         `.sc-row`, tutta la griglia `.jr-*` dei giudizi, e il `min-width: 0` su
         ogni `span` che impedisce a un identificatore di 93 caratteri di
         sfondare un telefono («Terza recidiva»). Le sezioni numerate escono e
         le schede prendono il loro posto: senza questa classe quelle 29 regole
         smetterebbero di applicarsi tutte insieme, e sarebbe un difetto
         invisibile in una prova di resa e visibile solo sulla pagina vera.
         `watcher-panel` resta la classe di QUESTA fetta, per cio' che e' suo. */
      var pannello = S.el('div', 'section-card watcher-panel');
      pannello.id = 'watcher-panel-' + def.nome;
      pannello.setAttribute('role', 'tabpanel');
      pannello.setAttribute('aria-labelledby', tab.id);
      pannello.tabIndex = 0;
      pannello.hidden = true;
      outlet.appendChild(pannello);

      var scheda = { def: def, tab: tab, pannello: pannello, corpo: null,
                     caricata: false, fresca: null };
      scheda.fresca = S.intestazioneFresca(pannello, function () { carica(scheda, true); });
      scheda.corpo = S.el('div', 'sc-body');
      pannello.appendChild(scheda.corpo);
      return scheda;
    });
    return { outlet: outlet, tablist: tablist, schede: schede };
  }

  /* `scheda` arriva dall'indirizzo (config/main.js). **Non si ricostruisce
     niente se i pannelli sono gia' li'**: cambiare scheda toglie `hidden` a uno
     e lo da' agli altri, e lo stato -- elenchi aperti, giorno scelto, posizione
     -- sopravvive (spec §2). */
  function mount(scheda) {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    var nome = nomeValido(scheda);
    if (!scheda) correggiIndirizzo(nome);
    if (!stato || stato.outlet !== outlet || !outlet.contains(stato.tablist)) {
      stato = costruisci(outlet);
    }
    mostra(nome);
  }

  return { mount: mount, _schede: SCHEDE, _mostra: mostra };
})();
