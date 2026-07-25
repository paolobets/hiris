# HIRIS — Come funziona

> Versione: 0.33.0 · Aggiornato: 2026-07-24

---

## Cos'è HIRIS

**HIRIS** (Home Intelligent Reasoning & Integration System) è un Add-on per Home Assistant che aggiunge un layer di intelligenza artificiale alla smart home. Espone una chat in linguaggio naturale configurata tramite **Personas**, ed esegue un livello proattivo built-in — la **Sentinella** — che sorveglia un set fisso di situazioni tarabili ("lenti") e ragiona su di esse tramite Claude (o OpenAI / Ollama) come motore di ragionamento.

HIRIS **non sostituisce** Home Assistant — si affianca a esso. Le automazioni semplici (luci al tramonto, sveglie) restano nel Layer 1 locale. Il ragionamento complesso, le anomalie, e le domande in linguaggio libero vanno al Layer 2 AI.

---

## Architettura a due livelli

```
┌───────────────────────────────────────────────────────┐
│  LAYER 2 — AI Agentic Loop                            │
│  • Chat in linguaggio naturale (Personas)              │
│  • Sentinella: lenti proattive built-in                │
│    (opening, fridge_temp, power, battery,              │
│     hot_and_away, arrival, ...)                         │
│  • Ragionamento multi-sorgente (meteo + energia + HA) │
│  • Memoria e RAG pre-fetch                            │
│  Modello: Claude Sonnet (chat) / Haiku (Sentinella)   │
│  Fallback: OpenAI GPT-4o / Ollama locale              │
└───────────────────────────────────────────────────────┘
          ↕  tool calls
┌───────────────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (locale, offline)       │
│  • Listener WebSocket HA: state_changed (detector)     │
│  • Snapshot periodico: situazioni/arrival               │
│  • Task engine: azioni differite                       │
│  • Semaforo: gate tier + denylist domini pericolosi   │
└───────────────────────────────────────────────────────┘
          ↕  REST + WebSocket
┌───────────────────────────────────────────────────────┐
│  HOME ASSISTANT CORE                                  │
└───────────────────────────────────────────────────────┘
```

---

## Flusso di una richiesta chat

Quando l'utente scrive un messaggio, HIRIS esegue questi passi in sequenza:

### 1. Ricezione e routing

`POST /api/chat` → `handlers_chat.py`

- Legge `{message, agent_id}` dal body JSON
- Identifica l'agente richiesto (o usa `hiris-default`)
- Carica la cronologia della conversazione da SQLite (`chat_history.db`)
- Recupera le memorie rilevanti dallo store vettoriale (RAG injection)

### 2. Costruzione del system prompt

Il system prompt è composto a strati, nell'ordine:

```
[1] strategic_context dell'agente  ("Sei il controllore della casa Rossi…")
[2] system_prompt dell'agente      (istruzioni, tool, regole)
[3] --- separatore ---
[4] Semantic Map Snippet           (snapshot live della casa, ~5 righe)
[5] --- separatore ---
[6] Memorie RAG                    (interazioni passate rilevanti, marcate untrusted)
[7] RAG pre-fetch entità           (stati live delle entità rilevanti per questo messaggio)
```

Esempio di system prompt che Claude riceve:

```
Sei HIRIS, assistente per la smart home…

---

CASA [mappa agg. 14:30]
Energia: sensor.potenza_rete(W), sensor.fotovoltaico(W)
Clima: climate.soggiorno(21.5°→22°C heating), climate.camera(20°→21°C idle)
Presenze: PIR Ingresso(off), PIR Salotto(on)
Luci: 18 entità / 5 stanze
Elettrodomestici: switch.lavatrice, switch.lavastoviglie

---

Entità rilevanti (dati in tempo reale):
- Luce Soggiorno [light.soggiorno]: on
- Termostato Salotto [climate.soggiorno]: heat, corrente 21.5°C → setpoint 22°C
- Potenza Rete [sensor.potenza_rete]: 1243 W
```

### 3. Agentic loop (Claude + tool use)

Claude riceve: system prompt + cronologia + messaggio utente.

Claude risponde con una di queste modalità:
- **Testo diretto** → risposta all'utente, fine
- **Tool call** → HIRIS esegue il tool, manda il risultato a Claude, Claude decide di nuovo

Il loop si ripete fino a **10 iterazioni** (protezione da loop infiniti). Claude decide autonomamente quando ha abbastanza informazioni per rispondere.

