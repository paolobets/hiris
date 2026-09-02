/* HIRIS · Configurazione · «Promesse» (route #/promesse)

   La terza condizione della spec dello Schedulatore (docs/design/2026-08-19-
   lo-schedulatore.md, §10): «Si vede. Un posto dove guardare cosa e' in
   sospeso e annullarlo. Promesse che HIRIS tiene e non mostra sarebbero
   stato invisibile.» Questa pagina e' quel posto: legge l'archivio vero
   (`GET /api/agenda?all=1`, `hiris/app/api/handlers_agenda.py`) e
   lascia disdire cio' che non e' ancora scattato (`DELETE
   /api/agenda/{id}`).

   UNA sola GET, filtrata qui per `stato`: lo stato di una promessa e' un
   campo della stessa lista, non due mondi -- due sezioni («In sospeso»,
   «Storico»), una richiesta.

   Il vocabolario mostrato non e' quello del backend (guida di disegno,
   scritta da ux-ui-specialist dopo aver letto handlers_agenda.py e
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
      `archivio.cancel()` scrive `WHERE stato='in_attesa'`, quindi un
      bottone su una riga `in_corso` sarebbe piu' confuso di nessun bottone.
   2. Nessun `window.confirm()`: disdire non distrugge niente, la riga passa
      allo storico con `stato:'disdetta'`, resta leggibile per sempre ed e'
      reversibile chiedendo di nuovo a voce -- diverso dalla cancellazione di
      un ricordo in memory-route.js, che e' per sempre.
   3. La DELETE riuscita risponde 200 con {"promessa": {...}}, MAI 204 come
      /api/memories/{id}: chi copia `res.status === 204` da li' legge un
      successo come un fallimento.

   Sicurezza: testi via textContent/createElement, mai innerHTML su dati
   server (stessa disciplina di memory-route.js/models-route.js) -- la
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
   potata dopo 90 giorni, `azione/cronaca.py::EXECUTIONS_RETENTION_S`) si
   dichiara onestamente dentro il pannello; un guasto di rete passa dalla
   riga di stato di pagina (`setStatus`), come ogni altro guasto di rete qui.
   L'`avviso` della porta (`azione/porta.py`) non si appiattisce MAI in
   «niente e' cambiato»: e' un fatto dichiarato su cio' che HIRIS ha potuto
   vedere, e si mostra verbatim. */
