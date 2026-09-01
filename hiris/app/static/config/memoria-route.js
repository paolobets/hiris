/* HIRIS · Configurazione · «Memoria» (route #/memoria)

   Sostituisce il pannello Memoria della chat, che interrogava la coda di
   approvazione di knowledge_store (lo stato "pending") — vuota per
   costruzione dalla fetta memoria-unica (Task 2): nessuno scriveva più
   quello stato. Un pannello con un badge fermo a zero per sempre non era un
   pannello vuoto, era una promessa che non arrivava mai. Dalla fetta «esce
   il documentale» quella coda non esiste più affatto: l'archivio di
   conoscenza, il suo handler e le sue quattro rotte /api/knowledge* sono
   usciti, restando senza nessun consumatore vivo. Questa pagina è l'unica
   vista della memoria, e legge l'archivio vero (/api/memories).

   Questa pagina interroga invece l'archivio vero (`GET/PATCH/DELETE
   /api/memories*`, `hiris/app/api/handlers_memoria.py`) ed esegue la
   decisione (5) del progetto della memoria (docs/design/2026-08-05-la-
   conoscenza-di-hiris.md, §6): «si può ricordare subito solo se poi si può
   guardare e correggere».

   Tre regole non negoziabili, tutte già motivate in handlers_memoria.py e
   verificate leggendo quel file prima di scrivere questa pagina:
   1. `ancora.esiste === null` significa «non ho potuto controllare»
      (l'anagrafe non è mai stata letta, o quel registro non ha risposto),
      e NON «l'ancora non esiste». Renderlo come «cancellata» sarebbe un
      silenzio non dichiarato — l'ancora tornerebbe visibilmente viva alla
      lettura successiva, e nel frattempo l'utente avrebbe letto un fatto
      falso. I tre stati (`true`/`false`/`null`) restano tre resi diversi.
   2. `PATCH` corregge l'interpretazione, MAI il testo — non c'è un campo
      per modificare `testo` in questa pagina, perché il backend lo
      ignorerebbe comunque (`_CORRECTABLE_FIELDS`). Un rifiuto (400, ancora
      senza riscontro nell'anagrafe; o 404, ricordo sparito nel frattempo)
      mostra sempre la ragione che il server manda, non un errore generico.
   3. La risposta porta sempre `totale` accanto ai ricordi mostrati
      (`_MEMORIES_SHOWN_LIMIT = 200`): se `mostrati < totale` la pagina
      lo dichiara, così un ricordo oltre il taglio non sembra cancellato.

   Ambito dichiarato di "correggere": i campi scalari dell'interpretazione
   (forza, grandezza, intervallo, unità, detto_da) — sono quelli che
   `ArchivioMemoria.correggi()` accetta come colonne singole. Le liste
   `ancore`/`condizioni` restano di sola lettura in questa pagina: il
   backend le accetta già in PATCH (sostituzione intera, non riga per
   riga), ma un editor di liste di oggetti tipo+riferimento con verifica
   contro l'anagrafe è un pezzo di superficie a sé, senza un pattern
   riusabile altrove in questo repo — resta un'estensione futura, non
   silenziosa: questo commento la dichiara, e dalla fetta «fix pre-UAT» la
   dichiara anche il modulo di correzione, sullo schermo, sopra i campi
   (`costruisciModuloCorrezione`) — un commento nel sorgente non lo legge
   nessuno di quelli che aprono la pagina.

   Cancellare un ricordo è distruttivo e definitivo (l'archivio non ha una
   coda di attesa): `window.confirm()` mostra SEMPRE la frase esatta del
   ricordo prima di procedere, stesso linguaggio del pannello Memoria che
   sostituisce (chat/knowledge.js, uscito con questo stesso task).

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati
   server (stessa disciplina di dashboard.js/models-route.js) — il testo di un ricordo è stato scritto in chat,
   eventualmente da un modello su dettatura dell'utente. */
