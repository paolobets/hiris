# HIRIS — Come funziona

> Versione: 0.2.2 · Aggiornato: 2026-04-22

---

## Cos'è HIRIS

**HIRIS** (Home Intelligent Reasoning & Integration System) è un Add-on per Home Assistant che aggiunge un layer di intelligenza artificiale alla smart home. Espone una chat in linguaggio naturale, monitora la casa in modo proattivo ed esegue automazioni ragionate tramite Claude (Anthropic) come motore di ragionamento.

HIRIS NON sostituisce HA — si affianca a esso. Le automazioni semplici (luci al tramonto, sveglia) restano nel Layer 1 locale; il ragionamento complesso, le anomalie, le domande in linguaggio libero vanno al Layer 2 AI.

---

## Architettura a due livelli

```
┌───────────────────────────────────────────────────────┐
│  LAYER 2 — Claude Agentic Loop                        │
│  • Chat in linguaggio naturale                        │
│  • Monitor proattivo (anomalie, consumi, clima)       │
│  • Ragionamento multi-sorgente (meteo + energia + HA) │
│  Modello: Claude Sonnet 4.6 (chat) / Haiku (monitor)  │
└───────────────────────────────────────────────────────┘
          ↕  tool calls (get/set HA entities)
┌───────────────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (locale, offline)       │
│  • Scheduler (APScheduler): ogni N minuti, cron       │
│  • Listener WebSocket: state_changed HA               │
│  • Azioni: chiamata servizio HA, notifica             │
└───────────────────────────────────────────────────────┘
          ↕  REST + WebSocket
┌───────────────────────────────────────────────────────┐
│  HOME ASSISTANT CORE                                  │
└───────────────────────────────────────────────────────┘
```

---

## Come ragiona HIRIS: il flusso di una richiesta chat

Quando l'utente scrive un messaggio, HIRIS esegue questi passi in sequenza:

### 1. Ricezione e routing

`POST /api/chat` → `handlers_chat.py`

- Legge `{message, agent_id}` dal body JSON
- Identifica l'agente richiesto (o usa il default `hiris-default`)
- Carica la cronologia della conversazione dal disco (`/data/chat_history_<id>.json`)
- Mantiene in contesto le ultime **30 coppie** domanda/risposta (le più vecchie restano su disco ma non vengono inviate a Claude, per risparmiare token ed evitare contesto stantio)

### 2. Costruzione del system prompt

Il system prompt che Claude riceve è composto a strati, nell'ordine:

```
[1] strategic_context dell'agente (es. "Sei il controllore della casa Rossi...")
[2] system_prompt dell'agente (istruzioni, tool disponibili, regole)
[3] --- separatore ---
[4] Semantic Map Snippet  ← snapshot live della casa (~5 righe)
[5] --- separatore ---
[6] RAG pre-fetch         ← entità rilevanti per QUESTO messaggio (top 12)
```

Esempio di come appare Claude il system prompt finale:

```
Sei HIRIS, assistente per la smart home...

---

CASA [mappa agg. 14:30]
Energia: sensor.potenza_rete(W), sensor.fotovoltaico(W)
Clima: climate.soggiorno(21.5°→22°C heating), climate.camera(20°→21°C idle)
Presenze: PIR Ingresso(off), PIR Salotto(on)
Luci: 18 entità / 5 stanze
Elettrodomestici: switch.lavatrice, switch.lavastoviglie

---

Entità rilevanti (dati in tempo reale):
- Soggiorno [light.soggiorno]: on
- Termostato Salotto [climate.soggiorno]: heat, corrente 21.5°C → setpoint 22°C (heating)
- Potenza Rete [sensor.potenza_rete]: 1243 W
```

### 3. RAG Pre-fetch (retrieval aumentato)

Prima ancora che Claude veda il messaggio, HIRIS:

1. Tokenizza il testo dell'utente (es. "accendi le luci del salotto")
2. Lo confronta con l'indice in-memory di tutte le entità (`EmbeddingIndex`)
3. Recupera le **12 entità più rilevanti** con il loro stato attuale dall'`EntityCache`
4. Le inietta come blocco finale del system prompt

