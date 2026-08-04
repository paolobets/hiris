# Agenti v1.1 — Fase 1: fondazione dello schema

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mettere lo schema in condizione di reggere le due modalità (REGOLA / OBIETTIVO) e rinominare `Task.chatbot_id → agent_id` **senza rompere nulla per l'utente e senza cambiare comportamento**.

**Architecture:** Fase deliberatamente *invisibile*. Nessuna modalità obiettivo funzionante, nessun tool nuovo, nessuna UI nuova. Si tocca solo il validatore, la persistenza e i contratti wire — perché il grounding ha mostrato che ogni campo nuovo introdotto dal front-end **sparisce in silenzio con un 201 di successo** (`validate_agentbot` scarta le chiavi sconosciute). Prima il validatore, poi tutto il resto.

**Tech Stack:** Python 3.11/3.12, aiohttp, pytest; JS vanilla senza build step, suite comportamentale `node --test` + jsdom.

## Global Constraints

- **Behavior-preserving.** A fine fase l'app si comporta *esattamente* come la 1.0. Un `mode` esiste nello schema ma solo il valore `"rule"` è raggiungibile.
- **Nessuna rottura per l'utente** — è la condizione che rende questa una 1.1 e non una 2.0. Se emerge una rottura inevitabile, **fermarsi e segnalarla**, non aggirarla.
- **Ordine non negoziabile: validatore → persistenza → wire → test → (FE nelle fasi successive).** `validate_agentbot` scarta le chiavi sconosciute *senza errore* (`watcher/agentbots.py:388-389`, pinnato da `tests/test_user_agentbots_store.py:72-78`): un campo aggiunto dal FE prima che il validatore lo conosca viene salvato con successo e sparisce.
- **Sicurezza invariata.** Non si tocca `security/semaphore.py`, non si tocca `allowed_tools=[]` (`server.py:1321`), non si tocca `agentbot_runner`. La modalità obiettivo è la Fase 3 e sarà un **percorso separato**, non un ramo di quello esistente.
- Suite verde dopo ogni task: baseline **pytest 1882**, **npm 62**.
- Commit per task. Nessun merge/tag senza conferma esplicita dell'utente.

### Riferimenti di grounding (verificati il 2026-07-29 su v1.0.0)

| Fatto | Dove |
|---|---|
| `validate_agentbot` ritorna una whitelist di **7 chiavi**; le sconosciute cadono in silenzio | `watcher/agentbots.py:438-446`, `:388-389` |
| **`action` è obbligatoria**: `if action is None: return None` | `watcher/agentbots.py:399-401` |
| `agentbots.json` è una **lista JSON nuda, senza `schema_version`** | `watcher/agentbots.py:39`, `:482`, `:515` |
| `Task.chatbot_id` + shim di lettura già esistente per `agent_id` | `task_engine.py:56`, `:208-211` |
| `tasks.json` scrive `schema_version: 1` ma **non lo legge mai** | `task_engine.py:181` vs `:198-235` |
| `GET /api/tasks` emette `chatbot_id` verbatim (`asdict`), **nessun alias, nessun test** | `handlers_tasks.py:15,25`; `task_engine.py:170` |
| Tool MCP `list_tasks`: proprietà `chatbot_id` letta **senza fallback** | `task_tools.py:62`; `dispatcher.py:387` |
| `?chatbot_id=` accetta **già** `?agent_id=` come fallback | `handlers_tasks.py:12` |
| `trigger.type` è già un discriminatore con **tre consumatori** | `handlers_agentbots.py:57-61`; `server.py:521+`; `agentbot_runner.py:130-141` |
| `test_fe_rename_regression.py` **vieta** `agent-editor.js` / `HirisAgentEditor` come "file pre-rename" | `tests/test_fe_rename_regression.py:23-27`, `:45-57` |

---

## Task 1: `mode` nello schema Agentbot (validatore per primo)

**Files:**
- Modify: `hiris/app/watcher/agentbots.py`
- Test: `tests/test_user_agentbots_store.py`

