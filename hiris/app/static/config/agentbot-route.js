/* HIRIS · Config · Sentinella (route #/agentbots)
   Configura i detector di anomalia/sicurezza (soglie, entità monitorate) e
   mostra la timeline degli eventi rilevati di recente.
   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati server. */
window.HirisAgentbotRoute = (function () {
  'use strict';

  var entityFieldSeq = 0;
  var labelFieldSeq = 0;
  function nextFieldId() {
    labelFieldSeq += 1;
    return 'sentinel-field-' + labelFieldSeq;
  }

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
    outlet.appendChild(el('div', 'page-title', 'Agentbot'));
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

    // SP-4 Fase B Task 5 (accoppiamento 1 del grounding A5): il backend
    // accetta un SOLO documento atomico (POST api/sentinel/policy con
    // {detectors, situations, preparation} insieme) -- non esiste un
    // endpoint per salvare una sola sezione. Dare a ciascuna card un
    // proprio bottone "Salva" implicherebbe comunque inviare l'intero
    // documento tre volte, con tre stati indipendenti che potrebbero
    // disallinearsi (es. Situazioni mostra "Salvato" mentre Preparazione è
    // ancora "Salvataggio…" per la STESSA richiesta HTTP). Scelta: UN solo
    // bottone Salva (su questa card, Detector) con UNO status. Le card
    // Situazioni/Preparazione non hanno più un proprio status "specchio"
    // (`sitStatus`, scritto da questo stesso handler ma disegnato su
    // un'altra card -- la vecchia fonte di ambiguità): mostrano invece un
    // richiamo testuale al bottone unico qui sotto (vedi 'sc-desc' aggiunto
    // alle loro card più sotto in questo file).
    var bar = el('div');
    bar.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center';
    var save = el('button', 'btn btn-primary', 'Salva impostazioni Sentinella');
    var status = el('span', 'sc-desc', '');
    bar.appendChild(save); bar.appendChild(status);
    body.appendChild(el('p', 'sc-desc', 'Salva insieme Detector, Situazioni e Preparazione (un unico documento).'));
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
      save.disabled = true; status.textContent = 'Salvataggio…';
      api('api/sentinel/policy', { method: 'POST', body: JSON.stringify(payload) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function () {
          status.textContent = 'Salvato ✓'; save.disabled = false;
        })
        .catch(function () {
          status.textContent = 'Errore nel salvataggio'; save.disabled = false;
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
      var inp = el('input'); inp.type = 'text';
      inp.id = nextFieldId();
      inp.value = value != null ? value : '';
      inp.style.cssText = 'flex:1;padding:6px 8px;border-radius:8px;min-width:120px';
      var lbl = el('label', null, labelText);
      lbl.setAttribute('for', inp.id);
      wrap.appendChild(lbl);
      wrap.appendChild(inp);
      parent.appendChild(wrap);
      return inp;
    }
    function entityField(parent, labelText, value, filterQuery) {
      var wrap = el('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
      var inp = el('input'); inp.type = 'text';
      inp.id = nextFieldId();
      inp.value = value != null ? value : '';
      inp.style.cssText = 'flex:1;padding:6px 8px;border-radius:8px;min-width:120px';
      var lbl = el('label', null, labelText);
      lbl.setAttribute('for', inp.id);
      entityFieldSeq += 1;
      var listId = 'entity-list-' + entityFieldSeq;
      inp.setAttribute('list', listId);
      var datalist = el('datalist');
      datalist.id = listId;
      wrap.appendChild(lbl);
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
      var inp = el('input'); inp.type = 'number';
      inp.id = nextFieldId();
      inp.value = value != null ? value : '';
      inp.style.cssText = 'width:100px;padding:6px 8px;border-radius:8px';
      var lbl = el('label', null, labelText);
      lbl.setAttribute('for', inp.id);
      wrap.appendChild(lbl);
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
    function selectField(parent, labelText, options, value) {
      var wrap = el('div');
      wrap.style.cssText = 'display:flex;align-items:center;gap:8px;margin-top:8px';
      var sel = el('select');
      sel.id = nextFieldId();
      sel.style.cssText = 'padding:6px 8px;border-radius:8px;min-width:120px';
      (options || []).forEach(function (o) {
        var opt = el('option');
        opt.value = o.value;
        opt.textContent = o.label;
        if (o.value === value) opt.selected = true;
        sel.appendChild(opt);
      });
      var lbl = el('label', null, labelText);
      lbl.setAttribute('for', sel.id);
      wrap.appendChild(lbl);
      wrap.appendChild(sel);
      parent.appendChild(wrap);
      return sel;
    }
    function textareaField(parent, labelText, value) {
      var wrap = el('div');
      wrap.style.cssText = 'margin-top:8px';
      var ta = el('textarea');
      ta.id = nextFieldId();
      ta.value = value != null ? value : '';
      ta.rows = 3;
      ta.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:8px;margin-top:4px;font-family:inherit';
      var lbl = el('label', null, labelText);
      lbl.setAttribute('for', ta.id);
      wrap.appendChild(lbl);
      wrap.appendChild(ta);
      parent.appendChild(wrap);
      return ta;
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

    // Accoppiamento 2 del grounding A5 (deciso sopra, vedi il commento sul
    // bottone Salva del Detector): niente più status "specchio" scritto da
    // un bottone che vive su un'altra card -- un solo richiamo testuale al
    // punto reale dove si salva.
    sitBody.appendChild(el('p', 'sc-desc', 'Si salva con "Salva impostazioni Sentinella" nella card Detector qui sopra.'));

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
    prepBody.appendChild(el('p', 'sc-desc', 'Si salva con "Salva impostazioni Sentinella" nella card Detector qui sopra.'));

    prepCard.appendChild(prepBody);
    outlet.appendChild(prepCard);

    // --- Regole Agentbot: elenco di navigazione, SOLA LETTURA -----------
    // SP-4 Fase B Task 5: l'editor per-entità (creazione/modifica/salvataggio
    // per riga, POST/PUT/DELETE api/agentbots) si è spostato in
    // config/agentbot-editor.js (route #/agentbots/new e #/agentbots/{id}).
    // Questa pagina resta "il documento" della policy Sentinella (un solo
    // POST api/sentinel/policy per detector+situazioni+preparazione) più
    // l'osservabilità (timeline, suggerimenti Brain) -- non possiede più
    // alcun CRUD sugli Agentbot. Questo blocco si limita a elencarli con un
    // link a testa (nessun form, nessun salvataggio, sola GET) così la
    // pagina resta il punto da cui si arriva a un Agentbot esistente o se
    // ne crea uno nuovo -- senza reintrodurre la logica rimossa.
    var rulesCard = el('section', 'section-card');
    var rulesBody = el('div', 'sc-body');
    var rulesHeader = el('div');
    rulesHeader.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline';
    rulesHeader.appendChild(el('div', 'page-title', 'Regole Agentbot'));
    var newRuleLink = document.createElement('a');
    newRuleLink.className = 'btn btn-primary';
    newRuleLink.href = '#/agentbots/new';
    newRuleLink.textContent = '+ Nuovo Agentbot';
    rulesHeader.appendChild(newRuleLink);
    rulesBody.appendChild(rulesHeader);
    rulesBody.appendChild(el('p', 'sc-desc',
      'Regole personalizzate: trigger (evento o pianificazione), ragionamento AI opzionale, azione. Click su una regola per aprirne l\'editor.'));

    var rulesListEl = el('div');
    rulesBody.appendChild(rulesListEl);
    rulesCard.appendChild(rulesBody);
    outlet.appendChild(rulesCard);

    api('api/agentbots', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (j) {
        var rules = j.agentbots || [];
        if (!rules.length) {
          rulesListEl.appendChild(el('p', 'sc-desc', 'Nessun Agentbot configurato.'));
          return;
        }
        rules.forEach(function (rule) {
          var link = document.createElement('a');
          link.className = 'log-row';
          link.style.cssText = 'display:block;text-decoration:none;color:inherit';
          link.href = '#/agentbots/' + encodeURIComponent(rule.id);
          var badge = rule.enabled ? '● Attiva' : '○ Disabilitata';
          link.textContent = (rule.name || '(senza nome)') + ' · ' + (rule.severity || 'info') + ' · ' + badge;
          rulesListEl.appendChild(link);
        });
      })
      .catch(function () {
        rulesListEl.appendChild(el('p', 'sc-desc', 'Errore nel caricamento degli Agentbot.'));
      });

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

    outlet.appendChild(el('p', 'page-subtitle', 'Suggerimenti del Brain'));
    var suggList = el('div');
    outlet.appendChild(suggList);
    api('api/suggestions', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (j) {
        var suggs = j.suggestions || [];
        if (!suggs.length) {
          suggList.appendChild(el('p', 'sc-desc', 'Nessun suggerimento del Brain.'));
          return;
        }
        suggs.forEach(function (s) {
          var row = el('div', 'log-row');

          var badge = el('span', 'sc-badge', 'Brain');
          badge.style.cssText = 'font-size:11px;padding:2px 6px;border-radius:6px;background:var(--accent,#3a6);color:#fff;margin-right:8px';
          row.appendChild(badge);

          var statusText = el('span', null,
            (s.title || '') + ' · ' + (s.rationale || '') + ' · ' + (s.status || ''));
          row.appendChild(statusText);

          if (s.kind === 'coverage' && s.status === 'applied') {
            var undoBtn = el('button', 'btn', 'Annulla');
            undoBtn.style.cssText = 'margin-left:8px';
            row.appendChild(undoBtn);
            var errText = el('span', 'sc-desc', '');
            errText.style.cssText = 'margin-left:8px';
            row.appendChild(errText);

            undoBtn.addEventListener('click', function () {
              undoBtn.disabled = true;
              errText.textContent = '';
              api('api/suggestions/' + s.id + '/undo', { method: 'POST' })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
                .then(function (res) {
                  if (res && res.ok) {
                    s.status = 'dismissed';
                    statusText.textContent =
                      (s.title || '') + ' · ' + (s.rationale || '') + ' · ' + (s.status || '');
                    undoBtn.style.display = 'none';
                  } else {
                    errText.textContent = 'Annullamento non riuscito.';
                    undoBtn.disabled = false;
                  }
                })
                .catch(function () {
                  errText.textContent = 'Errore nell\'annullamento.';
                  undoBtn.disabled = false;
                });
            });
          }

          suggList.appendChild(row);
        });
      })
      .catch(function () { suggList.appendChild(el('p', 'sc-desc', 'Errore nel caricamento dei suggerimenti.')); });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Agentbot'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));
    api('api/sentinel/policy', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (data) { render(outlet, data); })
      .catch(function () {
        outlet.innerHTML = '';
        outlet.appendChild(el('div', 'page-title', 'Agentbot'));
        outlet.appendChild(el('p', 'page-subtitle', 'Errore nel caricamento.'));
      });
  }

  return { mount: mount };
})();
