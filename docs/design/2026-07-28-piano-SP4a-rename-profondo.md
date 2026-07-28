# SP-4 Fase A — Rename profondo · Piano d'implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rinominare `agente→Chatbot` e `lente→Agentbot` in tutto HIRIS (entità, API, route, DB, storage, FE, MQTT, plumbing interno) + aggiornare Retro Panel in lockstep, **senza cambiare comportamento**.

**Architecture:** Rename meccanico esteso, eseguito per **domini coesi**. Ogni task rinomina un dominio + **tutti i chiamanti immediati** dei simboli che tocca + i suoi test, e termina con **suite completa verde** + un **grep di regressione** che prova zero residui del vecchio nome in quel dominio. Le migrazioni dati (storage/DB) usano il pattern `storage.init_schema` (`user_version`) e read-migration idempotente non-fatale.

**Tech Stack:** Python 3.11/3.12, aiohttp, SQLite (WAL via `app/storage.py`), APScheduler, MQTT (paho), vanilla JS (no bundler), pytest. Repo secondario: `retro-panel` (aiohttp).

## Global Constraints

- **Behavior-preserving:** il rename NON cambia semaforo, contratti E.2 (verdetto-JSON senza tool per Agentbot; tool liberi senza trigger per Chatbot), runner, memoria, scheduling. Solo nomi.
- **Scope massimale (deciso 2026-07-28):** rinominiamo anche (a) il **wire MQTT** (`hiris/agents`→`hiris/chatbots`, schema id discovery) **con cleanup one-time delle entità HA orfanizzate**; (b) **ogni `agent_id` interno → `chatbot_id`** (colonne+indici `chat_store`, `reasoning/queue`, metodi usage runner, kwargs dispatcher/task).
- **NON rinominare (flag, restano invariati):**
  - `agent_id` usato come **etichetta di origine richiesta** con valori `"mcp-gateway"`/`"unknown"` in `handlers_execute.py`, `handlers_gateway_pending.py`, `http_tools.py` — è un'origine, NON un id di Chatbot. Lasciare (eventuale rinomina a `origin`, mai a `chatbot_id`).
  - Il package/subsystem `hiris/app/agent/runner.py` (`"hiris-agent"` reasoning-queue poller) — è il runner-abbonamento, non l'entità Chatbot. Invariato.
  - `_DISCOVERY_PREFIX = "homeassistant"` (prefisso HA fisso).
  - Aggettivo `"agentic"` nei runner.
- **OUT del rename (route che restano):** `/api/chat`, `/api/chat/reply/{job_id}`, `/api/entities`, `/api/suggestions*`, `/api/sentinel/policy`, `/api/sentinel/timeline` (queste ultime = config/timeline Sentinella, non le lenti user-defined).
- **Migrazioni:** idempotenti, non-fatali al boot (pattern Slice 3: marker/guardia prima), nessuna perdita dati. Colonne DB via `init_schema` `user_version`.
- **Verifica completezza per dominio:** ogni task termina con un `grep` mirato che DEVE tornare zero (fuori dai path di migrazione/compat).
- **Suite completa verde** dopo ogni task (il rename è behavior-preserving: la suite è la rete di sicurezza).
- **Bump:** HIRIS **v0.102.0** + Retro Panel **v2.24.0** (rp-build `2240`) in **lockstep** nell'ultimo task.
- **Commit** per task. Conferma esplicita utente prima di merge/tag/release (fuori da questo piano).

## Mappa globale dei rename (riferimento per tutti i task)

