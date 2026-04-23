# ContextMap Design

> **Versione:** 1.0 · **Data:** 2026-04-23

## Goal

Sostituire il sistema RAG keyword-based (`EmbeddingIndex`) e lo snippet generico di `SemanticMap` con una **ContextMap strutturata per area**, costruita a partire dalla classificazione nativa di Home Assistant (`device_class` + domain). Ad ogni richiesta, un `ContextSelector` inietta nel prompt solo le sezioni rilevanti, riducendo il rumore e migliorando la precisione delle risposte di Claude.

---

## Problemi risolti

| Problema attuale | Soluzione |
|---|---|
| RAG keyword brittle: "termostato" non matcha `climate.bagno` | Classificazione per domain+device_class, non per nome |
| Claude dice "nessun termostato in bagno" quando esiste | Overview per area lista esplicitamente i tipi presenti |
| Sensori non pertinenti iniettati nel prompt | Retrieval mirato per area e tipo entity |
| `allowed_entities` non applicato uniformemente nei tool | ContextMap filtrata per agente = confine unico di visibilità |

---

## Classificazione entity: ENTITY_TYPE_SCHEMA

Fonte di verità per classificare ogni entity in base a `domain` + `device_class` (attributo nativo HA). Per ogni tipo: label italiano e attributi da estrarre.

### Domini con classificazione diretta (device_class non necessario)

| Domain | Tipo interno | Label IT | Attributi da estrarre |
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

### `sensor` — classificato per device_class

| device_class | Tipo interno | Label IT | Attributi |
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

### `binary_sensor` — classificato per device_class

| device_class | Tipo interno | Label IT | Stato significato |
|---|---|---|---|
| `motion` / `occupancy` | `motion` | Presenza | on=rilevato · off=assente |
| `door` | `door` | Porta | on=aperta · off=chiusa |
| `window` | `window` | Finestra | on=aperta · off=chiusa |
| `presence` | `presence` | Presenza | on=casa · off=assente |
| `smoke` | `smoke` | Fumo | on=rilevato · off=ok |
| `moisture` | `moisture` | Perdita | on=bagnato · off=asciutto |
| `vibration` | `vibration` | Vibrazione | on=rilevata · off=ok |
| `connectivity` | `connectivity` | Connessione | on=ok · off=persa |
| `cold` / `heat` | `temperature_alert` | Allerta temp. | on=allerta · off=ok |
| *(nessuno)* | `binary` | Sensore | on/off |

### Priorità di classificazione

1. `domain` + `device_class` → ENTITY_TYPE_SCHEMA (fonte primaria)
2. `domain` solo → fallback per domini diretti (climate, light, cover…)
3. SemanticMap LLM → fallback per entity senza device_class né domain riconosciuto
4. `sensor` generico → tipo `sensor`, incluso senza espansione attributi

---

## EntityCache — estensione

L'`EntityCache` attuale memorizza dati minimali. Viene esteso per includere `device_class` e `domain`, e per estrarre gli attributi tipizzati di tutti i domini (non solo `climate` come ora).

```python
# Formato esteso (aggiunto a minimal):
{
  "id": "climate.bagno",
  "state": "heat",
  "name": "Termostato Bagno",
  "unit": "",
  "domain": "climate",
  "device_class": None,
  "attributes": {
    "hvac_mode": "heat",
    "hvac_action": "heating",
    "current_temperature": 21.5,
    "temperature": 22.0,
    "preset_mode": "home"
  }
}
```

Gli attributi estratti per ogni entity dipendono da `ENTITY_TYPE_SCHEMA[entity_type]`. Solo gli attributi definiti nello schema vengono salvati — nessun attributo superfluo.

---

## ContextMap

### Struttura dati

```
ContextMap._map: dict[str | None, dict[str, list[str]]]

{
  "Bagno": {
    "climate": ["climate.bagno"],
    "temperature": ["sensor.temperatura_bagno"],
    "humidity": ["sensor.umidita_bagno"],
    "light": ["light.bagno"]
  },
  "Soggiorno": {
    "light": ["light.soggiorno_1", "light.soggiorno_2"],
    "temperature": ["sensor.temp_soggiorno"],
    "motion": ["binary_sensor.pir_soggiorno"],
    "media_player": ["media_player.tv_soggiorno"]
  },
  None: {
    "power": ["sensor.consumo_totale"],
    "energy": ["sensor.energia_totale"]
  }
}
```

Le chiavi sono `area_name` (stringa) o `None` (non assegnate). I valori sono dizionari `entity_type → [entity_ids]`.

### Costruzione all'avvio

