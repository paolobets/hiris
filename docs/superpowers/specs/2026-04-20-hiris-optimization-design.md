# HIRIS — Ottimizzazione Token, C-complete, Per-Agent Config, UX Azioni

**Data:** 2026-04-20  
**Versione target:** v0.0.9 → v0.1.0 → v0.1.1  
**Autore:** Paolo + Claude (brainstorming session)

---

## Contesto e motivazione

### Problema rilevato
La casa ha **606 entità** in Home Assistant. Ogni volta che Claude chiama
`get_entity_states([])` (comportamento default), riceve **67.771 token** di dati
— $0,2033 per singola chiamata con Sonnet. Una conversazione di 5 domande
può esaurire il budget TPM (tokens-per-minute) Anthropic in pochi minuti.
Il rate limit è già stato colpito in produzione.

### Causa radice
L'architettura attuale non ha nessun layer di filtraggio tra HA e Claude:
- `get_entity_states([])` scarica tutte le 606 entità con attributi completi
- 181 entità sono "rumore" (button, update, number, select) — mai utili
- Il formato JSON completo è 88% più grande del necessario
- Non esiste routing intelligente: Sonnet viene usato anche per query banali
- `restrict_to_home` e `max_tokens` sono globali, non per-agente

### Dati reali (rilevati il 2026-04-20)
```
Entità totali:           606
Token baseline (full):   67.771  →  $0,2033/call Sonnet
Token formato minimale:  14.848  →  $0,0445/call  (-79%)
Token senza rumore:      10.047  →  $0,0301/call  (-86%)
Token solo ON:            1.316  →  $0,0039/call  (-99%)
Entità "rumore" (181):   button(63) + update(54) + number(34) + select(19) + altri
Entità solare (16):      sensor.ze1es030n5e528_*  →  1.355 token  (-99%)
```

---

## Architettura target

```
User query
    │
    ▼
handlers_chat.py
    │  legge agent config: model, max_tokens, restrict, allowed_entities
    ▼
EntityCache (in-memory, aggiornata via WebSocket)
    │  serve i dati lokalmente senza HTTP verso HA
    ▼
EmbeddingIndex (fastembed, multilingual-e5-small, ~120MB)
    │  converte query in vettore, trova entità semanticamente rilevanti
    ▼
ClaudeRunner.chat(model, max_tokens, restrict_to_home)
    │  nuovi tool ottimizzati (get_home_status, get_entities_on, search_entities...)
    ▼
Anthropic API  (modello scelto per-agente)
    │
    ▼
Response + debug (tool calls, tokens usati)
```

---

## Ciclo 1 — Ottimizzazione token (v0.0.9)

**Obiettivo:** eliminare i rate limit. Ridurre il costo medio per query da
$0,20 a $0,005–$0,03 senza degradare la qualità delle risposte.

### 1.1 EntityCache — cache in-memory aggiornata via WebSocket

**File:** `hiris/app/proxy/entity_cache.py` (nuovo)

Classe `EntityCache` che:
- Al startup carica tutti gli stati via `GET /api/states` (una volta)
- Aggiorna la cache on ogni evento `state_changed` dal WebSocket già attivo
- Espone metodi di query locali (nessuna chiamata HTTP)
- Mantiene anche il registry delle aree (`get_area_registry()`)

```python
class EntityCache:
    def __init__(self) -> None:
        self._states: dict[str, dict] = {}  # entity_id → stato minimale
        self._by_domain: dict[str, list[str]] = {}  # domain → [entity_ids]
        self._by_area: dict[str, list[str]] = {}    # area_id → [entity_ids]

    async def load(self, ha_client: HAClient) -> None:
        """Carica tutti gli stati al startup."""

    def on_state_changed(self, event_data: dict) -> None:
        """Callback per aggiornamento real-time via WebSocket."""

    def get_minimal(self, entity_ids: list[str]) -> list[dict]:
        """Restituisce {id, state, name, unit} — formato compatto."""

    def get_by_domain(self, domain: str) -> list[dict]:
        """Tutte le entità di un dominio, formato minimale."""

    def get_on(self) -> list[dict]:
        """Solo entità con state='on', formato minimale."""

    def get_all_useful(self) -> list[dict]:
        """Tutte le entità meno i domini rumore, formato minimale."""
```

**Formato minimale** (vs JSON completo):
```python
# Prima: 670 chars / 167 token per entità
{"entity_id":"sensor.epson_wf_2850_series","state":"idle","attributes":{...molti campi...}}

# Dopo: 81 chars / 20 token per entità
{"id":"sensor.epson_wf_2850_series","state":"idle","name":"Epson WF","unit":""}
```

**Domini esclusi per default** (NOISE_DOMAINS):
```python
NOISE_DOMAINS = {"button", "update", "number", "select", "tag",
                 "event", "ai_task", "todo", "conversation"}
```