window.HirisMemoriaRoute = (function () {
  'use strict';

  var FORZA_LABELS = {
    preferenza: 'Preferenza', divieto: 'Divieto', fatto: 'Fatto', regola: 'Regola operativa'
  };
  var FORZA_OPZIONI = [
    ['', '(non impostata)'], ['preferenza', 'Preferenza'], ['divieto', 'Divieto'],
    ['fatto', 'Fatto'], ['regola', 'Regola operativa']
  ];
  var TIPO_ANCORA_LABELS = { area: 'Area', entita: 'Entità', dispositivo: 'Dispositivo' };

  function el(tag, cls, testo) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo != null) e.textContent = testo;
    return e;
  }
  function clearEl(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
  }
  function byId(id) { return document.getElementById(id); }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(path, opts);
  }

  /* L'istante arriva in ISO 8601 UTC (`detto_il`, `archivio.py`): l'utente
     legge l'ora locale. `null` se manca o non è interpretabile — si
     dichiara "data non disponibile", non se ne inventa una. */
  function fmtQuando(iso) {
    var t = iso ? Date.parse(iso) : NaN;
    if (isNaN(t)) return null;
    try {
      return new Date(t).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch { return new Date(t).toLocaleString(); }
  }

  function formattaIntervallo(r) {
    var u = r.unita ? ' ' + r.unita : '';
    if (r.minimo != null && r.massimo != null) {
      return (r.minimo === r.massimo ? String(r.minimo) : 'fra ' + r.minimo + ' e ' + r.massimo) + u;
    }
    if (r.minimo != null) return 'da ' + r.minimo + u;
    if (r.massimo != null) return 'fino a ' + r.massimo + u;
    return null;
  }

  function mostraErroreCard(nodo, testo) {
    nodo.textContent = testo;
    nodo.style.display = '';
  }

  function setStatus(testo) {
    var s = byId('memoria-status');
    if (s) s.textContent = testo || '';
  }

  /* ── Ancore: tre resi diversi per tre fatti diversi (regola 1) ────────── */
  function rendiAncore(corpo, ancore) {
    var tit = el('div', null, 'Riguarda:');
    tit.style.cssText = 'font-weight:500;font-size:var(--fs-13);margin:8px 0 4px';
    corpo.appendChild(tit);
    var ul = el('ul');
    ul.style.cssText = 'margin:0 0 8px;padding-left:18px;font-size:var(--fs-13);color:var(--text-2)';
    ancore.forEach(function (a) {
      var nome = a.nome_attuale || a.nome_visto || a.riferimento;
      var testo, tono;
      if (a.esiste === true) { testo = nome; tono = ''; }
      /* `--err-ink`/`--warn-ink` e non `--err`/`--warn`: e' testo, e sul tema
         chiaro i due originali stanno sotto AA (4.05:1 e 2.04:1). */
      else if (a.esiste === false) { testo = nome + ' — non esiste più nell’anagrafe'; tono = 'var(--err-ink)'; }
      else { testo = nome + ' — non è stato possibile verificarlo'; tono = 'var(--warn-ink)'; }
      var li = el('li', null, (TIPO_ANCORA_LABELS[a.tipo] || a.tipo) + ': ' + testo);
      if (tono) li.style.color = tono;
      ul.appendChild(li);
    });
    corpo.appendChild(ul);
  }

  /* ── Il modulo di correzione: solo i campi scalari (vedi header) ──────── */
  function costruisciModuloCorrezione(r, cardErr, dopoSalvataggio) {
    var wrap = el('div');
    wrap.style.cssText = 'border-top:1px solid var(--border);padding-top:10px;' +
      'display:flex;flex-direction:column;gap:8px;max-width:360px';

    function campo(etichetta, input) {
      var f = el('div');
      f.style.cssText = 'display:flex;flex-direction:column;gap:2px';
      var l = el('label', null, etichetta);
      l.style.cssText = 'font-size:var(--fs-12);color:var(--text-3)';
      f.appendChild(l);
      f.appendChild(input);
      return f;
    }

    var selForza = el('select');
    FORZA_OPZIONI.forEach(function (v) {
      var o = el('option', null, v[1]);
      o.value = v[0];
      selForza.appendChild(o);
    });
    // Una forza che questa pagina non conosce si AGGIUNGE, non si ignora.
    //
    // Senza, il difetto non era una tendina incompleta: era perdita di dati.
    // `selForza.value = <valore assente>` ricade in silenzio su '', poi il
    // confronto qui sotto vede '' !== 'obiettivo' e la PATCH manda
    // `forza: null`. Chi correggeva «Detto da» si vedeva cancellare la forza
    // del ricordo -- e la memoria e' l'unico archivio di HIRIS che non si
    // ricostruisce da nessuna parte.
    //
    // Il vocabolario vero sta in `memoria/interpretazione.py::VOCABOLARIO`, ed
    // e' legato a questo file da `tests/test_memoria_frontend_wiring.py`: quel
    // test si rompe il giorno in cui le liste divergono. Questo ramo e' cio'
    // che protegge l'utente NEL FRATTEMPO.
    if (r.forza && !FORZA_OPZIONI.some(function (v) { return v[0] === r.forza; })) {
      var sconosciuta = el('option', null, FORZA_LABELS[r.forza] || r.forza);
      sconosciuta.value = r.forza;
      selForza.appendChild(sconosciuta);
    }
    selForza.value = r.forza || '';

    var inpGrandezza = el('input'); inpGrandezza.type = 'text'; inpGrandezza.value = r.grandezza || '';
    var inpMinimo = el('input'); inpMinimo.type = 'number'; inpMinimo.step = 'any';
    inpMinimo.value = r.minimo != null ? r.minimo : '';
    var inpMassimo = el('input'); inpMassimo.type = 'number'; inpMassimo.step = 'any';
    inpMassimo.value = r.massimo != null ? r.massimo : '';
    var inpUnita = el('input'); inpUnita.type = 'text'; inpUnita.value = r.unita || '';
    var inpDettoDa = el('input'); inpDettoDa.type = 'text'; inpDettoDa.value = r.detto_da || '';

    /* L'ambito di «Correggi» era dichiarato SOLO nel commento in cima a
       questo file: chi apre il modulo vede sei campi e non ha modo di sapere
       che il testo del ricordo, le ancore («Riguarda:») e le condizioni
       («Quando vale:») non si toccano da qui -- e un salvataggio che non
       cambia cio' che l'utente si aspettava di cambiare e' esattamente il
       silenzio che questo prodotto paga da sempre. Ora la regola sta sullo
       schermo, sopra i campi. */
    var ambito = el('p', 'sc-desc',
      'Da qui si corregge solo come HIRIS ha interpretato il ricordo. ' +
      'La frase, le ancore («Riguarda:») e le condizioni («Quando vale:») ' +
      'sono in sola lettura: si cambiano parlando in chat.');
    ambito.style.cssText = 'margin:0;font-size:var(--fs-12);color:var(--text-3)';
    wrap.appendChild(ambito);

    wrap.appendChild(campo('Forza', selForza));
    wrap.appendChild(campo('Grandezza (es. temperature, humidity — vocabolario di Home Assistant)', inpGrandezza));
    wrap.appendChild(campo('Minimo', inpMinimo));
    wrap.appendChild(campo('Massimo', inpMassimo));
    wrap.appendChild(campo('Unità', inpUnita));
    wrap.appendChild(campo('Detto da', inpDettoDa));

    var salva = el('button', 'btn btn-primary btn-sm', 'Salva correzione');
    salva.type = 'button';
    wrap.appendChild(salva);

    salva.addEventListener('click', function () {
      /* Solo i campi TOCCATI entrano nel corpo: un PATCH parziale lascia
         intatto ciò che l'utente non ha guardato (es. non rimanda `unita`
         se ha corretto solo `grandezza` — il server la rideduce da sé,
         handlers_memoria.py). Un valore numerico illeggibile si dichiara
         qui, prima di mandarlo. */
      var corpo = {};
      var nMinimo = inpMinimo.value === '' ? null : parseFloat(inpMinimo.value);
      var nMassimo = inpMassimo.value === '' ? null : parseFloat(inpMassimo.value);
      if ((inpMinimo.value !== '' && isNaN(nMinimo)) || (inpMassimo.value !== '' && isNaN(nMassimo))) {
        mostraErroreCard(cardErr, 'Minimo e massimo devono essere numeri.');
        return;
      }
      var nForza = selForza.value || null;
      var nGrandezza = inpGrandezza.value.trim() || null;
      var nUnita = inpUnita.value.trim() || null;
      var nDettoDa = inpDettoDa.value.trim() || null;
      if (nForza !== (r.forza || null)) corpo.forza = nForza;
      if (nGrandezza !== (r.grandezza || null)) corpo.grandezza = nGrandezza;
      if (nMinimo !== r.minimo) corpo.minimo = nMinimo;
      if (nMassimo !== r.massimo) corpo.massimo = nMassimo;
      if (nUnita !== (r.unita || null)) corpo.unita = nUnita;
      if (nDettoDa !== (r.detto_da || null)) corpo.detto_da = nDettoDa;

      if (!Object.keys(corpo).length) {
        mostraErroreCard(cardErr, 'Nessuna modifica da salvare.');
        return;
      }
      cardErr.style.display = 'none';
      salva.disabled = true;
      api('api/memories/' + encodeURIComponent(r.id), { method: 'PATCH', body: JSON.stringify(corpo) })
        .then(function (res) {
          return res.json().catch(function () { return {}; }).then(function (json) {
            return { res: res, json: json };
          });
        })
        .then(function (esito) {
          salva.disabled = false;
          if (esito.res.status === 404) {
            /* Il ricaricamento sotto ricostruisce l'intera lista (compresa
               questa card, che sparisce): il messaggio va sulla riga di
               stato di pagina, che il ricaricamento NON tocca, altrimenti
               l'utente non fa in tempo a leggerlo. */
            setStatus('Questo ricordo non c’è più: è già stato cancellato altrove.');
            dopoSalvataggio();
            return;
          }
          if (!esito.res.ok) {
            /* Rifiutata con la ragione (regola 2): il messaggio del server
               dice QUALE ancora o intervallo non va, non un generico
               "errore". */
            mostraErroreCard(cardErr, (esito.json && esito.json.error) || ('Errore HTTP ' + esito.res.status));
            return;
          }
          var nota = 'Correzione salvata.';
          if (esito.json.correzioni && esito.json.correzioni.length) {
            nota += ' ' + esito.json.correzioni.join('; ') + '.';
          }
          setStatus(nota);
          dopoSalvataggio();
        }, function () {
          salva.disabled = false;
          mostraErroreCard(cardErr, 'La memoria non ha risposto. Riprova più tardi.');
        });
    });

    return wrap;
  }

  /* ── Una card per ricordo ──────────────────────────────────────────────── */
  function costruisciCard(r, ricarica) {
    var card = el('div', 'section-card');
    card.style.cssText = 'margin-bottom:10px';
    var body = el('div', 'sc-body');

    var testa = el('div');
    testa.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:6px';
    var quando = fmtQuando(r.detto_il);
    testa.appendChild(el('span', 'field-hint', (quando || 'data non disponibile') + (r.detto_da ? ' · ' + r.detto_da : '')));
    if (r.forza) testa.appendChild(el('span', 'agent-badge badge-off', FORZA_LABELS[r.forza] || r.forza));
    if (r.corretto_da_utente) testa.appendChild(el('span', 'agent-badge badge-on', 'corretto da te'));
    body.appendChild(testa);

    var frase = el('p', null, r.testo);
    frase.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:0 0 8px';
    body.appendChild(frase);

    var interpretazione = [];
    if (r.grandezza) interpretazione.push(r.grandezza);
    var intervallo = formattaIntervallo(r);
    if (intervallo) interpretazione.push(intervallo);
    body.appendChild(el('p', 'sc-desc', interpretazione.length
      ? 'HIRIS ha capito: ' + interpretazione.join(' · ')
      : 'Nessuna struttura riconosciuta — resta solo la frase.'));

    if (r.ancore && r.ancore.length) rendiAncore(body, r.ancore);
    if (r.condizioni && r.condizioni.length) {
      body.appendChild(el('p', 'sc-desc', 'Quando vale: ' +
        r.condizioni.map(function (c) { return c.tipo + ': ' + c.valore; }).join(' · ')));
    }

    var barra = el('div');
    barra.style.cssText = 'display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap';
    var btnCorreggi = el('button', 'btn btn-ghost btn-sm', 'Correggi');
    btnCorreggi.type = 'button';
    /* «Dimentica» era l'unico elemento della riga che sembrasse un bottone --
       rosso, bordato -- mentre «Correggi», l'azione sicura, sembrava
       un'etichetta: la gerarchia era rovesciata. Ora sono due ghost uguali e il
       rosso di questo arriva col passaggio del mouse (`.btn-ghost-danger`). */
    var btnCancella = el('button', 'btn btn-ghost btn-ghost-danger btn-sm', 'Dimentica');
    btnCancella.type = 'button';
    barra.appendChild(btnCorreggi);
    barra.appendChild(btnCancella);
    body.appendChild(barra);

    var formWrap = el('div');
    formWrap.style.display = 'none';
    body.appendChild(formWrap);

    var cardErr = el('p', 'proposals-error', '');
    cardErr.style.display = 'none';
    body.appendChild(cardErr);

    btnCorreggi.addEventListener('click', function () {
      var aperto = formWrap.style.display !== 'none';
      clearEl(formWrap);
      if (aperto) { formWrap.style.display = 'none'; return; }
      formWrap.appendChild(costruisciModuloCorrezione(r, cardErr, ricarica));
      formWrap.style.display = '';
    });

    /* Distruttivo e definitivo (niente coda: l'archivio non ha uno stato
       "in attesa"): la conferma mostra SEMPRE la frase esatta, così chi
       clicca sa cosa sta togliendo — stesso linguaggio del pannello che
       questa pagina sostituisce. */
    btnCancella.addEventListener('click', function () {
      var msg = 'Cancellare questo ricordo per sempre?\n\n«' + r.testo + '»\n\n' +
        'Non si può annullare: il ricordo e le sue ancore vengono tolti dall’archivio.';
      if (!window.confirm(msg)) return;
      cardErr.style.display = 'none';
      api('api/memories/' + encodeURIComponent(r.id), { method: 'DELETE' }).then(function (res) {
        if (res.status === 204) { setStatus('Ricordo cancellato.'); ricarica(); return; }
        return res.json().catch(function () { return {}; }).then(function (corpo) {
          mostraErroreCard(cardErr, (corpo && corpo.error) || ('Errore HTTP ' + res.status));
        });
      }, function () {
        mostraErroreCard(cardErr, 'La memoria non ha risposto. Riprova più tardi.');
      });
    });

    card.appendChild(body);
    return card;
  }

  /* ── I tre stati della lista: vuota, illeggibile, piena (ambiguità
     risolta nel brief: sono due fatti diversi e vanno detti diversamente) */
  function rendiNonDisponibile(lista) {
    clearEl(lista);
    lista.appendChild(el('p', 'proposals-error',
      'L’archivio della memoria non è disponibile in questo momento. Non significa che non ci ' +
      'siano ricordi: la richiesta non ha trovato l’archivio.'));
  }

  function rendiErrore(lista, ricarica) {
    clearEl(lista);
    lista.appendChild(el('p', 'proposals-error', 'Non è stato possibile leggere i ricordi. Riprova più tardi.'));
    var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
    retry.type = 'button';
    retry.addEventListener('click', ricarica);
    lista.appendChild(retry);
  }

  function rendiLista(lista, dati, ricarica) {
    clearEl(lista);
    var ricordi = dati.memories || [];
    var totale = dati.total != null ? dati.total : ricordi.length;
    var mostrati = dati.shown != null ? dati.shown : ricordi.length;

    if (!ricordi.length) {
      lista.appendChild(el('p', 'field-hint',
        'Nessun ricordo salvato — quando dici a HIRIS «ricordati che…», comparirà qui.'));
      return;
    }

    /* Il taglio a `_MEMORIES_SHOWN_LIMIT` si dichiara: senza questa
       riga un ricordo oltre il taglio è invisibile, indistinguibile da uno
       cancellato (handlers_memoria.py, regola 3). */
    lista.appendChild(el('p', 'field-hint', mostrati < totale
      ? ('Stai vedendo i ' + mostrati + ' ricordi più recenti su ' + totale + ' in tutto.')
      : (totale === 1 ? '1 ricordo.' : totale + ' ricordi.')));

    ricordi.forEach(function (r) { lista.appendChild(costruisciCard(r, ricarica)); });
  }

  function carica() {
    var lista = byId('memoria-list');
    if (!lista) return;
    clearEl(lista);
    lista.appendChild(el('p', 'field-hint', 'Caricamento…'));
    return fetch('api/memories').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (dati) {
      if (!dati.available) { rendiNonDisponibile(lista); return; }
      rendiLista(lista, dati, carica);
    }).catch(function (err) {
      console.error('[memoria] caricamento fallito', err);
      rendiErrore(lista, carica);
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Memoria'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Ciò che hai detto a HIRIS, e cosa ne ha capito. Puoi correggere l’interpretazione — mai il ' +
      'testo — o cancellare un ricordo per sempre.'));
    var status = el('p', 'sc-desc', '');
    status.id = 'memoria-status';
    outlet.appendChild(status);
    var lista = el('div');
    lista.id = 'memoria-list';
    outlet.appendChild(lista);
    carica();
  }

  return { mount: mount };
})();
