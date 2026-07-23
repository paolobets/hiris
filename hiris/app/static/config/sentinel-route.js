/* HIRIS · Config · Sentinella (route #/sentinel)
   Configura i detector di anomalia/sicurezza (soglie, entità monitorate) e
   mostra la timeline degli eventi rilevati di recente.
   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati server. */
window.HirisSentinelRoute = (function () {
  'use strict';

  var entityFieldSeq = 0;

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
      payload.situations = buildSituationsPayload();
      payload.preparation = buildPreparationPayload();
      save.disabled = true; status.textContent = 'Salvataggio…'; sitStatus.textContent = 'Salvataggio…';
      api('api/sentinel/policy', { method: 'POST', body: JSON.stringify(payload) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function () {
          status.textContent = 'Salvato ✓'; save.disabled = false;
          sitStatus.textContent = 'Salvato ✓';
        })
        .catch(function () {
          status.textContent = 'Errore nel salvataggio'; save.disabled = false;
          sitStatus.textContent = 'Errore nel salvataggio';
        });
    });

    card.appendChild(body);
    outlet.appendChild(card);

    // --- Situazioni ---
    var sit = data.situations || {};
    var sitHotAway = sit.hot_and_away || {};
    var sitAwayAlarm = sit.away_alarm_off || {};
    var sitHolistic = sit.holistic || {};
    var sitInputs = {};

    function textField(parent, labelText, value) {
      var wrap = el('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
      wrap.appendChild(el('span', null, labelText));
      var inp = el('input'); inp.type = 'text';
      inp.value = value != null ? value : '';
      inp.style.cssText = 'flex:1;padding:6px 8px;border-radius:8px;min-width:120px';
      wrap.appendChild(inp);
      parent.appendChild(wrap);
      return inp;
    }
    function entityField(parent, labelText, value, filterQuery) {
      var wrap = el('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
      wrap.appendChild(el('span', null, labelText));
      var inp = el('input'); inp.type = 'text';
      inp.value = value != null ? value : '';
      inp.style.cssText = 'flex:1;padding:6px 8px;border-radius:8px;min-width:120px';
      entityFieldSeq += 1;
      var listId = 'entity-list-' + entityFieldSeq;
      inp.setAttribute('list', listId);
      var datalist = el('datalist');
      datalist.id = listId;
      wrap.appendChild(inp);
      wrap.appendChild(datalist);
      parent.appendChild(wrap);
      api('api/entities?' + filterQuery, { method: 'GET' })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function (data) {
          var entities = data.entities || [];
          entities.forEach(function (e) {
            var option = el('option');
            option.value = e.entity_id;
            option.textContent = (e.friendly_name || '') + ' (' + e.entity_id + ')';
            datalist.appendChild(option);
          });
        })
        .catch(function () { /* free-text fallback resta disponibile */ });
      return inp;
    }
    function numberField(parent, labelText, value) {
      var wrap = el('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
      wrap.appendChild(el('span', null, labelText));
      var inp = el('input'); inp.type = 'number';
      inp.value = value != null ? value : '';
      inp.style.cssText = 'width:100px;padding:6px 8px;border-radius:8px';
      wrap.appendChild(inp);
      parent.appendChild(wrap);
      return inp;
    }
    function checkboxField(parent, labelText, checked) {
      var head = el('label');
      head.style.cssText = 'display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500;font-size:15px;margin-top:12px';
      var chk = el('input'); chk.type = 'checkbox'; chk.checked = !!checked;
      chk.style.cssText = 'width:20px;height:20px;flex:0 0 auto';
      head.appendChild(chk);
      head.appendChild(el('span', null, labelText));
      parent.appendChild(head);
      return chk;
    }

    var sitCard = el('section', 'section-card');
    var sitBody = el('div', 'sc-body');
    sitBody.appendChild(el('div', 'page-title', 'Situazioni'));
    sitBody.appendChild(el('p', 'sc-desc',
      'Comportamenti composti: ronda di sicurezza, caldo+assenza, allarme disinserito, riepilogo giornaliero.'));

    // Presenza (generali)
    var genRow = el('div');
    genRow.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--border,#2a2a2a)';
    sitInputs.presence_entity = entityField(genRow, 'Entità presenza', sit.presence_entity, 'domain=person,device_tracker,zone');
    genRow.appendChild(el('p', 'sc-desc',
      'La cadenza della ronda si imposta nelle opzioni dell\'add-on (sentinel_ronda_min).'));
    sitBody.appendChild(genRow);

    // hot_and_away
    var hotRow = el('div');
    hotRow.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--border,#2a2a2a)';
    var hotChk = checkboxField(hotRow, 'Caldo e fuori casa (hot_and_away)', sitHotAway.enabled);
    var hotOutsideTemp = entityField(hotRow, 'Entità temperatura esterna', sitHotAway.outside_temp_entity, 'device_class=temperature');
    var hotThreshold = numberField(hotRow, 'Soglia calore (°C)', sitHotAway.hot_threshold_c);
    var hotValve = entityField(hotRow, 'Entità valvola', sitHotAway.valve_entity, 'domain=switch,valve');
    var hotRunMinutes = numberField(hotRow, 'Durata attivazione (minuti)', sitHotAway.run_minutes);
    var hotSkipRain = checkboxField(hotRow, 'Salta se pioggia (skip_if_rain)', sitHotAway.skip_if_rain);
    sitBody.appendChild(hotRow);

    // away_alarm_off
    var awayRow = el('div');
    awayRow.style.cssText = 'padding:12px 0;border-bottom:1px solid var(--border,#2a2a2a)';
    var awayChk = checkboxField(awayRow, 'Allarme disinserito da fuori (away_alarm_off)', sitAwayAlarm.enabled);
    var awayAlarmEntity = entityField(awayRow, 'Entità allarme', sitAwayAlarm.alarm_entity, 'domain=alarm_control_panel');
    sitBody.appendChild(awayRow);

    // holistic
    var holRow = el('div');
    holRow.style.cssText = 'padding:12px 0';
    var holChk = checkboxField(holRow, 'Riepilogo giornaliero (holistic)', sitHolistic.enabled);
    var holHour = numberField(holRow, 'Ora invio', sitHolistic.hour);
    var holPerDay = numberField(holRow, 'Invii al giorno (per_day)', sitHolistic.per_day);
    sitBody.appendChild(holRow);

    var sitBar = el('div');
    sitBar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var sitStatus = el('span', 'sc-desc', '');
    sitBar.appendChild(sitStatus);
    sitBody.appendChild(sitBar);

    sitCard.appendChild(sitBody);
    outlet.appendChild(sitCard);

    // --- Preparazione ---
    var prep = data.preparation || {};
    var prepEvening = prep.evening_arrival || {};

    var prepCard = el('section', 'section-card');
    var prepBody = el('div', 'sc-body');
    prepBody.appendChild(el('div', 'page-title', 'Preparazione'));
    prepBody.appendChild(el('p', 'sc-desc',
      'Prepara la casa in anticipo su un evento previsto (es. rientro serale).'));

    var prepRow = el('div');
    prepRow.style.cssText = 'padding:12px 0';
    var prepEnabled = checkboxField(prepRow, 'Rientro serale (evening_arrival)', prepEvening.enabled);
    var prepTargetEntity = entityField(prepRow, 'Scena da attivare', prepEvening.target_entity, 'domain=scene,light,switch');
    var prepSunEntity = entityField(prepRow, 'Entità sole', prepEvening.sun_entity != null ? prepEvening.sun_entity : 'sun.sun', 'domain=sun');
    var prepAfterHour = numberField(prepRow, 'Non prima delle ore', prepEvening.after_hour);
    prepBody.appendChild(prepRow);

    prepCard.appendChild(prepBody);
    outlet.appendChild(prepCard);

    function buildPreparationPayload() {
      function n(v, fallback) { var x = parseInt(v, 10); return isNaN(x) ? fallback : x; }
      return {
        evening_arrival: {
          enabled: prepEnabled.checked,
          target_entity: prepTargetEntity.value,
          sun_entity: prepSunEntity.value,
          after_hour: n(prepAfterHour.value, prepEvening.after_hour)
        }
      };
    }

    function buildSituationsPayload() {
      function n(v, fallback) { var x = parseInt(v, 10); return isNaN(x) ? fallback : x; }
      return {
        presence_entity: sitInputs.presence_entity.value,
        hot_and_away: {
          enabled: hotChk.checked,
          outside_temp_entity: hotOutsideTemp.value,
          hot_threshold_c: n(hotThreshold.value, sitHotAway.hot_threshold_c),
          valve_entity: hotValve.value,
          run_minutes: n(hotRunMinutes.value, sitHotAway.run_minutes),
          skip_if_rain: hotSkipRain.checked
        },
        away_alarm_off: {
          enabled: awayChk.checked,
          alarm_entity: awayAlarmEntity.value
        },
        holistic: {
          enabled: holChk.checked,
          hour: n(holHour.value, sitHolistic.hour),
          per_day: n(holPerDay.value, sitHolistic.per_day)
        }
      };
    }

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
