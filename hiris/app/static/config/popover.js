/* HIRIS · Designer · popover atom (anchored, dismiss on outside click / ESC) */
(function() {
  var current = null;

  function position(pop, anchor) {
    var rect = anchor.getBoundingClientRect();
    var popHeight = pop.offsetHeight;
    var popWidth = pop.offsetWidth;
    var spaceBelow = window.innerHeight - rect.bottom;
    var below = spaceBelow > popHeight + 16;

    pop.style.position = 'absolute';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    if (below) {
      pop.style.top = (window.scrollY + rect.bottom + 6) + 'px';
    } else {
      pop.style.top = (window.scrollY + rect.top - popHeight - 6) + 'px';
    }
    /* clamp horizontal so popover stays in viewport */
    var leftEdge = parseFloat(pop.style.left);
    if (leftEdge + popWidth > window.scrollX + window.innerWidth - 12) {
      pop.style.left = (window.scrollX + window.innerWidth - popWidth - 12) + 'px';
    }
  }

  function build(opts) {
    var container = document.getElementById('popover-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'popover-container';
      document.body.appendChild(container);
    }
    container.innerHTML =
      '<div class="popover" role="dialog">' +
        '<div class="pop-arrow"></div>' +
        '<div class="popover-content"></div>' +
      '</div>';
    var pop = container.querySelector('.popover');
    var content = container.querySelector('.popover-content');
    if (typeof opts.body === 'string') content.innerHTML = opts.body;
    else if (opts.body instanceof HTMLElement) content.appendChild(opts.body);
    else if (opts.body instanceof DocumentFragment) content.appendChild(opts.body);

    requestAnimationFrame(function() { position(pop, opts.anchor); });

    function close() {
      container.innerHTML = '';
      current = null;
      document.removeEventListener('mousedown', onOutside, true);
      document.removeEventListener('keydown', onKey);
    }

    function onOutside(e) {
      if (!pop.contains(e.target) && !opts.anchor.contains(e.target)) {
        close();
        if (opts.onClose) opts.onClose();
      }
    }
    function onKey(e) {
      if (e.key === 'Escape') { close(); if (opts.onClose) opts.onClose(); }
    }

    setTimeout(function() {
      document.addEventListener('mousedown', onOutside, true);
      document.addEventListener('keydown', onKey);
    }, 0);

    current = { container: container, close: close, content: content };
    return current;
  }

  window.HirisPopover = {
    open: function(opts) {
      if (current) current.close();
      return build(opts || {});
    },
    close: function() { if (current) current.close(); },
    isOpen: function() { return current !== null; },
  };
})();
