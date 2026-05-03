/* HIRIS · Designer · tabs + theme toggle + version footer */

function switchTab(tabId) {
  document.querySelectorAll('#agent-tabs .tab-btn').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('#form fieldset').forEach(function(f) { f.classList.remove('tab-active'); });
  var btn = document.querySelector('#agent-tabs .tab-btn[data-tab="' + tabId + '"]');
  var panel = document.getElementById(tabId);
  if (btn) btn.classList.add('active');
  if (panel) panel.classList.add('tab-active');
}

function resetToFirstTab() {
  var firstVisible = document.querySelector('#agent-tabs .tab-btn:not([style*="display: none"])');
  if (firstVisible) switchTab(firstVisible.dataset.tab);
}

document.getElementById('agent-tabs').addEventListener('click', function(e) {
  var btn = e.target.closest('.tab-btn');
  if (btn) switchTab(btn.dataset.tab);
});

/* ── Theme toggle (v5) ─────────────────────────────── */
(function() {
  function currentTheme() {
    var t = document.documentElement.getAttribute('data-theme');
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function paint() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    var t = currentTheme();
    var sun = btn.querySelector('.ic-sun');
    var moon = btn.querySelector('.ic-moon');
    if (sun)  sun.style.display  = (t === 'dark') ? '' : 'none';
    if (moon) moon.style.display = (t === 'dark') ? 'none' : '';
  }
  document.addEventListener('click', function(e) {
    var btn = e.target.closest && e.target.closest('#theme-toggle');
    if (!btn) return;
    var next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('hiris-theme', next); } catch(e) {}
    paint();
  });
  paint();
})();

/* show version in chrome */
fetch('api/health').then(function(r){ return r.json(); }).then(function(d){
  var el = document.getElementById('hc-version');
  if (el && d.version) el.textContent = 'v' + d.version;
}).catch(function(){});
