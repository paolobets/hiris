/* HIRIS · Chat page · coda di approvazione della memoria.

   Perche' esisteva: fino alla fetta memoria-unica (Task 2), lo strumento che
   il modello chiamava quando l'utente diceva "ricordati che..." (allora
   `save_knowledge`, oggi fuso in `save_memory`) salvava in stato `pending`,
   mentre la ricerca nella knowledge base legge solo gli elementi `approved`.
   Senza una superficie che approvi, il Chatbot rispondeva "salvato" e quel
   ricordo non tornava mai: nessun errore, nessun log. Gli endpoint (GET
   /api/knowledge/pending, POST /api/knowledge/{id}/approve|reject) c'erano
   gia': mancava il posto dove decidere.

   Dopo Task 2 `save_memory` scrive sempre `status='approved'`: questa coda
   non riceve piu' nulla dal percorso della chat (resta raggiungibile solo da
   righe pre-esistenti o create a mano sullo store). La rimozione della coda
   stessa e la ridefinizione della pagina "Memoria" come "cio' che HIRIS sa"
   sono fuori dallo scope di questa fetta (design memoria-unica §2⑤, §4).

   Sta nella chat, accanto a Proposte e Task, perche' e' la stessa natura —
   un'inbox di cose che aspettano una decisione — e perche' e' li' che nasce:
   l'elemento e' stato salvato durante una conversazione.

   Struttura ricalcata su chat/proposals.js: voce di navigazione con badge,
   pannello mutuamente esclusivo con Task e Proposte, click delegato sul
   contenitore (la lista viene ricostruita a ogni caricamento, quindi un
   listener per bottone morirebbe al primo refresh). La rete sta in
   chat/knowledge-core.js, senza DOM. `esc()` e' il globale di config/api.js,
   gia' caricato in questa pagina.

   Due punti che non sono dettagli:
   - il contenuto e' testo scritto da un LLM su dettatura dell'utente: ogni
     valore interpolato passa da `esc()`;
   - un elemento marcato sensibile non viene reso in chiaro. Altrove (briefing,
     recall_memory) il sensibile viene nascosto o pseudonimizzato; qui non
     puo' essere nascosto del tutto — chi approva deve sapere cosa approva — ma
     resta coperto finche' non lo si chiede esplicitamente, e il contenuto non
     entra nemmeno nel DOM prima di quel momento. */