**Interfaces:**
- Produces: `validate_agentbot` accetta e restituisce `mode: "rule" | "objective"`; **assente ⇒ `"rule"`** (migrazione a fiuto sul contenuto); valore non ammesso ⇒ **rigetto dell'intero record** (coerente con `severity` e `enabled`, che rigettano se presenti-ma-invalidi).
- La whitelist di ritorno passa da 7 a **8 chiavi**.

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_user_agentbots_store.py  (aggiungi)
def test_mode_defaults_to_rule_when_absent():
    """Migrazione a fiuto: un agentbot pre-1.1 non ha `mode` -> e' una regola."""
    cleaned = validate_agentbot({
        "trigger": {"type": "event", "entity_id": "sensor.x",
                    "operator": ">", "threshold": 10},
        "action": {"type": "notify"},
    })
    assert cleaned is not None
    assert cleaned["mode"] == "rule"


def test_mode_objective_is_accepted():
    cleaned = validate_agentbot({
        "mode": "objective",
        "objective": "valuta i consumi",
        "trigger": {"type": "schedule", "interval_min": 60},
    })
    assert cleaned is not None
    assert cleaned["mode"] == "objective"


def test_mode_invalid_rejects_whole_record():
    """Coerente con severity/enabled: presente-ma-invalido = rigetto."""
    assert validate_agentbot({
        "mode": "banana",
        "trigger": {"type": "event", "entity_id": "sensor.x",
                    "operator": ">", "threshold": 10},
        "action": {"type": "notify"},
    }) is None
```

- [ ] **Step 2: Verifica che fallisca** — `pytest tests/test_user_agentbots_store.py -k mode -v` → FAIL (`KeyError: 'mode'`).

- [ ] **Step 3: Implementa.** In `validate_agentbot`, accanto ai controlli di `severity`/`enabled`, aggiungi:

```python
ALLOWED_MODES = frozenset({"rule", "objective"})
```
```python
    # mode: assente => "rule" (migrazione a fiuto: gli agentbot pre-1.1 sono
    # tutti regole). Presente-ma-non-ammesso => rigetto dell'intero record,
    # come per severity/enabled.
    mode = raw.get("mode", "rule")
    if mode not in ALLOWED_MODES:
        return None
```
e aggiungi `"mode": mode` al dict di ritorno.

**NON** toccare ancora `action` (Task 2) né aggiungere `objective` alla whitelist (Task 3): un test qui sopra usa già `mode: "objective"` con un `action` assente — **quel test fallirà finché il Task 2 non è fatto**. È voluto: rende visibile la dipendenza. Se preferisci una sequenza sempre-verde, unisci Task 1 e 2 in un solo commit.

- [ ] **Step 4: Verifica** — `pytest tests/test_user_agentbots_store.py -v` (atteso: `test_mode_objective_is_accepted` ancora rosso, gli altri verdi) poi `pytest -q --maxfail=10`.
- [ ] **Step 5: Commit** — `feat(agentbot): campo mode nello schema (rule|objective), default rule`

---

## Task 2: `action` condizionale al mode

**Il blocco più duro del grounding.** Oggi `action` è obbligatoria e la sua assenza rigetta l'intero record — ma un agente in modalità obiettivo **non ha un'azione dichiarata**: le sue azioni nascono come Task, a valle.

**Files:**
- Modify: `hiris/app/watcher/agentbots.py`
- Test: `tests/test_user_agentbots_store.py`

**Interfaces:**
- Produces: `action` **obbligatoria in `mode="rule"`** (invariato), **vietata in `mode="objective"`** (presente ⇒ rigetto: un agente-obiettivo che dichiara un'azione è una contraddizione, non una svista da ignorare).

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_user_agentbots_store.py  (aggiungi)
def test_rule_mode_still_requires_action():
    """Invariante 1.0: una REGOLA senza azione resta un rigetto."""
    assert validate_agentbot({
        "mode": "rule",
        "trigger": {"type": "event", "entity_id": "sensor.x",
                    "operator": ">", "threshold": 10},
    }) is None


def test_objective_mode_has_no_action():
    cleaned = validate_agentbot({
        "mode": "objective",
        "objective": "valuta i consumi",
        "trigger": {"type": "schedule", "interval_min": 60},
    })
    assert cleaned is not None
    assert cleaned.get("action") is None


def test_objective_mode_rejects_a_declared_action():
    """Un agente-obiettivo che dichiara un'azione e' una contraddizione."""
    assert validate_agentbot({
        "mode": "objective",
        "objective": "valuta i consumi",
        "trigger": {"type": "schedule", "interval_min": 60},
        "action": {"type": "notify"},
    }) is None
```