Questo significa che Claude risponde **con dati live senza dover chiamare un tool** per i casi semplici. Il tool viene chiamato solo se servono informazioni più specifiche o per eseguire azioni.

### 4. Agentic loop (Claude + tool use)

Claude riceve: system prompt + history + messaggio utente.

Claude risponde con una di queste modalità:
- **Testo diretto** → risposta all'utente, fine
- **Tool call** → HIRIS esegue il tool, manda il risultato a Claude, Claude decide di nuovo

Il loop si ripete fino a **max 10 iterazioni** (protezione da loop infiniti). Claude decide autonomamente quando ha abbastanza informazioni per rispondere.

**Gestione errori API:**
- Codice 429/529 (rate limit): 3 retry con backoff esponenziale (5s → 15s → 45s)
- Tool che fallisce: restituisce un dict `{error: "..."}` invece di lanciare eccezione; Claude vede l'errore e può gestirlo

### 5. Risposta e persistenza

- La risposta torna al frontend come `{response: "...", debug: {tools_called: [...]}}`
- Il turno (utente + assistente) viene scritto su disco in modo atomico
- I token usati vengono contabilizzati per modello e per agente

---

## I tool disponibili

Claude può chiamare questi tool (ogni agente può avere una whitelist):

### Esplorazione entità

| Tool | Cosa fa | Input |
|---|---|---|
| `get_entity_states` | Stato attuale di entità specifiche per ID | `ids: [...]` |
| `get_home_status` | Panoramica compatta di tutta la casa (esclude noise) | — |
| `get_area_entities` | Mappa stanze → entità | — |
| `get_entities_on` | Tutte le entità in stato "on" | — |
| `search_entities` | Ricerca semantica per linguaggio naturale | `query, top_k, domain?` |
| `get_entities_by_domain` | Tutte le entità di un dominio (light, sensor…) | `domain` |

### Controllo casa

| Tool | Cosa fa | Input |
|---|---|---|
| `call_ha_service` | Chiama qualsiasi servizio HA | `domain, service, data?` |

Esempi: `light.turn_on {entity_id: "light.soggiorno"}`, `climate.set_temperature {temperature: 21}`, `switch.toggle`.

**Protezione:** ogni agente ha una lista di servizi permessi (`allowed_services`). Pattern fnmatch: `"light.*"` permette tutti i servizi luce ma non il termostato.

### Energia e meteo

| Tool | Cosa fa | Input |
|---|---|---|
| `get_energy_history` | Storico consumi/produzione N giorni | `days: 1-30` |
| `get_weather_forecast` | Previsioni meteo Open-Meteo (gratis, no chiave) | `hours: 1-168` |

Il meteo usa le coordinate geografiche di HA (`HA_LATITUDE`, `HA_LONGITUDE`).

L'energia legge automaticamente dalla Semantic Map le entità classificate come `energy_meter`, `solar_production`, `grid_import` — nessun hardcoding di ID.

### Automazioni HA

| Tool | Cosa fa | Input |
|---|---|---|
| `get_ha_automations` | Lista tutte le automazioni | — |
| `trigger_automation` | Esegue subito un'automazione | `automation_id` |
| `toggle_automation` | Abilita/disabilita | `automation_id, enabled` |

### Notifiche

| Tool | Cosa fa | Canali disponibili |
|---|---|---|
| `send_notification` | Invia messaggio | `ha_push`, `telegram`, `retropanel` |

---

## La Semantic Map

La Semantic Map è il "modello cognitivo" che HIRIS costruisce della casa. È un dizionario persistente che mappa ogni entità HA a un **ruolo semantico** (cosa è) e una **label leggibile** (come si chiama).

### Ruoli disponibili

| Ruolo | Esempi |
|---|---|
| `energy_meter` | Contatore consumi, wattmetro |
| `solar_production` | Inverter fotovoltaico |
| `grid_import` | Scambio rete |
| `climate_sensor` | Termostato, sensore temperatura |
| `presence` | PIR, radar mmWave, occupancy |
| `lighting` | Qualsiasi luce |
| `door_window` | Contatto porta/finestra |
| `appliance` | Lavatrice, lavastoviglie, forno, boiler |
| `electrical` | Tensione, corrente |
| `diagnostic` | Config changed, versioni |
| `other` / `unknown` | Non classificato |

