/* HIRIS · Chat page · knowledge queue core — strato di rete senza DOM.

   La ragione della separazione: quando la logica di rete e' cablata sul DOM
   di una pagina, la vista successiva che la riusa aggiorna nodi che da lei
   non esistono e un'operazione RIUSCITA si presenta come "Errore di rete".
   Qui dentro non si tocca nessun nodo: si fa la chiamata e si ritorna
   l'esito; chi rende aggiorna il proprio DOM. (Lo stesso schema lo seguiva
   `config/proposals-core.js`, uscito con la fetta E5 Task 8 insieme al suo
   ultimo chiamante.)

   Vive sotto chat/ perche' oggi l'unica superficie della coda e' il pannello
   Memoria della chat. Se un domani la coda comparisse anche nella pagina di
   configurazione, il file va spostato in config/ e aggiunto al suo <script>:
   non c'e' altro da cambiare, non avendo DOM.

   Contratto: nessuna funzione lancia per un 4xx/5xx — un errore HTTP e' un
   esito, e chiamante lo legge da `ok`/`error`. Solo un fallimento di rete
   vero (fetch reject) resta un'eccezione. */
(function() {
  function _result(r) {
    /* Normalizza in {ok, error, data}. Legge il body JSON best-effort: un
       backend che risponde 503 con un messaggio lo fa arrivare a chi rende,
       ma una risposta senza body non deve far fallire la promise. */
    return r.json().then(
      function(d) { return { ok: r.ok, status: r.status, error: (d && d.error) || null, data: d || {} }; },
      function() { return { ok: r.ok, status: r.status, error: null, data: {} }; }
    );
  }

  /* Elementi della knowledge base salvati e non ancora approvati, cioe' non
     ancora richiamabili dalla ricerca. Ritorna SEMPRE {ok, items, error}: la
     distinzione fra "coda vuota" (ok, items vuoto) e "non ho potuto leggere"
     (ok false) e' il punto di tutta questa superficie e non va persa qui. */
  function listPending() {
    return fetch('api/knowledge/pending').then(_result).then(function(res) {
      return {
        ok: res.ok,
        status: res.status,
        error: res.error,
        items: (res.data && res.data.items) || []
      };
    });
  }

  function approve(id) {
    return fetch('api/knowledge/' + encodeURIComponent(id) + '/approve', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }

  /* Scartare cancella la riga (il backend fa DELETE, non un cambio di stato):
     e' definitivo, e chi rende deve chiederne conferma. */
  function reject(id) {
    return fetch('api/knowledge/' + encodeURIComponent(id) + '/reject', {
      method: 'POST', headers: { 'X-Requested-With': 'fetch' }
    }).then(_result);
  }

  window.HirisKnowledgeCore = {
    listPending: listPending, approve: approve, reject: reject
  };
})();
