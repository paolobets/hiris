/* HIRIS · Designer · models route mount (SP-2 Task 7)
   Sezione #/models — implementa il contratto UX di
   docs/design/2026-07-27-ux-models-section.md:
     01 Provider attivi (GET api/models, badge stato + picker default per-provider)
     02 Catena automatica (GET/PUT api/models/config chain_order, riordino frecce)
     03 Assegnazione per entità (Chatbot -> PUT api/agents/{id}, Brain -> PUT
        api/models/config brain_model, Agentbot -> rimando a #/sentinel)
     04 Embeddings (riga informativa, sola lettura)
   Sicurezza: testi via textContent/createElement, mai innerHTML su dati server
   (stesso vincolo di sentinel-route.js). */
(function() {
  'use strict';

  /* Ordine fisso di visualizzazione Parte 1/2 (design §3.1: "sempre in
     quest'ordine, attivi o no, così la lista non salta"). "id" è l'id nel
     payload GET /api/models; "key" è la chiave usata in chain_order /
     provider_models (vedi handlers_models.py _VALID_BACKENDS).
     Nota implementazione (assunzione risolta, vedi report): il contratto
     GET /api/models attuale (Task 5) espone solo anthropic/openai/openrouter/
     ollama -- non esiste un provider "subscription/Abbonamento" separato nel
     payload, quindi quella riga del wireframe di design non è renderizzabile
     e viene omessa qui. */
  var PROVIDER_ORDER = [
    { id: 'anthropic', key: 'claude', fallbackLabel: 'Claude API' },
    { id: 'openai', key: 'openai', fallbackLabel: 'OpenAI' },
    { id: 'openrouter', key: 'openrouter', fallbackLabel: 'OpenRouter' },
    { id: 'ollama', key: 'ollama', fallbackLabel: 'Locale (Ollama)' }
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

  /* ── Stato locale ──────────────────────────────────────────────────── */
  var state = {
    providers: [],  // GET api/models -> providers[]
    cfg: { chain_order: [], brain_model: 'auto', provider_models: { claude: '', openai: '', openrouter: '' } },
    agents: []      // GET api/agents
  };
  var providersReady = false;
  var agentsReady = false;

  function findProvider(id) {
    for (var i = 0; i < state.providers.length; i++) {
      if (state.providers[i].id === id) return state.providers[i];
    }
    return null;
  }

  /* Provider "usabili" = attivi + con credenziale (design §0.5/§4.1). Con il
     contratto attuale has_credential è sempre true quando active è true (vedi
     report), ma il controllo esplicito resta per fedeltà al contratto
     documentato. */
  function usableProviders() {
    var list = [];
    PROVIDER_ORDER.forEach(function(pd) {
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

  /* ── PUT api/models/config — SEMPRE l'oggetto intero (§7.2) ─────────── */
  function putModelsConfig() {
    return api('api/models/config', { method: 'PUT', body: JSON.stringify(state.cfg) })
      .then(function(r) { return r.ok; })
      .catch(function() { return false; });
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
    if (sel.value !== val) {
      /* Il modello salvato non è più offerto da nessun provider usabile
         (provider disattivato nel frattempo) — resta selezionato e visibile,
         segnalato, nessuna azione forzata (design §5.1). */
      var orphan = el('option', null, val + ' (provider non attivo)');
      orphan.value = val;
      sel.insertBefore(orphan, sel.firstChild);
      sel.value = val;
    }
  }

  /* ── Sezione 1: Provider attivi ──────────────────────────────────────── */
  function renderSection1() {
    var body = clearEl(byId('sec1-body'));
    if (!body) return;

    var anyActive = false;
    PROVIDER_ORDER.forEach(function(pd) {
      var p = findProvider(pd.id);
      var active = !!(p && p.active);
      var hasCred = !!(p && p.has_credential);
      if (active) anyActive = true;
      var label = p ? p.label : pd.fallbackLabel;

      var row = el('div', 'provider-row');
      var head = el('div', 'provider-row-head');
      var dotCls = active ? 'on' : ((p && !hasCred) ? 'warn' : 'off');
      head.appendChild(el('span', 'dot ' + dotCls));
      head.appendChild(el('span', 'provider-row-label', label));
      var badgeCls = active ? 'badge-on' : ((p && !hasCred) ? 'badge-warn' : 'badge-off');
      var badgeTxt = active ? 'Attivo' : ((p && !hasCred) ? '⚠ manca credenziale' : 'Disattivato');
      head.appendChild(el('span', 'agent-badge ' + badgeCls, badgeTxt));
      row.appendChild(head);

      if (active && p && !hasCred) {
        row.appendChild(el('p', 'field-hint', 'Aggiungi la chiave in Configurazione add-on per attivarlo davvero.'));
      } else if (active && pd.id === 'ollama') {
        var fixedModel = (p.models && p.models[0]) || '';
        row.appendChild(el('p', 'field-hint', 'Modello: ' + fixedModel + ' (fisso, da config add-on)'));
      } else if (active && p && p.models && p.models.length) {
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
        p.models.forEach(function(m) {
          if (m === 'auto') return; // design §3.3: nessuna "auto" nel picker default
          var opt = el('option', null, modelLabel(p.id, m));
          opt.value = m;
          if (m === currentVal) opt.selected = true;
          sel.appendChild(opt);
        });
        field.appendChild(lbl);
        field.appendChild(sel);
        var errBadge = el('span', 'agent-badge badge-warn', '⚠ Salvataggio non riuscito');
        errBadge.style.display = 'none';
        errBadge.setAttribute('aria-live', 'polite');
        field.appendChild(errBadge);
        field.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell’addon'));
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
            }
          });
        });
      }
      body.appendChild(row);
    });

    if (!anyActive) {
      body.appendChild(el('p', 'banner-warn',
        'Nessun provider attivo. HIRIS non può rispondere finché non ne attivi almeno uno nella configurazione dell’add-on.'));
    }

    var callout = el('div', 'info-callout');
    callout.appendChild(el('span', null, 'ℹ'));
    callout.appendChild(el('span', null,
      'I toggle vivono nella configurazione dell’add-on, non qui. Attivarne uno da lì non riattiva ' +
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

  function providerLabelForKey(key) {
    var pd = PROVIDER_ORDER.filter(function(x) { return x.key === key; })[0];
    if (!pd) return key;
    var p = findProvider(pd.id);
    return p ? p.label : pd.fallbackLabel;
  }

  function renderSection2(errText) {
    var body = clearEl(byId('sec2-body'));
    if (!body) return;
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

    body.appendChild(el('p', 'model-boot-hint', 'riapplicato al riavvio dell’addon'));
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
     Sola lettura, dato statico: né GET api/models né GET api/models/config
     espongono embedding_provider/embedding_model oggi (assunzione aperta
     #1 del design doc) -- fuori scope per Task 7 (frontend-only), quindi si
     mostra il fallback "non configurato" documentato dal design invece di
     inventare un terzo endpoint o dati non disponibili. */
  function renderSection4() {
    var body = clearEl(byId('sec4-body'));
    if (!body) return;
    body.appendChild(el('p', null, 'Non configurato — vedi local_model in Configurazione add-on.'));
    body.appendChild(el('p', 'field-hint', 'L’Abbonamento non fa embeddings.'));
  }

  /* ── Caricamento dati ─────────────────────────────────────────────────
     Le tre fetch (providers+config, agents) partono in parallelo (§7.1);
     providers+config sono trattati come un'unica unità dati perché Parte 1
     (picker), Parte 2 (catena) e Parte 3-Brain dipendono da entrambe. */
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
      providersReady = true;
      renderSection1();
      renderSection2();
      renderSection3Brain();
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
      'Riflesso della configurazione dell’add-on. Per attivare o disattivare un provider vai su Impostazioni → Add-on → HIRIS → Configurazione.'));
    outlet.appendChild(buildSectionShell('02', 'sec2', 'Catena automatica',
      'Ordine di failover quando un’entità è in "auto". Riordina con le frecce. Il preset attivo (llm_strategy) si imposta in Configurazione add-on.'));

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
    renderSection4();
    loadModelsAndConfig();
    loadAgents();
  }

  window.HirisModelsRoute = { mount: mount };
})();