| Vecchio | Nuovo |
|---|---|
| `Agent` (dataclass) | `Chatbot` |
| `AgentEngine` | `ChatbotEngine` |
| `create_agent/get_agent/update_agent/delete_agent/run_agent/list_agents/get_agent_status/_seed_default_agent/get_default_agent` | `*_chatbot` |
| `get_agent_usage/reset_agent_usage` (runner+router) | `get_chatbot_usage/reset_chatbot_usage` |
| `agents.json` · `AGENTS_DATA_PATH` · `DEFAULT_AGENTS_DATA_PATH` · `DEFAULT_AGENT_ID` | `chatbots.json` · `CHATBOTS_DATA_PATH` · `DEFAULT_CHATBOTS_DATA_PATH` · `DEFAULT_CHATBOT_ID` (valore literal `"hiris-default"` invariato) |
| `schema_version:3` chiave JSON `"agents"` | chiave `"chatbots"` (migrazione legge entrambe) |
| `handlers_agents.py` · `/api/agents` · `#/agents` | `handlers_chatbots.py` · `/api/chatbots` · `#/chatbots` |
| `watcher/lenses.py` fns (`validate_lens/load_lenses/save_lenses/upsert_lens/delete_lens`) | `validate_agentbot/load_agentbots/save_agentbots/upsert_agentbot/delete_agentbot` |
| `lens_runner.py` (`run_lens/lens_action/lens_message/normalize_lens_severity`) | `agentbot_runner`… (`run_agentbot/agentbot_action/agentbot_message/normalize_agentbot_severity`) |
| `sentinel_lenses.json` · `_LENS_JOB_PREFIX="hiris_lens_"` · `register_lens_schedules/_run_scheduled_lens` | `agentbots.json` · `"hiris_agentbot_"` · `register_agentbot_schedules/_run_scheduled_agentbot` |
| `handlers_lenses.py` · `/api/lenses` · `#/sentinel` (lenti) · `app["user_lenses"]` | `handlers_agentbots.py` · `/api/agentbots` · `#/agentbots` · `app["user_agentbots"]` |
| DB col `knowledge_items.lens` · kwarg `lens=` · `delete_by_lens/purge_expired_lens` | `chatbot_id` · `chatbot_id=` · `delete_by_chatbot/purge_expired_chatbot` |
| DB cols `chat_store.*.agent_id` + idx `idx_msg_agent/idx_sess_agent` · `reasoning/queue` `agent_id` · kwargs dispatcher/task `agent_id` | `chatbot_id` + `idx_msg_chatbot/idx_sess_chatbot` |
| MQTT `_STATE_PREFIX="hiris/agents"` · discovery id `hiris_<id>` · `publish_agent_state` | `"hiris/chatbots"` · nuovo schema (vedi Task 1) · `publish_chatbot_state` |
| FE `agent-editor.js/agent-form.js/agents-list.js/sentinel-route.js` + globali `HirisAgentEditor/HirisAgentsList/HirisSentinelRoute/loadAgents/window.agents` | `chatbot-editor.js/chatbot-form.js/chatbots-list.js/agentbot-route.js` + `HirisChatbotEditor/HirisChatbotsList/HirisAgentbotRoute/loadChatbots/window.chatbots` |
| RP `hiris_proxy.py` upstream `/api/agents` (×3) | `/api/chatbots` (`/api/chat` invariato) |

---

## Task 1: Chatbot entity, engine, storage + MQTT wire

**Files:**
- Modify: `hiris/app/agent_engine.py` (→ contenuto; opzionale rinominare file a `chatbot_engine.py`), `hiris/app/mqtt_publisher.py`, `hiris/app/server.py` (wiring engine + env), immediate callers of engine methods: `hiris/app/api/handlers_agents.py`, `hiris/app/api/handlers_chat.py`.
- Test: `tests/test_agent_engine.py` (→ `test_chatbot_engine.py`), MQTT tests, `tests/test_mqtt_*` se presenti.

**Interfaces:**
- Produces: `Chatbot` dataclass, `ChatbotEngine` (metodi `*_chatbot`), `chatbots.json` con migrazione da `agents.json`, MQTT topic `hiris/chatbots` + cleanup discovery orfani.

- [ ] **Step 1: Rinomina file engine (se scelto)**

```bash
git mv hiris/app/agent_engine.py hiris/app/chatbot_engine.py
git mv tests/test_agent_engine.py tests/test_chatbot_engine.py
```
Nota: se il rename-file crea troppo rumore nei riferimenti, è ammesso tenere il filename e rinominare solo i simboli — decidere all'inizio del task e restare coerenti. Default: rinominare il file.

- [ ] **Step 2: Rinomina i simboli entità/engine + storage migration**

In `chatbot_engine.py`: `Agent`→`Chatbot`, `AgentEngine`→`ChatbotEngine`, tutti i metodi `*_agent`→`*_chatbot`, costanti `DEFAULT_AGENTS_DATA_PATH`→`DEFAULT_CHATBOTS_DATA_PATH` (valore `/data/chatbots.json`), `DEFAULT_AGENT_ID`→`DEFAULT_CHATBOT_ID` (valore `"hiris-default"` invariato), env `AGENT_RUN_TIMEOUT`/`AGENT_RATE_LIMIT_*` → `CHATBOT_RUN_TIMEOUT`/`CHATBOT_RATE_LIMIT_*`, dict interni `_agents`→`_chatbots`, `_running_agents`→`_running_chatbots`, `_error_agents`→`_error_chatbots`.

