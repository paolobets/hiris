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
// when multiple card instances are present on the same dashboard.
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

// ---------------------------------------------------------------------------
// Module-level ingress URL discovery
// The Supervisor assigns a random token (not the add-on slug) to the ingress
// path. This function reads hiris-ingress.json written by the add-on at startup.
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
    // Keep timeout active through the entire streaming lifecycle
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    try {
      const resp = await fetch(this._hirisUrl('api/chat'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${this._authToken()}`,
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
              if (evt.type === 'done') { assistantMsg.streaming = false; }
              if (evt.type === 'error') {
                assistantMsg.text = `Errore: ${evt.message}`;
                assistantMsg.streaming = false;
              }
            } catch {}
          }
        }
        // Stream closed — clear flag regardless of whether SSE 'done' event arrived
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
        },
        body: JSON.stringify({ enabled: !this._enabled }),
      });
      if (resp.ok) await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
    }
  }

  _statusColor() {
    return {
      idle: '#10b981', running: '#3b82f6', error: '#ef4444',
      unavailable: '#9ca3af',
    }[this._status] || '#9ca3af';
  }

  _iconHtml(size) {
    return `<img src="${_HIRIS_ICON_DATA}" width="${size}" height="${size}" style="border-radius:50%;display:block;flex-shrink:0" alt="HIRIS">`;
  }

  _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _render() {
    // Unconfigured state — no agent_id yet (card just added from picker)
    if (!this._agentId) {
      this._shadow.innerHTML = `
        <style>
          :host { display: block; }
          .card { background: var(--card-background-color,#fff); border-radius: 12px;
            overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
          .header { display: flex; align-items: center; gap: 8px;
            padding: 12px 16px; border-bottom: 1px solid var(--divider-color,#e0e0e0); }
          .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
          .unconfigured { padding: 32px 16px; text-align: center;
            display: flex; flex-direction: column; align-items: center; gap: 12px; }
          .unconfigured-title { font-size: 13px; font-weight: 600;
            color: var(--primary-text-color,#374151); }
          .unconfigured-sub { font-size: 12px; color: var(--secondary-text-color,#9ca3af); }
        </style>
        <div class="card">
          <div class="header">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <div class="unconfigured">
            <div style="opacity:.7">${this._iconHtml(40)}</div>
            <div>
              <div class="unconfigured-title">Card non configurata</div>
              <div class="unconfigured-sub">Clicca ✏️ per selezionare un agente</div>
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
      // assistant — show typing indicator when waiting for first token
      if (m.streaming && !m.text) {
        return `<div class="typing-row">
          <div class="avatar">${this._iconHtml(28)}</div>
          <div class="typing-bubble">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>`;
      }
      return `<div class="msg-row assistant">
        <div class="avatar">${this._iconHtml(28)}</div>
        <div class="msg-col">
          <div class="bubble">${text}${m.streaming ? '<span class="cursor">&#x258C;</span>' : ''}</div>
        </div>
      </div>`;
    }).join('');

    // Preserve any text the user typed before rebuilding the DOM
    const _savedInput = this._shadow.getElementById('inp')?.value ?? '';

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .card { background: var(--card-background-color,#fff); border-radius: 12px;
          overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
        .header { display: flex; align-items: center; justify-content: space-between;
          padding: 12px 16px; border-bottom: 1px solid var(--divider-color,#e0e0e0); }
        .header-left { display: flex; align-items: center; gap: 8px; }
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
        .toggle { cursor: pointer; font-size: 18px; background: none; border: none;
          padding: 0; line-height: 1; opacity: .9; }
        .toggle:hover { opacity: 1; }
        .budget-bar { height: 3px; background: var(--divider-color,#eee); }
        .budget-fill { height: 100%; width: ${pct}%; background: var(--primary-color,#3b82f6);
          transition: width .3s; }
        .budget-text { font-size: 11px; color: var(--secondary-text-color,#9ca3af);
          padding: 2px 16px 4px; }
        .messages { height: 220px; overflow-y: auto; padding: 12px 16px;
          display: flex; flex-direction: column; gap: 10px; }
        /* User message */
        .msg-row { display: flex; align-items: flex-end; gap: 8px; }
        .msg-row.user { align-self: flex-end; flex-direction: row-reverse; max-width: 82%; }
        .msg-row.assistant { align-self: flex-start; max-width: 82%; }
        .avatar { width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
          display: flex; align-items: center; justify-content: center; }
        .msg-col { display: flex; flex-direction: column; }
        .bubble { padding: 8px 12px; border-radius: 18px;
          font-size: 14px; line-height: 1.5; word-break: break-word; }
        .msg-row.user .bubble {
          background: var(--primary-color,#2563eb); color: #fff;
          border-radius: 18px 18px 4px 18px; }
        .msg-row.assistant .bubble {
          background: var(--card-background-color,#fff);
          color: var(--primary-text-color,#111);
          border: 1px solid var(--divider-color,#e5e7eb);
          border-radius: 18px 18px 18px 4px; }
        /* Typing indicator */
        .typing-row { display: flex; align-items: flex-end; gap: 8px; align-self: flex-start; }
        .typing-bubble {
          background: var(--card-background-color,#fff);
          border: 1px solid var(--divider-color,#e5e7eb);
          border-radius: 18px; border-bottom-left-radius: 4px;
          padding: 10px 14px; display: flex; gap: 4px; align-items: center; }
        .typing-dot { width: 6px; height: 6px; border-radius: 50%;
          background: #9ca3af; animation: bounce 1.2s ease-in-out infinite; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }
        /* Streaming cursor */
        .cursor { animation: blink 1s step-start infinite; }
        @keyframes blink { 50% { opacity: 0; } }
        .empty { color: var(--secondary-text-color,#aaa); text-align: center;
          padding-top: 60px; font-size: 13px; }
        .error-badge { padding: 8px 16px; color: var(--warning-color,#f59e0b);
          font-size: 12px; text-align: center; }
        .input-row { display: flex; gap: 8px; padding: 12px 16px; align-items: center;
          border-top: 1px solid var(--divider-color,#e0e0e0); }
        .input { flex: 1; padding: 8px 12px; border: 1px solid var(--divider-color,#e0e0e0);
          border-radius: 20px; font-size: 14px; outline: none; font-family: inherit;
          background: var(--secondary-background-color,#f9fafb);
          color: var(--primary-text-color,#111);
          transition: border-color .15s; }
        .input:focus { border-color: var(--primary-color,#3b82f6); }
        .send { width: 36px; height: 36px; background: var(--primary-color,#2563eb); color: #fff;
          border: none; border-radius: 50%; cursor: pointer; flex-shrink: 0;
          display: flex; align-items: center; justify-content: center;
          transition: background .15s; }
        .send:hover { opacity: .9; }
        .send:disabled { opacity: .45; cursor: default; }
        .send.loading svg { display: none; }
        .send.loading::after {
          content: ''; width: 14px; height: 14px;
          border: 2px solid rgba(255,255,255,0.35); border-top-color: #fff;
          border-radius: 50%; animation: spin 0.7s linear infinite; display: block;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .messages::-webkit-scrollbar { width: 3px; }
        .messages::-webkit-scrollbar-track { background: transparent; }
        .messages::-webkit-scrollbar-thumb { background: var(--divider-color,#e0e0e0); border-radius: 2px; }
      </style>
      <div class="card">
        <div class="header">
          <div class="header-left">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <button class="toggle" id="tog" title="${this._enabled ? 'Disabilita agente' : 'Abilita agente'}">
            ${this._enabled ? '&#x1F7E2;' : '&#x26AA;'}
          </button>
        </div>
        ${this._budgetLimitEur > 0 ? `
          <div class="budget-bar"><div class="budget-fill"></div></div>
          <div class="budget-text">&#x20AC;${this._budgetEur.toFixed(2)} / &#x20AC;${this._budgetLimitEur.toFixed(2)}</div>
        ` : ''}
        ${this._error ? `<div class="error-badge">${this._esc(this._error)}</div>` : ''}
        <div class="messages" id="msgs">
          ${msgs || '<div class="empty">Scrivi un messaggio per iniziare&#x2026;</div>'}
        </div>
        <div class="input-row">
          <input class="input" id="inp" type="text"
            placeholder="${this._loading ? 'Elaborazione…' : 'Scrivi un messaggio…'}"
            ${!this._enabled ? 'disabled' : ''} />
          <button class="send${this._loading ? ' loading' : ''}" id="snd"
            ${this._loading || !this._enabled ? 'disabled' : ''} title="${this._loading ? 'Elaborazione…' : 'Invia'}">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          </button>
        </div>
      </div>`;

    const inp = this._shadow.getElementById('inp');
    const snd = this._shadow.getElementById('snd');
    const tog = this._shadow.getElementById('tog');
    const msgsEl = this._shadow.getElementById('msgs');

    // Restore typed text preserved before innerHTML rebuild
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
    this._config = {};
    this._hass = null;
    this._agents = null;   // null = not yet loaded, 'loading' = in-flight, [] = loaded, 'error' = failed
  }

  connectedCallback() {
    this._render();
  }

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
        this._agents = Array.isArray(result) ? result : [];
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
      agentField = `<select disabled style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#f9fafb;color:#9ca3af;box-sizing:border-box">
        <option>Caricamento agenti…</option>
      </select>`;
    } else if (this._agents === 'error' || this._agents.length === 0) {
      agentField = `<input id="agentInput" type="text" value="${this._esc(agentId)}"
        placeholder="es. hiris-default"
        style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#fff;color:#111;box-sizing:border-box">`;
    } else {
      const options = this._agents.map(a => {
        const sel = a.id === agentId ? ' selected' : '';
        return `<option value="${this._esc(a.id)}"${sel}>${this._esc(a.name || a.id)} (${this._esc(a.id)})</option>`;
      }).join('');
      agentField = `<div style="position:relative">
        <select id="agentSelect" style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#fff;appearance:none;color:#111;box-sizing:border-box">
          ${options}
        </select>
        <div style="position:absolute;right:10px;top:50%;transform:translateY(-50%);pointer-events:none;color:#9ca3af;font-size:12px">▾</div>
      </div>`;
    }

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .editor { font-family: var(--paper-font-body1_-_font-family, sans-serif); }
        .editor-header { display: flex; align-items: center; gap: 10px;
          padding-bottom: 12px; border-bottom: 1px solid #e5e7eb; margin-bottom: 14px; }
        .editor-title { font-weight: 700; font-size: 14px; color: #111; }
        .editor-sub { font-size: 11px; color: #9ca3af; }
        .field { margin-bottom: 14px; }
        .field-label { font-size: 11px; font-weight: 600; color: #6b7280;
          text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
        .field-hint { font-size: 11px; color: #9ca3af; margin-top: 3px; }
      </style>
      <div class="editor">
        <div class="editor-header">
          <img src="${_HIRIS_ICON_DATA}" width="32" height="32"
            style="border-radius:50%;flex-shrink:0" alt="HIRIS">
          <div>
            <div class="editor-title">HIRIS Chat</div>
            <div class="editor-sub">Configurazione card</div>
          </div>
        </div>

        <div class="field">
          <div class="field-label">Agente</div>
          ${agentField}
          <div class="field-hint">Agente che risponde nella chat</div>
        </div>

        <div class="field">
          <div class="field-label">Titolo</div>
          <input id="titleInput" type="text" value="${this._esc(title)}"
            style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#fff;color:#111;box-sizing:border-box">
          <div class="field-hint">Mostrato nell'intestazione</div>
        </div>
      </div>`;

    const agentSelect = this._shadow.getElementById('agentSelect');
    const agentInput = this._shadow.getElementById('agentInput');
    const titleInput = this._shadow.getElementById('titleInput');

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

// Register in window.customCards so HA shows the card in the picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hiris-chat-card',
  name: 'HIRIS Chat',
  description: 'Chat con il tuo assistente smart home HIRIS',
  preview: false,
});
