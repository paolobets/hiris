# Prompt per Claude Code — Roadmap HIRIS v0.3 → v1.0

Questo documento è il brief operativo per una sessione di lavoro agentico con Claude Code sul repository `paolobets/hiris`. Contiene contesto strategico, backlog tecnico dettagliato, decisioni architetturali da approfondire, policy di sicurezza del codice e piano di riposizionamento della documentazione GitHub.

---

## STATO CORRENTE (aggiornato 2026-04-28 — v0.6.1 → Sprint B completato)

### Completato rispetto alla roadmap originale

| Sezione doc | Feature | Versione |
|---|---|---|
| §2A.4 | `hiris-chat-card` Lovelace custom element + editor | v0.5.x |
| §2B.2 (parziale) | SQLite conversation history (`chat_store.py`) — sessioni, summary, retention 30d | v0.4.x |
| §2A.1 (parziale) | MQTT Discovery publisher (`mqtt_publisher.py`) — publish-only, discovery sensor/switch | v0.4.x |
| §2A: tools | `get_calendar_events` + `set_input_helper` già implementati (`calendar_tools.py`) | v0.4.x |
| §2A: tools | `send_notification` con canale telegram (token+chat_id da config) | v0.3.x |
| §2B.3 (parziale) | LLM Router base — routing classify_entities → Ollama | v0.3.x |
| §2A.1 | MQTT config in `config.yaml` (mqtt_host/port/user/password) | v0.4.x |

### Bug critici rilevati (audit codebase 2026-04-28) — **Sprint 0 obbligatorio**

Prima di qualsiasi feature sprint, i seguenti bug devono essere corretti:

| Priorità | File | Problema |
|---|---|---|
| **CRITICA** | `api/handlers_agents.py:137,161` | `get("claude_runner")` hardcoded → 503 su usage/reset con LLMRouter attivo |
| **CRITICA** | `api/handlers_usage.py` | Stesso bug → `/api/usage` restituisce 503 con LLMRouter |
| **ALTA** | `tools/task_tools.py` | Funzioni sync chiamate con `await` → `TypeError` a runtime |
| **ALTA** | `app/ha_client.py` | File stub orfano (nessun import) — duplica confusamente `proxy/ha_client.py` |
| **ALTA** | `proxy/semantic_context_map.py` | Zero persistenza tra restart (SemanticMap salva JSON, SemanticContextMap no) |
| **MEDIA** | 6 file | EUR rate `0.92` hardcoded in 6+ posti — deve essere costante centralizzata |
| **MEDIA** | `agent_engine.py:313-337` | `update_agent()` non chiama `publish_agent_state()` quando `enabled` cambia |

### Sprint Plan unificato (v0.6.x → v0.8.x)

| Sprint | Target | Competenza | Items chiave |
|---|---|---|---|
| **Sprint 0** ✅ | v0.6.0 | Bugfix | handler llm_router fix, task_tools await fix, ha_client stub rimosso, SemanticContextMap persist, EUR costante, MQTT enable publish, non-blocking I/O |
| **Sprint A** ✅ | v0.6.1 | HA Backend + MQTT | MQTT 2-way subscribe (enabled/run_now), nuove entità MQTT, `http_request` tool (Option C SSRF), `Agent.allowed_endpoints` |
| **Sprint B** ✅ | v0.6.x | External APIs + tools | `create_calendar_event`, Apprise unified layer (Telegram/WhatsApp/ntfy), action chaining agenti non-chat via TaskEngine, `EVALUATION_ONLY_TOOLS`, `trigger_on`, `on_fail`, UI editor wait/verify |
| **Sprint C** | v0.7.x | SQLite + embeddings | sqlite-vec, `recall_memory`/`save_memory`, RAG injection |
| **Sprint D** | v0.7.x | LLM abstraction | LiteLLM o shim, Router avanzato, `pricing.yaml` |
| **Sprint E** | v0.8.x | Frontend + distrib | `hiris-agent-card`, HACS, blueprints |

---

---

## 0. Contesto strategico (leggi prima di toccare codice)

HIRIS è un Home Assistant add-on che fornisce agenti AI powered by Claude per chat naturale, monitor proattivi, reactive events e preventive cron jobs. È in fase **experimental v0.2.2**, pubblicato senza stelle/fork, in una categoria di mercato **già affollata**.

**Competitor mappati** (da tenere presente per ogni decisione):

1. **goruck/home-generative-agent** — 195 stelle, integration (non addon), LangGraph, Sentinel anomaly detection, face recognition, PostgreSQL+pgvector, STT. È il riferimento tecnico più avanzato.
2. **Bobsilvio/ha-claude (Amira)** — 9 stelle, addon italiano, 23+ provider, Telegram/WhatsApp/Discord, HTML dashboards, vision, OAuth Copilot. È il competitor più simile strutturalmente.
3. **jekalmin/extended_openai_conversation** — storico, function calling.
4. **sbenodiz/ai_agent_ha** — multi-provider integration.
5. **valentinfrlch/ha-llmvision** — vision-specializzato.
6. **Integrazioni native HA** (Anthropic, OpenAI, Gemini, Ollama, AI Tasks da 2025.8).

**Posizionamento scelto per HIRIS:**
- *Agent framework strutturato per Home Assistant con controllo di costo*
- Vantaggi distintivi da preservare e amplificare: **4 tipi di agent come first-class citizens**, **budget EUR per-agent**, **auto-model selection per tipo**, **Semantic Home Map + RAG pre-fetch**, **Retro Panel integration** (complementare all'altro prodotto dell'autore).
- **Non** vendere come "il primo AI agent HA".
- **Non** inseguire tutte le feature dei concorrenti. Restare focalizzati.

