/* HIRIS · Designer · permessi (tools, actions)
   - tool checkboxes (call_ha_service toggles the action checkboxes section)
   - action domain checkboxes (light.*, climate.*, etc.)
   Il selettore entità è stato estratto in config/entity-picker.js
   (istanziabile — HirisEntityPicker.create()), vedi chatbot-editor.js
   populatePermessi() per l'istanza usata dall'editor Persona. */

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
