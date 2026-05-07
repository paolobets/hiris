/* HIRIS · Designer · drawer atom (right-slide overlay) */
(function() {
  var current = null;

  function build(opts) {
    var container = document.getElementById('drawer-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'drawer-container';
      document.body.appendChild(container);
    }
    container.innerHTML =
      '<div class="drawer-overlay"></div>' +
      '<aside class="drawer" role="dialog" aria-label="' + (opts.title || 'Drawer') + '">' +
        '<div class="drawer-head">' +
          '<h3>' + (opts.title || '') + '</h3>' +
          '<button class="drawer-close" aria-label="Chiudi">×</button>' +
        '</div>' +
        '<div class="drawer-body"></div>' +
        '<div class="drawer-foot">' +
          '<button class="btn btn-sm" data-act="cancel">' + (opts.cancelLabel || 'Annulla') + '</button>' +
          '<button class="btn btn-sm btn-primary" data-act="confirm">' + (opts.confirmLabel || '✓ Conferma') + '</button>' +
        '</div>' +
      '</aside>';
    var body = container.querySelector('.drawer-body');
    if (typeof opts.body === 'string') body.innerHTML = opts.body;
    else if (opts.body instanceof HTMLElement) body.appendChild(opts.body);
    else if (opts.body instanceof DocumentFragment) body.appendChild(opts.body);

    var overlay = container.querySelector('.drawer-overlay');
    var drawer = container.querySelector('.drawer');
    var closeBtn = container.querySelector('.drawer-close');
    var cancelBtn = container.querySelector('[data-act="cancel"]');
    var confirmBtn = container.querySelector('[data-act="confirm"]');

    function close() {
      drawer.classList.remove('open');
      overlay.classList.remove('open');
      setTimeout(function() {
        if (current && current.container === container) {
          container.innerHTML = '';
          current = null;
        }
      }, 240);
      document.removeEventListener('keydown', onKey);
    }

    function onKey(e) { if (e.key === 'Escape') { close(); if (opts.onCancel) opts.onCancel(); } }

    overlay.addEventListener('click', function() { close(); if (opts.onCancel) opts.onCancel(); });
    closeBtn.addEventListener('click', function() { close(); if (opts.onCancel) opts.onCancel(); });
    cancelBtn.addEventListener('click', function() { close(); if (opts.onCancel) opts.onCancel(); });
    confirmBtn.addEventListener('click', function() {
      var ok = !opts.onConfirm || opts.onConfirm() !== false;
      if (ok) close();
    });
    document.addEventListener('keydown', onKey);

    requestAnimationFrame(function() {
      drawer.classList.add('open');
      overlay.classList.add('open');
    });

    current = { container: container, close: close };
    return current;
  }

  window.HirisDrawer = {
    open: function(opts) {
      if (current) current.close();
      return build(opts || {});
    },
    close: function() { if (current) current.close(); },
    isOpen: function() { return current !== null; },
  };
})();