`_save()`: scrivi `{"schema_version": 4, "chatbots": [...]}`. `_load()`: **leggi retro-compat** sia `chatbots` sia `agents`, e migra `agents.json`→`chatbots.json` one-time. Codice di migrazione (aggiungi in cima a `_load`):

```python
    def _load(self) -> None:
        # One-time migration agents.json -> chatbots.json (idempotente).
        legacy = self._data_path.replace("chatbots.json", "agents.json")
        if not os.path.exists(self._data_path) and os.path.exists(legacy):
            try:
                with open(legacy, encoding="utf-8") as f:
                    raw = json.load(f)
                raw.setdefault("chatbots", raw.pop("agents", []))
                raw["schema_version"] = 4
                tmp = self._data_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, default=str)
                os.replace(tmp, self._data_path)
                logger.info("Migrated agents.json -> chatbots.json")
            except Exception:
                logger.warning("agents.json migration failed", exc_info=True)
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("chatbots", data.get("agents", [])):
                chatbot = Chatbot(
                    ...  # stessi campi di oggi (invariati)
                )
                self._chatbots[chatbot.id] = chatbot
        except Exception as exc:
            logger.error("Failed to load chatbots from %s: %s", self._data_path, exc)
```

- [ ] **Step 3: MQTT wire + cleanup discovery orfani** (`mqtt_publisher.py`)

Rinomina `_STATE_PREFIX = "hiris/agents"` → `"hiris/chatbots"`; lo schema discovery `hiris_<id>` → `chatbot_<id>`; metodo `publish_agent_state`→`publish_chatbot_state`; parametri `agent`→`chatbot`. Aggiungi una pulizia one-time delle entità pubblicate col vecchio schema, chiamata al primo publish o allo start:

```python
    _OLD_STATE_PREFIX = "hiris/agents"
    _OLD_ID_FMT = "hiris_{id}"

    async def cleanup_legacy_discovery(self, chatbot_ids: list[str], metrics: list[str]) -> None:
        """Rimuove le entità HA scoperte col vecchio schema (payload retained vuoto)."""
        for cid in chatbot_ids:
            for metric in metrics:
                topic = f"{_DISCOVERY_PREFIX}/sensor/{self._OLD_ID_FMT.format(id=cid)}_{metric}/config"
                try:
                    self._client.publish(topic, payload="", retain=True)
                except Exception:
                    logger.warning("legacy discovery cleanup failed for %s", topic, exc_info=True)
```
Chiamala una volta (guardia marker file `/data/.mqtt_discovery_migrated`) dopo che i chatbot sono caricati, prima di ripubblicare col nuovo schema. `metrics` = l'elenco reale usato in `publish_discovery` (status/enabled/last_run/last_result/…).

- [ ] **Step 4: Wiring in `server.py`** — import `ChatbotEngine`, env `AGENTS_DATA_PATH`→`CHATBOTS_DATA_PATH` (default `/data/chatbots.json`), variabile `engine`/chiave `app["engine"]` (ammesso mantenere la chiave `"engine"`; rinominare i metodi chiamati). Aggiorna i chiamanti dei metodi engine in `handlers_agents.py` (`engine.get_agent`→`get_chatbot`, ecc.) e `handlers_chat.py` (`engine.get_agent(agent_id)`→`get_chatbot(...)`), e il cleanup `app["engine"].stop()`.

- [ ] **Step 5: Aggiorna test + verde**

