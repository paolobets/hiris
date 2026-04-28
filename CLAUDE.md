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

## Claude Tools (Phase 1 — current)

| Tool | Description |
|---|---|
| `get_entity_states(ids)` | HA REST `/api/states` |
| `get_area_entities()` | Area→entity mapping via WS registry |
| `get_home_status()` | Compact summary of useful entities |
| `get_entities_on()` | All entities currently in `on` state |
| `get_entities_by_domain(domain)` | Entities filtered by domain |
| `get_energy_history(days)` | HA History API |
| `get_weather_forecast(hours)` | Open-Meteo (free, no key) |
| `call_ha_service(domain, service, data)` | HA REST, whitelisted domains |
| `send_notification(message, channel)` | HA push / Telegram / Retro Panel toast |
| `get_ha_automations()` | HA REST `/api/config/automation` |
| `trigger_automation(id)` | HA `automation.trigger` |
| `toggle_automation(id, enabled)` | HA `automation.turn_on/off` |
| `get_calendar_events(hours, calendar_entity)` | HA calendar integration |
| `set_input_helper(entity_id, value)` | input_boolean/number/text/select |
| `create_task(...)` / `list_tasks()` / `cancel_task(id)` | Internal task management |

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

### Phase 0 — Scaffold ✅ done
- HA add-on structure (config.yaml, Docker, aiohttp server)
- Basic routes: `/` placeholder, `/api/health`

### Phase 1 — Beta Standalone ✅ done (v0.3.17)
- HA client (REST + History + WebSocket)
- Claude runner with 15+ tools + retry logic
- Flow engine (scheduler + state_changed + cron trigger)
- Step-based agent designer UI + onboarding wizard
- Chat NL interface with persistent history
- Notifications: HA push + Telegram
- Security: API key vault, service whitelist, tool permissions per agent
- Test runner per agent, budget auto-disable, per-agent usage tracking
- SemanticContextMap + KnowledgeDB (area-aware context)
- Task engine, LLM Router (local model support)

### Phase 1.5 — Lovelace Dashboard Card ✅ done (v0.5.16)
- `hiris-chat-card` custom element + card picker registration
- Visual config editor (`hiris-chat-card-editor`)
- Auto-deploy to `/local/hiris/` + Lovelace resource registration via WebSocket
- Ingress URL discovery via `hiris-ingress.json` (fixes 503 on random ingress token)
- Animated typing indicator (HIRIS icon + 3 dots)

### Phase 2 — Sprint Plan (v0.6.x → v0.8.x)

Development organized in 6 competency-based sprints. **Sprint 0 must ship before any feature sprint.**
Full detail in [`docs/HIRIS_CLAUDE_CODE_PROMPT.md`](docs/HIRIS_CLAUDE_CODE_PROMPT.md).

#### Sprint 0 — Critical Bugfixes ✅ done (v0.6.0)
- `handlers_agents.py` + `handlers_usage.py` — `get("llm_router") or get("claude_runner")` fix
- `app/ha_client.py` — orphan stub removed; real impl is `proxy/ha_client.py`
- `SemanticContextMap` — JSON persist/load so classifications survive restart
- EUR exchange rate — centralized into `config.EUR_RATE` constant
- MQTT: `update_agent()` now calls `publish_agent_state()` on `enabled` change
- Non-blocking file I/O — `_save()` / `_save_usage()` / `SemanticContextMap.save()` use `run_in_executor`

#### Sprint A — HA-Bridge ✅ done (v0.6.1)
*Competenza: Python backend + HA WebSocket/MQTT*
- MQTT 2-way: subscribe `hiris/agents/+/{enabled,run_now}/set`; `AgentEngine._handle_mqtt_command` callback
- New MQTT entities: `last_result`, `budget_remaining_eur` ("unlimited" when no limit), `tokens_used_today` (daily lazy reset), `run_now` button
- Tool: `http_request(url, method?, headers?, body?)` — Option C security: structured `AllowedEndpoint`, DNS pinning (`_PinnedResolver`), correct RFC1918 DENY_NETS, `SOCK_STREAM` for Alpine/musl, redirects off by default, 4KB cap, internal header stripping
- `Agent.allowed_endpoints: list[dict] | None` — tool hidden from Claude when `None`
- *(§2A.2 REST bridge: deferred — Lovelace card already uses REST+SUPERVISOR\_TOKEN)*
- *(§2A.5 HA Services formal registration: deferred to Phase 3)*

