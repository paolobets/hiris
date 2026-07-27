/* HIRIS · Designer · models route mount (SP-2 Task 7 + Task 7-fix)
   Sezione #/models — implementa il contratto UX di
   docs/design/2026-07-27-ux-models-section.md:
     01 Provider attivi (GET api/models/config -> providers[], badge stato +
        picker default per-provider da GET api/models)
     02 Catena automatica (GET/PUT api/models/config chain_order, riordino
        frecce, preset llm_strategy)
     03 Assegnazione per entità (Chatbot -> PUT api/agents/{id}, Brain -> PUT
        api/models/config brain_model, Agentbot -> rimando a #/sentinel)
     04 Embeddings (riga informativa, sola lettura, da GET api/models/config)
   Sicurezza: testi via textContent/createElement, mai innerHTML su dati server
   (stesso vincolo di sentinel-route.js).

   Task 7B ha arricchito GET /api/models/config con:
     providers: [{id: subscription|claude|openai|openrouter|ollama, label,
                  active, has_credential, toggle}]  (tutti e 5, ordine fisso;
                  "toggle" aggiunto in Task 7-fix2: valore grezzo del toggle
                  addon, letto da env, distinto da "active" che è già
                  toggle AND credenziale — serve per lo stato "manca
                  credenziale" quando active è false ma il toggle è acceso)
     llm_strategy: string
     embeddings: {provider, model}
     ollama_model: nome del modello Ollama fisso configurato
   (oltre a chain_order/brain_model/provider_models già presenti). Questo file
   consuma quell'arricchimento invece di dedurre badge/stato da GET /api/models
   (che elenca solo i provider già credenziati, senza i disattivi/senza
   credenziale — vedi report Task 7-fix). */
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
    { configId: 'subscription', id: null, key: null, fallbackLabel: 'Abbonamento (Claude Max)' },
    { configId: 'claude', id: 'anthropic', key: 'claude', fallbackLabel: 'Claude API' },
    { configId: 'openai', id: 'openai', key: 'openai', fallbackLabel: 'OpenAI' },
    { configId: 'openrouter', id: 'openrouter', key: 'openrouter', fallbackLabel: 'OpenRouter' },
    { configId: 'ollama', id: 'ollama', key: 'ollama', fallbackLabel: 'Locale (Ollama)' }
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
     da chi crea il badge con buildSuccessBadge(). Riusato sia dai PUT
     models-config (§7.2) sia dal PUT per-Chatbot (§7.3). */
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

  /* ── Stato locale ──────────────────────────────────────────────────── */
  var state = {
    providers: [],        // GET api/models -> providers[] (solo credenziati, id anthropic/openai/openrouter/ollama)
    configProviders: [],  // GET api/models/config -> providers[] (tutti e 5, id subscription/claude/openai/openrouter/ollama)
    llmStrategy: '',       // GET api/models/config -> llm_strategy
    embeddings: { provider: '', model: '' },  // GET api/models/config -> embeddings
    ollamaModel: '',       // GET api/models/config -> ollama_model
    cfg: { chain_order: [], brain_model: 'auto', provider_models: { claude: '', openai: '', openrouter: '' } },
    agents: []            // GET api/agents
  };
  var providersReady = false;
  var agentsReady = false;

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

  /* Provider "usabili" = attivi + con credenziale (design §0.5/§4.1), fonte:
     GET /api/models (che lista solo chi ha già una lista modelli disponibile).
     "subscription" (key null) non entra mai qui: non fa parte di chain_order/
     provider_models nel contratto backend attuale (_VALID_BACKENDS). */
  function usableProviders() {
    var list = [];
    PROVIDER_ORDER.forEach(function(pd) {
      if (!pd.key) return;
      var p = findProvider(pd.id);
      if (p && p.active && p.has_credential) list.push(p);
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
     perso silenziosamente (design §5.1). Usata sia dal picker condiviso
     Brain/Chatbot (fillModelOptions) sia dal picker default-provider di
     Parte 1 (Task 7-fix punto 5). */
  function ensureOrphanOption(sel, val, suffix) {
    if (!val) return;
    if (sel.value === val) return; // già selezionabile, nessuna orfana da inserire
    var orphan = el('option', null, val + suffix);
    orphan.value = val;
    sel.insertBefore(orphan, sel.firstChild);
    sel.value = val;
  }

  /* ── Sezione 3: dropdown modello condivisa (Brain / Chatbot) ─────────
     Stesso value-format già in uso in tutta la SPA (agent.model, sentinel
     per-Agentbot picker in sentinel-route.js): id modello grezzo così come
     ritornato da GET api/models, "auto" come opzione top-level unica. */
  function fillModelOptions(sel, currentValue) {
    clearEl(sel);
    var autoOpt = el('option', null, 'auto');
    autoOpt.value = 'auto';
    sel.appendChild(autoOpt);
    usableProviders().forEach(function(p) {
      var grp = document.createElement('optgroup');
      grp.label = p.label;
      (p.models || []).forEach(function(m) {
        if (m === 'auto') return;
        var opt = el('option', null, modelLabel(p.id, m));
        opt.value = m;
        grp.appendChild(opt);
      });
      if (grp.children.length) sel.appendChild(grp);
    });
    var val = currentValue || 'auto';
    sel.value = val;
    /* Il modello salvato non è più offerto da nessun provider usabile
       (provider disattivato nel frattempo) — resta selezionato e visibile,
       segnalato, nessuna azione forzata (design §5.1). */
    ensureOrphanOption(sel, val, ' (provider non attivo)');
  }

  /* ── Sezione 1: Provider attivi ──────────────────────────────────────── */
  function renderSection1() {
    var body = clearEl(byId('sec1-body'));
    if (!body) return;

    var anyActive = false;
    PROVIDER_ORDER.forEach(function(pd) {
      var cp = findConfigProvider(pd.configId);
      var active = !!(cp && cp.active);
      var hasCred = !!(cp && cp.has_credential);
      var toggle = !!(cp && cp.toggle);
      /* design §3.2: "active" (toggle AND credential, già calcolato lato
         server) collassa "toggle ON ma credenziale mancante" in false, quindi
         non basta per distinguere "Disattivato" da "⚠ manca credenziale" — da
         qui l'uso del campo "toggle" grezzo (Task 7-fix2) solo per lo stato
         intermedio quando active è false. */
      var missingCred = !active && toggle && !hasCred;
      if (active) anyActive = true;
      var label = cp ? cp.label : pd.fallbackLabel;

      var row = el('div', 'provider-row');
      var head = el('div', 'provider-row-head');
      var dotCls = active ? 'on' : (missingCred ? 'warn' : 'off');
      head.appendChild(el('span', 'dot ' + dotCls));
      head.appendChild(el('span', 'provider-row-label', label));
      var badgeCls = active ? 'badge-on' : (missingCred ? 'badge-warn' : 'badge-off');
      var badgeTxt = active ? 'Attivo' : (missingCred ? '⚠ manca credenziale' : 'Disattivato');
      head.appendChild(el('span', 'agent-badge ' + badgeCls, badgeTxt));
      row.appendChild(head);

      if (missingCred) {
        row.appendChild(el('p', 'field-hint', 'Aggiungi la chiave in Configurazione add-on per attivarlo davvero.'));
      } else if (active && hasCred && pd.configId === 'ollama') {
        var fixedModel = state.ollamaModel || '';
        row.appendChild(el('p', 'field-hint',
          fixedModel ? ('Modello: ' + fixedModel + ' (fisso, da config add-on)') : 'Non configurato'));
      } else if (active && hasCred && pd.key) {
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
            ensureOrphanOption(sel, currentVal, ' (provider non attivo)');
          }
          field.appendChild(lbl);
          field.appendChild(sel);
          var okBadge = buildSuccessBadge();
          field.appendChild(okBadge);
          var errBadge = el('span', 'agent-badge badge-warn', '⚠ Salvataggio non riuscito');
          errBadge.style.display = 'none';
          errBadge.setAttribute('aria-live', 'polite');
          field.appendChild(errBadge);
          field.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell\'addon'));
          row.appendChild(field);

          sel.addEventListener('change', function() {
            var prev = currentVal;
            currentVal = sel.value;
            state.cfg.provider_models[pd.key] = sel.value;
            errBadge.style.display = 'none';
            putModelsConfig().then(function(ok) {
              if (!ok) {
                currentVal = prev;
                state.cfg.provider_models[pd.key] = prev;
                sel.value = prev;
                errBadge.style.display = '';
              } else {
                flashSuccess(okBadge);
              }
            });
          });
        }
      }
      body.appendChild(row);
    });

    if (!anyActive) {
      body.appendChild(el('p', 'banner-warn',
        'Nessun provider attivo. HIRIS non può rispondere finché non ne attivi almeno uno nella configurazione dell\'add-on.'));
    }

    var callout = el('div', 'info-callout');
    callout.appendChild(el('span', null, 'ℹ'));
    callout.appendChild(el('span', null,
      'I toggle vivono nella configurazione dell\'add-on, non qui. Attivarne uno da lì non riattiva ' +
      'automaticamente gli altri provider oggi spenti — vanno riattivati singolarmente se ti servono anche loro attivi in parallelo.'));
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
    if (body2) body2.appendChild(el('p', 'field-hint', 'Impossibile caricare la catena — vedi Provider attivi qui sopra.'));
    var brainBody = clearEl(byId('sec3-brain-body'));
    if (brainBody) brainBody.appendChild(el('p', 'field-hint', 'Impossibile caricare i modelli disponibili.'));
    var body4 = clearEl(byId('sec4-body'));
    if (body4) body4.appendChild(el('p', 'field-hint', 'Non configurato — vedi local_model in Configurazione add-on.'));
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
    return p ? p.label : pd.fallbackLabel;
  }

  function renderSection2(errText) {
    var body = clearEl(byId('sec2-body'));
    if (!body) return;

    /* Task 7-fix punto 6: preset reale da llm_strategy (payload config),
       non una stringa generica. */
    body.appendChild(el('p', 'field-hint', 'Preset: ' + strategyLabel(state.llmStrategy)));

    var keys = usableKeys();
    var shown = buildDisplayChain(keys);

    if (shown.length === 0) {
      body.appendChild(el('p', 'field-hint',
        'Nessun provider attivo e con credenziale — attivane almeno uno in Parte 1 per definire una catena.'));
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

    body.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell\'addon'));
    if (errText) body.appendChild(el('p', 'proposals-error', errText));
  }

  function moveChain(idx, dir) {
    var keys = usableKeys();
    var shown = buildDisplayChain(keys);
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

  /* ── Sezione 3: Brain ─────────────────────────────────────────────────
     brain_model è live (nessun hint boot-time, design §7.4). */
  function renderSection3Brain() {
    var wrap = clearEl(byId('sec3-brain-body'));
    if (!wrap) return;
    var field = el('div', 'field');
    var lbl = el('label', null, 'Ragionamento core');
    lbl.setAttribute('for', 'model-brain');
    var sel = el('select', 'select');
    sel.id = 'model-brain';
    fillModelOptions(sel, state.cfg.brain_model);
    field.appendChild(lbl);
    field.appendChild(sel);
    var okBadge = buildSuccessBadge();
    field.appendChild(okBadge);
    var errBadge = el('span', 'agent-badge badge-warn', '⚠ Salvataggio non riuscito');
    errBadge.style.display = 'none';
    errBadge.setAttribute('aria-live', 'polite');
    field.appendChild(errBadge);
    wrap.appendChild(field);

    sel.addEventListener('change', function() {
      var prev = state.cfg.brain_model;
      state.cfg.brain_model = sel.value;
      errBadge.style.display = 'none';
      putModelsConfig().then(function(ok) {
        if (!ok) {
          state.cfg.brain_model = prev;
          sel.value = prev;
          errBadge.style.display = '';
        } else {
          flashSuccess(okBadge);
        }
      });
    });
  }

  /* ── Sezione 3: Chatbot ───────────────────────────────────────────────
     model per-Chatbot è live, PUT diretto e isolato per riga (design §7.3). */
  function renderSection3Chatbot() {
    var body = clearEl(byId('sec3-chatbot-body'));
    if (!body) return;
    if (!state.agents.length) {
      body.appendChild(el('p', 'field-hint', 'Nessun Chatbot configurato.'));
      var link = el('a', 'btn btn-ghost btn-sm', 'Crea il primo Chatbot →');
      link.href = '#/agents';
      body.appendChild(link);
      return;
    }
    var sorted = state.agents.slice().sort(function(a, b) {
      var ea = a.enabled ? 1 : 0, eb = b.enabled ? 1 : 0;
      if (eb !== ea) return eb - ea;
      return (a.name || '').localeCompare(b.name || '');
    });
    sorted.forEach(function(a) {
      var field = el('div', 'field');
      var selId = 'model-agent-' + a.id;
      var lbl = el('label', null, a.name || a.id);
      lbl.setAttribute('for', selId);
      var sel = el('select', 'select');
      sel.id = selId;
      fillModelOptions(sel, a.model || 'auto');
      field.appendChild(lbl);
      field.appendChild(sel);
      var okBadge = buildSuccessBadge();
      field.appendChild(okBadge);
      var errBadge = el('span', 'agent-badge badge-warn', '⚠ Salvataggio non riuscito');
      errBadge.style.display = 'none';
      errBadge.setAttribute('aria-live', 'polite');
      field.appendChild(errBadge);
      body.appendChild(field);

      sel.addEventListener('change', function() {
        var prev = a.model || 'auto';
        var next = sel.value;
        errBadge.style.display = 'none';
        api('api/agents/' + encodeURIComponent(a.id), {
          method: 'PUT',
          body: JSON.stringify({ model: next })
        }).then(function(r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }).then(function(updated) {
          a.model = (updated && updated.model) || next;
          flashSuccess(okBadge);
        }).catch(function(err) {
          console.error('save agent model failed', err);
          sel.value = prev;
          errBadge.style.display = '';
        });
      });
    });
  }

  function renderSection3ChatbotError() {
    var body = clearEl(byId('sec3-chatbot-body'));
    if (body) body.appendChild(el('p', 'proposals-error', 'Errore caricamento Chatbot.'));
  }

  /* ── Sezione 4: Embeddings ────────────────────────────────────────────
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
      body.appendChild(el('p', null, 'Non configurato — vedi local_model in Configurazione add-on.'));
    }
    body.appendChild(el('p', 'field-hint', 'L\'Abbonamento non fa embeddings.'));
  }

  /* ── Caricamento dati ─────────────────────────────────────────────────
     Le tre fetch (models, models/config, agents) partono in parallelo (§7.1);
     models+models/config sono trattati come un'unica unità dati perché
     Parte 1 (picker), Parte 2 (catena), Parte 3-Brain e Parte 4 (embeddings)
     dipendono da entrambe. */
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
        brain_model: cfgRaw.brain_model || 'auto',
        provider_models: Object.assign({ claude: '', openai: '', openrouter: '' }, cfgRaw.provider_models || {})
      };
      state.configProviders = Array.isArray(cfgRaw.providers) ? cfgRaw.providers : [];
      state.llmStrategy = cfgRaw.llm_strategy || '';
      state.embeddings = (cfgRaw.embeddings && typeof cfgRaw.embeddings === 'object')
        ? cfgRaw.embeddings : { provider: '', model: '' };
      state.ollamaModel = cfgRaw.ollama_model || '';
      providersReady = true;
      renderSection1();
      renderSection2();
      renderSection3Brain();
      renderSection4();
      if (agentsReady) renderSection3Chatbot();
    }).catch(function(err) {
      console.error('models/config fetch failed', err);
      renderSection1Error();
    });
  }

  function loadAgents() {
    var body = byId('sec3-chatbot-body');
    if (body) { clearEl(body); body.appendChild(el('p', 'field-hint', 'Caricamento…')); }
    fetch('api/agents').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(d) {
      state.agents = Array.isArray(d) ? d : (d.agents || []);
      agentsReady = true;
      if (providersReady) renderSection3Chatbot();
    }).catch(function(err) {
      console.error('agents fetch failed', err);
      renderSection3ChatbotError();
    });
  }

  /* ── Shell statico ────────────────────────────────────────────────────── */
  function buildSectionShell(num, idPrefix, title, desc) {
    var section = el('section', 'section-card');
    section.id = idPrefix + '-card';
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    section.appendChild(head);
    section.appendChild(el('p', 'sc-desc', desc));
    var body = el('div', 'sc-body');
    body.id = idPrefix + '-body';
    body.appendChild(el('p', 'field-hint', 'Caricamento…'));
    section.appendChild(body);
    return section;
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Modelli'));
    outlet.appendChild(el('p', 'page-subtitle', 'Chi usa cosa: provider attivi, catena automatica e modello per entità.'));

    outlet.appendChild(buildSectionShell('01', 'sec1', 'Provider attivi',
      'Riflesso della configurazione dell\'add-on. Per attivare o disattivare un provider vai su Impostazioni → Add-on → HIRIS → Configurazione.'));
    outlet.appendChild(buildSectionShell('02', 'sec2', 'Catena automatica',
      'Ordine di failover quando un\'entità è in "auto". Riordina con le frecce. Il preset attivo (llm_strategy) si imposta in Configurazione add-on.'));

    var sec3 = buildSectionShell('03', 'sec3', 'Assegnazione per entità',
      'Ogni entità usa "auto" (segue la catena) o un modello esplicito.');
    outlet.appendChild(sec3);
    /* buildSectionShell già mette un placeholder "Caricamento…" in sec3-body;
       lo sostituiamo con i tre field-group Chatbot/Brain/Agentbot. */
    var sec3body = byId('sec3-body');
    clearEl(sec3body);

    var gChatbot = el('div', 'field-group');
    gChatbot.appendChild(el('div', 'fg-label', 'Chatbot'));
    var chatbotBody = el('div');
    chatbotBody.id = 'sec3-chatbot-body';
    chatbotBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    gChatbot.appendChild(chatbotBody);
    sec3body.appendChild(gChatbot);

    var gBrain = el('div', 'field-group');
    gBrain.appendChild(el('div', 'fg-label', 'Brain'));
    var brainBody = el('div');
    brainBody.id = 'sec3-brain-body';
    brainBody.appendChild(el('p', 'field-hint', 'Caricamento…'));
    gBrain.appendChild(brainBody);
    sec3body.appendChild(gBrain);

    var gAgentbot = el('div', 'field-group');
    gAgentbot.appendChild(el('div', 'fg-label', 'Agentbot'));
    var agentbotBlock = el('div', 'field-hint-block');
    agentbotBlock.appendChild(el('p', null, 'Il modello per singolo Agentbot si imposta nel suo editor, non qui.'));
    var sentinelLink = el('a', 'btn btn-ghost btn-sm', 'Vai a Agentbot →');
    sentinelLink.href = '#/sentinel';
    agentbotBlock.appendChild(sentinelLink);
    gAgentbot.appendChild(agentbotBlock);
    sec3body.appendChild(gAgentbot);

    outlet.appendChild(buildSectionShell('04', 'sec4', 'Embeddings',
      'Usati per RAG e memoria semantica — non fanno parte della catena sopra e non sono assegnabili per entità.'));

    providersReady = false;
    agentsReady = false;
    /* Sezione 4 parte con il placeholder "Caricamento…" di buildSectionShell;
       viene popolata con i dati reali (o il fallback) da loadModelsAndConfig
       una volta arrivato GET /api/models/config (Task 7-fix punto 7). */
    loadModelsAndConfig();
    loadAgents();
  }

  window.HirisModelsRoute = { mount: mount };
})();