### 1.2 EmbeddingIndex — ricerca semantica con fastembed

**File:** `hiris/app/proxy/embedding_index.py` (nuovo)

Usa `fastembed` con modello `intfloat/multilingual-e5-small` (~120MB):
- Supporto nativo italiano (friendly names sono in italiano)
- Dimensioni embedding: 384
- Latenza query: ~15-30ms
- RAM runtime: ~55MB modello + ~1MB per 606 vettori

```python
class EmbeddingIndex:
    def __init__(self) -> None:
        self._model = None          # TextEmbedding lazy-loaded
        self._entity_ids: list[str] = []
        self._matrix = None         # numpy array shape (N, 384)

    async def build(self, entities: list[dict]) -> None:
        """Indicizza tutte le entità dalla cache (friendly_name + entity_id)."""
        # Testo indicizzato: "luce soggiorno [light.soggiorno]"
        # Comprende sia il nome italiano che il dominio

    def search(self, query: str, top_k: int = 30,
               domain_filter: str | None = None) -> list[str]:
        """Restituisce i top_k entity_id più rilevanti per la query."""

    def rebuild_entity(self, entity_id: str, friendly_name: str) -> None:
        """Aggiorna il vettore di una singola entità (on state_changed)."""
```

**Testo indicizzato per entità:**
```
"SOLARE Potenza prodotta [sensor potenza]"
"Luce Soggiorno [light soggiorno]"  
"Termostato Camera [climate camera]"
```
Questo garantisce che sia il nome italiano che il dominio siano cercabili.

**Integrazione con EntityCache:**
`EmbeddingIndex.search("cosa ho acceso in soggiorno")` → restituisce entity_id
→ `EntityCache.get_minimal(entity_ids)` → formato compatto → a Claude

### 1.3 Nuovi tool ottimizzati

**File:** `hiris/app/tools/ha_tools.py` (modificato)

I nuovi tool usano `EntityCache` + `EmbeddingIndex` invece di chiamare HA HTTP.

```python
# NUOVO: stato casa senza rumore, formato minimale
get_home_status()
# → EntityCache.get_all_useful()
# → max 424 entità, ~10.000 token (vs 67.771)

# NUOVO: solo entità ON
get_entities_on()
# → EntityCache.get_on()
# → 53 entità, ~1.316 token

# NUOVO: ricerca semantica
search_entities(query: str, top_k: int = 30)
# → EmbeddingIndex.search(query) + EntityCache.get_minimal()
# → es. "cosa consuma la cucina" → 8-15 entità rilevanti, ~400 token

# NUOVO: per dominio
get_entities_by_domain(domain: str)
# → EntityCache.get_by_domain(domain)
# → es. "light" → 51 entità, ~1.200 token

# ESISTENTE: mantenuto per ID specifici
get_entity_states(ids: list[str])
# → EntityCache.get_minimal(ids) se ids non vuoto
# → get_home_status() se ids vuoto (non più "tutto raw")
```

**Tool definitions aggiornate** (cosa vede Claude):
```python
SEARCH_ENTITIES_TOOL = {
    "name": "search_entities",
    "description": (
        "Cerca entità Home Assistant rilevanti per la query usando ricerca semantica. "
        "Usalo quando non conosci gli entity_id esatti. "
        "Esempi: search_entities('consumi cucina'), search_entities('temperatura camera'), "
        "search_entities('cosa è acceso'). Restituisce solo le entità pertinenti."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Cosa cerchi in linguaggio naturale"},
            "top_k": {"type": "integer", "description": "Max risultati (default 20)", "default": 20}
        },
        "required": ["query"]
    }
}
```

### 1.4 Integrazione in AgentEngine e server.py

**File:** `hiris/app/server.py`, `hiris/app/agent_engine.py`

Al startup:
```python
cache = EntityCache()
await cache.load(ha_client)
ha_client.add_state_listener(cache.on_state_changed)

index = EmbeddingIndex()
await index.build(cache.get_all_useful())  # async, ~3-5s
app["entity_cache"] = cache
app["embedding_index"] = index
```

`ClaudeRunner` riceve `cache` e `index` e li passa ai tool dispatch.

### 1.5 Dipendenze

Aggiungere a `requirements.txt`:
```
fastembed>=0.3.0
numpy>=1.24.0
```

Modello scaricato automaticamente al primo avvio (~120MB, cached in `/data/fastembed_cache/`).

### 1.6 Impatto atteso