Aggiorna `test_chatbot_engine.py` (nomi nuovi), aggiungi un test di migrazione `agents.json`→`chatbots.json` (scrivi un `agents.json` legacy in tmp, costruisci l'engine, verifica i chatbot caricati e il file nuovo creato). Aggiorna i test MQTT.

Run: `pytest tests/test_chatbot_engine.py -v` poi `pytest -q --maxfail=10`
Expected: verde.

- [ ] **Step 6: Grep di regressione (dominio)**

```bash
grep -rnE "class Agent\b|AgentEngine|agents\.json|_STATE_PREFIX.*hiris/agents|def .*_agent\b" hiris/app/agent_engine.py hiris/app/chatbot_engine.py hiris/app/mqtt_publisher.py 2>/dev/null
```
Expected: nessun match (a parte i path di migrazione `agents.json` legacy e i simboli `_OLD_*`).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor(rename): Chatbot entity/engine/storage + MQTT wire (Agent->Chatbot)"
```

---

## Task 2: Chatbot HTTP API + route SPA-side backend

**Files:**
- Rename: `hiris/app/api/handlers_agents.py` → `handlers_chatbots.py`; `tests/test_handlers_agents.py` → `test_handlers_chatbots.py`.
- Modify: `hiris/app/server.py` (import + 11 route `/api/agents`→`/api/chatbots`), `hiris/app/api/handlers_chat_history.py`, `hiris/app/api/handlers_tasks.py` (filtro), `.smoke-test/mock_backend.py`.
- Test: `test_handlers_chatbots.py`, `tests/test_api.py`, `tests/test_handlers_chat_history.py`, `tests/test_handlers_smoke.py`, `tests/test_security.py`.

**Interfaces:**
- Consumes: `ChatbotEngine` (Task 1).
- Produces: route `/api/chatbots*`; handler `handle_*_chatbot`.

- [ ] **Step 1:** `git mv` dei due file. Rinomina handler `handle_list_agents`→`handle_list_chatbots` ecc.; helper `_check_agent_id`→`_check_chatbot_id`, `_validate_agent_payload`→`_validate_chatbot_payload`, `_AGENT_ID_RE`→`_CHATBOT_ID_RE`. `handle_list_entities` (che è `/api/entities`) **resta** (non rinominare la sua route).
- [ ] **Step 2:** In `server.py` aggiorna l'import e le **11 route** `/api/agents*`→`/api/chatbots*` (righe della lista in §inventario: list/create/get/put/delete/run/usage/usage-reset/context-preview/chat-history GET+DELETE). NON toccare `/api/chat`, `/api/entities`, `/api/suggestions*`. Aggiorna `handlers_chat_history.py` (path param del route). **NON** rinominare qui il query-param `agent_id` di `handlers_tasks.py` né i kwargs `agent_id` di `task_engine`/`chat_store` → restano fino al Task 6 (altrimenti la suite si rompe a metà sequenza).
- [ ] **Step 3:** Aggiorna i test elencati (`/api/agents`→`/api/chatbots`; import handler rinominati in `test_security.py`). Aggiorna `.smoke-test/mock_backend.py`.
- [ ] **Step 4:** Run `pytest tests/test_handlers_chatbots.py tests/test_api.py tests/test_security.py -v` poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 5: Grep**
```bash
grep -rn "/api/agents" hiris/app/ tests/ .smoke-test/ | grep -v "chatbots"
```
Expected: nessun match.
- [ ] **Step 6: Commit** `refactor(rename): /api/agents -> /api/chatbots + handlers_chatbots`

---

## Task 3: Agentbot (lens) entity, runner, scheduler

**Files:**
- Modify/rename: `hiris/app/watcher/lenses.py`, `hiris/app/watcher/lens_runner.py`, `hiris/app/server.py` (scheduler + guardian wiring).
- Test: `tests/test_user_lenses_store.py`, `tests/test_run_lens.py`, `tests/test_scheduled_lenses.py`, `tests/test_event_lenses.py`, `tests/test_generic_detector.py` (rinominare a `*agentbot*` dove sensato).

**Interfaces:**
- Produces: `validate_agentbot/load_agentbots/save_agentbots/upsert_agentbot/delete_agentbot`, `run_agentbot`, `agentbots.json` (migrazione da `sentinel_lenses.json`), job prefix `hiris_agentbot_`.

- [ ] **Step 1:** In `watcher/lenses.py`: `_PATH="sentinel_lenses.json"`→`"agentbots.json"` con **migrazione one-time** in `load_agentbots` (se esiste `sentinel_lenses.json` e non `agentbots.json`, copia/rinomina). Rinomina le funzioni (mappa globale). Le stringhe user-facing "Lente"/"lente" → "Agentbot".

Migrazione (in `load_agentbots`):
```python
def load_agentbots(data_dir: str) -> list[dict]:
    path = _file(data_dir)  # agentbots.json
    legacy = os.path.join(data_dir, "sentinel_lenses.json")
    if not os.path.exists(path) and os.path.exists(legacy):
        try:
            os.replace(legacy, path)
            logger.info("Migrated sentinel_lenses.json -> agentbots.json")
        except Exception:
            logger.warning("agentbots migration failed", exc_info=True)
    ...  # resto invariato (read+validate)
```

- [ ] **Step 2:** `watcher/lens_runner.py`: rinomina `run_lens`→`run_agentbot`, `lens_action`→`agentbot_action`, `lens_message`→`agentbot_message`, `normalize_lens_severity`→`normalize_agentbot_severity`; stringhe "Lente"→"Agentbot" (riga 94 messaggio). `cap_scope = f"lens:{...}"` → `f"agentbot:{...}"` (chiave runtime — coerente con lo store wake-count; verifica che non rompa conteggi persistiti: se `sentinel_store` conserva scope `lens:*`, aggiungi lettura retro-compat o accetta reset conteggi, decidi nel task e annota).
- [ ] **Step 3:** `server.py` scheduler/guardian: `_LENS_JOB_PREFIX="hiris_lens_"`→`"hiris_agentbot_"`, `register_lens_schedules`→`register_agentbot_schedules`, `_run_scheduled_lens`→`_run_scheduled_agentbot`, `_run_lens`→`_run_agentbot`, import `load_lenses`→`load_agentbots`, `app["run_lens"]`→`app["run_agentbot"]`, `app["register_lens_schedules"]`→`app["register_agentbot_schedules"]`, guardian kwargs `get_user_lenses`/`run_lens`.
- [ ] **Step 4:** Aggiorna i 5 test (nomi funzioni/file JSON). Aggiungi test migrazione `sentinel_lenses.json`→`agentbots.json`.
- [ ] **Step 5:** Run test mirati poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 6: Grep**
```bash
grep -rnE "sentinel_lenses\.json|def (validate|load|save|upsert|delete)_lens|run_lens|_LENS_JOB_PREFIX" hiris/app/watcher/ hiris/app/server.py | grep -v agentbot
```
Expected: nessun match (fuori dai path migrazione legacy).
- [ ] **Step 7: Commit** `refactor(rename): watcher lens -> Agentbot (store/runner/scheduler)`

---

## Task 4: Agentbot HTTP API + route

**Files:**
- Rename: `hiris/app/api/handlers_lenses.py` → `handlers_agentbots.py`; `tests/test_lenses_api.py` → `test_agentbots_api.py`.
- Modify: `hiris/app/server.py` (import + 4 route `/api/lenses`→`/api/agentbots`), `app["user_lenses"]`→`app["user_agentbots"]`.

- [ ] **Step 1:** `git mv` file. Rinomina `set_lenses`→`set_agentbots`, `get_event_lenses`→`get_event_agentbots`, handler `handle_*_lens`→`handle_*_agentbot`, chiave cache `app["user_lenses"]`→`app["user_agentbots"]`. Aggiorna i riferimenti a questa chiave anche in `server.py` (guardian wiring `get_event_lenses`).
- [ ] **Step 2:** `server.py`: import + 4 route `/api/lenses*`→`/api/agentbots*`.
- [ ] **Step 3:** Aggiorna `test_agentbots_api.py` (`/api/lenses`→`/api/agentbots`).
- [ ] **Step 4:** Run poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 5: Grep** `grep -rn "/api/lenses\|user_lenses\|handlers_lenses" hiris/app/ tests/` → zero.
- [ ] **Step 6: Commit** `refactor(rename): /api/lenses -> /api/agentbots + handlers_agentbots`

---

## Task 5: DB colonna `knowledge_items.lens` → `chatbot_id`

**Files:**
- Modify: `hiris/app/brain/knowledge_store.py` (schema + migrazione v3 + kwargs + metodi), callers: `hiris/app/api/handlers_chat.py`, `hiris/app/brain/memory_migration.py`, `hiris/app/brain/reasoner_memory.py`, `hiris/app/tools/memory_tools.py`, `hiris/app/tools/knowledge_tools.py`, `hiris/app/tools/dispatcher.py`, `hiris/app/api/handlers_chatbots.py` (`delete_by_lens`), `hiris/app/server.py` (`purge_expired_lens`).
- Test: `tests/test_knowledge_store_lens.py`→`test_knowledge_store_chatbot.py`, `tests/test_lens_purge.py`, `tests/test_memory_alias_unified.py`, `tests/test_memory_migration.py`, `tests/test_api.py`.

**Interfaces:**
- Produces: colonna `chatbot_id`, kwarg `chatbot_id=`, `delete_by_chatbot/purge_expired_chatbot`.

- [ ] **Step 1: Schema + migrazione v3** in `knowledge_store.py`.

`_SCHEMA` riga 33: `lens TEXT` → `chatbot_id TEXT`. Bump `init_schema(..., version=3, migrations={2: _migrate_v2, 3: _migrate_v3})`. Aggiungi:

```python
def _migrate_v3(conn: sqlite3.Connection) -> None:
    """v2 -> v3: rinomina la colonna `lens` (id del Chatbot che scopa la memoria)
    in `chatbot_id`. Idempotente: salta se gia' rinominata."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(knowledge_items)").fetchall()]
    if "lens" in cols and "chatbot_id" not in cols:
        conn.execute("ALTER TABLE knowledge_items RENAME COLUMN lens TO chatbot_id")
```
(SQLite ≥3.25 `RENAME COLUMN` sicuro: nessun indice/vista/trigger/FK su `lens`.)

- [ ] **Step 2:** Rinomina kwargs e SQL: `add_item(..., lens=...)`→`chatbot_id=...`, INSERT column list `lens`→`chatbot_id`; `search(..., lens=...)`→`chatbot_id=...` + le clausole `(lens = :lens OR lens IS NULL)`→`(chatbot_id = :chatbot_id OR chatbot_id IS NULL)`; `delete_by_lens`→`delete_by_chatbot` (SQL `WHERE chatbot_id=?`); `purge_expired_lens`→`purge_expired_chatbot` (SQL `WHERE chatbot_id IS NOT NULL ...`).
- [ ] **Step 3:** Aggiorna i 9 call-site a `chatbot_id=<valore>` (il valore resta la variabile id corrente): `handlers_chat.py:284`, `memory_migration.py:99`, `reasoner_memory.py:57`, `memory_tools.py` (param `lens`→`chatbot_id` a righe 81/114/135/160), `knowledge_tools.py:94/115`, `dispatcher.py:468/476/510`, `handlers_chatbots.py` (`delete_by_lens`→`delete_by_chatbot`), `server.py:1077` (`purge_expired_lens`→`purge_expired_chatbot`).
- [ ] **Step 4:** Aggiorna i test (colonna/kwarg/metodi). Aggiungi test migrazione v2→v3: crea una knowledge.db a `user_version=2` con righe che hanno `lens`, apri lo store, verifica `chatbot_id` presente e dati preservati.
- [ ] **Step 5:** Run test mirati poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 6: Grep** `grep -rnE "\blens\b" hiris/app/brain/knowledge_store.py hiris/app/tools/memory_tools.py hiris/app/tools/knowledge_tools.py | grep -viE "chatbot|# "` → zero (attenzione a non confondere col watcher-lens, già rinominato in Task 3).
- [ ] **Step 7: Commit** `refactor(rename): knowledge_items.lens -> chatbot_id (migrazione v3)`

---

## Task 6: Plumbing interno `agent_id` → `chatbot_id`

**Files:**
- Modify: `hiris/app/chat_store.py` (colonne+indici+migrazione+metodi), `hiris/app/reasoning/queue.py`, `hiris/app/backends/claude_runner.py`, `hiris/app/backends/openai_compat_runner.py`, `hiris/app/llm_router.py` (usage methods), `hiris/app/tools/dispatcher.py`, `hiris/app/task_engine.py`, `hiris/app/tools/task_tools.py`, `hiris/app/api/handlers_reasoning.py`, `hiris/app/api/handlers_chat.py` (`effective_agent_id`→`effective_chatbot_id`), `hiris/app/server.py` (`_submit_chat_reply`).
- Test: `tests/test_chat_store*.py`, `tests/test_tasks*.py`, `tests/test_reasoning*.py`, `tests/test_*usage*.py`, `tests/test_api.py`.

**Interfaces:**
- Produces: `chat_store` colonna `chatbot_id` + idx `idx_msg_chatbot/idx_sess_chatbot`; `get_chatbot_usage/reset_chatbot_usage`.

- [ ] **Step 1: chat_store migrazione colonna.** Rinomina le colonne `agent_id`→`chatbot_id` nelle due tabelle + indici `idx_msg_agent`→`idx_msg_chatbot`, `idx_sess_agent`→`idx_sess_chatbot`. Bump `user_version` con migrazione (usa il pattern rebuild se `RENAME COLUMN` non basta per gli indici — SQLite rinomina la colonna ma gli indici vanno ricreati). Codice migrazione (adatta al nome tabella reale):

```python
def _migrate_vN(conn):
    info = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "agent_id" in info and "chatbot_id" not in info:
        conn.execute("ALTER TABLE messages RENAME COLUMN agent_id TO chatbot_id")
    # ricrea gli indici col nuovo nome
    conn.execute("DROP INDEX IF EXISTS idx_msg_agent")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_chatbot ON messages(chatbot_id)")
    # idem per la tabella sessioni
```
(Verifica i nomi reali di tabelle/indici in `chat_store.py` prima; aggiorna `_SCHEMA` per le fresh install.)

- [ ] **Step 2:** Rinomina i metodi/param `agent_id`→`chatbot_id` in `chat_store.py`, `reasoning/queue.py`, `handlers_reasoning.py`, `server._submit_chat_reply`, `dispatcher.py`, `task_engine.py` (campo dataclass `Task.agent_id`→`chatbot_id` + migrazione se persistito), `task_tools.py`, `handlers_chat.py` (`effective_agent_id`→`effective_chatbot_id`, `agent_id`→`chatbot_id`). **NON toccare** gli `agent_id` di origine (`"mcp-gateway"`/`"unknown"`) in `handlers_execute.py`/`handlers_gateway_pending.py`/`http_tools.py`.
- [ ] **Step 3:** Runner usage: `get_agent_usage`→`get_chatbot_usage`, `reset_agent_usage`→`reset_chatbot_usage`, `_per_agent_usage`→`_per_chatbot_usage`, param `agent_id`→`chatbot_id` in `claude_runner.py`, `openai_compat_runner.py`, `llm_router.py`. Aggiorna i chiamanti (`handlers_chatbots.py` usage handlers da Task 2, `agent_engine`/`chatbot_engine` `get_agent_usage`).
- [ ] **Step 4:** Aggiorna i test. Aggiungi test migrazione chat_store (db legacy con `agent_id`→`chatbot_id`, dati preservati, indici nuovi presenti).
- [ ] **Step 5:** Run test mirati poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 6: Grep** `grep -rn "agent_id" hiris/app/ | grep -viE "mcp-gateway|origin|http_tools|handlers_execute|handlers_gateway_pending|chatbot"` → zero (restano solo le origini flaggate).
- [ ] **Step 7: Commit** `refactor(rename): agent_id interno -> chatbot_id (chat_store/queue/runner usage/dispatcher/task)`

---

## Task 7: Front-end

**Files:**
- Rename: `static/config/agent-editor.js`→`chatbot-editor.js`, `agent-form.js`→`chatbot-form.js`, `agents-list.js`→`chatbots-list.js`, `sentinel-route.js`→`agentbot-route.js`.
- Modify: `static/config/main.js`, `static/config.html`, `static/config/dashboard.js`, `models-route.js`, `usage-route.js`, `usage.js`, `logs.js`, `tasks-route.js`, `static/index.html`, `static/hiris-chat-card.js`.
- Test: `tests/test_models_frontend_wiring.py`, `tests/static/test_router.html`, eventuali wiring test.

**Interfaces:**
- Produces: file FE rinominati; globali `HirisChatbotEditor/HirisChatbotsList/HirisAgentbotRoute/loadChatbots/window.chatbots`; route `#/chatbots`, `#/agentbots`.

- [ ] **Step 1:** `git mv` dei 4 file. Rinomina i globali (`window.HirisAgentEditor`→`HirisChatbotEditor`, `HirisAgentsList`→`HirisChatbotsList`, `HirisSentinelRoute`→`HirisAgentbotRoute`, `loadAgents`→`loadChatbots`, `window.agents`→`window.chatbots`, `activeAgentId`→`activeChatbotId`, `nav-agents-count`→`nav-chatbots-count`) e tutti i loro chiamanti cross-file (`main.js`).
- [ ] **Step 2:** Sostituisci ovunque `api/agents`→`api/chatbots`, `api/lenses`→`api/agentbots`, `#/agents`→`#/chatbots`, `#/sentinel`→`#/agentbots`. In `main.js`: router regex, nav-active map (`route === 'agents'`→`'chatbots'`, `'sentinel'`→`'agentbots'`), badge fetch. In `config.html`: script includes (3 file rinominati) + nav template (`href`/`data-route`).
- [ ] **Step 3:** Aggiorna `test_models_frontend_wiring.py` (asserisce `"api/agents/"`→`"api/chatbots/"`), `tests/static/test_router.html` (`#/agents`→`#/chatbots`). Aggiungi/aggiorna un wiring test che asserisce l'assenza di `api/agents`/`#/sentinel` nei JS.
- [ ] **Step 4:** `node --check` su ogni JS modificato/rinominato. Poi `pytest -q --maxfail=10`. Verde.
- [ ] **Step 5: Grep**
```bash
grep -rnE "api/agents|api/lenses|#/agents|#/sentinel|HirisAgentEditor|HirisAgentsList|HirisSentinelRoute|loadAgents\b" hiris/app/static/ | grep -viE "chatbots|agentbots"
```
Expected: zero.
- [ ] **Step 6: Commit** `refactor(rename): front-end agent->chatbot, sentinel/lens->agentbot`

---

## Task 8: Retro Panel (lockstep) + cleanup + docs + bump + regressione finale

**Files:**
- Modify (RP): `retro-panel/app/api/hiris_proxy.py`, `retro-panel/tests/test_hiris_status_endpoint.py`, `retro-panel/config.yaml`, `retro-panel/app/static/config.html` + `index.html` (rp-build).
- Modify (HIRIS): vestigia in `chatbot_engine.py`/`templates.js` (placeholder "Monitor energia", hint "non gira automaticamente"), `hiris/config.yaml` (version), `CHANGELOG.md`, `docs/architettura.md`/`architecture.md`, `docs/come-funziona.md`/`how-it-works.md`, `PRODUCT.md`.

- [ ] **Step 1: Retro Panel** — in `hiris_proxy.py` aggiorna i 3 URL upstream `/api/agents`→`/api/chatbots` (L98 probe, L151 list, L193 toggle); `/api/chat` (L262) invariato. Aggiorna il commento L192. In `test_hiris_status_endpoint.py` L134 l'assert `.endswith("/api/agents")`→`"/api/chatbots"`. Le route browser-facing `/api/hiris/*` di RP restano.
- [ ] **Step 2: Bump RP** — `config.yaml` `2.23.0`→`2.24.0`; `rp-build`/`?v=` `2230`→`2240` in `config.html` e `index.html` (lockstep, entrambi). Run `pytest -q` in `retro-panel` → verde; `node --check` sugli static toccati.
- [ ] **Step 3: Cleanup vestigia HIRIS** — rimuovi/riscrivi placeholder e hint pre-Slice-5 (in `chatbot_engine.py` seed prompt, `templates.js`); i 5 template autonomi → riformulati o rimossi (decidi: mantieni come esempi Chatbot, togli il linguaggio "schedula/irriga").
- [ ] **Step 4: Docs + bump HIRIS** — `hiris/config.yaml` version → `0.102.0`; CHANGELOG entry (IT) SP-4 Fase A; `PRODUCT.md` + `architettura.md`/`architecture.md` + `come-funziona.md`/`how-it-works.md` allineati ai nomi Chatbot/Agentbot (chiude il TODO PRODUCT.md del north-star).
- [ ] **Step 5: Regressione finale whole-repo (HIRIS)** — DEVE tornare zero fuori da path di migrazione/flag:
```bash
grep -rnE "/api/agents|/api/lenses|class Agent\b|AgentEngine|def .*_lens\b|sentinel_lenses|#/sentinel|HirisAgentEditor" hiris/app/ tests/ | grep -viE "chatbot|agentbot|migrat|legacy|_OLD_"
```
Expected: zero. Poi `pytest -q` (HIRIS, atteso ~stesso conteggio di partenza, verde) e `pytest -q` (RP, verde).
- [ ] **Step 6: Commit** `chore(sp4a): Retro Panel lockstep, cleanup vestigia, docs+PRODUCT, bump HIRIS 0.102.0 / RP 2.24.0`

---

## Verifica finale & handoff (prima di merge — conferma utente)

- [ ] Suite completa verde su ENTRAMBI i repo; conteggio test HIRIS ~invariato (rename behavior-preserving).
- [ ] Grep di regressione finale = zero residui.
- [ ] Review indipendente whole-branch (Fable/Opus): behavior-preserving verificato; migrazioni (chatbots.json, agentbots.json, knowledge v3, chat_store, MQTT discovery cleanup) idempotenti e non-fatali; nessuna route/contratto cambiato oltre i nomi.
- [ ] Live-verify utente: addon HIRIS + RP aggiornati in lockstep; chat via RP funziona (`/api/chatbots`), gli Agentbot esistenti caricano da `agentbots.json`, le entità MQTT vecchie ripulite/rimpiazzate, la memoria per-Chatbot intatta.
- [ ] Conferma esplicita → merge `--no-ff` HIRIS + tag `v0.102.0`; RP release `v2.24.0`.

## Copertura spec (self-review)

- Rename entità/API/route/DB/storage/FE/MQTT/plumbing → Task 1-7. ✓
- Colonna `lens→chatbot_id` (uccide triplo-lens) → Task 5. ✓
- `agent_id` interno deep → Task 6. ✓
- MQTT wire + cleanup orfani → Task 1. ✓
- Retro Panel lockstep → Task 8. ✓
- Migrazioni idempotenti non-fatali → Task 1/3/5/6. ✓
- Behavior-preserving + grep zero-residui → ogni task + Task 8. ✓
- Bump v0.102.0 / RP v2.24.0 + PRODUCT.md → Task 8. ✓
- Flag NON-rinominati (origine mcp-gateway, `agent/runner.py`, discovery prefix, "agentic") → Global Constraints. ✓
