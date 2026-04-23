# SemanticContextMap Design

> **Versione:** 2.0 · **Data:** 2026-04-23

## Goal

Sostituire il sistema RAG keyword-based (`EmbeddingIndex`) e lo snippet generico di `SemanticMap` con una **SemanticContextMap** — knowledge base persistente della casa, organizzata per area, classificata tramite la tassonomia nativa di Home Assistant (`device_class` + domain), arricchita nel tempo dagli agenti, e interrogata semanticamente ad ogni richiesta per iniettare nel prompt solo il contesto pertinente.

---

## Problemi risolti

| Problema attuale | Soluzione |
|---|---|
| RAG keyword brittle: "termostato" non matcha `climate.bagno` | Classificazione per domain+device_class + ricerca semantica |
| Claude dice "nessun termostato in bagno" quando esiste | Overview per area lista esplicitamente i tipi presenti |
| Sensori non pertinenti iniettati nel prompt | Retrieval mirato per area e tipo entity |
| `allowed_entities` non applicato uniformemente | SemanticContextMap filtrata = confine unico di visibilità |
| Classificazioni LLM rifatte ad ogni restart | Persistenza SQLite — lavoro non ripetuto |
| Agenti non accumulano conoscenza | Annotation + correlation layer in SQLite |

---

## Architettura a tre layer

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 3 — Semantic Search (opzionale)                  │
│  ChromaDB embedded                                      │
│  Attivo solo se EmbeddingBackend configurato            │
│  Similarity search: "fa freddo" → climate.bagno        │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — Knowledge Base persistente (sempre attivo)   │
│  SQLite: hiris_knowledge.db                             │
│  entity_classifications · entity_annotations           │
│  entity_correlations · query_patterns                  │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — Stati live (sempre attivo)                   │
│  EntityCache in-memory                                  │
│  Aggiornato in real-time via WebSocket HA               │
└─────────────────────────────────────────────────────────┘
```

---

## EmbeddingBackend — astrazione pluggabile

Stesso pattern del `LLMBackend` esistente. ChromaDB usa il backend configurato per generare embedding — stessa collection, API invariata, backend intercambiabile.

```python
class EmbeddingBackend(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def available(self) -> bool: ...

class NoEmbeddingBackend(EmbeddingBackend):
    """Default — nessun embedding, keyword ContextSelector only."""
    available = False

class VoyageEmbeddingBackend(EmbeddingBackend):
    """Anthropic Voyage API — stesso account Claude, modello voyage-3-lite."""
    available = True  # se CLAUDE_API_KEY configurata

class OllamaEmbeddingBackend(EmbeddingBackend):
    """Ollama locale — modello nomic-embed-text o configurabile."""
    available = True  # se LOCAL_MODEL_URL configurata
```

### Scenari utente

| Configurazione | LLM | Embedding | Modalità ricerca |
|---|---|---|---|
| Solo Claude API | Claude | Voyage API | Semantic (ChromaDB + Voyage) |
| Solo Ollama | Ollama LLM | Ollama embed | Semantic (ChromaDB + Ollama) |
| Claude + Ollama | Claude | Ollama embed | Semantic (ChromaDB + Ollama) |
| Nessuno | — | — | Keyword (ContextSelector) |

Voyage è disponibile automaticamente a chi ha già `CLAUDE_API_KEY` — nessuna configurazione extra richiesta. Ollama usa l'endpoint `/api/embeddings` separato dal chat, con modello configurabile (`nomic-embed-text` default).

---

## ENTITY_TYPE_SCHEMA

Fonte di verità per classificare ogni entity in base a `domain` + `device_class` (attributo nativo HA). Per ogni tipo: label italiano e attributi da estrarre.

### Domini con classificazione diretta

| Domain | Tipo | Label IT | Attributi estratti |
|---|---|---|---|
| `climate` | `climate` | Termostato | `hvac_mode`, `hvac_action`, `current_temperature`, `temperature`, `preset_mode` |
| `light` | `light` | Luce | `state`, `brightness` (→ %), `color_temp` |
| `cover` | `cover` | Tapparella | `state`, `current_position` (%) |
| `media_player` | `media_player` | Media | `state`, `media_title`, `media_artist`, `source`, `volume_level` (→ %) |
| `lock` | `lock` | Serratura | `state` |
| `alarm_control_panel` | `alarm` | Allarme | `state` |
| `vacuum` | `vacuum` | Robot | `state`, `battery_level` |
| `fan` | `fan` | Ventilatore | `state`, `percentage`, `preset_mode` |
| `water_heater` | `water_heater` | Scaldabagno | `current_temperature`, `temperature`, `operation_mode` |
| `switch` | `switch` | Interruttore | `state` |
| `input_boolean` | `switch` | Interruttore | `state` |

### `sensor` — per device_class

| device_class | Tipo | Label IT | Attributi |
|---|---|---|---|
| `temperature` | `temperature` | Temperatura | `state`, `unit_of_measurement` |
| `humidity` | `humidity` | Umidità | `state`, `unit_of_measurement` |
| `power` | `power` | Potenza | `state`, `unit_of_measurement` |
| `energy` | `energy` | Energia | `state`, `unit_of_measurement` |
| `battery` | `battery` | Batteria | `state`, `unit_of_measurement` |
| `illuminance` | `illuminance` | Luminosità | `state`, `unit_of_measurement` |
| `co2` | `co2` | CO₂ | `state`, `unit_of_measurement` |
| `pm25` | `pm25` | PM2.5 | `state`, `unit_of_measurement` |
| `pressure` | `pressure` | Pressione | `state`, `unit_of_measurement` |
| `voltage` | `voltage` | Tensione | `state`, `unit_of_measurement` |
| `current` | `current` | Corrente | `state`, `unit_of_measurement` |
| `gas` | `gas` | Gas | `state`, `unit_of_measurement` |
| `water` | `water` | Acqua | `state`, `unit_of_measurement` |
| *(nessuno)* | `sensor` | Sensore | `state`, `unit_of_measurement` |

### `binary_sensor` — per device_class

| device_class | Tipo | Label IT | Stato |
|---|---|---|---|
| `motion` / `occupancy` | `motion` | Presenza | on=rilevato · off=assente |
| `door` | `door` | Porta | on=aperta · off=chiusa |
| `window` | `window` | Finestra | on=aperta · off=chiusa |
| `presence` | `presence` | Presenza | on=casa · off=assente |
| `smoke` | `smoke` | Fumo | on=rilevato · off=ok |
| `moisture` | `moisture` | Perdita | on=bagnato · off=asciutto |
| `vibration` | `vibration` | Vibrazione | on=rilevata · off=ok |
| `connectivity` | `connectivity` | Connessione | on=ok · off=persa |
| *(nessuno)* | `binary` | Sensore | on/off |

### Priorità di classificazione

1. `domain` + `device_class` → ENTITY_TYPE_SCHEMA (fonte primaria, nessun costo)
2. `domain` solo → fallback per domini diretti (climate, light, cover…)
3. LLM (Claude o Ollama) → fallback per entity senza device_class riconosciuto
4. Classificazione salvata in SQLite → non viene ripetuta ai restart successivi

---

## Layer 2 — SQLite: `hiris_knowledge.db`

Sempre attivo, indipendente dagli embedding.

```sql
-- Classificazioni persistenti (evita ricalcolo ad ogni restart)
CREATE TABLE entity_classifications (
    entity_id        TEXT PRIMARY KEY,
    area             TEXT,              -- NULL se non assegnata
    entity_type      TEXT,              -- 'climate', 'temperature', 'light'…
    label_it         TEXT,              -- 'Termostato', 'Luce'…
    friendly_name    TEXT,
    domain           TEXT,
    device_class     TEXT,
    classified_by    TEXT,              -- 'schema', 'llm', 'user'
    confidence       REAL DEFAULT 1.0,
    created_at       TEXT,
    updated_at       TEXT
);

-- Annotazioni apprese dagli agenti o dall'utente
CREATE TABLE entity_annotations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id    TEXT,
    source       TEXT,    -- 'user', agent_id, 'system'
    annotation   TEXT,    -- testo libero: "scalda lentamente", "sensore inaffidabile"
    created_at   TEXT
);

