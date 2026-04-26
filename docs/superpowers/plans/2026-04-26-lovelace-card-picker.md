# Lovelace Card Picker Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `hiris-chat-card` discoverable nel picker "Aggiungi scheda → Custom Cards" di Home Assistant, con editor visuale che carica la lista agenti, icona HIRIS inline, e stato "non configurata" invece di crash.

**Architecture:** Tutte le modifiche sono in un unico file JS (`hiris/app/static/hiris-chat-card.js`). Si aggiunge la costante `_HIRIS_ICON_DATA` (SVG come data URI), si registra la card in `window.customCards`, si corregge `setConfig`/`getStubConfig`, si aggiunge lo stato unconfigured in `_render()`, e si implementa la nuova classe `HirisChatCardEditor`. Nessun cambio backend — la registrazione della risorsa JS in `server.py` è già presente e funzionante.

**Tech Stack:** Vanilla JS (ES2020), Web Components / Shadow DOM, Lovelace Custom Card API (HA), pytest (test content-check)

---

## File Map

| File | Azione |
|------|--------|
| `hiris/app/static/hiris-chat-card.js` | Modifica (unico file) |
| `tests/test_lovelace_registration.py` | Modifica (aggiunge 5 test) |

---

## Context — struttura attuale di `hiris-chat-card.js`

Il file ha questa struttura (291 righe):
```
righe 1-15   — costanti: POLL_MS, CHAT_TIMEOUT_MS, EUR_RATE
righe 17-288 — class HirisCard extends HTMLElement { ... }
riga 290     — customElements.define('hiris-chat-card', HirisCard)
```

Dentro `HirisCard`:
- `constructor()` — riga 18
- `static getConfigElement()` — riga 36 → restituisce `div` vuoto (da cambiare)
- `static getStubConfig()` — riga 37 → `agent_id: ''` (da cambiare)
- `setConfig(config)` — riga 41 → lancia eccezione su `agent_id` vuoto (da correggere)
- `set hass(hass)` — riga 49
- `connectedCallback()` — riga 65
- `_startPolling()` — riga 73
- `_fetchStatus()` — riga 78
- `_sendMessage(text)` — riga 98
- `_toggleAgent()` — riga 169
- `_statusColor()` — riga 183
- `_esc(s)` — riga 190
- `_render()` — riga 194 → inizio con `const pct = ...`, contiene `&#x1F916;` nel header

---

## Task 1: Scrivere i 5 test (TDD — devono fallire)

**Files:**
- Modify: `tests/test_lovelace_registration.py` (append in fondo al file)

- [ ] **Step 1: Aggiungi i 5 test content-check in fondo a `tests/test_lovelace_registration.py`**

Aggiungi questo blocco dopo l'ultimo test esistente (riga 128):

```python
# ---------------------------------------------------------------------------
# Content-check tests for hiris-chat-card.js picker integration
# ---------------------------------------------------------------------------

from pathlib import Path

_CARD_JS = Path(__file__).parent.parent / "hiris" / "app" / "static" / "hiris-chat-card.js"


def _js() -> str:
    return _CARD_JS.read_text(encoding="utf-8")


def test_customcards_registration():
    """JS registers the card in window.customCards so HA shows it in the picker."""
    src = _js()
    assert "window.customCards" in src
    assert "'hiris-chat-card'" in src or '"hiris-chat-card"' in src


def test_editor_element_defined():
    """JS defines the hiris-chat-card-editor custom element for the config UI."""
    src = _js()
    assert "hiris-chat-card-editor" in src


def test_stub_config_has_default_agent():
    """getStubConfig returns hiris-default so the picker can add the card without crashing."""
    src = _js()
    assert "hiris-default" in src


def test_setconfig_no_throw():
    """setConfig no longer throws when agent_id is missing."""
    src = _js()
    assert "throw new Error('agent_id is required')" not in src


def test_hiris_icon_inlined():
    """The HIRIS SVG icon is inlined in the JS (petal colour c084fc is present)."""
    src = _js()
    assert "c084fc" in src
```

- [ ] **Step 2: Verifica che tutti e 5 i test falliscano (atteso)**

```bash
cd C:/Work/Sviluppo/hiris
python -m pytest tests/test_lovelace_registration.py::test_customcards_registration tests/test_lovelace_registration.py::test_editor_element_defined tests/test_lovelace_registration.py::test_stub_config_has_default_agent tests/test_lovelace_registration.py::test_setconfig_no_throw tests/test_lovelace_registration.py::test_hiris_icon_inlined -v
```

Atteso: **5 FAILED** — il JS non ha ancora nessuna di queste features.

- [ ] **Step 3: Commit dei test**

```bash
git add tests/test_lovelace_registration.py
git commit -m "test: add failing content-check tests for card picker integration"
```

---

