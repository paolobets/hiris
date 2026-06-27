/* HIRIS · Config · Accessi Gateway (route #/gateway)
   v1: scegli a click quali CATEGORIE di dispositivi il gateway MCP (Claude)
   puo' comandare, al posto del CSV nelle opzioni dell'add-on.
   Livelli v1: Verde (consenti) / Off (blocca). Giallo/Rosso arrivano in v2.
   Sicurezza: i testi dinamici vanno inseriti con textContent / nodi DOM,
   mai via innerHTML. */
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
    return fetch('api/gateway/policy' + (path || ''), opts);
  }

  function render(outlet, data) {
    outlet.innerHTML = '';
    var levels = data.levels || {};

    outlet.appendChild(el('div', 'page-title', 'Accessi Gateway'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Cosa Claude (via il gateway MCP) puo’ comandare in casa. Scegli per categoria.'));

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');

    var selects = {};
    var VALID = { off: 1, green: 1, yellow: 1, red: 1 };
    (data.categories || []).forEach(function (cat) {
      var count = cat.count || 0;
      var row = el('div', 'gw-row');
      row.style.cssText = 'display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border,#2a2a2a)';
      if (count === 0) row.style.opacity = '0.45';

      var ic = el('span', null, (EMOJI[cat.id] || '') + ' ');
      ic.style.fontSize = '18px';
      row.appendChild(ic);

      var lbl = el('span', null, cat.label);
      lbl.style.cssText = 'flex:1;font-weight:500';
      row.appendChild(lbl);

      var cnt = el('span', null, count + (count === 1 ? ' dispositivo' : ' dispositivi'));
      cnt.style.cssText = 'color:var(--text-4,#888);font-size:13px;min-width:110px;text-align:right';
      row.appendChild(cnt);

      var sel = el('select');
      sel.style.cssText = 'padding:6px 10px;border-radius:8px;min-width:220px';
      LEVELS.forEach(function (o) {
        var opt = el('option', null, o[1]);
        opt.value = o[0];
        sel.appendChild(opt);
      });
      var cur = levels[cat.id];
      sel.value = VALID[cur] ? cur : 'off';
      selects[cat.id] = sel;
      row.appendChild(sel);

      body.appendChild(row);
    });

    var hint = el('p', 'sc-desc',
      'Verde = Claude esegue subito (attivo ora). Giallo (notifica + approva) e ' +
      'Rosso (conferma manuale) li imposti già qui: il loro flusso di notifica si ' +
      'attiva col prossimo aggiornamento — fino ad allora, per sicurezza, si ' +
      'comportano come Off. Le categorie senza dispositivi sono attenuate.');
    hint.style.marginTop = '14px';
    body.appendChild(hint);

    var bar = el('div');
    bar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var save = el('button', 'btn btn-primary', 'Salva');
    var status = el('span', 'sc-desc', '');
    bar.appendChild(save);
    bar.appendChild(status);
    body.appendChild(bar);

    save.addEventListener('click', function () {
      var out = {};
      Object.keys(selects).forEach(function (id) { out[id] = selects[id].value; });
      save.disabled = true;
      status.textContent = 'Salvataggio…';
      api('', { method: 'POST', body: JSON.stringify({ levels: out }) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function () { status.textContent = 'Salvato ✓'; save.disabled = false; })
        .catch(function () { status.textContent = 'Errore nel salvataggio'; save.disabled = false; });
    });

    card.appendChild(body);
    outlet.appendChild(card);
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Accessi Gateway'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));
    api('', { method: 'GET' })
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