**Feature esplicitamente escluse dalla roadmap:** face recognition dal flusso telecamere, WhatsApp (compliance Twilio), ricostruzione completa del Sentinel workflow di goruck, adozione totale di LangChain/LangGraph.

---

## 1. Regole di ingaggio per Claude Code

Prima di iniziare qualsiasi implementazione, Claude Code deve:

1. Leggere `CLAUDE.md` e `README.md` del repo per allinearsi sullo stato corrente.
2. Verificare la versione attuale in `CHANGELOG.md` e allineare il lavoro a una nuova branch `feat/phase-2a-<nome-feature>` per ogni blocco di lavoro.
3. Non introdurre dipendenze pesanti (LangChain completo, PostgreSQL obbligatorio, torch, modelli ML locali) senza prima produrre un ADR — Architecture Decision Record — in `docs/adr/NNNN-nome-decisione.md` e attendere approvazione umana.
4. Scrivere test per ogni nuovo modulo (`tests/`) e mantenere coverage ≥70% sui moduli toccati.
5. Aggiornare `CHANGELOG.md` seguendo Keep a Changelog e rispettare SemVer.
6. Usare Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
7. Mai committare secrets. Mai scrivere `claude_api_key` reali in test, fixture, esempi, docstring.
8. Apertura di PR con descrizione strutturata (vedi template sezione 7).

---

## 2. Roadmap tecnica dettagliata

Organizzata in **4 fasi incrementali**, ciascuna con milestone di release. Ogni feature ha: *cosa fare*, *perché*, *criteri di accettazione*, *punti tecnici da approfondire*.

### PHASE 2A — Integrazione HA nativa → **Sprint A + Sprint E**

> **Stato aggiornato 2026-04-28:** La roadmap originale prevedeva target v0.3.0. La codebase reale è a v0.5.16.
> Items qui sotto sono mappati sui nuovi Sprint A e Sprint E (vedi tabella Sprint Plan sopra).

**Obiettivo di fase:** rendere HIRIS percepito come componente di HA, non come tab separata.

---

#### 2A.1 — Sensor bridge via MQTT Discovery → **Sprint A** ⚠️ PARZIALE

> **Stato:** `mqtt_publisher.py` già implementa publish + discovery per `sensor.status`, `sensor.last_run`, `sensor.budget_eur`, `switch.enabled`. MQTT config già in `config.yaml`.
> **Delta Sprint A:** aggiungere MQTT subscribe (command_topic per switch/button), entity `last_result`, `budget_remaining_eur`, `tokens_used_today`. Correggere `update_agent()` che non chiama publish su enable/disable.

**Cosa fare:**
Publisher MQTT già in produzione. Completare la bridge 2-way e le entità mancanti. Per ogni agent configurato HIRIS pubblica automaticamente:

- `sensor.hiris_<agent_id>_status` → `idle` / `running` / `disabled` / `budget_exceeded` / `error`
- `sensor.hiris_<agent_id>_last_run` → timestamp ISO 8601 ultima esecuzione
- `sensor.hiris_<agent_id>_last_result` → summary short (max 255 char) dell'ultimo output
- `sensor.hiris_<agent_id>_budget_consumed_eur` → float, costo cumulativo
- `sensor.hiris_<agent_id>_budget_remaining_eur` → float, budget - consumato
- `sensor.hiris_<agent_id>_tokens_used_today` → int, daily reset a mezzanotte locale
- `switch.hiris_<agent_id>_enabled` → on/off, comanda abilitazione agent
- `button.hiris_<agent_id>_run_now` → trigger manuale esecuzione

**Perché:** è il modo HA-nativo di esporre stato da un addon. Gli utenti possono inserire questi sensor in qualsiasi card Lovelace standard (entity, gauge, history-graph) senza plugin aggiuntivi.

**Criteri di accettazione:**
- Configurazione MQTT opzionale (se non configurato, HIRIS funziona senza bridge ma logga warning)
- Discovery topic conforme a `homeassistant/<component>/<node_id>/<object_id>/config`
- Reconnect automatico a MQTT broker con backoff esponenziale
- `device_info` che raggruppa tutti gli entity di un agent sotto un device HA unificato
- Test E2E con broker Mosquitto in Docker
- Documentazione utente: sezione "Dashboards" nel README con esempi card YAML

**Punti tecnici da approfondire:**
- Libreria MQTT Python: `asyncio-mqtt` (più moderno, asyncio-native) vs `paho-mqtt` (standard ma sincrono). Decisione da ADR. Nota: `asyncio-mqtt` è deprecated a favore di `aiomqtt`, verificare maintenance status.
- Retention dei messaggi di stato: retained messages per status, non retained per events.
- Autenticazione broker: supportare anonymous, username/password, TLS certificates (riutilizzo cert Mosquitto addon se presente).
- Fallback: se utente non ha broker MQTT, offrire REST API bridge con HA token long-lived come piano B (vedi 2A.2).

---

#### 2A.2 — REST bridge come fallback (no-MQTT path) → **DEFER (non in Sprint A)**

> **Decisione 2026-04-28:** La Lovelace card usa già REST + SUPERVISOR_TOKEN per tutte le chiamate. Aggiungere un secondo REST bridge per le entity sarebbe ridondante rispetto alla strada MQTT già avviata. Defer a dopo Sprint A per valutare se ancora necessario.

**Cosa fare (se ripreso):**
Se l'utente non ha Mosquitto installato, HIRIS deve comunque poter creare entità HA. Implementare un modulo che chiama direttamente l'API HA REST/WebSocket per mantenere entità template sincronizzate.

