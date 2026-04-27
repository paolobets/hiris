// hiris-chat-card.js — HA Lovelace custom card for HIRIS chat
// Served via /local/hiris/hiris-chat-card.js (auto-deployed by the add-on to /homeassistant/www/).
// For YAML-mode HA, add manually:
//   lovelace:
//     resources:
//       - url: /local/hiris/hiris-chat-card.js
//         type: module
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
    if (!config) throw new Error('Invalid configuration');
    const newAgentId = config.agent_id || null;
    const agentChanged = newAgentId !== this._agentId;
    this._agentId = newAgentId;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    if (agentChanged) {
      this._messages = [];
      this._status = 'idle';
      this._error = null;
      if (this._polling) { clearInterval(this._polling); this._polling = null; }
      if (this._agentId && this.isConnected) this._startPolling();
    }
    this._render();
  }

  set hass(hass) {
    if (!hass || !hass.states) return;
    this._hass = hass;
    if (!this._agentId) return;
    // Phase 2: auto-detect MQTT entities pushed by MQTTPublisher
    const statusKey = `sensor.hiris_${this._agentId}_status`;
    if (hass.states[statusKey]) {
      this._status = hass.states[statusKey].state || 'idle';
      const budgetKey = `sensor.hiris_${this._agentId}_budget_eur`;
      const rawBudget = parseFloat(hass.states[budgetKey]?.state);
      this._budgetEur = Number.isFinite(rawBudget) ? rawBudget : 0;
      const switchKey = `switch.hiris_${this._agentId}_enabled`;
      this._enabled = hass.states[switchKey]?.state !== 'off';
      if (this._shadow.querySelector('.card')) this._patchStatus();
      else this._render();
    } else if (this.isConnected && !this._polling) {
      this._startPolling();
    }
  }

  getCardSize() { return this._agentId ? 6 : 2; }

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

  async _fetchStatus() {
    if (!this._hass) return;
    try {
      const resp = await fetch(this._hirisUrl('api/agents'), {
        headers: { 'Authorization': `Bearer ${this._authToken()}` },
      });
      if (!resp.ok) { this._error = `⚠ HIRIS non disponibile (${resp.status})`; }
      else {
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
    } catch (e) {
      this._error = '⚠ HIRIS non disponibile';
    }
    // Patch only the status area to preserve input focus and typed text
    if (this._shadow.querySelector('.card') && !this._loading) this._patchStatus();
    else this._render();
  }

  _patchStatus() {
    const color = this._statusColor();
    const dot = this._shadow.querySelector('.dot');
    if (dot) dot.style.background = color;
    const statusText = this._shadow.querySelector('.status-text');
    if (statusText) statusText.textContent = this._status;
    const tog = this._shadow.getElementById('tog');
    if (tog) {
      tog.title = this._enabled ? 'Disabilita' : 'Abilita';
      tog.innerHTML = this._enabled ? '&#x1F7E2;' : '&#x26AA;';
    }
    const card = this._shadow.querySelector('.card');
    let badge = card?.querySelector('.error-badge');
    if (this._error) {
      if (!badge) {
        badge = document.createElement('div');
        badge.className = 'error-badge';
        const msgs = this._shadow.getElementById('msgs');
        if (card && msgs) card.insertBefore(badge, msgs);
      }
      badge.textContent = this._error;
    } else if (badge) {
      badge.remove();
    }
    const snd = this._shadow.getElementById('snd');
    if (snd) snd.disabled = this._loading || !this._enabled;
    const inp = this._shadow.getElementById('inp');
    if (inp) inp.disabled = !this._enabled;
  }

  async _sendMessage(text) {
    if (!text.trim() || this._loading) return;
    this._loading = true;
    this._messages.push({ role: 'user', text });
    const assistantMsg = { role: 'assistant', text: '', streaming: true };
    this._messages.push(assistantMsg);
    this._render();

    try {
      if (!this._hass) { this._loading = false; this._render(); return; }
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

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
      clearTimeout(timeout);

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
      this._loading = false;
      this._render();
      await this._fetchStatus();
    }
  }

  async _toggleAgent() {
    if (!this._hass) return;
    try {
      await fetch(this._hirisUrl(`api/agents/${this._agentId}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this._authToken()}`,
        },
        body: JSON.stringify({ enabled: !this._enabled }),
      });
      await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
    }
  }

  _hirisUrl(path) {
    const base = this._hass?.connection?.options?.hassUrl || '';
    return `${base}/api/hassio_ingress/${this._slug}/${path}`;
  }

  _authToken() {
    const auth = this._hass?.connection?.options?.auth;
    return auth?.accessToken ?? auth?.data?.access_token ?? '';
  }

  _statusColor() {
    return {
      idle: '#4caf50', running: '#2196f3', error: '#f44336',
      unavailable: '#9e9e9e',
    }[this._status] || '#9e9e9e';
  }

  _iconHtml(size) {
    return `<img src="${_HIRIS_ICON_DATA}" width="${size}" height="${size}" style="border-radius:50%;vertical-align:middle;flex-shrink:0" alt="HIRIS">`;
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
    const color = this._statusColor();
    const msgs = this._messages.map(m => `
      <div class="msg ${m.role}">
        ${this._esc(m.text).replace(/\n/g, '<br>')}
        ${m.streaming ? '<span class="cursor">&#x258C;</span>' : ''}
      </div>`).join('');

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .card { background: var(--card-background-color,#fff); border-radius: 12px;
          overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
        .header { display: flex; align-items: center; justify-content: space-between;
          padding: 12px 16px; border-bottom: 1px solid var(--divider-color,#e0e0e0); }
        .header-left { display: flex; align-items: center; gap: 8px; }
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
        .status { display: flex; align-items: center; gap: 6px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-text { font-size: 12px; color: var(--secondary-text-color,#666); }
        .toggle { cursor: pointer; font-size: 18px; background: none; border: none;
          padding: 0; line-height: 1; }
        .budget-bar { height: 4px; background: var(--divider-color,#eee); }
        .budget-fill { height: 100%; width: ${pct}%; background: var(--primary-color,#03a9f4);
          transition: width .3s; }
        .budget-text { font-size: 11px; color: var(--secondary-text-color,#888);
          padding: 2px 16px 4px; }
        .messages { height: 200px; overflow-y: auto; padding: 12px 16px;
          display: flex; flex-direction: column; gap: 8px; }
        .msg { max-width: 85%; padding: 8px 12px; border-radius: 12px;
          font-size: 14px; line-height: 1.4; word-break: break-word; }
        .msg.user { align-self: flex-end; background: var(--primary-color,#03a9f4);
          color: #fff; border-radius: 12px 12px 2px 12px; }
        .msg.assistant { align-self: flex-start;
          background: var(--secondary-background-color,#f5f5f5);
          color: var(--primary-text-color,#333); border-radius: 12px 12px 12px 2px; }
        .cursor { animation: blink 1s step-start infinite; }
        @keyframes blink { 50% { opacity: 0; } }
        .empty { color: #aaa; text-align: center; padding-top: 60px; font-size: 13px; }
        .error-badge { padding: 8px 16px; color: var(--warning-color,#ff9800);
          font-size: 13px; text-align: center; }
        .input-row { display: flex; gap: 8px; padding: 12px 16px;
          border-top: 1px solid var(--divider-color,#e0e0e0); }
        .input { flex: 1; padding: 8px 12px; border: 1px solid var(--divider-color,#e0e0e0);
          border-radius: 20px; font-size: 14px; outline: none;
          background: var(--secondary-background-color,#f5f5f5);
          color: var(--primary-text-color,#333); }
        .send { padding: 8px 16px; background: var(--primary-color,#03a9f4); color: #fff;
          border: none; border-radius: 20px; cursor: pointer; font-size: 14px; }
        .send:disabled { opacity: .5; cursor: default; }
      </style>
      <div class="card">
        <div class="header">
          <div class="header-left">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <div class="status">
            <span class="dot"></span>
            <span class="status-text">${this._esc(this._status)}</span>
            <button class="toggle" id="tog" title="${this._enabled ? 'Disabilita' : 'Abilita'}">
              ${this._enabled ? '&#x1F7E2;' : '&#x26AA;'}
            </button>
          </div>
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
          <input class="input" id="inp" type="text" placeholder="Scrivi un messaggio&#x2026;"
            ${!this._enabled ? 'disabled' : ''} />
          <button class="send" id="snd" ${this._loading || !this._enabled ? 'disabled' : ''}>&#x2191;</button>
        </div>
      </div>`;

    const inp = this._shadow.getElementById('inp');
    const snd = this._shadow.getElementById('snd');
    const tog = this._shadow.getElementById('tog');
    const msgsEl = this._shadow.getElementById('msgs');
    const dot = this._shadow.querySelector('.dot');
    if (dot) dot.style.background = color;

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
    this._agents = null;   // null = loading, [] = loaded (possibly empty), 'error' = failed
  }

  connectedCallback() {
    this._render();
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    if (!hass) return;
    this._hass = hass;
    if (this._agents === null) this._loadAgents();
  }

  async _loadAgents() {
    if (!this._hass) return;
    this._agents = 'loading';  // sentinel: prevents concurrent fetches
    const slug = this._config.hiris_slug || 'hiris';
    try {
      const result = await this._hass.callApi('GET', `hassio_ingress/${slug}/api/agents`);
      this._agents = Array.isArray(result) ? result : [];
    } catch (e) {
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
      // Still loading
      agentField = `<select disabled style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#f9fafb;color:#9ca3af;box-sizing:border-box">
        <option>Caricamento agenti…</option>
      </select>`;
    } else if (this._agents === 'error' || this._agents.length === 0) {
      // Fallback to text input
      agentField = `<input id="agentInput" type="text" value="${this._esc(agentId)}"
        placeholder="es. hiris-default"
        style="width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:13px;background:#fff;color:#111;box-sizing:border-box">`;
    } else {
      // Populated dropdown
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

    // Wire up events
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
      titleInput.onchange = (e) => {
        this._config = { ...this._config, title: e.target.value };
        this._fireConfigChanged();
      };
    }
  }
}

if (!customElements.get('hiris-chat-card-editor')) {
  customElements.define('hiris-chat-card-editor', HirisChatCardEditor);
}
if (!customElements.get('hiris-chat-card')) {
  customElements.define('hiris-chat-card', HirisCard);
}

// Register in window.customCards so HA shows the card in the picker
window.customCards = window.customCards || [];
if (!window.customCards.find(c => c.type === 'hiris-chat-card')) {
  window.customCards.push({
    type: 'hiris-chat-card',
    name: 'HIRIS Chat',
    description: 'Chat con il tuo assistente smart home HIRIS',
    preview: false,
  });
}
