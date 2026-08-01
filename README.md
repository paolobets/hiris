<p align="center">
  <img src="hiris/icon.png" alt="HIRIS logo" width="120"/>
</p>

<h1 align="center">HIRIS</h1>
<p align="center"><em>Home Intelligent Reasoning & Integration System</em></p>

<p align="center">
  <a href="https://github.com/paolobets/hiris/releases"><img src="https://img.shields.io/github/v/release/paolobets/hiris?label=version&color=blue" alt="version"/></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2023.1%2B-41BDF5" alt="Home Assistant"/>
  <img src="https://img.shields.io/badge/arch-amd64%20%7C%20aarch64-lightgrey" alt="arch"/>
  <img src="https://img.shields.io/badge/license-Proprietary-red" alt="license"/>
</p>

<p align="center">
  <strong>An AI agent platform for Home Assistant that actually reasons about your home.</strong>
</p>

---

## Why HIRIS exists

Most smart home AI tools are glorified voice assistants: they hear a command and execute it. HIRIS is different — it *thinks* before acting.

When you ask HIRIS why your electricity bill is higher this month, it queries your energy sensors, checks yesterday's weather forecast it already fetched, looks at which appliances ran the most, and gives you a reasoned answer. When it detects an anomaly at 2 AM it doesn't just send a notification — it evaluates the context, decides if it's worth waking you up, and tells you exactly what it found.

HIRIS is built on four ideas:

- **Three clear entities, not one blob** — Chatbot, Agentbot and Brain each have one job and one contract (see below), so you always know why something happened
- **Security is structural, not a setting** — every action, from any surface, passes through the same semaforo (tier + denylist + step-up); an Agentbot can never choose its own action, only trigger a declared one
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

### Three entities, one clear job each

| Entity | What it does | How it reasons | Who creates it |
|---|---|---|---|
| **Chatbot** | Conversational — you ask, it answers. | Free-form prompt; can read HA freely and use tools within its allowlist; actions are gated by the semaforo. **No autonomous trigger** — it only runs when you talk to it. | You |
| **Agentbot** | Autonomous — acts or notifies on its own, on a trigger (event or schedule), without you asking. | A restricted, tool-free reasoning step (optional) that returns a JSON verdict — never a free-form action. The action it may take is **declared in its configuration**, never chosen by the AI. Gated by the semaforo. | The Brain proposes one, or you create it directly |
| **Brain** | The fulcrum — observes the house, tracks habits, and proposes (new Agentbots, HA automations, config changes). Prefers flagging a problem and suggesting the fix over acting on its own. | Continuous reasoning over the home's state; lives on the app's home screen (`#/`). | Built-in — always there |

### Goal-first creation

