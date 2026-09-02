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
  var Word = {
    gratuito: 'Gratuito',
    compreso: "Compreso nell'abbonamento",
    non_noto: 'Prezzo sconosciuto'
  };

  /* L'ordine con cui i provider entrano nel grafico e nella legenda: fisso,
     cosi' due case identiche disegnano la stessa figura. */
  var Order = ['claude', 'openai', 'openrouter', 'ollama', 'ponte'];

  var state = { daAncora: true, giorni: 30, ultimo: null };

  /* Il costo di una riga, con le parole giuste per il suo stato.
     `misurato` e `reale` sono entrambi NUMERI: la differenza fra i due si
     dichiara una volta sola, nella nota della sezione, e non riga per riga --
     i due stati non convivono mai nella stessa sezione, perche' e' il
     provider a determinarli. */
  function costoDiRiga(m) {
    if (m.cost_state === 'misurato' || m.cost_state === 'reale') {
      return '<span class="umr-costo">' + fmtEuro(m.cost_eur, 4) + '</span>';
    }
    if (m.cost_state === 'non_noto' && m.cost_eur != null && m.cost_eur > 0) {
      /* Il pavimento a scala di riga: «questo l'ho pagato di sicuro, piu'
         qualcosa che non so». Un concetto solo, a due scale. */
      return '<span class="umr-costo umr-ignoto">≥ ' + fmtEuro(m.cost_eur, 4) + '</span>';
    }
    var cssClass = m.cost_state === 'non_noto' ? 'umr-costo umr-ignoto'
               : m.cost_state === 'compreso' ? 'umr-costo umr-compreso'
               : 'umr-costo umr-gratuito';
    return '<span class="' + cssClass + '">'
      + escHtml(Word[m.cost_state] || m.cost_state) + '</span>';
  }

  function rigaCache(m) {
    if (!m.cache_read && !m.cache_write) return '';
    return ' · cache ' + fmtNum(m.cache_read) + ' letti / '
      + fmtNum(m.cache_write) + ' scritti';
  }

  function modelRow(m, provider) {
    var when = m.first_use === m.last_use
      ? 'il ' + escHtml(m.first_use)
      : 'dal ' + escHtml(m.first_use) + ' al ' + escHtml(m.last_use);
    /* I rifiuti si mostrano SOLO se ce ne sono: lo stato-non-evento si omette,
       non si scrive a zero. */
    var refusals = m.rate_limit_errors
      ? ' · ' + m.rate_limit_errors + ' rifiuti per limite di frequenza'
      : '';
    var unit = provider === 'ponte' ? 'turni' : 'richieste';
    return '<div class="usage-model-row">'
      + '<div class="umr-top"><span class="umr-nome">' + escHtml(m.model) + '</span>'
      + costoDiRiga(m) + '</div>'
      + '<div class="umr-meta">' + m.requests + ' ' + unit + ' · '
      + fmtNum(m.token_in) + ' IN · ' + fmtNum(m.token_out) + ' OUT'
      + rigaCache(m) + '</div>'
      + '<div class="umr-foot">' + when + refusals + '</div>'
      + '</div>';
  }

  function sectionTotal(s) {
    if (s.provider === 'ponte') {
      return '<span class="usec-costo umr-compreso">Compreso</span>';
    }
    var text = fmtEuro(s.cost_eur, 2);
    return '<span class="usec-costo">' + (s.partial_cost ? '≥ ' : '') + text + '</span>';
  }

  function section(s) {
    return '<section class="usage-provider">'
      + '<div class="usec-testa"><h3 class="usec-nome">' + escHtml(s.label) + '</h3>'
      + sectionTotal(s) + '</div>'
      + '<p class="sc-desc">' + escHtml(s.note) + '</p>'
      + s.models.map(function(m) { return modelRow(m, s.provider); }).join('')
      + '</section>';
  }

  /* ---- il riepilogo ------------------------------------------------- */

  function summary(u) {
    var cost = (u.partial_cost ? '≥ ' : '') + fmtEuro(u.cost_eur, 2);
    /* Il simbolo da solo e' criptico per chi apre la pagina dal telefono: la
       frase lo accompagna SEMPRE. */
    var note = u.partial_cost
      ? '<div class="st-delta st-avviso">cifra minima — manca il prezzo di almeno un modello</div>'
      : '';
    return '<div class="stat-grid" id="usage-riepilogo">'
      + '<div class="stat-tile"><div class="st-label">Costo</div>'
      + '<div class="st-value">' + cost + '</div>' + note + '</div>'
      + '<div class="stat-tile"><div class="st-label">Richieste</div>'
      + '<div class="st-value">' + u.total_requests + '</div></div>'
      + '<div class="stat-tile"><div class="st-label">Token IN</div>'
      + '<div class="st-value">' + fmtNum(u.input_tokens) + '</div></div>'
      + '<div class="stat-tile"><div class="st-label">Token OUT</div>'
      + '<div class="st-value">' + fmtNum(u.output_tokens) + '</div></div>'
      + '</div>';
  }

  function bar(u) {
    var da = fmtDataOra(u.last_reset);
    return '<div class="usage-barra">'
      + '<div class="usage-quando" role="group" aria-label="Da quando contare">'
      + '<button class="btn btn-ghost' + (state.daAncora ? ' attivo' : '') + '" '
      + 'id="usage-da-ancora">da ultimo azzeramento</button>'
      + '<button class="btn btn-ghost' + (state.daAncora ? '' : ' attivo') + '" '
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
  function svgBarre(giorni, provider, key, title) {
    var L = 640, A = 120, base = A - 18, left = 4;
    if (!giorni.length) {
      return '<p class="hint">Nessun consumo nel periodo scelto.</p>';
    }
    var totali = giorni.map(function(g) {
      return provider.reduce(function(acc, p) {
        return acc + (((g.per_provider || {})[p] || {})[key] || 0);
      }, 0);
    });
    var maximum = Math.max.apply(null, totali.concat([0.000001]));
    var passo = (L - left * 2) / giorni.length;
    var bar = '';
    giorni.forEach(function(g, i) {
      var y = base;
      provider.forEach(function(p) {
        var v = ((g.per_provider || {})[p] || {})[key] || 0;
        if (!v) return;
        var h = (v / maximum) * (base - 6);
        y -= h;
        bar += '<rect x="' + (left + i * passo).toFixed(1) + '" y="' + y.toFixed(1)
          + '" width="' + Math.max(1, passo - 2).toFixed(1) + '" height="' + h.toFixed(1)
          + '" fill="var(--consumo-' + p + ')"><title>' + escHtml(g.day) + ' · '
          + escHtml(p) + '</title></rect>';
      });
    });
    return '<svg class="usage-grafico" viewBox="0 0 ' + L + ' ' + A + '" role="img" '
      + 'aria-label="' + escHtml(title) + '">'
      + '<title>' + escHtml(title) + '</title>'
      + '<desc>Barre impilate per giorno. Gli stessi numeri sono nella tabella '
      + 'qui sotto.</desc>' + bar
      + '<line x1="0" y1="' + base + '" x2="' + L + '" y2="' + base
      + '" stroke="var(--border)"></line></svg>';
  }

  function legend(provider, labels) {
    return '<div class="usage-legenda">' + provider.map(function(p) {
      return '<span class="ulg"><i style="background:var(--consumo-' + p + ')"></i>'
        + escHtml(labels[p] || p) + '</span>';
    }).join('') + '</div>';
  }

  function equivalentTable(giorni, provider, key, labels) {
    var line = giorni.map(function(g) {
      return '<tr><td>' + escHtml(g.day) + '</td>' + provider.map(function(p) {
        var v = ((g.per_provider || {})[p] || {})[key];
        return '<td>' + (v == null ? '' : (key === 'cost_eur' ? fmtEuro(v, 2) : v)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<details class="usage-section"><summary>I numeri del grafico</summary>'
      + '<table class="usage-tabella"><thead><tr><th>Giorno</th>'
      + provider.map(function(p) { return '<th>' + escHtml(labels[p] || p) + '</th>'; }).join('')
      + '</tr></thead><tbody>' + line + '</tbody></table></details>';
  }

  function charts(storia, sezioni) {
    var labels = {};
    var present = [];
    sezioni.forEach(function(s) { labels[s.provider] = s.label; });
    Order.forEach(function(p) { if (labels[p]) present.push(p); });

    var giorni = (storia.days || []).slice(-state.giorni);
    var conCosto = present.filter(function(p) { return p !== 'ponte'; });
    var outside = present.indexOf('ponte') >= 0
      ? '<p class="hint">L\'abbonamento non compare qui: non ha un costo da '
        + 'impilare. I suoi turni sono nel grafico sotto.</p>'
      : '';

    return '<div class="usage-grafici">'
      + '<div class="usage-testa-grafico"><h3>Costo al giorno</h3>'
      + '<div class="usage-quando"><button class="btn btn-ghost'
      + (state.giorni === 7 ? ' attivo' : '') + '" id="usage-7">7 giorni</button>'
      + '<button class="btn btn-ghost' + (state.giorni === 30 ? ' attivo' : '')
      + '" id="usage-30">30 giorni</button></div></div>'
      + svgBarre(giorni, conCosto, 'cost_eur', 'Costo al giorno per provider')
      + legend(conCosto, labels) + outside
      + equivalentTable(giorni, conCosto, 'cost_eur', labels)
      + '<h3>Richieste al giorno</h3>'
      + svgBarre(giorni, present, 'requests', 'Richieste al giorno per provider')
      + legend(present, labels)
      + equivalentTable(giorni, present, 'requests', labels)
      + '</div>';
  }

  /* ---- il montaggio -------------------------------------------------- */

  function draw(u, storia) {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;

    if (u.measured === false) {
      /* Il server DICHIARA che su questa configurazione i consumi non si
         misurano (200 con `measured: false`): non e' un guasto, ed e' un caso
         solo -- non e' mai stato usato niente e non c'e' niente che possa
         rispondere. Il pulsante non si mostra: non c'e' nessuna ancora da
         spostare. */
      outlet.innerHTML = '<div class="page-title">Consumi</div>'
        + '<p class="page-subtitle st-avviso">'
        + escHtml(u.message || 'I consumi non si misurano su questa configurazione.')
        + '</p>';
      return;
    }

    var timezone = u.timezone_known
      ? 'Giorni e orari nel fuso della casa (' + escHtml(u.timezone) + ').'
      : 'Il fuso della casa non è ancora noto: i giorni sono contati in UTC.';

    outlet.innerHTML = '<div class="page-title">Consumi</div>'
      + '<p class="page-subtitle">Quanto ha consumato ogni modello, e quanto è '
      + 'costato. ' + timezone + '</p>'
      + bar(u)
      + summary(u)
      + charts(storia, u.sections || [])
      + '<div class="usage-sezioni">'
      + (u.sections || []).map(section).join('')
      + '</div>';

    connect();
  }

  function connect() {
    var per = function(id, fn) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('click', fn);
    };
    per('usage-da-ancora', function() { state.daAncora = true; mount(); });
    per('usage-da-sempre', function() { state.daAncora = false; mount(); });
    per('usage-7', function() { state.giorni = 7; mount(); });
    per('usage-30', function() { state.giorni = 30; mount(); });
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
      fetch('api/usage' + (state.daAncora ? '' : '?from=sempre')).then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }),
      fetch('api/usage/history').then(function(r) {
        return r.ok ? r.json() : { days: [] };
      }).catch(function() { return { days: [] }; })
    ]).then(function(occurrence) {
      state.ultimo = occurrence[0];
      draw(occurrence[0], occurrence[1]);
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