**Criteri di accettazione:**
- Auto-detection: se Mosquitto addon è presente e raggiungibile, usa MQTT; altrimenti REST/WS.
- Uso di `SUPERVISOR_TOKEN` disponibile nell'ambiente addon per autenticazione senza config utente.
- Performance accettabile fino a 20 agent (per ogni tick di update, non più di 40 chiamate HA al secondo).

**Punti tecnici da approfondire:**
- Valutare se REST bridge richiede di mantenere uno stato server-side in HA tramite `hassio.addon_stdin` o se conviene un approach stateless con un'unica entità JSON blob da parsare in template sensor.
- Trade-off complessità vs UX: MQTT è più elegante ma ha prerequisito installazione broker. La strada più robusta è **MQTT first + documentazione chiara del prerequisito**, rimandando REST a versione successiva se la feedback community lo richiede.

---

#### 2A.3 — Custom Lovelace card `hiris-agent-card` → **Sprint E**

> **Stato:** Non ancora implementata. `hiris-chat-card` (2A.4) è il reference pattern per stile e deployment. Sprint E la costruisce riusando quella architettura.

**Cosa fare:**
Distribuire una custom card Lovelace che mostra lo stato di un singolo agent in una qualsiasi dashboard HA, con:

- Nome e tipo agent
- Badge status colorato
- Budget bar (consumato/totale)
- Ultima esecuzione + timestamp relativo
- Mini preview ultimo output (troncato, con "expand")
- Pulsante "Run now" (solo per monitor/preventive/reactive)
- Pulsante "Open chat" (apre HIRIS UI nella sidebar per agent di tipo chat)

Card distribuita come plugin HACS separato nel repo `paolobets/hiris` path `lovelace/hiris-agent-card/`.

**Criteri di accettazione:**
- Una card per agent, configurabile con:
  ```yaml
  type: custom:hiris-agent-card
  agent_id: soggiorno_monitor
  show_budget: true
  show_run_button: true
  ```
- Compatibile con Home Assistant ≥ 2024.1
- Stile allineato a Material Design 3 di HA (rispetta dark/light theme, usa variabili CSS `--primary-color`, `--secondary-background-color`)
- Bundle < 50KB minified
- No dipendenze esterne oltre a `lit` (già incluso in HA frontend)

**Punti tecnici da approfondire:**
- Stack: Lit 3 con TypeScript (stessa scelta delle custom cards ufficiali HA). Build con `rollup` o `vite`.
- Distribuzione via HACS: aggiungere `hacs.json` con `"content_in_root": false` e path specifico per le card. Verificare se serve repo separato o se HACS permette multi-content.
- Per la comunicazione con HIRIS, due opzioni: (a) WebSocket diretto all'addon via ingress URL (complicato, path ingress è dinamico), (b) chiamate HA service tramite entities MQTT (più semplice). Scegliere (b).

---

#### 2A.4 — Custom Lovelace card `hiris-chat-card` → ✅ COMPLETATA (v0.5.16)

> Chat card con streaming, selector agente, typing indicator, auto-deploy via WebSocket Lovelace, ingress URL discovery tramite `hiris-ingress.json`. Nessun delta necessario.

**Cosa fa:**
Custom card inline in una dashboard Lovelace, senza aprire la sidebar.

**Criteri di accettazione:**
- Layout responsive: mobile-friendly (usa stesse safe-area insets della UI principale)
- Supporto selezione agent (dropdown in header)
- Input testuale + pulsante send, streaming response token-by-token
- Storico conversazione persistente per agent (coerente con chat_history server-side di HIRIS)
- Lazy-loading: la card non apre WebSocket finché non è visibile

**Punti tecnici da approfondire:**
- Riuso codice: la chat UI già esiste come pagina standalone. Valutare se estrarre il core in un Web Component riutilizzabile oppure duplicare logica.
- Autenticazione: la card gira in contesto HA autenticato, serve un modo per HIRIS di fidarsi. Opzione 1: service call intermedio (`hiris.send_message`). Opzione 2: header `X-Supervisor-Token` tramite proxy HA ingress.

---

#### 2A.5 — HA Services esposti → **DEFER a Phase 3**

> **Decisione 2026-04-28:** La registrazione di servizi HA custom da un addon richiede ricerca approfondita sul Supervisor API (strada MQTT command_topic è più semplice e già parzialmente implementata). Defer a Phase 3 insieme al canvas designer.

**Cosa fare (se ripreso):**
Registrare servizi HA chiamabili da automation e script:

- `hiris.run_agent` — esegue un agent on-demand. Args: `agent_id`, `input` (opzionale).
- `hiris.enable_agent` / `hiris.disable_agent` — args: `agent_id`.
- `hiris.reset_budget` — args: `agent_id`, `period` (`monthly` / `total`).
- `hiris.chat` — invia messaggio a chat agent. Args: `agent_id`, `message`. Response: testo risposta in `response_variable`.
- `hiris.get_agent_status` — args: `agent_id`. Ritorna stato completo.

**Criteri di accettazione:**
- Schema YAML `services.yaml` completo con description, fields, examples
- Gestione errori con exception chiarite (es. `agent_not_found`, `budget_exceeded`, `agent_disabled`)
- Test integrazione: un'automation YAML che triggera un agent e riceve il risultato

**Punti tecnici da approfondire:**
- I servizi custom degli addon richiedono registrazione via Supervisor API o esposizione tramite MQTT command topic. Approfondire il modello in HA docs: probabilmente strada più pulita è MQTT con `command_topic` su un entity `button.hiris_...`. Evitare di creare una finta integration solo per i services.

---

#### 2A.6 — Blueprint distribuiti → **Sprint E**

> Bundle con `hiris-agent-card` e HACS. Sono YAML puri, nessun codice Python. Sprint E li crea insieme al packaging HACS.

