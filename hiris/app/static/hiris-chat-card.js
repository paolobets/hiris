// hiris-chat-card.js — HA Lovelace custom card for HIRIS chat
// Served at: /local/hiris/hiris-chat-card.js (deployed automatically by add-on)
// Add to Lovelace resources if not auto-detected:
//   url: /local/hiris/hiris-chat-card.js
//   type: module
// Dashboard config:
//   type: custom:hiris-chat-card
//   agent_id: hiris-default
//   title: "Assistente Casa"
//   hiris_slug: hiris

const POLL_MS = 30_000;
const CHAT_TIMEOUT_MS = 30_000;

// HIRIS SVG icon inlined as a data URI to avoid Shadow DOM ID conflicts
const _HIRIS_ICON_DATA = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
  '<defs>' +
  '<radialGradient id="bg" cx="50%" cy="50%" r="50%">' +
  '<stop offset="0%" stop-color="#2a0a4e"/>' +
  '<stop offset="100%" stop-color="#0a0015"/>' +
  '</radialGradient>' +
  '<filter id="glow" x="-25%" y="-25%" width="150%" height="150%">' +
  '<feGaussianBlur in="SourceGraphic" stdDeviation="1.8" result="blur"/>' +
  '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>' +
  '</filter>' +
  '</defs>' +
  '<circle cx="50" cy="50" r="50" fill="url(#bg)"/>' +
  '<g transform="translate(50,50)" filter="url(#glow)">' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#c084fc"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#818cf8" transform="rotate(60)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#60a5fa" transform="rotate(120)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#22d3ee" transform="rotate(180)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#2dd4bf" transform="rotate(240)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#e879f9" transform="rotate(300)"/>' +
  '</g>' +
  '<circle cx="50" cy="50" r="4.5" fill="white"/>' +
  '</svg>'
);

// Iris design tokens embedded for Shadow DOM.
// Prefixed --i- to avoid collisions with HA's own CSS variables.
const IRIS_CSS = `
  :host {
    --i-surface:     oklch(1.00 0 0);
    --i-surface-2:   oklch(0.97 0.008 280);
    --i-surface-3:   oklch(0.94 0.012 280);
    --i-hover:       oklch(0.95 0.015 280);
    --i-border:      oklch(0.91 0.012 280);
    --i-border-2:    oklch(0.86 0.018 280);
    --i-text:        oklch(0.22 0.02 280);
    --i-text-2:      oklch(0.45 0.015 280);
    --i-text-3:      oklch(0.62 0.012 280);
    --i-accent:      oklch(0.66 0.20 280);
    --i-accent-ink:  oklch(0.32 0.18 280);
    --i-accent-tint: oklch(0.96 0.04 280);
    --i-accent-tint-2: oklch(0.92 0.07 280);
    --i-on-accent:   oklch(0.99 0 0);
    --i-iris-glow:   oklch(0.78 0.17 280 / 0.18);
    --i-p-violet:    #8b5cf6;
    --i-p-fuchsia:   #c026d3;
    --i-ok:          oklch(0.70 0.16 155);
    --i-ok-tint:     oklch(0.95 0.05 155);
    --i-err:         oklch(0.62 0.22 25);
    --i-err-tint:    oklch(0.95 0.05 25);
    --i-shadow-sm:   0 1px 2px oklch(0.20 0.05 280 / 0.06);
    --i-shadow:      0 4px 16px oklch(0.20 0.05 280 / 0.08);
    --i-r-sm:        6px;
    --i-r:           10px;
    --i-r-md:        14px;
    --i-font-sans:   "Geist", "Inter Tight", "Inter", system-ui, -apple-system, sans-serif;
    --i-font-mono:   "Geist Mono", "JetBrains Mono", "SF Mono", ui-monospace, monospace;
    display: block;
  }
  @media (prefers-color-scheme: dark) {
    :host {
      --i-surface:     oklch(0.205 0.022 280);
      --i-surface-2:   oklch(0.235 0.025 280);
      --i-surface-3:   oklch(0.275 0.028 280);
      --i-hover:       oklch(0.255 0.028 280);
      --i-border:      oklch(0.295 0.025 280);
      --i-border-2:    oklch(0.350 0.030 280);
      --i-text:        oklch(0.97 0.006 280);
      --i-text-2:      oklch(0.74 0.014 280);
      --i-text-3:      oklch(0.56 0.018 280);
      --i-accent:      oklch(0.78 0.17 280);
      --i-accent-ink:  oklch(0.86 0.14 280);
      --i-accent-tint: oklch(0.30 0.10 280);
      --i-accent-tint-2: oklch(0.36 0.12 280);
      --i-on-accent:   oklch(0.16 0.04 280);
      --i-iris-glow:   oklch(0.78 0.17 280 / 0.40);
      --i-p-violet:    #c084fc;
      --i-p-fuchsia:   #e879f9;
      --i-ok-tint:     oklch(0.30 0.08 155);
      --i-err-tint:    oklch(0.30 0.09 25);
      --i-shadow-sm:   0 1px 2px oklch(0 0 0 / 0.32);
      --i-shadow:      0 8px 24px oklch(0 0 0 / 0.32);
    }
  }
  *, *::before, *::after { box-sizing: border-box; }
`;

