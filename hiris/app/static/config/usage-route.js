/* HIRIS - Config - la pagina Consumi.
 *
 * Fetta «i consumi, per modello» (22/08/2026). Prima mostrava quattro numeri,
 * la somma di tutto: non si poteva sapere quale modello avesse consumato che
 * cosa, ne' quale provider -- benche' la separazione per provider esistesse
 * gia' nei dati e venisse buttata via nella somma.
 *
 * Disegno fatto con `ux-ui-specialist` PRIMA di scrivere. Le tre regole che
 * ne sono uscite, e che questo file esiste per rispettare:
 *
 * 1. I CINQUE STATI DEL COSTO si distinguono per TIPOGRAFIA, non per pastiglie
 *    colorate. Non sono cinque varianti della stessa cosa: sono due numeri
 *    veri (`misurato`, `reale`) e tre non-numeri di natura diversa -- uno zero
 *    letterale (`gratuito`), un'assenza neutra (`compreso`) e un'assenza che
 *    chiede attenzione (`non_noto`). Cinque pastiglie li appiattirebbero di
 *    nuovo, stavolta con piu' colore.
 * 2. MAI UN TRATTINO PER UN COSTO. In questa pagina il trattino significa gia'
 *    «sto caricando» (`fmtNum`/`fmtEuro` lo danno su `null`), e riusarlo per
 *    «non lo so» rifarebbe in piccolo l'errore che la fetta esiste per
 *    togliere.
 * 3. I COLORI DEI PROVIDER NON RIUSANO --ok/--warn/--err. In HIRIS quei tre
 *    significano gia' riuscito / incerto / fallito (le pastiglie di Modelli e
 *    Promesse): un provider colorato `--warn` si leggerebbe come «in stato di
 *    allerta».
 */
