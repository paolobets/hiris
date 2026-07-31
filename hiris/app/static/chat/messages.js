/* HIRIS · Chat page · message rendering (SP-4 Fase B Task 8)
   Bubble rendering, inline markdown-lite formatting, tool-call debug chips,
   typing indicator. Uses the shared esc() from config/api.js (the page's
   private copy was removed by this rebuild -- see task-8-report.md). */
(function() {
  var state = window.HirisChatState;

  function nowHHMM() {
    return new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  }

  function formatContent(text) {
    return esc(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code style="font-family:var(--font-mono);font-size:12.5px;background:var(--surface-2);padding:1px 5px;border-radius:4px;border:1px solid var(--border)">$1</code>')
      .replace(/\n/g, '<br>');
  }

  function appendMsg(role, text) {
    if (!state.hasMessages) { state.els.welcome.style.display = 'none'; state.hasMessages = true; }
    var row = document.createElement('div');
    row.className = 'msg-row ' + role;
    var time = nowHHMM();
    var content = formatContent(text);
    if (role === 'assistant') {
      row.innerHTML =
        '<div class="avatar">' + state.HIRIS_AVATAR + '</div>' +
        '<div class="msg-col"><div class="bubble">' + content + '</div><div class="msg-time">' + time + '</div></div>';
    } else {
      row.innerHTML =
        '<div class="msg-col"><div class="bubble">' + content + '</div><div class="msg-time">' + time + '</div></div>' +
        '<div class="avatar user">io</div>';
    }
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
    return row;
  }

  function updateBubble(row, text) {
    if (!row) return;
    /* Se era una bolla "in elaborazione" (showThinking) ferma il timer che scorre
       e togli lo stile animato prima di scrivere la risposta reale. */
    if (row._thinkingTimer) { clearInterval(row._thinkingTimer); row._thinkingTimer = null; }
    var bubble = row.querySelector('.bubble');
    if (bubble) { bubble.classList.remove('thinking-live'); bubble.innerHTML = formatContent(text); }
    var timeEl = row.querySelector('.msg-time');
    if (timeEl && !timeEl.textContent) timeEl.textContent = nowHHMM();
  }

  function appendDebug(tools) {
    var row = document.createElement('div');
    row.className = 'debug-row';
    /* Render tool calls as inline mono chips. Click to expand/collapse the args. */
    var chips = tools.map(function(t) {
      // Defensive: never let a malformed debug payload throw here -- an
      // exception would be swallowed by sendMessage()'s catch and
      // mislabeled as a connection error, AFTER the answer already rendered.
      if (!t || typeof t !== 'object') return '';
      var inp = JSON.stringify(t.input !== undefined && t.input !== null ? t.input : {});
      return '<button class="tool-chip" data-args="' + esc(inp) + '" type="button">'
           + '<svg viewBox="0 0 24 24" class="tc-ic" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
           + '<span class="tc-name">' + esc(t.tool || '') + '</span>'
           + '</button>';
    }).filter(Boolean).join('');
    row.innerHTML = '<div class="tool-chips">' + chips + '</div><div class="tool-args" style="display:none"></div>';
    /* Toggle args panel on chip click */
    row.querySelectorAll('.tool-chip').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var panel = row.querySelector('.tool-args');
        var args = btn.getAttribute('data-args');
        var name = btn.querySelector('.tc-name').textContent;
        var open = panel.dataset.openName === name && panel.style.display !== 'none';
        if (open) {
          panel.style.display = 'none';
          panel.dataset.openName = '';
        } else {
          panel.innerHTML = '<code><b>' + esc(name) + '</b>(' + esc(args) + ')</code>';
          panel.style.display = '';
          panel.dataset.openName = name;
        }
      });
    });
    state.els.messages.appendChild(row);
  }

  function showTyping() {
    /* Indicatore "sta elaborando" stile code/terminale (issue #3): un prompt col
       caret lampeggiante + barrette monospace che scorrono come codice in
       scrittura. Contenuto statico (nessun input utente) -> innerHTML sicuro. */
    var row = document.createElement('div');
    row.className = 'typing-row';
    row.id = 'typing-indicator';
    row.innerHTML =
      '<div class="avatar">' + state.HIRIS_AVATAR + '</div>' +
      '<div class="thinking-code" role="status" aria-label="HIRIS sta elaborando">' +
        '<span class="tk-prompt">&rsaquo;</span>' +
        '<span class="tk-stream"><i></i><i></i><i></i><i></i><i></i></span>' +
        '<span class="tk-label">elaboro</span>' +
      '</div>';
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
    return row;
  }

  function showThinking() {
    /* Placeholder per la risposta via abbonamento (202): invece del vecchio testo
       "HIRIS sta pensando…", il LOGO HIRIS che pulsa + label nei colori del logo +
       un timer che scorre, cosi' si vede che NON e' bloccato. Contenuto statico
       (nessun input utente) -> innerHTML sicuro. updateBubble() ferma il timer e
       sostituisce col testo quando la risposta arriva. */
    if (!state.hasMessages) { state.els.welcome.style.display = 'none'; state.hasMessages = true; }
    var row = document.createElement('div');
    row.className = 'msg-row assistant';
    row.innerHTML =
      '<div class="avatar thinking-logo">' + state.HIRIS_AVATAR + '</div>' +
      '<div class="msg-col"><div class="bubble thinking-live">' +
        '<div class="tl-top">' +
          '<span class="tl-label">HIRIS sta elaborando</span>' +
          '<span class="tl-dots"><i></i><i></i><i></i></span>' +
        '</div>' +
        '<div class="thinking-timer">0:00</div>' +
      '</div><div class="msg-time"></div></div>';
    state.els.messages.appendChild(row);
    state.els.messages.scrollTop = state.els.messages.scrollHeight;
    var start = Date.now();
    var timerEl = row.querySelector('.thinking-timer');
    row._thinkingTimer = setInterval(function() {
      var s = Math.floor((Date.now() - start) / 1000);
      var mm = Math.floor(s / 60);
      var ss = s % 60;
      if (timerEl) timerEl.textContent = mm + ':' + (ss < 10 ? '0' + ss : ss);
    }, 1000);
    return row;
  }

  window.HirisChatMessages = {
    appendMsg: appendMsg,
    updateBubble: updateBubble,
    appendDebug: appendDebug,
    showTyping: showTyping,
    showThinking: showThinking,
  };
})();
