/* HIRIS · shared proposals core — DOM-agnostic fetch layer.

   Perché esiste: apply/reject di una proposta vivevano SOLO in
   config/proposals.js, cablati sul DOM di quella pagina (righe #pr-<id>,
   contenitore #proposals-list). La Dashboard riusava quelle funzioni globali
   ma rende card diverse (.prop-card, nessun #pr-<id>, contenitore
   #dash-proposals-body): dopo un apply RIUSCITO, `row` era null -> ramo else
   -> checkEmptyList() -> getElementById('proposals-list') null ->
   null.querySelector -> TypeError -> catch -> alert('Errore di rete').
   Cioè: l'automazione VENIVA attivata, ma appariva un falso errore di rete.

   Questo core fa SOLO la chiamata di rete e ritorna l'esito. Ogni vista
   (pagina Proposte del config, peek della Dashboard, pannello Proposte della
   chat) aggiorna il PROPRIO DOM: nessuna vista eredita il DOM di un'altra,
   quindi quella classe di bug non può più ripresentarsi.

   Caricato come <script src> statico sia in config.html sia in
   static/index.html (la chat), come config/api.js. */
(function() {
  function _result(r) {
    /* Normalizza in {ok, error}. Legge il body JSON best-effort per estrarne
       l'eventuale messaggio d'errore del backend senza mai far lanciare la
       promise: un 4xx/5xx è un esito, non un'eccezione. Solo un fallimento di
       RETE reale (fetch reject) resta un'eccezione, gestita dal chiamante. */
    return r.json().then(
      function(d) { return { ok: r.ok, error: (d && d.error) || null, data: d || {} }; },
      function() { return { ok: r.ok, error: null, data: {} }; }
    );
  }

  function list(status) {
    var url = 'api/proposals' + (status ? '?status=' + encodeURIComponent(status) : '');
    return fetch(url).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) { return (d && d.proposals) || []; });
  }

  function apply(id) {
    return fetch('api/proposals/' + encodeURIComponent(id) + '/apply', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }

  function reject(id) {
    return fetch('api/proposals/' + encodeURIComponent(id) + '/reject', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }

  /* Quali plance hanno uno snapshot ripristinabile, e da quando: metadati
     {url_path, saved_at, count}, dal più recente al più vecchio. È da QUI che
     ogni vista deriva l'affordance di ripristino, non dalla propria memoria:
     una sostituzione approvata in un'altra schermata deve restare annullabile,
     e un refresh del browser non deve farla sparire. Come `list`: la vista
     riceve dati grezzi e decide da sé cosa mostrarne. */
  function listDashboardBackups() {
    return fetch('api/dashboards/backups').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) { return (d && d.backups) || []; });
  }

  /* Ripristina l'ultimo snapshot di una plancia (url_path), cioè annulla una
     proposta `mode: replace` appena applicata. Come apply/reject: nessun DOM,
     solo la chiamata e l'esito normalizzato. */
  function restoreDashboard(urlPath) {
    return fetch('api/dashboards/' + encodeURIComponent(urlPath) + '/restore', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }

  window.HirisProposalsCore = {
    list: list, apply: apply, reject: reject,
    listDashboardBackups: listDashboardBackups, restoreDashboard: restoreDashboard
  };
})();