### Pipeline di classificazione

```
Entità HA
    │
    ▼
[Regole keyword]  ←  _RULES: _solar, _temp, _motion, _door…
    │                _DOMAIN_RULES: light→lighting, climate→climate_sensor
    │
    ├─ Match trovato → classificata subito (ms, no LLM)
    │
    └─ No match → coda "pending"
                        │
                        ▼
                [LLM batch, 20 entità/chiamata]
                        │
                        ├─ Ollama locale (se configurato) → gratis, veloce
                        │
                        └─ Claude (fallback) → preciso
                                │
                                ▼
                        role + label + confidence
```

La classificazione avviene:
- **Al primo avvio**: tutte le entità vengono processate
- **In tempo reale**: quando HA aggiunge una nuova entità (evento `entity_registry_updated`)
- **Persistente**: salvata su `/data/home_semantic_map.json`, ricaricata ai riavvii

### Cosa entra nel system prompt

`get_prompt_snippet()` produce un blocco compatto (~5 righe) che Claude riceve ad ogni richiesta:

```
CASA [mappa agg. HH:MM]
Energia: sensor.pv(W), sensor.rete(W), sensor.consumo(W)
Clima: climate.soggiorno(21.5°→22°C heating), climate.camera(20°→21°C idle)
Presenze: PIR Ingresso(off), PIR Salotto(on)
Luci: 18 entità / 5 stanze
Elettrodomestici: switch.lavatrice, switch.lavastoviglie
```

Il timestamp `HH:MM` è granulare al minuto per ottimizzare la **prompt cache** di Anthropic: se il sistema prompt non cambia tra due richieste ravvicinate, il costo degli input token si riduce fino al ~90%.

---

## Il LLM Router

`LLMRouter` è il layer di astrazione tra HIRIS e i modelli linguistici. Espone la stessa interfaccia indipendentemente da quale modello è dietro.

### Architettura

```
HIRIS (handlers, agents)
        │
        ▼
   LLMRouter
   ├── chat() / run_with_actions()  →  ClaudeRunner (Anthropic API)
   │
   └── classify_entities()
       ├── OllamaBackend   se LOCAL_MODEL_URL configurato
       └── ClaudeRunner    fallback
```

### Perché separare la classificazione

Classificare le entità (task ripetitivo, bassa complessità) è diverso da rispondere all'utente (task complesso, alta qualità richiesta).

- **Chat/ragionamento** → sempre Claude (qualità massima, tool use nativo)
- **Classificazione batch** → Ollama locale se disponibile (gratis, veloce, nessuna latenza rete)

### Validazione della risposta LLM

Quando il modello restituisce la classificazione JSON, HIRIS valida:
- Il ruolo è uno dei ruoli validi (non accetta ruoli inventati)
- La label è al massimo 128 caratteri
- La confidence è tra 0 e 1
- Max 500 entità per risposta (protezione da output malevoli/malformati)
- Raw response cappato a 100.000 caratteri

---

## I tipi di agente

Ogni agente ha un `type` che determina quando e come viene attivato:

### `chat` — Agente conversazionale

Attivato dall'utente tramite UI. Usa Claude Sonnet (qualità massima).

```json
{
  "type": "chat",
  "trigger": {"type": "manual"},
  "model": "auto"
}
```

### `monitor` — Agente proattivo periodico

Si attiva ogni N minuti. Esamina la casa e notifica se trova anomalie.

```json
{
  "type": "monitor",
  "trigger": {"type": "schedule", "interval_minutes": 15},
  "model": "auto",
  "actions": [
    {"condition": "consumi > soglia", "action": "notifica"}
  ]
}
```

Risposta strutturata obbligatoria:
```
VALUTAZIONE: ANOMALIA
AZIONE: Consumo anomalo rilevato — lavatrice attiva da 3 ore
```

Usa Claude Haiku (economico) perché gira in modo continuativo.

### `reactive` — Agente event-driven

Si attiva quando un'entità HA cambia stato.

