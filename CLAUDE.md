# HIRIS — Claude Code Context

## What is HIRIS

**HIRIS** (Home Intelligent Reasoning & Integration System) is a standalone **Home Assistant Add-on** that provides an AI-powered agent platform for smart home management, built around three AI entities — **Chatbot**, **Agentbot**, **Brain** (see below) — all gated by a single security **semaforo**.

---

## Stack

| Component | Technology |
|---|---|
| Backend | Python 3.13 + aiohttp |
| AI | Claude API (claude-sonnet-4-6), tool use / agentic loop |
| Frontend | Modern JS (no iOS 12 constraint) |
| HA integration | Supervisor Ingress, `SUPERVISOR_TOKEN` env var |
| Config | HA add-on options (`config.yaml`) |
| Port | 8099 (internal only, via Ingress) |

---

## Architecture (current — see `docs/architecture.md` for full detail)

> The "Two-Layer Architecture" this section used to describe (Layer 2 =
> Claude agentic loop, Layer 1 = a 100%-offline, no-AI Python flow engine)
> is retired along with the rest of the Sprint A/B autonomous-agent
> machinery (Slice 5, v0.33.0). There is no AI-free automation path anymore:
> every Agentbot trigger wakes an LLM reasoner (verdict-JSON, gated by the
> semaforo before any action executes) — see "The current model" above.

```
┌──────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                           │
│  Static HTML/JS frontend (chat UI, Chatbot/Agentbot designer)│
│  Lovelace custom card (hiris-chat-card)                      │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  APPLICATION LAYER                                            │
│  aiohttp REST API · Chatbot Engine · LLM Router               │
│  Tool Dispatcher · Task Engine · Semantic Map                 │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE LAYER                                         │
│  HA WebSocket client · SQLite · MQTT publisher                │
│  Anthropic SDK · OpenAI SDK · Ollama HTTP client               │
└──────────────────────────────────────────────────────────────┘
```

---

## Claude Tools (Phase 1 baseline — non-exhaustive)

Core tool set from Phase 1, still valid. Many more tools have shipped since (memory/RAG, knowledge, proposals, HTTP, health, automation-config, dashboard authoring — see `hiris/app/tools/*.py` for the authoritative, current list; `EVALUATION_ONLY_TOOLS` in `hiris/app/claude_runner.py` marks which are Agentbot-safe).

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
| `send_notification(message, channel)` | HA push / Telegram / Apprise (80+ channels) |
| `get_ha_automations()` | HA REST `/api/config/automation` |
| `trigger_automation(id)` | HA `automation.trigger` |
| `toggle_automation(id, enabled)` | HA `automation.turn_on/off` |
| `get_calendar_events(hours, calendar_entity)` | HA calendar integration |
| `set_input_helper(entity_id, value)` | input_boolean/number/text/select |
| `create_task(...)` / `list_tasks()` / `cancel_task(id)` | Internal task management |

---

## The current model — three AI entities

*(supersedes the old "4 Agent Types" table — Proactive Monitor / Reactive Agent / Preventive Scheduler / Chat NL Agent — retired in Slice 5, v0.33.0; see the Roadmap history below for context, not as current fact)*

| Entity | Role | Trigger | Reasoning | Action |
|---|---|---|---|---|
| **Chatbot** | Conversa: chiedi → risponde | User message (UI/Lovelace card) | Free-form prompt, tool use within its allowlist | Gated by the semaforo — **no autonomous trigger** |
| **Agentbot** | Vigila: watches for a condition | Event / cron / interval (built-in Sentinella detectors **or** user-defined) | Single-shot LLM reasoner, **verdict-JSON contract, no free tool use** | Action **declared in config**, never chosen by the AI at runtime — gated by the semaforo |
| **Brain** | Il fulcro: observes, reasons, proposes | Continuous (cognitive loop) | Cross-entity reasoning over knowledge/history | Surfaces proposals/advisories; home at `#/` |

Storage: `chatbots.json`, `agentbots.json` (both under `/data`). DB: `knowledge.db` (per-Chatbot scoping via `chatbot_id` column), `advisory.db`, `chat_history.db`, `proposals.db`; the Brain's reasoning log lives in a `brain_reasoning` table.

API surface: `/api/chatbots*`, `/api/agentbots*`, `/api/chat`, `/api/brain/*`, `/api/models*`, `/api/sentinel/*`, `/api/entities`, `/api/proposals*`.

