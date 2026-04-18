# HIRIS — Design Spec
**Home Intelligent Reasoning & Integration System**

**Date:** 2026-04-18
**Status:** Feasibility Study / Brainstorming
**Branch:** claude/beautiful-booth-639783 (study branch, no production changes)

---

## 1. Product Identity

**HIRIS** is a standalone Home Assistant Add-on that provides an AI-powered agent platform for smart home management. It combines a visual flow designer with Claude API reasoning to enable proactive, reactive, and conversational home automation.

**Acronym:** **H**ome **I**ntelligent **R**easoning & **I**ntegration **S**ystem

**Relationship to Retro Panel:**
- Phase 1: Standalone HA Add-on, independent of Retro Panel
- Phase 2: Becomes a Retro Panel plugin (embedded chat in kiosk, shared auth)
- Separation rationale: Retro Panel stays focused on its "minimal kiosk" identity; users who don't want AI don't install HIRIS

---

## 2. Infrastructure

| Property | Value |
|---|---|
| Type | HA Add-on (separate container) |
| Add-on name | `hiris` |
| Ingress | `ingress: true`, `ingress_port: 8099` (no external ports exposed) |
| Authentication | HA Supervisor Ingress (no direct port access) |
| Backend | Python 3.11 + aiohttp |
| Frontend | Modern JS (no iOS 12 constraint — this is not the kiosk) |
| AI Model | claude-sonnet-4-6 (tool use / agentic loop) |
| Configuration | HA add-on options (managed by Supervisor) |

**HA panel integration:** Automatic via Supervisor Ingress — no manual `panel_iframe` needed. HA adds the panel entry automatically when `ingress: true` is set in `config.yaml`.

---

## 3. Architecture

### Two-Layer Design

```
┌─────────────────────────────────────────────┐
│  LAYER 2 — Claude Agentic Loop              │
│  Claude API + tool use                      │
│  • Chat NL interface                        │
│  • Proactive monitors (anomaly detection)   │
│  • Multi-source reasoning (meteo+energy)    │
│  Claude decides autonomously which tools    │
│  to call based on context                   │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (local)       │
│  Runs 100% offline, no AI required          │
│  • Triggers: schedule / state_changed /     │
│    manual                                   │
│  • Steps: read HA data, condition, delay    │
│  • Actions: HA service call, notification   │
└─────────────────────────────────────────────┘
```

**When to use each layer:**
- Simple time-based automations → Layer 1 (no Claude cost, no internet dependency)
- Complex reasoning, NL chat, multi-source decisions → Layer 2 (Claude)

### Backend File Structure

```
hiris/
├── config.yaml                  # HA add-on manifest
├── app/
│   ├── server.py                # aiohttp server + routes
│   ├── agent_engine.py          # Flow engine scheduler + state machine
│   ├── claude_runner.py         # Claude API agentic loop + tool orchestrator
│   ├── tools/
│   │   ├── ha_tools.py          # get_entity_states, call_ha_service
│   │   ├── energy_tools.py      # get_energy_history
│   │   ├── weather_tools.py     # get_weather_forecast (Open-Meteo)
│   │   ├── notify_tools.py      # send_notification (multi-channel)
│   │   └── automation_tools.py  # get_ha_automations, trigger/toggle
│   ├── api/
│   │   ├── handlers_chat.py     # POST /api/chat
│   │   ├── handlers_agents.py   # CRUD /api/agents
│   │   └── handlers_status.py   # GET /api/status
│   ├── proxy/
│   │   └── ha_client.py         # HA REST + History + WebSocket client
│   └── static/
│       ├── index.html           # Chat UI (/)
│       └── config.html          # Agent Designer (/config)
```

---

## 4. Claude Tool Kit — Phase 1

Claude has access to 8 tools for reasoning and action:

| Tool | Signature | Data Source |
|---|---|---|
| `get_energy_history` | `(days: int) → list` | HA History API |
| `get_entity_states` | `(ids: list[str]) → dict` | HA REST `/api/states` |
| `get_weather_forecast` | `(hours: int) → dict` | Open-Meteo API (free, no key) |
| `call_ha_service` | `(domain, service, data) → bool` | HA REST (whitelisted) |
| `send_notification` | `(message, channel) → bool` | Multi-channel (see §6) |
| `get_ha_automations` | `() → list` | HA REST `/api/config/automation` |
| `trigger_automation` | `(automation_id) → bool` | HA `automation.trigger` service |
| `toggle_automation` | `(automation_id, enabled) → bool` | HA `automation.turn_on/off` |

