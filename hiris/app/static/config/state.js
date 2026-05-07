/* HIRIS · Designer · global state with mini pub-sub */
(function() {
  var data = { unsaved: false };
  var subs = {};

  window.HirisState = {
    get: function(key) { return data[key]; },
    set: function(key, value) {
      data[key] = value;
      (subs[key] || []).forEach(function(fn) {
        try { fn(value); } catch(e) { console.error('state subscriber error', e); }
      });
    },
    subscribe: function(key, fn) {
      if (!subs[key]) subs[key] = [];
      subs[key].push(fn);
      return function() {
        subs[key] = (subs[key] || []).filter(function(f) { return f !== fn; });
      };
    },
    _internal_data: data, /* exposed for test only */
  };
})();
