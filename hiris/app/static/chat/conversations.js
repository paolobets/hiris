/* HIRIS · Chat page · le conversazioni del filo (fetta «il seguito delle chat
   divise», spec 2026-09-26 §4, disegno con ux-ui-specialist del 25/09)

   Nel filo di chi scrive ci sono piu' conversazioni: la barra laterale le
   elenca, «Nuova conversazione» chiude quella aperta, toccarne una la
   riprende, il cestino dell'header cancella quella aperta (chat/agents.js).
   Qui vive l'unica casa delle quattro rotte `api/chat/conversations`: la
   forma del percorso, l'intestazione anti-CSRF e la lettura degli errori non
   si ripetono altrove.

   Sicurezza: testi via textContent. Il titolo e' la prima frase dell'utente,
   grezza (puo' portare markup, caratteri invisibili o di direzione), e il
   testo d'errore viene dal server: tutti e due entrano nel DOM solo come
   testo, con createElement. Il formattatore dei messaggi (chat/messages.js)
   produce HTML e qui non serve.

   L'id della conversazione aperta non si indovina: e' quello che l'elenco del
   server marca `attiva`. Dopo «Nuova conversazione» non ce n'e' nessuna
   finche' non si scrive (la sessione nasce al primo messaggio), e il cestino
   in quello stato si spegne dicendo perche'. */
