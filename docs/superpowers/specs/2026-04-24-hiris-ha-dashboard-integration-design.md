# HIRIS — HA Dashboard Integration Design

**Data:** 2026-04-24  
**Versione:** 1.0  
**Autore:** brainstorming session  
**Stato:** Approvato — pronto per implementazione

---

## 1. Obiettivo

Integrare HIRIS nelle dashboard di Home Assistant e Retro Panel permettendo:

1. **Chat interattiva** con agenti Chat direttamente da una Lovelace card o dal widget Retro Panel
2. **Stato degli agenti** visibile nelle dashboard (status, last run, budget, enable/disable)
3. **Canale condiviso**: HA card e Retro Panel usano gli stessi endpoint HIRIS e lo stesso formato, garantendo parità funzionale

---

## 2. Scope

### In scope (questo repo — HIRIS)
- Middleware autenticazione inter-addon (`X-HIRIS-Internal-Token`)
- HA Lovelace custom card `hiris-chat-card` (Lit 3, distribuita con HIRIS)
- MQTT publisher per entità agenti — fase 2 (opzionale)
- Spec documento per il team Retro Panel
- Aggiornamento README.md e ROADMAP.md

### Out of scope
- Modifiche al codice di Retro Panel (gestite dal team RP con la spec fornita)
- `send_email`, `http_request`, `analyze_image` (rinviati)
- Telegram bot, HACS distribution (roadmap futura)

---

## 3. Architettura — Opzione C: Ibrido progressivo

### Filosofia
- **Chat sempre via REST + SSE**: sincrona, streaming token-per-token, nessuna dipendenza MQTT
- **Status fase 1 via polling**: GET /api/agents ogni 30s — zero dipendenze
- **Status fase 2 via MQTT entities**: push real-time, entità native HA — MQTT opzionale, non blocca la fase 1

### Confine di rete

```
┌─────────────────────────────────────────────────────────────┐
│  Rete interna Docker / HA Supervisor                        │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐ │
│  │ HIRIS :8099  │   │ Retro Panel  │   │    HA Core      │ │
│  │              │   │    :7654     │   │                 │ │
│  │ /api/chat    │   │ /api/hiris-  │   │ Supervisor      │ │
│  │ /api/agents  │   │   proxy/*    │   │ WebSocket API   │ │
│  │              │   │              │   │ MQTT (fase 2)   │ │
│  └──────────────┘   └──────────────┘   └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ↑ HA Ingress (auth)         ↑ IP allowlist
┌─────────────────────┐   ┌──────────────────────────────────┐
│  Browser — HA UI    │   │  Browser — Retro Panel           │
│  hiris-chat-card    │   │  Widget HIRIS                    │
└─────────────────────┘   └──────────────────────────────────┘
```

### Flussi dati — Fase 1

| Operazione | Percorso |
|---|---|
| Chat (HA card) | Browser → HA Ingress (auth) → HIRIS `/api/chat` → SSE stream |
| Chat (Retro Panel) | Browser → RP `/api/hiris-proxy/chat` → HIRIS `:8099/api/chat` + `X-HIRIS-Internal-Token` → SSE proxied |
| Status (entrambi) | Card / widget → GET `/api/agents` ogni 30s → JSON |
| Toggle enable/disable | Card → PUT `/api/agents/{id}` `{enabled: bool}` |

### Flussi dati — Fase 2 (aggiunte, chat invariata)

| Operazione | Percorso |
|---|---|
| Status push | AgentEngine → MQTTPublisher → broker → HA → `sensor.hiris_*` → WS push → card / RP |
| Toggle enable/disable | `switch.hiris_{id}_enabled` → MQTT command_topic → AgentEngine |

---

## 4. Componenti da implementare

### 4.1 HIRIS backend — Fase 1

**File:** `hiris/app/api/middleware_internal_auth.py` (nuovo)

Middleware aiohttp che valida `X-HIRIS-Internal-Token` sulle richieste non-Ingress:

```python
@web.middleware
async def internal_auth_middleware(request, handler):
    if request.headers.get("X-Ingress-Path"):
        return await handler(request)   # via HA Ingress: già autenticato
    token = app["internal_token"]
    if token and request.headers.get("X-HIRIS-Internal-Token") != token:
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)
```

**Config addon** (`config.yaml`):
```yaml
options:
  internal_token: ""    # shared secret per chiamate inter-addon
schema:
  internal_token: str
```

**Comportamento:**
- `internal_token` vuoto → middleware disabilitato (backward compat)
- Token errato o assente (con token configurato) → `401 {"error": "unauthorized"}`
- Richieste via `X-Ingress-Path` → bypass totale

---

### 4.2 HIRIS backend — Fase 2 (MQTT publisher)

**File:** `hiris/app/mqtt_publisher.py` (nuovo)

```python
class MQTTPublisher:
    async def start(self, host, port, user, password): ...
    async def publish_agent_state(self, agent: Agent): ...
    async def publish_discovery(self, agent: Agent): ...
    async def stop(self): ...
```

**Entità pubblicate per agente** (MQTT Discovery):

| Entità HA | Topic stato | Tipo |
|---|---|---|
| `sensor.hiris_{id}_status` | `hiris/agents/{id}/status` | `idle` \| `running` \| `error` |
| `sensor.hiris_{id}_last_run` | `hiris/agents/{id}/last_run` | ISO8601 timestamp |
| `sensor.hiris_{id}_budget_eur` | `hiris/agents/{id}/budget_eur` | float |
| `switch.hiris_{id}_enabled` | `hiris/agents/{id}/enabled` | `ON` \| `OFF` |

**Command topic** per switch: `hiris/agents/{id}/enabled/set` → `ON`/`OFF` → `AgentEngine.set_enabled(id, bool)`

