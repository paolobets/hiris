/* HIRIS · Config · Accessi Gateway (route #/gateway)
   v1: scegli a click quali CATEGORIE di dispositivi il gateway MCP (Claude)
   puo' comandare, al posto del CSV nelle opzioni dell'add-on.
   Livelli v1: Verde (consenti) / Off (blocca). Giallo/Rosso arrivano in v2.
   Sicurezza: i testi dinamici vanno inseriti con textContent / nodi DOM,
   mai via innerHTML. */
window.HirisGatewayRoute = (function () {
  'use strict';

  var EMOJI = {
    light: '💡', scene: '🎬', climate: '🌡️',
    cover: '🪟', media_player: '📺', switch: '🔌',
    fan: '🌀', vacuum: '🧹', lock: '🔒',
    alarm_control_panel: '🚨', script: '📝'
  };

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
    (data.categories || []).forEach(function (cat) {
      var row = el('div', 'gw-row');
      row.style.cssText = 'display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border,#2a2a2a)';

      var ic = el('span', null, (EMOJI[cat.id] || '') + ' ');
      ic.style.fontSize = '18px';
      row.appendChild(ic);

      var lbl = el('span', null, cat.label);
      lbl.style.cssText = 'flex:1;font-weight:500';
      row.appendChild(lbl);

      var sel = el('select');
      sel.style.cssText = 'padding:6px 10px;border-radius:8px';
      [['off', 'Off (blocca)'], ['green', '🟢 Verde (consenti)']].forEach(function (o) {
        var opt = el('option', null, o[1]);
        opt.value = o[0];
        sel.appendChild(opt);
      });
      sel.value = (levels[cat.id] === 'green') ? 'green' : 'off';
      selects[cat.id] = sel;
      row.appendChild(sel);

      body.appendChild(row);
    });

    var hint = el('p', 'sc-desc',
      'v1: Verde = Claude esegue subito (entro la whitelist). I livelli ' +
      '🟡 Giallo (notifica) e 🔴 Rosso (conferma manuale) arrivano a breve.');
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
