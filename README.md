<p align="center">
  <img src="hiris/icon.png" alt="HIRIS logo" width="120"/>
</p>

<h1 align="center">HIRIS</h1>
<p align="center"><strong>Home Intelligent Reasoning & Integration System</strong></p>
<p align="center">
  <a href="https://github.com/paolobets/hiris/releases"><img src="https://img.shields.io/github/v/release/paolobets/hiris?label=version&color=blue" alt="version"/></a>
  <img src="https://img.shields.io/badge/stage-experimental-orange" alt="stage"/>
  <img src="https://img.shields.io/badge/HA-2023.1%2B-41BDF5" alt="Home Assistant"/>
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20aarch64-lightgrey" alt="arch"/>
</p>

> **Experimental** — HIRIS is under active development. APIs and configuration options may change between releases.

A standalone **Home Assistant Add-on** that brings AI-powered agent reasoning to your smart home. HIRIS combines a Python flow engine (runs 100% locally, no AI cost) with a Claude-powered agentic loop for natural language chat, anomaly detection, and autonomous actions.

---

## What HIRIS can do

### Chat with your home
Ask anything about your home in natural language. HIRIS queries Home Assistant in real time and uses Claude to reason before answering or acting.

```
You: "Accendi le luci del salotto e dimmi quanto consuma la casa in questo momento"
HIRIS: "Ho acceso le luci del soggiorno. La casa consuma attualmente 2.4 kW:
        lavatrice (1.8 kW), forno (0.6 kW). Fotovoltaico: 0 W (è notte)."
```

### Autonomous agents
Configure agents that run on a schedule, react to HA events, or trigger at fixed times — with or without Claude.

| Agent type | Trigger | Use case |
|---|---|---|
| **Monitor** | Every N minutes | Energy anomaly detection, presence monitoring |
| **Reactive** | HA `state_changed` event | Door opened at night → notify; motion detected → lights on |
| **Preventive** | Fixed cron time | Morning briefing, daily energy report, pre-heat house |
| **Chat** | User message | Natural language interface |

### Semantic Home Map
HIRIS automatically classifies every entity in your HA installation (lights, climate, sensors, appliances…) using rule-based logic and LLM-assisted classification. This map is used to:
- give Claude a structured snapshot of your home before each call
- pre-fetch only the entities relevant to the current query (RAG)
- power the energy tools without manual configuration

### RAG pre-fetch
Before calling Claude, HIRIS searches for entities semantically related to the user's message and injects their live states into the system prompt. Claude sees real data before calling any tool — faster and cheaper.

---

## Features

- **8 built-in tools** — entity states, energy history, weather forecast (Open-Meteo, no key needed), HA service calls, notifications, automation management
- **4 agent types** — chat, monitor, reactive, preventive
- **Per-agent security filters** — allowed entities (glob patterns), allowed services, require confirmation, restrict to home topics only
- **Per-agent budget** — auto-disable when cost exceeds EUR limit
- **Chat history** — server-side conversation persistence per agent, configurable max turns
- **Model auto-selection** — chat agents use Sonnet; monitor/reactive/preventive use Haiku (cheaper)
- **Optional local model** — route classification tasks to a local Ollama model to save API cost
- **Mobile-optimized UI** — safe-area insets, 16px font, 44px touch targets
- **Notifications** — HA push, Telegram, or custom channels
- **Execution log** — last 20 runs per agent with token usage, tool calls, and structured evaluation

---

## Installation

### Via Home Assistant Add-on Store

1. **Settings** → **Add-ons** → **Add-on Store** → three-dot menu → **Repositories**
2. Add: `https://github.com/paolobets/hiris`
3. Find **HIRIS** in the store and install
4. Configure your API key (see below) and start the add-on

### Via HACS (Custom Repository)

1. Open HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/paolobets/hiris` with category **Add-ons**
3. Go to **Add-ons** → search for **HIRIS** → Install

---

## Configuration

| Option | Type | Default | Description |
|---|---|---|---|
| `claude_api_key` | `password` | — | Anthropic API key (required for AI features) |
| `log_level` | `list` | `info` | `debug` / `info` / `warning` / `error` |
| `theme` | `list` | `auto` | `light` / `dark` / `auto` |
| `primary_model` | `str` | `claude-sonnet-4-6` | Claude model for chat agents |
| `local_model_url` | `str` | — | Ollama base URL for local classification (e.g. `http://192.168.1.10:11434`) |
| `local_model_name` | `str` | — | Ollama model name (e.g. `llama3`) |

