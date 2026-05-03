/* HIRIS · Designer · action builder
   Build a list of actions (notify / call_service / wait / verify) for an agent.
   Inline editor opens via #btn-add-action and confirms via #ae-confirm. */

var _agentActions = [];

function _actionsRender() {
  var list = document.getElementById('actions-list');
  list.innerHTML = '';
  var TYPE_LABELS = { notify: 'Notifica', call_service: 'Servizio', wait: 'Attendi', verify: 'Verifica' };
  _agentActions.forEach(function(a, i) {
    var typeLabel = TYPE_LABELS[a.type] || a.type;
    var detail;
    if (a.type === 'notify') {
      detail = 'canale: ' + esc(a.channel || 'ha_push');
    } else if (a.type === 'call_service') {
      detail = esc(a.domain || '') + '.' + esc(a.service || '') + (a.entity_pattern ? ' su ' + esc(a.entity_pattern) : '');
    } else if (a.type === 'wait') {
      detail = esc(String(a.minutes || 5)) + ' min';
      if (a.actions && a.actions.length) {
        var ta = a.actions[0];
        detail += ta.type === 'send_notification'
          ? ' → notifica:' + esc(ta.channel || 'ha_push')
          : ' → ' + esc(ta.domain || '') + '.' + esc(ta.service || '');
      }
    } else if (a.type === 'verify') {
      detail = esc(a.entity_id || '?') + ' ' + esc(a.operator || '') + ' ' + esc(String(a.value || ''));
      if (a.actions && a.actions.length) {
        var ta = a.actions[0];
        detail += ta.type === 'send_notification'
          ? ' → notifica:' + esc(ta.channel || 'ha_push')
          : ' → ' + esc(ta.domain || '') + '.' + esc(ta.service || '');
      }
    } else {
      detail = '';
    }
    var onFailBadge = (a.on_fail === 'stop')
      ? ' <span style="font-size:10px;color:var(--danger);background:var(--danger-bg);padding:1px 5px;border-radius:8px">stop</span>'
      : '';
    var div = document.createElement('div');
    div.className = 'action-item';
    div.innerHTML =
      '<span class="ai-type">' + esc(typeLabel) + '</span>' +
      '<span class="ai-label">' + esc(a.label || '—') +
        ' <span style="color:var(--text-muted);font-size:11px">(' + detail + ')</span>' + onFailBadge + '</span>' +
      '<span class="ai-remove" data-i="' + i + '">×</span>';
    div.querySelector('.ai-remove').addEventListener('click', function() {
      _agentActions.splice(parseInt(this.dataset.i), 1);
      _actionsRender();
    });
    list.appendChild(div);
  });
}

function _actionsLoad(actions) {
  _agentActions = Array.isArray(actions) ? JSON.parse(JSON.stringify(actions)) : [];
  _actionsRender();
  document.getElementById('action-editor').style.display = 'none';
}

function _actionsValue() {
  return JSON.parse(JSON.stringify(_agentActions));
}

document.getElementById('btn-add-action').addEventListener('click', function() {
  document.getElementById('action-editor').style.display = 'block';
  document.getElementById('ae-type').value = 'notify';
  document.getElementById('ae-label').value = '';
  document.getElementById('ae-domain').value = '';
  document.getElementById('ae-service').value = '';
  document.getElementById('ae-entity-pattern').value = '';
  document.getElementById('ae-wait-minutes').value = '5';
  document.getElementById('ae-verify-entity').value = '';
  document.getElementById('ae-verify-value').value = '';
  document.getElementById('ae-verify-window').value = '30';
  document.getElementById('ae-on-fail').value = 'continue';
  document.getElementById('ae-then-type').value = '';
  document.getElementById('ae-then-message').value = '';
  document.getElementById('ae-then-channel').value = 'ha_push';
  document.getElementById('ae-then-svc-domain').value = '';
  document.getElementById('ae-then-svc-service').value = '';
  document.getElementById('ae-then-svc-entity').value = '';
  document.getElementById('ae-notify-fields').style.display  = '';
  document.getElementById('ae-service-fields').style.display = 'none';
  document.getElementById('ae-wait-fields').style.display    = 'none';
  document.getElementById('ae-verify-fields').style.display  = 'none';
  document.getElementById('ae-then-section').style.display   = 'none';
  document.getElementById('ae-then-notify-fields').style.display  = 'none';
  document.getElementById('ae-then-service-fields').style.display = 'none';
});

