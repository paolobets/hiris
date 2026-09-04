/* HIRIS · «Impegni» (route #/agenda)

   La terza condizione della spec dello Schedulatore (docs/design/2026-08-19-
   lo-schedulatore.md, §10): «Si vede. Un posto dove guardare cosa e' in
   sospeso e annullarlo. Promesse che HIRIS tiene e non mostra sarebbero
   stato invisibile.»
   [La parola «Promesse» qui dentro NON si rinomina in «Impegni»: e' una
   citazione verbatim della spec dello Schedulatore, e una citazione
   corretta a posteriori smette di essere una citazione. La pagina si chiama
   Impegni dal 03/09; la frase che la motivo' resta quella che fu scritta.]
   Questa pagina e' quel posto: legge l'archivio vero
   (`GET /api/agenda?all=1`, `hiris/app/api/handlers_agenda.py`) e
   lascia disdire cio' che non e' ancora scattato (`DELETE
   /api/agenda/{id}`).

   UNA sola GET, filtrata qui per `stato`: lo stato di una promessa e' un
   campo della stessa lista, non due mondi -- tre sezioni («Esiti da
   leggere», «In sospeso», «Storico»), una richiesta.

   «Esiti da leggere» (fetta «i menu esecutivi»): il pallino del menu conta,
   su questa voce, gli esiti conclusi che nessuno ha ancora letto
   (`GET /api/pending` -> `agenda_unread`, `api/handlers_pending.py`), non
   gli impegni in sospeso -- quelli aspettano l'ora, non te. Il pallino manda
   qui: se cio' che lo ha acceso finisse dentro uno «Storico» chiuso a
   chiave, avrebbe mentito una seconda volta, stavolta sulla strada. Percio'
   quelle righe hanno una sezione propria, in cima, e lo «Storico» -- che
   e' un registro di consultazione, non l'atterraggio -- nasce chiuso.
   Non e' un quarto contenitore: le stesse righe stanno ANCHE nello storico
   (e' un affaccio sulla sua testa), quindi «Esiti da leggere» non toglie
   niente a nessuno e sparisce quando non ha piu' niente da dire.

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
   potata dopo 90 giorni, `action/journal.py::EXECUTIONS_RETENTION_S`) si
   dichiara onestamente dentro il pannello; un guasto di rete passa dalla
   riga di stato di pagina (`setStatus`), come ogni altro guasto di rete qui.
   L'`avviso` della porta (`action/actuator.py`) non si appiattisce MAI in
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
    var s = byId('agenda-status');
    if (s) s.textContent = text || '';
  }

  /* Lo stato di un rivelatore scritto in un posto solo: `hidden` sul
     pannello e `aria-expanded` sul bottone che lo governa non possono
     divergere se nessuno li assegna separatamente -- ed e' proprio la
     divergenza (il pannello aperto e lo screen reader che lo annuncia
     chiuso) il difetto che questa riga rende impossibile. Lo usano tutti e
     due i rivelatori della pagina, l'intestazione dello «Storico» e il
     pannello «Cosa è cambiato»: un secondo meccanismo sarebbe un doppione.
     Gemello di `constructions-route.js::setDisclosure` -- non condiviso in
     `config/api.js` perche' i test caricano ciascuna route DA SOLA, senza
     quel file (vedi la nota nel rapporto della fetta). */
  function setDisclosure(btn, panel, open) {
    panel.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
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
     `entita`, `cambiato`, `avviso`, `errore` (`action/journal.py::_riga`).

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
      // Difensivo: nella porta attuale (`action/actuator.py`) un `cambiato`
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
    var panel = el('div');
    panel.style.marginTop = '6px';
    var panelId = 'execution-' + p.id;
    panel.id = panelId;
    btn.setAttribute('aria-controls', panelId);
    setDisclosure(btn, panel, false);
    var loaded = false;

    btn.addEventListener('click', function () {
      var open = btn.getAttribute('aria-expanded') === 'true';
      if (open) {
        setDisclosure(btn, panel, false);
        btn.textContent = closedText;
        return;
      }
      if (loaded) {
        setDisclosure(btn, panel, true);
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
        setDisclosure(btn, panel, true);
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

  /* ── Una riga conclusa (guida §2, §3, §6) ────────────────────────────────
     La usano tutte e due le sezioni di righe concluse, «Esiti da leggere» e
     «Storico»: un esito non letto E' una riga conclusa a tutti gli effetti,
     e un terzo costruttore di riga sarebbe solo un secondo posto in cui
     dimenticare di aggiornare il vocabolario.

     Una promessa conclusa e non letta viene disegnata DUE volte -- una volta
     per sezione -- ma il rivelatore «Cosa è cambiato» sta su UNA copia sola,
     quella piu' in alto: possiede un `id` (`aria-controls` di due bottoni
     punterebbe allo stesso pannello) e possiede una cache di rete, e due
     copie vorrebbero dire due richieste per la stessa cronaca. Lo decide
     `conDettaglio`, che il chiamante mette a falso sulla copia dello storico
     quando la stessa riga sta gia' in «Esiti da leggere». ───────────────── */
  function buildHistoryRow(p, conDettaglio) {
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

    if (conDettaglio) addExecutionDetail(line, p);

    return line;
  }

  function sortPending(list) {
    return list.slice().sort(function (a, b) { return a.quando_ts - b.quando_ts; });
  }
  function sortHistory(list) {
    return list.slice().sort(function (a, b) { return b.quando_ts - a.quando_ts; });
  }
  function descrizioneSospeso(n) { return n === 0 ? 'Nessuna in sospeso.' : (n + ' in sospeso.'); }
  /* Il conteggio dello storico e' passato NEL TITOLO (`Storico (14)`): da
     quando lo storico nasce chiuso, il titolo e' l'unica riga che si vede
     sempre, e il numero deve stare li'. Questa descrizione dice cosa c'e'
     dentro, non quanto -- ripetere il numero a due centimetri da se stesso
     sarebbe un doppione visibile all'utente. */
  function descrizioneStorico(n) {
    return n === 0 ? 'Nessuna promessa nello storico.'
      : 'Ciò che è già successo, dal più recente.';
  }
  function descrizioneDaLeggere(n) {
    return n === 1 ? 'Un esito concluso da quando non guardavi.'
      : (n + ' esiti conclusi da quando non guardavi.');
  }

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

  /* `giaSopra`: gli id gia' disegnati in «Esiti da leggere». Le righe si
     ripetono (lo storico e' il registro completo, la sezione in cima e' un
     affaccio sulla sua testa che si svuota man mano che si legge), il
     rivelatore no -- vedi `buildHistoryRow`. */
  function renderHistory(body, desc, list, giaSopra) {
    clearEl(body);
    desc.textContent = descrizioneStorico(list.length);
    if (!list.length) {
      body.appendChild(el('p', 'field-hint', 'Nessuna promessa nello storico.'));
      return;
    }
    sortHistory(list).forEach(function (p) {
      body.appendChild(buildHistoryRow(p, giaSopra.indexOf(p.id) === -1));
    });
  }

  /* Il conteggio dello storico vive nel titolo, e si sa solo DOPO la fetch:
     si scrive al render, non al montaggio. `null` quando non lo sappiamo (la
     lettura e' fallita): un numero vecchio lasciato li' direbbe una cosa
     falsa sul quando, che e' lo stesso difetto del pallino spento per
     errore (`static/pending-badge.js`). */
  function setHistoryCount(n) {
    var btn = byId('agenda-history-toggle');
    if (btn) btn.textContent = n == null ? 'Storico' : ('Storico (' + n + ')');
  }

  /* I numeri di sezione dicono l'ordine di lettura: 01/02/03 con «Esiti da
     leggere» presente, 01/02 senza. Si rinumerano al render e non al
     montaggio proprio perche' la prima sezione nasce e muore col proprio
     contenuto. */
  function renumberSections() {
    var outlet = byId('route-outlet');
    if (!outlet) return;
    var nums = outlet.querySelectorAll('.sc-num');
    for (var i = 0; i < nums.length; i++) nums[i].textContent = pad2(i + 1);
  }

  /* «Esiti da leggere»: le righe che il pallino del menu ha contato.
     Restituisce gli id DISEGNATI, che sono esattamente quelli che verranno
     segnati letti -- la pagina dichiara cio' che ha messo sullo schermo, non
     «tutti i non letti».

     Quando la lista e' vuota la sezione non esiste nel DOM, e non e' una
     sfumatura: una sezione vuota permanente insegna a non guardare quella
     zona dello schermo, e il giorno in cui ha qualcosa dentro non la si vede
     piu'. Per questo nasce e muore qui dentro, a ogni caricamento, e non
     viene montata una volta per tutte in `mount()`. */
  function renderUnread(list) {
    var outlet = byId('route-outlet');
    var body = byId('agenda-unread-body');
    if (!list.length) {
      if (body) body.parentNode.parentNode.removeChild(body.parentNode);
      return [];
    }
    if (!body) {
      /* Il numero qui e' un segnaposto: `renumberSections()` lo riscrive
         subito dopo, con la posizione vera fra le sezioni presenti. */
      var section = buildSectionShell('01', 'unread', 'unread', 'Esiti da leggere');
      outlet.insertBefore(section, outlet.querySelector('.section-card'));
      body = byId('agenda-unread-body');
    }
    clearEl(body);
    byId('agenda-unread-desc').textContent = descrizioneDaLeggere(list.length);
    var ids = [];
    sortHistory(list).forEach(function (p) {
      body.appendChild(buildHistoryRow(p, true));
      ids.push(p.id);
    });
    return ids;
  }

  /* Il segno di lettura: una POST con esattamente gli id disegnati, mandata
     DOPO averli disegnati (`api/handlers_agenda.py::handle_mark_read`).

     Non e' agganciata alla catena di `load()` apposta. Sbaglia sempre per
     eccesso di notizia -- se fallisce, le righe restano non lette e
     ricompaiono alla visita dopo, che e' il guasto giusto -- quindi non deve
     poter far comparire il messaggio d'errore della pagina: un
     `console.warn` e basta. */
  function segnaLetti(ids) {
    if (!ids.length) return;
    api('api/agenda/read', { method: 'POST', body: JSON.stringify({ ids: ids }) })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        /* La guardia `if` ci vuole SOLO qui: `static/pending-badge.js` e'
           caricato da tutti e due i gusci in produzione, ma questa pagina
           gira anche nei test senza quel file (`tests/js/agenda-route.
           test.mjs` carica `config/agenda-route.js` da solo). Senza il
           rinfresco il pallino resterebbe acceso mentre l'utente sta gia'
           leggendo cio' che lo aveva acceso. */
        if (window.HirisPendingBadge) window.HirisPendingBadge.refresh();
      })
      .catch(function (err) {
        console.warn('[promesse] segno di lettura non riuscito', err);
      });
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
    var pendingBody = byId('agenda-pending-body');
    var historyBody = byId('agenda-history-body');
    var pendingDesc = byId('agenda-pending-desc');
    var historyDesc = byId('agenda-history-desc');
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
      /* DUE condizioni, ed e' la seconda a essere facile da dimenticare:
         `esito_letto_ts` e' NULL anche per ogni promessa IN SOSPESO -- non
         ha ancora un esito da leggere -- quindi un filtro scritto sul solo
         campo nullo riempirebbe «Esiti da leggere» di impegni futuri. Serve
         anche lo stato concluso, che e' il complemento di `PENDING_STATES`:
         lo stesso che usa `renderHistory` qui sopra, non una costante nuova
         (sarebbe un doppione, e `scripts/doppioni.py` avrebbe ragione). */
      var unread = all.filter(function (p) {
        return PENDING_STATES.indexOf(p.stato) === -1 && p.esito_letto_ts == null;
      });
      /* «Esiti da leggere» si disegna per PRIMA: e' quella che decide su
         quale copia di una riga ripetuta va il rivelatore «Cosa è
         cambiato», e lo storico ha bisogno di saperlo. */
      var disegnati = renderUnread(unread);
      renderPending(pendingBody, pendingDesc, pending, load);
      renderHistory(historyBody, historyDesc, history, disegnati);
      setHistoryCount(history.length);
      renumberSections();
      segnaLetti(disegnati);
    }).catch(function (err) {
      console.error('[promesse] caricamento fallito', err);
      /* La sezione degli esiti da leggere sparisce: dopo un guasto non
         sappiamo piu' quali siano, e lasciare le righe di prima sarebbe
         affermare un fatto che non abbiamo piu'. */
      renderUnread([]);
      setHistoryCount(null);
      renumberSections();
      renderError(pendingBody, historyBody, load);
    });
  }

  /* Il titolo di una sezione richiudibile: il bottone sta DENTRO l'`<h2>`,
     non al suo posto. Chi naviga per intestazioni continua a trovare la
     sezione, e un `<h2>` dentro un `<button>` sarebbe comunque HTML non
     valido (un bottone accetta solo contenuto di frase). L'etichetta non
     cambia fra aperto e chiuso -- porta il conteggio, che e' l'unica cosa
     visibile quando la sezione e' chiusa: lo stato lo dicono `aria-expanded`
     per chi ascolta e il triangolo di `.sc-toggle` per chi guarda. */
  function buildDisclosureTitle(toggleId, title, panel) {
    var btn = el('button', 'sc-toggle', title);
    btn.type = 'button';
    btn.id = toggleId;
    btn.setAttribute('aria-controls', panel.id);
    setDisclosure(btn, panel, false);
    /* Nasce chiusa a ogni montaggio, e lo stato non si ricorda fra una
       visita e l'altra: la domanda con cui si apre questa pagina e' «cosa
       c'e' in sospeso», e deve avere la stessa risposta tutte le volte. */
    btn.addEventListener('click', function () {
      setDisclosure(btn, panel, btn.getAttribute('aria-expanded') !== 'true');
    });
    var heading = el('h2', 'sc-title');
    heading.appendChild(btn);
    return heading;
  }

  /* ── Shell statico: due `.section-card` al montaggio (la terza, «Esiti da
     leggere», nasce in `renderUnread()` solo quando ha qualcosa dentro),
     stesso pattern di `buildSectionShell` in models-route.js.
     `#agenda-unread-body`/`#agenda-pending-body`/`#agenda-history-body`
     ricevono `gap:0` da hiris-config.css, stesso trattamento di
     `#chain-body`/`#outside-body`: le righe si separano con un `border-top`
     proprio (guida §2), non col gap del flex. ─────────────────────────── */
  function buildSectionShell(num, idPrefix, sectionAttr, title, toggleId) {
    var section = el('section', 'section-card');
    var body = el('div', 'sc-body');
    body.id = 'agenda-' + idPrefix + '-body';
    body.setAttribute('data-sezione', sectionAttr);
    body.appendChild(el('p', 'field-hint', 'Caricamento…'));

    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(toggleId ? buildDisclosureTitle(toggleId, title, body)
      : el('h2', 'sc-title', title));
    section.appendChild(head);
    var desc = el('p', 'sc-desc', '');
    desc.id = 'agenda-' + idPrefix + '-desc';
    section.appendChild(desc);
    section.appendChild(body);
    return section;
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Impegni'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Ciò che hai chiesto a HIRIS di fare o guardare più tardi, e com’è andata finora.'));
    var status = el('p', 'sc-desc', '');
    status.id = 'agenda-status';
    outlet.appendChild(status);

    /* «In sospeso» sopra: e' la sezione corta, azionabile, ed e' la
       domanda con cui si apre questa pagina piu' spesso. Lo storico e' un
       registro di consultazione, non l'atterraggio (guida §1) -- per questo
       nasce chiuso. Sopra a tutti, quando esiste, «Esiti da leggere»:
       l'inserisce `renderUnread()`, che rinumera anche i `.sc-num`. */
    outlet.appendChild(buildSectionShell('01', 'pending', 'pending', 'In sospeso'));
    outlet.appendChild(buildSectionShell('02', 'history', 'history', 'Storico',
      'agenda-history-toggle'));

    load();
  }

  return { mount: mount };
})();