-- Correlazioni osservate tra entity
CREATE TABLE entity_correlations (
    entity_a         TEXT,
    entity_b         TEXT,
    correlation_type TEXT,   -- 'triggers', 'co-occurs', 'inverse'
    confidence       REAL,
    observed_count   INTEGER DEFAULT 1,
    last_observed    TEXT,
    PRIMARY KEY (entity_a, entity_b, correlation_type)
);

-- Pattern d'uso: quali entity vengono chieste insieme
CREATE TABLE query_patterns (
    entity_id    TEXT,
    concept_type TEXT,   -- 'climate', 'energy'…
    hit_count    INTEGER DEFAULT 1,
    last_hit     TEXT,
    PRIMARY KEY (entity_id, concept_type)
);
```

### Ciclo di apprendimento

1. **Startup** — carica `entity_classifications` da SQLite, evita ricalcolo
2. **Nuova entity** — classifica via schema → LLM se necessario → salva in SQLite
3. **Ogni richiesta** — incrementa `query_patterns.hit_count` per le entity iniettate
4. **Agente nota qualcosa** — inserisce riga in `entity_annotations`
   (`"climate.bagno scalda da 3h senza raggiungere setpoint"`)
5. **Correlazione rilevata** — quando entity A cambia e B segue sistematicamente → `entity_correlations`
6. **Correzione utente** — aggiorna `entity_classifications` con `classified_by='user'`

---

## Layer 3 — ChromaDB (opzionale)

Attivato automaticamente quando `EmbeddingBackend.available == True`.

### Documento per entity

```python
collection.upsert(
    ids=["climate.bagno"],
    documents=[
        "Termostato Bagno — dispositivo riscaldamento area bagno. "
        "Modalità: heat. Temperatura attuale 21.5°C, setpoint 22°C. "
        "Annotazioni: scalda lentamente in inverno."
    ],
    metadatas=[{
        "area": "Bagno",
        "entity_type": "climate",
        "label_it": "Termostato",
        "domain": "climate",
        "device_class": None,
        "classified_by": "schema",
    }]
)
```

Il testo del documento include annotazioni da SQLite — la ricerca semantica beneficia dell'arricchimento accumulato.

### Query semantica

```python
results = collection.query(
    query_texts=[user_message],
    n_results=15,
    where={"area": {"$in": agent_allowed_areas}},  # filtro permessi
)
# → entity_ids più semanticamente rilevanti
# → stati live letti da EntityCache
```

### Sincronizzazione ChromaDB ↔ SQLite

- Nuova entity → upsert in entrambi
- Annotazione aggiunta in SQLite → rigenera documento ChromaDB per quell'entity
- Classificazione corretta da utente → aggiorna metadata ChromaDB

---

## ContextSelector — modalità keyword (fallback)

Usato quando ChromaDB non è disponibile. Dizionario fisso concetti → tipi:

```python
CONCEPT_TO_TYPES = {
    "termostato": ["climate"], "riscaldamento": ["climate"],
    "caldo": ["climate", "temperature"], "freddo": ["climate", "temperature"],
    "luce": ["light"], "luci": ["light"], "illuminazione": ["light"],
    "consumo": ["power", "energy"], "energia": ["energy"], "watt": ["power"],
    "movimento": ["motion"], "presenza": ["motion", "presence"],
    "porta": ["door"], "finestra": ["window"],
    "tapparella": ["cover"], "veneziana": ["cover"],
    "tv": ["media_player"], "musica": ["media_player"], "volume": ["media_player"],
    "umidità": ["humidity"], "temperatura": ["climate", "temperature"],
    "serratura": ["lock"], "allarme": ["alarm"],
    "robot": ["vacuum"], "aspirapolvere": ["vacuum"],
    "lavatrice": ["switch"], "lavastoviglie": ["switch"],
}
```

Logica: area match + concept match → sezione espansa. Nessun match → solo overview.

---

## Permission model

### Visibilità (`allowed_entities`)

```python
SemanticContextMap.get_context(
    query: str,
    entity_cache: EntityCache,
    allowed_entities: list[str] | None = None,
) -> tuple[str, frozenset[str]]
# Returns: (prompt_context, visible_entity_ids)
```

Filtraggio applicato prima del retrieval (sia ChromaDB `where` clause, sia keyword filter). `visible_entity_ids` = entity accessibili dall'agente in questa chiamata.

### Controllo (`allowed_services`)

Invariato — verificato in `_dispatch_tool` per `call_ha_service` e `create_task`.

### Validazione tool call

```python
# In claude_runner._dispatch_tool:
if entity_id not in self._visible_entity_ids:
    return {"error": f"Entity {entity_id} non accessibile da questo agente"}
