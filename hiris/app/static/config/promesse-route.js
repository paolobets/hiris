/* HIRIS · Configurazione · «Promesse» (route #/promesse)

   La terza condizione della spec dello Schedulatore (docs/design/2026-08-19-
   lo-schedulatore.md, §10): «Si vede. Un posto dove guardare cosa e' in
   sospeso e annullarlo. Promesse che HIRIS tiene e non mostra sarebbero
   stato invisibile.» Questa pagina e' quel posto: legge l'archivio vero
   (`GET /api/agenda?all=1`, `hiris/app/api/handlers_promesse.py`) e
   lascia disdire cio' che non e' ancora scattato (`DELETE
   /api/agenda/{id}`).

   UNA sola GET, filtrata qui per `stato`: lo stato di una promessa e' un
   campo della stessa lista, non due mondi -- due sezioni («In sospeso»,
   «Storico»), una richiesta.

   Il vocabolario mostrato non e' quello del backend (guida di disegno,
   scritta da ux-ui-specialist dopo aver letto handlers_promesse.py e
   archivio.py): `saltata` -> «Non eseguita», `fallita` -> «Non riuscita».
   Sono scelte apposta per non fare rima e non condividere la prima parola --
   la stessa distinzione che la spec (§7) chiama «non e' un guasto, e' la
   Legge del mai-in-ritardo»: una promessa scaduta oltre tolleranza non
   diventa un errore rosso, resta una decisione ambra del prodotto. Il vero
   fallimento (`fallita`, un `fai` che ha provato ed e' andato male) e' l'unico
   che porta il rosso.

   Tre cose che la guida chiede esplicitamente:
   1. `in_corso` sta nella sezione «In sospeso» insieme a `in_attesa` (non e'
      ancora concluso), ma SOLO `in_attesa` ha il bottone disdici:
      `archivio.disdici()` scrive `WHERE stato='in_attesa'`, quindi un
      bottone su una riga `in_corso` sarebbe piu' confuso di nessun bottone.
   2. Nessun `window.confirm()`: disdire non distrugge niente, la riga passa
      allo storico con `stato:'disdetta'`, resta leggibile per sempre ed e'
      reversibile chiedendo di nuovo a voce -- diverso dalla cancellazione di
      un ricordo in memoria-route.js, che e' per sempre.
   3. La DELETE riuscita risponde 200 con {"promessa": {...}}, MAI 204 come
      /api/memories/{id}: chi copia `res.status === 204` da li' legge un
      successo come un fallimento.

   Sicurezza: testi via textContent/createElement, mai innerHTML su dati
   server (stessa disciplina di memoria-route.js/models-route.js) -- la
   frase e il testo di una promessa sono stati scritti in chat.

   «Cosa e' cambiato» (review finale, rilievo ①): un `fai` mantenuto porta
   un `esecuzione_id`, e la riga si collega alla cronaca PER IDENTIFICATORE
   (`GET /api/executions/{id}`, spec §8) -- non ne ricopia mai i fatti dentro
   `serializza()`. Caricata A RICHIESTA quando l'utente apre quella riga, non
   all'apertura della pagina: con N righe nello storico sarebbe una richiesta
   per riga. E' l'unico posto di questa pagina in cui un dettaglio sta dietro
   un click (la guida di disegno §8.2 lo vieta per `motivo`/`istantanea`, che
   pero' arrivano gia' dentro il payload della promessa senza costo aggiuntivo
   -- qui il costo e' una richiesta di rete per riga, e quello va evitato
   all'apertura). Il bottone e' un `<button>` semplice: raggiungibile da
   tastiera e con il focus visibile del browser di serie, stessa disciplina
   del bottone «Disdici» qui sotto -- nessun sistema nuovo. Un 404 (riga
   potata dopo 90 giorni, `azione/cronaca.py::CONSERVAZIONE_ESECUZIONI_S`) si
   dichiara onestamente dentro il pannello; un guasto di rete passa dalla
   riga di stato di pagina (`setStatus`), come ogni altro guasto di rete qui.
   L'`avviso` della porta (`azione/porta.py`) non si appiattisce MAI in
   «niente e' cambiato»: e' un fatto dichiarato su cio' che HIRIS ha potuto
   vedere, e si mostra verbatim. */