**Config addon** (`config.yaml`):
```yaml
options:
  mqtt_host: ""
  mqtt_port: 1883
  mqtt_user: ""
  mqtt_password: ""
schema:
  mqtt_host: str
  mqtt_port: int
  mqtt_user: str
  mqtt_password: password
```

Se `mqtt_host` è vuoto → `MQTTPublisher` non viene avviato, HIRIS funziona in fase 1.

**Reconnect:** backoff esponenziale 1s → 2s → 4s → … → 60s max.

---

### 4.3 HA Lovelace Card — `hiris-chat-card`

**File:** `hiris/app/static/hiris-chat-card.js` (nuovo)  
**Stack:** Lit 3, bundle singolo, nessuna dipendenza esterna  
**Distribuzione:** servita da HIRIS via `/static/hiris-chat-card.js`, referenziata nel `configuration.yaml` di HA

**Configurazione YAML dashboard:**
```yaml
type: custom:hiris-chat-card
agent_id: agent-energia-001   # obbligatorio
title: "Agente Energia"       # opzionale, default: nome agente
hiris_slug: hiris             # slug addon HA, default: "hiris"
```

**Chiamate API dalla card:**

La card usa `hass.callApi()` che instrada automaticamente via HA Supervisor — nessun URL hardcoded, auth gestita da HA:

```javascript
// Chat
hass.callApi("POST", `hassio_ingress/${slug}/api/chat`, {
  message: text,
  agent_id: agentId
})
// SSE: fetch nativa con credentials

// Status — Fase 1
hass.callApi("GET", `hassio_ingress/${slug}/api/agents`)
// → polling ogni 30s

// Status — Fase 2 (auto-detect)
// Se hass.states["sensor.hiris_${agentId}_status"] esiste → WS subscription
// Altrimenti → resta in polling
```

**UI della card:**
```
┌─────────────────────────────────┐
│ 🤖 Agente Energia    ● idle  🔘 │  ← nome, status badge, toggle
├─────────────────────────────────┤
│ Budget: €0.12 / €5.00           │  ← barra budget
├─────────────────────────────────┤
│                                 │
│  [risposta precedente...]       │  ← history chat
│                                 │
│  Quanto ho consumato oggi?      │  ← messaggio utente
│  Il consumo di oggi è 12kWh...  │  ← risposta SSE (streaming)
│                                 │
├─────────────────────────────────┤
│  [Scrivi un messaggio...   ] ↑  │  ← input + invio
└─────────────────────────────────┘
```

**Istruzioni installazione** (in README):
```yaml
# configuration.yaml
lovelace:
  resources:
    - url: /api/hassio_ingress/hiris/static/hiris-chat-card.js
      type: module
```

---

## 5. Spec Retro Panel (documento separato)

Il file `docs/superpowers/specs/2026-04-24-retropanel-hiris-spec.md` contiene la spec completa da consegnare al team Retro Panel, includendo:

- Endpoint HIRIS da chiamare e formato request/response
- Header `X-HIRIS-Internal-Token` e come ottenerlo dalla config
- Pattern SSE proxy (stream response al browser)
- Schema widget UI (mockup)
- Nuove config RP: `hiris_url`, `hiris_internal_token`
- Gestione errori (HIRIS non raggiungibile, token invalido)

---

## 6. Error handling

### HIRIS backend
| Situazione | Comportamento |
|---|---|
| Token errato/assente | `401 {"error": "unauthorized"}` |
| MQTT disconnect | Reconnect backoff, entità restano nell'ultimo stato |
| MQTT non configurato | Avvio normale senza publisher, log info |

### HA Card
| Situazione | Comportamento |
|---|---|
| HIRIS non raggiungibile | Badge "⚠ Non disponibile", retry ogni 60s |
| Chat timeout (>30s) | Messaggio errore inline, card non bloccata |
| SSE interrotto | Riconnessione automatica (EventSource retry) |
| Agente non trovato | Card mostra "Agente non configurato" |
| `sensor.hiris_*` assente | Resta in polling fase 1, nessun errore |

---

## 7. Testing

### HIRIS backend
- `test_internal_auth_middleware.py`: token valido, errato, assente, bypass Ingress
- `test_mqtt_publisher.py` (fase 2): mock broker (aiomqtt), verifica topic Discovery e payload
- Integrazione: command_topic → AgentEngine.set_enabled()

### HA Card
- Test manuali su dashboard locale con HIRIS reale
- Verifica: streaming SSE, polling status, toggle, error states
- Smoke test Playwright opzionale per fase futura

---

## 8. Dipendenze

### Fase 1
- Nessuna dipendenza esterna nuova
- Lit 3 (CDN o bundled nel JS della card)

### Fase 2
- `aiomqtt` (o `paho-mqtt` — da ADR-001) aggiunta a `requirements.txt`
- Mosquitto add-on installato e configurato dall'utente

---

## 9. Documentazione da aggiornare a fine implementazione

- **README.md**: sezione "HA Dashboard Integration" con istruzioni installazione card, config MQTT
- **ROADMAP.md**: v0.5 aggiornato con item completati (HA card, MQTT bridge), rimozione da priority stack

---

## 10. Ordine di implementazione suggerito

1. **Middleware X-HIRIS-Internal-Token** — prerequisito per tutto il resto
2. **HA Lovelace card `hiris-chat-card`** — valore principale, fase 1
3. **Test middleware + card manuale**
4. **Spec Retro Panel** — documento consegnabile al team
5. **MQTTPublisher** — fase 2, richiede ADR-001 e Mosquitto
6. **Upgrade card a WS status** — dopo MQTT funzionante
7. **README + ROADMAP update**