```

### Tabella permessi

| In `allowed_entities` | In `allowed_services` | Vede nel prompt | Può controllare |
|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ |
| ✅ | ❌ | ✅ | ❌ |
| ❌ | qualsiasi | ❌ | ❌ |

---

## Formato prompt iniettato

**Overview compatto** (sempre, ~80 token):
```
CASA — 4 aree [agg. 14:32]
  Bagno:      Termostato · Temperatura · Umidità · Luce
  Soggiorno:  Luci×2 · Temperatura · Presenza · TV
  Camera:     Termostato · Temperatura · Luce
  Cucina:     Temperatura · Presenza · Interruttore×2
[Non assegnate: Potenza · Energia]
```

**Dettaglio espanso** (solo aree/tipi rilevanti, ~150 token per area):
```
BAGNO [agg. 14:32]
  Termostato  climate.bagno            heat · 21.5°C → 22°C · heating
  Temperatura sensor.temperatura_bagno 21.5°C
  Umidità     sensor.umidita_bagno     65%
  Luce        light.bagno              spenta
  [Nota: scalda lentamente in inverno — da annotazione agente 2026-04-20]
```

Le annotazioni da SQLite vengono incluse nel dettaglio espanso quando presenti.

---

## Agenti per tipo

| Tipo agente | Query per retrieval | Contesto iniettato |
|---|---|---|
| Chat | Messaggio utente | Overview + aree/tipi rilevanti |
| Monitor | `system_prompt` dell'agente | Overview + aree nel suo scope |
| Reactive | Entity_id che ha scatenato l'evento | Area dell'entity + tipi correlati |
| Preventive | `system_prompt` dell'agente | Overview + aree rilevanti |

---

## Integrazione con codice esistente

### File da creare

| File | Responsabilità |
|---|---|
| `hiris/app/proxy/semantic_context_map.py` | `ENTITY_TYPE_SCHEMA`, `SemanticContextMap`, `ContextSelector` |
| `hiris/app/proxy/embedding_backend.py` | `EmbeddingBackend` ABC, `NoEmbeddingBackend`, `VoyageEmbeddingBackend`, `OllamaEmbeddingBackend` |
| `hiris/app/proxy/knowledge_db.py` | SQLite `hiris_knowledge.db` — classificazioni, annotazioni, correlazioni, pattern |

### File da modificare

| File | Modifica |
|---|---|
| `hiris/app/proxy/entity_cache.py` | Aggiungere `domain`, `device_class`, attributi tipizzati per tutti i domini |
| `hiris/app/server.py` | Startup: init `KnowledgeDB`, `EmbeddingBackend`, `SemanticContextMap.build()` |
| `hiris/app/api/handlers_chat.py` | Sostituire `_prefetch_context()` con `SemanticContextMap.get_context()` |
| `hiris/app/claude_runner.py` | Accettare `visible_entity_ids`; validare entity nei tool |
| `hiris/app/tools/ha_tools.py` | Filtrare `get_entity_states`, `get_area_entities` su `visible_entity_ids` |
| `hiris/app/proxy/semantic_map.py` | Rimuovere `get_prompt_snippet()` — mantenere classificazione per `get_home_status` tool |
| `hiris/config.yaml` | Aggiungere opzioni: `embedding_backend`, `embedding_model` |

### File da rimuovere

| File | Motivo |
|---|---|
| `hiris/app/proxy/embedding_index.py` | Sostituito da `SemanticContextMap` + `ContextSelector` |

### Compatibilità

- API REST invariata
- Tool Claude invariati (validazione rafforzata trasparente)
- `runner.chat()` signature invariata
- `SemanticMap` mantenuta per `get_home_status` tool
- Zero breaking changes per agenti esistenti

---

## Stima risparmio token

| Componente | Attuale | SemanticContextMap |
|---|---|---|
| Snippet SemanticMap | ~200 token | 0 |
| RAG prefetch (30 entity rumorose) | ~400 token | 0 |
| Overview compatto | — | ~80 token |
| Dettaglio espanso (1 area) | — | ~150 token |
| **Totale** | **~600 token** | **~230 token** |

---

## Roadmap embedding

| Fase | Backend | Quando |
|---|---|---|
| **Ora** | `NoEmbeddingBackend` | Keyword ContextSelector, SQLite persistence |
| **Prossimo step** | `OllamaEmbeddingBackend` | Quando utente configura Ollama |
| **Parallelo** | `VoyageEmbeddingBackend` | Chi ha Claude API key, zero config extra |
| **Futuro** | Scelta utente da UI | `embedding_backend` option in config.yaml |