**Service whitelist (call_ha_service):**
Same security model as Retro Panel — allowed domains/services defined in `hiris_config.json`. Default whitelist covers: light, switch, climate, cover, scene, script, automation, input_boolean.

---

## 5. Agent Types

### 5.1 Proactive Monitor
- **Trigger:** schedule (every N minutes)
- **Pattern:** gather data → Claude reasons → if anomaly: notify + recommend
- **Example:** "Energy consumption is 3.2kW with washing machine + oven active. Solar production is only 0.4kW. Recommend delaying washing machine 2h — sun forecast improving."

### 5.2 Reactive Agent
- **Trigger:** HA `state_changed` WebSocket event on specific entities
- **Pattern:** state change → Claude reasons over context → act/notify
- **Example:** "Garage door open for 30min → send notification: 'Garage still open, want me to close it?'"

### 5.3 Preventive Scheduler
- **Trigger:** fixed time (e.g., 06:00 daily)
- **Pattern:** read yesterday's history + weather forecast → Claude decides → act autonomously
- **Example:** "Yesterday: 35°C max, 25% humidity. Forecast: sunny morning. Activating irrigation for 20 minutes at 06:30."

### 5.4 Chat NL Agent
- **Trigger:** user message in chat interface
- **Pattern:** user question → Claude gathers data with tools → natural language response + optional action
- **Example:** "When should I start the washing machine?" → Claude checks solar production, weather forecast, time-of-use tariffs → "I'd suggest 14:30 when solar production peaks at ~2.5kW."

---

## 6. Notification Channels — Phase 1

| Channel | Mechanism | Use Case |
|---|---|---|
| **HA Mobile App** | `notify.*` HA service call | Push to phone when away |
| **Telegram** | Telegram Bot API via HTTP | Real-time rich messages |
| **Retro Panel kiosk** | `POST /api/notify` → Retro Panel toast overlay | Immediate on-screen display |

The Retro Panel notification API becomes the first integration contract between the two products, establishing the foundation for the Phase 2 plugin.

---

## 7. Web Interface

### 7.1 Chat Interface ( `/` )

- Sidebar: list of configured agents with status (active/paused)
- Main area: chat conversation with Claude
- Features: agent trigger buttons, last notification summary, conversation history (in-memory, session-scoped)
- Mobile-friendly: accessible from iPad kiosk browser or HA mobile app

### 7.2 Agent Designer ( `/config` )

**Step-based editor (Phase 1):**

Each agent is composed of ordered steps:

```
[TRIGGER] → [GATHER DATA] → [CLAUDE REASONS] → [ACTION / NOTIFY]
```

Step types:
- **Trigger:** schedule (cron), state_changed (entity + condition), manual
- **Gather Data:** entity picker (multi-select HA entities), energy history (N days)
- **Claude Reasons:** system prompt textarea, tool permissions checkboxes, model selector
- **HA Action:** service picker (domain + service + data)
- **Notification:** channel selector + message template
- **Condition:** entity state comparison (value, operator)
- **Delay:** wait N seconds/minutes

Each agent has a **Test Runner** button that executes the flow immediately with live output.

---

## 8. Data Flow Examples

### Example 1: "Quando avvio la lavatrice?"

```
User types in chat
    ↓
POST /api/chat → claude_runner.py
    ↓
Claude receives message + system context (home description)
    ↓
Claude calls: get_entity_states(["sensor.solar_power", "sensor.grid_import"])
Claude calls: get_weather_forecast(hours=8)
Claude calls: get_energy_history(days=1)
    ↓
Claude reasons: "Solar peaks at 14:30 (~2.5kW). Currently 0.4kW. Grid import active."
    ↓
Response: "Ti consiglio le 14:30 — produzione solare prevista 2.5kW,
           coprirà i 1.8kW della lavatrice senza prelievo da rete."
```

### Example 2: Proactive energy monitor (every 5 min)