- [ ] **Step 2: Verifica che fallisca.**
- [ ] **Step 3: Implementa.** Rendi il controllo di `action` condizionale:

```python
    if mode == "rule":
        action = _validate_action(raw.get("action"))
        if action is None:
            return None
    else:  # objective
        if raw.get("action") is not None:
            return None
        action = None
```
e nel dict di ritorno emetti `"action": action` (che sarà `None` in objective).

- [ ] **Step 4: Verifica** — tutti i test di `test_user_agentbots_store.py` verdi, incluso `test_mode_objective_is_accepted` del Task 1. Poi `pytest -q --maxfail=10`.
- [ ] **Step 5: Commit** — `feat(agentbot): action obbligatoria solo in mode=rule, vietata in objective`

---

## Task 3: `objective` + gate incrociato mode/trigger

**Files:**
- Modify: `hiris/app/watcher/agentbots.py`
- Test: `tests/test_user_agentbots_store.py`

**Interfaces:**
- Produces: campo `objective` (stringa, troncata a 2000 come `reasoning.prompt`), **obbligatorio e non vuoto in objective**, **vietato in rule**.
- Gate incrociato: **`mode="objective"` con `trigger.type="event"` ⇒ rigetto**. Da design (§Decisioni punto 2) gli eventi restano dominio delle regole; un agente-obiettivo si innesca a mano, a pianificazione o su invocazione del Brain. Oggi il validatore non ha alcun controllo incrociato fra campi: questo è il primo.

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_user_agentbots_store.py  (aggiungi)
def test_objective_required_and_bounded():
    base = {"mode": "objective", "trigger": {"type": "schedule", "interval_min": 60}}
    assert validate_agentbot({**base}) is None                     # assente
    assert validate_agentbot({**base, "objective": "   "}) is None  # vuoto
    cleaned = validate_agentbot({**base, "objective": "x" * 5000})
    assert cleaned is not None and len(cleaned["objective"]) == 2000


def test_rule_mode_rejects_objective_field():
    assert validate_agentbot({
        "mode": "rule", "objective": "non dovrei esserci",
        "trigger": {"type": "event", "entity_id": "sensor.x",
                    "operator": ">", "threshold": 10},
        "action": {"type": "notify"},
    }) is None


def test_objective_mode_rejects_event_trigger():
    """Design: gli eventi restano alle REGOLE (costo zero); una regola puo'
    invocare un agente-obiettivo, ma l'obiettivo non si aggancia all'evento."""
    assert validate_agentbot({
        "mode": "objective", "objective": "valuta i consumi",
        "trigger": {"type": "event", "entity_id": "sensor.x",
                    "operator": ">", "threshold": 10},
    }) is None
```

- [ ] **Step 2: Verifica che fallisca.**
- [ ] **Step 3: Implementa** `objective` + il gate incrociato, ed emetti `"objective"` nel dict di ritorno (assente/`None` in rule).
- [ ] **Step 4: Verifica** — `pytest tests/test_user_agentbots_store.py -v` poi `pytest -q --maxfail=10`.
- [ ] **Step 5: Commit** — `feat(agentbot): campo objective + gate mode/trigger (objective non si aggancia a un evento)`

---

## Task 4: `Task.chatbot_id → agent_id`, con i due shim wire

**Il rename è meccanico; i due shim sono la parte che conta.** Senza, la promessa "1.1 non rompe nulla" è falsa (vedi §Correzione nel design doc).

**Files:**
- Modify: `hiris/app/task_engine.py`, `hiris/app/tools/task_tools.py`, `hiris/app/tools/dispatcher.py`, `hiris/app/api/handlers_tasks.py`, `hiris/app/static/config/tasks-route.js`
- Test: `tests/test_task_engine.py` (~40 call site), `tests/test_task_tools.py`, `tests/test_api_tasks.py`, `tests/test_dispatcher_tool_errors.py`, `tests/test_dispatcher_automation.py`

**Interfaces:**
- Produces: `Task.agent_id`; `add_task(..., agent_id=...)`; `list_tasks(agent_id=...)`.
- **Shim 1 (persistenza):** `_load` legge `agent_id` → `chatbot_id` → default. Copre tutte e tre le generazioni di nome. Nessuna riscrittura del file.
- **Shim 2 (risposta HTTP):** `GET /api/tasks` e `/api/tasks/{id}` emettono **entrambe** le chiavi (`agent_id` nuova + `chatbot_id` deprecata) finché non si decide di ritirarla.
- **Shim 3 (tool MCP):** lo schema di `list_tasks` dichiara `agent_id`, e `dispatcher.py` legge `inputs.get("agent_id") or inputs.get("chatbot_id")`.

- [ ] **Step 1: Test che fallisce — i due contratti wire, oggi scoperti**

```python
# tests/test_api_tasks.py  (aggiungi)
@pytest.mark.asyncio
async def test_task_response_carries_both_keys(aiohttp_client):
    """Il corpo di risposta emetteva chatbot_id verbatim, senza alias:
    rinominare senza shim romperebbe in silenzio ogni consumatore esterno."""
    client = await aiohttp_client(_make_app())      # helper esistente nel file
    body = await (await client.get("/api/tasks")).json()
    assert body, "il fixture deve produrre almeno un task"
    t = body[0]
    assert "agent_id" in t, "chiave nuova assente"
    assert "chatbot_id" in t, "alias deprecato rimosso troppo presto"
    assert t["agent_id"] == t["chatbot_id"]