document.getElementById('ae-type').addEventListener('change', function() {
  var v = this.value;
  document.getElementById('ae-notify-fields').style.display  = v === 'notify'       ? '' : 'none';
  document.getElementById('ae-service-fields').style.display = v === 'call_service' ? '' : 'none';
  document.getElementById('ae-wait-fields').style.display    = v === 'wait'         ? '' : 'none';
  document.getElementById('ae-verify-fields').style.display  = v === 'verify'       ? '' : 'none';
  document.getElementById('ae-then-section').style.display   = (v === 'wait' || v === 'verify') ? '' : 'none';
});

document.getElementById('ae-then-type').addEventListener('change', function() {
  var v = this.value;
  document.getElementById('ae-then-notify-fields').style.display  = v === 'notify'       ? '' : 'none';
  document.getElementById('ae-then-service-fields').style.display = v === 'call_service' ? '' : 'none';
});

document.getElementById('ae-confirm').addEventListener('click', function() {
  var type = document.getElementById('ae-type').value;
  var label = document.getElementById('ae-label').value.trim();
  if (!label) { alert('Inserisci un\'etichetta per l\'azione.'); return; }
  var onFail = document.getElementById('ae-on-fail').value;
  var action = { type: type, label: label, on_fail: onFail };
  if (type === 'notify') {
    action.channel = document.getElementById('ae-channel').value;
  } else if (type === 'call_service') {
    action.domain = document.getElementById('ae-domain').value.trim();
    action.service = document.getElementById('ae-service').value.trim();
    var ep = document.getElementById('ae-entity-pattern').value.trim();
    if (ep) action.entity_pattern = ep;
  } else if (type === 'wait') {
    action.minutes = parseInt(document.getElementById('ae-wait-minutes').value) || 5;
  } else if (type === 'verify') {
    var eid = document.getElementById('ae-verify-entity').value.trim();
    var op  = document.getElementById('ae-verify-operator').value;
    var val = document.getElementById('ae-verify-value').value.trim();
    if (!eid || !val) { alert('Inserisci Entity ID e Valore per la verifica.'); return; }
    action.entity_id = eid;
    action.operator  = op;
    action.value     = val;
    action.window_minutes = parseInt(document.getElementById('ae-verify-window').value) || 30;
    action.condition = { entity_id: eid, operator: op, value: val };
  }
  /* Build child action for wait/verify */
  if (type === 'wait' || type === 'verify') {
    var thenType = document.getElementById('ae-then-type').value;
    if (thenType === 'notify') {
      var thenMsg = document.getElementById('ae-then-message').value.trim() || 'Azione completata.';
      action.actions = [{ type: 'send_notification', message: thenMsg,
        channel: document.getElementById('ae-then-channel').value }];
    } else if (thenType === 'call_service') {
      var thenDomain = document.getElementById('ae-then-svc-domain').value.trim();
      var thenSvc    = document.getElementById('ae-then-svc-service').value.trim();
      if (!thenDomain || !thenSvc) { alert('Inserisci dominio e servizio per l\'azione successiva.'); return; }
      var thenData = {};
      var thenEid  = document.getElementById('ae-then-svc-entity').value.trim();
      if (thenEid) thenData.entity_id = thenEid;
      action.actions = [{ type: 'call_ha_service', domain: thenDomain, service: thenSvc, data: thenData }];
    }
  }
  _agentActions.push(action);
  _actionsRender();
  document.getElementById('action-editor').style.display = 'none';
});

document.getElementById('ae-cancel').addEventListener('click', function() {
  document.getElementById('action-editor').style.display = 'none';
});
