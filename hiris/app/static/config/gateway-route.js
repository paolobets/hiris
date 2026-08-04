/* HIRIS · Config · Accessi Gateway (route #/gateway)
   Semaforo per categoria (Off / 🟢 / 🟡 / 🔴), servizio notifica configurabile,
   e coda "Da approvare (inbox)" (Giallo/Rosso, gateway o chat) con Approva/Rifiuta.
   Sicurezza: testi dinamici via textContent / nodi DOM, mai innerHTML. */
window.HirisGatewayRoute = (function () {
  'use strict';

  var EMOJI = {
    light: '💡', scene: '🎬', script: '📝', climate: '🌡️',
    cover: '🪟', media_player: '📺', switch: '🔌', fan: '🌀',
    vacuum: '🧹', humidifier: '💧', water_heater: '♨️', valve: '🚰',
    siren: '📢', lawn_mower: '🌿', select: '🔽', number: '🔢',
    button: '🔘', input_boolean: '🎚️', automation: '⚙️', remote: '🎮',
    lock: '🔒', alarm_control_panel: '🚨'
  };
  var LEVELS = [
    ['off', 'Off (blocca)'],
    ['green', '🟢 Verde (esegui subito)'],
    ['yellow', '🟡 Giallo (notifica + approva)'],
    ['red', '🔴 Rosso (conferma manuale)']
  ];
  var VALID = { off: 1, green: 1, yellow: 1, red: 1 };

  /* M-7: la denylist DANGEROUS_DOMAINS non e' piu' ricopiata a mano qui
     (era disallineata dal backend -- conteneva "garage_door", che non e'
     nemmeno una categoria valida in GATEWAY_CATEGORIES, e usava una parola
     diversa da quella mostrata all'utente per "cover"). Ogni categoria
     arriva dal backend con il flag booleano `dangerous`
     (handlers_gateway_policy.py::handle_get_gateway_policy, calcolato da
     security/semaphore.py::DANGEROUS_DOMAINS -- una sola fonte, stesso
     principio gia' in uso per l'Autonomia del Chatbot). */

  /* Testo dell'avviso sotto ogni categoria pericolosa, legato al livello
     selezionato (I-2) e verificato contro il comportamento reale DOPO S-1
     (handlers_execute.py forza sempre rosso un dominio pericoloso prima di
     creare il pending, qualunque livello sia salvato):
     - off/green: l'esecuzione e' negata SEMPRE (off per configurazione,
       verde perche' il dispatcher nega comunque via denylist -- vedi
       security/semaphore.py::gate_action, chiamato con tier_confirmed=False
       su questo percorso);
     - giallo/rosso: finiscono comunque in coda, ma dopo S-1 richiedono
       SEMPRE l'approvazione manuale qui in HIRIS -- mai un tocco sulla
       notifica, perche' handlers_execute.py non lascia mai nascere un
       pending giallo (quindi mai actionable) per questi domini. */
  function dangerHintText(level) {
    if (level === 'yellow' || level === 'red') {
      return '🔒 dominio pericoloso: finisce comunque in coda, ma richiede sempre ' +
        'conferma manuale qui in HIRIS — mai un tocco sulla notifica, qualunque sia il livello scelto.';
    }
    return '🔒 sempre bloccato (dominio pericoloso)';
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {}
    );
    return fetch('api/gateway' + path, opts);
  }

  var ENT_LEVELS = { off: 1, green: 1, yellow: 1, red: 1 };
  var ENT_RE = /^[a-z][a-z0-9_]*\.[a-z0-9_]+$/;
  function parseEntityOverrides(text) {
    var out = {};
    (text || '').split('\n').forEach(function (line) {
      var parts = line.trim().split(/\s+/);
      if (parts.length !== 2) return;
      var eid = parts[0], lvl = parts[1];
      if (ENT_RE.test(eid) && ENT_LEVELS[lvl]) out[eid] = lvl;
    });
    return out;
  }
  function entitiesToText(entities) {
    return Object.keys(entities || {}).sort().map(function (eid) {
      return eid + ' ' + entities[eid];
    }).join('\n');
  }

  /* Coda vuota e coda illeggibile sono due fatti diversi e vanno detti in
     modo diverso -- stessa regola del pannello Memoria della chat
     (chat/knowledge.js::renderError/load): "nessun comando in attesa" non e'
     la stessa cosa di "non sono riuscito a leggere la coda", e prima di
     questa correzione la seconda si presentava come la prima (la sezione
     spariva senza dire nulla).
     M-8: classe distinta (.gw-error) invece di uno stile inline -- stessa
     convenzione di .proposals-error/.kb-error. */
  function renderPendingError(host) {
    host.innerHTML = '';
    var card = el('section', 'section-card');
    var b = el('div', 'sc-body');
    b.appendChild(el('p', 'sc-desc gw-error', 'Non è stato possibile leggere la coda delle approvazioni. Riprova più tardi.'));
    card.appendChild(b);
    host.appendChild(card);
  }

  function renderPending(host, list) {
    host.innerHTML = '';
    list = list || [];
    var card = el('section', 'section-card');
    var b = el('div', 'sc-body');
    // M-8: la coda vuota porta la STESSA intestazione della coda piena
    // (prima spariva del tutto, senza dire nemmeno "Da approvare (inbox)").
    b.appendChild(el('h2', 'sc-title', 'Da approvare (inbox) (' + list.length + ')'));
    if (!list.length) {
      b.appendChild(el('p', 'sc-desc', 'Nessun comando in attesa di approvazione.'));
      card.appendChild(b);
      host.appendChild(card);
      return;
    }
    list.forEach(function (p) {
      var row = el('div');
      row.style.cssText = 'display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border,#2a2a2a)';
      var dot = el('span', null, p.tier === 'red' ? '🔴 ' : '🟡 ');
      row.appendChild(dot);
      var lab = el('span', null, p.label || p.tool);
      lab.style.cssText = 'flex:1';
      row.appendChild(lab);
      var originText = p.origin === 'chat'
        ? ('chat' + (p.user ? ' · ' + p.user : ''))
        : (p.origin || 'gateway');
      var badge = el('span', null, '[' + originText + ']');
      badge.style.cssText = 'font-size:11px;color:var(--text-4,#888);padding:2px 6px;border:1px solid var(--border,#2a2a2a);border-radius:10px;white-space:nowrap';
      row.appendChild(badge);
      var ok = el('button', 'btn btn-primary', 'Approva');
      var no = el('button', 'btn btn-ghost', 'Rifiuta');
      ok.addEventListener('click', function () { resolve(p.id, 'approve'); });
      no.addEventListener('click', function () { resolve(p.id, 'reject'); });
      row.appendChild(ok); row.appendChild(no);
      b.appendChild(row);
    });
    card.appendChild(b);
    host.appendChild(card);
  }

  /* I-4 (review indipendente): un solo messaggio ("potrebbe essere scaduto o
     gia' gestito") copriva TRE esiti diversi, e uno era descritto male --
     l'endpoint di approvazione/rifiuto NON ritorna sempre 200: un 403 arriva
     da _require_human_auth (handlers_gateway_pending.py:292-311) quando la
     richiesta non viene dall'ingress HIRIS, e ripetere il tentativo su un
     problema di permessi non risolve nulla. Il terzo esito e' ok:true con
     result.error: il nonce E' stato consumato e l'entry marcata "approved"
     (handlers_gateway_pending.py:257-266), ma il comando non e' arrivato a
     Home Assistant -- quella approvazione non e' piu' riprovabile, e il
     vecchio messaggio lo lasciava intendere. Il messaggio e' derivato dallo
     stato della risposta, stesso principio di chat/knowledge.js
     ::messaggioErrore -- mai la stringa tecnica del backend verso l'utente. */
  function messaggioErrore(res, isReject) {
    if (res.status === 403) {
      return 'Non hai i permessi per farlo da qui: apri questa pagina dentro HIRIS ' +
        '(il solo token del gateway non basta ad approvare o rifiutare).';
    }
    if (!res.httpOk) {
      return 'Il server ha risposto con un errore (' + res.status + '). Riprova più tardi.';
    }
    if (res.data.ok === false) {
      return isReject
        ? 'Non è stato possibile rifiutare questo comando: potrebbe essere scaduto o già gestito.'
        : 'Non è stato possibile approvare questo comando: potrebbe essere scaduto o già gestito.';
    }
    if (res.data.result && res.data.result.error) {
      return 'Comando approvato ma NON eseguito su Home Assistant: questa approvazione è già ' +
        'stata usata e non è più riprovabile. Verifica su Home Assistant e, se serve, ripeti ' +
        'l’azione dall’inizio.';
    }
    return isReject
      ? 'Non è stato possibile rifiutare questo comando.'
      : 'Non è stato possibile approvare questo comando.';
  }

  /* Approvare o rifiutare e' un comando su casa propria arrivato in coda
     perche' il semaforo l'ha giudicato giallo o rosso: chiede conferma come
     ogni altra azione irreversibile del progetto (window.confirm, gia'
     usato ovunque). Sull'esito segue la stessa regola di chat/knowledge.js
     ::act(): un fallimento va detto (mai in silenzio, mai con la stringa
     tecnica del backend), e la coda si ricarica comunque per riflettere lo
     stato vero. */
  function resolve(id, verb) {
    var isReject = (verb === 'reject');
    var confirmMsg = isReject
      ? 'Rifiutare questo comando? Non verrà eseguito.'
      : 'Approvare questo comando? Verrà eseguito su Home Assistant.';
    if (!window.confirm(confirmMsg)) return;
    api('/pending/' + encodeURIComponent(id) + '/' + verb, { method: 'POST' })
      .then(function (r) {
        return r.json().then(function (d) { return { httpOk: r.ok, status: r.status, data: d || {} }; },
          function () { return { httpOk: r.ok, status: r.status, data: {} }; });
      })
      .then(function (res) {
        var fallito = !res.httpOk || res.data.ok === false
          || (res.data.result && res.data.result.error);
        if (fallito) {
          console.error('gateway pending ' + verb + ' failed', res.status, res.data);
          window.alert(messaggioErrore(res, isReject));
        }
      }, function (e) {
        console.error('gateway pending ' + verb + ' failed', e);
        window.alert('Errore di rete: riprova.');
      })
      .then(loadPending);
  }

  var _pendingHost = null;
  function loadPending() {
    if (!_pendingHost) return;
    api('/pending', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (d) {
        // M-8: un'eccezione DENTRO renderPending e' un bug di rendering (i
        // dati sono stati letti correttamente), non un guasto di lettura
        // della coda -- va isolata qui, altrimenti il .catch() sotto la
        // confonderebbe con un fallimento di rete/HTTP e direbbe "non e'
        // stato possibile leggere la coda" su un problema che non e' quello.
        try {
          renderPending(_pendingHost, d.pending || []);
        } catch (e) {
          console.error('renderPending failed (dati della coda letti correttamente)', e);
        }
      })
      .catch(function () { renderPendingError(_pendingHost); });
  }

  function render(outlet, data) {
    outlet.innerHTML = '';
    var levels = data.levels || {};
    var settings = data.settings || {};

    outlet.appendChild(el('div', 'page-title', 'Accessi Gateway'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Cosa Claude (via il gateway MCP) puo’ comandare in casa. Scegli per categoria.'));

    _pendingHost = el('div');
    outlet.appendChild(_pendingHost);

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');

    // notify service
    var srow = el('div');
    srow.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:6px 0 14px';
    srow.appendChild(el('span', null, '🔔 Servizio notifica (Giallo):'));
    var svc = el('input');
    svc.type = 'text';
    svc.value = settings.notify_service || '';
    svc.placeholder = 'es. notify.mobile_app_<device>';
    svc.style.cssText = 'padding:8px 10px;border-radius:8px;min-width:160px;flex:1 1 200px;min-height:44px;box-sizing:border-box';
    srow.appendChild(svc);
    body.appendChild(srow);

    var selects = {};
    (data.categories || []).forEach(function (cat) {
      var count = cat.count || 0;
      var row = el('div', 'gw-row');
      row.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;padding:10px 0;border-bottom:1px solid var(--border,#2a2a2a)';
      if (count === 0) row.style.opacity = '0.45';
      var ic = el('span', null, (EMOJI[cat.id] || '') + ' ');
      ic.style.fontSize = '18px';
      row.appendChild(ic);
      var lbl = el('span', null, cat.label);
      lbl.style.cssText = 'flex:1 1 120px;font-weight:500;font-size:15px';
      row.appendChild(lbl);
      var cnt = el('span', null, count + (count === 1 ? ' disp.' : ' disp.'));
      cnt.style.cssText = 'color:var(--text-4,#888);font-size:13px;min-width:64px;text-align:right';
      row.appendChild(cnt);
      var sel = el('select');
      sel.style.cssText = 'padding:8px 10px;border-radius:8px;min-width:150px;flex:1 1 170px;min-height:44px;box-sizing:border-box';
      LEVELS.forEach(function (o) {
        var opt = el('option', null, o[1]); opt.value = o[0]; sel.appendChild(opt);
      });
      var cur = levels[cat.id];
      sel.value = VALID[cur] ? cur : 'off';
      selects[cat.id] = sel;
      row.appendChild(sel);
      if (cat.dangerous) {
        // I-2: il testo e' legato al livello selezionato (dangerHintText),
        // non piu' fisso -- "sempre bloccato" e' vero solo per Off/Verde,
        // Giallo/Rosso finiscono comunque in coda (vedi commento sopra
        // dangerHintText). Si aggiorna al `change` della select.
        var warn = el('span', 'gw-danger-hint', dangerHintText(sel.value));
        row.appendChild(warn);
        sel.addEventListener('change', function () {
          warn.textContent = dangerHintText(sel.value);
        });
      }
      body.appendChild(row);
    });

    var entWrap = el('div');
    entWrap.style.cssText = 'padding:14px 0 4px;border-top:1px solid var(--border,#2a2a2a);margin-top:8px';
    var entTitle = el('div', null, 'Override per entità (avanzato)');
    entTitle.style.cssText = 'font-weight:600;margin-bottom:4px';
    entWrap.appendChild(entTitle);
    var entHint = el('p', 'sc-desc',
      'Una per riga: "entity_id livello" (off/green/yellow/red). ' +
      'L\'entità batte il livello del dominio — es. dominio Interruttori verde ma ' +
      '"switch.cancello off" per bloccarlo, o dominio off con "switch.lampada green".');
    entWrap.appendChild(entHint);
    var entTa = el('textarea');
    entTa.value = entitiesToText(data.entities || {});
    entTa.rows = 4;
    entTa.placeholder = 'switch.cancello off\nlock.ingresso red';
    entTa.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:8px;font-family:var(--font-mono,monospace);font-size:13px';
    entWrap.appendChild(entTa);
    body.appendChild(entWrap);

    body.appendChild(el('p', 'sc-desc',
      'Verde = esegui subito · Giallo = notifica sul telefono e approvi (anche qui sopra) · ' +
      'Rosso = conferma solo qui in HIRIS. Le categorie senza dispositivi sono attenuate.'));

    // I-1/M-7: prima diceva "un'approvazione esplicita in HIRIS (giallo o
    // rosso) puo' scavalcare il blocco" -- falso per il Giallo, che si
    // approvava con un tocco sulla notifica, MAI passando da HIRIS. Dopo
    // S-1 (handlers_execute.py forza sempre rosso un dominio pericoloso
    // prima di creare il pending) il giallo su questi domini non produce
    // piu' una notifica azionabile: l'unica approvazione possibile, a
    // qualunque livello sia impostata la categoria, e' manuale qui in
    // HIRIS. L'elenco delle categorie e' quello che il backend marca
    // `dangerous` (stessa fonte del warn per riga sopra), non piu' una
    // lista scritta a mano nel frontend.
    var dangerousLabels = (data.categories || [])
      .filter(function (c) { return c.dangerous; })
      .map(function (c) { return c.label; });
    if (dangerousLabels.length) {
      body.appendChild(el('p', 'sc-desc',
        '🔒 ' + dangerousLabels.join(', ') + ': dominio pericoloso, verde e giallo qui non hanno mai ' +
        'effetto diretto (il verde resta sempre negato, il giallo finisce comunque in coda ma senza ' +
        'notifica azionabile). Solo un’approvazione manuale qui in HIRIS può scavalcare il blocco — ' +
        'mai un tocco sulla notifica, qualunque sia il livello scelto.'));
    }

    var bar = el('div');
    bar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var save = el('button', 'btn btn-primary', 'Salva');
    var status = el('span', 'sc-desc', '');
    bar.appendChild(save); bar.appendChild(status);
    body.appendChild(bar);

    save.addEventListener('click', function () {
      var out = {};
      Object.keys(selects).forEach(function (id) { out[id] = selects[id].value; });
      save.disabled = true; status.textContent = 'Salvataggio…';
      api('/policy', { method: 'POST', body: JSON.stringify({
        levels: out,
        entities: parseEntityOverrides(entTa.value),
        settings: { notify_service: svc.value.trim() }
      }) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function () { status.textContent = 'Salvato ✓'; save.disabled = false; })
        .catch(function () { status.textContent = 'Errore nel salvataggio'; save.disabled = false; });
    });

    card.appendChild(body);
    outlet.appendChild(card);
    loadPending();
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Accessi Gateway'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));
    api('/policy', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) { render(outlet, data); })
      .catch(function () {
        outlet.innerHTML = '';
        outlet.appendChild(el('div', 'page-title', 'Accessi Gateway'));
        outlet.appendChild(el('p', 'page-subtitle', 'Errore nel caricamento della policy.'));
      });
  }

  return { mount: mount };
})();
