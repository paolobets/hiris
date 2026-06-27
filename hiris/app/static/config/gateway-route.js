/* HIRIS · Config · Accessi Gateway (route #/gateway)
   Semaforo per categoria (Off / 🟢 / 🟡 / 🔴), servizio notifica configurabile,
   e coda "Approvazioni in attesa" (Giallo/Rosso) con Approva/Rifiuta.
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

  function renderPending(host, list) {
    host.innerHTML = '';
    if (!list || !list.length) return;
    var card = el('section', 'section-card');
    var b = el('div', 'sc-body');
    b.appendChild(el('h2', 'sc-title', 'Approvazioni in attesa (' + list.length + ')'));
    list.forEach(function (p) {
      var row = el('div');
      row.style.cssText = 'display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border,#2a2a2a)';
      var dot = el('span', null, p.tier === 'red' ? '🔴 ' : '🟡 ');
      row.appendChild(dot);
      var lab = el('span', null, (p.label || p.tool) + '  ·  ' + (p.origin || ''));
      lab.style.cssText = 'flex:1';
      row.appendChild(lab);
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

  function resolve(id, verb) {
    api('/pending/' + encodeURIComponent(id) + '/' + verb, { method: 'POST' })
      .then(function () { loadPending(); });
  }

  var _pendingHost = null;
  function loadPending() {
    if (!_pendingHost) return;
    api('/pending', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : { pending: [] }; })
      .then(function (d) { renderPending(_pendingHost, d.pending || []); })
      .catch(function () {});
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
    svc.value = settings.notify_service || 'notify.iphone_bet';
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
      body.appendChild(row);
    });

    body.appendChild(el('p', 'sc-desc',
      'Verde = esegui subito · Giallo = notifica sul telefono e approvi (anche qui sopra) · ' +
      'Rosso = conferma solo qui in HIRIS. Le categorie senza dispositivi sono attenuate.'));

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
        levels: out, settings: { notify_service: svc.value.trim() }
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
