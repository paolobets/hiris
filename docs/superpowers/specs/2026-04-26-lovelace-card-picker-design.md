# HIRIS Lovelace Card — Picker Integration Design

> **Date:** 2026-04-26
> **Status:** Approved
> **Scope:** Make `hiris-chat-card` discoverable nel picker "Aggiungi scheda" di Home Assistant con editor visuale di configurazione

---

## Goal

Quando un utente installa l'add-on HIRIS, la card Lovelace deve:
1. Apparire automaticamente nella sezione **Custom Cards** del picker "Aggiungi scheda"
2. Avere un **editor visuale** che carica la lista agenti e permette la configurazione senza YAML
3. Mostrare uno **stato "non configurata"** invece di crashare se `agent_id` è assente

## Problem Statement

Stato attuale (`v0.5.1`):
- `hiris-chat-card.js` esiste ed è funzionale (streaming SSE, budget bar, toggle)
- `_register_lovelace_card()` in `server.py` registra il file JS come risorsa Lovelace all'avvio (idempotente)
- **Mancante:** `window.customCards` registration → HA non mostra la card nel picker
- **Bug:** `setConfig()` lancia eccezione se `agent_id` è vuoto → il picker non riesce ad aggiungere la card
- **Mancante:** `getConfigElement()` restituisce `<div>` vuoto → nessun editor visuale

---

## Architecture

### File modificato

**Un solo file:** `hiris/app/static/hiris-chat-card.js`

Nessun cambio backend. La registrazione JS in `server.py` è già corretta.

### Componenti aggiunti/modificati

#### 1. `window.customCards` registration

Aggiunto in fondo al file, dopo `customElements.define`:

```javascript
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hiris-chat-card',
  name: 'HIRIS Chat',
  description: 'Chat con il tuo assistente smart home HIRIS',
  preview: true,
});
```

Questo è il meccanismo standard HA per far apparire una card custom nel picker con nome e descrizione.

#### 2. `HirisChatCardEditor` — editor di configurazione

Nuova classe custom element `hiris-chat-card-editor` che implementa il protocollo HA per gli editor di card:

**Protocollo HA:**
- HA chiama `setConfig(config)` → l'editor popola il form con la config corrente
- HA imposta `set hass(hass)` → l'editor usa `hass` per caricare agenti
- L'editor emette `CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true })` ad ogni modifica → HA salva in tempo reale

**Campi dell'editor:**
| Campo | Tipo | Default | Descrizione |
|-------|------|---------|-------------|
| `agent_id` | dropdown | `hiris-default` | Agente che risponde nella chat |
| `title` | text | `HIRIS Chat` | Titolo mostrato nell'header della card |

Il dropdown agenti è popolato chiamando `hass.callApi('GET', 'hassio_ingress/{slug}/api/agents')`. In caso di errore mostra un input testo come fallback.

**Header dell'editor:** icona HIRIS SVG inline (stessa usata nel file `hiris-icon.svg`) + titolo "HIRIS Chat" / "Configurazione card".

**Registrazione:**
```javascript
customElements.define('hiris-chat-card-editor', HirisChatCardEditor);
```

**`HirisCard.getConfigElement()`** aggiornato:
```javascript
static getConfigElement() {
  return document.createElement('hiris-chat-card-editor');
}
```

#### 3. Fix `setConfig()` — stato "non configurata"

**Prima (bug):**
```javascript
setConfig(config) {
  if (!config.agent_id) throw new Error('agent_id is required');
  // ...
}
```

**Dopo:**
```javascript
setConfig(config) {
  this._agentId = config.agent_id || null;
  this._slug = config.hiris_slug || 'hiris';
  this._title = config.title || 'HIRIS Chat';
  this._render();
}
```

Quando `_agentId` è `null`, `_render()` mostra lo stato "non configurata":
- Icona HIRIS SVG centrata (40×40)
- Testo "Card non configurata"
- Sottotesto "Clicca ✏️ per selezionare un agente"

