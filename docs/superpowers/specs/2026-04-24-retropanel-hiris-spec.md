# Retro Panel × HIRIS — Integration Spec

**Data:** 2026-04-24  
**Versione:** 1.0  
**Destinatari:** Team Retro Panel  
**Contesto:** HIRIS è un HA add-on AI separato. Questo documento specifica cosa il team RP deve implementare per integrare HIRIS nel pannello Retro Panel.

---

## Obiettivo

Aggiungere a Retro Panel:
1. **Widget chat** per dialogare con un agente HIRIS
2. **Widget status agenti** per vedere lo stato degli agenti attivi
3. Il backend RP fa da proxy verso HIRIS — il browser non chiama mai HIRIS direttamente

---

## Come funziona HIRIS

HIRIS è raggiungibile dalla rete interna Docker su `http://hiris:8099`.  
Tutte le chiamate dal backend RP a HIRIS devono includere:
```
X-HIRIS-Internal-Token: <valore dalla config>
```
Senza questo header (se configurato) HIRIS risponde `401`.

---

## Configurazione da aggiungere a Retro Panel

Nel manifest/config del addon RP aggiungere le opzioni:

```yaml
options:
  hiris_url: "http://hiris:8099"   # URL interno HIRIS (default)
  hiris_internal_token: ""          # shared secret, vuoto = HIRIS senza auth
schema:
  hiris_url: str
  hiris_internal_token: str
```

---

## API HIRIS da proxare

### 1. Lista agenti

```
GET http://hiris:8099/api/agents
Headers: X-HIRIS-Internal-Token: <token>

Response 200:
[
  {
    "id": "agent-energia-001",
    "name": "Energia",
    "type": "chat",           // chat | monitor | reactive | preventive
    "enabled": true,
    "status": "idle",         // idle | running | error
    "last_run": "2026-04-24T10:30:00Z",   // null se mai eseguito
    "budget_eur": 0.12,
    "budget_limit_eur": 5.0,
    "is_default": false
  },
  ...
]
```

### 2. Chat con agente (SSE streaming)

```
POST http://hiris:8099/api/chat
Headers:
  Content-Type: application/json
  X-HIRIS-Internal-Token: <token>

Body:
{
  "message": "Quanto ho consumato oggi?",
  "agent_id": "agent-energia-001"        // opzionale, default: agente default
}
```

**Risposta sincrona (attuale):**
```
Response 200:
{
  "response": "Il consumo di oggi è 12kWh, +8% rispetto a ieri.",
  "agent_id": "agent-energia-001",
  "tool_calls": [...]   // opzionale, lista tool chiamati
}
```

> **Nota per il team RP:** HIRIS supporta SSE (streaming token-per-token). Il proxy RP deve gestire `Content-Type: text/event-stream` e streammare la risposta al browser. In alternativa, è possibile attendere il completamento e restituire la risposta intera come JSON — ma si perde l'effetto typing.

### 3. Enable / disable agente

```
PUT http://hiris:8099/api/agents/{agent_id}
Headers:
  Content-Type: application/json
  X-HIRIS-Internal-Token: <token>

Body:
{
  "enabled": true   // o false
}

Response 200: agente aggiornato (stesso schema di GET /api/agents item)
```

---

## Endpoint proxy da aggiungere a RP

Seguendo il pattern già usato per camera, calendar, ecc.:

```python
# /api/hiris/agents  → GET lista agenti
# /api/hiris/chat    → POST chat (body passato a HIRIS)
# /api/hiris/agents/{agent_id}/toggle → PUT enable/disable
```

Schema implementativo (adatta al pattern RP):
```python
async def hiris_chat(request):
    hiris_url = config.hiris_url
    token = config.hiris_internal_token
    body = await request.json()
    headers = {"X-HIRIS-Internal-Token": token} if token else {}
    async with session.post(f"{hiris_url}/api/chat", json=body, headers=headers) as resp:
        data = await resp.json()
        return web.json_response(data)
```

---

## Fase 2 — Status via entità HA (quando disponibile)

Se HIRIS ha MQTT configurato, pubblica automaticamente queste entità in HA:

```
sensor.hiris_{agent_id}_status       → idle | running | error
sensor.hiris_{agent_id}_last_run     → ISO8601
sensor.hiris_{agent_id}_budget_eur   → float
switch.hiris_{agent_id}_enabled      → on | off
```

In fase 2, il widget RP può leggere queste entità via WebSocket HA (che RP già usa) invece di pollare `/api/hiris/agents`. La chat resta sempre via proxy REST.

---

## Widget UI — specifiche

### Widget "HIRIS Chat"

```
┌─────────────────────────────────┐
│ 🤖 Agente Energia    ● idle  🔘 │  ← nome, status, toggle on/off
├─────────────────────────────────┤
│ ▓▓▓░░░░░░░░ €0.12 / €5.00      │  ← barra budget
├─────────────────────────────────┤
│                                 │
│  Risposta precedente...         │
│                                 │
│  [Quanto ho consumato oggi?]    │  ← ultimo messaggio utente
│  Il consumo è 12kWh...          │  ← risposta (con typing indicator)
│                                 │
├─────────────────────────────────┤
│  [Scrivi un messaggio...   ] ↑  │
└─────────────────────────────────┘
```

### Widget "HIRIS Agenti" (status panel)

```
┌─────────────────────────────────┐
│ HIRIS — Agenti                  │
├────────────┬────────┬───────────┤
│ Energia    │ ● idle │ €0.12 🔘  │
│ Monitor    │ ● run  │ €1.40 🔘  │
│ Sicurezza  │ ○ off  │ €0.00 🔘  │
└────────────┴────────┴───────────┘
```

---

## Gestione errori

| Situazione | Comportamento UI |
|---|---|
| HIRIS non raggiungibile | Badge "⚠ HIRIS non disponibile", retry 60s |
| Token errato (401) | Log errore, badge "⚠ Auth fallita — controlla config" |
| Chat timeout (>30s) | Messaggio "Timeout — riprova" inline nel thread |
| Agente non trovato (404) | "Agente non disponibile" |

---

## Note di sicurezza

- `X-HIRIS-Internal-Token` non viene mai esposto al browser — solo il backend RP lo usa
- Il browser chiama RP (`/api/hiris/*`), RP chiama HIRIS — il browser non conosce l'URL né il token HIRIS
- L'IP allowlist esistente di RP protegge il direct port :7654 — nessuna modifica necessaria
