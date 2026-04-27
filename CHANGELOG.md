# HIRIS — Changelog

## [0.5.7] — 2026-04-27

### Fixed
- `_deploy_card_to_www()` ora prova sia `/config` che `/homeassistant` per trovare la directory di configurazione HA (il Supervisor monta il volume `config:rw` su `/config` nelle versioni correnti, non su `/homeassistant`); la funzione usa il percorso che contiene effettivamente `configuration.yaml` o `.storage`
- Aggiunta funzione `_find_ha_config_dir()` che individua il percorso corretto in modo robusto tra le versioni di Supervisor

## [0.5.6] — 2026-04-26

### Fixed
- `map: homeassistant:rw` replaced with `map: config:rw` — `homeassistant` is not a recognized HA Supervisor volume key and was silently ignored, leaving `/homeassistant` unmounted inside the container; the card copy appeared to succeed but wrote to the ephemeral container filesystem instead of the HA host, so `/local/hiris/hiris-chat-card.js` always returned 404
- `_deploy_card_to_www()` now verifies the HA config volume is actually mounted (checks for `configuration.yaml` or `.storage` at `/homeassistant`) before copying; logs a clear ERROR with actionable instructions if not, instead of silently "succeeding" with no visible failure

## [0.5.5] — 2026-04-26

### Fixed
- `setConfig` lancia eccezione su config null (contratto HA), resetta messaggi/polling al cambio agente
- Token SSE in `_sendMessage` usa `auth.accessToken` (HA 2024+) con fallback a `data.access_token`
- Rimossa costante `EUR_RATE` inutilizzata

## [0.5.4] — 2026-04-26

### Fixed
- Aggiunto `getCardSize()` → HA alloca la griglia correttamente senza mostrare shimmer di caricamento permanente
- `preview: false` nel registro `window.customCards` → il picker non tenta un render live (che richiede HIRIS attivo)
- `_fetchStatus()` usa `_patchStatus()` invece di `_render()` quando il DOM è già inizializzato → preserva il testo digitato nella chat
- `set hass()` usa `_patchStatus()` per aggiornamenti MQTT → nessuna sostituzione DOM su ogni cambio entity

## [0.5.3] — 2026-04-26

### Fixed
- Lovelace card JS ora servita via `/local/hiris/hiris-chat-card.js` invece dell'URL ingress (che richiedeva auth e restituiva 401 al browser)
- Aggiunto `map: homeassistant:rw` in `config.yaml` per consentire la copia del JS in `/homeassistant/www/hiris/` all'avvio
- Migrazione automatica: l'URL ingress stale viene eliminata da Lovelace resources e sostituita con quella `/local/`

## [0.5.2] — 2026-04-26

### Added
- Lovelace card picker: registrazione custom card, visual editor e stato "unconfigured"
- Lovelace card picker integration completa (v0.6.0 feature set)

### Fixed
- Code review findings post-picker integration

## [0.5.1] — 2026-04-25

### Added
- **Lovelace card auto-registration** — on startup HIRIS calls `POST /api/lovelace/resources` (via Supervisor token) to register `hiris-chat-card.js` as a UI module; idempotent, graceful in YAML-mode HA
- **Single-source versioning** — version read dynamically from `config.yaml` at runtime; `server.py` and `handlers_status.py` no longer hardcode it
- **Release script** — `scripts/release.py`: 10-step mechanical release executor (semver validation → changelog check → tests → git tag → GitHub Release); supports `--dry-run` and `--skip-tests`

## [0.5.0] — 2026-04-25

### Added
- **X-HIRIS-Internal-Token middleware** — HMAC-validated auth for inter-add-on requests (non-Ingress)
- **Enriched `/api/agents` response** — includes `status`, `budget_eur`, `budget_limit_eur` for Lovelace dashboard
- **SSE streaming for `/api/chat`** — Server-Sent Events path when `stream: true` or `Accept: text/event-stream`; Phase 1 pseudo-streaming (full response sliced into 80-char tokens)
- **`hiris-chat-card.js`** — vanilla JS Lovelace custom card (shadow DOM, 30s polling, SSE streaming, budget bar, toggle enable/disable)
- **MQTT Discovery publisher** — publishes `sensor.hiris_*_status/budget_eur/last_run` and `switch.hiris_*_enabled` via aiomqtt; exponential backoff reconnect; discovery messages queue during initial backoff