**Cosa fare:**
Creare e distribuire blueprint HA pronti all'uso per i pattern più comuni:

- `blueprints/hiris_morning_briefing.yaml` — preventive agent + notification + TTS opzionale
- `blueprints/hiris_energy_anomaly.yaml` — monitor agent su entità power con threshold
- `blueprints/hiris_door_reactive.yaml` — reactive agent su door/window + notifica contestuale
- `blueprints/hiris_chat_via_voice.yaml` — inoltra comandi vocali Assist a chat agent HIRIS

**Criteri di accettazione:**
- Ogni blueprint testato end-to-end in una VM HA pulita
- Documentazione d'uso in `docs/blueprints.md`
- Pulsante "Import Blueprint" badge nel README puntato a ciascun YAML

---

### PHASE 2B — Multi-provider e memoria persistente → **Sprint C + Sprint D**

> **Stato aggiornato 2026-04-28:** `chat_store.py` già implementa SQLite conversation history (sessioni, summary, retention 30d). Manca la parte vettoriale (sqlite-vec + RAG). LiteLLM non ancora implementato. LLM Router base esiste.

**Obiettivo di fase:** rimuovere il vendor lock-in su Claude e aggiungere memoria a lungo termine, due feature che abilitano conversazioni continuate e riduzione del gap con goruck.

---

#### 2B.1 — Adozione di LiteLLM come abstraction layer → **Sprint D** ⚠️ ADR-0002 first

> **Attenzione:** LiteLLM pesa ~100MB+. Su Raspberry Pi (target principale) potrebbe essere troppo pesante. ADR-0002 deve scegliere tra LiteLLM e uno shim custom leggero prima di iniziare l'implementazione.

**Cosa fare:**
Sostituire la chiamata diretta all'SDK Anthropic con [LiteLLM](https://github.com/BerriAI/litellm), libreria che espone una interface OpenAI-compatible su 100+ provider (Anthropic, OpenAI, Gemini, Ollama, Groq, Mistral, DeepSeek, Bedrock, Azure, OpenRouter, ecc.).

Claude rimane **default e consigliato**, ma configurabile.

**Criteri di accettazione:**
- Config option `model_provider` con valori `anthropic` (default), `openai`, `gemini`, `ollama`, `openrouter`, `auto`.
- Config option `model_id` che accetta qualsiasi identifier LiteLLM (es. `claude-sonnet-4-6`, `gpt-4o`, `gemini-2.5-flash`, `ollama/llama3.1`).
- Mapping automatico cost (€ per 1M token) per i model più comuni, aggiornabile via file `pricing.yaml`.
- Token counting accurato per-provider (LiteLLM lo gestisce).
- Auto-fallback opzionale: se primary provider fallisce, tenta fallback list.
- Test: ogni provider testato almeno con un happy path più un error path (401, 429, timeout).

**Punti tecnici da approfondire:**
- **Tool use cross-provider**: i schema di function calling di OpenAI, Anthropic e Gemini hanno sfumature diverse. LiteLLM astrae ma bisogna verificare compatibilità degli 8 tool HIRIS esistenti con OpenAI e Gemini. In particolare: parametri JSON schema rigidi di OpenAI, parameters object di Gemini. Produrre test matrix.
- **Streaming**: verificare che il token streaming via LiteLLM funzioni con tutti i provider target.
- **Prompt caching**: Claude ha il miglior supporto di prompt caching (fino a 90% riduzione costi). Con LiteLLM viene usato? Se no, valutare di mantenere una path specifica per Anthropic che bypassa LiteLLM per le chiamate principali, usando LiteLLM solo come fallback.
- **Size dependency**: LiteLLM è pesante (~100MB+ con tutti gli extras). Installare solo con `litellm[proxy]` → no. Usare `litellm` base + lazy-load provider specifici.
- Alternativa valutata: restare su SDK Anthropic diretto e scrivere uno shim minimal in-house per OpenAI/Gemini/Ollama. Costo manutenzione più alto ma dipendenza più leggera. **ADR richiesto** per scelta finale.

---

#### 2B.2 — Vector memory persistente con SQLite+sqlite-vec → **Sprint C**

> **Stato:** `chat_store.py` già implementa la tabella `chat_messages` + `chat_sessions` in SQLite. Sprint C aggiunge:
> - sqlite-vec come estensione sulla stessa `/data/chat_history.db`
> - Colonna `embedding BLOB` su `chat_messages`
> - Tabella `memories` per memorie esplicite
> - Tools `recall_memory`/`save_memory` per Claude
> - RAG injection nel system prompt prima di ogni call
> - `HISTORY_RETENTION_DAYS` configurabile (ora hardcoded a 30d)

**Cosa fare:**
Aggiungere layer vettoriale sulla base SQLite esistente. Ogni messaggio, ogni anomalia rilevata, ogni action suggerita viene vettorizzata e indicizzata. Prima di ogni chiamata LLM, RAG retrieval porta in contesto i k ricordi più rilevanti.

**Criteri di accettazione:**
- Database SQLite persistente in `/data/hiris.db` (mount volume addon)
- Schema:
  - `memories` (id, agent_id, content, embedding BLOB, metadata JSON, created_at, tags)
  - `chat_messages` (session_id, role, content, embedding BLOB, ts)
  - `anomalies` (agent_id, finding_type, entities JSON, severity, embedding BLOB, resolved_at)
- Embedding provider configurabile: `openai/text-embedding-3-small` (default, economico), `ollama/nomic-embed-text` (locale gratis), `gemini/text-embedding-004`.
- Similarity search < 50ms per 10k memorie (sqlite-vec benchmark).
- Decay: memorie vecchie (>6 mesi) e poco rilevanti vengono prunate automaticamente (configurable).
- Tool nuovo: `recall_memory(query, k=5, tags=[])` disponibile a Claude.
- Tool nuovo: `save_memory(content, tags=[])` per memorie esplicite.