> If `claude_api_key` is empty, HIRIS starts in **local-only mode**: the UI and agent engine run, but Claude calls are disabled.

---

## Agent configuration

Each agent exposes the following fields in the designer UI:

| Field | Description |
|---|---|
| `name` | Display name |
| `type` | `chat` / `monitor` / `reactive` / `preventive` |
| `trigger` | `{type, interval_minutes?, entity_id?, cron?}` |
| `system_prompt` | Instructions for Claude |
| `strategic_context` | House/family context prepended to every call |
| `allowed_tools` | Which of the 8 tools this agent can call |
| `allowed_entities` | Glob patterns — e.g. `["light.*", "climate.soggiorno"]` |
| `allowed_services` | Glob patterns — e.g. `["light.*", "climate.*"]` |
| `require_confirmation` | Claude must ask user before calling `call_ha_service` |
| `restrict_to_home` | Refuse off-topic questions |
| `model` | `auto` (default) or explicit model ID |
| `max_tokens` | Max tokens per call (default 4096) |
| `budget_eur_limit` | Auto-disable when cumulative cost exceeds this (0 = unlimited) |
| `max_chat_turns` | Max conversation turns (0 = unlimited, chat agents only) |

### Automatic model selection (`model: auto`)

| Agent type | Model |
|---|---|
| `chat` | `claude-sonnet-4-6` |
| `monitor` | `claude-haiku-4-5` |
| `reactive` | `claude-haiku-4-5` |
| `preventive` | `claude-haiku-4-5` |

---

## Available tools

| Tool | Description |
|---|---|
| `get_entity_states(ids)` | Live state of one or more HA entities |
| `get_area_entities()` | All entities grouped by HA area |
| `get_home_status()` | Structured home snapshot (energy, climate, lights) |
| `get_energy_history(days)` | Historical energy consumption from HA History API |
| `get_weather_forecast(hours)` | Forecast from Open-Meteo (free, no key needed) |
| `call_ha_service(domain, service, data)` | Call any HA service (subject to `allowed_services` filter) |
| `send_notification(message, channel)` | Push via HA, Telegram, or other channels |
| `get_ha_automations()` | List HA automations |
| `trigger_automation(id)` | Trigger an HA automation |
| `toggle_automation(id, enabled)` | Enable or disable an HA automation |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  LAYER 2 — Claude Agentic Loop              │
│  Claude API + tool use (max 10 iterations)  │
│  • Chat NL interface                        │
│  • Proactive monitors                       │
│  • Semantic Home Map + RAG pre-fetch        │
│  • LLM Router (optional Ollama offload)     │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (local)       │
│  Runs offline — no AI cost                  │
│  • APScheduler for monitor/preventive       │
│  • HA WebSocket for reactive triggers       │
│  • Per-agent budget enforcement             │
└─────────────────────────────────────────────┘
```

**Stack:** Python 3.11 · aiohttp · Anthropic SDK · APScheduler · Open-Meteo

---

## Versioning

HIRIS uses semantic versioning. The project remains at `0.x.x` (experimental) until Phase 1 is fully stable. `1.0.0` marks the first production-ready release.

**Current version: v0.2.2**

---

## Roadmap

### Phase 1 — Beta Standalone (current)
- [x] HA client (REST + History + WebSocket)
- [x] Claude agentic loop with 8 tools
- [x] 4 agent types (chat, monitor, reactive, preventive)
- [x] Agent designer UI
- [x] Chat NL interface with conversation history
- [x] Semantic Home Map (rule + LLM classification)
- [x] RAG pre-fetch
- [x] LLM Router with optional Ollama offload
- [x] Per-agent security filters
- [x] Per-agent budget & usage tracking
- [x] Notifications: HA push + Telegram
- [x] Mobile-optimized UI

### Phase 2 — Retro Panel Plugin (planned)
- [ ] Canvas drag-and-drop agent designer (n8n style)
- [ ] Retro Panel plugin integration (embedded chat in kiosk)
- [ ] Conversation memory (Redis or SQLite)
- [ ] Additional tools: email, HTTP custom, calendar
- [ ] HACS official distribution

---

## License

MIT