(function() {
  var KIND_LABELS = {
    fact: 'fatto',
    preference: 'preferenza',
    obligation: 'scadenza',
    expense: 'spesa',
    note: 'nota',
    document: 'documento',
    memory: 'memoria'
  };

  /* Le chiavi sono i valori che gli scrittori della knowledge base mettono
     davvero in `source` (memory_tools "chat", handlers_knowledge "manual",
     mayan_ingest "mayan", history_digest "history-digest", brain_trace
     "brain", memory_migration "migrated"). Dopo Task 2 (memoria unica)
     memory_tools scrive sempre approvato: "chat" non arriva piu' qui da solo
     -- resta nell'elenco perche' un elenco che inventa nomi mai scritti
     inganna chi legge, non perche' sia ancora l'unico caso pratico. */
  var SOURCE_LABELS = {
    chat: 'conversazione',
    manual: 'inserimento manuale',
    mayan: 'documenti',
    'history-digest': 'storico',
    brain: 'Brain',
    migrated: 'memoria migrata'
  };

  /* Ultimo elenco letto dal server. Serve al "Mostra" degli elementi
     sensibili: il contenuto viene preso da qui e scritto come testo, cosi'
     non finisce nell'HTML della card finche' non lo si chiede. */
  var pending = [];

  /* L'istante arriva in ISO 8601 UTC: all'utente va mostrata l'ora locale.
     Ritorna null se manca o non e' interpretabile — chi chiama dichiara "data
     non disponibile" invece di inventarne una. */
  function fmtWhen(iso) {
    var t = iso ? Date.parse(iso) : NaN;
    if (isNaN(t)) return null;
    try {
      return new Date(t).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
    } catch (e) {
      return new Date(t).toLocaleString();
    }
  }

  /* La scadenza e' una data pura (YYYY-MM-DD) e va letta come tale: senza
     orario e senza fuso, altrimenti una scadenza del primo del mese puo'
     mostrarsi come l'ultimo del mese precedente. Se non ha quella forma la si
     ripropone com'e': meglio un formato grezzo di una data sbagliata. */
  function fmtDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
    return m ? (m[3] + '/' + m[2] + '/' + m[1]) : String(iso || '');
  }

  /* Lo store tratta come sensibile QUALUNQUE valore diverso da 'normal'
     (knowledge_store.search, briefing._collect_deadlines, recall_memory):
     stessa regola qui, altrimenti un terzo valore di sensibilita' passerebbe
     in chiaro proprio dove altrove viene coperto. */
  function isSensitive(item) {
    return ((item && item.sensitivity) || 'normal') !== 'normal';
  }

  /* Da dove viene: la conversazione o lo strumento che l'ha salvato, se il
     dato c'e'. Niente riga se non si sa nulla — meglio tacere che scrivere
     "origine: sconosciuta" sotto ogni card. */
  function provenance(item) {
    var parti = [];
    if (item.source) parti.push(SOURCE_LABELS[item.source] || String(item.source));
    if (item.chatbot_id) parti.push('Chatbot ' + item.chatbot_id);
    if (item.source_ref) parti.push(item.source_ref);
    return parti.length ? parti.join(' · ') : '';
  }

  /* Corpo della card. Per un elemento sensibile il contenuto NON viene
     interpolato: resta fuori dal DOM finche' "Mostra" non lo inserisce come
     testo (vedi reveal). */
  function renderBody(item, safeId) {
    if (isSensitive(item)) {
      return '<div class="kb-content kb-masked" id="kb-body-' + safeId + '">'
        + 'Contenuto sensibile — nascosto.</div>'
        + '<button class="kb-reveal" type="button" data-kb-act="reveal" data-kid="'
        + safeId + '">Mostra contenuto</button>';
    }
    return '<div class="kb-content" id="kb-body-' + safeId + '">'
      + esc(item.content || '') + '</div>';
  }

  function renderItem(item) {
    var safeId = esc(item.id);
    var kind = KIND_LABELS[item.kind] || String(item.kind || 'elemento');
    var when = fmtWhen(item.created_at);
    var meta = [];
    if (item.due_date) meta.push('scade il ' + fmtDate(item.due_date));
    if (item.amount !== null && item.amount !== undefined && item.amount !== '') {
      meta.push('importo ' + item.amount);
    }
    if (item.category) meta.push(item.category);
    var origine = provenance(item);
    return '<div class="kb-card' + (isSensitive(item) ? ' kb-sensitive' : '')
      + '" id="kb-' + safeId + '">'
      + '<div class="kb-head">'
      + '<span class="kb-kind">' + esc(kind) + '</span>'
      + (isSensitive(item) ? '<span class="kb-flag">sensibile</span>' : '')
      + '<span class="kb-date">' + esc(when || 'data non disponibile') + '</span>'
      + '</div>'
      + (item.title ? '<div class="kb-title">' + esc(item.title) + '</div>' : '')
      + renderBody(item, safeId)
      + (meta.length ? '<div class="kb-meta">' + esc(meta.join(' · ')) + '</div>' : '')
      + (origine ? '<div class="kb-origin">Da: ' + esc(origine) + '</div>' : '')
      + '<div class="kb-actions">'
      + '<button class="btn kb-approve" type="button" data-kb-act="approve" data-kid="' + safeId + '">Approva</button>'
      + '<button class="btn kb-discard" type="button" data-kb-act="reject" data-kid="' + safeId + '">Scarta</button>'
      + '</div>'
      + '</div>';
  }

  function setBadges(n) {
    var count = n || 0;
    var b = document.getElementById('knowledge-badge');
    if (b) { b.textContent = count || ''; b.dataset.count = count; }
    var mb = document.getElementById('mobile-knowledge-badge');
    if (mb) { mb.textContent = count || ''; mb.dataset.count = count; }
  }

  /* Non aver potuto leggere la coda non e' una coda vuota: il primo caso
     nasconde ricordi che restano non richiamabili, il secondo dice che non
     c'e' nulla da fare. Vanno detti in modo diverso, e in caso di dubbio il
     badge non deve mostrare un conteggio inventato. */
  function renderError() {
    var list = document.getElementById('chat-knowledge-list');
    if (list) {
      list.innerHTML = '<div class="task-empty kb-error">'
        + 'Non è stato possibile leggere la coda della memoria. '
        + 'Riprova più tardi.</div>';
    }
    setBadges(0);
  }

  function load() {
    return HirisKnowledgeCore.listPending().then(function(res) {
      if (!res.ok) { pending = []; renderError(); return; }
      pending = res.items || [];
      setBadges(pending.length);
      var list = document.getElementById('chat-knowledge-list');
      if (!list) return;
      list.innerHTML = pending.length
        ? pending.map(renderItem).join('')
        : '<div class="task-empty">Nessun elemento in attesa di conferma</div>';
    }).catch(function(e) {
      console.error('loadKnowledgePending failed', e);
      pending = [];
      renderError();
    });
  }

  function findItem(id) {
    for (var i = 0; i < pending.length; i++) {
      if (String(pending[i].id) === String(id)) return pending[i];
    }
    return null;
  }

  /* Mostra il contenuto di un elemento sensibile su richiesta esplicita.
     `textContent` e non innerHTML: il testo arriva da un LLM e qui non
     passerebbe da esc(). */
  function reveal(id) {
    var item = findItem(id);
    var body = document.getElementById('kb-body-' + id);
    if (!item || !body) return;
    body.textContent = item.content || '';
    body.classList.remove('kb-masked');
    var card = document.getElementById('kb-' + id);
    var btn = card && card.querySelector('[data-kb-act="reveal"]');
    if (btn) btn.remove();
  }

  /* Il messaggio all'utente e' scritto qui, in italiano, e NON e' l'`error`
     del backend (stringa tecnica in inglese): quello finisce in console per
     chi diagnostica. Lo stato HTTP distingue i due casi che l'utente puo'
     effettivamente interpretare — l'elemento non c'e' piu' (gia' gestito
     altrove, e la coda va riletta) e la memoria non risponde. */
  function messaggioErrore(res, isReject) {
    if (res.status === 404) {
      return 'Questo elemento non è più in attesa: potrebbe essere già stato gestito.';
    }
    if (res.status === 503) {
      return 'La memoria non è raggiungibile in questo momento. Riprova più tardi.';
    }
    return isReject
      ? 'Non è stato possibile scartare questo elemento.'
      : 'Non è stato possibile approvare questo elemento.';
  }

  function act(id, kind) {
    var isReject = (kind === 'reject');
    var msg = isReject
      ? 'Scartare questo elemento? Verrà eliminato definitivamente.'
      : 'Approvare questo elemento? Da quel momento HIRIS potrà richiamarlo.';
    if (!window.confirm(msg)) return;
    var fn = isReject ? HirisKnowledgeCore.reject : HirisKnowledgeCore.approve;
    var card = document.getElementById('kb-' + id);
    fn(id).then(function(res) {
      if (!res.ok) {
        console.error('knowledge action failed', kind, res.status, res.error);
        window.alert(messaggioErrore(res, isReject));
        /* Un 404 significa che la coda a schermo non e' piu' quella vera:
           rileggerla evita che l'utente continui a lavorare su una lista
           stantia. */
        if (res.status === 404) load();
        return;
      }
      if (card) {
        card.style.opacity = '0.5';
        var body = card.querySelector('.kb-content');
        if (body) {
          body.textContent = isReject ? 'Elemento scartato' : 'Elemento approvato';
        }
        var acts = card.querySelector('.kb-actions');
        if (acts) acts.remove();
        var revealBtn = card.querySelector('[data-kb-act="reveal"]');
        if (revealBtn) revealBtn.remove();
      }
      setTimeout(load, 1000);
    }, function() { window.alert('Errore di rete'); });
  }

  function showPanel(name) {
    var isKb = (name === 'knowledge');
    var messages = document.getElementById('messages');
    var inputArea = document.getElementById('input-area');
    if (messages) messages.style.display = isKb ? 'none' : '';
    if (inputArea) inputArea.style.display = isKb ? 'none' : '';
    var tc = document.getElementById('turn-counter'); if (tc) tc.style.display = isKb ? 'none' : '';
    var se = document.getElementById('session-ended-msg'); if (se) se.style.display = isKb ? 'none' : '';
    /* mutua esclusione con Task e Proposte (stessa area overlay) */
    var taskPanel = document.getElementById('task-panel'); if (taskPanel) taskPanel.style.display = 'none';
    var propPanel = document.getElementById('proposals-panel'); if (propPanel) propPanel.style.display = 'none';
    var panel = document.getElementById('knowledge-panel');
    if (panel) panel.style.display = isKb ? 'flex' : 'none';
    var nav = document.getElementById('nav-knowledge');
    if (nav) nav.classList.toggle('active', isKb);
    var mobileBtn = document.getElementById('mobile-knowledge-btn');
    if (mobileBtn) mobileBtn.classList.toggle('active', isKb);
    if (isKb) {
      var navTasks = document.getElementById('nav-tasks'); if (navTasks) navTasks.classList.remove('active');
      var mobileTask = document.getElementById('mobile-task-btn'); if (mobileTask) mobileTask.classList.remove('active');
      var navProp = document.getElementById('nav-proposals'); if (navProp) navProp.classList.remove('active');
      var mobileProp = document.getElementById('mobile-proposals-btn'); if (mobileProp) mobileProp.classList.remove('active');
    }
    var header = document.getElementById('knowledge-panel-header');
    if (header) header.style.display = (isKb && window.innerWidth <= 720) ? 'flex' : 'none';
    if (isKb) load();
  }

  function init() {
    var nav = document.getElementById('nav-knowledge');
    if (nav) nav.addEventListener('click', function(e) { e.preventDefault(); showPanel('knowledge'); });
    var mobileBtn = document.getElementById('mobile-knowledge-btn');
    if (mobileBtn) mobileBtn.addEventListener('click', function(e) { e.preventDefault(); showPanel('knowledge'); });
    var backBtn = document.getElementById('knowledge-panel-back-btn');
    if (backBtn) backBtn.addEventListener('click', function() { showPanel('chat'); });

    var panel = document.getElementById('knowledge-panel');
    if (panel) panel.addEventListener('click', function(e) {
      var btn = e.target.closest && e.target.closest('[data-kb-act]');
      if (!btn) return;
      var azione = btn.getAttribute('data-kb-act');
      if (azione === 'reveal') { reveal(btn.getAttribute('data-kid')); return; }
      act(btn.getAttribute('data-kid'), azione);
    });

    setInterval(load, 30000);
    load();   /* popola il badge anche senza aprire il pannello */
  }

  window.HirisChatKnowledge = {
    showPanel: showPanel, load: load, act: act, reveal: reveal, init: init
  };
})();
