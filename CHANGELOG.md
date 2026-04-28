# HIRIS — Changelog

## [0.6.10] — 2026-04-28

### Fixed
- **`run.sh`**: `bashio::config --raw` is not a valid bashio flag and caused 12 jq compile errors on every startup; replaced with `jq -c '.apprise_urls // []' /data/options.json` which reads the array directly from the HA options file — Apprise URLs were being silently ignored before this fix

## [0.6.9] — 2026-04-28

### Fixed
- **Chat input (`index.html`)**: textarea now grows dynamically as you type without ever showing a scrollbar (`overflow-y: hidden`); height cap raised to 40% of viewport height instead of the fixed 8rem/128px limit

## [0.6.8] — 2026-04-28

### Added
- **fastembed embedding provider**: fully local RAG with no external server or API key required; uses ONNX Runtime (ARM64/amd64 compatible); models cached in `/config/hiris/models/`; default model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` supports 50+ languages including Italian
- `fastembed>=0.3.0` added to `requirements.txt`
- Configuration guide updated with Option C (fastembed) section; translations updated with fastembed in provider description

## [0.6.7] — 2026-04-28

### Added
- **Configuration guide** (`docs/configuration-guide.md` / `docs/guida-configurazione.md`): step-by-step setup for Apprise notifications (Telegram, ntfy, Gotify, email, Discord, WhatsApp) and Memory/RAG (OpenAI embeddings, Ollama local embeddings, tuning parameters)
- README: links to new configuration guide docs

## [0.6.6] — 2026-04-28

### Changed
- **Config restructure**: options now grouped into logical nested sections (`local_model`, `mqtt`, `memory`) instead of flat underscore-prefixed keys; HA UI renders each group as a collapsible section
- **`run.sh`**: updated all `bashio::config` calls to dotted path notation (`mqtt.host`, `local_model.model`, etc.); added missing `LLM_STRATEGY` export (was always defaulting to `balanced` regardless of config UI)
- **Translations**: added `hiris/translations/en.yaml` and `hiris/translations/it.yaml` with human-readable labels and descriptions for all 18 configuration options in both English and Italian

## [0.6.5] — 2026-04-28

### Fixed
- **Chat UI (`index.html`)**: added `_isLoading` flag — Enter key can no longer trigger a second request while a response is in progress; send button shows a CSS spinner during generation
- **Lovelace card**: text typed in the input field is now preserved across streaming re-renders (previously lost on every token); send button shows a spinner and `title="Elaborazione…"` while loading; input placeholder changes to "Elaborazione…" during generation

## [0.6.4] — 2026-04-28

### Fixed
- `ClaudeRunner.__init__()` crashed on startup due to spurious `entity_cache` and `semantic_map` kwargs passed from `server.py` (introduced in v0.6.3)

## [0.6.3] — 2026-04-28

### Added
- **LLMRouter strategy**: `strategy` param (`balanced` / `quality_first` / `cost_first`) controls backend preference order; wired via `LLM_STRATEGY` env var and `llm_strategy` config option
- **LLMRouter fallback**: when `model="auto"`, if the primary backend raises an exception the next backend in the strategy chain is tried automatically
- `backends/pricing.py`: centralized USD/MTok pricing table for all supported models (Claude 4.x, GPT-4o/4.1/o-series, Ollama free); replaces duplicate `_PRICING` dicts in `ClaudeRunner` and `OpenAICompatRunner`

## [0.6.2] — 2026-04-28

### Fixed
- **SSRF**: `http_tools` now blocks IPv4-mapped IPv6 addresses (`::ffff:127.x`) and always disables redirects (redirects bypassed `_PinnedResolver`)
- **Entity leakage**: `allowed_entities` filter now applied to `get_home_status`, `get_entities_on`, `get_entities_by_domain` (was only enforced on `get_entity_states`)
- **Prompt injection**: RAG memories marked as untrusted data in system context; `debug.tools_called` response redacted to tool names only
- **Path traversal**: `agent_id` validated with regex in chat history handler
- **Auth bypass**: middleware now denies non-ingress requests by default when no `internal_token` is configured
- `ClaudeRunner.run_with_actions` now includes action instructions in augmented prompt (was inconsistent with `OpenAICompatRunner`)
- `openai_compat_runner`: imports hoisted to module top (were dynamic per-call)
- `handlers_agents`: `_validate_agent_payload()` validates type/name/trigger/budget on create and update

### Removed
- Dead `entity_cache`/`semantic_map` params from `ClaudeRunner` (unreachable branch in production)
- Dead `set_notify_config()` / `_notify_config` from `AgentEngine` (written, never read)

## [0.6.1] — 2026-04-28

### Added
- **Sprint D — Multi-provider LLM**: supporto OpenAI e Ollama per-agente; `OpenAICompatRunner`
  con loop agentico completo (tool use, `run_with_actions`); `ToolDispatcher` condiviso tra tutti
  i runner; `LLMRouter` ridisegnato come router reale; endpoint `/api/models` con lista dinamica
  (fetch live da OpenAI, `/api/tags` per Ollama); dropdown modello con `<optgroup>` per provider;
  `_PRICING_OAI` per tracking costi OpenAI/Ollama
- **Sprint C — Memory-RAG**: tabella `agent_memories` in SQLite; tool `recall_memory` / `save_memory`;
  RAG pre-injection nelle chat; `EmbeddingProvider` Protocol + `OpenAIEmbedder` + `OllamaEmbedder`
  + `NullEmbedder`; job APScheduler retention 03:00 UTC; config: `memory_embedding_provider`,
  `memory_embedding_model`, `memory_rag_k`, `memory_retention_days`, `history_retention_days`
- **Sprint B — Tool Expansion**: tool `create_calendar_event`; layer Apprise (80+ canali via
  `apprise_urls`); `EVALUATION_ONLY_TOOLS` frozenset; `Agent.trigger_on` + `AgentEngine._execute_agent_actions`;
  `on_fail: continue|stop` per azione; `TaskEngine` trigger `immediate`; UI: trigger_on checkboxes,
  on_fail dropdown, editor azioni child (wait/verify)
- **Sprint A — HA-Bridge**: MQTT 2-way subscribe (`hiris/agents/+/{enabled,run_now}/set`);
  nuove entità MQTT `last_result`, `budget_remaining_eur`, `tokens_used_today`, `run_now`;
  tool `http_request` con security strutturata (AllowedEndpoint, DNS pinning, RFC1918 DENY_NETS);
  `Agent.allowed_endpoints`

### Fixed
- **Sprint 0 — Bugfixes critici**: `handlers_agents.py` / `handlers_usage.py` usa
  `get("llm_router") or get("claude_runner")`; stub `app/ha_client.py` rimosso; `SemanticContextMap`
  persist/load JSON su restart; `EUR_RATE` centralizzato in `config`; MQTT pubblica stato su
  cambio `enabled`
- I/O file non bloccante: `_save()`, `_save_usage()`, `SemanticContextMap.save()` via
  `run_in_executor`

## [0.5.16] — 2026-04-27

### Fixed
- Lovelace card: server writes `hiris-ingress.json` to `/local/hiris/` at startup so the card discovers the real Supervisor ingress URL — resolves all card 503 errors
- Lovelace card: chat streaming hang fixed — timeout now covers the entire stream lifecycle; `streaming` flag cleared when stream closes even without SSE `done` event
- Lovelace card: replaced blinking cursor with animated typing indicator (HIRIS icon + three bouncing dots) matching the add-on's direct chat UI
- Lovelace card: removed duplicate status indicator from header — only the enable/disable toggle button remains in the top-right
- Lovelace card: switched all API calls from `hass.callApi()` to `fetch()` with explicit Authorization header
- Lovelace card: SyntaxError and constructor render crash blocking the HA card picker
- Docker: `config.yaml` now copied into the container so `read_version()` returns the correct version string instead of "unknown"

## [0.5.15] — 2026-04-27

### Fixed
- La card Lovelace restituiva HTTP 503 per tutte le chiamate API anche con il add-on attivo: il Supervisor HA assegna ad ogni add-on un token casuale come percorso ingress (`/api/hassio_ingress/{token}/`) invece dello slug, quindi il vecchio URL hardcoded `/api/hassio_ingress/hiris/` non veniva riconosciuto da HA
- All'avvio HIRIS interroga il Supervisor (`/addons/self/info`) per ottenere il proprio `ingress_url` reale e lo scrive in `/homeassistant/www/hiris/hiris-ingress.json` (file statico pubblico, nessuna auth richiesta)
- La card legge questo file una volta prima della prima chiamata API e usa l'URL corretto per tutte le operazioni; se il file non è disponibile usa l'URL basato sullo slug come fallback
- `HirisChatCardEditor._loadAgents()` migrato da `hass.callApi()` a `fetch()` con auth esplicita (stesso motivo)

## [0.5.14] — 2026-04-27

### Fixed
- `_fetchStatus()` e `_toggleAgent()` ora usano `fetch()` con auth esplicita invece di `hass.callApi()`: quest'ultimo fallisce su alcuni HA/Supervisor con percorsi di ingress, mostrando "HIRIS non disponibile" anche quando il backend è raggiungibile
- Il messaggio di errore nel chat ora mostra la causa reale dal body JSON del backend (es. "Claude runner not configured — set CLAUDE_API_KEY") invece del generico "HTTP 503"
- Estratti i metodi helper `_hirisUrl(path)` e `_authToken()` per eliminare la duplicazione della logica di autenticazione

## [0.5.13] — 2026-04-27

### Fixed
- `config.yaml` ora viene copiato nel container Docker (`COPY config.yaml /usr/lib/hiris/config.yaml`): `read_version()` restituiva sempre `"unknown"` in produzione perché il file non era presente, rendendo l'URL della risorsa Lovelace sempre `/local/hiris/hiris-chat-card.js?v=unknown` e vanificando il cache-busting introdotto in v0.5.12

## [0.5.12] — 2026-04-27

### Fixed
- La risorsa Lovelace ora viene registrata come `/local/hiris/hiris-chat-card.js?v=VERSION` invece dell'URL senza versione: ad ogni aggiornamento dell'add-on il vecchio URL viene rimosso e quello nuovo creato, forzando il browser a ricaricare il JS aggiornato (cache-busting)
- Migrazione automatica da tre tipi di URL obsoleti: vecchio ingress URL, vecchio URL senza versione, vecchio URL con versione diversa

## [0.5.11] — 2026-04-27

### Fixed
- `set hass()` in `HirisCard` non guardava contro `hass` null/undefined — il card picker di HA istanzia gli elementi e chiama il setter prima di `setConfig`, causando `TypeError` che HA interpreta come "card rotta" e rimuove silenziosamente dal picker
- `set hass()` in `HirisChatCardEditor` idem — impediva il caricamento dell'editor di configurazione
- `_loadAgents()` ora verifica `this._hass` prima di chiamare `callApi`
- `_sendMessage()` ora esce anticipatamente se `this._hass` non è disponibile
- `parseFloat` sul budget ora usa `Number.isFinite` per evitare `NaN.toFixed(2)` in template
- `customElements.define()` ora guarda con `customElements.get()` prima di registrare: se il file viene caricato due volte (hot reload HA) la `define()` non lancia più `NotSupportedError` che bloccava la `window.customCards.push()` sottostante
- `window.customCards.push()` ora deduplica con `.find()`: nessuna doppia registrazione nel picker
- `titleInput.oninput` → `onchange` nell'editor: HA chiama `setConfig` → `_render()` → `innerHTML` ricreato ad ogni tasto, causando perdita del focus; con `onchange` il focus si perde solo al blur
- `getCardSize()` ora restituisce 2 in stato non configurato (era 6: riservava troppo spazio verticale)

## [0.5.10] — 2026-04-27

### Fixed
- `SyntaxError: Identifier 'msgs' has already been declared` in `hiris-chat-card.js`: variabile `msgs` dichiarata due volte nella stessa funzione `_render()`, impediva il parsing del file e rendeva la card completamente invisibile in HA
- Rimosso `this._render()` dai costruttori di `HirisCard` e `HirisChatCardEditor`: il card picker di HA istanzia gli elementi custom prima di connetterli al DOM, causando ricorsione Shadow DOM tramite i mutation observer di Lit (`Maximum call stack size exceeded`)
- Aggiunto `connectedCallback` a `HirisChatCardEditor` in modo che il primo render avvenga nel momento corretto del lifecycle

## [0.5.9] — 2026-04-27

### Fixed
- `get_area_registry()` e `get_entity_registry()` migrati da REST
  (`/api/config/*/list`, restituiva 404 via Supervisor) a WebSocket
  (`config/area_registry/list`, `config/entity_registry/list`);
  il tool Claude `get_area_entities` ora funziona e le aree/stanze
  sono disponibili come contesto per gli agenti

## [0.5.8] — 2026-04-27

### Added
- **Lovelace card picker** — `window.customCards` registration, visual editor
  (`hiris-chat-card-editor`), `getStubConfig` returning `hiris-default`; card
  now appears in the HA "Add Card" picker without manual YAML

### Fixed
- **Lovelace resource registration** — switched from REST API
  (`/api/lovelace/resources`, returned 404 in many HA setups) to WebSocket API
  (`lovelace/resources/create/delete`); works in all storage-mode configurations
- **Card JS deployment** — add-on copies `hiris-chat-card.js` to
  `<ha-config>/www/{slug}/` on startup so `/local/{slug}/hiris-chat-card.js`
  resolves without authentication; probes `/config` then `/homeassistant`
- **Stale ingress URL migration** — removes old `/api/hassio_ingress/` resource
  automatically and registers the new `/local/` URL in its place
- `config:rw` added to add-on map (`config.yaml`) — required for www deployment
- `getCardSize()` implemented; `preview: false` set to prevent HA from
  attempting live renders in the picker

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
