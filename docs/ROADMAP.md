# HIRIS — Roadmap

> Ultimo aggiornamento: 2026-04-25 | Versione corrente: **v0.5.0** | Ultimo aggiornamento roadmap: 2026-04-25
>
> Questo file è il **single source of truth** della roadmap. Il vecchio `docs/2026-04-18-hiris-design.md` §11 e `docs/HIRIS_CLAUDE_CODE_PROMPT.md` sono da considerare superseded da questo documento.

---

## Stato attuale — v0.5.0 ✅

### Backend
- aiohttp server + 23 API endpoints
- HAClient: REST, WebSocket, History, Calendar
- ClaudeRunner: 17 tool, retry 429/529, prompt caching 3 layer, token tracking, `chat_stream()` SSE
- AgentEngine: 4 tipi agent (chat/monitor/reactive/preventive), 4 trigger types, cron APScheduler, MQTT hooks
- TaskEngine: task deferred (delay/at_time/at_datetime/time_window)
- LLMRouter: Claude primario + Ollama-compatible locale
- ChatStore: SQLite history per agent, session gap 2h, riassunti, `count_user_turns`
- SemanticContextMap + KnowledgeDB: context injection area-aware
- SemanticMap: classificazione entità via LLM
- **MQTTPublisher**: pubblica stato agenti come entità HA native (Discovery), reconnect backoff
- **X-HIRIS-Internal-Token**: middleware auth inter-addon per chiamate non-Ingress

### Tool Claude (17)
`get_entity_states`, `get_area_entities`, `get_home_status`, `get_entities_on`, `get_entities_by_domain`, `get_energy_history`, `get_weather_forecast`, `call_ha_service`, `send_notification`, `get_ha_automations`, `trigger_automation`, `toggle_automation`, `create_task`, `list_tasks`, `cancel_task`, `get_calendar_events`, `set_input_helper`

### Frontend
- Chat UI (index.html): agenti, chat, tool log, task panel, onboarding wizard
- Config UI (config.html): designer agenti, token counter live, context preview, templates
- **hiris-chat-card**: HA Lovelace custom card (vanilla JS, shadow DOM, SSE streaming, polling fase 1, MQTT fase 2)

### Sicurezza
`allowed_tools`, `allowed_entities`, `allowed_services`, `restrict_to_home`, `require_confirmation`, budget auto-disable, entity_id validation, security headers, inter-addon token auth

### Test
337 test, 22 moduli

---

## Roadmap

### v0.5 — Integrazione HA nativa 🏠 ✅ (parziale)

Rende HIRIS percepito come componente nativo di HA. Prerequisito per HACS distribution.

| Feature | Descrizione | Stato |
|---|---|---|
| **MQTT bridge** ✅ | Pubblica stato agenti come entità HA via MQTT Discovery: `sensor.hiris_<id>_status`, `_last_run`, `_budget_eur`, `switch.hiris_<id>_enabled`. Reconnect con backoff esponenziale. Config opzionale — se assente HIRIS funziona uguale. | **Fatto** (v0.5.0) |
| **Lovelace chat card** ✅ | `hiris-chat-card` vanilla JS, shadow DOM, SSE streaming, polling fase 1, MQTT auto-detect fase 2, toggle enable/disable, budget bar. | **Fatto** (v0.5.0) |
| **SSE streaming** ✅ | `/api/chat` supporta `stream: true` + `Accept: text/event-stream`. `chat_stream()` in ClaudeRunner. | **Fatto** (v0.5.0) |
| **Inter-addon auth** ✅ | Middleware `X-HIRIS-Internal-Token` per chiamate non-Ingress (Retro Panel, etc.). | **Fatto** (v0.5.0) |
| **HA Services** | Registra `hiris.run_agent`, `hiris.chat`, `hiris.enable_agent` come comandi HA. | Da fare (v0.5.x) |
| **Blueprints** | 3-4 blueprint pronti: morning briefing, energy anomaly, door reactive. | Da fare (v0.5.x) |
| **CI/CD GitHub** | `.github/workflows/ci.yml`: lint (ruff), typecheck (mypy), pytest, build Docker. | Da fare (v0.5.x) |

---

### v0.6 — Multi-provider LLM 🔌 (rimuove vendor lock-in)

| Feature | Descrizione | Note |
|---|---|---|
| **LiteLLM adapter** | Sostituisce chiamate dirette Anthropic SDK con LiteLLM: supporta OpenAI, Gemini, Ollama, Groq, OpenRouter, ecc. Claude rimane default. | ADR richiesto: LiteLLM vs shim custom. Attenzione weight (~100MB), prompt caching cross-provider. |
| **Tool use cross-provider** | Verifica compatibilità 17 tool con OpenAI e Gemini schema. Test matrix. | Da fare dopo LiteLLM. |
| **Router avanzato** | Config `strategy: cost_first | quality_first | latency_first`. Fallback chain configurabile. Task routing: classify→haiku, chat→sonnet, summarize→haiku. | Estende LLMRouter esistente. |

**Criteri done:** Claude, OpenAI GPT-4o e Ollama testati con tutti i tool, costo tracking cross-provider, fallback chain funzionante.

---

### v0.7 — Memoria vettoriale 🧠 (conversazioni continue)

| Feature | Descrizione | Note |
|---|---|---|
| **sqlite-vec memory** | DB embeddings in `hiris.db`: tabelle `memories`, `anomalies`. Tool `recall_memory(query, k)` e `save_memory(content, tags)`. Similarity search < 50ms su 10k entry. Pruning automatico memorie vecchie. | ADR richiesto: sqlite-vec vs chromadb vs txtai. Verifica ARM64 stability. |
| **Embedding provider** | Default: `openai/text-embedding-3-small` ($0.02/1M tok ≈ $0.001/mese). Alternativa locale: `ollama/nomic-embed-text`. | Config option `embedding_provider`. |

