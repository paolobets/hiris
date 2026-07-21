/* HIRIS · Config · Sentinella (route #/sentinel)
   Configura i detector di anomalia/sicurezza (soglie, entità monitorate) e
   mostra la timeline degli eventi rilevati di recente.
   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati server. */
window.HirisSentinelRoute = (function () {
  'use strict';

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
      opts.headers || {});
    return fetch(path, opts);
  }

  function render(outlet, data) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Sentinella'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Detector di anomalie: quali entità monitorare e con quali soglie.'));

    var meta = data.detectors_meta || [];
    var det = data.detectors || {};
    var inputs = {};

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');

    meta.forEach(function (m) {
      var cfg = det[m.id] || {};
      var row = el('div');
      row.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--border,#2a2a2a)';

      var head = el('label');
      head.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500;font-size:15px';
      var chk = el('input'); chk.type = 'checkbox'; chk.checked = !!cfg.enabled;
      chk.style.cssText = 'width:20px;height:20px;flex:0 0 auto';
      head.appendChild(chk);
      head.appendChild(el('span', null, m.label));
      row.appendChild(head);

      var entWrap = el('div');
      entWrap.style.cssText = 'margin-top:8px';
      entWrap.appendChild(el('span', 'sc-desc', 'Entità monitorate (separate da virgola)'));
      var entities = el('input');
      entities.type = 'text';
      entities.value = (cfg.entities || []).join(',');
      entities.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:8px;margin-top:4px';
      entWrap.appendChild(entities);
      row.appendChild(entWrap);

      var fields = {};
      (m.fields || []).forEach(function (f) {
        var frow = el('div');
        frow.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
        frow.appendChild(el('span', null, f.label));
        var inp = el('input'); inp.type = 'number';
        inp.value = cfg[f.key] != null ? cfg[f.key] : '';
        inp.style.cssText = 'width:100px;padding:6px 8px;border-radius:8px';
        frow.appendChild(inp);
        row.appendChild(frow);
        fields[f.key] = inp;
      });

      inputs[m.id] = { chk: chk, entities: entities, fields: fields };
      body.appendChild(row);
    });

    var bar = el('div');
    bar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var save = el('button', 'btn btn-primary', 'Salva');
    var status = el('span', 'sc-desc', '');
    bar.appendChild(save); bar.appendChild(status);
    body.appendChild(bar);

    save.addEventListener('click', function () {
      var payload = { detectors: {} };
      meta.forEach(function (m) {
        var i = inputs[m.id];
        var d = {
          enabled: i.chk.checked,
          entities: i.entities.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
        };
        Object.keys(i.fields).forEach(function (k) {
          var v = parseInt(i.fields[k].value, 10);
          if (!isNaN(v)) d[k] = v;
        });
        payload.detectors[m.id] = d;
      });
      save.disabled = true; status.textContent = 'Salvataggio…';
      api('api/sentinel/policy', { method: 'POST', body: JSON.stringify(payload) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function () { status.textContent = 'Salvato ✓'; save.disabled = false; })
        .catch(function () { status.textContent = 'Errore nel salvataggio'; save.disabled = false; });
    });

    card.appendChild(body);
    outlet.appendChild(card);

    outlet.appendChild(el('p', 'page-subtitle', 'Eventi recenti'));
    var list = el('div');
    outlet.appendChild(list);
    api('api/sentinel/timeline', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (t) {
        var events = t.events || [];
        if (!events.length) {
          list.appendChild(el('p', 'sc-desc', 'Nessun evento registrato.'));
          return;
        }
        events.forEach(function (ev) {
          list.appendChild(el('div', 'log-row',
            (ev.kind || '') + ' · ' + (ev.entity_id || '') + ' · ' + (ev.outcome || '') + ' · ' + (ev.message || '')));
        });
      })
      .catch(function () { list.appendChild(el('p', 'sc-desc', 'Errore nel caricamento della timeline.')); });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Sentinella'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));
    api('api/sentinel/policy', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) { render(outlet, data); })
      .catch(function () {
        outlet.innerHTML = '';
        outlet.appendChild(el('div', 'page-title', 'Sentinella'));
        outlet.appendChild(el('p', 'page-subtitle', 'Errore nel caricamento.'));
      });
  }

  return { mount: mount };
})();