| Scenario | Prima | Dopo | Risparmio |
|---|---|---|---|
| "Cosa ho acceso?" | 67.771 tok | ~1.316 tok | -98% |
| "Luci soggiorno" | 67.771 tok | ~400 tok | -99% |
| "Consumi solare" | 67.771 tok | ~1.355 tok | -98% |
| "Stato casa generale" | 67.771 tok | ~10.047 tok | -85% |
| Costo/query Sonnet | $0,20 | $0,004–$0,030 | -85/98% |
| Costo/query Haiku | $0,017 | $0,0003–$0,003 | -98% |

---

## Ciclo 2 — Per-Agent Config + UX Azioni (v0.1.0)

**Obiettivo:** rendere ogni agente autonomamente configurabile per modello,
limiti, restrizioni e azioni permesse. Rimuovere tutte le configurazioni
globali dall'add-on HA.

### 2.1 Nuovi campi Agent dataclass

```python
@dataclass
class Agent:
    # ... campi esistenti ...
    model: str = "auto"              # auto|haiku|sonnet|opus
    restrict_to_home: bool = False   # rimosso da config globale
    max_tokens: int = 4096           # 256-8192
```

**Logica "auto":**
```python
AUTO_MODEL_MAP = {
    "chat":       "claude-sonnet-4-6",
    "monitor":    "claude-haiku-4-5",
    "reactive":   "claude-haiku-4-5",
    "preventive": "claude-haiku-4-5",
}
```

**Risparmio modello auto:**
- Agenti monitor/reactive/preventive → Haiku → costo ÷12 vs Sonnet

### 2.2 Rimozione configurazione globale

**Rimuovere da `hiris/config.yaml`:**
```yaml
# RIMUOVERE:
restrict_chat_to_home: false
```

**Rimuovere da `hiris/run.sh`:**
```bash
# RIMUOVERE:
export RESTRICT_CHAT_TO_HOME=...
```

**ClaudeRunner:** `restrict_to_home` diventa parametro di `chat()`, non di `__init__()`.

### 2.3 Home Profile nel system prompt

**File:** `hiris/app/proxy/home_profile.py` (nuovo)

Genera un profilo compatto (~300 token) da includere nel system prompt
degli agenti. Aggiornato ogni 5 minuti dalla cache.

```
CASA [aggiornato 14:32]:
Aree: soggiorno, cucina, camera, bagno, studio, esterno
Accesi(53): switch(28) automation(14) binary_sensor(8) light(2) input_boolean(1)
Clima: nessun termostato attivo
Solare: produzione=1520W batteria=20% consumo=430W rete=0W
Meteo: soleggiato 18°C, domani nuvoloso
```

Agenti chat semplici rispondono senza tool call → 1 API call invece di 2.

### 2.4 Tab "Azioni" nel designer

**File:** `hiris/app/static/config.html`

Sostituisce la textarea `allowed_services` con interfaccia guidata:

```
COSA PUÒ FARE QUESTO AGENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Luci
  ☑ Accendere/spegnere    ☐ Dimmer e colore

🔌 Prese e switch
  ☑ Accendere/spegnere

🌡 Clima
  ☐ Regolare temperatura  ☐ Cambiare modalità

🔔 Notifiche
  ☑ Push HA    ☑ Telegram    ☐ RetroPanel

⚡ Automazioni
  ☑ Attivare    ☐ Abilitare/disabilitare

🎬 Scene e script
  ☐ Attivare scene   ☐ Eseguire script

🔧 Avanzato (servizi specifici)
  [textarea libera per pattern domain.service]
```

Ogni checkbox si traduce in `allowed_services` patterns internamente.

### 2.5 Rate limit handling

**File:** `hiris/app/claude_runner.py`

Retry con exponential backoff su errori `429` (rate limit) e `529` (overloaded):
```python
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]  # secondi

# Risposta utente durante retry:
"[Limite API raggiunto — riprovo tra 5s...]"
```

Aggiunta al widget usage: contatore errori rate limit.

---

## Ciclo 3 — Robustezza e Template (v0.1.1)

**Obiettivo:** rendere il sistema solido per uso quotidiano prolungato.

### 3.1 Strategic Context templates

Template pre-compilati nel designer per agenti comuni.
L'utente seleziona il template e personalizza i campi chiave.

```
Template: Monitor Energia Solare
────────────────────────────────
SISTEMA ENERGETICO:
- Produzione: sensor.{{solare_id}}_potenza_prodotta
- Batteria: sensor.{{solare_id}}_batteria (%)
- Consumo: sensor.{{solare_id}}_potenza_consumata
- Rete: sensor.{{solare_id}}_potenza_importata

SOGLIE:
- Allarme rete: importata > 100W per 15+ min
- Batteria critica: < 15%
- Surplus solare: esportata > 300W (usa ora)

CARICHI DIFFERIBILI: {{lista dispositivi}}
```

Altri template: Sicurezza Casa, Presenza Famiglia,
Monitor Clima, Risparmio Energetico.

