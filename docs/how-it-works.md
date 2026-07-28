# HIRIS — How It Works

> Version: 0.102.0 · Updated: 2026-07-28

---

## What HIRIS is

**HIRIS** (Home Intelligent Reasoning & Integration System) is a Home Assistant Add-on that adds an AI reasoning layer to your smart home. It exposes a natural language chat interface configured via **Chatbot**, and runs a proactive layer — the **Sentinella** — that watches built-in tunable situations ("lenti") and user-defined **Agentbot**, reasoning about them with Claude (or OpenAI / Ollama) as its reasoning engine.

HIRIS does **not** replace Home Assistant — it works alongside it. Simple time-based automations (lights at sunset, alarms) belong in Layer 1 (local, no AI cost). Complex reasoning, anomaly detection, and natural language interaction belong in Layer 2 (AI).

---

## Two-layer architecture

```
┌───────────────────────────────────────────────────────┐
│  LAYER 2 — AI Agentic Loop                            │
│  • Natural language chat (Chatbot)                     │
│  • Sentinella: Agentbot (built-in + user-defined)      │
│    (opening, fridge_temp, power, battery,             │
│     hot_and_away, arrival, ...)                        │
│  • Multi-source reasoning (weather + energy + HA)     │
│  • Memory & RAG pre-fetch                             │
│  Model: Claude Sonnet (chat) / Haiku (Sentinella)     │
│  Fallback: OpenAI GPT-4o / local Ollama               │
└───────────────────────────────────────────────────────┘
          ↕  tool calls
┌───────────────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (local, offline)        │
│  • HA WebSocket listener: state_changed (detectors)   │
│  • Periodic snapshot: situations/arrival               │
│  • Task engine: deferred actions                       │
│  • Semaforo: tier gate + dangerous-domain denylist    │
└───────────────────────────────────────────────────────┘
          ↕  REST + WebSocket
┌───────────────────────────────────────────────────────┐
│  HOME ASSISTANT CORE                                  │
└───────────────────────────────────────────────────────┘
```

---

## Request flow — chat

When the user sends a message, HIRIS executes the following steps:

### 1. Receive and route

`POST /api/chat` → `handlers_chat.py`

- Reads `{message, chatbot_id}` from the JSON body (legacy `agent_id` still accepted, retro-compat)
- Identifies the requested Chatbot (or uses `hiris-default`)
- Loads conversation history from SQLite (`chat_history.db`)
- Retrieves relevant memories from the vector store (RAG injection)

### 2. Build the system prompt

The system prompt is composed in layers:

```
[1] Chatbot strategic_context  ("You are the controller of the Rossi household…")
[2] Chatbot system_prompt      (instructions, tool rules, restrictions)
[3] --- separator ---
[4] Semantic Map snippet     (live home snapshot, ~5 lines)
[5] --- separator ---
[6] RAG memories             (top-k relevant past interactions, tagged as untrusted)
[7] RAG entity pre-fetch     (live states of entities relevant to this message)
```

Example of what Claude receives:

```
You are HIRIS, assistant for the smart home…

---

HOME [map updated 14:30]
Energy: sensor.power_grid(W), sensor.solar(W)
Climate: climate.living_room(21.5°→22°C heating), climate.bedroom(20°→21°C idle)
Presence: PIR Hallway(off), PIR Living room(on)
Lights: 18 entities / 5 rooms
Appliances: switch.washing_machine, switch.dishwasher

---

Relevant entities (live data):
- Living Room Light [light.living_room]: on
- Living Room Thermostat [climate.living_room]: heat, current 21.5°C → setpoint 22°C
- Grid Power [sensor.grid_power]: 1243 W
```

### 3. Agentic loop

Claude receives: system prompt + conversation history + user message.

Claude responds with one of:
- **Direct text** → returned to user, loop ends
- **Tool call** → HIRIS executes the tool, sends the result back to Claude, Claude decides again

