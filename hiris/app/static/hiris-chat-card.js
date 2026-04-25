// hiris-chat-card.js — HA Lovelace custom card for HIRIS chat
// Add to configuration.yaml:
//   lovelace:
//     resources:
//       - url: /api/hassio_ingress/hiris/static/hiris-chat-card.js
//         type: module
// Dashboard config:
//   type: custom:hiris-chat-card
//   agent_id: hiris-default
//   title: "Assistente Casa"
//   hiris_slug: hiris

const POLL_MS = 30_000;
const CHAT_TIMEOUT_MS = 30_000;
const EUR_RATE = 0.92;

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
    this._render();
  }

  static getConfigElement() { return document.createElement('div'); }
  static getStubConfig() {
    return { agent_id: '', title: 'HIRIS Chat', hiris_slug: 'hiris' };
  }

  setConfig(config) {
    if (!config.agent_id) throw new Error('agent_id is required');
    this._agentId = config.agent_id;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Phase 2: auto-detect MQTT entities pushed by MQTTPublisher
    const statusKey = `sensor.hiris_${this._agentId}_status`;
    if (hass.states[statusKey]) {
      this._status = hass.states[statusKey].state || 'idle';
      const budgetKey = `sensor.hiris_${this._agentId}_budget_eur`;
      this._budgetEur = parseFloat(hass.states[budgetKey]?.state || '0');
      const switchKey = `switch.hiris_${this._agentId}_enabled`;
      this._enabled = hass.states[switchKey]?.state !== 'off';
      this._render();
    } else if (!this._polling) {
      this._startPolling();
    }
  }

  connectedCallback() {
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
      const agents = await this._hass.callApi('GET', `hassio_ingress/${this._slug}/api/agents`);
      const agent = agents.find(a => a.id === this._agentId);
      if (agent) {
        this._status = agent.status || 'idle';
        this._enabled = !!agent.enabled;
        this._budgetEur = agent.budget_eur || 0;
        this._budgetLimitEur = agent.budget_limit_eur || 0;
        this._error = null;
      } else {
        this._error = 'Agente non configurato';
      }
    } catch (e) {
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

    try {
      const hassUrl = this._hass.connection.options.hassUrl || '';
      const token = this._hass.connection.options.auth?.data?.access_token || '';
      const url = `${hassUrl}/api/hassio_ingress/${this._slug}/api/chat`;

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, agent_id: this._agentId, stream: true }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
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
      await this._hass.callApi(
        'PUT',
        `hassio_ingress/${this._slug}/api/agents/${this._agentId}`,
        { enabled: !this._enabled },
      );
      await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
    }
  }

  _statusColor() {
    return {
      idle: '#4caf50', running: '#2196f3', error: '#f44336',
      unavailable: '#9e9e9e',
    }[this._status] || '#9e9e9e';
  }

  _render() {
    const pct = this._budgetLimitEur > 0
      ? Math.min(100, (this._budgetEur / this._budgetLimitEur) * 100)
      : 0;
    const color = this._statusColor();
    const msgs = this._messages.map(m => `
      <div class="msg ${m.role}">
        ${m.text.replace(/</g, '&lt;').replace(/\n/g, '<br>')}
        ${m.streaming ? '<span class="cursor">&#x258C;</span>' : ''}
      </div>`).join('');

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .card { background: var(--card-background-color,#fff); border-radius: 12px;
          overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
        .header { display: flex; align-items: center; justify-content: space-between;
          padding: 12px 16px; border-bottom: 1px solid var(--divider-color,#e0e0e0); }
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
        .status { display: flex; align-items: center; gap: 6px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: ${color}; }
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
          <span class="title">&#x1F916; ${this._title}</span>
          <div class="status">
            <span class="dot"></span>
            <span class="status-text">${this._status}</span>
            <button class="toggle" id="tog" title="${this._enabled ? 'Disabilita' : 'Abilita'}">
              ${this._enabled ? '&#x1F7E2;' : '&#x26AA;'}
            </button>
          </div>
        </div>
        ${this._budgetLimitEur > 0 ? `
          <div class="budget-bar"><div class="budget-fill"></div></div>
          <div class="budget-text">&#x20AC;${this._budgetEur.toFixed(2)} / &#x20AC;${this._budgetLimitEur.toFixed(2)}</div>
        ` : ''}
        ${this._error ? `<div class="error-badge">${this._error}</div>` : ''}
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
    const msgs = this._shadow.getElementById('msgs');

    if (msgs) msgs.scrollTop = msgs.scrollHeight;
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

customElements.define('hiris-chat-card', HirisCard);