Frontend: no build step — `<script src>` tags with a per-file fingerprint appended server-side. Key modules: `hiris/app/static/config/entity-picker.js`, `editor-kit.js`, `chatbot-editor.js`, `agentbot-editor.js`, `create-wizard.js`; chat UI in `hiris/app/static/chat/*.js`.

Security: the **semaforo** (`hiris/app/security/semaphore.py`) is the single gate for every action toward the house — tier (green/yellow/red/off) per domain/entity + denylist of dangerous domains + step-up — enforced from every surface (chat, agentbots, gateway, deferred tasks). Reads never go through it.

Full narrative: `docs/how-it-works.md` ("Chatbot and Agentbot", "The Brain Home"), `docs/architecture.md`.

---

## Project Structure

> The two trees below are Phase 0/1 scaffold planning (pre-implementation) and
> are stale as a file listing — `app/routes.py`, top-level `app/ha_client.py`,
> `app/agent_engine.py`, `api/handlers_agents.py` and
> `docs/2026-04-18-hiris-design.md` do **not** exist. Kept only for roadmap
> history below; do not `cd`/`Read` these paths expecting them to exist.

**Current structure** (verify with `ls hiris/app/` — this list drifts as the app grows):
```
hiris/                    # add-on root: config.yaml, Dockerfile, run.sh, requirements.txt
└── app/
    ├── main.py           # aiohttp app factory + web.run_app
    ├── server.py         # route registration (app.router.add_*) — routes live HERE, not routes.py
    ├── claude_runner.py  # Claude API agentic loop + tool orchestrator (MODEL default, AUTO_MODEL_MAP)
    ├── chatbot_engine.py
    ├── llm_router.py     # provider order (cost_first/quality_first)
    ├── model_activation.py
    ├── storage.py
    ├── chat_store.py     # chat_history.db
    ├── config.py / env_util.py / version.py / mqtt_publisher.py / task_engine.py
    ├── agent/            # runner.py, prompts.py (Chatbot agentic-loop internals)
    ├── watcher/           # Sentinella: detectors/situations, agentbots.py, evaluator.py, executor.py
    ├── brain/             # cognitive_loop.py, advisory_store.py, knowledge_store.py, reasoning_log.py
    ├── security/          # semaphore.py — the semaforo gate
    ├── api/                # handlers_chatbots.py, handlers_agentbots.py, handlers_brain.py, handlers_models.py, ...
    ├── tools/              # ha_tools.py, calendar_tools.py, memory_tools.py, dispatcher.py, ...
    ├── proxy/              # ha_client.py (real HA REST/WS client — NOT app/ha_client.py)
    ├── mcp/, history/, reasoning/
    └── static/
        ├── index.html / config.html
        ├── chat/           # agents.js, main.js, messages.js, sidebar.js, ...
        └── config/         # entity-picker.js, editor-kit.js, chatbot-editor.js, agentbot-editor.js, create-wizard.js, ...
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
Full detail was in `docs/HIRIS_CLAUDE_CODE_PROMPT.md` — **that file no longer exists**; treat the Roadmap entries below as the record.

#### Sprint 0 — Critical Bugfixes ✅ done (v0.6.0)
- `handlers_agents.py` + `handlers_usage.py` — `get("llm_router") or get("claude_runner")` fix
- `app/ha_client.py` — orphan stub removed; real impl is `proxy/ha_client.py`
- `SemanticContextMap` — JSON persist/load so classifications survive restart
- EUR exchange rate — centralized into `config.EUR_RATE` constant
- MQTT: `update_agent()` now calls `publish_agent_state()` on `enabled` change
- Non-blocking file I/O — `_save()` / `_save_usage()` / `SemanticContextMap.save()` use `run_in_executor`

#### Sprint A — HA-Bridge ✅ done (v0.6.1)
*Competenza: Python backend + HA WebSocket/MQTT*
- MQTT 2-way: subscribe `hiris/agents/+/{enabled,run_now}/set`; `AgentEngine._handle_mqtt_command` callback — **retired in Slice 5 (v0.33.0)**: no autonomous scheduler/executor is left to enable or trigger remotely; the command subscribe loop and `_handle_mqtt_command` are gone, `enabled` is now a read-only `sensor`, and the `run_now` button was removed (see `docs/mqtt-integration.md`)
- New MQTT entities: `last_result`, `budget_remaining_eur` ("unlimited" when no limit), `tokens_used_today` (daily lazy reset), `run_now` button — `run_now` button retired along with the item above; `budget_remaining_eur` is now *always* `"unlimited"` (no per-agent budget cap exists anymore, see Slice 5 note below)
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

> **Retired in Slice 5 — Lenti + Personas (v0.33.0):** the whole autonomous-agent
> machinery from this sprint — `action_mode`/`rules`/`states`, `Agent.trigger_on`,
> `AgentEngine._execute_agent_actions()` (and `_execute_action_chain`/
> `_parse_azioni_lines` added later), `on_fail`, the `VALUTAZIONE`/`AZIONI`
> structured-output convention, per-agent `budget_eur_limit` auto-disable, and the
> corresponding config.html trigger/action-sequence UI — has been deleted, not
> deprecated.
>
> **Current model (superseded the Slice-5 "Personas" naming too):** chat is
> configured via a **Chatbot** (prompt, tool/entity/service scope, memory
> scope, chat policy — "Personas" was an interim name, no longer used). The
> proactive layer is the **Sentinella** (`hiris/app/watcher/`): fixed, tunable
> built-in detectors/situations ("lenti") **plus user-defined Agentbot**
> (`/api/agentbots`, persisted in `agentbots.json`) — custom triggers/prompts
> have shipped, this is not a future-version item. See `docs/how-it-works.md`
> ("Chatbot and Agentbot") and `docs/architecture.md` ("Sentinella execution
> lifecycle").

#### Sprint C — Memory-RAG ✅ done (v0.7.x)
*Competenza: SQLite + embeddings + AI context*
- `HISTORY_RETENTION_DAYS` configurable via env (0=unlimited, default 90d) + `delete_old_messages()` DELETE job
- `backends/embeddings.py`: `EmbeddingProvider` Protocol + `OpenAIEmbedder` (httpx) + `OllamaEmbedder` (aiohttp) + `NullEmbedder`
- `proxy/memory_store.py`: `agent_memories` SQLite table, pure-Python cosine similarity (no sqlite-vec — Alpine compat), async save/search
- Tools: `recall_memory(query, k, tags)` + `save_memory(content, tags)` — `recall_memory` in `EVALUATION_ONLY_TOOLS`; `save_memory` chat-only (security)
- RAG pre-injection: top-k memories prepended to `context_str` in `handlers_chat.py` before every `runner.chat()`
- Config: `openai_api_key`, `memory_embedding_provider` (openai|ollama|""), `memory_embedding_model`, `memory_rag_k`, `memory_retention_days`, `history_retention_days`
- Daily APScheduler retention job at 03:00 UTC: purge old chat messages + expired memories

#### Sprint D — Multi-provider LLM (v0.7.x)
*Competenza: LLM abstraction layer — requires ADR-0002 first*
- LiteLLM integration in `backends/` (or custom shim — ADR decides)
- Advanced LLM Router: strategy `cost_first`/`quality_first`, fallback chain, `task_routing` per agent type
- `pricing.yaml`: centralized EUR/1M token cost map per model

> **What actually shipped (superseded the plan above):** no `task_routing`
> concept exists. Model selection is `hiris/app/llm_router.py`
> (`cost_first`/`quality_first` provider order) + a persisted `chain_order`
> (`/api/models/config`, edited at `#/models`) used as the fallback chain
> when a Chatbot or Agentbot has `model="auto"`. Each Chatbot/Agentbot picks
> its own model directly in its editor (not "per type"). `pricing.yaml` did
> not materialize as a file — costs live in `hiris/app/backends/pricing.py`
> (`PRICING` dict).

#### Sprint E — Lovelace + HACS (v0.8.x)
*Competenza: Web Components + distribution*
- `hiris-agent-card`: agent status, budget bar, run button, last output (reuses `hiris-chat-card` patterns)
- HACS packaging (`hacs.json`, `repository.json`)
- Blueprint YAML starter pack (morning briefing, energy anomaly, door reactive)

### Phase 3 — Canvas (v0.9.x+)
- Canvas drag-and-drop designer (n8n style)
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
- Every action toward HA is gated by the **semaforo** (`hiris/app/security/semaphore.py`) — tier per domain/entity + dangerous-domain denylist + step-up — not a flat per-agent whitelist. See "The current model" above.
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