```
agent_engine.py fires scheduled trigger
    ↓
claude_runner.py invoked with agent config + system prompt
    ↓
Claude calls: get_entity_states(["sensor.power_total", "switch.washing_machine", "switch.oven"])
    ↓
Claude reasons: "3.2kW total. Washing machine (1.8kW) + oven (1.4kW) active. Solar 0.4kW."
Claude decides: anomaly detected → notify
    ↓
Claude calls: send_notification("Alto consumo: lavatrice + forno attivi. Posticipare lavatrice?", "retropanel")
Claude calls: send_notification("...", "telegram")
    ↓
Toast appears on Retro Panel kiosk + Telegram message sent
```

### Example 3: Morning irrigation decision (06:00 daily)

```
agent_engine.py fires at 06:00
    ↓
Claude calls: get_energy_history(days=1)  → yesterday temp 35°C, humidity 22%
Claude calls: get_weather_forecast(hours=6) → sunny, low humidity forecast
Claude calls: get_entity_states(["sensor.soil_moisture"])
    ↓
Claude reasons: "Dry conditions yesterday + dry forecast + low soil moisture = irrigate"
    ↓
Claude calls: call_ha_service("switch", "turn_on", {"entity_id": "switch.irrigazione"})
Claude calls: send_notification("Irrigazione attivata (20 min) — ieri 35°C, umidità 22%.", "retropanel")
```

---

## 9. Security Model

- **Claude API key:** stored in HA add-on options (encrypted at rest by HA Supervisor), never exposed to browser
- **HA token:** fetched from `SUPERVISOR_TOKEN` env var (same as Retro Panel)
- **Service call whitelist:** configurable per-agent, default restricts to safe domains
- **Tool permissions per agent:** each agent declares which tools it can use (principle of least privilege)
- **No persistent storage of conversations:** chat history is in-memory, cleared on restart
- **Telegram token:** stored in add-on options, server-side only

---

## 10. Feasibility Assessment

| Concern | Assessment |
|---|---|
| Hardware (mini PC 16GB) | No constraint — Python flow engine is lightweight, Claude API is remote |
| iOS 12 kiosk | Not affected — HIRIS UI is a separate web app, no iOS constraint |
| Claude API costs | Controlled — tools called only when agent fires or user chats; simple flows skip Claude entirely |
| HA integration complexity | Low — same pattern as Retro Panel (ha_client.py, Supervisor token) |
| Flow designer complexity | Medium — step-based editor (Phase 1) is feasible without canvas libraries |
| Open-Meteo | Free, no API key, reliable, covers all European locations |
| Retro Panel notification API | Requires small addition to Retro Panel (`POST /api/notify` endpoint) |
| Phase 2 canvas designer | High effort — defer to after Phase 1 beta validation |

---

## 11. Phase Roadmap

### Phase 1 — Beta Standalone
- [ ] HA add-on structure (config.yaml, Docker, aiohttp server)
- [ ] HA client (REST + History + WebSocket)
- [ ] Claude runner with 8 tools
- [ ] Flow engine (scheduler + state_changed trigger)
- [ ] Step-based agent designer UI
- [ ] Chat NL interface
- [ ] Notification: HA push + Telegram + Retro Panel toast
- [ ] Agent types: Monitor, Reactive, Preventive, Chat
- [ ] Security: key vault, service whitelist, tool permissions
- [ ] Test runner per agent

### Phase 2 — Plugin + Canvas
- [ ] Canvas drag-and-drop designer (n8n style)
- [ ] Retro Panel plugin integration (embedded chat in kiosk)
- [ ] Conversation memory (Redis or SQLite)
- [ ] Additional tools: email (SMTP), HTTP custom, calendar
- [ ] Multi-user / role support
- [ ] HACS official distribution

---

## 12. Open Questions (for future sessions)

1. **Agent library:** ship with pre-built agent templates (energy monitor, irrigation, etc.) or blank canvas only?
2. **Conversation memory:** session-scoped (simple) vs persistent SQLite (powerful but complex)?
3. **Retro Panel `/api/notify`:** what's the minimal API contract needed for Phase 1 integration?
4. **Open-Meteo coordinates:** auto-detect from HA `homeassistant.latitude/longitude` or manual config?
5. **Claude model:** claude-sonnet-4-6 default, allow user to override to claude-haiku-4-5 for cost savings?

---

*Feasibility study — no code changes made. Implementation to be planned in a separate session.*