The loop repeats up to **10 iterations** (infinite loop protection). Claude decides autonomously when it has enough information to answer.

**API error handling:**
- 429/529 (rate limit): 3 retries with exponential backoff (5s → 15s → 45s)
- Tool failure: returns `{error: "..."}` instead of raising — Claude sees the error and can handle it

### 4. Response and persistence

- The response is returned to the frontend as `{response: "...", debug: {tools_called: [...]}}`
- The turn (user + assistant) is written atomically to SQLite
- Token usage is tracked per model and per Chatbot

---

## Available tools

| Tool | Description |
|---|---|
| `get_entity_states(ids)` | Live state of specific HA entities |
| `get_home_status()` | Compact structured home snapshot |
| `get_area_entities()` | All entities grouped by HA area |
| `get_entities_on()` | All entities currently in `on` state |
| `get_entities_by_domain(domain)` | Entities filtered by domain |
| `get_energy_history(days)` | Historical consumption from HA History API |
| `get_weather_forecast(hours)` | Forecast from Open-Meteo (free, no key needed) |
| `call_ha_service(domain, service, data)` | Call any HA service (subject to `allowed_services` filter) |
| `send_notification(message, channel)` | Push via HA, Telegram, Apprise (80+ channels) |
| `get_ha_automations()` | List HA automations |
| `trigger_automation(id)` | Trigger an HA automation |
| `toggle_automation(id, enabled)` | Enable or disable an HA automation |
| `get_calendar_events(hours, calendar)` | HA calendar events |
| `set_input_helper(entity_id, value)` | Set input_boolean / input_number / input_text |
| `create_task(...)` / `list_tasks()` / `cancel_task(id)` | Internal task management |
| `recall_memory(query, k, tags)` | Search past memories (vector similarity) |
| `save_memory(content, tags)` | Store a new memory (Chatbot only) |
| `http_request(url, method, headers, body)` | HTTP call to whitelisted external endpoints |
| `get_ha_health(sections)` | HA health snapshot: unavailable entities, integration errors, pending updates, system info |
| `create_automation_proposal(type, name, description, config, routing_reason)` | Queue a new automation proposal for human review (Chatbot only) |

---

## Chatbot and Agentbot

There is no longer a single "agent" concept split into types (`chat` /
`monitor` / `reactive` / `preventive`) with custom rules and states. HIRIS now
distinguishes two entities, with unambiguous behavior: the **Chatbot**
(conversational, on-demand) and the **Agentbot** (autonomous, trigger-based).

### Chatbot — conversational

Activated by the user via the UI (or the Lovelace card). Each Chatbot is a
configuration — system prompt + strategic context, tool/entity/service scope,
memory scope (`knowledge_access`), chat policy (`max_chat_turns`,
`require_confirmation`, `response_mode`) — never an autonomous schedule. Uses
Claude Sonnet for maximum quality by default.

### Agentbot — proactive (Sentinella engine)

A set of **built-in** detectors/situations (tunable, each independently
enabled with an entity selector + thresholds from the Sentinella config page:
`opening` — door/window left open, `fridge_temp`, `power` — consumption
anomaly, `battery` — low battery, `hot_and_away` — hot outside + nobody home →
suggests running a valve/relay for N minutes, `evening_arrival` — presence
returns in the evening → suggests a scene) **plus** **user-defined Agentbot**
(`/api/agentbots`, persisted in `agentbots.json` — born from a Brain proposal
or created by hand), each with its own trigger (cron/interval/event). A
signal/trigger wakes a single-shot LLM reasoner (Claude Haiku by default,
restricted to read-only tools) that decides whether to notify and/or suggest
one low-risk action, gated by the semaforo (tier + dangerous-domain denylist)
before anything is actually executed. Verdict-JSON contract; no free tool use
(security pillar).

