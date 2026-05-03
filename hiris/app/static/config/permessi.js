/* HIRIS · Designer · permessi (tools, actions, entity selector)
   - tool checkboxes (call_ha_service toggles the action checkboxes section)
   - action domain checkboxes (light.*, climate.*, etc.)
   - entity selector with domain pills + search + chips */

function buildToolChecks(selected) {
  var el = document.getElementById('tool-checks');
  el.innerHTML = '';
  TOOLS.forEach(function(t) {
    var item = document.createElement('div');
    item.className = 'tool-item';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.value = t.id;
    chk.checked = selected.indexOf(t.id) >= 0;
    chk.id = 'tool-' + t.id;
    if (t.id === 'call_ha_service') {
      chk.addEventListener('change', updateServicesVisibility);
    }
    var lbl = document.createElement('label');
    lbl.htmlFor = 'tool-' + t.id;
    lbl.appendChild(chk);
    lbl.appendChild(document.createTextNode(' ' + t.label));
    var desc = document.createElement('div');
    desc.className = 'tool-desc';
    desc.textContent = t.desc;
    item.appendChild(lbl);
    item.appendChild(desc);
    el.appendChild(item);
  });
  updateServicesVisibility();
}

function updateServicesVisibility() {
  var chk = document.querySelector('#tool-checks input[value="call_ha_service"]');
  document.getElementById('f-actions-section').style.display = (chk && chk.checked) ? '' : 'none';
}

function getSelectedTools() {
  return Array.from(document.querySelectorAll('#tool-checks input:checked')).map(function(i) { return i.value; });
}

function buildActionChecks(selected) {
  var el = document.getElementById('action-checks');
  el.innerHTML = '';
  ACTIONS.forEach(function(a) {
    var item = document.createElement('div');
    item.className = 'tool-item';
    var chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.value = a.id;
    chk.checked = selected.indexOf(a.id) >= 0;
    chk.id = 'action-' + a.id.replace('.*', '');
    var lbl = document.createElement('label');
    lbl.htmlFor = chk.id;
    lbl.appendChild(chk);
    lbl.appendChild(document.createTextNode(' ' + a.label));
    var desc = document.createElement('div');
    desc.className = 'tool-desc';
    desc.textContent = a.desc;
    item.appendChild(lbl);
    item.appendChild(desc);
    el.appendChild(item);
  });
}

function getSelectedActions() {
  return Array.from(document.querySelectorAll('#action-checks input:checked')).map(function(i) { return i.value; });
}

/* ── Entity Selector ───────────────────────────────────────── */
var _entitySelectionSet = new Set();

function _entitySelectorRender() {
  var chips = document.getElementById('entity-chips');
  chips.innerHTML = '';
  _entitySelectionSet.forEach(function(pattern) {
    var chip = document.createElement('span');
    chip.className = 'entity-chip';
    chip.innerHTML = '<span>' + esc(pattern) + '</span><span class="chip-remove" data-p="' + esc(pattern) + '">×</span>';
    chip.querySelector('.chip-remove').addEventListener('click', function() {
      _entitySelectionSet.delete(this.dataset.p);
      _entitySelectorRender();
    });
    chips.appendChild(chip);
  });
  document.getElementById('f-entities').value = JSON.stringify(Array.from(_entitySelectionSet));
}

function _entitySelectorAdd(pattern) {
  if (pattern && !_entitySelectionSet.has(pattern)) {
    _entitySelectionSet.add(pattern);
    _entitySelectorRender();
  }
}

function _entitySelectorLoad(patterns) {
  _entitySelectionSet = new Set(Array.isArray(patterns) ? patterns : []);
  _entitySelectorRender();
  var srch = document.getElementById('entity-search');
  var sugg = document.getElementById('entity-suggestions');
  if (srch) srch.value = '';
  if (sugg) sugg.style.display = 'none';
}

/* domain pills */
document.querySelectorAll('.domain-pill').forEach(function(pill) {
  pill.addEventListener('click', function() {
    _entitySelectorAdd(this.dataset.pattern);
    document.getElementById('entity-search').value = '';
  });
});

/* search with debounce */
var _entitySearchTimer = null;
var _entitySearchInput = document.getElementById('entity-search');
var _entitySuggestions = document.getElementById('entity-suggestions');

_entitySearchInput.addEventListener('input', function() {
  clearTimeout(_entitySearchTimer);
  var q = _entitySearchInput.value.trim();
  if (!q) { _entitySuggestions.style.display = 'none'; return; }
  _entitySearchTimer = setTimeout(async function() {
    try {
      var resp = await fetch('api/entities?q=' + encodeURIComponent(q));
      var items = await resp.json();
      _entitySuggestions.innerHTML = '';
      if (!items.length) { _entitySuggestions.style.display = 'none'; return; }
      items.slice(0, 20).forEach(function(e) {
        var div = document.createElement('div');
        div.className = 'suggestion-item';
        div.innerHTML = '<span>' + esc(e.id) + '</span><span class="s-name">' + esc(e.name || '') + '</span>';
        div.addEventListener('click', function() {
          _entitySelectorAdd(e.id);
          _entitySearchInput.value = '';
          _entitySuggestions.style.display = 'none';
        });
        _entitySuggestions.appendChild(div);
      });
      _entitySuggestions.style.display = 'block';
    } catch(err) { /* ignore network errors */ }
  }, 300);
});

_entitySearchInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    var q = _entitySearchInput.value.trim();
    if (q) {
      _entitySelectorAdd(q);
      _entitySearchInput.value = '';
      _entitySuggestions.style.display = 'none';
    }
  }
  if (e.key === 'Escape') { _entitySuggestions.style.display = 'none'; }
});

document.addEventListener('click', function(e) {
  if (_entitySearchInput && !_entitySearchInput.contains(e.target) && !_entitySuggestions.contains(e.target)) {
    _entitySuggestions.style.display = 'none';
  }
});