Instead of picking "Chatbot or Agentbot" in front of an empty form, you start
from `#/nuovo` with a goal in plain language ("avvisami se la porta resta
aperta" vs "rispondimi quante luci sono accese"). HIRIS derives the right
entity type with a deterministic heuristic — **no LLM call** — walks you
through a few guided steps for that type, and always lets you confirm or
override the suggested type before continuing. The full editor (`#/chatbots/
new`, `#/agentbots/new`) remains available for starting from a blank form.

### Security: one gate, no exceptions

Every action HIRIS could take on your home — from a Chatbot, an Agentbot, or
the gateway — passes through the same **semaforo**: a tier per domain/entity
(green/yellow/red/off), a hard denylist for dangerous domains (locks, alarms,
covers, sirens, garage doors), and step-up confirmation for anything above
green. There is no surface that bypasses it, and an Agentbot's reasoning step
never gets to invent an action — only the action declared in its own
configuration can ever fire.

### Semantic Home Map

HIRIS automatically builds a semantic model of your home by classifying every entity (lights, climate sensors, appliances, power meters) using rule-based logic + optional LLM assistance. This map powers:

- Structured home snapshots injected into every AI call
- RAG pre-fetch: live entity states loaded before each call (Claude gets real data without needing to call a tool first)
- Energy tools that work without any manual entity configuration

### Multi-provider LLM

Supported backends: Anthropic Claude (API or Claude Max subscription), OpenAI (GPT-4o, GPT-4.1, o-series), OpenRouter, any Ollama-compatible local model — each toggled on independently, used only when active *and* credentialed.

Every Chatbot and every Agentbot picks its own model (or `auto`), and the Brain has its own `brain_model` setting — there's no more one-size-fits-all mapping by entity type. The model dropdown is populated live from your active, credentialed providers.

**Fallback chain:** when `model="auto"`, if the primary backend is unavailable the next one in the strategy chain is tried automatically (`balanced`: Claude → OpenRouter → OpenAI → Ollama; `quality_first`: Claude → OpenAI → OpenRouter → Ollama; `cost_first`: Ollama → OpenRouter → OpenAI → Claude).

### Memory & RAG

HIRIS stores and retrieves memories across conversations. Before every Claude call, relevant past interactions are injected as context — so a Chatbot remembers what happened last Tuesday and can build on it.

### Notifications everywhere

Send alerts via Home Assistant push, Telegram, WhatsApp, ntfy, Gotify, Pushover, Slack, and 80+ other channels — all configured through a single `apprise_urls` option.

### HA and system health monitoring

A live health snapshot of your Home Assistant installation — unavailable entities, integration errors, per-integration native health, add-on states and host disk space from the Supervisor, and available updates for core, OS, Supervisor and add-ons — updated in real time via WebSocket and refreshed every 30 minutes. Accessible to any Chatbot (within its tool allowlist) via the `get_ha_health` tool, via `GET /api/health/ha`, and feeds the Brain's own health scan.

The Brain's own advisories (low batteries, entities unavailable for days, broken automations, dangerous domains left enabled) are readable from chat via `get_advisories`, and a push notification goes out for **severe** ones — once when the issue appears, again only if it reopens or escalates, with a 12-hour quiet period (toggle: `brain_notify_high`). `get_logbook` answers "what happened last night?" and `render_template` evaluates an HA Jinja template on the spot.

**All of it is read-only, by design.** HIRIS reports available updates but never applies them, and cannot start, stop, restart or update anything — neither directly nor by raising a proposal.

### Proposal workflow

The Brain proposes new Agentbots, HA automations, and config changes for human review instead of applying them on its own — it prefers to flag a problem and suggest the fix. Proposals show up in the Brain's home stream (`#/`) and in `#/proposals`, with approve/reject actions, keeping a human in the loop for every configuration change.

---

## Use cases

### Door left open
An **Agentbot** with an event trigger on the front door contact sensor
(`entity_id`, `operator: ">"` a duration in minutes) sends a notification the
moment the condition is met — no polling, no custom code. Turn on its
optional reasoning step to have the model phrase the alert instead of a flat
template message.

### Energy anomaly alert
An **Agentbot** with an event trigger on your grid power sensor
(`threshold` in watts) notifies you the instant consumption crosses the
line. Its action is declared up front — the AI never decides *what* to do,
only whether and how to phrase the notification.

### Morning briefing, pre-heat, or a security sweep across multiple sensors
These need to read several sources (forecast, calendar, more than one
sensor) and reason across them — which is exactly what a **Chatbot**'s free
tool access is for. Ask it in chat, or from a Lovelace card, whenever you
want the answer: *"give me yesterday's energy summary and today's
forecast"*. An Agentbot's reasoning step is intentionally tool-free, so this
kind of multi-source, on-demand judgment call belongs to a Chatbot, not an
Agentbot.

### Chat for guests
A **Chatbot** restricted to lighting and climate only, with `restrict_to_home: true` and `require_confirmation: true` — so guests can control the house without accessing sensitive data or executing unreviewed actions.

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
| `claude_api_key` | Anthropic API key — required for Claude models |
| `openai_api_key` | OpenAI API key — optional, enables GPT models |
| `local_model.url` | Ollama base URL for local inference (e.g. `http://192.168.1.10:11434`) |
| `local_model.model` | Ollama model name (e.g. `qwen2.5:27b`) |
| `llm_strategy` | `balanced` (default) · `quality_first` · `cost_first` |
| `mqtt.host` | MQTT broker for native HA entity publishing (optional) |
| `apprise_urls` | Notification URLs — one per channel (optional) |
| `internal_token` | Shared secret for inter-addon calls (optional) |

> If `local_model.url` and `local_model.model` are set, HIRIS runs fully offline using Ollama as the AI backend — the full agentic loop, tool use, and all three entities remain available. No API key is required. If neither a cloud key nor a local model is configured, AI calls are disabled.

---

## Lovelace Chat Card

Add the chat card to any dashboard:

```yaml
type: custom:hiris-chat-card
chatbot_id: hiris-default
title: "Home Assistant"
```

HIRIS auto-deploys the card to `/local/hiris/` and registers the Lovelace resource on startup. No manual resource configuration needed.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  LAYER 2 — AI Reasoning                     │
│  Claude / OpenAI / OpenRouter / Ollama      │
│  • Chatbot — free-form chat + tool use      │
│  • Agentbot — tool-free JSON-verdict step   │
│  • Brain — continuous reasoning + proposals │
│  • Semantic Home Map + RAG pre-fetch        │
│  • LLM Router with strategy + fallback      │
│  • Memory store (vector search)             │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  LAYER 1 — Local Flow Engine                │
│  Runs 100% offline — zero AI cost           │
│  • APScheduler (Agentbot schedule triggers) │
│  • HA WebSocket (Agentbot event triggers)   │
│  • Semaforo: tier + denylist + step-up gate │
│  • Task engine with action chaining         │
└─────────────────────────────────────────────┘
```

**Stack:** Python 3.13 · aiohttp · Anthropic SDK · OpenAI SDK · APScheduler · SQLite · Open-Meteo

---

## Documentation

| Document | Language |
|---|---|
| [Configuration guide — Apprise & Memory/RAG](docs/configuration-guide.md) | 🇬🇧 English |
| [Guida alla configurazione — Apprise & Memoria/RAG](docs/guida-configurazione.md) | 🇮🇹 Italiano |
| [Full local mode — zero cloud dependencies](docs/full-local-mode.md) | 🇬🇧 English |
| [Modalità completamente locale — zero cloud](docs/full-local-mode-it.md) | 🇮🇹 Italiano |
| [MQTT integration — HA entities & automations](docs/mqtt-integration.md) | 🇬🇧 English |
| [How it works — architecture & internals](docs/how-it-works.md) | 🇬🇧 English |
| [Come funziona — architettura e internals](docs/come-funziona.md) | 🇮🇹 Italiano |
| [Technical architecture](docs/architecture.md) | 🇬🇧 English |
| [Architettura tecnica](docs/architettura.md) | 🇮🇹 Italiano |
| [Use cases & examples](docs/use-cases.md) | 🇬🇧 English |
| [Casi d'uso ed esempi](docs/casi-duso.md) | 🇮🇹 Italiano |

---

## License

Copyright © 2026 Paolo Bets. All Rights Reserved.  
Personal non-commercial use permitted. See [LICENSE](LICENSE) for details.