```json
{
  "type": "reactive",
  "trigger": {"type": "state_changed", "entity_id": "binary_sensor.porta_ingresso"}
}
```

Esempio: porta aperta a mezzanotte → Claude decide se notificare.

### `preventive` — Agente schedulato con cron

Si attiva a orari fissi (es. ogni mattina alle 7).

```json
{
  "type": "preventive",
  "trigger": {"type": "preventive", "cron": "0 7 * * *"}
}
```

Esempio: ogni mattina controlla meteo + consumi ieri → suggerisce ottimizzazioni.

---

## Sicurezza e permessi

Ogni agente può essere limitato a:

| Campo | Funzione | Esempio |
|---|---|---|
| `allowed_tools` | Whitelist tool utilizzabili | `["get_entity_states", "call_ha_service"]` |
| `allowed_entities` | Glob sugli entity ID accessibili | `["light.*", "climate.soggiorno"]` |
| `allowed_services` | Glob sui servizi chiamabili | `["light.*", "switch.turn_*"]` |
| `restrict_to_home` | Claude risponde solo a domande smart home | `true` |
| `require_confirmation` | Claude chiede conferma prima di agire | `true` |
| `budget_eur_limit` | Si auto-disabilita al superamento budget | `2.00` |
| `max_chat_turns` | Limita lunghezza conversazione | `20` |

---

## Infrastruttura locale

### EntityCache

Cache in-memory di tutti gli stati HA, aggiornata in tempo reale via WebSocket.

```
EntityCache._states = {
  "light.soggiorno": {id, state:"on", name:"Soggiorno", unit:""},
  "climate.soggiorno": {id, state:"heat", name:"...", attributes:{current_temperature:21.5, temperature:22, hvac_action:"heating"}},
  ...
}
```

Quando HA invia un evento `state_changed`, l'EntityCache aggiorna la entry corrispondente senza nessuna chiamata HTTP.

### EmbeddingIndex

Indice keyword-based per la ricerca semantica delle entità. Zero dipendenze ML — puro Python.

- Tokenizza nome e ID di ogni entità
- Calcola score per overlap di token con la query
- Ritorna i top-K più rilevanti per il RAG pre-fetch

### WebSocket HA

Connessione permanente a `ws://supervisor/core/api/websocket`. Sottoscrive:
- `state_changed` → aggiorna EntityCache
- `entity_registry_updated` → trigger classificazione nuove entità in SemanticMap

In caso di disconnessione: riconnessione automatica con backoff 10s.

---

## Configurazione (variabili d'ambiente)

| Variabile | Default | Descrizione |
|---|---|---|
| `CLAUDE_API_KEY` | — | **Obbligatoria.** Chiave Anthropic |
| `SUPERVISOR_TOKEN` | — | Iniettato automaticamente da HA Supervisor |
| `HA_BASE_URL` | `http://supervisor/core` | URL core HA |
| `PRIMARY_MODEL` | `claude-sonnet-4-6` | Modello Claude principale |
| `LOCAL_MODEL_URL` | `""` | URL Ollama per classificazione locale (es. `http://ollama:11434`) |
| `LOCAL_MODEL_NAME` | `""` | Nome modello Ollama (es. `mistral`, `llama3`) |
| `HA_LATITUDE` | `45.4642` | Latitudine per meteo Open-Meteo |
| `HA_LONGITUDE` | `9.1900` | Longitudine |
| `HA_NOTIFY_SERVICE` | `notify.notify` | Servizio HA per notifiche push |
| `TELEGRAM_TOKEN` | `""` | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | `""` | Chat ID Telegram |
| `RETROPANEL_URL` | `http://retropanel:8098` | URL Retro Panel per toast |
| `THEME` | `auto` | Tema UI: `light` / `dark` / `auto` |
| `LOG_LEVEL` | `info` | Livello log: `debug` / `info` / `error` |

Tutte le variabili sono impostate da `run.sh` leggendo le opzioni del config HA (`config.yaml`).

---

## Costi e tracciamento token

HIRIS traccia ogni richiesta per modello e per agente:

| Modello | Input (1M tok) | Output (1M tok) |
|---|---|---|
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.25 | $1.25 |
| claude-opus-4-7 | $15.00 | $75.00 |