## Task 2: `window.customCards` + fix `getStubConfig` + costante SVG

**Files:**
- Modify: `hiris/app/static/hiris-chat-card.js`

Questo task fa passare `test_customcards_registration`, `test_stub_config_has_default_agent`, `test_hiris_icon_inlined`.

- [ ] **Step 1: Aggiungi la costante `_HIRIS_ICON_DATA` dopo le costanti esistenti (riga 15)**

Trova questo blocco in fondo alle costanti (righe 13-15):
```javascript
const POLL_MS = 30_000;
const CHAT_TIMEOUT_MS = 30_000;
const EUR_RATE = 0.92;
```

Aggiungi subito dopo (riga 16, prima della classe):
```javascript
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
```

Nota: l'uso di `data:image/svg+xml` con `<img>` evita conflitti tra ID SVG (`#bg`, `#glow`) quando più istanze della card sono presenti nella stessa pagina.

- [ ] **Step 2: Correggi `getStubConfig` (riga ~37)**

Trova:
```javascript
  static getStubConfig() {
    return { agent_id: '', title: 'HIRIS Chat', hiris_slug: 'hiris' };
  }
```

Sostituisci con:
```javascript
  static getStubConfig() {
    return { agent_id: 'hiris-default', title: 'HIRIS Chat', hiris_slug: 'hiris' };
  }
```

- [ ] **Step 3: Aggiungi `window.customCards` in fondo al file (dopo `customElements.define`)**

Trova l'ultima riga del file:
```javascript
customElements.define('hiris-chat-card', HirisCard);
```

Aggiungi subito dopo:
```javascript

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hiris-chat-card',
  name: 'HIRIS Chat',
  description: 'Chat con il tuo assistente smart home HIRIS',
  preview: true,
});
```

- [ ] **Step 4: Verifica che 3 test passino**

```bash
python -m pytest tests/test_lovelace_registration.py::test_customcards_registration tests/test_lovelace_registration.py::test_stub_config_has_default_agent tests/test_lovelace_registration.py::test_hiris_icon_inlined -v
```

Atteso: **3 PASSED** — `test_editor_element_defined` e `test_setconfig_no_throw` ancora FAILED (ok).

- [ ] **Step 5: Verifica che i test esistenti non siano rotti**

```bash
python -m pytest tests/test_lovelace_registration.py -v
```

Atteso: 6 test esistenti PASSED + 3 nuovi PASSED + 2 nuovi FAILED (quelli non ancora implementati).

- [ ] **Step 6: Commit**

```bash
git add hiris/app/static/hiris-chat-card.js
git commit -m "feat: add HIRIS icon constant, window.customCards registration, fix getStubConfig"
```

---

## Task 3: Fix `setConfig`, `connectedCallback`, stato "non configurata" + icona nel header

**Files:**
- Modify: `hiris/app/static/hiris-chat-card.js`

Questo task fa passare `test_setconfig_no_throw`. Aggiunge anche il metodo `_iconHtml`, lo stato unconfigured in `_render()`, e sostituisce l'emoji 🤖 con l'icona HIRIS nell'header della card.

- [ ] **Step 1: Correggi `setConfig` (riga ~41)**

Trova:
```javascript
  setConfig(config) {
    if (!config.agent_id) throw new Error('agent_id is required');
    this._agentId = config.agent_id;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._render();
  }
```

Sostituisci con:
```javascript
  setConfig(config) {
    this._agentId = config.agent_id || null;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._render();
  }
```

- [ ] **Step 2: Verifica `connectedCallback` (riga ~65) — nessun cambio richiesto**

Cerca questa riga nel file:
```javascript
  connectedCallback() {
    if (this._agentId && !this._polling) this._startPolling();
  }
```

Il controllo `this._agentId` è già presente nel codice originale — nessuna modifica necessaria. Se non fosse presente (versione molto vecchia del file), aggiungerla sarebbe il fix. Prosegui al passo successivo.

- [ ] **Step 3: Aggiungi il metodo helper `_iconHtml(size)` nella classe `HirisCard`**

Aggiungi subito prima del metodo `_esc(s)` (cerca `_esc(s) {`):

```javascript
  _iconHtml(size) {
    return `<img src="${_HIRIS_ICON_DATA}" width="${size}" height="${size}" style="border-radius:50%;flex-shrink:0;vertical-align:middle;" alt="HIRIS">`;
  }

```

- [ ] **Step 4: Aggiungi lo stato "non configurata" all'inizio di `_render()`**

Trova l'inizio del metodo `_render()`:
```javascript
  _render() {
    const pct = this._budgetLimitEur > 0
```