**Gestione errori API:**
- 429/529 (rate limit): 3 retry con backoff esponenziale (5s → 15s → 45s)
- Tool che fallisce: restituisce `{error: "..."}` invece di lanciare eccezione — Claude vede l'errore e può gestirlo

### 4. Risposta e persistenza

- La risposta torna al frontend come `{response: "...", debug: {tools_called: [...]}}`
- Il turno (utente + assistente) viene scritto atomicamente su SQLite
- I token usati vengono contabilizzati per modello e per agente

---

## I tool disponibili

| Tool | Descrizione |
|---|---|
| `get_entity_states(ids)` | Stato live di specifiche entità HA |
| `get_home_status()` | Snapshot strutturato compatto della casa |
| `get_area_entities()` | Tutte le entità raggruppate per stanza |
| `get_entities_on()` | Tutte le entità attualmente in stato `on` |
| `get_entities_by_domain(domain)` | Entità filtrate per dominio |
| `get_energy_history(days)` | Storico consumi dall'HA History API |
| `get_weather_forecast(hours)` | Previsioni da Open-Meteo (gratis, no chiave) |
| `call_ha_service(domain, service, data)` | Chiama qualsiasi servizio HA (filtrato da `allowed_services`) |
| `send_notification(message, channel)` | Push via HA, Telegram, Apprise (80+ canali) |
| `get_ha_automations()` | Lista automazioni HA |
| `trigger_automation(id)` | Esegue un'automazione HA |
| `toggle_automation(id, enabled)` | Abilita/disabilita un'automazione |
| `get_calendar_events(hours, calendar)` | Eventi calendario HA |
| `set_input_helper(entity_id, value)` | Imposta input_boolean / input_number / input_text |
| `create_task(...)` / `list_tasks()` / `cancel_task(id)` | Gestione task interni |
| `recall_memory(query, k, tags)` | Ricerca memorie passate (similarità vettoriale) |
| `save_memory(content, tags)` | Salva una nuova memoria (solo agenti chat) |
| `http_request(url, method, headers, body)` | Chiamata HTTP verso endpoint approvati |
| `get_ha_health(sections)` | Snapshot salute HA: entità non disponibili, errori integrazioni, aggiornamenti, info sistema |
| `create_automation_proposal(type, name, description, config, routing_reason)` | Propone una nuova automazione per revisione umana (solo agenti chat) |

---

## Personas e Sentinella

Non esiste più un unico concetto di "agente" diviso in tipi (`chat` /
`monitor` / `reactive` / `preventive`) con regole e stati personalizzati.
HIRIS oggi ragiona sulla casa in due soli modi:

### Personas — conversazionale

Attivata dall'utente tramite UI (o la card Lovelace). Ogni Persona è una
configurazione — system prompt + contesto strategico, scope tool/entità/
servizi, scope memoria (`knowledge_access`), politica chat
(`max_chat_turns`, `require_confirmation`, `response_mode`) — mai uno
scheduling autonomo. Usa Claude Sonnet per la massima qualità di default.

### Sentinella — proattiva, lenti built-in

Un set fisso di **lenti** (detector/situazioni), ciascuna abilitabile e
tarabile singolarmente (selettore entità + soglie) dalla pagina di
configurazione Sentinella: `opening` (apertura prolungata),
`fridge_temp` (catena del freddo), `power` (consumo anomalo), `battery`
(batteria scarica), `hot_and_away` (fa caldo e non c'è nessuno →
suggerisce di accendere una valvola/relè per N minuti), `evening_arrival`
(rientro serale → suggerisce una scena). Un segnale da una lente sveglia
un reasoner LLM single-shot (Claude Haiku di default, ristretto a tool
di sola lettura) che decide se notificare e/o suggerire un'unica azione
a basso rischio, filtrata dal semaforo (tier + denylist domini
pericolosi) prima che venga davvero eseguita.

Esempio della risposta strutturata del reasoner (interna — non più una
sintassi da scrivere nel prompt utente):
```json
{"verdict": "anomalia", "severity": "warn", "message": "Consumo anomalo — lavatrice attiva da 3 ore", "action": null}
```

Le lenti definite dall'utente (trigger/prompt personalizzati, in
sostituzione dei vecchi agenti autonomi `monitor`/`reactive`/`preventive`)
sono previste in una versione successiva — oggi il livello proattivo
copre solo le lenti built-in elencate sopra.

---

## La Semantic Map

La Semantic Map è il "modello cognitivo" che HIRIS costruisce della casa. Mappa ogni entità HA a un **ruolo semantico** e una **label leggibile**.

