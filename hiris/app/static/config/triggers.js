/* HIRIS · Designer · trigger builder
   Manages list of triggers per agent. Depends on cron.js for cron expressions. */

var _agentTriggers = [];

function _triggerLabel(t) {
  if (t.type === 'schedule')      return '⏱ ogni ' + (t.interval_minutes || 5) + ' min';
  if (t.type === 'state_changed') return '👁 ' + (t.entity_id || 'entity');
  if (t.type === 'cron')          return '📅 ' + _cronDesc(t.cron || '');
  if (t.type === 'manual')        return '▶ manuale';
  return t.type;
}

function _triggersRender() {
  var el = document.getElementById('triggers-list');
  el.innerHTML = '';
  _agentTriggers.forEach(function(t, i) {
    var chip = document.createElement('span');
    chip.className = 'entity-chip';
    chip.innerHTML = esc(_triggerLabel(t)) +
      ' <span class="chip-remove" data-idx="' + i + '">&times;</span>';
    el.appendChild(chip);
  });
}

function _triggersLoad(triggers) {
  _agentTriggers = Array.isArray(triggers) ? JSON.parse(JSON.stringify(triggers)) : [];
  _triggersRender();
}

function _triggersValue() {
  return JSON.parse(JSON.stringify(_agentTriggers));
}

document.getElementById('triggers-list').addEventListener('click', function(e) {
  var btn = e.target.closest('.chip-remove');
  if (!btn) return;
  var idx = parseInt(btn.dataset.idx);
  _agentTriggers.splice(idx, 1);
  _triggersRender();
});

document.getElementById('new-trigger-type').addEventListener('change', function() {
  var v = this.value;
  document.getElementById('nt-schedule-fields').style.display = v === 'schedule' ? 'flex' : 'none';
  document.getElementById('nt-state-fields').style.display    = v === 'state_changed' ? '' : 'none';
  if (v === 'cron') {
    document.getElementById('nt-cron-fields').style.display = 'flex';
    _cronInitUI();
  } else {
    document.getElementById('nt-cron-fields').style.display = 'none';
  }
});

document.getElementById('btn-add-trigger').addEventListener('click', function() {
  var ttype = document.getElementById('new-trigger-type').value;
  var trigger = {type: ttype};
  if (ttype === 'schedule')           trigger.interval_minutes = parseInt(document.getElementById('nt-interval').value) || 5;
  else if (ttype === 'state_changed') trigger.entity_id = document.getElementById('nt-entity').value.trim();
  else if (ttype === 'cron')          trigger.cron = document.getElementById('nt-cron').value.trim();
  _agentTriggers.push(trigger);
  _triggersRender();
  document.getElementById('nt-entity').value = '';
  if (ttype === 'cron') _cronApply('0 6 * * *');
  else document.getElementById('nt-cron').value = '';
});
