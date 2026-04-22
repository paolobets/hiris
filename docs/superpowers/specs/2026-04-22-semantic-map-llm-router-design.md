# HIRIS — Semantic Home Map + LLM Router Design

**Date:** 2026-04-22  
**Status:** Approved  
**Scope:** Phase 1 enhancement — home intelligence layer + pluggable LLM backend

---

## Problem Statement

Two related gaps in the current architecture:

1. **Energy history broken**: `energy_tools.py` uses hardcoded entity IDs (`sensor.energy_consumption` etc.) that don't exist in most real HA installations. Claude reports "no historical data access" when it actually queried non-existent entities.

2. **Agents lack home domain knowledge**: Claude doesn't know what entities semantically *are*. It can keyword-search `sensor.shellyem3_34945479_a_power` but doesn't know it's the kitchen energy meter. With ~600 entities, this gap matters.

3. **LLM is hardcoded**: `claude_runner.py` is tightly coupled to the Anthropic SDK. Users cannot route simple tasks to a local/cheaper model or switch providers.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  HIRIS Intelligence Layer                   │
│  Semantic Map · RAG · Entity Knowledge      │
│  History · Patterns · Home Context          │
└─────────────────────────────────────────────┘
                      ↕ feeds
┌─────────────────────────────────────────────┐
│  LLM Router (pluggable)                     │
│  Claude · GPT · Gemini · Llama/Ollama       │
└─────────────────────────────────────────────┘
```

HIRIS owns the domain intelligence (the home). The LLM provides reasoning. These are separate concerns.

---

## Component 1: Semantic Home Map

### Storage

**File:** `/data/home_semantic_map.json`

```json
{
  "version": "1",
  "generated_at": "2026-04-22T10:00:00Z",
  "last_updated": "2026-04-22T14:30:00Z",
  "categories": {
    "energy_meters":    ["sensor.shellyem3_xxx_power"],
    "solar_production": ["sensor.solaredge_dc_power"],
    "grid_import":      ["sensor.tibber_energy_import"],
    "climate_sensors":  ["climate.heatpump", "sensor.aqara_temp_salotto"],
    "presence":         ["binary_sensor.presence_home"],
    "appliances":       ["switch.lavatrice", "switch.lavastoviglie"],
    "lighting":         ["light.salotto", "light.cucina"],
    "unknown":          ["sensor.shellyem3_34945479_ch1_cfgchanged"]
  },
  "entity_meta": {
    "sensor.shellyem3_xxx_power": {
      "label": "Contatore energia cucina",
      "role": "energy_meter",
      "area": "cucina",
      "unit": "W",
      "classified_by": "rules"
    },
    "sensor.shellyem3_34945479_ch1_cfgchanged": {
      "label": "Shelly ch1 config change event",
      "role": "diagnostic",
      "classified_by": "claude",
      "confidence": 0.9
    }
  }
}
```

### Build Lifecycle

```
Startup
  → load existing map from disk (if exists)
  → diff: entity_cache IDs vs map known IDs → new entities?
  → classify new via Rules → residual ambiguous → LLM batch queue

WebSocket: entity_registry_updated (new device added in HA)
  → detect new entity_id
  → rules: classified? → update map immediately
  → ambiguous? → LLM batch queue (background, ~2-5 sec)

LLM batch (background task)
  → classify "unknown" in groups of 20
  → update map → persist to disk
```

### Rule-Based Classifier (~80% coverage)

| Pattern | Category |
|---|---|
| `*_power`, `*_energy`, `*_consumption`, `*_watt*` | energy_meter |
| `*_solar*`, `*_pv*`, `*_photovoltaic*` | solar_production |
| `*_grid*`, `*_import*`, `*_export*` | grid_import |
| `*_temp*`, `climate.*` | climate_sensors |
| `binary_sensor.*_motion*`, `*_presence*`, `*_occupancy*` | presence |
| `light.*` | lighting |
| `binary_sensor.*_door*`, `*_window*` | door_window |
| `*_lavatrice*`, `*_lavastoviglie*`, `*_forno*`, `*_boiler*` | appliances |
| `sensor.*_voltage`, `sensor.*_current` | electrical |
| `*.update`, `*.config_*`, `*_cfgchanged` | diagnostic (excluded from useful) |

### LLM Classification Prompt (for ambiguous entities)

```
Classifica queste entità Home Assistant. Per ciascuna, restituisci JSON con:
- role: una di [energy_meter, solar_production, grid_import, climate_sensor,
         presence, lighting, appliance, door_window, electrical, diagnostic, other]
- label: descrizione italiana breve (max 5 parole)
- confidence: 0.0-1.0