I dati vengono salvati su `/data/usage.json` e sono consultabili da `/api/usage`.

**Budget per agente:** se `budget_eur_limit` è configurato, l'agente si auto-disabilita al superamento. Il controllo avviene ad ogni esecuzione.

**Prompt cache:** il system prompt è costruito in modo stabile (timestamp granulare al minuto) per massimizzare il riuso della cache Anthropic — fino al 90% di risparmio sui token di input per messaggi frequenti.

---

## Persistenza su disco

| File | Contenuto |
|---|---|
| `/data/agents.json` | Configurazione di tutti gli agenti |
| `/data/usage.json` | Contatori token e costi |
| `/data/home_semantic_map.json` | Classificazione semantica entità HA |
| `/data/chat_history_<agent_id>.json` | Cronologia chat per agente (30 giorni) |

Tutti i file vengono scritti atomicamente (temp file + rename) per resistere ai crash.

---

## Differenze tra spec e implementazione

Questa sezione documenta i punti dove l'implementazione reale diverge dalle specifiche di progetto (`docs/superpowers/specs/`).

### EmbeddingIndex: keyword overlap invece di fastembed

**Spec** (2026-04-20): usare `fastembed` con modello `intfloat/multilingual-e5-small` (120 MB, vettori 384-dim, ricerca coseno).

**Implementato**: token overlap puro Python, zero dipendenze ML.

Motivazione: `fastembed` usa `onnxruntime` che non compila su Alpine/musllinux (base Docker di HA). L'approccio keyword è istantaneo, senza download, deterministico. La qualità di ricerca è sufficiente per nomi di entità HA (es. "luce salotto" trova `light.soggiorno_principale`).

**Impatto**: `search_entities()` è meno accurata su query linguisticamente distanti dall'ID entità, ma funziona bene per i casi d'uso reali.

---

### LLMRouter: wrapper sottile, non orchestratore per complessità

**Spec**: il router avrebbe dovuto scegliere il modello in base alla complessità della richiesta (bassa → Ollama locale, alta → Claude).

**Implementato**: `LLMRouter` è un thin wrapper attorno a `ClaudeRunner`. L'unico routing reale è in `classify_entities()` → Ollama se configurato, Claude altrimenti. La chat principale va sempre su Claude.

**Motivazione**: il routing per complessità richiederebbe una stima della complessità prima della risposta — un problema difficile. Il routing per tipo di task (classificazione vs chat) è invece naturale e già implementato.

---

### Doppio sistema contesto casa (home_profile + semantic_map snippet)

Esistono due sistemi che generano il contesto della casa per il system prompt:

| Sistema | File | Quando usato |
|---|---|---|
| `SemanticMap.get_prompt_snippet()` | `proxy/semantic_map.py` | `handlers_chat.py` — normale flusso chat |
| `get_cached_home_profile()` | `proxy/home_profile.py` | `claude_runner.py` — solo se `semantic_map is None` |

In pratica: se la Semantic Map è attiva (configurazione normale), `home_profile` non viene mai iniettato nella chat. È un fallback per installazioni senza Semantic Map.

Il commento in `handlers_chat.py` lo spiega: `# Inject semantic map snippet (replaces home_profile — richer context)`.

---

### LLMResponse dataclass: non implementata

**Spec**: `chat()` avrebbe dovuto restituire un oggetto `LLMResponse(content, tool_calls, stop_reason, usage)`.

**Implementato**: le funzioni restituiscono `str` o `dict` direttamente. Non c'è overhead di wrapping — è più semplice e il codice chiamante non ne aveva bisogno.

---

### Funzionalità pianificate ma non ancora implementate

| Funzionalità | Spec | Stato |
|---|---|---|
| Test Runner per agente | `hiris-design.md` | Non implementato |
| Template agenti pre-costruiti | `hiris-design.md` | Solo campo `strategic_context` libero |
| Canvas drag-and-drop (n8n style) | `hiris-design.md` | Phase 2 |
| Plugin Retro Panel | `hiris-design.md` | Phase 2 |
| Memoria conversazione Redis/SQLite | `hiris-design.md` | Phase 2 |