### Changed
- `config.yaml`: added `internal_token`, `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` options
- `AgentEngine`: tracks running/error agent status; publishes MQTT state on each run

## [0.4.2] — 2026-04-24

### Fixed
- `internal_token` option uses `password` schema in `config.yaml` (masked in HA UI)
- HMAC comparison uses `hmac.compare_digest` (constant-time, prevents timing attacks)

## [0.4.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex; organizes entities by area using `device_class` + domain classification; ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations
- **TaskEngine** — shared deferred-task system; 4 trigger types (`delay`, `at_time`, `at_datetime`, `time_window`); 3 action types; task persistence in `/data/tasks.json`
- **LLM Router** — routes standard inference to Claude, offloads `classify_entities()` to local Ollama when `LOCAL_MODEL_URL` configured
- **Task UI** — "Task" tab with pending-count badge; active + recent task list; cancel button; auto-refresh every 30s

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.3.0] — 2026-04-23

### Added
- **SemanticContextMap** — replaces EmbeddingIndex RAG and SemanticMap snippet; organizes all HA entities by area using native `device_class` + domain classification
- **ENTITY_TYPE_SCHEMA** — maps (domain, device_class) → (entity_type, label_it) for 30+ entity types, based on HA documentation
- **ContextSelector** — keyword-based query: extracts area + concept→type matches from user message, injects only relevant sections
- **Two-tier prompt injection** — compact home overview always present (~80 token); area/type detail expanded on match (~150 token); ~60% token reduction vs previous RAG
- **KnowledgeDB** — SQLite persistence for entity classifications, agent annotations, entity correlations, query patterns
- **Unified permission boundary** — `visible_entity_ids` from `SemanticContextMap.get_context()` used to validate all entity tool calls; consistent `allowed_entities` enforcement
- **EntityCache enriched** — `domain`, `device_class`, and typed attributes (hvac_mode, brightness, current_position, etc.) stored per entity for all domains

### Removed
- `EmbeddingIndex` — replaced by `SemanticContextMap` + `ContextSelector`
- `SemanticMap.get_prompt_snippet()` — replaced by `SemanticContextMap._format_overview()` + `_format_detail()`
- `search_entities` Claude tool — removed with EmbeddingIndex dependency

## [0.2.3] — 2026-04-22

### Added
- **TaskEngine** — shared deferred-task system available to all agent types (chat, monitor, reactive, preventive)
- **4 trigger types** — `delay` (minutes from now), `at_time` (wall-clock HH:MM local time), `at_datetime` (ISO datetime), `time_window` (poll every N min within a HH:MM–HH:MM window)
- **Optional condition** — entity state check at trigger time with operators `<`, `<=`, `>`, `>=`, `=`, `!=`; task skipped (not failed) if condition unmet
- **3 action types** — `call_ha_service`, `send_notification`, `create_task` (chaining: child task inherits `agent_id`, sets `parent_task_id`)
- **Task persistence** — tasks saved to `/data/tasks.json` with atomic write; pending tasks rescheduled on restart
- **Automatic cleanup** — terminal tasks (done/skipped/failed/expired/cancelled) deleted after 24h via hourly APScheduler job
- **3 Claude tools** — `create_task`, `list_tasks`, `cancel_task` available in `allowed_tools` per agent
- **REST API** — `GET /api/tasks`, `GET /api/tasks/{id}`, `DELETE /api/tasks/{id}`
- **Task UI** — "Task" tab in sidebar with pending-count badge; active task list + recent (24h) list; Annulla button for pending tasks; auto-refresh every 30s
- **Python 3.13** — upgraded base image from `3.11-alpine3.18` to `3.13-alpine3.21`

### Fixed
- `at_datetime` trigger called removed `_run_task_async` method — changed to `_execute_task`
- `_check_time_window` stored naive local timestamp in `executed_at` — now UTC-aware
- `create_task` tool dispatch now enforces agent's `allowed_services` whitelist on all `call_ha_service` actions before scheduling (previously bypassable via deferred tasks)
- Task UI: `label`, `result`, `error`, `status`, and `id` fields now HTML-escaped before injection into innerHTML (XSS prevention)
- `EntityCache`: added `get_state(entity_id)` method required by `TaskEngine` condition evaluation

## [0.2.2] — 2026-04-22