Sostituisci con:
```javascript
  _render() {
    if (!this._agentId) {
      this._shadow.innerHTML = `
        <style>
          :host { display: block; }
          .card { background: var(--card-background-color,#fff); border-radius: 12px;
            overflow: hidden; box-shadow: var(--ha-card-box-shadow,0 2px 4px rgba(0,0,0,.1)); }
          .header { display: flex; align-items: center; gap: 8px; padding: 12px 16px;
            border-bottom: 1px solid var(--divider-color,#e0e0e0); }
          .title-text { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
          .unconfigured { padding: 32px 16px; text-align: center;
            display: flex; flex-direction: column; align-items: center; gap: 10px; }
          .unconfigured-label { font-size: 13px; font-weight: 600;
            color: var(--primary-text-color,#374151); }
          .unconfigured-hint { font-size: 11px; color: var(--secondary-text-color,#9ca3af); }
        </style>
        <div class="card">
          <div class="header">
            ${this._iconHtml(22)}
            <span class="title-text">${this._esc(this._title)}</span>
          </div>
          <div class="unconfigured">
            ${this._iconHtml(40)}
            <span class="unconfigured-label">Card non configurata</span>
            <span class="unconfigured-hint">Clicca ✏️ per selezionare un agente</span>
          </div>
        </div>`;
      return;
    }
    const pct = this._budgetLimitEur > 0
```

- [ ] **Step 5: Sostituisci l'emoji 🤖 con l'icona HIRIS nell'header della card configurata**

Nella parte esistente di `_render()` (dopo il blocco unconfigured), trova la riga nel template HTML che contiene l'emoji:
```javascript
          <div class="header">
            <span class="title">&#x1F916; ${this._esc(this._title)}</span>
```

Sostituisci con:
```javascript
          <div class="header">
            <div class="title-row">
              ${this._iconHtml(20)}
              <span class="title">${this._esc(this._title)}</span>
            </div>
```

E nel blocco `<style>` dello stesso template (dentro la parte configurata di `_render()`), trova:
```css
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
```

Sostituisci con:
```css
        .title-row { display: flex; align-items: center; gap: 8px; }
        .title { font-size: 15px; font-weight: 600; color: var(--primary-text-color,#333); }
```

- [ ] **Step 6: Verifica che il test passi**

```bash
python -m pytest tests/test_lovelace_registration.py::test_setconfig_no_throw -v
```

Atteso: **1 PASSED**.

- [ ] **Step 7: Verifica lo stato complessivo dei test**

```bash
python -m pytest tests/test_lovelace_registration.py -v
```

Atteso: 6 + 4 = **10 PASSED**, 1 FAILED (`test_editor_element_defined`).

- [ ] **Step 8: Esegui la suite completa per rilevare regressioni**

```bash
python -m pytest --tb=short -q
```

Atteso: tutti i test esistenti passano ancora.

- [ ] **Step 9: Commit**

```bash
git add hiris/app/static/hiris-chat-card.js
git commit -m "feat: fix setConfig no-throw, add unconfigured state, HIRIS icon in card header"
```

---

## Task 4: Implementare `HirisChatCardEditor`

**Files:**
- Modify: `hiris/app/static/hiris-chat-card.js`

Questo task fa passare `test_editor_element_defined` e completa tutti e 5 i test.

- [ ] **Step 1: Aggiorna `getConfigElement` nella classe `HirisCard` (riga ~36)**

Trova:
```javascript
  static getConfigElement() { return document.createElement('div'); }
```

Sostituisci con:
```javascript
  static getConfigElement() { return document.createElement('hiris-chat-card-editor'); }
```

- [ ] **Step 2: Aggiungi la classe `HirisChatCardEditor` prima di `customElements.define('hiris-chat-card', HirisCard)`**

Cerca la riga:
```javascript
customElements.define('hiris-chat-card', HirisCard);
```

Inserisci PRIMA di questa riga il seguente blocco completo:

```javascript
// ---------------------------------------------------------------------------
// HirisChatCardEditor — editor di configurazione per il picker Lovelace
// ---------------------------------------------------------------------------

class HirisChatCardEditor extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._agents = [];
    this._agentsLoaded = false;
    this._loadError = false;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._agentsLoaded) this._loadAgents();
  }

  async _loadAgents() {
    if (!this._hass) return;
    this._agentsLoaded = true;
    const slug = this._config.hiris_slug || 'hiris';
    try {
      const agents = await this._hass.callApi('GET', `hassio_ingress/${slug}/api/agents`);
      this._agents = Array.isArray(agents) ? agents : [];
      this._loadError = false;
    } catch (_e) {
      this._agents = [];
      this._loadError = true;
    }
    this._render();
  }

  _fireConfigChanged(newConfig) {
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: newConfig },
      bubbles: true,
      composed: true,
    }));
  }

  _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _render() {
    const cfg = this._config;
    const agentId = cfg.agent_id || '';
    const title = cfg.title || 'HIRIS Chat';

    // Build agent dropdown or text fallback
    let agentField;
    if (this._loadError) {
      agentField = `<input class="field" id="agent-input" type="text"
        value="${this._esc(agentId)}" placeholder="hiris-default">`;
    } else if (this._agents.length > 0) {
      const opts = this._agents.map(a =>
        `<option value="${this._esc(a.id)}" ${a.id === agentId ? 'selected' : ''}>
          ${this._esc(a.name)} (${this._esc(a.id)})
        </option>`
      ).join('');
      agentField = `<select class="field" id="agent-select">${opts}</select>`;
    } else {
      // Still loading
      agentField = `<select class="field" id="agent-select" disabled>
        <option>${agentId || 'Caricamento…'}</option>
      </select>`;
    }

    this._shadow.innerHTML = `
      <style>
        :host { display: block; }
        .editor-header { display: flex; align-items: center; gap: 10px;
          padding-bottom: 12px; border-bottom: 1px solid var(--divider-color,#e5e7eb);
          margin-bottom: 14px; }
        .editor-header-title { font-weight: 700; font-size: 14px;
          color: var(--primary-text-color,#111); }
        .editor-header-sub { font-size: 11px; color: var(--secondary-text-color,#9ca3af); }
        .row { margin-bottom: 14px; }
        .label { font-size: 11px; font-weight: 600;
          color: var(--secondary-text-color,#6b7280);
          text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
        .hint { font-size: 11px; color: var(--secondary-text-color,#9ca3af); margin-top: 3px; }
        .field { width: 100%; padding: 9px 12px;
          border: 1px solid var(--divider-color,#d1d5db);
          border-radius: 8px; font-size: 13px;
          background: var(--card-background-color,#fff);
          color: var(--primary-text-color,#111);
          box-sizing: border-box; }
        select.field { appearance: none; cursor: pointer; }
      </style>

      <div class="editor-header">
        <img src="${_HIRIS_ICON_DATA}" width="32" height="32"
          style="border-radius:50%;flex-shrink:0;" alt="HIRIS">
        <div>
          <div class="editor-header-title">HIRIS Chat</div>
          <div class="editor-header-sub">Configurazione card</div>
        </div>
      </div>

      <div class="row">
        <div class="label">Agente</div>
        ${agentField}
        <div class="hint">Agente che risponde nella chat</div>
      </div>

      <div class="row">
        <div class="label">Titolo</div>
        <input class="field" id="title-input" type="text"
          value="${this._esc(title)}" placeholder="HIRIS Chat">
        <div class="hint">Mostrato nell'intestazione della card</div>
      </div>`;

    // Wire up change listeners
    const agentSelect = this._shadow.getElementById('agent-select');
    const agentInput  = this._shadow.getElementById('agent-input');
    const titleInput  = this._shadow.getElementById('title-input');

    if (agentSelect && !agentSelect.disabled) {
      agentSelect.onchange = () =>
        this._fireConfigChanged({ ...this._config, agent_id: agentSelect.value });
    }
    if (agentInput) {
      agentInput.oninput = () =>
        this._fireConfigChanged({ ...this._config, agent_id: agentInput.value.trim() || 'hiris-default' });
    }
    if (titleInput) {
      titleInput.oninput = () =>
        this._fireConfigChanged({ ...this._config, title: titleInput.value || 'HIRIS Chat' });
    }
  }
}

customElements.define('hiris-chat-card-editor', HirisChatCardEditor);

```

- [ ] **Step 3: Verifica che tutti e 5 i test passino**

```bash
python -m pytest tests/test_lovelace_registration.py::test_customcards_registration tests/test_lovelace_registration.py::test_editor_element_defined tests/test_lovelace_registration.py::test_stub_config_has_default_agent tests/test_lovelace_registration.py::test_setconfig_no_throw tests/test_lovelace_registration.py::test_hiris_icon_inlined -v
```

Atteso: **5 PASSED**.

- [ ] **Step 4: Esegui la suite completa**

```bash
python -m pytest --tb=short -q
```

Atteso: tutti i test passano.

- [ ] **Step 5: Commit finale**

```bash
git add hiris/app/static/hiris-chat-card.js
git commit -m "feat: implement HirisChatCardEditor with agent dropdown and HIRIS icon"
```

---

## Verifica end-to-end (manuale, opzionale)

Dopo il deploy su HA:
1. Apri una dashboard in modifica → "Aggiungi scheda"
2. Scorri fino a "Custom Cards" — deve apparire **HIRIS Chat** con icona e descrizione
3. Cliccaci sopra → si apre l'editor con dropdown agenti e campo titolo
4. Seleziona un agente e salva → la card appare funzionante con icona HIRIS nell'header
5. Aggiungi la card su un'altra dashboard → funziona uguale
