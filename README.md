<p align="center">
  <img src="hiris/icon.png" alt="HIRIS logo" width="120"/>
</p>

<h1 align="center">HIRIS</h1>
<p align="center"><em>Home Intelligent Reasoning & Integration System</em></p>

<p align="center">
  <a href="https://github.com/paolobets/hiris/releases"><img src="https://img.shields.io/github/v/release/paolobets/hiris?label=version&color=blue" alt="version"/></a>
  <img src="https://img.shields.io/badge/stage-experimental-orange" alt="stage"/>
  <img src="https://img.shields.io/badge/Home%20Assistant-2023.1%2B-41BDF5" alt="Home Assistant"/>
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20aarch64-lightgrey" alt="arch"/>
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="license"/>
</p>

<p align="center">
  <strong>An AI agent platform for Home Assistant that actually reasons about your home.</strong>
</p>

---

> **Experimental** — HIRIS is under active development. APIs and configuration options may change between releases.

## Why HIRIS exists

Most smart home AI tools are glorified voice assistants: they hear a command and execute it. HIRIS is different — it *thinks* before acting.

When you ask HIRIS why your electricity bill is higher this month, it queries your energy sensors, checks yesterday's weather forecast it already fetched, looks at which appliances ran the most, and gives you a reasoned answer. When it detects an anomaly at 2 AM it doesn't just send a notification — it evaluates the context, decides if it's worth waking you up, and tells you exactly what it found.

HIRIS is built on four ideas:

- **Agents as first-class citizens** — not a single chatbot, but a team of specialized agents each with their own trigger, permissions, and budget
- **Cost visibility** — every euro spent on AI is tracked, capped, and visible; agents auto-disable when they exceed their budget
- **Local-first when possible** — simple automations run entirely offline; AI is called only when reasoning is actually needed
- **Your home, not a generic demo** — context about your house, your family, your habits is part of every AI call

---

## What HIRIS can do

### Talk to your home in natural language

Ask anything. HIRIS queries Home Assistant in real time and reasons before answering.

```
You:   "Is the washing machine still running?"
HIRIS: "Yes — it started 47 minutes ago and is drawing 980W. Based on the
        usual cycle length, it should finish in about 25 minutes."

You:   "Turn off the living room lights and tell me how much the house is
        consuming right now."
HIRIS: "Done. Current draw: 2.4 kW — oven (1.8 kW), fridge (0.6 kW).
        Solar is producing 0W (it's night)."
```

### Four types of autonomous agents

| Type | Trigger | What it does |
|---|---|---|
| **Chat** | You send a message | Natural language interface, full tool access |
| **Monitor** | Every N minutes | Scans the house, detects anomalies, notifies only when needed |
| **Reactive** | HA `state_changed` event | Reacts instantly to sensor changes |
| **Preventive** | Fixed cron time | Prepares your day — briefings, energy reports, pre-heating |

### Semantic Home Map

HIRIS automatically builds a semantic model of your home by classifying every entity (lights, climate sensors, appliances, power meters) using rule-based logic + optional LLM assistance. This map powers:

- Structured home snapshots injected into every AI call
- RAG pre-fetch: live entity states loaded before each call (Claude gets real data without needing to call a tool first)
- Energy tools that work without any manual entity configuration

### Multi-provider LLM

HIRIS routes to the right model for each task:

- **Chat agents** → Claude Sonnet (highest quality)
- **Monitor / reactive / preventive** → Claude Haiku (cheaper for high-frequency tasks)
- **Entity classification** → Local Ollama model (free, if configured)
- **Fallback chain** → if the primary backend fails, the next one is tried automatically

Supported backends: Anthropic Claude, OpenAI (GPT-4o, GPT-4.1, o-series), any Ollama-compatible local model.

### Memory & RAG

HIRIS stores and retrieves memories across conversations. Before every Claude call, relevant past interactions are injected as context — so agents remember what happened last Tuesday and can build on it.

### Notifications everywhere

Send alerts via Home Assistant push, Telegram, WhatsApp, ntfy, Gotify, Pushover, Slack, and 80+ other channels — all configured through a single `apprise_urls` option.

---

## Use cases

### Morning briefing
A **preventive agent** triggers at 7:00 AM. It fetches yesterday's energy consumption, today's weather forecast, and any pending calendar events. Claude writes a concise briefing and sends it as a push notification.

### Energy anomaly detection
A **monitor agent** runs every 15 minutes. It checks consumption against historical patterns. If the house is drawing 3× more than usual at 11 PM with no one awake, it sends an alert with the specific culprits identified.