### Fixed
- `get_weather_forecast`: cast `hours` parameter to `int` to handle Claude passing it as string
- `get_energy_history`: cast `days` parameter to `int` for the same reason

## [0.2.1] — 2026-04-22

### Fixed
- `EntityCache.get_state()` method missing — caused `AttributeError` in `SemanticMap.get_prompt_snippet()` on production

## [0.2.0] — 2026-04-22

### Added
- **Semantic Home Map** — automatic rule-based + LLM-assisted classification of all HA entities into semantic roles (energy_meter, solar_production, climate_sensor, lighting, appliance, presence, door_window, etc.)
- **LLM Router** — thin routing layer that forwards standard inference to Claude and offloads `classify_entities()` to a local Ollama model when `LOCAL_MODEL_URL` is configured
- **LLM Backend abstraction** — `LLMBackend` ABC with `ClaudeBackend` and `OllamaBackend` implementations
- **Semantic prompt snippet** — structured home context injected into every Claude call (energy, climate, lights summary with live state)
- **SemanticMap persistence** — classification saved to disk and reloaded on startup; LLM re-classifies only unknown entities
- **HAClient entity registry listener** — SemanticMap updates automatically when new entities are added to HA
- **`get_home_status` enriched** — returns semantic labels from SemanticMap instead of raw entity IDs
- **Energy tools read SemanticMap** — `get_energy_history` resolves entity IDs from SemanticMap; no manual configuration needed
- **Config options** — `primary_model`, `local_model_url`, `local_model_name` in `config.yaml`
- **SSRF protection** — `OllamaBackend` validates URL and blocks cloud metadata endpoints (169.254.169.254, etc.)

### Security
- **CVE-2024-52304** — upgraded `aiohttp` to `>=3.10.11` (HTTP request smuggling)
- **CVE-2024-42367** — same upgrade covers path traversal via static routes
- **Prompt injection sanitization** — control characters stripped from entity names, states, units, and action fields before injection into system prompt (`handlers_chat.py`, `semantic_map.py`)
- **asyncio race condition** — `SemanticMap._classify_unknown_batch()` protected with `asyncio.Lock`
- **JSON schema validation** — `LLMRouter._parse_classify_response()` validates role against allowlist, clamps confidence, truncates fields; truncates raw response to 100 KB before parse
- **WebSocket reconnect** — `HAClient._ws_loop` now reconnects automatically after any disconnect (10 s backoff); listener callback exceptions are isolated

---

## [0.1.9] — 2026-04-22

### Added
- **RAG pre-fetch** — before each Claude call, HIRIS tokenizes the user message, finds semantically related entities via `EmbeddingIndex` (keyword overlap), fetches their live states from `EntityCache`, and injects them into the system prompt under "Entità rilevanti"
- `EmbeddingIndex` — in-memory keyword index built from entity names and IDs; no ML dependency
- `EntityCache` — in-memory entity state cache updated in real time from HA WebSocket events

### Fixed
- Include climate entity temperatures in EntityCache
- Default agent system prompt updated with correct tool signatures

---

## [0.1.8] — 2026-04-22

### Fixed
- Mobile UI: `100dvh` viewport height, `font-size: 16px` (prevents iOS auto-zoom), 44px send button, `enterkeyhint: send` on message input, safe-area insets for notch/home-bar

---

## [0.1.7] — 2026-04-22

### Added
- **Per-agent usage tracking** — token counts (input/output) and estimated cost in USD tracked per agent and model; reset endpoint available
- **Budget auto-disable** — agent auto-disables when cumulative cost (USD × 0.92) reaches `budget_eur_limit`; logs reason
- **Global usage endpoint** — `GET /api/usage` returns total tokens and cost across all agents
- **Agent usage endpoints** — `GET /api/agents/{id}/usage`, `POST /api/agents/{id}/usage/reset`

### Fixed
- Count global request tokens once per `chat()` call, not once per tool iteration
- Truncate conversation history to last 30 messages sent to Claude API

---

## [0.1.6] — 2026-04-21

### Added
- **Chat persistence** — server-side conversation history stored per agent in `/data/chat_history_<agent_id>.json`
- **Max chat turns** — `max_chat_turns` field on agent; chat returns `{error: "max_turns_reached"}` when limit is hit
- **Chat history endpoints** — `GET /api/agents/{id}/chat-history`, `DELETE /api/agents/{id}/chat-history`
- **New conversation button** — UI clears client-side history and calls delete endpoint
- **Turn counter** — displayed in chat UI header
- **`icon.png`** — add-on icon for HA Supervisor store
- `script.*` added to allowed action domains in agent designer

