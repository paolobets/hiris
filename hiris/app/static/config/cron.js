/* HIRIS · Designer · cron builder
   Preset list + visual builder + live preview. Used by triggers.js. */

var _CRON_PRESETS = [
  ['0 6 * * *',    'Ogni giorno alle 06:00'],
  ['0 5 * * *',    'Ogni giorno alle 05:00'],
  ['0 7 * * *',    'Ogni giorno alle 07:00'],
  ['0 8 * * *',    'Ogni giorno alle 08:00'],
  ['0 12 * * *',   'Ogni giorno a mezzogiorno'],
  ['0 18 * * *',   'Ogni giorno alle 18:00'],
  ['0 22 * * *',   'Ogni giorno alle 22:00'],
  ['0 * * * *',    'Ogni ora (al minuto :00)'],
  ['*/15 * * * *', 'Ogni 15 minuti'],
  ['*/30 * * * *', 'Ogni 30 minuti'],
  ['0 6 * * 1-5',  'Giorni feriali alle 06:00'],
  ['0 6 * * 6,0',  'Weekend alle 06:00'],
  ['0 6 1 * *',    'Il 1° del mese alle 06:00'],
];
var _CRON_DOW   = [['*','ogni giorno'],['1','Lunedì'],['2','Martedì'],['3','Mercoledì'],['4','Giovedì'],['5','Venerdì'],['6','Sabato'],['0','Domenica'],['1-5','Lun–Ven (feriali)'],['6,0','Sab–Dom (weekend)']];
var _CRON_MONTH = [['*','ogni mese'],['1','Gennaio'],['2','Febbraio'],['3','Marzo'],['4','Aprile'],['5','Maggio'],['6','Giugno'],['7','Luglio'],['8','Agosto'],['9','Settembre'],['10','Ottobre'],['11','Novembre'],['12','Dicembre']];

function _cronDesc(cron) {
  var p = (cron || '').trim().split(/\s+/);
  if (p.length !== 5) return cron || '';
  var min = p[0], hour = p[1], dom = p[2], month = p[3], dow = p[4];
  var time = '';
  if (min === '*' && hour === '*') time = 'ogni minuto';
  else if (/^\*\/(\d+)$/.test(min) && hour === '*') time = 'ogni ' + min.slice(2) + ' min';
  else if (hour === '*') time = 'al minuto ' + min + ' di ogni ora';
  else time = 'alle ' + ('0'+hour).slice(-2) + ':' + ('0'+(min==='0'?'00':min)).slice(-2);
  var dowMap = {'*':'ogni giorno','1':'lun','2':'mar','3':'mer','4':'gio','5':'ven','6':'sab','0':'dom','1-5':'lun–ven','6,0':'sab–dom'};
  var when = dow !== '*' ? 'ogni ' + (dowMap[dow] || dow) : (dom !== '*' ? 'il giorno ' + dom : 'ogni giorno');
  var mnames = ['','gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic'];
  if (month !== '*') when += ' di ' + (mnames[+month] || 'mese '+month);
  if (time === 'ogni minuto') return 'ogni minuto';
  if (/^ogni \d+ min$/.test(time)) return time + (when === 'ogni giorno' ? '' : ', ' + when);
  if (time.startsWith('al minuto')) return time;
  return when + ' ' + time;
}

var _cronBuilt = false;
function _cronBuildSelects() {
  if (_cronBuilt) return;
  _cronBuilt = true;
  function _opts(selId, items) {
    var sel = document.getElementById(selId);
    sel.innerHTML = '';
    items.forEach(function(item) { var o = document.createElement('option'); o.value = item[0]; o.textContent = item[1]; sel.appendChild(o); });
  }
  var minItems = [['*','ogni minuto'],['*/5','ogni 5 min'],['*/10','ogni 10 min'],['*/15','ogni 15 min'],['*/30','ogni 30 min']];
  for (var m = 0; m <= 59; m++) minItems.push([String(m), ('0'+m).slice(-2)]);
  var hourItems = [['*','ogni ora']];
  for (var h = 0; h <= 23; h++) hourItems.push([String(h), ('0'+h).slice(-2)+':00']);
  var domItems = [['*','ogni giorno']];
  for (var d = 1; d <= 31; d++) domItems.push([String(d), String(d)]);
  _opts('nt-cron-min',   minItems);
  _opts('nt-cron-hour',  hourItems);
  _opts('nt-cron-dom',   domItems);
  _opts('nt-cron-month', _CRON_MONTH);
  _opts('nt-cron-dow',   _CRON_DOW);
  var presetSel = document.getElementById('nt-cron-preset');
  presetSel.innerHTML = '';
  _CRON_PRESETS.forEach(function(item) { var o = document.createElement('option'); o.value = item[0]; o.textContent = item[1]; presetSel.appendChild(o); });
  var adv = document.createElement('option'); adv.value = 'custom'; adv.textContent = 'Avanzato…'; presetSel.appendChild(adv);
  presetSel.addEventListener('change', function() {
    if (this.value === 'custom') {
      document.getElementById('nt-cron-builder').style.display = 'flex';
    } else {
      document.getElementById('nt-cron-builder').style.display = 'none';
      _cronApply(this.value);
    }
  });
  ['nt-cron-min','nt-cron-hour','nt-cron-dom','nt-cron-month','nt-cron-dow'].forEach(function(id) {
    document.getElementById(id).addEventListener('change', function() {
      var raw = ['nt-cron-min','nt-cron-hour','nt-cron-dom','nt-cron-month','nt-cron-dow'].map(function(i){ return document.getElementById(i).value; }).join(' ');
      _cronApply(raw, true);
    });
  });
}

function _cronApply(cron, fromBuilder) {
  var p = (cron || '0 6 * * *').trim().split(/\s+/);
  if (p.length !== 5) return;
  document.getElementById('nt-cron').value = cron;
  document.getElementById('nt-cron-raw').textContent = cron;
  document.getElementById('nt-cron-desc').textContent = _cronDesc(cron);
  if (!fromBuilder) {
    function _setOpt(id, val) { var s = document.getElementById(id); for (var i=0;i<s.options.length;i++) { if (s.options[i].value===val){s.value=val;return;} } }
    _setOpt('nt-cron-min',p[0]); _setOpt('nt-cron-hour',p[1]); _setOpt('nt-cron-dom',p[2]); _setOpt('nt-cron-month',p[3]); _setOpt('nt-cron-dow',p[4]);
  }
  var ps = document.getElementById('nt-cron-preset');
  var matched = false;
  for (var i=0; i<ps.options.length; i++) { if (ps.options[i].value === cron) { ps.value = cron; matched = true; break; } }
  if (!matched) { ps.value = 'custom'; if (!fromBuilder) document.getElementById('nt-cron-builder').style.display = 'flex'; }
}

function _cronInitUI(cron) {
  _cronBuildSelects();
  _cronApply(cron || '0 6 * * *');
  var ps = document.getElementById('nt-cron-preset');
  document.getElementById('nt-cron-builder').style.display = (ps.value === 'custom') ? 'flex' : 'none';
}