window.HirisAgendaRoute = (function () {
  'use strict';

  /* Vocabolario dell'interfaccia (guida di disegno §0), diverso dai nomi
     tecnici di `stato` in archivio: non toccare senza rileggere quella
     guida, la distinzione non e' un dettaglio estetico. */
  var STATE_LABEL = {
    in_attesa: 'In attesa',
    in_corso: 'In corso',
    mantenuta: 'Mantenuta',
    saltata: 'Non eseguita',
    fallita: 'Non riuscita',
    disdetta: 'Disdetta'
  };
  var STATE_BADGE = {
    in_attesa: 'badge-off',
    in_corso: 'badge-on',
    mantenuta: 'badge-on',
    saltata: 'badge-warn',
    fallita: 'badge-err',
    disdetta: 'badge-off'
  };
  var PENDING_STATES = ['in_attesa', 'in_corso'];

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
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

  function setStatus(text) {
    var s = byId('promesse-status');
    if (s) s.textContent = text || '';
  }

  /* ── Date e ore (guida §4): sempre da `quando_ts`, mai da `quando_detto`
     -- quello e' gia' dentro la `frase` verbatim. Il fuso non si mostra:
     `new Date(ts*1000)` legge gia' quello del browser di chi guarda. ──── */
  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function fmtAbsoluteTime(d) {
    return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  function isToday(d) {
    var hour = new Date();
    return d.getFullYear() === hour.getFullYear() && d.getMonth() === hour.getMonth() &&
      d.getDate() === hour.getDate();
  }

  function fmtAbsolute(ts) {
    var d = new Date(ts * 1000);
    var hour = fmtAbsoluteTime(d);
    return isToday(d) ? ('oggi alle ' + hour) : (pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + ', ' + hour);
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

  function fmtRelative(ts) {
    if (!RTF) return '';
    var diffS = ts - (Date.now() / 1000);
    if (Math.abs(diffS) < 3600) return RTF.format(Math.round(diffS / 60), 'minute');
    return RTF.format(Math.round(diffS / 3600), 'hour');
  }

  /* Il colore del TESTO del motivo porta il significato, non solo il badge
     (guida §3, stesso principio di rendiAncore in memory-route.js): rosso
     solo per un vero fallimento, ambra per tutto il resto (compresa la
     nota su una "mantenuta" con motivo -- §6 della spec). */
  function reasonColor(state) {
    return state === 'fallita' ? 'var(--err-ink)' : 'var(--warn-ink)';
  }

  function formatSnapshot(snapshot) {
    if (!snapshot || !snapshot.length) return null;
    return snapshot.map(function (m) {
      return (m.entita || '?') + ' ' + m.valore + (m.unita ? ' ' + m.unita : '');
    }).join(' · ');
  }

  function formatEntityList(list) {
    return (list && list.length) ? list.join(', ') : null;
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
  function renderExecutionDetail(panel, execution) {
    clearEl(panel);
    if (execution.errore) {
      var error = el('p', null, execution.errore);
      error.style.cssText = 'font-size:var(--fs-14);color:var(--err-ink);margin:4px 0 0';
      panel.appendChild(error);
    }
    var changed = formatEntityList(execution.cambiato);
    if (changed) {
      var riga1 = el('p', null, 'Cambiate: ' + changed);
      riga1.style.cssText = 'font-size:var(--fs-14);color:var(--text);margin:4px 0 0';
      panel.appendChild(riga1);
    }
    if (execution.avviso) {
      var notice = el('p', null, execution.avviso);
      notice.style.cssText = 'font-size:var(--fs-13);color:var(--warn-ink);margin:4px 0 0';
      panel.appendChild(notice);
    } else if (!changed && !execution.errore) {
      // Difensivo: nella porta attuale (`azione/porta.py`) un `cambiato`
      // vuoto porta SEMPRE un `avviso` -- questo ramo non dovrebbe mai
      // rendersi oggi, ma se un domani smettesse di esserlo, tacere
      // sarebbe di nuovo il difetto che questo rilievo chiude.
      panel.appendChild(el('p', 'field-hint', 'Nessuna nota su cosa sia cambiato.'));
    }
    var touched = formatEntityList(execution.entita);
    if (touched) panel.appendChild(el('div', 'field-hint', 'Toccate: ' + touched));
  }

  /* Il bottone «Cosa è cambiato» di una riga storico `fai` mantenuta
     (review finale, rilievo ①). Condizione esatta -- non "ogni riga con
     esecuzione_id": la spec (§8) mostra questo caso per un `fai`, ed e' il
     solo in cui la sfumatura vale la richiesta in piu' -- una `chiedi`
     mantenuta mostra gia' la sua risposta (§6), e per un `fai` `fallita` il
     `motivo` che l'utente vede e' gia' `esito.errore` (`orologio.py::
     _mantieni_fai`): la stessa frase, non un secondo dettaglio da aprire. */
  function addExecutionDetail(line, p) {
    if (!(p.specie === 'fai' && p.stato === 'mantenuta' && p.esecuzione_id)) return;

    var group = el('div', 'field-group');
    group.style.marginTop = '8px';
    var closedText = 'Cosa è cambiato';
    var openText = 'Nascondi il dettaglio';
    var btn = el('button', 'btn btn-ghost btn-sm', closedText);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false');
    var panel = el('div');
    panel.style.marginTop = '6px';
    panel.hidden = true;
    var panelId = 'esec-' + p.id;
    panel.id = panelId;
    btn.setAttribute('aria-controls', panelId);
    var loaded = false;

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      if (open) {
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        btn.textContent = closedText;
        return;
      }
      if (loaded) {
        panel.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = openText;
        return;
      }
      btn.disabled = true;
      btn.textContent = 'Verifica…';
      fetch('api/executions/' + encodeURIComponent(p.esecuzione_id)).then(function (res) {
        if (res.status === 404) {
          clearEl(panel);
          panel.appendChild(el('p', 'field-hint', 'Non ne ho più il dettaglio.'));
          loaded = true;
          return;
        }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json().then(function (body) {
          renderExecutionDetail(panel, body.execution);
          loaded = true;
        });
      }).then(function () {
        btn.disabled = false;
        panel.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        btn.textContent = openText;
      }, function () {
        // Guasto di rete: stessa riga di stato di pagina di ogni altro
        // guasto qui (§7 della guida), non un pannello mezzo scritto. Il
        // bottone torna chiuso cosi' un nuovo click riprova da capo.
        btn.disabled = false;
        btn.textContent = closedText;
        setStatus('HIRIS non ha risposto. Riprova più tardi.');
      });
    });

    group.appendChild(btn);
    group.appendChild(panel);
    line.appendChild(group);
  }

  /* ── Una riga «in sospeso» (guida §2, §5) ────────────────────────────── */
  function buildPendingRow(p, reload) {
    var line = el('div');
    line.style.cssText = 'border-top:1px solid var(--border);padding:10px 0;' +
      'display:flex;justify-content:space-between;align-items:flex-start;gap:var(--sp-3)';

    var body = el('div');
    body.appendChild(el('div', 'field-hint', fmtAbsolute(p.quando_ts) + ' · ' + fmtRelative(p.quando_ts)));
    var phrase = el('p', null, p.frase);
    phrase.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:2px 0 0';
    body.appendChild(phrase);
    body.appendChild(el('div', 'field-hint', p.specie));
    line.appendChild(body);

    /* Condizione ESATTA `stato === 'in_attesa'`, non "riga in questa
       sezione": `in_corso` ci sta (non e' ancora concluso) ma non e'
       disdicibile (`archivio.cancel` scrive WHERE stato='in_attesa'). */
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
          .then(function (occurrence) {
            /* Trappola dichiarata dalla guida: la DELETE riuscita risponde
               200 con un corpo, MAI 204 come /api/memories/{id} -- si
               guarda `res.ok`, non uno status specifico. 404 e 409
               arrivano gia' col testo giusto dal server (handlers_
               promesse.py / archivio.py::disdici): si mostra quello,
               verbatim, non un errore generico -- dicono cose diverse
               (non esiste vs. gia' concluso) e l'utente deve poterle
               distinguere. */
            setStatus(occurrence.res.ok ? 'Promessa disdetta.' :
              ((occurrence.corpo && occurrence.corpo.error) || ('Errore HTTP ' + occurrence.res.status)));
            reload();
          }, function () {
            btn.disabled = false;
            setStatus('HIRIS non ha risposto. Riprova più tardi.');
          });
      });
      line.appendChild(btn);
    }
    return line;
  }

  /* ── Una riga «storico» (guida §2, §3, §6) ───────────────────────────── */
  function buildHistoryRow(p) {
    var line = el('div');
    line.style.cssText = 'border-top:1px solid var(--border);padding:10px 0';

    line.appendChild(el('div', 'field-hint', fmtAbsolute(p.quando_ts)));
    var phrase = el('p', null, p.frase);
    phrase.style.cssText = 'font-size:var(--fs-15);font-weight:500;margin:2px 0 8px';
    line.appendChild(phrase);

    line.appendChild(el('span', 'agent-badge ' + (STATE_BADGE[p.stato] || 'badge-off'),
      STATE_LABEL[p.stato] || p.stato));

    if (p.motivo) {
      var reason = el('p', null, p.motivo);
      reason.style.cssText = 'font-size:var(--fs-13);margin:6px 0 0;color:' + reasonColor(p.stato);
      line.appendChild(reason);
    }

    /* Il blocco risposta di un `chiedi` mantenuto: e' cio' che l'utente e'
       venuto a cercare, peso visivo proprio, mai dietro un click (guida
       §6, §8.2) -- anche quando HIRIS ha concluso "in silenzio"
       (`avvisare:false`): questa pagina e' di sola lettura, quindi non
       importa se non e' arrivata una notifica. */
    if (p.specie === 'chiedi' && p.stato === 'mantenuta' && p.testo) {
      var group = el('div', 'field-group');
      group.style.marginTop = '8px';
      group.appendChild(el('div', 'fg-label', 'HIRIS ha risposto'));
      var answer = el('p', null, p.testo);
      answer.style.cssText = 'font-size:var(--fs-14);color:var(--text);margin-top:4px';
      group.appendChild(answer);
      var basedOn = formatSnapshot(p.istantanea);
      if (basedOn) group.appendChild(el('div', 'field-hint', 'Basato su: ' + basedOn));
      line.appendChild(group);
    }

    addExecutionDetail(line, p);

    return line;
  }

  function sortPending(list) {
    return list.slice().sort(function (a, b) { return a.quando_ts - b.quando_ts; });
  }
  function sortHistory(list) {
    return list.slice().sort(function (a, b) { return b.quando_ts - a.quando_ts; });
  }
  function descrizioneSospeso(n) { return n === 0 ? 'Nessuna in sospeso.' : (n + ' in sospeso.'); }
  function descrizioneStorico(n) { return n === 0 ? 'Nessuna promessa nello storico.' : (n + ' nello storico.'); }

  function renderPending(body, desc, list, reload) {
    clearEl(body);
    desc.textContent = descrizioneSospeso(list.length);
    if (!list.length) {
      body.appendChild(el('p', 'field-hint',
        'Nessuna promessa in sospeso — quando dici a HIRIS «fra un\'ora…» o «alle…», comparirà qui.'));
      return;
    }
    sortPending(list).forEach(function (p) { body.appendChild(buildPendingRow(p, reload)); });
  }

  function renderHistory(body, desc, list) {
    clearEl(body);
    desc.textContent = descrizioneStorico(list.length);
    if (!list.length) {
      body.appendChild(el('p', 'field-hint', 'Nessuna promessa nello storico.'));
      return;
    }
    sortHistory(list).forEach(function (p) { body.appendChild(buildHistoryRow(p)); });
  }

  /* Un errore di lettura e una lista vuota vera NON hanno lo stesso testo
     (guida §7): un guasto non deve poter sembrare "non hai promesse". Copre
     anche il 503 di `handle_get_agenda` (archivio non disponibile), che
     manda gia' `promesse: []` dentro un corpo comunque non-2xx: basta
     guardare `r.ok`, non serve leggere un campo apposito. */
  function renderError(pendingBody, historyBody, reload) {
    [pendingBody, historyBody].forEach(function (node) {
      clearEl(node);
      node.appendChild(el('p', 'proposals-error', 'Non è stato possibile leggere le promesse. Riprova più tardi.'));
      var retry = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      retry.type = 'button';
      retry.addEventListener('click', reload);
      node.appendChild(retry);
    });
  }

  function load() {
    var pendingBody = byId('promesse-sospeso-body');
    var historyBody = byId('promesse-storico-body');
    var pendingDesc = byId('promesse-sospeso-desc');
    var historyDesc = byId('promesse-storico-desc');
    if (!pendingBody || !historyBody) return;
    clearEl(pendingBody); pendingBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    clearEl(historyBody); historyBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    return fetch('api/agenda?all=1').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      var all = data.agenda || [];
      var pending = all.filter(function (p) { return PENDING_STATES.indexOf(p.stato) !== -1; });
      var history = all.filter(function (p) { return PENDING_STATES.indexOf(p.stato) === -1; });
      renderPending(pendingBody, pendingDesc, pending, load);
      renderHistory(historyBody, historyDesc, history);
    }).catch(function (err) {
      console.error('[promesse] caricamento fallito', err);
      renderError(pendingBody, historyBody, load);
    });
  }

  /* ── Shell statico: due `.section-card`, stesso pattern di
     `buildSectionShell` in models-route.js. `#promesse-sospeso-body`/
     `#promesse-storico-body` ricevono `gap:0` da hiris-config.css, stesso
     trattamento di `#catena-body`/`#fuori-body`: le righe si separano con
     un `border-top` proprio (guida §2), non col gap del flex. ────────── */
  function buildSectionShell(num, idPrefix, sectionAttr, title) {
    var section = el('section', 'section-card');
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    section.appendChild(head);
    var desc = el('p', 'sc-desc', '');
    desc.id = 'promesse-' + idPrefix + '-desc';
    section.appendChild(desc);
    var body = el('div', 'sc-body');
    body.id = 'promesse-' + idPrefix + '-body';
    body.setAttribute('data-sezione', sectionAttr);
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

    load();
  }

  return { mount: mount };
})();