### Door left open
A **reactive agent** listens to the front door contact sensor. If it's been open for more than 5 minutes, Claude checks whether someone is home (via presence sensors), decides if this is unusual, and sends a contextual notification — not just "door open" but "front door has been open 7 minutes, no motion detected inside for the last 20 minutes."

### Night security check
A **monitor agent** runs at midnight. It reads all door/window sensors and presence detectors. If anything is unexpected, it sends a structured security report.

### Pre-heat before arrival
A **preventive agent** at 5:30 PM checks tomorrow's forecast and your calendar. If it's going to be cold and you have an early meeting, it starts heating 30 minutes earlier than usual.

### Chat for guests
A **chat agent** restricted to lighting and climate only, with `restrict_to_home: true` and `require_confirmation: true` — so guests can control the house without accessing sensitive data or executing unreviewed actions.

---

## Installation

### Home Assistant Add-on Store

1. **Settings → Add-ons → Add-on Store** → ⋮ → **Repositories**
2. Add: `https://github.com/paolobets/hiris`
3. Find **HIRIS** → Install
4. Set your API key in the configuration tab, then start

### HACS

1. HACS → ⋮ → **Custom repositories**
2. URL: `https://github.com/paolobets/hiris` — Category: **Add-ons**
3. Install from the Add-ons section

---

## Quick configuration

| Option | Description |
|---|---|
| `claude_api_key` | Anthropic API key — required for AI features |
| `openai_api_key` | OpenAI API key — optional, enables GPT models |
| `local_model_url` | Ollama base URL for local inference (e.g. `http://192.168.1.10:11434`) |
| `local_model_name` | Ollama model name (e.g. `llama3`) |
| `llm_strategy` | `balanced` (default) · `quality_first` · `cost_first` |
| `mqtt_host` | MQTT broker for native HA entity publishing (optional) |
| `apprise_urls` | Notification URLs — one per channel (optional) |
| `internal_token` | Shared secret for inter-addon calls (optional) |

> If `claude_api_key` is empty, HIRIS runs in **local-only mode**: the UI and flow engine work, but AI calls are disabled.

---

## Lovelace Chat Card

Add the chat card to any dashboard:

```yaml
type: custom:hiris-chat-card
agent_id: hiris-default
title: "Home Assistant"
```

HIRIS auto-deploys the card to `/local/hiris/` and registers the Lovelace resource on startup. No manual resource configuration needed.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  LAYER 2 — AI Reasoning                     │
│  Claude / OpenAI / Ollama + tool use        │
│  • Natural language chat                    │
│  • Anomaly detection & reasoning            │
│  • Semantic Home Map + RAG pre-fetch        │
│  • LLM Router with strategy + fallback      │
│  • Memory store (vector search)             │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  LAYER 1 — Local Flow Engine                │
│  Runs 100% offline — zero AI cost           │
│  • APScheduler (monitor / preventive)       │
│  • HA WebSocket (reactive triggers)         │
│  • Task engine with action chaining         │
│  • Per-agent budget enforcement             │
└─────────────────────────────────────────────┘
```

**Stack:** Python 3.13 · aiohttp · Anthropic SDK · OpenAI SDK · APScheduler · SQLite · Open-Meteo

---

## Roadmap

| Milestone | Status |
|---|---|
| Phase 1 — Core platform (tools, agents, chat UI, MQTT, Lovelace card) | ✅ v0.6.x |
| Sprint C — Memory & RAG (SQLite vector store, recall/save memory tools) | ✅ v0.6.x |
| Sprint D — Multi-provider LLM (OpenAI, Ollama, strategy routing) | ✅ v0.6.3 |
| Sprint E — Lovelace agent card + HACS packaging | 🔜 v0.8.x |
| Phase 2 — Automation intelligence (proposal workflow, anomaly baseline) | 📋 v0.9.x |
| Phase 3 — Canvas designer (n8n-style drag-and-drop) | 📋 v1.0 |

---

## Documentation

| Document | Language |
|---|---|
| [How it works — architecture & internals](docs/how-it-works.md) | 🇬🇧 English |
| [Come funziona — architettura e internals](docs/come-funziona.md) | 🇮🇹 Italiano |
| [Technical architecture](docs/architecture.md) | 🇬🇧 English |
| [Architettura tecnica](docs/architettura.md) | 🇮🇹 Italiano |
| [Use cases & examples](docs/use-cases.md) | 🇬🇧 English |
| [Casi d'uso ed esempi](docs/casi-duso.md) | 🇮🇹 Italiano |
| [Roadmap](docs/roadmap.md) | 🇬🇧 English |

---

## License

Copyright © 2026 Paolo Bets. All Rights Reserved.  
Personal non-commercial use permitted. See [LICENSE](LICENSE) for details.
