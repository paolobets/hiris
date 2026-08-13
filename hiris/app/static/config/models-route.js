/* HIRIS · Config · models route mount (SP-2 Task 7 + Task 7-fix; fetta E5
   Task 7 ha tolto la sezione "Assegnazione per entità" — vedi sotto)
   Sezione #/models — implementa il contratto UX di
   docs/design/2026-07-27-ux-models-section.md, ridotto a tre sezioni vive
   dal contratto originale di quattro:
     01 Provider e credenziali (GET api/models/config -> providers[], badge +
        picker default per-provider da GET api/models)
     02 Catena automatica (GET/PUT api/models/config chain_order, riordino
        frecce, preset llm_strategy)
     03 Embeddings (riga informativa, sola lettura, da GET api/models/config)
   Fino alla 2.4.1 la pagina si apriva con la sezione 01. Dalla fetta «la
   catena diventa l'unica verità» si apre, PRIMA delle tre sezioni, con il
   riquadro «Adesso» (renderAdesso): chi risponde al prossimo messaggio, in
   una frase che arriva già scritta dal backend (campo `adesso` del payload
   GET api/models/config, composto da decisione_modelli.componi_adesso). Non
   è numerato perché non fa decidere niente -- vedi il commento sopra la
   funzione.
   La sezione 03 originale del design doc ("Assegnazione per entità": Chatbot
   -> PUT api/chatbots/{id}, Brain -> PUT api/models/config brain_model) è
   uscita alla fetta E5 Task 7 ("Consumi e Modelli smettono di mentire"): il
   ramo Chatbot faceva PUT su una rotta che non esisteva per quel metodo
   (solo GET rispondeva su /api/chatbots — rotta uscita per intero, GET
   compreso, alla fetta E5 Task 10) — ogni cambio di select falliva con
   404, sel.value tornava al valore precedente e compariva il badge rosso; il
   ramo Brain scriveva brain_model, una configurazione senza più nessun
   lettore da quando il Brain è uscito con la E3. Il modello della chat si
   cambia dal Task 2 della E5 (impostazioni chat), dove è sempre dovuto stare.
   Sicurezza: testi via textContent/createElement, mai innerHTML su dati server
   (stesso vincolo di dashboard.js e impostazioni-route.js).

   Task 7B ha arricchito GET /api/models/config con:
     providers: [{id: subscription|claude|openai|openrouter|ollama, label,
                  in_catena, has_credential}]  (tutti e 5, ordine fisso)
     -- fetta «la catena diventa l'unica verità»: il campo si chiamava
     "active" (interruttore add-on AND credenziale) e viaggiava insieme a
     "toggle" (il valore grezzo dell'interruttore). Erano DUE rappresentazioni
     dello stato di un provider accanto all'appartenenza alla catena, ed è la
     seconda rappresentazione che permetteva a questa pagina di mostrare
     spento un provider che stava lavorando. Adesso ce n'è una: un provider è
     usato se e solo se sta in catena. Questa pagina viene riscritta dal
     Task 8 (che consumerà `catena`/`fuori_catena`, le due liste già ordinate
     dal backend); qui si adegua ai nomi nuovi per non restare a leggere un
     campo che non esiste più -- cioè per non ricominciare a mentire mentre
     aspetta il suo turno.
     llm_strategy: string
     embeddings: {provider, model}
     ollama_model: nome del modello Ollama fisso configurato
   (oltre a chain_order/provider_models già presenti — brain_model è uscito
   dal payload alla fetta E5 Task 7). Questo file consuma quell'arricchimento
   invece di dedurre badge/stato da GET /api/models (che elenca solo i
   provider già credenziati, senza i disattivi/senza credenziale — vedi
   report Task 7-fix). */