(function() {
  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* Le parole dei cinque stati. Vivono qui e non nel server perche' sono
     TESTO DI PAGINA -- il server manda lo stato, che e' il fatto. */
  var PAROLA = {
    gratuito: 'Gratuito',
    compreso: "Compreso nell'abbonamento",
    non_noto: 'Prezzo sconosciuto'
  };

  /* L'ordine con cui i provider entrano nel grafico e nella legenda: fisso,
     cosi' due case identiche disegnano la stessa figura. */
  var ORDINE = ['claude', 'openai', 'openrouter', 'ollama', 'ponte'];

  var stato = { daAncora: true, giorni: 30, ultimo: null };

  /* Il costo di una riga, con le parole giuste per il suo stato.
     `misurato` e `reale` sono entrambi NUMERI: la differenza fra i due si
     dichiara una volta sola, nella nota della sezione, e non riga per riga --
     i due stati non convivono mai nella stessa sezione, perche' e' il
     provider a determinarli. */
  function costoDiRiga(m) {
    if (m.costo_stato === 'misurato' || m.costo_stato === 'reale') {
      return '<span class="umr-costo">' + fmtEuro(m.cost_eur, 4) + '</span>';
    }
    if (m.costo_stato === 'non_noto' && m.cost_eur != null && m.cost_eur > 0) {
      /* Il pavimento a scala di riga: «questo l'ho pagato di sicuro, piu'
         qualcosa che non so». Un concetto solo, a due scale. */
      return '<span class="umr-costo umr-ignoto">≥ ' + fmtEuro(m.cost_eur, 4) + '</span>';
    }
    var classe = m.costo_stato === 'non_noto' ? 'umr-costo umr-ignoto'
               : m.costo_stato === 'compreso' ? 'umr-costo umr-compreso'
               : 'umr-costo umr-gratuito';
    return '<span class="' + classe + '">'
      + escHtml(PAROLA[m.costo_stato] || m.costo_stato) + '</span>';
  }

  function rigaCache(m) {
    if (!m.cache_lettura && !m.cache_scrittura) return '';
    return ' · cache ' + fmtNum(m.cache_lettura) + ' letti / '
      + fmtNum(m.cache_scrittura) + ' scritti';
  }

  function rigaModello(m, provider) {
    var quando = m.primo_uso === m.ultimo_uso
      ? 'il ' + escHtml(m.primo_uso)
      : 'dal ' + escHtml(m.primo_uso) + ' al ' + escHtml(m.ultimo_uso);
    /* I rifiuti si mostrano SOLO se ce ne sono: lo stato-non-evento si omette,
       non si scrive a zero. */
    var rifiuti = m.errori_rate_limit
      ? ' · ' + m.errori_rate_limit + ' rifiuti per limite di frequenza'
      : '';
    var unita = provider === 'ponte' ? 'turni' : 'richieste';
    return '<div class="usage-model-row">'
      + '<div class="umr-top"><span class="umr-nome">' + escHtml(m.modello) + '</span>'
      + costoDiRiga(m) + '</div>'
      + '<div class="umr-meta">' + m.richieste + ' ' + unita + ' · '
      + fmtNum(m.token_in) + ' IN · ' + fmtNum(m.token_out) + ' OUT'
      + rigaCache(m) + '</div>'
      + '<div class="umr-foot">' + quando + rifiuti + '</div>'
      + '</div>';
  }

  function totaleSezione(s) {
    if (s.provider === 'ponte') {
      return '<span class="usec-costo umr-compreso">Compreso</span>';
    }
    var testo = fmtEuro(s.cost_eur, 2);
    return '<span class="usec-costo">' + (s.costo_parziale ? '≥ ' : '') + testo + '</span>';
  }

  function sezione(s) {
    return '<section class="usage-provider">'
      + '<div class="usec-testa"><h3 class="usec-nome">' + escHtml(s.etichetta) + '</h3>'
      + totaleSezione(s) + '</div>'
      + '<p class="sc-desc">' + escHtml(s.nota) + '</p>'
      + s.modelli.map(function(m) { return rigaModello(m, s.provider); }).join('')
      + '</section>';
  }

  /* ---- il riepilogo ------------------------------------------------- */

  function riepilogo(u) {
    var costo = (u.costo_parziale ? '≥ ' : '') + fmtEuro(u.cost_eur, 2);
    /* Il simbolo da solo e' criptico per chi apre la pagina dal telefono: la
       frase lo accompagna SEMPRE. */
    var nota = u.costo_parziale
      ? '<div class="st-delta st-avviso">cifra minima — manca il prezzo di almeno un modello</div>'
      : '';
    return '<div class="stat-grid" id="usage-riepilogo">'
      + '<div class="stat-tile"><div class="st-label">Costo</div>'
      + '<div class="st-value">' + costo + '</div>' + nota + '</div>'
      + '<div class="stat-tile"><div class="st-label">Richieste</div>'
      + '<div class="st-value">' + u.total_requests + '</div></div>'
      + '<div class="stat-tile"><div class="st-label">Token IN</div>'
      + '<div class="st-value">' + fmtNum(u.input_tokens) + '</div></div>'
      + '<div class="stat-tile"><div class="st-label">Token OUT</div>'
      + '<div class="st-value">' + fmtNum(u.output_tokens) + '</div></div>'
      + '</div>';
  }

  function barra(u) {
    var da = fmtDataOra(u.last_reset);
    return '<div class="usage-barra">'
      + '<div class="usage-quando" role="group" aria-label="Da quando contare">'
      + '<button class="btn btn-ghost' + (stato.daAncora ? ' attivo' : '') + '" '
      + 'id="usage-da-ancora">da ultimo azzeramento</button>'
      + '<button class="btn btn-ghost' + (stato.daAncora ? '' : ' attivo') + '" '
      + 'id="usage-da-sempre">da sempre</button>'
      + '</div>'
      + '<div class="usage-riparti-blocco">'
      + '<button class="btn btn-ghost" id="usage-riparti">Riparti da adesso</button>'
      + '<div class="hint">Non cancella niente: sposta solo il punto da cui contare.'
      + (da ? ' Adesso conta da ' + escHtml(da) + '.' : '') + '</div>'
      + '</div></div>';
  }

  /* ---- i grafici ---------------------------------------------------- */

  /* Due grafici e non uno. Il costo NON puo' contenere il ponte -- non ha un
     costo da impilare -- e la sua assenza si DICHIARA sotto il grafico invece
     di lasciarlo sparire in silenzio. Le richieste li contengono tutti, ed e'
     il grafico che risponde a «quanto sto usando cosa» anche dove il costo
     non esiste. Nessun terzo grafico per i token: quel dettaglio vive gia' in
     ogni riga. */
  function svgBarre(giorni, provider, chiave, titolo) {
    var L = 640, A = 120, base = A - 18, sinistra = 4;
    if (!giorni.length) {
      return '<p class="hint">Nessun consumo nel periodo scelto.</p>';
    }
    var totali = giorni.map(function(g) {
      return provider.reduce(function(acc, p) {
        return acc + (((g.per_provider || {})[p] || {})[chiave] || 0);
      }, 0);
    });
    var massimo = Math.max.apply(null, totali.concat([0.000001]));
    var passo = (L - sinistra * 2) / giorni.length;
    var barre = '';
    giorni.forEach(function(g, i) {
      var y = base;
      provider.forEach(function(p) {
        var v = ((g.per_provider || {})[p] || {})[chiave] || 0;
        if (!v) return;
        var h = (v / massimo) * (base - 6);
        y -= h;
        barre += '<rect x="' + (sinistra + i * passo).toFixed(1) + '" y="' + y.toFixed(1)
          + '" width="' + Math.max(1, passo - 2).toFixed(1) + '" height="' + h.toFixed(1)
          + '" fill="var(--consumo-' + p + ')"><title>' + escHtml(g.giorno) + ' · '
          + escHtml(p) + '</title></rect>';
      });
    });
    return '<svg class="usage-grafico" viewBox="0 0 ' + L + ' ' + A + '" role="img" '
      + 'aria-label="' + escHtml(titolo) + '">'
      + '<title>' + escHtml(titolo) + '</title>'
      + '<desc>Barre impilate per giorno. Gli stessi numeri sono nella tabella '
      + 'qui sotto.</desc>' + barre
      + '<line x1="0" y1="' + base + '" x2="' + L + '" y2="' + base
      + '" stroke="var(--border)"></line></svg>';
  }

  function legenda(provider, etichette) {
    return '<div class="usage-legenda">' + provider.map(function(p) {
      return '<span class="ulg"><i style="background:var(--consumo-' + p + ')"></i>'
        + escHtml(etichette[p] || p) + '</span>';
    }).join('') + '</div>';
  }

  function tabellaEquivalente(giorni, provider, chiave, etichette) {
    var righe = giorni.map(function(g) {
      return '<tr><td>' + escHtml(g.giorno) + '</td>' + provider.map(function(p) {
        var v = ((g.per_provider || {})[p] || {})[chiave];
        return '<td>' + (v == null ? '' : (chiave === 'cost_eur' ? fmtEuro(v, 2) : v)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<details class="usage-section"><summary>I numeri del grafico</summary>'
      + '<table class="usage-tabella"><thead><tr><th>Giorno</th>'
      + provider.map(function(p) { return '<th>' + escHtml(etichette[p] || p) + '</th>'; }).join('')
      + '</tr></thead><tbody>' + righe + '</tbody></table></details>';
  }

  function grafici(storia, sezioni) {
    var etichette = {};
    var presenti = [];
    sezioni.forEach(function(s) { etichette[s.provider] = s.etichetta; });
    ORDINE.forEach(function(p) { if (etichette[p]) presenti.push(p); });

    var giorni = (storia.giorni || []).slice(-stato.giorni);
    var conCosto = presenti.filter(function(p) { return p !== 'ponte'; });
    var fuori = presenti.indexOf('ponte') >= 0
      ? '<p class="hint">L\'abbonamento non compare qui: non ha un costo da '
        + 'impilare. I suoi turni sono nel grafico sotto.</p>'
      : '';

    return '<div class="usage-grafici">'
      + '<div class="usage-testa-grafico"><h3>Costo al giorno</h3>'
      + '<div class="usage-quando"><button class="btn btn-ghost'
      + (stato.giorni === 7 ? ' attivo' : '') + '" id="usage-7">7 giorni</button>'
      + '<button class="btn btn-ghost' + (stato.giorni === 30 ? ' attivo' : '')
      + '" id="usage-30">30 giorni</button></div></div>'
      + svgBarre(giorni, conCosto, 'cost_eur', 'Costo al giorno per provider')
      + legenda(conCosto, etichette) + fuori
      + tabellaEquivalente(giorni, conCosto, 'cost_eur', etichette)
      + '<h3>Richieste al giorno</h3>'
      + svgBarre(giorni, presenti, 'richieste', 'Richieste al giorno per provider')
      + legenda(presenti, etichette)
      + tabellaEquivalente(giorni, presenti, 'richieste', etichette)
      + '</div>';
  }

  /* ---- il montaggio -------------------------------------------------- */

  function disegna(u, storia) {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;

    if (u.misurata === false) {
      /* Il server DICHIARA che su questa configurazione i consumi non si
         misurano (200 con `misurata: false`): non e' un guasto, ed e' un caso
         solo -- non e' mai stato usato niente e non c'e' niente che possa
         rispondere. Il pulsante non si mostra: non c'e' nessuna ancora da
         spostare. */
      outlet.innerHTML = '<div class="page-title">Consumi</div>'
        + '<p class="page-subtitle st-avviso">'
        + escHtml(u.messaggio || 'I consumi non si misurano su questa configurazione.')
        + '</p>';
      return;
    }

    var fuso = u.fuso_noto
      ? 'Giorni e orari nel fuso della casa (' + escHtml(u.fuso) + ').'
      : 'Il fuso della casa non è ancora noto: i giorni sono contati in UTC.';

    outlet.innerHTML = '<div class="page-title">Consumi</div>'
      + '<p class="page-subtitle">Quanto ha consumato ogni modello, e quanto è '
      + 'costato. ' + fuso + '</p>'
      + barra(u)
      + riepilogo(u)
      + grafici(storia, u.sezioni || [])
      + '<div class="usage-sezioni">'
      + (u.sezioni || []).map(sezione).join('')
      + '</div>';

    collega();
  }

  function collega() {
    var per = function(id, fn) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('click', fn);
    };
    per('usage-da-ancora', function() { stato.daAncora = true; mount(); });
    per('usage-da-sempre', function() { stato.daAncora = false; mount(); });
    per('usage-7', function() { stato.giorni = 7; mount(); });
    per('usage-30', function() { stato.giorni = 30; mount(); });
    /* Nessun `confirm()`: il gesto e' reversibile dall'interfaccia stessa
       (basta «da sempre») e non distrugge niente. La frase che lo dice e'
       SEMPRE visibile sotto il pulsante, non nascosta in un blocco modale che
       compare a cose fatte. */
    per('usage-riparti', function() {
      fetch('api/usage/reset', {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(function() { mount(); })
        .catch(function(e) { console.error('reset consumi fallito', e); });
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (outlet && !outlet.innerHTML) {
      outlet.innerHTML = '<div class="page-title">Consumi</div>'
        + '<p class="page-subtitle">Carico…</p>';
    }
    /* Due domande, due rotte: il riepilogo e' leggero perche' lo richiama
       anche il riquadro della chat a intervalli, e trenta giorni di serie
       storica li' sarebbero un peso che la chat non chiede mai. */
    Promise.all([
      fetch('api/usage' + (stato.daAncora ? '' : '?from=sempre')).then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }),
      fetch('api/usage/history').then(function(r) {
        return r.ok ? r.json() : { giorni: [] };
      }).catch(function() { return { giorni: [] }; })
    ]).then(function(esiti) {
      stato.ultimo = esiti[0];
      disegna(esiti[0], esiti[1]);
    }).catch(function(err) {
      console.error('usage fetch failed', err);
      var outlet2 = document.getElementById('route-outlet');
      if (outlet2) {
        outlet2.innerHTML = '<div class="page-title">Consumi</div>'
          + '<div class="proposals-error">Errore caricamento consumi.</div>';
      }
    });
  }

  window.HirisUsageRoute = { mount: mount };
})();