Example of the reasoner's own structured reply (internal — not user-facing
prompt syntax; the reasoner always answers in Italian):
```json
{"verdict": "anomalia", "severity": "warn", "message": "Consumo anomalo — lavatrice attiva da 3 ore", "action": null}
```

---

## The Brain Home (`#/`)

The **Dashboard** (accessible at `#/`) is the Brain's home — the central place where HIRIS
shows you what it observes and reasons about your home, alerts you to problems that need
attention, and gathers all proposed actions for your approval.

### Three zones

1. **Home oversight** — compact status strip showing: current door/window openings, presence,
   offline devices, last reasoning round timestamp, and active AI provider.
2. **Reasoning stream** — reverse-chronological cards that surface the Brain's rationale:
   "At 08:00 I observed…" with deductions and related findings. No new LLM call — the text
   is captured from reasoning already performed by the Sentinella during its cycle.
3. **Actions and alerts** — two lists: **Proposals** (suggested automations, approve/reject)
   and **Alerts** (5 read-only checks: unavailable entities, low batteries, broken automations,
   dangerous domains, unassigned entities). Alerts auto-resolve when the issue disappears;
   you can also manually acknowledge them.

Behind the scenes: `brain/health_scan.py` runs the 5 checks and writes/updates the
advisory rows (`advisory.db`); `brain/feed.py` assembles the single stream the
Dashboard renders by combining reasoning rounds (`brain_reasoning.db`), open/
acknowledged alerts, and proposals, served over `GET /api/brain/feed`.

---

## The Models layer (`#/models`)

The **Models** page (SP-2) is the single place where the user sees and governs
which LLM provider/model is used where, without editing environment variables
or add-on options. It reads/writes `GET`/`PUT /api/models/config`
(`handlers_models.py`, persisted to `/data/models_config.json`) and has four
parts:

1. **Active providers** — all 5 providers (Claude Max subscription, Claude API,
   OpenAI, OpenRouter, Ollama) in a fixed order, with a status badge (active /
   missing credential / off) and, for already-credentialed providers, a picker
   for the default model (`provider_models`).
2. **Automatic chain** — the fallback order (`chain_order`) used when a Chatbot
   or Agentbot has `model="auto"`: reorderable with arrows, with presets that
   mirror `LLMRouter`'s strategies (`cost_first` / `quality_first` / `balanced`).
3. **Per-entity assignment** — a Chatbot's model is set in the Chatbot editor
   itself (`PUT /api/chatbots/{id}`); the Brain's is set here (`brain_model` in
   `models_config.json`, used by the proactive/cognitive reasoner whenever it
   isn't "auto"); an Agentbot's is set in the Agentbot editor (`#/agentbots`,
   per-Agentbot `reasoning.model` field).
4. **Embeddings** — a read-only informational row (active embedding
   provider/model), useful to see what powers the second brain's vector search.

Frontend implementation: `static/config/models-route.js`. The backend never
returns secrets (API keys) — only `has_credential: true/false` per provider.

---

## The Semantic Home Map

