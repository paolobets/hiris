/* HIRIS · Config · Storicizzazione (route #/history)
   Sceglie quali entità lo storico HIRIS registra (per dominio + allowlist/exclude)
   e la retention dei dati grezzi. Opt-in: di default nulla viene storicizzato.
   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati server. */
window.HirisHistoryRoute = (function () {
  'use strict';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function api(opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch('api/history/policy', opts);
  }
  function toList(v) {
    return (v || '').split(/[\n,]+/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length; });
  }
  function textareaField(body, title, desc, value) {
    var wrap = el('div');
    wrap.style.cssText = 'padding:12px 0 4px';
    var t = el('div', null, title);
    t.style.cssText = 'font-weight:500;margin-bottom:4px';
    wrap.appendChild(t);
    var ta = el('textarea');
    ta.value = value || ''; ta.rows = 3;
    ta.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:8px;font-family:var(--font-mono,monospace);font-size:13px';
    wrap.appendChild(ta);
    wrap.appendChild(el('p', 'sc-desc', desc));
    body.appendChild(wrap);
    return ta;
  }

  function render(outlet, data) {
    outlet.innerHTML = '';
    var domains = data.domains || {};
    outlet.appendChild(el('div', 'page-title', 'Storicizzazione'));
    outlet.appendChild(el('p', 'page-subtitle',
      'Quali entità HIRIS registra nello storico per analisi (trend, durate). ' +
      'Di default nulla è storicizzato: scegli tu le categorie.'));
    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');

    var checks = {};
    (data.categories || []).forEach(function (cat) {
      var row = el('label', 'gw-row');
      row.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;padding:10px 0;border-bottom:1px solid var(--border,#2a2a2a);cursor:pointer';
      var cb = el('input'); cb.type = 'checkbox'; cb.checked = !!domains[cat.id];
      cb.style.cssText = 'width:20px;height:20px;flex:0 0 auto';
      checks[cat.id] = cb;
      row.appendChild(cb);
      var lbl = el('span', null, cat.label);
      lbl.style.cssText = 'flex:1 1 120px;font-weight:500;font-size:15px';
      row.appendChild(lbl);
      body.appendChild(row);
    });

    var entTa = textareaField(body, 'Entità extra (una per riga)',
      'Aggiunge singole entità anche se il loro dominio è spento.',
      (data.entities || []).join('\n'));
    var excTa = textareaField(body, 'Escludi (una per riga)',
      'Entità rumorose da NON storicizzare (es. sensor.uptime).',
      (data.exclude || []).join('\n'));

    var rrow = el('div');
    rrow.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 0 4px';
    rrow.appendChild(el('span', null, 'Retention grezzi (giorni):'));
    var ret = el('input'); ret.type = 'number'; ret.min = '1'; ret.max = '365';
    ret.value = String(data.retention_days || 90);
    ret.style.cssText = 'padding:8px 10px;border-radius:8px;width:90px;min-height:44px;box-sizing:border-box';
    rrow.appendChild(ret);
    rrow.appendChild(el('p', 'sc-desc',
      'I riepiloghi giornalieri restano per sempre; i grezzi oltre questa soglia vengono potati.'));
    body.appendChild(rrow);

    var bar = el('div');
    bar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var save = el('button', 'btn btn-primary', 'Salva');
    var status = el('span', 'sc-desc', '');
    bar.appendChild(save); bar.appendChild(status);
    body.appendChild(bar);

    save.addEventListener('click', function () {
      var out = {};
      Object.keys(checks).forEach(function (id) { out[id] = checks[id].checked; });
      var r = parseInt(ret.value, 10); if (isNaN(r)) r = 90;
      save.disabled = true; status.textContent = 'Salvataggio…';
      api({ method: 'POST', body: JSON.stringify({
        domains: out, entities: toList(entTa.value),
        exclude: toList(excTa.value), retention_days: r
      }) })
        .then(function (rs) { return rs.ok ? rs.json() : Promise.reject(rs); })
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
    outlet.appendChild(el('div', 'page-title', 'Storicizzazione'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));
    api({ method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) { render(outlet, data); })
      .catch(function () {
        outlet.innerHTML = '';
        outlet.appendChild(el('div', 'page-title', 'Storicizzazione'));
        outlet.appendChild(el('p', 'page-subtitle', 'Errore nel caricamento.'));
      });
  }
  return { mount: mount };
})();