**Punti tecnici da approfondire:**
- **sqlite-vec status**: è una libreria giovane (2024) ma molto promettente, successore spirituale di sqlite-vss. Verificare stabilità su ARM64 (Raspberry Pi, il target di Paolo). Alternative: `chromadb` in embedded mode (più pesante), `txtai` con FAISS (complicato da packagizzare).
- **Embedding cost**: OpenAI text-embedding-3-small costa $0.02 per 1M token. Per un homelab medio: stima 500 memorie al mese × 100 token medi = 50k token/mese = $0.001/mese. Trascurabile. Tuttavia in local-only mode serve Ollama.
- **Chunking strategy**: conversazioni lunghe vanno splittate in chunk (~500 token) o indicizzate come singola memoria? Decisione con impatto su qualità retrieval.
- **Privacy**: gli utenti homelab sono sensibili al leak. Documentare chiaramente cosa viene inviato a OpenAI per embeddings; default ragionevole è "opt-in, Ollama consigliato".

---

#### 2B.3 — Router LLM più sofisticato → **Sprint D**

> **Stato:** `llm_router.py` già wrappa `ClaudeRunner` e fa routing `classify_entities` → Ollama se configurato. Sprint D estende questo wrapper con strategy configurabile e fallback chain. **Dipende da ADR-0002** (se si sceglie LiteLLM, il Router diventa un thin wrapper su LiteLLM; se shim custom, il Router gestisce la logica direttamente).

**Cosa fare:**
Estendere il Router esistente (che già offre Ollama offload) con routing per:

- **Task complexity**: task semplici → Haiku/modello piccolo; task complessi → Sonnet/modello grande
- **Cost vs latency preference**: settings globale o per-agent
- **Provider fallback chain** configurabile

**Criteri di accettazione:**
- Config YAML:
  ```yaml
  llm_router:
    strategy: cost_first  # or: quality_first, latency_first, balanced
    fallback_chain:
      - claude-sonnet-4-6
      - gpt-4o-mini
      - ollama/llama3.1
    task_routing:
      classify: ollama/llama3.1
      chat: claude-sonnet-4-6
      summarize: claude-haiku-4-5
      tool_selection: claude-haiku-4-5
  ```

---

### PHASE 2C — Automation intelligence (target: v0.5.0, 6-8 settimane)

**Obiettivo di fase:** aggiungere capability da "agent vero" — scrittura/proposta automazioni, dashboard generator, anomaly baseline statistico.

---

#### 2C.1 — Tool di scrittura YAML con approval workflow

**Cosa fare:**
Permettere agli agent di **proporre** nuove automation/script/scene, ma **non scriverle direttamente**. La proposta finisce in una queue review, accessibile da:

- Custom card `hiris-proposals-card` (nella UI di HIRIS e/o dashboard)
- Notifica mobile HA con action buttons (Approve/Reject)

Se approvato, HIRIS scrive il YAML in `/config/automations.yaml` (o equivalent) con backup automatico.

**Criteri di accettazione:**
- Nuovo tool `propose_automation(yaml_content, rationale)` esposto a Claude
- Backup pre-scrittura in `/config/.storage/hiris_snapshots/<timestamp>_<file>`
- Validazione YAML sintattica e semantica (load via `voluptuous` se possibile)
- Reload automatico automazioni post-scrittura via service `automation.reload`
- Limite hard: max 5 proposte pending per agent

**Punti tecnici da approfondire:**
- File access: gli addon con `hassio_api: true` e `config_rw: true` possono scrivere in `/config`. Verificare che HIRIS abbia i permessi giusti in `config.yaml` addon.
- Rollback: se automation rotta, come tornare indietro? Backup + CLI command in HIRIS UI per restore.
- Approvazione multi-step: per automation "critiche" (es. che tocca lock, alarm, climate) richiedere PIN come fa goruck.

---

#### 2C.2 — Dashboard Lovelace generator

**Cosa fare:**
Tool `generate_dashboard(description)` che chiede a Claude di generare una dashboard Lovelace YAML valida, la applica via API `lovelace/config` (storage mode), e ritorna URL.

**Criteri di accettazione:**
- Supporto view multiple, cards standard (entity, picture-entity, gauge, history-graph, glance, grid)
- Supporto alcune card custom comuni (mushroom, bubble-card) se detected come installate
- Preview text nel chat prima di applicare
- Comando "revert" per annullare l'ultima dashboard generata

**Punti tecnici da approfondire:**
- API Lovelace storage mode: `GET/POST /api/lovelace/config`. Documentazione frammentata; valutare reverse-engineering o uso di `hass-client` Python se esiste.
- Content safety: l'AI potrebbe generare card che referenziano entità inesistenti. Validation pre-apply confrontando con `states` di HA.

---

#### 2C.3 — Baseline statistico per anomaly detection

**Cosa fare:**
Background job che per ogni entità numerica tracciata calcola rolling statistics (mean, stddev) su finestre 1h/24h/7d, salvate in SQLite. Rule engine deterministico che fa trigger findings quando:

- Deviation > N×stddev dal rolling mean (`baseline_deviation` rule)
- Deviation dal pattern hour-of-day medio (`time_of_day_anomaly` rule)
- Threshold assoluto configurabile (`sensor_threshold` rule)

**Findings notificati solo se un LLM triage (opt-in) li classifica come notify-worthy.**