```
```python
# tests/test_task_tools.py  (aggiungi)
def test_list_tasks_tool_accepts_both_input_keys():
    """dispatcher leggeva inputs['chatbot_id'] senza fallback: un client MCP
    esterno con la vecchia chiave riceveva la lista NON filtrata."""
    from hiris.app.tools.task_tools import LIST_TASKS_TOOL_DEF
    props = LIST_TASKS_TOOL_DEF["input_schema"]["properties"]
    assert "agent_id" in props
```

- [ ] **Step 2: Verifica che falliscano** — `pytest tests/test_api_tasks.py tests/test_task_tools.py -v`.
- [ ] **Step 3: Rinomina** il campo e i parametri nei 5 file di produzione. Lo shim di lettura in `_load` diventa:

```python
                    # Retro-compat a tre generazioni: agent_id (pre-SP4a),
                    # chatbot_id (SP-4a), agent_id (v1.1). Le due estremita'
                    # collassano sulla stessa chiave: nessuna riscrittura file.
                    agent_id=raw.get("agent_id", raw.get("chatbot_id", "hiris-default")),
```

- [ ] **Step 4: Shim di risposta HTTP.** In `handlers_tasks.py`, invece di restituire `asdict` grezzo:

```python
def _with_legacy_alias(t: dict) -> dict:
    """Emette anche `chatbot_id` (deprecato) accanto ad `agent_id`: il corpo di
    risposta non aveva alias e nessun test lo copriva -- vedi piano Fase 1."""
    out = dict(t)
    out["chatbot_id"] = out.get("agent_id")
    return out
```
applicato sia alla lista sia al singolo.

- [ ] **Step 5: Shim tool MCP.** In `task_tools.py` la proprietà diventa `agent_id` (descrizione aggiornata); in `dispatcher.py`:
```python
                    agent_id=inputs.get("agent_id") or inputs.get("chatbot_id"),