Nessun polling né chiamate API finché `agent_id` non è configurato.

#### 4. Fix `connectedCallback` e `getStubConfig`

```javascript
// Evita polling se agent_id assente
connectedCallback() {
  if (this._agentId && !this._polling) this._startPolling();
}

// Default valido per lo stub del picker
static getStubConfig() {
  return { agent_id: 'hiris-default', title: 'HIRIS Chat', hiris_slug: 'hiris' };
}
```

---

## Icona HIRIS

L'icona SVG (`hiris/app/static/hiris-icon.svg`) viene inlinata nel JS come stringa letterale, usata in tre punti:
1. **Picker entry** — accanto al nome "HIRIS Chat" (36×36)
2. **Header card** — sostituisce l'emoji 🤖 (22×22)
3. **Stato non configurata** — centrata, opacità 70% (40×40)

L'SVG è **inlinato come costante stringa** in `hiris-chat-card.js` — il markup `<svg>...</svg>` è inserito direttamente nell'innerHTML del Shadow DOM, non come `<img src="...">` né come data URI. Questo garantisce che funzioni nel picker (dove lo slug non è ancora noto) e che l'icona erediti correttamente i colori del tema HA.

```javascript
const HIRIS_ICON_SVG = `<svg xmlns="..." viewBox="0 0 100 100">...</svg>`;
```

---

## Data Flow — aggiunta card dal picker

```
Utente: "Aggiungi scheda" → Custom Cards → HIRIS Chat
  │
  ▼
HA crea istanza HirisCard
HA chiama setConfig(getStubConfig())  →  agent_id = 'hiris-default', no throw
  │
  ▼
HA mostra editor: crea <hiris-chat-card-editor>
HA chiama editor.setConfig(config)    →  form popolato
HA imposta editor.hass = hass         →  editor chiama GET /api/agents
  │                                      dropdown popolato con nomi agenti
  ▼
Utente seleziona agente / modifica titolo
  │
  ▼
Editor emette config-changed          →  HA salva config
  │
  ▼
HA chiama card.setConfig(nuovaConfig) →  card si aggiorna con agent_id reale
card avvia polling, mostra chat       →  pronta
```

---

## Error Handling

| Scenario | Comportamento |
|----------|---------------|
| `agent_id` assente/vuoto | Card mostra stato "non configurata", nessun polling |
| `/api/agents` fallisce nell'editor | Fallback a input testo per `agent_id` |
| HIRIS non raggiungibile (card già configurata) | Messaggio `⚠ HIRIS non disponibile` (comportamento invariato) |
| Slug errato | Stessa gestione errori esistente in `_fetchStatus` |

---

## Testing

**File:** `tests/test_lovelace_registration.py` — aggiunte al file esistente

| Test | Verifica |
|------|----------|
| `test_customcards_registration` | JS contiene `window.customCards` e `hiris-chat-card` |
| `test_editor_element_defined` | JS contiene `hiris-chat-card-editor` |
| `test_stub_config_has_default_agent` | JS contiene `hiris-default` in `getStubConfig` |
| `test_setconfig_no_throw` | JS non contiene `throw new Error('agent_id is required')` |
| `test_hiris_icon_inlined` | JS contiene il markup SVG dell'icona |

Tutti i test sono **content checks** sul file JS (nessuna dipendenza frontend/browser).

---

## File Map

| File | Modifica |
|------|----------|
| `hiris/app/static/hiris-chat-card.js` | Aggiunge `HirisChatCardEditor`, `window.customCards`, fix `setConfig`, fix `connectedCallback`, fix `getStubConfig`, icona SVG inline |
| `tests/test_lovelace_registration.py` | Aggiunge 5 test content-check |

---

## Out of Scope

- Auto-creazione di dashboard o viste Lovelace — non richiesta
- Card editor avanzato (more fields: `height`, `theme`) — Phase 2
- `hiris-status-card` (widget compatto) — Phase 2
- Test E2E browser per l'editor — Phase 2
