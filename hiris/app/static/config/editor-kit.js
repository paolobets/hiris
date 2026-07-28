/* HIRIS · Designer · editor-kit (SP-4 Fase B Task 3)
   Kit condiviso fra gli editor Chatbot/Agentbot: fabbriche di campo, select
   modello con fetch cachata, gruppo checkbox istanza-scoped, dirty tracking
   reale (MutationObserver, non uno snapshot one-shot) + guard di navigazione,
   barra Salva/Annulla sticky.

   Chiude due bug live (vedi docs/design/2026-07-28-piano-SP4b1-cornice-
   unificata.md):
   1) le modifiche a chip/tool/azioni non attivavano "Salva" -- setupStickyActions
      faceva un querySelectorAll UNA VOLTA al mount, i controlli creati dopo
      (chip entity-picker, checkbox di buildToolChecks/buildActionChecks) non
      erano mai agganciati a markDirty. dirty.track() qui sotto osserva il
      sottoalbero con un MutationObserver, non lo fotografa.
   2) navigare via con modifiche non salvate le perdeva in silenzio -- 'unsaved'
      era letto solo dal bottone Annulla, nessun guard su hashchange/beforeunload.
      dirty.guard() qui sotto lo installa.

   loadModels()/_setModelValue() vivevano in api.js (file di utility pure) ma
   sono codice editor -- assorbiti qui in modelSelect()/setModelValue() con
   UNA fetch condivisa e cachata (prima: una per riga in agentbot-route.js).

   buildToolChecks/buildActionChecks/getSelectedTools/getSelectedActions
   (permessi.js) sono assorbiti in checkGroup(): istanza-scoped, non più
   #tool-checks/#action-checks globali. */