Entità da classificare:
{batch_of_20_entities_with_id_state_attributes}
```

Complexity: **low** — routed to local model if configured.

### Prompt Injection (replaces `home_profile.py`)

```
CASA [mappa agg. 14:30]
Energia: sensor.shellyem3_xxx_power(W), sensor.solaredge_dc_power(W)
Clima: climate.heatpump(22.5°→21°C heating), sensor.aqara_temp_salotto(19.8°C)
Presenze: binary_sensor.presence_home(home)
Luci: 14 entità / 6 stanze
Elettrodomestici: switch.lavatrice, switch.lavastoviglie
Sconosciuti: 3 entità in attesa classificazione
```

### New File

**`app/proxy/semantic_map.py`** — `SemanticMap` class:
- `load() / save()` — disk persistence
- `classify_new(entities, entity_cache)` — rules + LLM queue
- `get_category(role: str) -> list[str]` — used by tools
- `get_prompt_snippet() -> str` — replaces home_profile
- `on_entity_added(entity_id, attributes)` — WebSocket hook

---

## Component 2: LLM Router

### Configuration (new options in `config.yaml`)

```yaml
primary_model: "claude-sonnet-4-6"   # high-complexity tasks + default
local_model_url: ""                   # e.g. http://192.168.1.x:11434 (Ollama)
local_model_name: ""                  # e.g. llama3.2
```

If `local_model_url` is empty → all tasks route to `primary_model`, zero behavior change.

### Unified Interface (`app/llm_router.py`)

```python
@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]
    stop_reason: str
    usage: dict          # input_tokens, output_tokens, cost_eur

class LLMRouter:
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str = "",
        complexity: Literal["low", "high"] = "high",
        model_override: str | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...
```

### Routing Logic

```
model_override = explicit model string  → use that provider/model directly
model_override = "auto" + high          → primary_model (Claude or configured)
model_override = "auto" + low           → local_model (if configured)
                                          └→ fallback to primary_model if not
```

### Backend Architecture

```
app/backends/
├── __init__.py
├── base.py          # LLMBackend ABC: chat() → LLMResponse
├── claude.py        # ClaudeBackend — migrated from claude_runner.py
└── ollama.py        # OllamaBackend — OpenAI-compat API (stub, Phase 1.5)
```

`ClaudeBackend` contains all current `claude_runner.py` logic (tool dispatch, usage tracking, retry, structured response parsing). It does NOT change behavior — only moves.

GPT/Gemini backends are Phase 2 stubs: implement `LLMBackend.chat()` when needed.

### Migration from `claude_runner.py`

| Current | New location |
|---|---|
| `ClaudeRunner.chat()` | `ClaudeBackend.chat()` |
| `ClaudeRunner._dispatch_tool()` | `ClaudeBackend._dispatch_tool()` |
| `ClaudeRunner._per_agent_usage` | `ClaudeBackend._per_agent_usage` |
| Agentic loop logic | `LLMRouter.chat()` (provider-agnostic) |

`agent_engine.py` and `handlers_chat.py` call `router.chat()` only — unaware of which backend runs.

---

## Component 3: Energy Fix

### Problem

`energy_tools.py` hardcodes entity IDs that don't exist in real installations.

### Fix

```python
async def get_energy_history(
    ha: HAClient,
    semantic_map: SemanticMap,
    days: int
) -> list[dict] | dict:
    entity_ids = (
        semantic_map.get_category("energy_meters") +
        semantic_map.get_category("solar_production") +
        semantic_map.get_category("grid_import")
    )
    if not entity_ids:
        return {
            "error": "Nessun contatore energia nella mappa semantica.",
            "hint": "Aggiungi i sensori energia alla mappa o aspetta la classificazione automatica."
        }
    raw = await ha.get_history(entity_ids=entity_ids, days=days)
    return _compress_energy_history(raw)
```

### Same pattern for other domain-aware tools

| Tool | Change |
|---|---|
| `get_energy_history` | reads `energy_meters + solar + grid` from map |
| `get_home_status` | enriches output with semantic labels from map |
| RAG prefetch | keyword search + category boost (energy query → always include energy_meters) |

---

## Files Changed

| File | Action |
|---|---|
| `app/proxy/semantic_map.py` | **new** — SemanticMap class |
| `app/llm_router.py` | **new** — LLMRouter + routing logic |
| `app/backends/__init__.py` | **new** |
| `app/backends/base.py` | **new** — LLMBackend ABC |
| `app/backends/claude.py` | **new** — migrated from claude_runner.py |
| `app/backends/ollama.py` | **new** — stub, Phase 1.5 |
| `app/claude_runner.py` | **modified** → thin wrapper or deprecated |
| `app/tools/energy_tools.py` | **modified** — reads from semantic_map |
| `app/tools/ha_tools.py` | **modified** — get_home_status enriched |
| `app/api/handlers_chat.py` | **modified** — use router, inject map snippet |
| `app/agent_engine.py` | **modified** — use router instead of runner |
| `app/server.py` | **modified** — wire SemanticMap + LLMRouter |
| `app/proxy/home_profile.py` | **replaced** by SemanticMap.get_prompt_snippet() |
| `hiris/config.yaml` | **modified** — new options: primary_model, local_model_url, local_model_name |

---

## Out of Scope (Phase 2)

- GPT / Gemini backend implementations
- UI for semantic map visualization / manual override
- Cross-entity relationship modeling (Knowledge Graph)
- Semantic map export / import between installations

---

## Success Criteria

- `get_energy_history` returns real data (not empty) for any HA installation
- Claude's system prompt contains structured home context from the semantic map
- New HA device added → classified and in map within 10 seconds
- Switching `primary_model` in config changes which model all agents use
- Setting `local_model_url` routes low-complexity tasks (map classification) to local model
- No behavior change when `local_model_url` is empty
