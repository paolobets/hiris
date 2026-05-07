/* HIRIS · Designer · cron chip + popover (Phase 7) */
(function() {
  var CRON_PRESETS = [
    { id: 'hourly',   label: '⏰ Ogni ora',           expr: '0 * * * *',   desc: 'Ogni ora al minuto 0' },
    { id: 'morning',  label: '🌅 Ogni mattina 06:00', expr: '0 6 * * *',   desc: 'Ogni giorno alle 06:00' },
    { id: 'evening',  label: '🌙 Ogni sera 20:00',    expr: '0 20 * * *',  desc: 'Ogni giorno alle 20:00' },
    { id: 'weekday',  label: '📆 Solo lunedì 09:00',  expr: '0 9 * * 1',   desc: 'Ogni lunedì alle 09:00' },
    { id: 'weekend',  label: '🛋 Weekend 10:00',      expr: '0 10 * * 6,0', desc: 'Sab/dom alle 10:00' },
    { id: 'custom',   label: '⚙ Custom…',             expr: null,          desc: 'Espressione cron personalizzata' },
  ];

  function findPresetByExpr(expr) {
    for (var i = 0; i < CRON_PRESETS.length; i++) {
      if (CRON_PRESETS[i].expr === expr) return CRON_PRESETS[i];
    }
    return null;
  }

  function describeCron(expr) {
    var p = findPresetByExpr(expr);
    if (p) return p.desc;
    if (typeof _cronDesc === 'function') {
      try { return _cronDesc(expr); } catch(e) {}
    }
    return 'Espressione personalizzata';
  }

  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function updateChip(expr) {
    var hidden = document.getElementById('nt-cron');
    var label = document.getElementById('nt-cron-chip-label');
    var exprEl = document.getElementById('nt-cron-chip-expr');
    if (hidden) hidden.value = expr;
    if (label) label.textContent = describeCron(expr);
    if (exprEl) exprEl.textContent = expr;
  }

  function buildPopoverBody(currentExpr) {
    var matched = findPresetByExpr(currentExpr);
    var activeId = matched ? matched.id : 'custom';
    var html =
      '<div class="popover-presets">' +
        CRON_PRESETS.map(function(p) {
          return '<button class="popover-preset' + (p.id === activeId ? ' active' : '') + '" data-preset="' + p.id + '">' + p.label + '</button>';
        }).join('') +
      '</div>' +
      '<div class="popover-custom" id="popover-cron-custom" style="display:' + (activeId === 'custom' ? 'grid' : 'none') + ';grid-template-columns:repeat(5, 1fr);gap:8px"></div>' +
      '<div class="popover-preview" id="popover-cron-preview"><strong>' + escHtml(currentExpr) + '</strong> · ' + escHtml(describeCron(currentExpr)) + '</div>' +
      '<div class="popover-foot">' +
        '<button class="btn btn-sm" data-act="cancel">Annulla</button>' +
        '<button class="btn btn-sm btn-primary" data-act="confirm">✓ Conferma</button>' +
      '</div>';
    return html;
  }

  function renderCustomFields(container, currentExpr) {
    var parts = (currentExpr || '0 6 * * *').split(' ');
    while (parts.length < 5) parts.push('*');
    var labels = ['Min', 'Ora', 'G/m', 'Mese', 'G/sett'];
    container.innerHTML = labels.map(function(label, i) {
      return '<div>' +
        '<label style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-4);display:block;margin-bottom:4px">' + label + '</label>' +
        '<input class="input" type="text" value="' + escHtml(parts[i]) + '" data-cron-pos="' + i + '" style="font-size:12px;padding:5px">' +
      '</div>';
    }).join('');
    container.querySelectorAll('[data-cron-pos]').forEach(function(input) {
      input.addEventListener('input', function() {
        var pos = parseInt(input.dataset.cronPos);
        parts[pos] = input.value || '*';
        var expr = parts.join(' ');
        updateChip(expr);
        var preview = container.parentElement.querySelector('#popover-cron-preview');
        if (preview) preview.innerHTML = '<strong>' + escHtml(expr) + '</strong> · ' + escHtml(describeCron(expr));
      });
    });
  }

  function openCronPopover(anchor) {
    var hidden = document.getElementById('nt-cron');
    var current = (hidden && hidden.value) || '0 6 * * *';

    var pop = HirisPopover.open({
      anchor: anchor,
      body: buildPopoverBody(current),
    });

    var content = pop.content;

    /* Custom fields render iniziale se attivo */
    if (findPresetByExpr(current) === null) {
      renderCustomFields(content.querySelector('#popover-cron-custom'), current);
    }

    /* Preset clicks */
    content.querySelectorAll('.popover-preset').forEach(function(btn) {
      btn.addEventListener('click', function() {
        content.querySelectorAll('.popover-preset').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var preset = CRON_PRESETS.filter(function(p) { return p.id === btn.dataset.preset; })[0];
        var customDiv = content.querySelector('#popover-cron-custom');
        if (preset.id === 'custom') {
          customDiv.style.display = 'grid';
          renderCustomFields(customDiv, hidden ? hidden.value : '0 6 * * *');
        } else {
          customDiv.style.display = 'none';
          updateChip(preset.expr);
          var preview = content.querySelector('#popover-cron-preview');
          if (preview) preview.innerHTML = '<strong>' + escHtml(preset.expr) + '</strong> · ' + escHtml(preset.desc);
        }
      });
    });

    /* Cancel/confirm */
    content.querySelector('[data-act="cancel"]').addEventListener('click', function() {
      HirisPopover.close();
    });
    content.querySelector('[data-act="confirm"]').addEventListener('click', function() {
      HirisPopover.close();
      /* Trigger change event on hidden input for any listener (legacy triggers.js) */
      var hidden = document.getElementById('nt-cron');
      if (hidden) hidden.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  /* Delegated click handler on chip */
  document.addEventListener('click', function(e) {
    var chip = e.target.closest('#nt-cron-chip');
    if (chip) {
      e.preventDefault();
      e.stopPropagation();
      openCronPopover(chip);
    }
  });

  /* Keyboard: Enter/Space sul chip apre popover */
  document.addEventListener('keydown', function(e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.id === 'nt-cron-chip') {
      e.preventDefault();
      openCronPopover(e.target);
    }
  });

  /* When trigger type changes to cron, populate chip with current value */
  document.addEventListener('change', function(e) {
    if (e.target && e.target.id === 'new-trigger-type' && e.target.value === 'cron') {
      var hidden = document.getElementById('nt-cron');
      if (hidden && hidden.value) updateChip(hidden.value);
    }
  });

  window.HirisCronPopover = { open: openCronPopover, updateChip: updateChip, presets: CRON_PRESETS };
})();