(function() {
  'use strict';

  var _seq = 0;
  function nextId(prefix) {
    _seq += 1;
    return (prefix || 'hk') + '-' + _seq;
  }

  /* ── field factories ──────────────────────────────────────────────
     Ognuna ritorna l'elemento input/select/textarea creato. Stessa
     struttura visiva (classi field/input/select/textarea/checkbox-row,
     field-hint) già usata dal markup statico di chatbot-editor.js, così
     la CSS esistente (hiris-config.css) si applica senza modifiche. */

  function fieldWrap(parent, labelText, forId) {
    var wrap = document.createElement('div');
    wrap.className = 'field';
    if (labelText) {
      var lbl = document.createElement('label');
      lbl.setAttribute('for', forId);
      lbl.textContent = labelText;
      wrap.appendChild(lbl);
    }
    parent.appendChild(wrap);
    return wrap;
  }

  function appendHint(wrap, hintText) {
    if (!hintText) return null;
    var h = document.createElement('p');
    h.className = 'field-hint';
    h.textContent = hintText;
    wrap.appendChild(h);
    return h;
  }

  function text(parent, opts) {
    opts = opts || {};
    var id = opts.id || nextId('hk-text');
    var wrap = fieldWrap(parent, opts.label, id);
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.className = 'input';
    inp.id = id;
    inp.value = opts.value != null ? opts.value : '';
    if (opts.placeholder) inp.placeholder = opts.placeholder;
    wrap.appendChild(inp);
    appendHint(wrap, opts.hint);
    return inp;
  }

  function number(parent, opts) {
    opts = opts || {};
    var id = opts.id || nextId('hk-number');
    var wrap = fieldWrap(parent, opts.label, id);
    var inp = document.createElement('input');
    inp.type = 'number';
    inp.className = 'input';
    inp.id = id;
    inp.value = opts.value != null ? opts.value : '';
    if (opts.min != null) inp.min = opts.min;
    if (opts.max != null) inp.max = opts.max;
    wrap.appendChild(inp);
    appendHint(wrap, opts.hint);
    return inp;
  }

  function checkbox(parent, opts) {
    opts = opts || {};
    var id = opts.id || nextId('hk-check');
    var row = document.createElement('label');
    row.className = 'checkbox-row';
    var inp = document.createElement('input');
    inp.type = 'checkbox';
    inp.id = id;
    inp.checked = !!opts.value;
    row.appendChild(inp);
    row.appendChild(document.createTextNode(' ' + (opts.label || '')));
    parent.appendChild(row);
    return inp;
  }

  function select(parent, opts) {
    opts = opts || {};
    var id = opts.id || nextId('hk-select');
    var wrap = fieldWrap(parent, opts.label, id);
    var sel = document.createElement('select');
    sel.className = 'select';
    sel.id = id;
    (opts.options || []).forEach(function(o) {
      var opt = document.createElement('option');
      opt.value = o.value;
      opt.textContent = o.label != null ? o.label : o.value;
      if (o.value === opts.value) opt.selected = true;
      sel.appendChild(opt);
    });
    wrap.appendChild(sel);
    appendHint(wrap, opts.hint);
    return sel;
  }

  function textarea(parent, opts) {
    opts = opts || {};
    var id = opts.id || nextId('hk-textarea');
    var wrap = fieldWrap(parent, opts.label, id);
    var ta = document.createElement('textarea');
    ta.className = 'textarea';
    ta.id = id;
    ta.rows = opts.rows || 3;
    ta.value = opts.value != null ? opts.value : '';
    if (opts.placeholder) ta.placeholder = opts.placeholder;
    wrap.appendChild(ta);
    appendHint(wrap, opts.hint);
    return ta;
  }

  /* ── modelSelect: UNA fetch api/models condivisa e cachata ──────────
     Prima: agentbot-route.js chiamava GET api/models per OGNI riga
     (modelSelectField, una per lens). api.js.loadModels() ne faceva
     un'altra copia indipendente per l'editor Chatbot (#f-model). Qui:
     un'unica promise a livello di modulo, risolta una sola volta, letta
     da tutte le modelSelect() della pagina. */

  var _modelsPromise = null;
  function loadModelsOnce() {
    if (!_modelsPromise) {
      _modelsPromise = fetch('api/models')
        .then(function(r) { return r.ok ? r.json() : { providers: [] }; })
        .catch(function() { return { providers: [] }; });
    }
    return _modelsPromise;
  }

  function setModelValue(sel, val) {
    if (!sel) return;
    sel.value = val;
    if (sel.value !== val) {
      /* Modello non nell'elenco (provider non configurato) -- lo aggiunge
         come opzione orfana invece di scartare silenziosamente la scelta
         salvata dall'utente. */
      var opt = document.createElement('option');
      opt.value = val;
      opt.textContent = val + ' (provider non configurato)';
      sel.insertBefore(opt, sel.firstChild);
      sel.value = val;
    }
  }

  function populateModelOptions(sel, opts) {
    opts = opts || {};
    return loadModelsOnce().then(function(data) {
      var providers = data.providers || [];
      var current = (opts.value != null ? opts.value : sel.value) || 'auto';
      sel.innerHTML = '';
      providers.forEach(function(p) {
        var grp = document.createElement('optgroup');
        grp.label = p.label;
        (p.models || []).forEach(function(m) {
          var opt = document.createElement('option');
          opt.value = m;
          var isFree = /:free$/.test(m);
          if (m === 'auto') {
            opt.textContent = 'auto — sceglie il modello migliore';
          } else if (isFree) {
            /* Hint visivo: il modello ha i vincoli del piano gratuito
               OpenRouter (quota giornaliera bassa, rate-limit frequenti). */
            opt.textContent = m + '  • free';
            opt.title = 'Modello gratuito: quota giornaliera bassa e rate-limit upstream frequenti. Adatto a chat occasionale, sconsigliato per Chatbot/Agentbot schedulati.';
          } else {
            opt.textContent = m;
          }
          grp.appendChild(opt);
        });
        sel.appendChild(grp);
      });
      if (providers.length === 0) {
        var opt = document.createElement('option');
        opt.value = 'auto';
        opt.textContent = 'auto — nessun provider configurato';
        sel.appendChild(opt);
      }
      setModelValue(sel, current);
      if (opts.hintEl && providers.length > 0) {
        opts.hintEl.textContent = 'Seleziona il modello AI. Sono disponibili '
          + providers.map(function(p) { return p.label; }).join(', ')
          + '. «auto» sceglie automaticamente.';
      }
      return sel;
    });
  }

  function modelSelect(parent, opts) {
    opts = opts || {};
    var sel = opts.selectEl;
    var hint = opts.hintEl || null;
    if (!sel) {
      var id = opts.id || nextId('hk-model');
      var wrap = fieldWrap(parent, opts.label, id);
      sel = document.createElement('select');
      sel.className = 'select';
      sel.id = id;
      var optAuto = document.createElement('option');
      optAuto.value = 'auto';
      optAuto.textContent = 'auto — sceglie il modello migliore';
      sel.appendChild(optAuto);
      wrap.appendChild(sel);
      if (opts.hint !== false) {
        hint = document.createElement('p');
        hint.className = 'field-hint';
        hint.id = opts.hintId || (id + '-hint');
        hint.textContent = 'Seleziona il modello AI. «auto» sceglie automaticamente.';
        wrap.appendChild(hint);
      }
    }
    if (opts.value) setModelValue(sel, opts.value);
    populateModelOptions(sel, { value: opts.value, hintEl: hint });
    return sel;
  }

  /* ── checkGroup: gruppo checkbox istanza-scoped ──────────────────────
     Sostituisce buildToolChecks/buildActionChecks/getSelectedTools/
     getSelectedActions (permessi.js): non più #tool-checks/#action-checks
     globali, ogni chiamata crea il proprio contenitore + stato. */

  function checkGroup(parent, opts) {
    opts = opts || {};
    var items = opts.items || [];
    var selected = (opts.selected || []).slice();
    var wrap = document.createElement('div');
    wrap.className = opts.className || 'tool-checkboxes';
    var prefix = opts.idPrefix || nextId('hk-cg');

    function safeId(rawId) {
      return prefix + '-' + String(rawId).replace(/[^a-zA-Z0-9_-]/g, '_');
    }

    function render() {
      wrap.innerHTML = '';
      items.forEach(function(it) {
        var row = document.createElement('div');
        row.className = 'tool-item';
        var chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.value = it.id;
        chk.checked = selected.indexOf(it.id) >= 0;
        chk.id = safeId(it.id);
        var lbl = document.createElement('label');
        lbl.htmlFor = chk.id;
        lbl.appendChild(chk);
        lbl.appendChild(document.createTextNode(' ' + (it.label || it.id)));
        row.appendChild(lbl);
        if (it.desc) {
          var desc = document.createElement('div');
          desc.className = 'tool-desc';
          desc.textContent = it.desc;
          row.appendChild(desc);
        }
        chk.addEventListener('change', function() {
          var i = selected.indexOf(it.id);
          if (chk.checked && i === -1) selected.push(it.id);
          else if (!chk.checked && i !== -1) selected.splice(i, 1);
        });
        wrap.appendChild(row);
      });
    }

    function getSelected() { return selected.slice(); }
    function setSelected(vals) {
      selected = Array.isArray(vals) ? vals.slice() : [];
      render();
    }

    render();
    parent.appendChild(wrap);
    return { el: wrap, getSelected: getSelected, setSelected: setSelected };
  }

  /* ── dirty tracking: MutationObserver + delegation, non uno snapshot ── */

  function track(rootEl, onDirty) {
    function wire(el) {
      if (el.__hkWired) return;
      el.__hkWired = true;
      el.addEventListener('change', onDirty);
      el.addEventListener('input', onDirty);
    }
    rootEl.querySelectorAll('input, select, textarea').forEach(wire);
    var mo = new window.MutationObserver(function(muts) {
      muts.forEach(function(m) {
        Array.prototype.forEach.call(m.addedNodes, function(n) {
          if (n.nodeType !== 1) return;
          if (n.matches && n.matches('input, select, textarea')) wire(n);
          if (n.querySelectorAll) n.querySelectorAll('input, select, textarea').forEach(wire);
        });
      });
    });
    mo.observe(rootEl, { childList: true, subtree: true });
    return { stop: function() { mo.disconnect(); } };
  }

  /* ── guard: hashchange + beforeunload, chiede conferma se dirty ──────
     Nota su hashchange: l'URL è GIA' cambiato quando l'evento arriva (non
     è annullabile via preventDefault). "Annullare" qui significa: se
     l'utente rifiuta, si ripristina l'hash precedente (che a sua volta
     genera un secondo hashchange -- il flag `reverting` lo ignora per non
     ri-chiedere conferma su un evento che il guard stesso ha causato). */

  function guard(isDirtyFn) {
    var lastHash = window.location.hash;
    var reverting = false;

    function onHashChange(e) {
      if (reverting) {
        reverting = false;
        lastHash = window.location.hash;
        return;
      }
      if (typeof isDirtyFn === 'function' && isDirtyFn()) {
        var ok = window.confirm('Ci sono modifiche non salvate. Vuoi davvero uscire senza salvare?');
        if (!ok) {
          reverting = true;
          window.location.hash = lastHash;
          if (e && typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
          return;
        }
      }
      lastHash = window.location.hash;
    }

    function onBeforeUnload(e) {
      if (typeof isDirtyFn === 'function' && isDirtyFn()) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    }

    window.addEventListener('hashchange', onHashChange);
    window.addEventListener('beforeunload', onBeforeUnload);

    return {
      stop: function() {
        window.removeEventListener('hashchange', onHashChange);
        window.removeEventListener('beforeunload', onBeforeUnload);
      }
    };
  }

  /* ── saveBar: barra sticky unica, Salva disabled quando clean ────────
     rootEl deve contenere i bottoni #btn-save/#btn-cancel/#btn-test-run/
     #btn-delete (o [data-hk="save|cancel|test-run|delete"]). onDelete
     assente -> il bottone Elimina resta nascosto (agente nuovo, non
     ancora salvato -- stesso comportamento di prima). */

  function saveBar(rootEl, opts) {
    opts = opts || {};
    function find(name, legacyId) {
      return rootEl.querySelector('[data-hk="' + name + '"]') ||
        (legacyId ? rootEl.querySelector('#' + legacyId) : null);
    }
    var btnSave = find('save', 'btn-save');
    var btnCancel = find('cancel', 'btn-cancel');
    var btnDelete = find('delete', 'btn-delete');
    var btnTestRun = find('test-run', 'btn-test-run');

    if (btnSave && opts.onSave) {
      btnSave.addEventListener('click', function() { opts.onSave(); });
    }
    if (btnCancel && opts.onCancel) {
      btnCancel.addEventListener('click', function() { opts.onCancel(); });
    }
    if (btnDelete) {
      if (opts.onDelete) {
        btnDelete.style.display = '';
        btnDelete.addEventListener('click', function() { opts.onDelete(); });
      } else {
        btnDelete.style.display = 'none';
      }
    }
    if (btnTestRun && opts.onTestRun) {
      btnTestRun.addEventListener('click', function() { opts.onTestRun(); });
    }

    return {
      setDirty: function(isDirty) { if (btnSave) btnSave.disabled = !isDirty; }
    };
  }

  window.HirisEditorKit = {
    field: { text: text, number: number, checkbox: checkbox, select: select, textarea: textarea },
    modelSelect: modelSelect,
    setModelValue: setModelValue,
    checkGroup: checkGroup,
    dirty: { track: track, guard: guard },
    saveBar: saveBar
  };
})();
