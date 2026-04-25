# HIRIS — Claude Code Context

## What is HIRIS

**HIRIS** (Home Intelligent Reasoning & Integration System) is a standalone **Home Assistant Add-on** that provides an AI-powered agent platform for smart home management. It combines a Python flow engine with a Claude API agentic loop.

**Relationship to Retro Panel:**
- Phase 1: Standalone HA Add-on, independent of Retro Panel
- Phase 2: Becomes a Retro Panel plugin (embedded chat in kiosk, shared auth)
- Separation rationale: Retro Panel stays a "minimal kiosk"; users who don't want AI don't install HIRIS

Full design spec: [`docs/2026-04-18-hiris-design.md`](docs/2026-04-18-hiris-design.md)

---

## Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11 + aiohttp |
| AI | Claude API (claude-sonnet-4-6), tool use / agentic loop |
| Frontend | Modern JS (no iOS 12 constraint) |
| HA integration | Supervisor Ingress, `SUPERVISOR_TOKEN` env var |
| Config | HA add-on options (`config.yaml`) |
| Port | 8099 (internal only, via Ingress) |

---

## Two-Layer Architecture

```
┌─────────────────────────────────────────────┐
│  LAYER 2 — Claude Agentic Loop              │
│  Claude API + tool use                      │
│  • Chat NL interface                        │
│  • Proactive monitors (anomaly detection)   │
│  • Multi-source reasoning (meteo+energy)    │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│  LAYER 1 — Python Flow Engine (local)       │
│  Runs 100% offline, no AI required          │
│  • Triggers: schedule / state_changed /     │
│    manual                                   │
│  • Actions: HA service call, notification   │
└─────────────────────────────────────────────┘
```

- Simple time-based automations → Layer 1 (no Claude cost, no internet)
- Complex reasoning, NL chat, multi-source decisions → Layer 2

---

## 8 Claude Tools (Phase 1)

| Tool | Description |
|---|---|
| `get_entity_states(ids)` | HA REST `/api/states` |
| `get_energy_history(days)` | HA History API |
| `get_weather_forecast(hours)` | Open-Meteo (free, no key) |
| `call_ha_service(domain, service, data)` | HA REST, whitelisted domains |
| `send_notification(message, channel)` | HA push / Telegram / Retro Panel toast |
| `get_ha_automations()` | HA REST `/api/config/automation` |
| `trigger_automation(id)` | HA `automation.trigger` |
| `toggle_automation(id, enabled)` | HA `automation.turn_on/off` |

---

## 4 Agent Types

| Type | Trigger | Pattern |
|---|---|---|
| **Proactive Monitor** | Schedule (every N min) | gather → Claude reasons → if anomaly: notify |
| **Reactive Agent** | HA `state_changed` WebSocket | state change → Claude → act/notify |
| **Preventive Scheduler** | Fixed time (e.g. 06:00) | history + forecast → Claude → autonomous action |
| **Chat NL Agent** | User message in UI | question → Claude + tools → NL response |

---

## Project Structure

```
hiris/
├── config.yaml          # HA add-on manifest (name, arch, ingress, options)
├── Dockerfile           # HA add-on container
├── run.sh               # Entrypoint (bashio config → python -m app.main)
├── requirements.txt     # aiohttp, anthropic, python-dotenv
├── app/
│   ├── main.py          # aiohttp app factory + web.run_app
│   ├── routes.py        # Route registration
│   ├── ha_client.py     # HA REST + History + WebSocket client
│   └── config.py        # Config helpers
└── docs/
    └── 2026-04-18-hiris-design.md  # Full design spec
```

**Target structure (Phase 1 implementation):**
```
app/
├── server.py            # aiohttp server + routes
├── agent_engine.py      # Flow engine scheduler + state machine
├── claude_runner.py     # Claude API agentic loop + tool orchestrator
├── tools/
│   ├── ha_tools.py
│   ├── energy_tools.py
│   ├── weather_tools.py
│   ├── notify_tools.py
│   └── automation_tools.py
├── api/
│   ├── handlers_chat.py
│   ├── handlers_agents.py
│   └── handlers_status.py
├── proxy/
│   └── ha_client.py
└── static/
    ├── index.html       # Chat UI (/)
    └── config.html      # Agent Designer (/config)
```

---

## Roadmap

### Phase 0 — Scaffold (done)
- HA add-on structure (config.yaml, Docker, aiohttp server)
- Basic routes: `/` placeholder, `/api/health`

### Phase 1 — Beta Standalone
- HA client (REST + History + WebSocket)
- Claude runner with 8 tools
- Flow engine (scheduler + state_changed trigger)
- Step-based agent designer UI
- Chat NL interface
- Notifications: HA push + Telegram + Retro Panel toast
- Security: API key vault, service whitelist, tool permissions per agent
- Test runner per agent

### Phase 2 — Retro Panel Plugin + Canvas
- Canvas drag-and-drop designer (n8n style)
- Retro Panel plugin integration (embedded chat in kiosk)
- Conversation memory (Redis or SQLite)
- Additional tools: email, HTTP custom, calendar
- HACS official distribution

---

## Security Notes

- `CLAUDE_API_KEY`: HA add-on option (encrypted by Supervisor), never exposed to browser
- `SUPERVISOR_TOKEN`: env var injected by HA Supervisor
- Service call whitelist: configurable per-agent
- No persistent storage of chat history (in-memory, session-scoped)

---

## Release Procedure

Follow these steps **in order** whenever asked for a release ("fai il release", "prepara la X.Y.Z", "rilascia", "nuova versione"):

### Step 1 — Scope commits
```bash
git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline
```
Collect all commits since the last tag (or since repo start if no tags yet).

### Step 2 — Propose version
Determine bump type:
- Any `feat:` or `feat(...):` → minimum **minor** bump (0.5.x → 0.6.0)
- Any `BREAKING CHANGE` or `!:` → **major** bump
- Only `fix:`, `chore:`, `docs:`, `test:` → **patch** bump (0.5.0 → 0.5.1)

Show proposed version to user. Wait for confirmation. User may override.

### Step 3 — Draft CHANGELOG section
Generate a Keep-a-Changelog section and show it to the user:
```
## [X.Y.Z] — YYYY-MM-DD

### Added      ← feat: commits
### Fixed      ← fix: commits
### Changed    ← refactor:, perf: commits
### Removed    ← commits that delete features
```
Wait for user approval. Incorporate any edits.

### Step 4 — Update files (after user approves)
a. Insert the approved section into `CHANGELOG.md` immediately after the `# HIRIS — Changelog` heading line.
b. Update `hiris/config.yaml` → `version: "X.Y.Z"`.

### Step 5 — Run release script (Bash only — never PowerShell)
```bash
python scripts/release.py --version X.Y.Z
```

### Step 6 — Report
Show full script output to the user.
- Exit 0 → announce "Release vX.Y.Z completato ✓ — HA rileverà l'aggiornamento al prossimo check."
- Non-zero → show the failing step. **Do NOT retry automatically.** Wait for the user to fix the issue.