```

- [ ] **Step 6: FE** — `tasks-route.js:53` legge `t.agent_id || t.chatbot_id` (tollerante durante il rollout).

- [ ] **Step 7: Aggiorna i test** (~40 call site in `test_task_engine.py`, più gli altri file). **Aggiungi il test che manca:** il grounding ha rilevato che lo shim di lettura retro-compat in `_load` **non è coperto da alcun test** — scrivine uno che carica un `tasks.json` con la vecchia chiave e verifica che il task si carichi.

- [ ] **Step 8: Verifica** — `pytest -q --maxfail=10` verde; `node --check hiris/app/static/config/tasks-route.js`; `npm test` verde. Grep: `grep -rn "chatbot_id" hiris/app/task_engine.py hiris/app/tools/task_tools.py` → solo gli shim.
- [ ] **Step 9: Commit** — `refactor(task): chatbot_id -> agent_id con shim su persistenza, risposta HTTP e tool MCP`

---

## Task 5: riallineare le guardie anti-regressione FE

**Perché è un task e non una riga.** `tests/test_fe_rename_regression.py` è nato nella 1.0 per impedire di tornare ai nomi pre-rename: vieta `agent-editor.js` e la regex `HirisAgentEditor`. La v1.1 muove la nomenclatura **verso** "agent" — quindi quella guardia **collide di proposito** con la direzione nuova. Va **riscritta**, non aggirata.

**Files:**
- Modify: `tests/test_fe_rename_regression.py`
- Test: sé stesso

- [ ] **Step 1:** Leggi il file e distingui due categorie: (a) ciò che vieta i nomi *davvero* morti (`api/agents`, `api/lenses`, `#/sentinel`, `agent-form.js`, `agents-list.js`, `sentinel-route.js`) — **resta**; (b) ciò che vieta token che la v1.1 vuole riusare (`agent-editor.js`, `HirisAgentEditor`) — va rimosso dalla lista dei proibiti, con un commento che spiega *perché* è cambiato (altrimenti fra sei mesi qualcuno lo ri-aggiunge).
- [ ] **Step 2:** Nessun file FE viene rinominato in questa fase — il test va solo *preparato* a non ostacolare le fasi successive. Documenta nel file che il confine si è spostato.
- [ ] **Step 3: Verifica** — `pytest tests/test_fe_rename_regression.py -v` verde, poi `pytest -q --maxfail=10`.
- [ ] **Step 4: Commit** — `test(fe): la guardia anti-regressione non vieta piu' i nomi che la v1.1 riusa`

---

## Verifica finale & handoff (conferma utente prima di merge)

- [ ] `pytest -q` e `npm test` verdi.
- [ ] **Comportamento invariato:** un utente con Agentbot esistenti non nota nulla. Verificare che `agentbots.json` esistente si carichi, riceva `mode: "rule"` e venga risalvato senza perdite.
- [ ] Review indipendente: il gate incrociato mode/trigger regge; `action` resta obbligatoria in rule; i tre shim del Task 4 fanno il loro lavoro; nulla tocca semaforo/`allowed_tools`/`agentbot_runner`.
- [ ] Conferma esplicita utente → merge. **Nessun tag**: la 1.1 si tagga a fine Fase 4.

## Mappa delle fasi successive (da pianificare separatamente)

| Fase | Contenuto | Rilasciabile |
|---|---|---|
| **2 — Autorizzazione e perimetro** | opzione `owners` (lista, sul modello di `apprise_urls`, non `bashio::config`); perimetro sull'agente (ambito azione, tetto tier, budget, scadenza); **nuovo store per le concessioni** (`agente, verbo, entità`) — lo store step-up attuale è monouso con TTL 5 min e **una sola OTP viva per utente**, quindi non può ospitare un "Sempre"; richiesta cumulativa come **un solo** pending con N azioni (per non violare quell'invariante); sezione «Cosa gli hai permesso» + revoca | sì |
| **3 — Modalità obiettivo** | il **percorso separato** di ragionamento con tool di sola lettura (lista chiusa nel codice). **Non** è un ramo di `_llm_reason`: le invarianti complementari (`decision.action = suggested`, `force_notify_only`) esistono proprio perché l'output del modello non è mai fidato per le azioni. Loop legge→valuta→emette task→osserva; budget/scadenza/richiesta all'80%/resoconto | sì |
| **4 — Ciclo di miglioramento** | Brain propone agenti (il ponte esiste già); regola che invoca agente-obiettivo; agente ripetuto che propone di diventare regola; poi **tag v1.1** | sì |

## Copertura (self-review)

- `mode` nello schema, default a fiuto → Task 1 ✓
- `action` condizionale (il blocco più duro) → Task 2 ✓
- `objective` + gate incrociato mode/trigger → Task 3 ✓
- Rename Task + **i due contratti wire scoperti dal grounding** → Task 4 ✓
- Guardia FE che collide con la direzione v1.1 → Task 5 ✓
- Test mancante sullo shim retro-compat di `_load` → Task 4 Step 7 ✓
- Comportamento invariato / nessuna rottura utente → Global Constraints + verifica finale ✓
- Sicurezza non toccata (semaforo, `allowed_tools`, runner) → Global Constraints ✓
