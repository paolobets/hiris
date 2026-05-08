/* HIRIS · Designer · script action helper + drawer-based action editor (Phase 6)
   Esposes window.HirisScriptAction (loadScripts, populateScriptPicker,
   isScriptAction, asScriptAction) and window.HirisActionDrawer (open). */
(function() {
  /* ---------- script registry --------------------------------------- */
  var scripts = null;
  var scriptsPromise = null;

  function loadScripts() {
    if (scripts !== null) return Promise.resolve(scripts);
    if (scriptsPromise) return scriptsPromise;
    scriptsPromise = fetch('api/scripts')
      .then(function(r) { return r.ok ? r.json() : { scripts: [] }; })
      .then(function(d) {
        var raw = (d && d.scripts) || [];
        scripts = raw.map(function(s) {
          if (typeof s === 'string') return { id: s, name: s };
          return {
            id: s.entity_id || s.id || '',
            name: (s.attributes && s.attributes.friendly_name) || s.name || s.entity_id || s.id || '',
          };
        }).filter(function(s) { return !!s.id; });
        return scripts;
      })
      .catch(function() {
        scripts = [];
        return scripts;
      });
    return scriptsPromise;
  }

  function populateScriptPicker(selectEl) {
    if (!selectEl) return;
    selectEl.innerHTML = '<option>Caricamento…</option>';
    loadScripts().then(function(list) {
      if (!list.length) {
        var parent = selectEl.parentElement;
        if (parent) {
          var input = document.createElement('input');
          input.type = 'text';
          input.className = 'input';
          input.id = selectEl.id;
          input.placeholder = 'script.bedtime_routine';
          parent.replaceChild(input, selectEl);
        }
        return;
      }
      selectEl.innerHTML = '<option value="">— seleziona script —</option>' +
        list.map(function(s) {
          return '<option value="' + escAttr(s.id) + '">' +
            escHtml(s.id) + ' — "' + escHtml(s.name) + '"</option>';
        }).join('');
    });
  }

  function isScriptAction(action) {
    return !!(action && action.type === 'call_service' && action.domain === 'script');
  }

  function asScriptAction(label, scriptId, variables) {
    var sid = String(scriptId || '').replace(/^script\./, '');
    var data = null;
    if (variables !== null && variables !== undefined && variables !== '') {
      var parsed;
      if (typeof variables === 'string') {
        try { parsed = JSON.parse(variables); }
        catch (e) { parsed = variables; /* leave raw string for backend to reject */ }
      } else {
        parsed = variables;
      }
      data = { variables: parsed };
    }
    return {
      type: 'call_service',
      label: label || ('Esegui ' + sid),
      domain: 'script',
      service: sid,
      entity_pattern: 'script.' + sid,
      service_data: data,
    };
  }

  /* ---------- escape helpers ---------------------------------------- */
  function escHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function escAttr(s) { return escHtml(s); }

  /* ---------- drawer-based action editor ---------------------------- */
  function buildFormBody(action) {
    var isScript = isScriptAction(action);
    var t = (action && action.type) || 'notify';
    var displayType = isScript ? 'script' : t;

    var html =
      '<div class="field">' +
        '<label>Tipo azione</label>' +
        '<select class="select" id="ae6-type">' +
          '<option value="notify"' + (displayType === 'notify' ? ' selected' : '') + '>📢 Notifica</option>' +
          '<option value="script"' + (displayType === 'script' ? ' selected' : '') + '>▶ Esegui script HA</option>' +
          '<option value="call_service"' + (displayType === 'call_service' && !isScript ? ' selected' : '') + '>⚙ Chiama servizio HA (avanzato)</option>' +
          '<option value="wait"' + (displayType === 'wait' ? ' selected' : '') + '>⏳ Attendi (delay)</option>' +
          '<option value="verify"' + (displayType === 'verify' ? ' selected' : '') + '>🔍 Verifica condizione</option>' +
        '</select>' +
      '</div>' +
      '<div class="field">' +
        '<label>Etichetta</label>' +
        '<input class="input" type="text" id="ae6-label" value="' + escAttr((action && action.label) || '') + '" placeholder="Es. Avvisa Telegram famiglia">' +
      '</div>' +
      /* notify */
      '<div data-form-type="notify" style="display:none">' +
        '<div class="field"><label>Canale</label><select class="select" id="ae6-channel">' +
          '<option value="ha_push"' + (action && action.channel === 'ha_push' ? ' selected' : '') + '>Home Assistant push</option>' +
          '<option value="apprise"' + (action && action.channel === 'apprise' ? ' selected' : '') + '>Apprise (Telegram, WhatsApp, ntfy…)</option>' +
        '</select></div>' +
        '<div class="field"><label>Destinatario</label>' +
          '<input class="input" type="text" id="ae6-target" value="' + escAttr((action && action.target) || '') + '" placeholder="es. notify.mobile_app_paolo o config Apprise">' +
          '<p class="field-hint">HA push: nome notify.* del dispositivo. Apprise: lascia vuoto per usare gli URL globali da configurazione.</p>' +
        '</div>' +
      '</div>' +
      /* script */
      '<div data-form-type="script" style="display:none">' +
        '<div class="field"><label>Script Home Assistant</label>' +
          '<select class="select" id="ae6-script"></select>' +
          '<p class="field-hint">Lista popolata da HA (entità di dominio script.*).</p></div>' +
        '<div class="field"><label>Variabili (opzionale, JSON)</label>' +
          '<textarea class="textarea" id="ae6-script-vars" rows="3" style="font-size:12px">' +
            escHtml(action && action.service_data && action.service_data.variables ? JSON.stringify(action.service_data.variables, null, 2) : '') +
          '</textarea>' +
          '<p class="field-hint">JSON passato come <code>variables</code> allo script.</p></div>' +
      '</div>' +
      /* call_service avanzato */
      '<div data-form-type="call_service" style="display:none">' +
        '<div class="field-row">' +
          '<div class="field"><label>Dominio</label><input class="input" type="text" id="ae6-domain" value="' + escAttr((action && !isScript && action.domain) || '') + '" placeholder="light"></div>' +
          '<div class="field"><label>Servizio</label><input class="input" type="text" id="ae6-service" value="' + escAttr((action && !isScript && action.service) || '') + '" placeholder="turn_off"></div>' +
        '</div>' +
        '<div class="field"><label>Pattern entità</label><input class="input" type="text" id="ae6-entity-pattern" value="' + escAttr((action && !isScript && action.entity_pattern) || '') + '" placeholder="light.* (opzionale)"></div>' +
        '<div class="field"><label>Dati servizio (opzionale, JSON)</label>' +
          '<textarea class="textarea" id="ae6-cs-data" rows="3" style="font-size:12px">' +
            escHtml(action && !isScript && action.service_data ? JSON.stringify(action.service_data, null, 2) : '') +
          '</textarea></div>' +
      '</div>' +
      /* wait */
      '<div data-form-type="wait" style="display:none">' +
        '<div class="field"><label>Attendi (min)</label><input class="input" type="number" id="ae6-wait-minutes" value="' + ((action && (action.wait_minutes || action.minutes)) || 5) + '" min="1"></div>' +
      '</div>' +
      /* verify */
      '<div data-form-type="verify" style="display:none">' +
        '<div class="field"><label>Entity ID</label><input class="input" type="text" id="ae6-verify-entity" value="' + escAttr((action && (action.verify_entity || action.entity_id)) || '') + '" placeholder="sensor.temperature"></div>' +
        '<div class="field-row">' +
          '<div class="field"><label>Operatore</label><select class="select" id="ae6-verify-op">' +
            ['<','<=','>','>=','==','!='].map(function(op) {
              var sel = (action && (action.verify_operator || action.operator) === op) ? ' selected' : '';
              return '<option value="' + op + '"' + sel + '>' + op + '</option>';
            }).join('') +
          '</select></div>' +
          '<div class="field"><label>Valore</label><input class="input" type="text" id="ae6-verify-value" value="' + escAttr((action && (action.verify_value || action.value)) || '') + '" placeholder="20"></div>' +
        '</div>' +
        '<div class="field"><label>Finestra (min)</label><input class="input" type="number" id="ae6-verify-window" value="' + ((action && (action.verify_window || action.window_minutes)) || 30) + '" min="1"></div>' +
      '</div>' +
      /* on_fail comune */
      '<div class="field">' +
        '<label>Se fallisce</label>' +
        '<select class="select" id="ae6-on-fail">' +
          '<option value="continue"' + (!action || action.on_fail !== 'stop' ? ' selected' : '') + '>Continua sequenza</option>' +
          '<option value="stop"' + (action && action.on_fail === 'stop' ? ' selected' : '') + '>Ferma esecuzione</option>' +
        '</select>' +
      '</div>';

    return html;
  }

  function showFormFor(type, container) {
    var blocks = container.querySelectorAll('[data-form-type]');
    for (var i = 0; i < blocks.length; i++) {
      blocks[i].style.display = blocks[i].getAttribute('data-form-type') === type ? '' : 'none';
    }
  }

  function collectAction(container, originalAction) {
    var t = container.querySelector('#ae6-type').value;
    var label = container.querySelector('#ae6-label').value.trim();
    var onFail = container.querySelector('#ae6-on-fail').value;
    var a;

    if (t === 'notify') {
      a = { type: 'notify', label: label, channel: container.querySelector('#ae6-channel').value };
      var tgt = container.querySelector('#ae6-target');
      if (tgt && tgt.value.trim()) a.target = tgt.value.trim();
    } else if (t === 'script') {
      var scriptId = container.querySelector('#ae6-script').value;
      var varsRaw = container.querySelector('#ae6-script-vars').value.trim();
      var vars = null;
      if (varsRaw) {
        try { vars = JSON.parse(varsRaw); } catch (e) { vars = varsRaw; }
      }
      a = asScriptAction(label, scriptId, vars);
    } else if (t === 'call_service') {
      var dataRaw = container.querySelector('#ae6-cs-data').value.trim();
      var data = null;
      if (dataRaw) { try { data = JSON.parse(dataRaw); } catch (e) {} }
      a = {
        type: 'call_service',
        label: label,
        domain: container.querySelector('#ae6-domain').value.trim(),
        service: container.querySelector('#ae6-service').value.trim(),
        entity_pattern: container.querySelector('#ae6-entity-pattern').value.trim(),
        service_data: data,
      };
    } else if (t === 'wait') {
      a = {
        type: 'wait',
        label: label,
        minutes: parseInt(container.querySelector('#ae6-wait-minutes').value, 10) || 5,
      };
    } else if (t === 'verify') {
      var eid = container.querySelector('#ae6-verify-entity').value.trim();
      var op = container.querySelector('#ae6-verify-op').value;
      var val = container.querySelector('#ae6-verify-value').value.trim();
      a = {
        type: 'verify',
        label: label,
        entity_id: eid,
        operator: op,
        value: val,
        window_minutes: parseInt(container.querySelector('#ae6-verify-window').value, 10) || 30,
        condition: { entity_id: eid, operator: op, value: val },
      };
    }
    a.on_fail = onFail;
    if (originalAction && originalAction.id) a.id = originalAction.id;
    return a;
  }

  function openActionDrawer(existingAction, onSave) {
    if (!window.HirisDrawer) {
      console.error('HirisDrawer not available');
      return;
    }
    HirisDrawer.open({
      title: existingAction ? 'Modifica azione' : 'Aggiungi azione',
      confirmLabel: existingAction ? '✓ Salva' : '✓ Aggiungi',
      body: buildFormBody(existingAction),
      onConfirm: function() {
        var container = document.querySelector('.drawer-body');
        if (!container) return false;
        var label = container.querySelector('#ae6-label').value.trim();
        if (!label) {
          alert('Inserisci un\'etichetta per l\'azione.');
          return false;
        }
        var t = container.querySelector('#ae6-type').value;
        if (t === 'script') {
          var sid = container.querySelector('#ae6-script').value.trim();
          if (!sid) { alert('Seleziona uno script.'); return false; }
        } else if (t === 'verify') {
          var eid = container.querySelector('#ae6-verify-entity').value.trim();
          var val = container.querySelector('#ae6-verify-value').value.trim();
          if (!eid || !val) { alert('Inserisci Entity ID e Valore.'); return false; }
        } else if (t === 'call_service') {
          var dom = container.querySelector('#ae6-domain').value.trim();
          var svc = container.querySelector('#ae6-service').value.trim();
          if (!dom || !svc) { alert('Inserisci dominio e servizio.'); return false; }
        }
        var action = collectAction(container, existingAction);
        if (onSave) onSave(action);
        return true;
      },
    });
    var container = document.querySelector('.drawer-body');
    if (!container) return;
    var typeSelect = container.querySelector('#ae6-type');
    showFormFor(typeSelect.value, container);
    typeSelect.addEventListener('change', function() {
      showFormFor(typeSelect.value, container);
      if (typeSelect.value === 'script') {
        var picker = container.querySelector('#ae6-script');
        if (picker && picker.tagName === 'SELECT') populateScriptPicker(picker);
      }
    });
    if (typeSelect.value === 'script') {
      var picker = container.querySelector('#ae6-script');
      if (picker) populateScriptPicker(picker);
      if (existingAction && existingAction.service) {
        setTimeout(function() {
          var p = container.querySelector('#ae6-script');
          if (p && p.tagName === 'SELECT') p.value = 'script.' + existingAction.service;
        }, 250);
      }
    }
  }

  /* ---------- delegated hook on #btn-add-action --------------------- */
  /* Capture-phase listener so we run BEFORE the legacy bubble-phase
     listener attached in action-editor.js, and stop it. */
  document.addEventListener('click', function(e) {
    var btn = e.target && e.target.closest && e.target.closest('#btn-add-action');
    if (!btn) return;
    /* Only intercept when v6 outlet is mounted (drawer atom present) */
    if (!window.HirisDrawer) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    openActionDrawer(null, function(action) {
      if (window._agentActions && Array.isArray(window._agentActions)) {
        window._agentActions.push(action);
        if (typeof window._actionsRender === 'function') window._actionsRender();
      } else if (typeof window.pushAction === 'function') {
        window.pushAction(action);
      }
    });
  }, true);

  /* ---------- exports ----------------------------------------------- */
  window.HirisScriptAction = {
    loadScripts: loadScripts,
    populateScriptPicker: populateScriptPicker,
    isScriptAction: isScriptAction,
    asScriptAction: asScriptAction,
  };
  window.HirisActionDrawer = { open: openActionDrawer };
})();