// ---------------------------------------------------------------------------
// Module-level ingress URL discovery
// ---------------------------------------------------------------------------
let _cachedIngressBase;

async function _discoverIngressBase(slug) {
  if (_cachedIngressBase !== undefined) return;
  _cachedIngressBase = null;
  try {
    const r = await fetch(`/local/${slug}/hiris-ingress.json`);
    if (r.ok) {
      const d = await r.json();
      const url = d?.ingress_url;
      if (typeof url === 'string' && url) {
        _cachedIngressBase = url.endsWith('/') ? url : url + '/';
      }
    }
  } catch {}
}

// ---------------------------------------------------------------------------
// HirisCard — main card element
// ---------------------------------------------------------------------------

class HirisCard extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    // Persistent font link — survives container innerHTML resets
    const fontLink = document.createElement('link');
    fontLink.rel = 'stylesheet';
    fontLink.href = 'https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap';
    this._shadow.appendChild(fontLink);
    // Render target (allows font link to persist across renders)
    this._container = document.createElement('div');
    this._shadow.appendChild(this._container);

    this._agentId = null;
    this._slug = 'hiris';
    this._title = 'HIRIS Chat';
    this._hass = null;
    this._status = 'idle';
    this._enabled = true;
    this._budgetEur = 0;
    this._budgetLimitEur = 0;
    this._messages = [];
    this._polling = null;
    this._loading = false;
    this._error = null;
  }

  static getConfigElement() { return document.createElement('hiris-chat-card-editor'); }
  static getStubConfig() {
    return { agent_id: 'hiris-default', title: 'HIRIS Chat', hiris_slug: 'hiris' };
  }

  setConfig(config) {
    this._agentId = config.agent_id || null;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const statusKey = `sensor.hiris_${this._agentId}_status`;
    if (hass.states[statusKey]) {
      this._status = hass.states[statusKey].state || 'idle';
      const budgetKey = `sensor.hiris_${this._agentId}_budget_eur`;
      this._budgetEur = parseFloat(hass.states[budgetKey]?.state || '0');
      const switchKey = `switch.hiris_${this._agentId}_enabled`;
      this._enabled = hass.states[switchKey]?.state !== 'off';
      this._render();
    } else if (this._agentId && !this._polling) {
      this._startPolling();
    }
  }

  getCardSize() { return 6; }

  connectedCallback() {
    this._render();
    if (this._agentId && !this._polling) this._startPolling();
  }

  disconnectedCallback() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }

  _startPolling() {
    this._fetchStatus();
    this._polling = setInterval(() => this._fetchStatus(), POLL_MS);
  }

  _hirisUrl(path) {
    const base = _cachedIngressBase
      ?? `${this._hass?.connection?.options?.hassUrl || ''}/api/hassio_ingress/${this._slug}/`;
    return `${base}${path}`;
  }

  _authToken() {
    const auth = this._hass?.connection?.options?.auth;
    return auth?.accessToken ?? auth?.data?.access_token ?? '';
  }

  async _fetchStatus() {
    if (!this._hass) return;
    await _discoverIngressBase(this._slug);
    try {
      const resp = await fetch(this._hirisUrl('api/agents'), {
        headers: { 'Authorization': `Bearer ${this._authToken()}` },
      });
      if (!resp.ok) {
        this._error = `⚠ HIRIS non disponibile (${resp.status})`;
      } else {
        const agents = await resp.json();
        const agent = Array.isArray(agents) && agents.find(a => a.id === this._agentId);
        if (agent) {
          this._status = agent.status || 'idle';
          this._enabled = !!agent.enabled;
          this._budgetEur = agent.budget_eur || 0;
          this._budgetLimitEur = agent.budget_limit_eur || 0;
          this._error = null;
        } else {
          this._error = 'Agente non configurato';
        }
      }
    } catch {
      this._error = '⚠ HIRIS non disponibile';
    }
    this._render();
  }

  async _sendMessage(text) {
    if (!text.trim() || this._loading) return;
    this._loading = true;
    this._messages.push({ role: 'user', text });
    const assistantMsg = { role: 'assistant', text: '', streaming: true };
    this._messages.push(assistantMsg);
    this._render();

    await _discoverIngressBase(this._slug);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    try {
      const resp = await fetch(this._hirisUrl('api/chat'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${this._authToken()}`,
          'X-Requested-With': 'fetch',
        },
        body: JSON.stringify({ message: text, agent_id: this._agentId, stream: true }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const d = await resp.json(); msg = d.error || msg; } catch {}
        throw new Error(msg);
      }

      const ct = resp.headers.get('Content-Type') || '';
      if (ct.includes('text/event-stream')) {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'token') { assistantMsg.text += evt.text; this._render(); }
              if (evt.type === 'discard_collected') { assistantMsg.text = ''; this._render(); }
              if (evt.type === 'done') { assistantMsg.streaming = false; }
              if (evt.type === 'error') {
                assistantMsg.text = `Errore: ${evt.message}`;
                assistantMsg.streaming = false;
              }
            } catch {}
          }
        }
        assistantMsg.streaming = false;
      } else {
        const data = await resp.json();
        assistantMsg.text = data.response || 'Nessuna risposta';
        assistantMsg.streaming = false;
      }
    } catch (e) {
      assistantMsg.text = e.name === 'AbortError'
        ? 'Timeout — riprova'
        : `Errore: ${e.message}`;
      assistantMsg.streaming = false;
    } finally {
      clearTimeout(timeout);
      this._loading = false;
      this._render();
      await this._fetchStatus();
    }
  }

  async _toggleAgent() {
    if (!this._hass) return;
    await _discoverIngressBase(this._slug);
    try {
      const resp = await fetch(this._hirisUrl(`api/agents/${this._agentId}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this._authToken()}`,
          'X-Requested-With': 'fetch',
        },
        body: JSON.stringify({ enabled: !this._enabled }),
      });
      if (resp.ok) await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
    }
  }

  _iconHtml(size) {
    return `<img src="${_HIRIS_ICON_DATA}" width="${size}" height="${size}" style="border-radius:50%;display:block;flex-shrink:0" alt="HIRIS">`;
  }

  _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _statusClass() {
    return { idle: 'idle', running: 'running', error: 'error', unavailable: 'offline' }[this._status] ?? 'offline';
  }

  _statusLabel() {
    return { idle: 'online', running: 'in esecuzione', error: 'errore', unavailable: 'offline' }[this._status] ?? this._status;
  }

  _render() {
    // Unconfigured state
    if (!this._agentId) {
      this._container.innerHTML = `
        <style>
          ${IRIS_CSS}
          .card {
            background: var(--i-surface);
            border: 1px solid var(--i-border);
            border-radius: var(--i-r-md);
            overflow: hidden;
            box-shadow: var(--ha-card-box-shadow, var(--i-shadow-sm));
            font-family: var(--i-font-sans);
            color: var(--i-text);
            -webkit-font-smoothing: antialiased;
          }
          .header {
            display: flex; align-items: center; gap: 8px;
            padding: 12px 16px;
            border-bottom: 1px solid var(--i-border);
          }
          .title { font-size: 14px; font-weight: 600; letter-spacing: -0.01em; color: var(--i-text); }
          .unconfigured {
            padding: 36px 20px;
            display: flex; flex-direction: column; align-items: center; gap: 10px;
            text-align: center;
          }
          .unc-title { font-size: 13px; font-weight: 600; color: var(--i-text); }
          .unc-sub { font-size: 12px; color: var(--i-text-3); }
        </style>
        <div class="card">
          <div class="header">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <div class="unconfigured">
            <div style="opacity:.7">${this._iconHtml(38)}</div>
            <div>
              <div class="unc-title">Card non configurata</div>
              <div class="unc-sub">Clicca ✏️ per selezionare un agente</div>
            </div>
          </div>
        </div>`;
      return;
    }

    const pct = this._budgetLimitEur > 0
      ? Math.min(100, (this._budgetEur / this._budgetLimitEur) * 100)
      : 0;

    const msgs = this._messages.map(m => {
      const text = this._esc(m.text).replace(/\n/g, '<br>');
      if (m.role === 'user') {
        return `<div class="msg-row user">
          <div class="msg-col"><div class="bubble">${text}</div></div>
        </div>`;
      }
      if (m.streaming && !m.text) {
        return `<div class="typing-row">
          <div class="avatar">${this._iconHtml(26)}</div>
          <div class="typing-bubble">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>`;
      }
      return `<div class="msg-row assistant">
        <div class="avatar">${this._iconHtml(26)}</div>
        <div class="msg-col">
          <div class="bubble">${text}${m.streaming ? '<span class="cursor">&#x258C;</span>' : ''}</div>
        </div>
      </div>`;
    }).join('');

    const _savedInput = this._container.querySelector('#inp')?.value ?? '';

    this._container.innerHTML = `
      <style>
        ${IRIS_CSS}
        .card {
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-md);
          overflow: hidden;
          box-shadow: var(--ha-card-box-shadow, var(--i-shadow-sm));
          font-family: var(--i-font-sans);
          font-size: 14px;
          color: var(--i-text);
          -webkit-font-smoothing: antialiased;
        }
        /* ── Header ── */
        .header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 16px;
          border-bottom: 1px solid var(--i-border);
          position: relative;
        }
        .header::before {
          content: ''; position: absolute; inset: 0;
          background: radial-gradient(ellipse 80% 100% at 0% 0%, var(--i-iris-glow), transparent 60%);
          pointer-events: none;
          border-radius: var(--i-r-md) var(--i-r-md) 0 0;
        }
        .header > * { position: relative; z-index: 1; }
        .header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
        .header-left img {
          filter: drop-shadow(0 0 10px var(--i-iris-glow));
          animation: iris-breathe 6s ease-in-out infinite;
        }
        @keyframes iris-breathe {
          0%, 100% { transform: scale(1); }
          50%      { transform: scale(1.04); }
        }
        @media (prefers-reduced-motion: reduce) {
          .header-left img,
          .typing-dots span,
          .spinner { animation: none !important; }
        }
        .title {
          font-size: 14.5px; font-weight: 600; letter-spacing: -0.012em;
          color: var(--i-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .header-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .status-pill {
          display: inline-flex; align-items: center; gap: 5px;
          padding: 3px 9px; border-radius: 999px;
          font-size: 10.5px; font-weight: 500;
          font-family: var(--i-font-mono);
          background: var(--i-ok-tint); color: var(--i-ok);
        }
        .status-pill::before {
          content: ""; width: 5px; height: 5px; border-radius: 50%; background: currentColor;
        }
        .status-pill.running  { background: var(--i-accent-tint); color: var(--i-accent-ink); }
        .status-pill.error,
        .status-pill.offline  { background: var(--i-err-tint); color: var(--i-err); }
        .toggle {
          cursor: pointer; background: none; border: none; padding: 0;
          width: 26px; height: 26px; display: grid; place-items: center;
          border-radius: var(--i-r-sm); color: var(--i-text-3); font-size: 15px;
          transition: background 0.15s;
        }
        .toggle:hover { background: var(--i-hover); color: var(--i-text); }
        /* ── Budget ── */
        .budget-wrap { padding: 6px 16px 2px; }
        .budget-bar {
          height: 3px; background: var(--i-surface-3);
          border-radius: 2px; overflow: hidden;
        }
        .budget-fill {
          height: 100%; width: ${pct}%; background: var(--i-accent);
          border-radius: 2px; transition: width .4s;
        }
        .budget-text {
          font-size: 10.5px; font-family: var(--i-font-mono);
          color: var(--i-text-3); margin-top: 4px;
          font-variant-numeric: tabular-nums;
        }
        /* ── Error badge ── */
        .error-badge {
          padding: 5px 16px;
          font-size: 11.5px; font-family: var(--i-font-mono);
          color: var(--i-err); background: var(--i-err-tint);
          border-bottom: 1px solid var(--i-border);
          text-align: center;
        }
        /* ── Messages ── */
        .messages {
          height: 220px; overflow-y: auto;
          padding: 12px 16px;
          display: flex; flex-direction: column; gap: 10px;
          background: var(--i-surface);
        }
        .messages::-webkit-scrollbar { width: 4px; }
        .messages::-webkit-scrollbar-track { background: transparent; }
        .messages::-webkit-scrollbar-thumb { background: var(--i-border); border-radius: 2px; }
        .empty {
          flex: 1; display: flex; align-items: center; justify-content: center;
          color: var(--i-text-3); font-size: 13px; text-align: center; padding: 24px 0;
        }
        /* ── Bubbles — matches index.html ── */
        .msg-row { display: flex; gap: 8px; align-items: flex-start; }
        .msg-row.user { justify-content: flex-end; }
        .avatar { width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0; overflow: hidden; }
        .msg-col { display: flex; flex-direction: column; max-width: 80%; }
        .msg-row.user .msg-col { align-items: flex-end; }
        .bubble {
          padding: 8px 12px;
          border-radius: var(--i-r-md);
          font-size: 13.5px; line-height: 1.5; word-break: break-word;
        }
        .msg-row.assistant .bubble {
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-top-left-radius: 4px;
          color: var(--i-text);
        }
        .msg-row.user .bubble {
          background: var(--i-accent-tint);
          color: var(--i-text);
          border: 1px solid var(--i-accent-tint-2);
          border-top-right-radius: 4px;
        }
        /* ── Typing indicator ── */
        .typing-row { display: flex; gap: 8px; align-items: flex-start; }
        .typing-bubble {
          display: inline-flex; gap: 4px; align-items: center;
          padding: 10px 14px;
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-md); border-top-left-radius: 4px;
        }
        .typing-dot {
          width: 5px; height: 5px; border-radius: 50%;
          background: var(--i-text-3);
          animation: bounce 1.2s ease-in-out infinite;
        }
        .typing-dot:nth-child(2) { animation-delay: 0.15s; }
        .typing-dot:nth-child(3) { animation-delay: 0.30s; }
        @keyframes bounce {
          0%,60%,100% { transform: translateY(0); opacity: 0.4; }
          30%         { transform: translateY(-5px); opacity: 1; }
        }
        .cursor { animation: blink 1s step-start infinite; }
        @keyframes blink { 50% { opacity: 0; } }
        /* ── Composer — matches index.html #input-inner ── */
        .input-row {
          padding: 8px 12px 12px;
          border-top: 1px solid var(--i-border);
          background: var(--i-surface);
        }
        .input-inner {
          display: flex; align-items: center; gap: 6px;
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-md);
          padding: 5px 5px 5px 12px;
          transition: border-color 0.15s, box-shadow 0.15s;
        }
        .input-inner:focus-within {
          border-color: var(--i-accent);
          box-shadow: 0 0 0 3px var(--i-accent-tint);
        }
        .input {
          flex: 1; border: 0; background: transparent; outline: none;
          padding: 4px 0; font-size: 13.5px; line-height: 1.5;
          font-family: var(--i-font-sans); color: var(--i-text);
        }
        .input::placeholder { color: var(--i-text-3); }
        .input:disabled { opacity: 0.5; cursor: not-allowed; }
        .send {
          width: 32px; height: 32px; flex-shrink: 0;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--i-p-violet), var(--i-p-fuchsia));
          color: white;
          border: none; cursor: pointer;
          display: grid; place-items: center;
          transition: transform 0.15s, box-shadow 0.15s;
          box-shadow: 0 4px 12px var(--i-iris-glow);
        }
        .send:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 16px var(--i-iris-glow); }
        .send:active:not(:disabled) { transform: scale(0.92); }
        .send:disabled { background: var(--i-surface-3); color: var(--i-text-3); cursor: not-allowed; box-shadow: none; }
        .send.loading { background: var(--i-surface-3); cursor: default; box-shadow: none; }
        .send.loading svg { display: none; }
        .send.loading::after {
          content: ''; width: 12px; height: 12px;
          border: 2px solid var(--i-text-3); border-top-color: var(--i-accent);
          border-radius: 50%; animation: spin 0.7s linear infinite; display: block;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
      <div class="card">
        <div class="header">
          <div class="header-left">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <div class="header-right">
            <div class="status-pill ${this._statusClass()}">${this._statusLabel()}</div>
            <button class="toggle" id="tog" title="${this._enabled ? 'Disabilita agente' : 'Abilita agente'}">
              ${this._enabled ? '&#x1F7E2;' : '&#x26AA;'}
            </button>
          </div>
        </div>
        ${this._budgetLimitEur > 0 ? `
          <div class="budget-wrap">
            <div class="budget-bar"><div class="budget-fill"></div></div>
            <div class="budget-text">&#x20AC;${this._budgetEur.toFixed(2)} / &#x20AC;${this._budgetLimitEur.toFixed(2)}</div>
          </div>
        ` : ''}
        ${this._error ? `<div class="error-badge">${this._esc(this._error)}</div>` : ''}
        <div class="messages" id="msgs">
          ${msgs || '<div class="empty">Scrivi un messaggio per iniziare…</div>'}
        </div>
        <div class="input-row">
          <div class="input-inner">
            <input class="input" id="inp" type="text"
              placeholder="${this._loading ? 'Elaborazione…' : 'Scrivi un messaggio…'}"
              ${!this._enabled ? 'disabled' : ''}>
            <button class="send${this._loading ? ' loading' : ''}" id="snd"
              ${this._loading || !this._enabled ? 'disabled' : ''} title="${this._loading ? 'Elaborazione…' : 'Invia'}">
              <svg viewBox="0 0 24 24" width="14" height="14">
                <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>`;

    const inp = this._container.querySelector('#inp');
    const snd = this._container.querySelector('#snd');
    const tog = this._container.querySelector('#tog');
    const msgsEl = this._container.querySelector('#msgs');

    if (inp && _savedInput) inp.value = _savedInput;
    if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
    if (snd) snd.onclick = () => {
      const t = inp?.value.trim();
      if (t) { inp.value = ''; this._sendMessage(t); }
    };
    if (inp) inp.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); snd?.click(); }
    };
    if (tog) tog.onclick = () => this._toggleAgent();
  }
}

// ---------------------------------------------------------------------------
// HirisChatCardEditor — visual config editor shown in the HA card picker
// ---------------------------------------------------------------------------

class HirisChatCardEditor extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    const fontLink = document.createElement('link');
    fontLink.rel = 'stylesheet';
    fontLink.href = 'https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap';
    this._shadow.appendChild(fontLink);
    this._container = document.createElement('div');
    this._shadow.appendChild(this._container);

    this._config = {};
    this._hass = null;
    this._agents = null;
  }

  connectedCallback() { this._render(); }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._agents === null) this._loadAgents();
  }

  async _loadAgents() {
    this._agents = 'loading';
    const slug = this._config.hiris_slug || 'hiris';
    await _discoverIngressBase(slug);
    const base = _cachedIngressBase
      ?? `${this._hass?.connection?.options?.hassUrl || ''}/api/hassio_ingress/${slug}/`;
    const auth = this._hass?.connection?.options?.auth;
    const token = auth?.accessToken ?? auth?.data?.access_token ?? '';
    try {
      const resp = await fetch(`${base}api/agents`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (resp.ok) {
        const result = await resp.json();
        // Only chat-type agents are compatible with this card
        this._agents = Array.isArray(result) ? result.filter(a => a.type === 'chat') : [];
      } else {
        this._agents = 'error';
      }
    } catch {
      this._agents = 'error';
    }
    this._render();
  }

  _fireConfigChanged() {
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: { ...this._config } },
      bubbles: true,
      composed: true,
    }));
  }

  _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _render() {
    const agentId = this._config.agent_id || '';
    const title = this._config.title || 'HIRIS Chat';

    let agentField;
    if (this._agents === null || this._agents === 'loading') {
      agentField = `<div class="field-loading">Caricamento agenti…</div>`;
    } else if (this._agents === 'error' || this._agents.length === 0) {
      agentField = `<input id="agentInput" class="field-input" type="text"
        value="${this._esc(agentId)}" placeholder="es. hiris-default">`;
    } else {
      const options = this._agents.map(a => {
        const sel = a.id === agentId ? ' selected' : '';
        return `<option value="${this._esc(a.id)}"${sel}>${this._esc(a.name || a.id)} (${this._esc(a.id)})</option>`;
      }).join('');
      agentField = `<div class="select-wrap">
        <select id="agentSelect" class="field-select">
          ${options}
        </select>
        <span class="select-arrow">▾</span>
      </div>`;
    }

    this._container.innerHTML = `
      <style>
        ${IRIS_CSS}
        .editor {
          font-family: var(--i-font-sans);
          font-size: 13px;
          color: var(--i-text);
          -webkit-font-smoothing: antialiased;
        }
        .editor-header {
          display: flex; align-items: center; gap: 10px;
          padding-bottom: 14px;
          border-bottom: 1px solid var(--i-border);
          margin-bottom: 16px;
        }
        .editor-title { font-size: 14px; font-weight: 600; color: var(--i-text); }
        .editor-sub { font-size: 11px; color: var(--i-text-3); font-family: var(--i-font-mono); margin-top: 1px; }
        .field { margin-bottom: 14px; }
        .field-label {
          font-size: 11px; font-weight: 600; font-family: var(--i-font-mono);
          text-transform: uppercase; letter-spacing: 0.06em;
          color: var(--i-text-3); margin-bottom: 6px;
        }
        .field-hint { font-size: 11px; color: var(--i-text-3); margin-top: 4px; }
        .field-loading {
          padding: 9px 12px;
          background: var(--i-surface-2);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-sm);
          font-size: 12.5px; color: var(--i-text-3);
          font-family: var(--i-font-mono);
        }
        .field-input, .field-select {
          width: 100%;
          padding: 8px 12px;
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-sm);
          font-size: 13px; font-family: var(--i-font-sans);
          color: var(--i-text);
          outline: none;
          transition: border-color 0.15s, box-shadow 0.15s;
          box-sizing: border-box;
          appearance: none;
        }
        .field-input:focus, .field-select:focus {
          border-color: var(--i-accent);
          box-shadow: 0 0 0 3px var(--i-accent-tint);
        }
        .select-wrap { position: relative; }
        .select-arrow {
          position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
          pointer-events: none; color: var(--i-text-3); font-size: 11px;
        }
      </style>
      <div class="editor">
        <div class="editor-header">
          <img src="${_HIRIS_ICON_DATA}" width="30" height="30"
            style="border-radius:50%;flex-shrink:0" alt="HIRIS">
          <div>
            <div class="editor-title">HIRIS Chat</div>
            <div class="editor-sub">configurazione card</div>
          </div>
        </div>

        <div class="field">
          <div class="field-label">Agente</div>
          ${agentField}
          <div class="field-hint">Solo agenti di tipo Chat</div>
        </div>

        <div class="field">
          <div class="field-label">Titolo</div>
          <input id="titleInput" class="field-input" type="text"
            value="${this._esc(title)}">
          <div class="field-hint">Mostrato nell'intestazione della card</div>
        </div>
      </div>`;

    const agentSelect = this._container.querySelector('#agentSelect');
    const agentInput  = this._container.querySelector('#agentInput');
    const titleInput  = this._container.querySelector('#titleInput');

    if (agentSelect) {
      agentSelect.onchange = (e) => {
        this._config = { ...this._config, agent_id: e.target.value };
        this._fireConfigChanged();
      };
    }
    if (agentInput) {
      agentInput.oninput = (e) => {
        this._config = { ...this._config, agent_id: e.target.value };
        this._fireConfigChanged();
      };
    }
    if (titleInput) {
      titleInput.oninput = (e) => {
        this._config = { ...this._config, title: e.target.value };
        this._fireConfigChanged();
      };
    }
  }
}

customElements.define('hiris-chat-card-editor', HirisChatCardEditor);
customElements.define('hiris-chat-card', HirisCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hiris-chat-card',
  name: 'HIRIS Chat',
  description: 'Chat con il tuo assistente smart home HIRIS',
  preview: false,
});
