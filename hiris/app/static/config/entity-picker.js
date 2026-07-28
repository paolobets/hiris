/* HIRIS · Designer · entity picker (instance-scoped)
   Sostituisce il selettore singleton (permessi.js _entitySelectionSet) con un
   componente istanziabile: HirisEntityPicker.create(rootEl, opts) -> instance.
   Ogni istanza ha il proprio stato e i propri id generati (nessun accesso a
   id globali) — necessario perché l'editor Agentbot ne serve TRE indipendenti
   per riga (entità trigger, entità condizione, entità target).
   Richiede escHtml (api.js), caricato prima di questo file in config.html. */
(function() {
  var _seq = 0;

  function create(rootEl, opts) {
    opts = opts || {};
    var id = 'ep' + (++_seq);
    var single = !!opts.single;
    var selection = [];                       // stato PER ISTANZA
    var searchTimer = null;
    var destroyed = false;

    rootEl.innerHTML =
      '<div class="ep-pills" id="' + id + '-pills"></div>' +
      '<div class="ep-chips" id="' + id + '-chips"></div>' +
      '<input class="ep-search" id="' + id + '-search" type="text" autocomplete="off" placeholder="' +
        escHtml(opts.placeholder || 'Cerca entità…') + '">' +
      '<div class="ep-suggestions" id="' + id + '-sugg" style="display:none"></div>';

    var chipsEl = rootEl.querySelector('#' + id + '-chips');
    var searchEl = rootEl.querySelector('#' + id + '-search');
    var suggEl = rootEl.querySelector('#' + id + '-sugg');
    var pillsEl = rootEl.querySelector('#' + id + '-pills');

    function emit() { if (opts.onChange) opts.onChange(getValue()); }

    function render() {
      chipsEl.innerHTML = '';
      selection.forEach(function(p) {
        var chip = document.createElement('span');
        chip.className = 'entity-chip';
        chip.innerHTML = '<span>' + escHtml(p) + '</span><span class="chip-remove">×</span>';
        chip.querySelector('.chip-remove').addEventListener('click', function() { remove(p); });
        chipsEl.appendChild(chip);
      });
    }

    function add(pattern) {
      if (!pattern) return;
      if (single) { selection = [pattern]; }
      else if (selection.indexOf(pattern) === -1) { selection.push(pattern); }
      else { return; }
      render(); emit();
    }
    function remove(pattern) {
      var i = selection.indexOf(pattern);
      if (i === -1) return;
      selection.splice(i, 1); render(); emit();
    }
    function getValue() { return selection.slice(); }
    function setValue(patterns) {
      selection = Array.isArray(patterns) ? patterns.filter(Boolean).slice() : [];
      if (single) selection = selection.slice(0, 1);
      render();               // setValue NON emette: è il caricamento, non una modifica utente
      searchEl.value = ''; suggEl.style.display = 'none';
    }

    (opts.pills || []).forEach(function(p) {
      // pill può essere una stringa (label === pattern) o { label, pattern }
      // per riusare le pillole con emoji del vecchio markup (label decorativa,
      // pattern è il valore effettivo aggiunto alla selezione).
      var label = (p && typeof p === 'object') ? p.label : p;
      var pattern = (p && typeof p === 'object') ? p.pattern : p;
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'domain-pill'; b.textContent = label;
      b.addEventListener('click', function() { add(pattern); searchEl.value = ''; });
      pillsEl.appendChild(b);
    });

    searchEl.addEventListener('input', function() {
      var q = searchEl.value.trim();
      clearTimeout(searchTimer);
      if (!q) { suggEl.style.display = 'none'; return; }
      searchTimer = setTimeout(function() {
        fetch('api/entities?q=' + encodeURIComponent(q))
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (destroyed) return;
            var items = (data && data.entities) || [];
            suggEl.innerHTML = '';
            if (!items.length) { suggEl.style.display = 'none'; return; }
            items.slice(0, 20).forEach(function(item) {
              var div = document.createElement('div');
              div.className = 'ep-suggestion';
              div.innerHTML = '<span>' + escHtml(item.entity_id) + '</span>' +
                '<span class="s-name">' + escHtml(item.friendly_name || '') + '</span>';
              div.addEventListener('click', function() {
                add(item.entity_id); searchEl.value = ''; suggEl.style.display = 'none';
              });
              suggEl.appendChild(div);
            });
            suggEl.style.display = '';
          })
          .catch(function() { suggEl.style.display = 'none'; });
      }, 300);
    });

    searchEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); add(searchEl.value.trim()); searchEl.value = ''; suggEl.style.display = 'none'; }
      if (e.key === 'Escape') { suggEl.style.display = 'none'; }
    });

    function onDocClick(e) { if (!rootEl.contains(e.target)) suggEl.style.display = 'none'; }
    document.addEventListener('click', onDocClick);

    setValue(opts.initial || []);

    return {
      getValue: getValue, setValue: setValue, add: add, remove: remove,
      destroy: function() {
        destroyed = true;
        clearTimeout(searchTimer);
        document.removeEventListener('click', onDocClick);   // chiude il leak del click-fuori
        rootEl.innerHTML = '';
      }
    };
  }

  window.HirisEntityPicker = { create: create };
})();