### Pipeline di classificazione

```
Entità HA
    │
    ▼
[Regole keyword]  ← _solar, _temp, _motion, _door, domain rules…
    │
    ├─ Match trovato → classificata subito (ms, no LLM)
    │
    └─ No match → coda pending
                    │
                    ▼
            [Batch LLM, 20 entità/chiamata]
                    ├── Ollama locale (se configurato) → gratis, veloce
                    └── Claude (fallback) → preciso
```

La mappa è:
- Costruita al primo avvio (tutte le entità processate)
- Aggiornata in real time quando HA aggiunge nuove entità (`entity_registry_updated`)
- Persistente su `/data/home_semantic_map.json`, ricaricata ai riavvii

---

## LLM Router

`LLMRouter` è il layer di astrazione tra HIRIS e i modelli linguistici.

### Strategy e fallback

```
HIRIS (handlers, agents)
        │
        ▼
   LLMRouter (strategy: balanced / quality_first / cost_first)
   ├── claude  → ClaudeRunner (Anthropic SDK)
   ├── openai  → OpenAICompatRunner (OpenAI API)
   └── ollama  → OpenAICompatRunner (Ollama locale)
```

Con `model="auto"`:
- **balanced**: Claude → OpenRouter → OpenAI → Ollama
- **quality_first**: Claude → OpenAI → OpenRouter → Ollama
- **cost_first**: Ollama → OpenRouter → OpenAI → Claude

Se il backend primario fallisce, viene tentato automaticamente il successivo nella catena.

---

## Memoria e RAG

HIRIS salva le memorie degli agenti in SQLite con ricerca per similarità vettoriale (coseno puro Python — nessuna estensione nativa, compatibile Alpine/ARM).

- `recall_memory(query, k, tags)` — recupera le top-k memorie più simili alla query
- `save_memory(content, tags)` — salva una nuova memoria (solo agenti chat, per sicurezza)
- Le memorie sono marcate come dati non fidati nel system prompt (protezione prompt injection)
- Retention configurabile (default 90 giorni)

---

## Sicurezza e permessi

Ogni Persona può essere limitata tramite:

| Campo | Funzione | Esempio |
|---|---|---|
| `allowed_tools` | Whitelist tool utilizzabili | `["get_entity_states", "call_ha_service"]` |
| `allowed_entities` | Glob sugli entity ID accessibili | `["light.*", "climate.soggiorno"]` |
| `allowed_services` | Glob sui servizi chiamabili | `["light.*", "switch.turn_*"]` |
| `allowed_endpoints` | URL approvati per `http_request` | `[{"url": "https://api.example.com", ...}]` |
| `restrict_to_home` | Rifiuta domande off-topic | `true` |
| `require_confirmation` | Claude chiede conferma prima di agire | `true` |
| `knowledge_access` | Scope memoria (dati sensibili, quali kind) | `{"allow_sensitive": false, "kinds": "all"}` |
| `max_chat_turns` | Limita lunghezza conversazione | `20` |

Costi/token restano tracciati per Persona (visibili nella UI di
configurazione e via MQTT), ma non esiste più un tetto di budget per
Persona né un auto-disable — quel meccanismo è stato ritirato insieme ai
vecchi campi degli agenti autonomi.

Protezione SSRF su `http_request`: range RFC1918, IPv6 mapped-IPv4, loopback e link-local bloccati. Redirect disabilitati. Risposta cappata a 4KB.

---

## Persistenza su disco

| File | Contenuto |
|---|---|
| `/data/agents.json` | Configurazione di tutti gli agenti |
| `/data/usage.json` | Contatori token e costi per agente |
| `/data/home_semantic_map.json` | Classificazione semantica entità HA |
| `/data/chat_history.db` | SQLite: cronologia conversazioni + memorie |
| `/data/ha_health.json` | Snapshot salute HA (HealthMonitor — entità non disponibili, errori integrazioni, aggiornamenti) |
| `/data/proposals.db` | SQLite: proposte automazione con lifecycle (pending → applied/rejected/archived → eliminato) |

Tutti i file vengono scritti atomicamente (temp file + rename o commit SQLite via executor) per resistere ai crash.

---

## Costi e tracciamento

HIRIS traccia ogni richiesta per modello e per agente:

| Modello | Input (1M tok) | Output (1M tok) |
|---|---|---|
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.25 | $1.25 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| Ollama (locale) | gratis | gratis |

I dati sono consultabili via `/api/usage` e visibili nella UI di configurazione HIRIS per ogni agente.