1. `EntityCache.load()` — carica tutti gli stati HA
2. `EntityCache.load_area_registry()` — carica area registry e entity registry
3. `ContextMap.build(entity_cache)` — per ogni entity_id:
   - Ricava `domain` dall'entity_id (parte prima del punto)
   - Legge `device_class` dagli attributi
   - Classifica con ENTITY_TYPE_SCHEMA
   - Inserisce nella mappa sotto l'area corretta (o `None`)
4. `ContextMap` pronto — struttura immutabile fino al prossimo `state_changed` che aggiunga/rimuova entity

### Aggiornamento

- **Stato entity cambiato** (`state_changed`): nessuna modifica alla mappa strutturale — la mappa contiene solo entity_ids; gli stati live vengono sempre letti da `EntityCache` al momento della richiesta
- **Nuova entity aggiunta** (`entity_registry_updated`): `ContextMap.add_entity(entity_id, attributes)` la classifica e inserisce nella mappa
- **Entity rimossa**: `ContextMap.remove_entity(entity_id)`

---

## ContextSelector

### Dizionario concetti → tipi (italiano)

```python
CONCEPT_TO_TYPES = {
    # climate
    "termostato": ["climate"], "riscaldamento": ["climate"],
    "raffreddamento": ["climate"], "clima": ["climate"],
    "caldo": ["climate", "temperature"], "freddo": ["climate", "temperature"],
    "gradi": ["climate", "temperature"], "temperatura": ["climate", "temperature"],

    # light
    "luce": ["light"], "luci": ["light"], "illuminazione": ["light"],
    "lampada": ["light"], "accesa": ["light"], "spenta": ["light"],

    # energy
    "consumo": ["power", "energy"], "energia": ["energy"],
    "watt": ["power"], "kwh": ["energy"], "corrente": ["power"],
    "bolletta": ["energy"], "elettricità": ["power", "energy"],

    # presence/motion
    "movimento": ["motion", "occupancy"], "presenza": ["motion", "presence"],
    "qualcuno": ["motion", "occupancy"], "persona": ["motion"],

    # door/window
    "porta": ["door"], "finestra": ["window"], "ingresso": ["door"],
    "aperta": ["door", "window", "cover"], "chiusa": ["door", "window", "cover"],

    # cover
    "tapparella": ["cover"], "veneziana": ["cover"],
    "tenda": ["cover"], "avvolgibile": ["cover"],

    # media
    "tv": ["media_player"], "televisione": ["media_player"],
    "musica": ["media_player"], "volume": ["media_player"],

    # lock
    "serratura": ["lock"], "chiave": ["lock"],

    # humidity
    "umidità": ["humidity"],

    # switch/appliance
    "lavatrice": ["switch"], "lavastoviglie": ["switch"],
    "presa": ["switch"], "interruttore": ["switch"],

    # alarm
    "allarme": ["alarm"], "sicurezza": ["alarm"],

    # vacuum
    "robot": ["vacuum"], "aspirapolvere": ["vacuum"],
}
```

### Logica di selezione

```
query = messaggio utente (lowercase)

1. area_matches = [area for area in map.areas if area.lower() in query]
2. type_matches = flatten([CONCEPT_TO_TYPES[c] for c in CONCEPT_TO_TYPES if c in query])

Selezione:
  - area_matches E type_matches → espandi solo quei tipi in quelle aree
  - solo area_matches           → espandi tutta l'area
  - solo type_matches           → espandi quel tipo in tutte le aree
  - nessun match                → solo overview compatto
```

### Formato output nel prompt

**Overview compatto** (sempre iniettato, ~80 token):
```
CASA — 4 aree [agg. 14:32]
  Bagno:      Termostato · Temperatura · Umidità · Luce
  Soggiorno:  Luci×2 · Temperatura · Presenza · TV
  Camera:     Termostato · Temperatura · Luce
  Cucina:     Temperatura · Presenza · Interruttore×2
[Non assegnate: Potenza · Energia]
```

**Dettaglio espanso** (solo aree/tipi matchati, ~150 token per area):
```
BAGNO [agg. 14:32]
  Termostato  climate.bagno            heat · 21.5°C → 22°C · azione: heating
  Temperatura sensor.temperatura_bagno 21.5°C
  Umidità     sensor.umidita_bagno     65%
  Luce        light.bagno              spenta
```

---

## Permission model — ContextMap come confine unico

### Asse visibilità (`allowed_entities`)

```python
ContextMap.get_context(
    query: str,
    entity_cache: EntityCache,
    allowed_entities: list[str] | None = None,  # glob patterns
) -> tuple[str, frozenset[str]]
# Returns: (prompt_context, visible_entity_ids)
```