**Criteri done:** `recall_memory` + `save_memory` tool, decay automatico, Ollama embedding come alternativa locale.

---

### v0.8 — Automazione intelligente 🤖 (capacità agent avanzata)

| Feature | Descrizione | Note |
|---|---|---|
| **Proposal automazioni** | Tool `propose_automation(yaml, rationale)`: proposta va in review queue. Approvazione via notifica mobile HA con action button Approve/Reject. Scrittura YAML con backup pre-apply. | `config_rw: true` nel manifest addon. Rollback disponibile via UI. |
| **Anomaly baseline** | Job ogni 15min: rolling stats (mean, stddev) per entità numeriche su finestre 1h/24h/7d in SQLite. Trigger finding se deviation > N×stddev. Triage LLM opzionale (opt-in) via Haiku. | Ispirato a goruck Sentinel, scope più ristretto (no LLM discovery nuove regole). |
| **Dashboard generator** | Tool `generate_dashboard(description)` → YAML Lovelace via `POST /api/lovelace/config`. Preview text in chat + confirm prima di applicare. Revert disponibile. | API Lovelace storage mode. Validation entità pre-apply. |

---

### v1.0 — Canali + Release pubblica 🚀

| Feature | Descrizione | Note |
|---|---|---|
| **Telegram bot nativo** | Long polling, no IP pubblico. Allowlist `telegram_allowed_user_ids`. Comandi `/agent`, `/status`, `/history`. Routing user→agent. Stream risposta via edit message. | Skip WhatsApp (compliance). `python-telegram-bot` asyncio. |
| **Lovelace cards** | `hiris-agent-card`: status badge, budget bar, run button. `hiris-chat-card`: chat inline in dashboard Lovelace. Stack: Lit 3, bundle < 50KB. | Distribuzione come plugin HACS separato o path `lovelace/` in repo. |
| **HACS distribution** | `hacs.json` corretto, repository.json, release notes strutturate, topic GitHub. | Prerequisito: CI verde su main 30gg, zero bug critical, 20+ beta users. |
| **Docs rinnovati** | README storytelling (perché HIRIS esiste, philosophy, confronto onesto con competitor), ARCHITECTURE.md, COST_GUIDE.md, USE_CASES.md in italiano, COMPARISON.md. Logo SVG, screenshot dark+light, video demo 90s. | Non blocca v1.0 ma va fatto in parallelo. |

---

## ADR da scrivere prima di implementare

| ID | Decisione | Blocca |
|---|---|---|
| ADR-001 | MQTT library: `aiomqtt` vs `paho-mqtt` | v0.5 MQTT bridge |
| ADR-002 | Multi-provider: LiteLLM vs shim custom | v0.6 |
| ADR-003 | Vector store: sqlite-vec vs chromadb vs txtai (ARM64 stability) | v0.7 |
| ADR-004 | Embedding provider default: cloud vs local-first | v0.7 |
| ADR-005 | Lovelace cards: mono-repo vs repo separato HACS | v1.0 |
| ADR-006 | Licensing: MIT puro vs dual-license per parti premium | Pre v1.0 |

---

## Priority stack (cosa fare dopo)

1. **v0.5 CI/CD** — GitHub Actions (lint, test, build Docker) → prerequisito qualsiasi rilascio pubblico
2. **v0.5 HA Services** — `hiris.run_agent`, `hiris.chat`, `hiris.enable_agent` → automazioni HA native
3. **v0.5 Blueprints** — morning briefing, energy anomaly, door reactive
4. **v0.6** — multi-provider LLM → rimuove dipendenza Anthropic-only
5. **v0.7/v0.8/v1.0** — memoria vettoriale, automazione intelligente, distribuzione

---

## Feature da valutare — fuori scope attuale

Queste feature sono state valutate e rinviate. Non hanno una versione assegnata. Da rivalutare solo dopo v0.7+, sulla base di reale domanda utente.

| Feature | Motivo del rinvio | Condizione di rivalutazione |
|---|---|---|
| `send_email(to, subject, body)` | Sostituibile con notifica HA push/Telegram già esistente. Aggiunge dipendenza SMTP e configurazione utente. | Se emerge domanda esplicita da utenti beta post-v1.0 |
| `http_request(url, method, headers, body)` | Apre superficie di attacco ampia (SSRF). Richiederebbe `allowed_urls` per agente e sandboxing. Complessità di sicurezza non giustificata ora. | Se MQTT bridge non copre casi d'uso custom; rivalutare con whitelist statica |
| `analyze_image(source)` | **Out of scope** per privacy (snapshot telecamere), costo token Claude vision, complessità gestione media HA. Nessun caso d'uso primario identificato. | Non pianificato. Richiederebbe ADR dedicato e consenso esplicito. |

---

## Definition of Done — v1.0

- [ ] CI verde su master per 30 giorni consecutivi
- [ ] HACS distribution funzionante
- [ ] MQTT bridge + HA services registrati
- [ ] Multi-provider (Claude + OpenAI + Ollama) testati
- [ ] README + docs rinnovati con video demo
- [ ] 20+ utenti beta attivi (GitHub stars + Issues feedback)
- [ ] Zero bug critical aperti
- [ ] Cost guide verificata da 3 utenti reali
- [ ] Coverage ≥70% su tutti i moduli