The Semantic Map is the cognitive model HIRIS builds of your home. It maps every HA entity to a **semantic role** (what it is) and a **readable label** (what it's called).

### Classification pipeline

```
HA entity
    │
    ▼
[Keyword rules]  ← _solar, _temp, _motion, _door, domain rules…
    │
    ├─ Match found → classified immediately (ms, no LLM)
    │
    └─ No match → pending queue
                    │
                    ▼
            [LLM batch, 20 entities/call]
                    ├── Local Ollama (if configured) → free, fast
                    └── Claude (fallback) → precise
```

The map is:
- Built at first startup (all entities processed)
- Updated in real time when HA adds a new entity (`entity_registry_updated`)
- Persisted to `/data/home_semantic_map.json` and reloaded on restart

### Prompt snippet

`get_prompt_snippet()` produces a compact block (~5 lines) injected into every AI call:

```
HOME [map updated 14:30]
Energy: sensor.solar(W), sensor.grid(W), sensor.consumption(W)
Climate: climate.living_room(21.5°→22°C heating)
Presence: PIR Hallway(off), PIR Living room(on)
Lights: 18 entities / 5 rooms
```

The `HH:MM` timestamp is minute-granular to maximize Anthropic prompt cache reuse — up to 90% savings on input tokens for frequent messages.

---

## LLM Router

`LLMRouter` is the abstraction layer between HIRIS and language models. It exposes the same interface regardless of which model is behind it.

### Strategy and fallback

```
HIRIS (handlers, chatbots/agentbots)
        │
        ▼
   LLMRouter (strategy: balanced / quality_first / cost_first)
   ├── claude  → ClaudeRunner (Anthropic SDK)
   ├── openai  → OpenAICompatRunner (OpenAI API)
   └── ollama  → OpenAICompatRunner (local Ollama)
```

When `model="auto"`:
- **balanced**: Claude → OpenRouter → OpenAI → Ollama
- **quality_first**: Claude → OpenAI → OpenRouter → Ollama
- **cost_first**: Ollama → OpenRouter → OpenAI → Claude

If the primary backend fails, the next one in the chain is tried automatically.

---

## Memory & RAG

HIRIS stores Chatbot memories in SQLite with vector similarity search (pure Python cosine similarity — no native extensions required, Alpine/ARM compatible).

- `recall_memory(query, k, tags)` — retrieve top-k memories matching the query
- `save_memory(content, tags)` — store a new memory (Chatbot only, for security)
- Memories are tagged as untrusted data in the system prompt to prevent prompt injection
- Configurable retention (default 90 days)

---

## Security model

Each Chatbot can be restricted to:

| Field | Purpose | Example |
|---|---|---|
| `allowed_tools` | Tool whitelist | `["get_entity_states", "call_ha_service"]` |
| `allowed_entities` | Glob patterns on entity IDs | `["light.*", "climate.living_room"]` |
| `allowed_services` | Glob patterns on callable services | `["light.*", "switch.turn_*"]` |
| `allowed_endpoints` | Whitelisted URLs for `http_request` | `[{"url": "https://api.example.com", ...}]` |
| `restrict_to_home` | Refuse off-topic questions | `true` |
| `require_confirmation` | Claude must ask before calling `call_ha_service` | `true` |
| `knowledge_access` | Memory scope (sensitive data, which kinds) | `{"allow_sensitive": false, "kinds": "all"}` |
| `max_chat_turns` | Limit conversation length | `20` |

Cost/tokens are still tracked per Chatbot (visible in the config UI and via
MQTT) but there is no per-Chatbot budget cap or auto-disable anymore — that
mechanism was retired together with the old Slice 5 fields.

SSRF protection is enforced on `http_request`: RFC1918 ranges, IPv4-mapped IPv6, loopback, and link-local addresses are blocked. Redirects are disabled. Requests are capped at 4KB.

---

## Disk persistence

| File | Content |
|---|---|
| `/data/chatbots.json` | All Chatbot configurations |
| `/data/agentbots.json` | User-defined Agentbot configurations |
| `/data/usage.json` | Token counters and costs per Chatbot |
| `/data/home_semantic_map.json` | Semantic entity classification |
| `/data/chat_history.db` | SQLite: conversation history + memories |
| `/data/ha_health.json` | HA health snapshot (HealthMonitor — unavailable entities, integration errors, updates) |
| `/data/proposals.db` | SQLite: automation proposals with lifecycle (pending → applied/rejected/archived → deleted) |

All files are written atomically (temp file + rename or executor-dispatched SQLite commit) for crash safety.

---

## Cost tracking

HIRIS tracks every request by model and Chatbot:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|---|---|---|
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.25 | $1.25 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| Ollama (local) | free | free |

Usage is available via `/api/usage` and visible in the HIRIS config UI per Chatbot.
