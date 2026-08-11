/* HIRIS · shared proposals core — DOM-agnostic fetch layer.

   Perché esiste: apply/reject di una proposta vivevano SOLO in
   config/proposals.js, cablati sul DOM di quella pagina (righe #pr-<id>,
   contenitore #proposals-list). La Dashboard riusava quelle funzioni globali
   ma rende card diverse (.prop-card, nessun #pr-<id>, contenitore
   #dash-proposals-body): dopo un apply RIUSCITO, `row` era null -> ramo else
   -> checkEmptyList() -> getElementById('proposals-list') null ->
   null.querySelector -> TypeError -> catch -> alert('Errore di rete').
   Cioè: l'automazione VENIVA attivata, ma appariva un falso errore di rete.

   Questo core fa SOLO la chiamata di rete e ritorna l'esito: ogni vista
   aggiorna il PROPRIO DOM, senza ereditare quello di un'altra.

   Stato alla fetta E5 Task 6: delle tre viste ne resta UNA, il peek della
   Dashboard (config/dashboard.js) -- la pagina Proposte del config e il
   pannello Proposte della chat sono uscite con /api/proposals*. Il file
   sopravvive percio' solo finche' sopravvive quel peek, che il Task 8
   riscrive. Caricato come <script src> statico da config.html soltanto. */
(function() {
  function _result(r) {
    /* Normalizza in {ok, error, status}. Legge il body JSON best-effort per
       estrarne l'eventuale messaggio d'errore del backend senza mai far
       lanciare la promise: un 4xx/5xx è un esito, non un'eccezione. Solo un
       fallimento di RETE reale (fetch reject) resta un'eccezione, gestita
       dal chiamante. `status` è sempre presente (anche quando il corpo non è
       JSON): è quello che errorMessage() usa per dire qualcosa quando
       `error` manca. */
    return r.json().then(
      function(d) { return { ok: r.ok, error: (d && d.error) || null, status: r.status, data: d || {} }; },
      function() { return { ok: r.ok, error: null, status: r.status, data: {} }; }
    );
  }

  /* I-5 (review indipendente su bee3ab1): ogni chiamante di apply/reject/
     restoreDashboard mostrava `res.error || 'Errore'` direttamente
     all'utente -- la stringa tecnica del backend (handlers_proposals.py /
     handlers_dashboards.py), non un testo italiano derivato dallo stato:
     "ProposalStore not initialized", "Proposal not found or not in pending
     state", "Automazione non creata in HA: <eccezione HA grezza>". Stesso
     principio di chat/knowledge.js::messaggioErrore, qui condiviso in UN
     punto perche' i chiamanti di allora (chat/proposals.js,
     config/proposals.js, config/dashboard.js) userebbero altrimenti una
     copia a testa della stessa mappa, a rischio di deriva. Oggi ne resta
     uno solo, config/dashboard.js.
     Quando lo stato non rientra in nessuno dei casi noti (un guasto non-
     JSON, un proxy che risponde con un HTML di errore, ...) si mostra
     comunque il codice HTTP: "Errore 502" e "Errore 404" mandano l'utente in
     due direzioni diverse, "Errore" e basta no -- ed e' esattamente cio' che
     rendeva illeggibile un guasto reale in produzione. */
  function errorMessage(res) {
    var status = res && res.status;
    if (status === 409) {
      return 'Non è più valida: probabilmente è già stata gestita altrove. Ricarica per vedere lo stato aggiornato.';
    }
    if (status === 404) {
      return 'Non trovato: probabilmente non è (più) disponibile.';
    }
    if (status === 503) {
      return 'Il servizio non è disponibile in questo momento. Riprova più tardi.';
    }
    if (status === 502) {
      return 'Home Assistant ha rifiutato l’operazione. Riprova più tardi o controlla la configurazione in HA.';
    }
    if (status === 400) {
      return 'La configurazione proposta non è valida.';
    }
    return 'Operazione non riuscita' + (status ? ' (errore ' + status + ')' : '') + '.';
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
    listDashboardBackups: listDashboardBackups, restoreDashboard: restoreDashboard,
    errorMessage: errorMessage
  };
})();
