/* HIRIS · Config · usage route mount (Phase 9) */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* `formatTokens` viveva qui e arrotondava i milioni a un decimale mentre
     `fmtNum` (config/api.js), che serve il riquadro della chat, ne usa due:
     lo stesso numero appariva come `1.3M` di qua e `1.28M` di la'. La copia
     locale e' uscita, restano le funzioni condivise -- api.js e' gia' il posto
     delle utilita' comuni e questa pagina lo carica gia'. */

  function mount() {
    var outlet = document.getElementById('route-outlet');
    outlet.innerHTML =
      '<div class="page-title">Consumi globali</div>' +
      '<p class="page-subtitle">Token e costi complessivi, aggregati dall\'avvio o dall\'ultimo reset. ' +
        'Il dettaglio per singolo assistente non esiste più: HIRIS ha una chat sola, senza id.</p>' +
      '<div class="stat-grid" id="usage-global-grid">' +
        '<div class="stat-tile"><div class="st-label">Richieste</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token IN</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token OUT</div><div class="st-value">—</div></div>' +
        '<div class="stat-tile"><div class="st-label">Costo</div><div class="st-value">—</div></div>' +
      '</div>' +
      '<div style="margin-top:24px;display:flex;gap:8px" id="usage-azioni">' +
        '<button class="btn btn-danger" id="usage-reset-global">↺ Azzera contatori globali</button>' +
      '</div>';

    /* Global usage */
    fetch('api/usage').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(u) {
      var grid = document.getElementById('usage-global-grid');
      if (!grid) return;
      /* Il server DICHIARA che su questa configurazione i consumi non si
         misurano (200 con `misurata: false`, vedi api/handlers_usage.py).
         Prima questo caso arrivava qui come 503 e finiva nel `catch` in
         fondo, insieme ai guasti di rete: la pagina diceva soltanto «Errore
         caricamento consumi.» su una configurazione perfettamente sana --
         ed era una delle sei pagine superstiti, ridotta a un vicolo cieco
         proprio sul percorso piu' comune (abbonamento acceso, nessuna
         chiave API). Ora dice la cosa vera, con le parole del server, e
         toglie di mezzo il pulsante di azzeramento: non c'e' nessun
         contatore da azzerare. */
      if (u.misurata === false) {
        grid.innerHTML = '';
        grid.style.display = 'none';
        var avviso = document.createElement('p');
        avviso.className = 'page-subtitle';
        /* `--warn-ink`, non `--warn`: e' testo, e questa e' la frase che
           spiega perche' non ci sono numeri. */
        avviso.style.cssText = 'color:var(--warn-ink)';
        avviso.textContent = u.messaggio || 'I consumi non si misurano su questa configurazione.';
        grid.parentNode.insertBefore(avviso, grid);
        var azioni = document.getElementById('usage-azioni');
        if (azioni) azioni.style.display = 'none';
        return;
      }
      grid.style.display = '';
      var tin = u.total_input_tokens || u.input_tokens || 0;
      var tout = u.total_output_tokens || u.output_tokens || 0;
      var cost = u.total_cost_eur || u.cost_eur || 0;
      var req = u.total_requests || u.requests || 0;
      var lastReset = fmtDataOra(u.last_reset || u.reset_at);
      grid.innerHTML =
        '<div class="stat-tile"><div class="st-label">Richieste</div><div class="st-value">' + req + '</div><div class="st-delta">' + (lastReset ? 'da ' + escHtml(lastReset) : '') + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token IN</div><div class="st-value">' + fmtNum(tin) + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Token OUT</div><div class="st-value">' + fmtNum(tout) + '</div></div>' +
        '<div class="stat-tile"><div class="st-label">Costo</div><div class="st-value">' + fmtEuro(cost) + '</div></div>';
    }).catch(function(err) {
      console.error('usage global fetch failed', err);
      var grid = document.getElementById('usage-global-grid');
      if (grid) grid.innerHTML = '<div class="proposals-error" style="grid-column:1/-1">Errore caricamento consumi.</div>';
    });

    /* fetta E5 Task 7 ("Consumi e Modelli smettono di mentire"): la tabella
       "Per Chatbot" esce -- non era una rotta morta (GET api/chatbots
       rispondeva ancora, prima di uscire per intero alla fetta E5 Task 10),
       ma mentiva per omissione: i campi usage/budget_limit_eur/
       _rate_limit_paused che leggeva non esistevano piu' nel payload
       (handlers_chatbots.handle_list_chatbots, dalla E4 Task 4 "un bot
       solo") e degradavano tutti a zero -- sembrava un consumo azzerato, era
       un consumo mai misurato per-entita'. Il sottotitolo qui sopra lo
       dichiara invece di lasciarlo sparire in silenzio. */

    /* Reset button */
    var resetBtn = document.getElementById('usage-reset-global');
    if (resetBtn) {
      resetBtn.addEventListener('click', function() {
        if (!confirm('Azzerare tutti i contatori globali? L\'operazione è irreversibile.')) return;
        fetch('api/usage/reset', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
          .then(function(r) { if (r.ok) mount(); else alert('Errore reset'); })
          .catch(function() { alert('Errore di rete'); });
      });
    }
  }

  window.HirisUsageRoute = { mount: mount };
})();