La mappa viene filtrata prima del retrieval. Se `allowed_entities = ["climate.*", "sensor.temp_*"]`:
- Overview mostra solo le aree che hanno almeno una entity permessa
- Overview lista solo i tipi che hanno entity permesse
- Dettaglio espande solo entity permesse
- `visible_entity_ids` = set delle entity_id visibili all'agente in questa chiamata

### Asse controllo (`allowed_services`)

Invariato rispetto a oggi — verificato in `_dispatch_tool` per `call_ha_service` e `create_task`.

### Validazione tool call

```python
# In claude_runner._dispatch_tool, per ogni tool che accede a entity:
if entity_id not in self._visible_entity_ids:
    return {"error": f"Entity {entity_id} non accessibile da questo agente"}
```

`_visible_entity_ids` viene impostato da `runner.chat()` a ogni chiamata, basato sul risultato di `ContextMap.get_context()`.

**Tabella permessi completa:**

| Entity in allowed_entities | Service in allowed_services | Può vedere (prompt) | Può controllare (tool) |
|---|---|---|---|
| ✅ | ✅ | ✅ | ✅ |
| ✅ | ❌ | ✅ | ❌ |
| ❌ | qualsiasi | ❌ | ❌ |

### Agenti per tipo

| Tipo agente | Query per ContextSelector | allowed_entities applicato |
|---|---|---|
| Chat | Messaggio utente | Sì |
| Monitor | `system_prompt` dell'agente | Sì |
| Reactive | ID entity che ha scatenato l'evento → area corrispondente | Sì |
| Preventive | `system_prompt` dell'agente | Sì |

---

## Integrazione con codice esistente

### File da creare

| File | Responsabilità |
|---|---|
| `hiris/app/proxy/context_map.py` | `ENTITY_TYPE_SCHEMA`, `ContextMap`, `ContextSelector` |

### File da modificare

| File | Modifica |
|---|---|
| `hiris/app/proxy/entity_cache.py` | Aggiungere `domain`, `device_class`, attributi tipizzati per tutti i tipi (non solo climate) |
| `hiris/app/server.py` | Startup: `ContextMap.build(entity_cache)` dopo `load_area_registry()`; registra callback per entity added/removed |
| `hiris/app/api/handlers_chat.py` | Sostituire `_prefetch_context()` con `ContextMap.get_context(message, entity_cache, allowed_entities)` |
| `hiris/app/claude_runner.py` | Accettare `visible_entity_ids` in `chat()`; validare entity nei tool |
| `hiris/app/tools/ha_tools.py` | `get_entity_states`, `get_area_entities`: filtrare risultati su `visible_entity_ids` |
| `hiris/app/proxy/semantic_map.py` | Rimuovere `get_prompt_snippet()` — mantenere solo classificazione per `get_home_status` tool |

### File da rimuovere

| File | Motivo |
|---|---|
| `hiris/app/proxy/embedding_index.py` | Sostituito da `ContextSelector` |

### Compatibilità

- API REST invariata
- Tool Claude invariati (solo validazione rafforzata)
- `runner.chat()` signature invariata — `visible_entity_ids` è dettaglio interno
- `SemanticMap` rimane per `get_home_status` tool
- Zero breaking changes per gli agenti esistenti

---

## Stima risparmio token

| Componente | Attuale | ContextMap |
|---|---|---|
| Snippet SemanticMap | ~200 token | 0 |
| RAG prefetch (30 entity) | ~400 token | 0 |
| Overview compatto | — | ~80 token |
| Dettaglio espanso (1 area) | — | ~150 token |
| **Totale** | **~600 token** | **~230 token** |

Risparmio stimato: ~60% per richiesta, con qualità superiore (nessun falso positivo).

---

## Scenari di esempio

### "C'è un termostato in bagno?"
- area_match: `Bagno`
- type_match: `climate` (da "termostato")
- Inietta: overview + dettaglio Bagno/climate

```
BAGNO
  Termostato  climate.bagno  heat · 21.5°C → 22°C · azione: heating
```

### "Quanta energia sto consumando?"
- area_match: nessuna
- type_match: `power`, `energy` (da "energia", "consumo")
- Inietta: overview + tutti i sensori power/energy di tutte le aree

### "Accendi le luci del soggiorno"
- area_match: `Soggiorno`
- type_match: `light` (da "luci")
- Inietta: overview + dettaglio Soggiorno/light
- Tool call: `call_ha_service` validato contro `visible_entity_ids`

### "Tutto ok in casa?" (query generica)
- area_match: nessuna
- type_match: nessuna
- Inietta: solo overview compatto — Claude vede la struttura e usa i tool per approfondire