window.HirisPromesseRoute = (function () {
  'use strict';

  /* Vocabolario dell'interfaccia (guida di disegno §0), diverso dai nomi
     tecnici di `stato` in archivio: non toccare senza rileggere quella
     guida, la distinzione non e' un dettaglio estetico. */
  var STATO_LABEL = {
    in_attesa: 'In attesa',
    in_corso: 'In corso',
    mantenuta: 'Mantenuta',
    saltata: 'Non eseguita',
    fallita: 'Non riuscita',
    disdetta: 'Disdetta'
  };
  var STATO_BADGE = {
    in_attesa: 'badge-off',
    in_corso: 'badge-on',
    mantenuta: 'badge-on',
    saltata: 'badge-warn',
    fallita: 'badge-err',
    disdetta: 'badge-off'
  };
  var STATI_SOSPESO = ['in_attesa', 'in_corso'];

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

  function setStatus(testo) {
    var s = byId('promesse-status');
    if (s) s.textContent = testo || '';
  }

  /* ── Date e ore (guida §4): sempre da `quando_ts`, mai da `quando_detto`
     -- quello e' gia' dentro la `frase` verbatim. Il fuso non si mostra:
     `new Date(ts*1000)` legge gia' quello del browser di chi guarda. ──── */
  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function fmtOraAssoluta(d) {
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  function eOggi(d) {
    var ora = new Date();
    return d.getFullYear() === ora.getFullYear() && d.getMonth() === ora.getMonth() &&
      d.getDate() === ora.getDate();
  }

  function fmtAssoluto(ts) {
    var d = new Date(ts * 1000);
    var ora = fmtOraAssoluta(d);
    return eOggi(d) ? ('oggi alle ' + ora) : (pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + ', ' + ora);
  }

  /* Intl.RelativeTimeFormat, API nativa (nessuna libreria, nessun build
     step): sotto l'ora si arrotonda ai minuti, sopra alle ore -- risponde
     alla domanda vera di "In sospeso", "quanto manca". La guida mostra
     l'esempio con la parola «fra»; l'ICU di questo motore la scrive «tra»
     (sinonimo, stessa lingua) -- si preferisce l'uscita nativa dell'API
     invece di ricomporre a mano una frase che l'API gia' costruisce intera,
     comprese le forme limite ("questo minuto", "1 ora fa"). */
  var RTF = (typeof Intl !== 'undefined' && Intl.RelativeTimeFormat)
    ? new Intl.RelativeTimeFormat('it', { numeric: 'auto' }) : null;

  function fmtRelativo(ts) {
    if (!RTF) return '';
    var diffS = ts - (Date.now() / 1000);
    if (Math.abs(diffS) < 3600) return RTF.format(Math.round(diffS / 60), 'minute');
    return RTF.format(Math.round(diffS / 3600), 'hour');
  }

  /* Il colore del TESTO del motivo porta il significato, non solo il badge
     (guida §3, stesso principio di rendiAncore in memoria-route.js): rosso
     solo per un vero fallimento, ambra per tutto il resto (compresa la
     nota su una "mantenuta" con motivo -- §6 della spec). */
  function coloreMotivo(stato) {
    return stato === 'fallita' ? 'var(--err-ink)' : 'var(--warn-ink)';
  }

  function formattaIstantanea(istantanea) {
    if (!istantanea || !istantanea.length) return null;
    return istantanea.map(function (m) {
      return (m.entita || '?') + ' ' + m.valore + (m.unita ? ' ' + m.unita : '');
    }).join(' · ');
  }

  function formattaElencoEntita(elenco) {
    return (elenco && elenco.length) ? elenco.join(', ') : null;
  }

  /* Il contenuto del pannello «Cosa è cambiato» (review finale, rilievo ①):
     legge la riga di `GET /api/executions/{id}` cosi' com'e', senza
     ricostruire un'altra forma -- la cronaca gia' porta `servizio`,
     `entita`, `cambiato`, `avviso`, `errore` (`azione/cronaca.py::_riga`).

     Il caso «cambiato è vuoto» (guida generale del progetto, non della
     pagina: il rilievo la richiama esplicitamente) NON diventa mai «niente
     è cambiato» in silenzio: l'`avviso` della porta e' un fatto dichiarato
     su cio' che HIRIS ha potuto vedere (non ho guardato in tempo / ho
     guardato e non e' arrivato niente entro la scadenza / e' cambiato
     qualcosa che non so mostrare), e si mostra SEMPRE quando c'e', verbatim
     e senza riformularlo -- riformularlo rischierebbe di appiattire
     esattamente la distinzione per cui quel campo esiste. */
  function rendiDettaglioEsecuzione(pannello, esecuzione) {
    clearEl(pannello);
    if (esecuzione.errore) {
      var errore = el('p', null, esecuzione.errore);
      errore.style.cssText = 'font-size:var(--fs-14);color:var(--err-ink);margin:4px 0 0';
      pannello.appendChild(errore);
    }
    var cambiate = formattaElencoEntita(esecuzione.cambiato);
    if (cambiate) {
      var riga1 = el('p', null, 'Cambiate: ' + cambiate);
      riga1.style.cssText = 'font-size:var(--fs-14);color:var(--text);margin:4px 0 0';
      pannello.appendChild(riga1);
    }
    if (esecuzione.avviso) {
      var avviso = el('p', null, esecuzione.avviso);
      avviso.style.cssText = 'font-size:var(--fs-13);color:var(--warn-ink);margin:4px 0 0';
      pannello.appendChild(avviso);
    } else if (!cambiate && !esecuzione.errore) {
      // Difensivo: nella porta attuale (`azione/porta.py`) un `cambiato`
      // vuoto porta SEMPRE un `avviso` -- questo ramo non dovrebbe mai
      // rendersi oggi, ma se un domani smettesse di esserlo, tacere
      // sarebbe di nuovo il difetto che questo rilievo chiude.
      pannello.appendChild(el('p', 'field-hint', 'Nessuna nota su cosa sia cambiato.'));
    }
    var toccate = formattaElencoEntita(esecuzione.entita);
    if (toccate) pannello.appendChild(el('div', 'field-hint', 'Toccate: ' + toccate));
  }

  /* Il bottone «Cosa è cambiato» di una riga storico `fai` mantenuta
     (review finale, rilievo ①). Condizione esatta -- non "ogni riga con
     esecuzione_id": la spec (§8) mostra questo caso per un `fai`, ed e' il
     solo in cui la sfumatura vale la richiesta in piu' -- una `chiedi`
     mantenuta mostra gia' la sua risposta (§6), e per un `fai` `fallita` il
     `motivo` che l'utente vede e' gia' `esito.errore` (`orologio.py::
     _mantieni_fai`): la stessa frase, non un secondo dettaglio da aprire. */
  function aggiungiDettaglioEsecuzione(riga, p) {
    if (!(p.specie === 'fai' && p.stato === 'mantenuta' && p.esecuzione_id)) return;

    var gruppo = el('div', 'field-group');
    gruppo.style.marginTop = '8px';
    var testoChiuso = 'Cosa è cambiato';
    var testoAperto = 'Nascondi il dettaglio';
    var btn = el('button', 'btn btn-ghost btn-sm', testoChiuso);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');
    var pannello = el('div');
    pannello.style.marginTop = '6px';
    pannello.hidden = true;
    var idPannello = 'esec-' + p.id;
    pannello.id = idPannello;
    btn.setAttribute('aria-controls', idPannello);
    var caricato = false;

    btn.addEventListener('click', function () {
      var aperto = btn.getAttribute('aria-expanded') === 'true';
      if (aperto) {
        pannello.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = testoChiuso;
        return;
      }
      if (caricato) {
        pannello.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = testoAperto;
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Verifica…';
      fetch('api/executions/' + encodeURIComponent(p.esecuzione_id)).then(function (res) {
        if (res.status === 404) {
          clearEl(pannello);
          pannello.appendChild(el('p', 'field-hint', 'Non ne ho più il dettaglio.'));
          caricato = true;
          return;
        }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json().then(function (corpo) {
          rendiDettaglioEsecuzione(pannello, corpo.execution);
          caricato = true;
        });
      }).then(function () {
        btn.disabled = false;
        pannello.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = testoAperto;
      }, function () {
        // Guasto di rete: stessa riga di stato di pagina di ogni altro
        // guasto qui (§7 della guida), non un pannello mezzo scritto. Il
        // bottone torna chiuso cosi' un nuovo click riprova da capo.
        btn.disabled = false;
        btn.textContent = testoChiuso;
        setStatus('HIRIS non ha risposto. Riprova più tardi.');
      });
    });

    gruppo.appendChild(btn);
    gruppo.appendChild(pannello);
    riga.appendChild(gruppo);
  }

  /* ── Una riga «in sospeso» (guida §2, §5) ────────────────────────────── */
  function costruisciRigaSospeso(p, ricarica) {
    var riga = el('div');
    riga.style.cssText = 'border-top:1px solid var(--border);padding:10px 0;' +
      'display:flex;justify-content:space-between;align-items:flex-start;gap:var(--sp-3)';

    var corpo = el('div');
    corpo.appendChild(el('div', 'field-hint', fmtAssoluto(p.quando_ts) + ' · ' + fmtRelativo(p.quando_ts)));
    var frase = el('p', null, p.frase);
    frase.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:2px 0 0';
    corpo.appendChild(frase);
    corpo.appendChild(el('div', 'field-hint', p.specie));
    riga.appendChild(corpo);

    /* Condizione ESATTA `stato === 'in_attesa'`, non "riga in questa
       sezione": `in_corso` ci sta (non e' ancora concluso) ma non e'
       disdicibile (`archivio.disdici` scrive WHERE stato='in_attesa'). */
    if (p.stato === 'in_attesa') {
      var btn = el('button', 'btn btn-ghost btn-ghost-danger btn-sm', 'Disdici');
      btn.type = 'button';
      btn.setAttribute('data-disdici', p.id);
      btn.addEventListener('click', function () {
        btn.disabled = true;
        api('api/agenda/' + encodeURIComponent(p.id), { method: 'DELETE' })
          .then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (corpo2) {
              return { res: res, corpo: corpo2 };
            });
          })
          .then(function (esito) {
            /* Trappola dichiarata dalla guida: la DELETE riuscita risponde
               200 con un corpo, MAI 204 come /api/memories/{id} -- si
               guarda `res.ok`, non uno status specifico. 404 e 409
               arrivano gia' col testo giusto dal server (handlers_
               promesse.py / archivio.py::disdici): si mostra quello,
               verbatim, non un errore generico -- dicono cose diverse
               (non esiste vs. gia' concluso) e l'utente deve poterle
               distinguere. */
            setStatus(esito.res.ok ? 'Promessa disdetta.' :
              ((esito.corpo && esito.corpo.error) || ('Errore HTTP ' + esito.res.status)));
            ricarica();
          }, function () {
            btn.disabled = false;
            setStatus('HIRIS non ha risposto. Riprova più tardi.');
          });
      });
      riga.appendChild(btn);
    }
    return riga;
  }

  /* ── Una riga «storico» (guida §2, §3, §6) ───────────────────────────── */
  function costruisciRigaStorico(p) {
    var riga = el('div');
    riga.style.cssText = 'border-top:1px solid var(--border);padding:10px 0';

    riga.appendChild(el('div', 'field-hint', fmtAssoluto(p.quando_ts)));
    var frase = el('p', null, p.frase);
    frase.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:2px 0 8px';
    riga.appendChild(frase);

    riga.appendChild(el('span', 'agent-badge ' + (STATO_BADGE[p.stato] || 'badge-off'),
      STATO_LABEL[p.stato] || p.stato));

    if (p.motivo) {
      var motivo = el('p', null, p.motivo);
      motivo.style.cssText = 'font-size:var(--fs-13);margin:6px 0 0;color:' + coloreMotivo(p.stato);
      riga.appendChild(motivo);
    }

    /* Il blocco risposta di un `chiedi` mantenuto: e' cio' che l'utente e'
       venuto a cercare, peso visivo proprio, mai dietro un click (guida
       §6, §8.2) -- anche quando HIRIS ha concluso "in silenzio"
       (`avvisare:false`): questa pagina e' di sola lettura, quindi non
       importa se non e' arrivata una notifica. */
    if (p.specie === 'chiedi' && p.stato === 'mantenuta' && p.testo) {
      var gruppo = el('div', 'field-group');
      gruppo.style.marginTop = '8px';
      gruppo.appendChild(el('div', 'fg-label', 'HIRIS ha risposto'));
      var risposta = el('p', null, p.testo);
      risposta.style.cssText = 'font-size:var(--fs-14);color:var(--text);margin-top:4px';
      gruppo.appendChild(risposta);
      var basatoSu = formattaIstantanea(p.istantanea);
      if (basatoSu) gruppo.appendChild(el('div', 'field-hint', 'Basato su: ' + basatoSu));
      riga.appendChild(gruppo);
    }

    aggiungiDettaglioEsecuzione(riga, p);

    return riga;
  }

  function ordinaSospeso(lista) {
    return lista.slice().sort(function (a, b) { return a.quando_ts - b.quando_ts; });
  }
  function ordinaStorico(lista) {
    return lista.slice().sort(function (a, b) { return b.quando_ts - a.quando_ts; });
  }
  function descrizioneSospeso(n) { return n === 0 ? 'Nessuna in sospeso.' : (n + ' in sospeso.'); }
  function descrizioneStorico(n) { return n === 0 ? 'Nessuna promessa nello storico.' : (n + ' nello storico.'); }

  function rendiSospeso(corpo, desc, lista, ricarica) {
    clearEl(corpo);
    desc.textContent = descrizioneSospeso(lista.length);
    if (!lista.length) {
      corpo.appendChild(el('p', 'field-hint',
        'Nessuna promessa in sospeso — quando dici a HIRIS «fra un\'ora…» o «alle…», comparirà qui.'));
      return;
    }
    ordinaSospeso(lista).forEach(function (p) { corpo.appendChild(costruisciRigaSospeso(p, ricarica)); });
  }

  function rendiStorico(corpo, desc, lista) {
    clearEl(corpo);
    desc.textContent = descrizioneStorico(lista.length);
    if (!lista.length) {
      corpo.appendChild(el('p', 'field-hint', 'Nessuna promessa nello storico.'));
      return;
    }
    ordinaStorico(lista).forEach(function (p) { corpo.appendChild(costruisciRigaStorico(p)); });
  }

  /* Un errore di lettura e una lista vuota vera NON hanno lo stesso testo
     (guida §7): un guasto non deve poter sembrare "non hai promesse". Copre
     anche il 503 di `handle_get_promesse` (archivio non disponibile), che
     manda gia' `promesse: []` dentro un corpo comunque non-2xx: basta
     guardare `r.ok`, non serve leggere un campo apposito. */
  function rendiErrore(sospesoCorpo, storicoCorpo, ricarica) {
    [sospesoCorpo, storicoCorpo].forEach(function (nodo) {
      clearEl(nodo);
      nodo.appendChild(el('p', 'proposals-error', 'Non è stato possibile leggere le promesse. Riprova più tardi.'));
      var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      retry.type = 'button';
      retry.addEventListener('click', ricarica);
      nodo.appendChild(retry);
    });
  }

  function carica() {
    var sospesoCorpo = byId('promesse-sospeso-body');
    var storicoCorpo = byId('promesse-storico-body');
    var sospesoDesc = byId('promesse-sospeso-desc');
    var storicoDesc = byId('promesse-storico-desc');
    if (!sospesoCorpo || !storicoCorpo) return;
    clearEl(sospesoCorpo); sospesoCorpo.appendChild(el('p', 'field-hint', 'Caricamento…'));
    clearEl(storicoCorpo); storicoCorpo.appendChild(el('p', 'field-hint', 'Caricamento…'));
    return fetch('api/agenda?all=1').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (dati) {
      var tutte = dati.agenda || [];
      var sospeso = tutte.filter(function (p) { return STATI_SOSPESO.indexOf(p.stato) !== -1; });
      var storico = tutte.filter(function (p) { return STATI_SOSPESO.indexOf(p.stato) === -1; });
      rendiSospeso(sospesoCorpo, sospesoDesc, sospeso, carica);
      rendiStorico(storicoCorpo, storicoDesc, storico);
    }).catch(function (err) {
      console.error('[promesse] caricamento fallito', err);
      rendiErrore(sospesoCorpo, storicoCorpo, carica);
    });
  }

  /* ── Shell statico: due `.section-card`, stesso pattern di
     `buildSectionShell` in models-route.js. `#promesse-sospeso-body`/
     `#promesse-storico-body` ricevono `gap:0` da hiris-config.css, stesso
     trattamento di `#catena-body`/`#fuori-body`: le righe si separano con
     un `border-top` proprio (guida §2), non col gap del flex. ────────── */
  function buildSectionShell(num, idPrefix, sezioneAttr, titolo) {
    var section = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', titolo));
    section.appendChild(head);
    var desc = el('p', 'sc-desc', '');
    desc.id = 'promesse-' + idPrefix + '-desc';
    section.appendChild(desc);
    var body = el('div', 'sc-body');
    body.id = 'promesse-' + idPrefix + '-body';
    body.setAttribute('data-sezione', sezioneAttr);
    body.appendChild(el('p', 'field-hint', 'Caricamento…'));
    section.appendChild(body);
    return section;
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Promesse'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Ciò che hai chiesto a HIRIS di fare o guardare più tardi, e com’è andata finora.'));
    var status = el('p', 'sc-desc', '');
    status.id = 'promesse-status';
    outlet.appendChild(status);

    /* «In sospeso» sopra: e' la sezione corta, azionabile, ed e' la
       domanda con cui si apre questa pagina piu' spesso. Lo storico e' un
       registro di consultazione, non l'atterraggio (guida §1). */
    outlet.appendChild(buildSectionShell('01', 'sospeso', 'in-sospeso', 'In sospeso'));
    outlet.appendChild(buildSectionShell('02', 'storico', 'storico', 'Storico'));

    carica();
  }

  return { mount: mount };
})();