### 3.2 Require confirmation per azioni

Campo `require_confirmation: bool = False` su Agent.

Se `True`, l'agente che vuole eseguire un'azione (`call_ha_service`)
risponde con una proposta invece di agire:
```
"Proposta: spegnere climate.soggiorno per risparmiare energia.
 Conferma? [Sì/No]"
```

La conferma arriva via chat → agente esegue.

### 3.3 Agent execution log / visibility

Pannello "Log esecuzioni" nel designer:
- Timestamp + trigger di ogni run
- Tool calls usati
- Token consumati
- Risultato (successo/errore/notifica inviata)
- Storico ultimi 20 run per agente

---

## Tavola riepilogativa completa

| # | Intervento | Ciclo | Priorità | File chiave |
|---|---|---|---|---|
| 1 | EntityCache in-memory + WebSocket | 1 | 🔴 | `proxy/entity_cache.py` |
| 2 | Formato minimale {id,state,name,unit} | 1 | 🔴 | `entity_cache.py` |
| 3 | Domain noise filter (181 entità) | 1 | 🔴 | `entity_cache.py` |
| 4 | EmbeddingIndex fastembed multilingual | 1 | 🔴 | `proxy/embedding_index.py` |
| 5 | Nuovi tool ottimizzati (5 tool) | 1 | 🔴 | `tools/ha_tools.py` |
| 6 | Deprecare get_entity_states([]) raw | 1 | 🔴 | `tools/ha_tools.py` |
| 7 | Per-agent model (auto/haiku/sonnet/opus) | 2 | 🟠 | `agent_engine.py`, `config.html` |
| 8 | Per-agent max_tokens (256-8192) | 2 | 🟡 | `agent_engine.py`, `config.html` |
| 9 | restrict_to_home per-agente, rimuovi globale | 2 | 🟡 | `server.py`, `config.yaml`, `run.sh` |
| 10 | Home Profile nel system prompt | 2 | 🟡 | `proxy/home_profile.py` |
| 11 | Tab Azioni guidata nel designer | 2 | 🟡 | `static/config.html` |
| 12 | Rate limit retry + feedback utente | 2 | 🟡 | `claude_runner.py` |
| 13 | Strategic Context templates | 3 | 🟢 | `static/config.html` |
| 14 | Require confirmation per azioni | 3 | 🟢 | `agent_engine.py`, `handlers_chat.py` |
| 15 | Agent execution log / visibility | 3 | 🟢 | `static/config.html`, `agent_engine.py` |

---

## Vincoli e decisioni architetturali

### Modello embedding scelto
`intfloat/multilingual-e5-small` via `fastembed`:
- Supporto italiano nativo ✅
- Dimensione: ~120MB (scaricato una volta, cached in `/data/fastembed_cache/`)
- RAM runtime: ~55MB modello + <1MB vettori
- Latenza query: 15-30ms

### Compatibilità backward
- `get_entity_states(ids)` con lista non vuota: invariato (usa cache)
- `get_entity_states([])`: reindirizzato a `get_home_status()` — breaking change solo per agenti con system prompt che forza la chiamata diretta. La migrazione avviene aggiornando il default agent system prompt.
- `agents.json`: i nuovi campi hanno default → nessuna migrazione manuale

### Sequenza avvio addon (dopo ottimizzazione)
```
1. HAClient.start()           → sessione HTTP
2. EntityCache.load()         → carica 606 entità (~0.5s)
3. HAClient.start_websocket() → subscribe state_changed
4. EmbeddingIndex.build()     → indicizza entità (~3-5s, async)
5. AgentEngine.start()        → scheduler + agenti
6. Server HTTP pronto
```
L'app risponde alle richieste HTTP anche durante il build dell'index
(fase 4), usando un fallback su `get_home_status()` grezzo finché
l'index non è pronto.

---

## Verifica per ogni ciclo

**Ciclo 1:**
```bash
py -m pytest tests/ -v          # tutti i test passano
```
UAT:
1. "Cosa ho acceso?" → log mostra ~1.316 token (non 67.771)
2. "Luci del soggiorno" → solo entità light + area soggiorno
3. "Consumi solare" → solo sensor.ze1es030n5e528_*
4. Widget usage mostra costo drasticamente ridotto
5. 10 domande di fila → nessun rate limit error

**Ciclo 2:**
1. Agente monitor con model=haiku → usage mostra costo Haiku
2. restrict_to_home su agente singolo → altri agenti non limitati
3. Tab Azioni → selezionare "Notifiche Telegram" → saved correttamente

**Ciclo 3:**
1. Template "Monitor Energia" → pre-compila strategic context
2. Agente con require_confirmation=true → propone azione, aspetta
3. Log esecuzioni → mostra storico ultimi 20 run