**Criteri di accettazione:**
- Nuova tabella SQLite `baselines` (entity_id, metric, window, mean, stddev, sample_count, updated_at)
- Job APScheduler ogni 15 min (configurable) per recompute
- UI HIRIS: sezione "Anomaly Rules" dove utente gestisce regole attive per entity
- LLM triage opzionale: se abilitato, ogni finding passa da Claude/Haiku con prompt minimal (solo type, severity, 3-5 campi derivati) che decide `notify` or `suppress`

**Punti tecnici da approfondire:**
- Source dei dati: HA History API (via REST recorder) o sottoscrizione WebSocket eventi? Mix ottimale: WebSocket per live, History per backfill baseline iniziale.
- Scale: con 100+ entità e 3 finestre ciascuna, siamo a ~300 righe da aggiornare ogni 15min. SQLite gestisce facile.
- Goruck ha fatto tutto questo in Sentinel: non copiare, ispirare. Mantenere scope più ristretto (senza discovery LLM di nuove regole, senza proposal lifecycle complesso).

---

### PHASE 2D — Canali e vision (nice-to-have, 4 settimane)

**Obiettivo di fase:** allargare superficie di contatto (Telegram bot) e aggiungere vision senza face recognition.

---

#### 2D.1 — Telegram bot channel