### Fixed
- Notify channel value corrected from `ha` to `ha_push` in Action Builder
- `agent_id` sanitized in chat store path to prevent path traversal

---

## [0.1.5] — 2026-04-21

### Added
- **Action Builder** — visual step editor for agent actions in the Config UI; supports `call_ha_service`, `send_notification`, and `trigger_automation` actions
- **Per-agent entity chips** — quick entity selector in agent designer; entities filtered by `allowed_entities` patterns
- **`strategic_context`** field on agents — house/family context prepended to every Claude system prompt

### Fixed
- Agent designer improvements merged from feature branch
- Four issues from final branch review

---

## [0.1.4] — 2026-04-20

### Added
- **Chat NL UI** — full conversation interface at `/` with real-time assistant responses, sidebar for agent selection, message history display
- **Agents CRUD API** — `GET/POST /api/agents`, `GET/PUT/DELETE /api/agents/{id}`, `POST /api/agents/{id}/run`
- **Agent Designer UI** — step-based editor at `/config` for creating and editing agents
- **`require_confirmation` mode** — Claude must ask user before executing `call_ha_service`
- **`restrict_to_home` mode** — agent refuses off-topic questions
- **`allowed_entities` filter** — glob-pattern entity whitelist per agent
- **`allowed_services` filter** — glob-pattern service whitelist per agent
- **Default agent seed** — `hiris-default` chat agent created automatically on first startup
- **Execution log** — last 20 runs logged per agent with tokens, tool calls, result summary, `eval_status`, `action_taken`

---

## [0.1.3] — 2026-04-20

### Added
- **Claude agentic loop** — multi-turn tool use loop (max 10 iterations) with retry logic (429/529: 5s → 15s → 45s → error)
- **8 built-in tools**: `get_entity_states`, `get_area_entities`, `get_home_status`, `get_energy_history`, `get_weather_forecast`, `call_ha_service`, `send_notification`, `get_ha_automations`, `trigger_automation`, `toggle_automation`
- **Notify tools** — HA push, Telegram, Retro Panel toast
- **Automation tools** — list, trigger, toggle HA automations
- **Weather tools** — Open-Meteo forecast (no API key needed)
- **Energy tools** — HA History API integration
- **HA tools** — entity states and area grouping

### Fixed
- `AsyncAnthropic` client initialization
- Error handling in chat dispatch and tool calls
- Weather tools zip safety, unused imports

---

## [0.1.2] — 2026-04-19

### Added
- **AgentEngine** — APScheduler-based scheduler for `monitor` and `preventive` agents, WebSocket listener for `reactive` agents, CRUD persistence to `/data/agents.json`
- **Structured response parsing** — `VALUTAZIONE: [OK|ATTENZIONE|ANOMALIA]` and `AZIONE:` fields stripped from agent output and saved to execution log
- REST API handlers for chat, agent CRUD, and status endpoints
- Comprehensive API test coverage

### Fixed
- Cron expression parsing, `last_run` tracking, WebSocket startup, task error callbacks

---

## [0.1.1] — 2026-04-19

### Added
- **HA Client** — REST client for `/api/states`, `/api/services`, History API; WebSocket client for `state_changed` events with auto-reconnect
- Module restructure: `proxy/`, `tools/`, `api/` sub-packages

### Fixed
- HA client error logging, automations endpoint, async WebSocket startup

---

## [0.0.2] — 2026-04-18

### Added
- Restructured app into `proxy/tools/api` module layout
- Static file serving with 503 guard when UI not yet built

---

## [0.0.1] — 2026-04-18

### Added
- Phase 0 scaffold: HA add-on structure with `config.yaml` (ingress, `stage: experimental`)
- `Dockerfile` based on Python 3.11 HA base image
- `build.yaml`: HA Supervisor base-image declarations for `aarch64` and `amd64`
- `run.sh` entrypoint using bashio for configuration reading
- `aiohttp` server on port 8099
- `GET /` placeholder UI, `GET /api/health` → `{"status": "ok"}`
- `hacs.json`: HACS custom repository metadata
- MIT licence