#### Sprint B — Tool Expansion ✅ done (v0.6.x)
*Competenza: External APIs + Python tool layer*
- Tool: `create_calendar_event(calendar_entity, summary, event_type, ...)` — datetime + all-day events
- Apprise unified notification layer — replaces dedicated Telegram/WhatsApp tools; 80+ channels via `apprise_urls` config
- `EVALUATION_ONLY_TOOLS` frozenset: non-chat agents restricted to read-only + task-mgmt tools (no direct HA execution)
- `Agent.trigger_on: list[str]` — eval statuses (OK/ATTENZIONE/ANOMALIA) that activate `agent.actions`
- `AgentEngine._execute_agent_actions()` — dispatches notify/call_service/wait/verify via TaskEngine immediate/delay/time_window tasks
- `on_fail: continue|stop` per action; `_check_budget_auto_disable` helper extracted
- `TaskEngine`: `immediate` trigger type; per-action `on_fail` loop with `_stop` flag
- config.html UI: trigger_on checkboxes, on_fail dropdown, wait/verify action types with child-action editor ("Poi esegui")

#### Sprint C — Memory-RAG (v0.7.x)
*Competenza: SQLite + embeddings + AI context*
- `chat_store.py`: `HISTORY_RETENTION_DAYS` configurable (default 90d, `None` = unlimited)
- sqlite-vec layer on existing DB: message vectorization + agent memory store
- Tools: `recall_memory(query, k, tags)` + `save_memory(content, tags)` exposed to Claude
- RAG injection: inject k relevant memories into system prompt before each Claude call
- Embedding provider configurable: `openai/text-embedding-3-small` (default) / `ollama/nomic-embed-text`

#### Sprint D — Multi-provider LLM (v0.7.x)
*Competenza: LLM abstraction layer — requires ADR-0002 first*
- LiteLLM integration in `backends/` (or custom shim — ADR decides)
- Advanced LLM Router: strategy `cost_first`/`quality_first`, fallback chain, `task_routing` per agent type
- `pricing.yaml`: centralized EUR/1M token cost map per model

#### Sprint E — Lovelace + HACS (v0.8.x)
*Competenza: Web Components + distribution*
- `hiris-agent-card`: agent status, budget bar, run button, last output (reuses `hiris-chat-card` patterns)
- HACS packaging (`hacs.json`, `repository.json`)
- Blueprint YAML starter pack (morning briefing, energy anomaly, door reactive)

### Phase 3 — Plugin + Canvas (v0.9.x+)
- Canvas drag-and-drop designer (n8n style)
- ✅ Retro Panel plugin integration (embedded chat in kiosk, shared auth)
- HA Services formal registration (`hiris.run_agent`, `hiris.chat`, etc.)
- Multi-user / role support

### Phase 4 — Integrazioni esterne (futuro)
- Tool: `send_email(to, subject, body)` via SMTP
- Vision tool: `analyze_image(image_source)` — camera snapshot → Claude multimodal
- Telegram bot full (long polling, `/agent`, `/status`, streaming edit)

---

## Security Notes

- `CLAUDE_API_KEY`: HA add-on option (encrypted by Supervisor), never exposed to browser
- `SUPERVISOR_TOKEN`: env var injected by HA Supervisor
- Service call whitelist: configurable per-agent
- Chat history persisted in SQLite (`/data/chat_history.db`), session-scoped with configurable retention

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

> **Recovery if the script fails after step 6 (commit/tag already created):** Do NOT re-run the script — it will fail at the commit step because the tag already exists. Instead diagnose the specific failure (e.g. push rejected → `git push origin master --tags` manually; gh CLI missing → create the GitHub Release at https://github.com/paolobets/hiris/releases/new).