(function() {
  'use strict';

  /* Ordine fisso di visualizzazione Parte 1 (design §3.1: "sempre in
     quest'ordine, attivi o no, così la lista non salta"): Abbonamento, Claude
     API, OpenAI, OpenRouter, Ollama.
     - "configId" è l'id nel payload GET /api/models/config -> providers[]
       (subscription/claude/openai/openrouter/ollama, Task 7B).
     - "id" è l'id nel payload GET /api/models (anthropic/openai/openrouter/
       ollama — SOLO per i provider già credenziati, usato per i modelli
       disponibili nei picker; "anthropic" diverge da "claude" per storia
       dell'endpoint, vedi handlers_models.py _ACTIVE_PROVIDERS_KEY).
     - "key" è la chiave usata in chain_order / provider_models (vedi
       handlers_models.py _VALID_BACKENDS) — null per "subscription", che non
       fa parte della catena/assegnazione automatica nel contratto attuale. */
  var PROVIDER_ORDER = [
    { configId: 'subscription', id: null, key: null },
    { configId: 'claude', id: 'anthropic', key: 'claude' },
    { configId: 'openai', id: 'openai', key: 'openai' },
    { configId: 'openrouter', id: 'openrouter', key: 'openrouter' },
    { configId: 'ollama', id: 'ollama', key: 'ollama' }
  ];

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

  function byId(id) {
    var node = document.getElementById(id);
    return node;
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(path, opts);
  }

  /* Etichetta leggibile per i modelli Claude (design §3.3: "Claude Opus 4.5"
     invece dell'id tecnico grezzo). Gli altri provider non hanno un mapping
     label lato backend: fallback all'id as-is (design §11 punto 2). */
  function prettyClaudeLabel(id) {
    var m = /^claude-(haiku|sonnet|opus)-(\d+)-(\d+)/.exec(id);
    if (!m) return id;
    var name = m[1].charAt(0).toUpperCase() + m[1].slice(1);
    return 'Claude ' + name + ' ' + m[2] + '.' + m[3];
  }

  function modelLabel(providerId, modelId) {
    if (modelId === 'auto') return 'auto';
    if (providerId === 'anthropic') return prettyClaudeLabel(modelId);
    return modelId;
  }

  /* ── Feedback di successo condiviso (design §7.2.3): un check "✓" che
     compare per ~1.2s accanto al controllo toccato poi svanisce. Testo via
     textContent (mai innerHTML), contenitore aria-live="polite" già impostato
     da chi crea il badge con buildSuccessBadge(). Usato dal picker
     default-provider di Parte 1 (§7.2); il secondo chiamante storico, il PUT
     per-Chatbot (§7.3), è uscito con la fetta E5 Task 7 insieme alla sezione
     che lo usava. */
  function buildSuccessBadge() {
    var b = el('span', 'agent-badge badge-on', '');
    b.style.display = 'none';
    b.setAttribute('aria-live', 'polite');
    return b;
  }

  function flashSuccess(badge) {
    if (!badge) return;
    badge.textContent = '✓';
    badge.style.display = '';
    if (badge._flashTimer) clearTimeout(badge._flashTimer);
    badge._flashTimer = setTimeout(function() {
      badge.style.display = 'none';
      badge.textContent = '';
    }, 1200);
  }

  /* ── Feedback di errore condiviso (design §7.2/§7.3 + fix UX review) ────
     aria-live="polite" annuncia MUTAZIONI di contenuto, non cambi di
     visibilità: un badge creato una sola volta con testo fisso e poi solo
     mostrato/nascosto via style.display non viene mai riletto da uno
     screen reader al secondo fallimento (il testo non cambia mai). Per
     questo showErrBadge svuota e riscrive textContent ad ogni fallimento —
     così c'è sempre una mutazione da annunciare, anche quando il messaggio
     è identico alla volta precedente. */
  var ERR_BADGE_TEXT = '⚠ Salvataggio non riuscito';

  function buildErrorBadge() {
    var b = el('span', 'agent-badge badge-warn', '');
    b.style.display = 'none';
    b.setAttribute('aria-live', 'polite');
    return b;
  }

  function showErrBadge(badge) {
    if (!badge) return;
    badge.textContent = '';
    badge.style.display = '';
    badge.textContent = ERR_BADGE_TEXT;
  }

  function hideErrBadge(badge) {
    if (!badge) return;
    badge.style.display = 'none';
  }

  /* ── Stato locale ──────────────────────────────────────────────────── */
  var state = {
    providers: [],        // GET api/models -> providers[] (solo credenziati, id anthropic/openai/openrouter/ollama)
    configProviders: [],  // GET api/models/config -> providers[] (tutti e 5, id subscription/claude/openai/openrouter/ollama)
    llmStrategy: '',       // GET api/models/config -> llm_strategy
    embeddings: { provider: '', model: '' },  // GET api/models/config -> embeddings
    ollamaModel: '',       // GET api/models/config -> ollama_model
    adesso: null,          // GET api/models/config -> adesso (la decisione già presa)
    /* Letto dal payload e non ancora consumato da nessuna render: e' lo
       slot che il Task 8 usa per dire, nella catena, che il ponte la
       scavalca. Sta qui perche' e' il posto in cui il payload si legge
       una volta sola; se il Task 8 non arrivasse, va tolto con lui. */
    ponteAttivo: false,    // GET api/models/config -> ponte_attivo
    cfg: { chain_order: [], provider_models: { claude: '', openai: '', openrouter: '' } }
  };

  function findProvider(id) {
    for (var i = 0; i < state.providers.length; i++) {
      if (state.providers[i].id === id) return state.providers[i];
    }
    return null;
  }

  function findConfigProvider(configId) {
    for (var i = 0; i < state.configProviders.length; i++) {
      if (state.configProviders[i].id === configId) return state.configProviders[i];
    }
    return null;
  }

  /* Provider "usabili" = in catena + con credenziale (design §0.5/§4.1),
     fonte: GET /api/models (che lista solo chi ha già una lista modelli
     disponibile). "subscription" (key null) non entra mai qui: non fa parte di
     chain_order/provider_models nel contratto backend attuale
     (_VALID_BACKENDS). */
  function usableProviders() {
    var list = [];
    PROVIDER_ORDER.forEach(function(pd) {
      if (!pd.key) return;
      var p = findProvider(pd.id);
      if (p && p.in_catena && p.has_credential) list.push(p);
    });
    return list;
  }

  function usableKeys() {
    return usableProviders().map(function(p) {
      var pd = PROVIDER_ORDER.filter(function(x) { return x.id === p.id; })[0];
      return pd ? pd.key : p.id;
    });
  }

  /* ── PUT api/models/config — SEMPRE l'oggetto intero (§7.2), serializzato ──
     Task 7-fix punto 4: due controlli che scrivono quasi in contemporanea
     (es. picker default-provider + riordino catena) potrebbero far arrivare
     le risposte fuori ordine se le richieste partono in parallelo, e un PUT
     con uno snapshot "vecchio" di state.cfg potrebbe sovrascrivere sul server
     una modifica concorrente più recente. Mutex a catena di promise: al più
     una richiesta in volo per volta, e ogni richiesta legge state.cfg SOLO
     quando è il suo turno di partire (non quando viene accodata) — così
     include sempre anche le modifiche sincrone fatte nel frattempo da altri
     handler. */
  var putChain = Promise.resolve();
  function putModelsConfig() {
    var result = putChain.then(function() {
      return api('api/models/config', { method: 'PUT', body: JSON.stringify(state.cfg) })
        .then(function(r) { return r.ok; })
        .catch(function() { return false; });
    });
    /* La catena deve proseguire anche se questa chiamata fallisce, altrimenti
       un fallimento bloccherebbe per sempre le PUT successive in coda. */
    putChain = result.catch(function() { return null; });
    return result;
  }

  /* Inserisce (in testa) e seleziona un'opzione "orfana" quando il valore
     salvato non è (più) tra le opzioni disponibili — così il valore non viene
     perso silenziosamente (design §5.1). Usata dal picker default-provider di
     Parte 1 (Task 7-fix punto 5); il secondo chiamante storico — il picker
     condiviso Brain/Chatbot, fillModelOptions — è uscito con la fetta E5
     Task 7 insieme alla sezione che lo usava. */
  function ensureOrphanOption(sel, val, suffix) {
    if (!val) return;
    if (sel.value === val) return; // già selezionabile, nessuna orfana da inserire
    var orphan = el('option', null, val + suffix);
    orphan.value = val;
    sel.insertBefore(orphan, sel.firstChild);
    sel.value = val;
  }

  /* ── «Adesso»: la risposta, prima delle ragioni ────────────────────────
     Non è una sezione e non è numerata: la numerazione, in questa pagina,
     significa «qui si decide qualcosa». Questo riquadro non fa decidere
     niente -- dice cosa succede.

     Non compone NESSUNA frase: `adesso.frase` e ogni `diagnosi[].testo`
     arrivano già scritti da `decisione_modelli.componi_adesso`. È l'invariante
     2 della spec applicato al testo e non solo all'ordine: se le parole si
     componessero qui, esisterebbero due posti che affermano cose sul
     prodotto, e uno dei due prima o poi affermerebbe più di quanto il sistema
     sa. */
  function renderAdesso() {
    var vecchio = byId('adesso-card');
    if (vecchio && vecchio.parentNode) vecchio.parentNode.removeChild(vecchio);
    if (!state.adesso || !state.adesso.frase) return null;

    var card = el('div', 'adesso-card');
    card.id = 'adesso-card';
    card.appendChild(el('p', 'adesso-frase', state.adesso.frase));

    var diagnosi = state.adesso.diagnosi;
    if (Array.isArray(diagnosi) && diagnosi.length) {
      var ul = el('ul', 'adesso-diagnosi');
      diagnosi.forEach(function(d) {
        if (!d || !d.testo) return;
        var li = el('li', 'diagnosi-' + (d.gravita || 'guasto'), d.testo);
        ul.appendChild(li);
      });
      if (ul.firstChild) card.appendChild(ul);
    }
    return card;
  }

  /* ── Sezione 1: Provider e credenziali ───────────────────────────────── */
  function renderSection1() {
    var body = clearEl(byId('sec1-body'));
    if (!body) return;

    var anyInCatena = false;
    PROVIDER_ORDER.forEach(function(pd) {
      var cp = findConfigProvider(pd.configId);
      var inCatena = !!(cp && cp.in_catena);
      var hasCred = !!(cp && cp.has_credential);
      /* fetta «la catena diventa l'unica verità»: i due fatti sono adesso
         INDIPENDENTI e nessuno dei due collassa nell'altro -- l'appartenenza
         alla catena e la presenza della credenziale. Prima erano "active"
         (interruttore AND credenziale) più "toggle" grezzo per recuperare lo
         stato che l'AND aveva schiacciato: la parola «Attivo» ne era la
         conseguenza, e diceva «funziona» mentre misurava una configurazione.
         Qui non c'è più niente da recuperare, quindi non c'è più una parola
         che affermi più di ciò che il sistema sa. */
      var missingCred = !hasCred;
      if (inCatena) anyInCatena = true;
      var label = (cp && cp.label) || pd.configId;

      var row = el('div', 'provider-row');
      var head = el('div', 'provider-row-head');
      var dotCls = inCatena ? 'on' : (missingCred ? 'warn' : 'off');
      head.appendChild(el('span', 'dot ' + dotCls));
      head.appendChild(el('span', 'provider-row-label', label));
      var badgeCls = inCatena ? 'badge-on' : (missingCred ? 'badge-warn' : 'badge-off');
      var badgeTxt = inCatena ? 'In catena' : (missingCred ? '⚠ manca credenziale' : 'Fuori dalla catena');
      head.appendChild(el('span', 'agent-badge ' + badgeCls, badgeTxt));
      row.appendChild(head);

      if (missingCred) {
        row.appendChild(el('p', 'field-hint', 'Aggiungi la chiave in Configurazione add-on: senza credenziale non può entrare in catena.'));
      } else if (!inCatena) {
        /* Lo stato che prima non esisteva: credenziale presente, fuori dalla
           catena. Prima `reconcile_chain` lo accodava da solo alla catena, e
           il provider entrava senza che nessuno ce l'avesse messo; adesso
           resta fuori, ed è la pagina a doverlo dire invece di lasciarlo
           dedurre da un pallino spento. */
        row.appendChild(el('p', 'field-hint', 'Ha una credenziale ma non è in catena: HIRIS non lo consulta.'));
      } else if (inCatena && hasCred && pd.configId === 'ollama') {
        var fixedModel = state.ollamaModel || '';
        row.appendChild(el('p', 'field-hint',
          fixedModel ? ('Modello: ' + fixedModel + ' (fisso, da config add-on)') : 'Non configurato'));
      } else if (inCatena && hasCred && pd.key) {
        /* Picker "Modello di default" — SOLO per provider con una lista
           modelli (claude/openai/openrouter): opzioni da GET /api/models
           (id "anthropic"/"openai"/"openrouter"), non dal payload config
           che non porta la lista modelli. */
        var mp = findProvider(pd.id);
        if (mp && mp.models && mp.models.length) {
          var field = el('div', 'field');
          var selId = 'model-provider-' + pd.key;
          var lbl = el('label', null, 'Modello di default');
          lbl.setAttribute('for', selId);
          var sel = el('select', 'select');
          sel.id = selId;
          var currentVal = state.cfg.provider_models[pd.key] || '';
          if (!currentVal) {
            var ph = el('option', null, '(usa il default interno)');
            ph.value = '';
            ph.disabled = true;
            ph.selected = true;
            sel.appendChild(ph);
          }
          mp.models.forEach(function(m) {
            if (m === 'auto') return; // design §3.3: nessuna "auto" nel picker default
            var opt = el('option', null, modelLabel(mp.id, m));
            opt.value = m;
            if (m === currentVal) opt.selected = true;
            sel.appendChild(opt);
          });
          if (currentVal) {
            sel.value = currentVal;
            ensureOrphanOption(sel, currentVal, ' (provider fuori dalla catena)');
          }
          field.appendChild(lbl);
          field.appendChild(sel);
          var okBadge = buildSuccessBadge();
          field.appendChild(okBadge);
          var errBadge = buildErrorBadge();
          field.appendChild(errBadge);
          field.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell\'add-on'));
          row.appendChild(field);

          sel.addEventListener('change', function() {
            var prev = currentVal;
            currentVal = sel.value;
            state.cfg.provider_models[pd.key] = sel.value;
            hideErrBadge(errBadge);
            putModelsConfig().then(function(ok) {
              if (!ok) {
                currentVal = prev;
                state.cfg.provider_models[pd.key] = prev;
                sel.value = prev;
                showErrBadge(errBadge);
              } else {
                flashSuccess(okBadge);
              }
            });
          });
        }
      }
      body.appendChild(row);
    });

    if (!anyInCatena) {
      body.appendChild(el('p', 'banner-warn',
        'Nessun provider in catena. HIRIS non può rispondere finché non ne metti almeno uno in catena.'));
    }

    var callout = el('div', 'info-callout');
    callout.appendChild(el('span', null, 'ℹ'));
    callout.appendChild(el('span', null,
      'Le credenziali vivono nella configurazione dell\'add-on; la catena si decide qui. ' +
      'Aggiungere una chiave non mette il provider in catena: lo rende disponibile, e sta a te metterlo in catena.'));
    body.appendChild(callout);
  }

  function renderSection1Error() {
    var body = clearEl(byId('sec1-body'));
    if (!body) return;
    body.appendChild(el('p', 'proposals-error', 'Errore caricamento provider.'));
    var btn = el('button', 'btn btn-ghost btn-sm', 'Riprova');
    btn.type = 'button';
    btn.addEventListener('click', function() { loadModelsAndConfig(); });
    body.appendChild(btn);

    var body2 = clearEl(byId('sec2-body'));
    if (body2) body2.appendChild(el('p', 'field-hint', 'Impossibile caricare la catena — vedi Provider e credenziali qui sopra.'));
    var body4 = clearEl(byId('sec4-body'));
    if (body4) body4.appendChild(el('p', 'field-hint', 'Non configurato — si imposta da memory.embedding_provider in Configurazione add-on.'));
  }

  /* ── Sezione 2: Catena automatica ─────────────────────────────────────
     design §4.3: chain_order persistito può contenere provider non-usabili
     (es. openrouter senza credenziale) -- non mostrati, ma ricostruiti in
     coda intatti a ogni PUT così non "saltano" in cima se tornano usabili. */
  function buildDisplayChain(keys) {
    var order = state.cfg.chain_order.filter(function(k) { return keys.indexOf(k) !== -1; });
    keys.forEach(function(k) { if (order.indexOf(k) === -1) order.push(k); });
    return order;
  }

  /* Mappa label preset llm_strategy -> IT (design §4, "Mappa label preset").
     Fallback al valore grezzo se sconosciuto (design §11 punto 2, stesso
     pattern di modelLabel per provider senza mapping). */
  var STRATEGY_LABELS = {
    balanced: 'Bilanciato',
    cost_first: 'Risparmio',
    quality_first: 'Qualità massima'
  };

  function strategyLabel(raw) {
    raw = raw || 'balanced';
    return STRATEGY_LABELS[raw] || raw;
  }

  function providerLabelForKey(key) {
    var pd = PROVIDER_ORDER.filter(function(x) { return x.key === key; })[0];
    if (!pd) return key;
    var p = findProvider(pd.id);
    if (p && p.label) return p.label;
    var cp = findConfigProvider(pd.configId);
    return (cp && cp.label) || key;
  }

  function renderSection2(errText) {
    var body = clearEl(byId('sec2-body'));
    if (!body) return;

    /* Task 7-fix punto 6: preset reale da llm_strategy (payload config), non
       una stringa generica. UX review: era duplicato con la sc-desc statica
       ("Il preset attivo... si imposta in Configurazione add-on") — consolidato
       in un'unica frase qui; la sc-desc statica ora parla solo di ordine/frecce. */
    body.appendChild(el('p', 'field-hint', 'Preset corrente: ' + strategyLabel(state.llmStrategy) + '.'));

    var keys = usableKeys();
    var shown = buildDisplayChain(keys);

    /* Una configurazione oggi INESPRIMIBILE da questa pagina, dichiarata
       invece che taciuta: chi ha una credenziale e sta fuori dalla catena non
       può essere messo in catena da qui -- il controllo che lo fa arriva con
       il ridisegno di questa pagina. Fino ad allora la pagina lo dice, perché
       il contrario (un provider configurato che non risponde mai, senza una
       riga che spieghi perché) è la stessa opacità che questa pagina esiste
       per togliere. */
    var fuoriConCredenziale = (state.configProviders || []).filter(function(p) {
      return p && p.has_credential && !p.in_catena && p.id !== 'subscription';
    });
    if (fuoriConCredenziale.length) {
      body.appendChild(el('p', 'field-hint',
        'Fuori dalla catena, con credenziale: ' +
        fuoriConCredenziale.map(function(p) { return p.label; }).join(', ') +
        '. Da qui la catena si riordina; per aggiungerne uno serve il prossimo aggiornamento della pagina.'));
    }

    if (shown.length === 0) {
      body.appendChild(el('p', 'field-hint',
        'Nessun provider in catena — mettine almeno uno in catena per definirne l\'ordine.'));
      return;
    }

    shown.forEach(function(key, idx) {
      var label = providerLabelForKey(key);
      var row = el('div', 'chain-row');
      row.setAttribute('role', 'listitem');
      row.appendChild(el('span', 'chain-num', String(idx + 1)));
      row.appendChild(el('span', 'chain-label', label));
      if (shown.length > 1) {
        var up = el('button', 'btn-icon-only', '↑');
        up.type = 'button';
        up.setAttribute('aria-label', 'Sposta "' + label + '" su, posizione ' + (idx + 1) + ' di ' + shown.length);
        if (idx === 0) up.disabled = true;
        up.addEventListener('click', function() { moveChain(idx, -1); });
        var down = el('button', 'btn-icon-only', '↓');
        down.type = 'button';
        down.setAttribute('aria-label', 'Sposta "' + label + '" giù, posizione ' + (idx + 1) + ' di ' + shown.length);
        if (idx === shown.length - 1) down.disabled = true;
        down.addEventListener('click', function() { moveChain(idx, 1); });
        row.appendChild(up);
        row.appendChild(down);
      } else {
        row.appendChild(el('span'));
        row.appendChild(el('span'));
      }
      body.appendChild(row);
    });

    body.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell\'add-on'));
    if (errText) body.appendChild(el('p', 'proposals-error', errText));
  }

  function moveChain(idx, dir) {
    var keys = usableKeys();
    var shown = buildDisplayChain(keys);

    /* Una configurazione oggi INESPRIMIBILE da questa pagina, dichiarata
       invece che taciuta: chi ha una credenziale e sta fuori dalla catena non
       può essere messo in catena da qui -- il controllo che lo fa arriva con
       il ridisegno di questa pagina. Fino ad allora la pagina lo dice, perché
       il contrario (un provider configurato che non risponde mai, senza una
       riga che spieghi perché) è la stessa opacità che questa pagina esiste
       per togliere. */
    var fuoriConCredenziale = (state.configProviders || []).filter(function(p) {
      return p && p.has_credential && !p.in_catena && p.id !== 'subscription';
    });
    if (fuoriConCredenziale.length) {
      body.appendChild(el('p', 'field-hint',
        'Fuori dalla catena, con credenziale: ' +
        fuoriConCredenziale.map(function(p) { return p.label; }).join(', ') +
        '. Da qui la catena si riordina; per aggiungerne uno serve il prossimo aggiornamento della pagina.'));
    }
    var j = idx + dir;
    if (j < 0 || j >= shown.length) return;
    var tmp = shown[idx]; shown[idx] = shown[j]; shown[j] = tmp;
    var rest = state.cfg.chain_order.filter(function(k) { return shown.indexOf(k) === -1; });
    var prevOrder = state.cfg.chain_order.slice();
    state.cfg.chain_order = shown.concat(rest);
    renderSection2();
    putModelsConfig().then(function(ok) {
      if (!ok) {
        state.cfg.chain_order = prevOrder;
        renderSection2('Errore salvataggio ordine. Riprova.');
      }
    });
  }

  /* ── Sezione 3 (Brain + Chatbot) uscita alla fetta E5 Task 7 ───────────
     renderSection3Brain scriveva PUT api/models/config brain_model: il
     Brain che lo leggeva è uscito con la E3, zero lettori di produzione da
     allora (configurazione morta, tolta anche da handlers_models.py
     load/save nello stesso commit). renderSection3Chatbot faceva PUT
     api/chatbots/{id} a ogni cambio di select: quella rotta non esisteva
     per il metodo PUT (solo GET rispondeva — uscita anch'essa, per intero,
     alla fetta E5 Task 10) — ogni salvataggio falliva con 404, sel.value
     tornava al valore precedente e compariva il badge rosso.
     Il modello della chat si cambia dal Task 2 della E5 (impostazioni
     chat), dove è sempre dovuto stare. */

  /* ── Sezione 3 (id interno "sec4", invariato — vedi buildSectionShell in
     mount()): Embeddings ─────────────────────────────────────────────────
     Sola lettura. Task 7B ha aggiunto embeddings.{provider,model} al payload
     GET /api/models/config — mostrato qui invece del fallback statico
     precedente (assunzione aperta #1 del design doc, ora risolta). */
  function renderSection4() {
    var body = clearEl(byId('sec4-body'));
    if (!body) return;
    var provider = state.embeddings && state.embeddings.provider;
    var model = state.embeddings && state.embeddings.model;
    if (provider && model) {
      body.appendChild(el('p', null, 'Provider: ' + provider + ' · Modello: ' + model));
    } else {
      body.appendChild(el('p', null, 'Non configurato — si imposta da memory.embedding_provider in Configurazione add-on.'));
    }
    body.appendChild(el('p', 'field-hint', 'Oggi nessun testo viene vettorizzato: il valore è letto e mostrato, non usato. (L\'Abbonamento non fa embeddings.)'));
  }

  /* ── Caricamento dati ─────────────────────────────────────────────────
     Le due fetch (models, models/config) partono in parallelo (§7.1);
     trattate come un'unica unità dati perché Parte 1 (picker), Parte 2
     (catena) e Parte 3 (embeddings) dipendono da entrambe. Non c'è più una
     terza fetch verso api/chatbots: la sezione che la consumava (Chatbot,
     dentro la vecchia "Assegnazione per entità") è uscita con la fetta E5
     Task 7. */
  function loadModelsAndConfig() {
    var body1 = byId('sec1-body');
    if (body1) { clearEl(body1); body1.appendChild(el('p', 'field-hint', 'Caricamento…')); }
    Promise.all([
      fetch('api/models').then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }),
      fetch('api/models/config').then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
    ]).then(function(results) {
      state.providers = results[0].providers || [];
      var cfgRaw = results[1] || {};
      state.cfg = {
        chain_order: Array.isArray(cfgRaw.chain_order) ? cfgRaw.chain_order.slice() : [],
        provider_models: Object.assign({ claude: '', openai: '', openrouter: '' }, cfgRaw.provider_models || {})
      };
      state.configProviders = Array.isArray(cfgRaw.providers) ? cfgRaw.providers : [];
      state.llmStrategy = cfgRaw.llm_strategy || '';
      state.embeddings = (cfgRaw.embeddings && typeof cfgRaw.embeddings === 'object')
        ? cfgRaw.embeddings : { provider: '', model: '' };
      state.ollamaModel = cfgRaw.ollama_model || '';
      state.adesso = (cfgRaw.adesso && typeof cfgRaw.adesso === 'object') ? cfgRaw.adesso : null;
      state.ponteAttivo = !!cfgRaw.ponte_attivo;
      var outlet = document.getElementById('route-outlet');
      var card = renderAdesso();
      /* Sopra la prima section-card: la risposta viene prima delle ragioni. */
      if (card && outlet) outlet.insertBefore(card, outlet.querySelector('.section-card'));
      renderSection1();
      renderSection2();
      renderSection4();
    }).catch(function(err) {
      console.error('models/config fetch failed', err);
      renderSection1Error();
    });
  }

  /* ── Shell statico ────────────────────────────────────────────────────── */
  function buildSectionShell(num, idPrefix, title, desc, bodyRole) {
    var section = el('section', 'section-card');
    section.id = idPrefix + '-card';
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    section.appendChild(head);
    section.appendChild(el('p', 'sc-desc', desc));
    var body = el('div', 'sc-body');
    body.id = idPrefix + '-body';
    /* Sezione 2 (Catena automatica): le righe hanno role="listitem"
       (renderSection2) — serve role="list" sul contenitore perché la
       relazione list/listitem sia esposta correttamente all'AT. */
    if (bodyRole) body.setAttribute('role', bodyRole);
    body.appendChild(el('p', 'field-hint', 'Caricamento…'));
    section.appendChild(body);
    return section;
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Modelli'));
    outlet.appendChild(el('p', 'page-subtitle', 'Chi usa cosa: provider, credenziali e catena automatica di failover.'));

    outlet.appendChild(buildSectionShell('01', 'sec1', 'Provider e credenziali',
      'Le credenziali vivono in Impostazioni → Add-on → HIRIS → Configurazione. Avere una credenziale non mette un provider in catena: HIRIS consulta soltanto chi sta in catena.'));
    outlet.appendChild(buildSectionShell('02', 'sec2', 'Catena automatica',
      'Ordine di failover quando un\'entità è in "auto". Riordina con le frecce.', 'list'));

    /* La sezione 03 originale del design doc ("Assegnazione per entità":
       Chatbot + Brain) è uscita alla fetta E5 Task 7 -- vedi il commento
       sopra renderSection4 per il perché. Embeddings diventa così la terza
       e ultima sezione della pagina (id interno invariato "sec4", numero
       mostrato "03"). */
    outlet.appendChild(buildSectionShell('03', 'sec4', 'Embeddings (oggi inattivi)',
      'Oggi nessuna parte di HIRIS calcola embedding: qui vedi solo cosa hai configurato. La ricerca per somiglianza è rimandata, non annullata.'));

    /* La sezione "03" (Embeddings) parte con il placeholder "Caricamento…"
       di buildSectionShell; viene popolata con i dati reali (o il
       fallback) da loadModelsAndConfig una volta arrivato GET
       /api/models/config (Task 7-fix punto 7). */
    loadModelsAndConfig();
  }

  window.HirisModelsRoute = { mount: mount };
})();