(function() {
  var state = window.HirisChatState;

  var BASE = 'api/chat/conversations';
  var EMPTY_TEXT = 'Le tue conversazioni con HIRIS compariranno qui.';
  var NOTHING_TO_DELETE = 'Cancella la conversazione: nessuna conversazione aperta';
  var NETWORK_TEXT = 'Non è stato possibile raggiungere HIRIS. Riprova tra poco.';

  var active = null;
  /* L'ultima operazione partita (lettura dell'elenco o scrittura). La
     aspettano le prove, che toccano i bottoni come un utente e poi guardano
     il risultato; la pagina non ne ha bisogno. */
  var inFlight = Promise.resolve();

  function track(p) { inFlight = p; return p; }
  function idle() { return inFlight; }
  function activeId() { return active; }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /* «oggi», «ieri», poi gg-mm, nel fuso di chi guarda. `ultimo_messaggio` si
     mostra cosi' com'e': dopo una ripresa e' l'ora della ripresa (serve alla
     regola delle due ore del server), e inventarne un'altra direbbe una data
     che nessuno ha scritto. Una data illeggibile non diventa «oggi». */
  function relativeDay(iso, now) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var n = now || new Date();
    var today = new Date(n.getFullYear(), n.getMonth(), n.getDate());
    var day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    /* `round` e non `floor`: nei giorni del cambio d'ora la mezzanotte dista
       23 o 25 ore dalla precedente. */
    var diff = Math.round((today - day) / 86400000);
    if (diff === 0) return 'oggi';
    if (diff === 1) return 'ieri';
    return pad2(d.getDate()) + '-' + pad2(d.getMonth() + 1);
  }

  /* Il cestino ha due ragioni per spegnersi: HIRIS sta rispondendo (la
     risposta atterrerebbe in una conversazione sparita) o non c'e' una
     conversazione aperta. Tutte e due si leggono qui, in un posto solo:
     chat/send.js chiama questa funzione invece di scrivere `disabled`. */
  function syncDeleteButton() {
    var btn = document.getElementById('delete-conv-btn');
    if (!btn) return;
    btn.disabled = state.isLoading || active === null;
    if (active === null) btn.setAttribute('aria-label', NOTHING_TO_DELETE);
    else btn.removeAttribute('aria-label');
  }

  function showNotice(text) {
    var el = document.getElementById('conv-notice');
    if (!el) return;
    el.textContent = text;
    el.hidden = false;
  }

  function hideNotice() {
    var el = document.getElementById('conv-notice');
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
  }

  function buildItem(row) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sb-nav-item conv-item';
    btn.setAttribute('data-id', String(row.id));
    if (row.id === active) {
      btn.classList.add('active');
      btn.setAttribute('aria-current', 'true');
    }
    var title = document.createElement('span');
    title.className = 'conv-title';
    title.textContent = String(row.titolo == null ? '' : row.titolo);
    var when = document.createElement('time');
    when.className = 'conv-when';
    if (row.ultimo_messaggio) when.setAttribute('datetime', String(row.ultimo_messaggio));
    when.textContent = relativeDay(row.ultimo_messaggio);
    btn.appendChild(title);
    btn.appendChild(when);
    var li = document.createElement('li');
    li.appendChild(btn);
    return li;
  }

  function render(rows) {
    active = null;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].attiva) { active = rows[i].id; break; }
    }
    var list = document.getElementById('conv-list');
    var empty = document.getElementById('conv-empty');
    if (list) {
      list.textContent = '';
      rows.forEach(function(row) { list.appendChild(buildItem(row)); });
      list.hidden = rows.length === 0;
    }
    if (empty) {
      empty.textContent = EMPTY_TEXT;
      empty.hidden = rows.length > 0;
    }
    syncDeleteButton();
  }

  /* Rilegge l'elenco. Un elenco riletto e' anche la fine di un avviso
     vecchio: «c'e' gia' una risposta in arrivo» smette di essere vero quando
     il turno finisce, ed e' li' che chat/send.js chiama questa funzione. */
  function refresh() {
    return track((async function() {
      try {
        var r = await fetch(BASE);
        if (!r.ok) throw new Error('conversazioni: ' + r.status);
        var data = await r.json();
        render(Array.isArray(data.conversations) ? data.conversations : []);
        hideNotice();
      } catch (e) {
        console.error('conversations refresh failed', e);
      }
    })());
  }

  /* Le tre scritture passano da qui: stessa intestazione (il middleware CSRF
     rifiuta una scrittura senza), stessa lettura dell'errore, stesso seguito.
     Un fallimento non tocca la vista e si dice col testo del server quando
     c'e' (il 409 «risposta in arrivo», il 404): nessun nuovo tentativo da
     solo, perche' e' chi legge a decidere se riprovare. Una riuscita mostra
     la conversazione che il server dice attiva -- la storia riletta, non una
     vista svuotata a mano -- e rilegge l'elenco. */
  function act(method, url, fallback) {
    return track((async function() {
      hideNotice();
      var r;
      try {
        r = await fetch(url, { method: method, headers: { 'X-Requested-With': 'fetch' } });
      } catch (e) {
        console.error('conversation ' + method + ' failed', e);
        showNotice(NETWORK_TEXT);
        return false;
      }
      if (!r.ok) {
        var text = fallback;
        try {
          var body = await r.json();
          if (body && typeof body.error === 'string' && body.error) text = body.error;
        } catch { /* corpo non JSON: resta il testo di ripiego */ }
        console.error('conversation ' + method + ' failed', r.status);
        /* L'elenco si rilegge anche qui (un 404 vuol dire che la voce non
           c'e' piu'), e l'avviso si scrive DOPO, o la rilettura lo
           spegnerebbe. */
        await refresh();
        showNotice(text);
        return false;
      }
      await window.HirisChatAgents.restore();
      await refresh();
      return true;
    })());
  }

  function focusInput() {
    if (state.els.input && !state.els.input.disabled) state.els.input.focus();
  }

  function startNew() {
    return act('POST', BASE,
      'Non è stato possibile aprire una nuova conversazione. Riprova più tardi.')
      .then(function(ok) { if (ok) focusInput(); return ok; });
  }

  function resume(id) {
    return act('POST', BASE + '/' + encodeURIComponent(id) + '/resume',
      'Non è stato possibile riprendere questa conversazione. Riprova più tardi.')
      .then(function(ok) { if (ok) focusInput(); return ok; });
  }

  function remove(id) {
    return act('DELETE', BASE + '/' + encodeURIComponent(id),
      'Non è stato possibile cancellare la conversazione. Riprova più tardi.');
  }

  /* Il cassetto su telefono lo chiude chat/sidebar.js, che ascolta i tocchi
     su ogni `.sb-nav-item` della barra: le voci lo sono, e cosi' «Nuova
     conversazione». Qui c'e' solo cosa fa la voce. */
  function init() {
    var newBtn = document.getElementById('new-conv-btn');
    if (newBtn) newBtn.addEventListener('click', function() { startNew(); });
    var list = document.getElementById('conv-list');
    if (list) list.addEventListener('click', function(e) {
      var item = e.target.closest('.conv-item');
      if (!item) return;
      var id = item.getAttribute('data-id');
      /* La voce attiva e' gia' quella a schermo: riprenderla chiuderebbe e
         riaprirebbe la stessa sessione, buttandone il riassunto. */
      if (id === String(active)) { track(Promise.resolve()); focusInput(); return; }
      resume(id);
    });
    return refresh();
  }

  window.HirisChatConversations = {
    init: init,
    refresh: refresh,
    startNew: startNew,
    resume: resume,
    remove: remove,
    activeId: activeId,
    syncDeleteButton: syncDeleteButton,
    relativeDay: relativeDay,
    idle: idle,
  };
})();