**Cosa fare:**
Integrare [python-telegram-bot](https://python-telegram-bot.org/) per permettere chat con HIRIS via Telegram. Long polling (no IP pubblico richiesto).

**Criteri di accettazione:**
- Config: `telegram_bot_token`, `telegram_allowed_user_ids` (allowlist obbligatoria)
- Mapping bot → agent (routing: ogni user_id può avere un default agent)
- Comandi: `/start`, `/agent <id>`, `/status`, `/history`, `/stop`
- Stream response token-by-token via edit message
- Immagini: utenti possono mandare foto che vengono analizzate se vision tool abilitato

**Punti tecnici da approfondire:**
- Single bot vs multi-bot: un singolo bot con routing per user è più pulito.
- Compliance GDPR: log delle chat salvati, documentare data retention. Nessun dato di Telegram venduto/condiviso.
- **Skip WhatsApp** (Twilio, costi, compliance). **Skip Discord** salvo richiesta esplicita community.

---

#### 2D.2 — Vision tool (scene analysis senza face recognition)

**Cosa fare:**
Tool `analyze_image(image_source)` che accetta:
- `image.*` entity
- `camera.*` entity (snapshot via `camera.snapshot` service)
- Path file in `/media`
- Base64 image data

Passa a Claude (o altro provider multimodale) con prompt configurable. Ritorna description.

**Criteri di accettazione:**
- Object detection generico (persona, veicolo, pacco, animale) — **senza identificazione di persone specifiche**
- Costo monitorato: ogni chiamata vision è ~$0.003-0.01 con Claude Sonnet → segnalata nel budget
- Downscaling automatico prima dell'invio (max 1024px lato lungo, ~100KB JPEG)
- Cache: se stessa immagine analizzata negli ultimi 60s, restituisci cached result

**Punti tecnici da approfondire:**
- Formato API: Claude accetta base64 `image/jpeg|png|gif|webp`. OpenAI accetta URL o base64. LiteLLM normalizza.
- Privacy: documentare chiaramente che se si usa provider cloud, le immagini escono dalla rete locale.
- Face blur opzionale: se si vuole offrire vision **con** privacy, prima del send passare l'immagine per un blur dei volti usando OpenCV + Haar cascades o YuNet (sempre locale, sempre gratis). Bonus feature.

---

## 3. Decisioni architetturali da approfondire (ADR richiesti)

Per ciascuna delle seguenti decisioni Claude Code deve produrre un documento `docs/adr/NNNN-*.md` seguendo template standard (Context, Decision, Status, Consequences, Alternatives) **prima** di iniziare implementazione.

1. **ADR-0001: MQTT vs REST bridge vs Integration HA** (scelta primaria per esporre entity)
2. **ADR-0002: LiteLLM vs shim custom vs multi-SDK** (multi-provider strategy)
3. **ADR-0003: SQLite+sqlite-vec vs chromadb vs PostgreSQL** (vector store)
4. **ADR-0004: LangGraph adoption scope** (se/quando/dove)
5. **ADR-0005: Embedding provider default** (cloud vs local)
6. **ADR-0006: Custom card packaging** (HACS, repo separato vs mono-repo)
7. **ADR-0007: Auth model per Telegram bot** (long polling con allowlist vs webhook)

Ogni ADR deve citare esplicitamente le alternative valutate e il rationale della scelta. Se c'è incertezza, esplicitarla come "Open Question" e richiedere input umano.

---

## 4. Sicurezza del codice sorgente su Git

HIRIS è un progetto di un singolo sviluppatore con valore commerciale potenziale (futuro paid tier, consulenza, prestigio professionale). La sicurezza del codice è una prerequisite non negoziabile.

### 4.1 — Repository hygiene

- Attivare **branch protection** su `master` (o rinominare in `main` — standard moderno):
  - Require PR prima del merge
  - Require status checks (CI) before merging
  - Require linear history (no merge commits)
  - Dismiss stale reviews on new push
  - Include administrators nella protection (self-discipline)
- Abilitare **Secret scanning** (gratuito su public repo) e **Push protection**
- Abilitare **Dependabot** per:
  - Python dependencies (`requirements.txt`, `pyproject.toml`)
  - GitHub Actions workflows
  - Docker base images nel `Dockerfile`
- Abilitare **Code scanning** con GitHub CodeQL (gratis su public)
- Aggiungere `.gitignore` completo che esclude:
  ```
  .env
  .env.*
  *.key
  *.pem
  *.p12
  secrets.yaml
  /data/
  /config/
  .idea/
  .vscode/
  *.log
  __pycache__/
  .pytest_cache/
  .coverage
  htmlcov/
  dist/
  build/
  *.egg-info/
  node_modules/
  ```

### 4.2 — Pre-commit hooks

File `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: detect-private-key
      - id: no-commit-to-branch
        args: [--branch, master, --branch, main]
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.0
    hooks:
      - id: gitleaks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-PyYAML]
```

### 4.3 — Secret management

- **Mai** committare API keys, token, password. Neanche in test fixture.
- Fixture di test usano placeholder (`sk-ant-test-XXXX`) riconoscibili come fake.
- Se un secret viene committato per errore:
  1. Rotate immediato il secret reale
  2. `git filter-repo` per rimuovere dalla history (non solo `git rm`)
  3. Force-push (coordinato)
  4. Audit log per capire se è stato esposto
- Distribuzione di secrets in CI: GitHub Actions Secrets, mai in YAML plaintext.
- Per sviluppo locale: `.env.example` committato, `.env` gitignored.

### 4.4 — Backup e disaster recovery

- **Mirror read-only del repo** su un secondo git remote ogni settimana (cron job locale o GitHub Action che push su GitLab/Gitea/Codeberg).
- **Backup settimanale del repo + issues + wiki** usando `gh repo clone` + export issues. Salvato su QNAP NAS locale di Paolo (indirizzo già noto: 192.168.1.131).
- **Version tag** per ogni release + backup dell'artifact (tarball) su NAS.

### 4.5 — Commit signing

Abilitare GPG o SSH signing dei commit per garantire autenticità:

```bash
git config --global user.signingkey <key>
git config --global commit.gpgsign true
git config --global tag.gpgsign true
```

Aggiungere key pubblica su GitHub profile → commit appariranno con badge "Verified".

### 4.6 — CI/CD pipeline sicura

File `.github/workflows/ci.yml`:

- Run su ogni PR + push a main
- Jobs: `lint` (ruff, mypy), `test` (pytest con coverage), `build-docker` (dry-run), `security-scan` (trivy su image)
- **Non** dare write access a GITHUB_TOKEN se non strettamente necessario (`permissions: contents: read`)
- Pin di tutte le action a SHA commit, non tag mobili
- Require 2FA per maintainer accounts GitHub

### 4.7 — Licenza e IP

HIRIS è MIT. Considerare se per le parti che rappresentano valore commerciale (Retro Panel integration code, eventualmente parti di HIRIS in futuro) vale la pena:

- **Dual licensing** (MIT community + commercial license per uso B2B)
- **Business Source License (BSL)** per feature premium (delayed open source)
- Contributor License Agreement (CLA) per evitare che contributor esterni creino complicazioni IP

Questa decisione è strategica, da prendere prima di iniziare Phase 2C/2D. **ADR-0008: Licensing strategy** da scrivere.

---

## 5. Aggiornamento documentazione GitHub — dare carattere a HIRIS

La documentazione attuale è tecnicamente corretta ma anonima. Non crea attaccamento, non racconta una storia, non differenzia. Gli utenti scelgono progetti open source anche (e spesso soprattutto) per ragioni di *identità*.

### 5.1 — Nuovo README.md

Struttura target:

1. **Hero** con logo SVG grande, tagline **in italiano + inglese**:
   > *L'agente AI che tratta la tua casa come la tratti tu.*
   > *The AI agent that treats your home the way you do.*
2. **"Perché HIRIS esiste"** (3-4 paragrafi personali): cosa mancava negli altri progetti, cosa rappresenta la scelta dei 4 agent type, perché il budget EUR. **Scrivere in prima persona**.
3. **"Cosa rende HIRIS diverso"** (confronto onesto con i competitor): mini tabella che dichiara dove HIRIS è più forte e dove *non è il prodotto giusto*. Autenticità > marketing.
4. **Demo animata** (GIF/video) della chat in azione.
5. **Architettura** in 1 diagramma + 3 righe di testo. No paragrafate.
6. **Quick start** in 60 secondi: 4 comandi, schermo.
7. **Installation** dettagliata (già presente, migliorare).
8. **Showcase use cases** con 5-6 esempi narrativi.
9. **Philosophy** (nuova sezione): 4-5 principi che guidano il progetto (es. *Local-first when possible*, *Cost visibility over cost hiding*, *Italian ergonomics*, *Minimum viable magic*).
10. **Roadmap** pubblica (estratto da questo doc, versione leggibile).
11. **Contributing** + Code of Conduct.
12. **License + acknowledgments**.

### 5.2 — File aggiuntivi nel repo

- `docs/ARCHITECTURE.md` — deep dive tecnico
- `docs/COMPARISON.md` — confronto dettagliato con home-generative-agent, ha-claude, extended_openai_conversation. Onesto, niente FUD.
- `docs/PHILOSOPHY.md` — il manifesto del progetto
- `docs/USE_CASES.md` — 10-15 scenari reali di famiglia italiana (non generici US-centric)
- `docs/COST_GUIDE.md` — guida pratica al budget: quanto costa davvero usare HIRIS, esempi €/mese per 3 profili d'uso (basic/moderate/power)
- `docs/TROUBLESHOOTING.md`
- `docs/CHANGELOG.md` (esistente, mantenere)
- `CONTRIBUTING.md` + `CODE_OF_CONDUCT.md` (template GitHub)

### 5.3 — Branding e identità visiva

- **Logo**: attualmente c'è un `icon.png`. Commissionare o auto-produrre un logo SVG proper con un marchio riconoscibile. Paletta: consigliabile tonalità calde (non il solito blu tech), qualcosa che evochi "casa italiana" senza essere kitsch (pensa terracotta, olivastro, crema, con accento vivace).
- **Screenshots aggiornati** della UI in dark + light, mobile + desktop
- **Video demo** 60-90s caricato su YouTube e linkato nel README
- **Tagline ufficiale** (da finalizzare, proposte):
  - "AI agents che capiscono la tua casa"
  - "La tua casa, con un agente che ragiona"
  - "Home Assistant agents, made in Italy"

### 5.4 — GitHub repository metadata

- **About** (sidebar GitHub): tagline concisa + keywords
- **Topics**: `home-assistant`, `home-assistant-addon`, `ai-agent`, `claude`, `anthropic`, `llm`, `smart-home`, `agentic-ai`, `italian`, `homelab`
- **Website**: dominio custom se disponibile (es. `hiris.cloud`, `hiris.app`, `hiris.dev` — verifica disponibilità)
- **Social preview image** 1280×640 custom (non il default)
- Impostare **Releases** con release notes reali (non solo autogenerate), includere video/screenshot di cosa cambia

### 5.5 — Presenza esterna collegata

- Discussion GitHub attivata con categorie: Q&A, Ideas, Show & Tell, Announcements
- Issue templates: Bug report, Feature request, Question
- Pinned issues: "Welcome & Roadmap", "Known issues", "FAQ"

---

## 6. Milestone e delivery (aggiornato 2026-04-28)

Partenza da **v0.5.16**. Piano sprint:

### Sprint 0 — Critical Bugfixes → **v0.6.0** (patch release, 1-2 giorni)
- Fix `handlers_agents.py` + `handlers_usage.py`: `get("llm_router") or get("claude_runner")`
- Fix `task_tools.py`: funzioni sync → async
- Remove `app/ha_client.py` stub orfano
- Fix `SemanticContextMap`: aggiungere JSON persist/load
- EUR rate: costante centralizzata `_EUR_RATE` in un unico posto
- Fix `agent_engine.update_agent()`: publish MQTT su enable/disable
- **Versione: `0.6.0`** (breaking fix per LLMRouter users)

### Sprint A — HA-Bridge → **v0.6.1–v0.6.x**
- MQTT subscribe command_topic (switch + button.run_now)
- Entità MQTT mancanti (last_result, budget_remaining_eur, tokens_used_today)
- Tool `http_request`
- **Versione finale sprint: `0.6.x`**

### Sprint B — Tool Expansion → **v0.6.x**
- Tool `create_calendar_event`
- Tool `send_telegram` dedicato
- Tool `send_whatsapp`
- Action chaining reale
- **Versione finale sprint: `0.6.x`** (minor bump dal primo feat)

### Sprint C — Memory-RAG → **v0.7.0**
- Retention configurabile
- sqlite-vec + `recall_memory`/`save_memory`
- RAG injection
- **Versione: `0.7.0`** (minor bump per feature significativa)

### Sprint D — Multi-provider → **v0.7.x**
*Prerequisito: ADR-0002 scritto e approvato*
- LiteLLM o shim custom
- Router avanzato + pricing.yaml
- **Versione finale sprint: `0.7.x`**

### Sprint E — Lovelace + HACS → **v0.8.0**
- `hiris-agent-card`
- HACS packaging + blueprints
- **Versione: `0.8.0`** (milestone distribuzione pubblica)

### Phase 2C–2D (futuro, post v0.8.0)
- 2C: Automation intelligence (proposal workflow, dashboard generator, anomaly baseline)
- 2D: Telegram long-polling bot, vision tool
- **Target: v0.9.x → v1.0.0**

---

## 7. Template pull request

Ogni PR aperta da Claude Code deve seguire questo template:

```markdown
## Scope
<descrizione in 2-3 righe cosa fa questa PR>

## Linked ADR
<link a ADR se applicabile, o "N/A">

## Changes
- feat: ...
- fix: ...
- docs: ...
- test: ...

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual test steps documented
- [ ] Tested on HA 2024.1+ clean install

## Breaking changes
<Yes/No. If yes, migration path>

## Screenshots
<if UI change>

## Checklist
- [ ] Updated CHANGELOG.md
- [ ] Updated docs/ if relevant
- [ ] No secrets committed
- [ ] Coverage ≥70% on touched modules
- [ ] Lint/format/typecheck pass

## Open questions
<any decision needed from human review>
```

---

## 8. Interrupt conditions — quando fermarsi e chiedere

Claude Code deve fermarsi e richiedere input umano se:

1. Qualsiasi ADR ha alternative con trade-off significativi che non sono stati esplicitati in questo brief.
2. Un'implementazione richiede dipendenza > 50MB non prevista.
3. Un cambiamento tocca il file `repository.json` o `hacs.json` in modo che possa rompere installazioni esistenti.
4. Un bug fix richiede cambiare il nome di un entity/sensor già esposto (breaking change per utenti esistenti).
5. Si scopre una dipendenza tra phase diverse che richiede di riordinare il piano.
6. Test falliscono in modo inatteso e la causa non è chiara dopo 2 iterazioni di debug.

---

## 9. Definition of Done per HIRIS v1.0

Il progetto è considerato pronto per release 1.0 quando:

- Phase 2A completa e rilasciata
- Phase 2B completa e rilasciata
- Phase 2C completa (almeno approval workflow + baseline anomaly)
- Phase 2D opzionale (Telegram sì, vision bonus)
- README e documentazione rinnovati (sezione 5)
- 20+ utenti beta attivi (misurabile via GitHub stars + feedback in Issues/Discussions)
- CI verde su main per 30 giorni consecutivi
- Zero bug critical aperti
- Cost guide verificata da almeno 3 utenti reali
- Marketing asset prodotti (vedi documento separato di strategia marketing)

---

**Fine del brief. Claude Code può iniziare leggendo il repo attuale e proponendo il piano Week-by-Week per approvazione umana.**
