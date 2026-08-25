# SP-4 Fase B — Piano A: bonifica (bug live + backlog)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere quattro bug **silenziosi** già in produzione + il backlog di igiene, per costruire la cornice unificata (Piano B) su terreno pulito.

**Architecture:** Tutti e quattro i bug sono la stessa famiglia — **disallineamento silenzioso di forma fra front-end e back-end**, che degrada a "lista vuota" invece che a errore. La bonifica stabilisce **una sola forma canonica** per `/api/entities`, elimina i filtri su campi inesistenti, e allinea le etichette. Poi igiene: rename dei due moduli watcher, refresh dei doc.

**Tech Stack:** Python 3.11/3.12, aiohttp, pytest; vanilla JS (no bundler); MQTT (paho).

## Global Constraints

- **Target 1.0 — nessuna retrocompatibilità richiesta** (decisione utente 2026-07-28). Dove esistono due forme, si tiene **la nuova** e si elimina la vecchia. Non aggiungere shim.
- Non toccare le pagine sane e recenti: Brain home (`#/`), Models (`#/models`), Gateway, Storico. Il rifacimento dell'editor e delle card è il **Piano B**.
- **Behavior-preserving NON è un vincolo qui**: questi sono bug, il comportamento *deve* cambiare. Ma ogni cambiamento va coperto da un test che sarebbe fallito prima.
- Il front-end è validato da test pytest che leggono il JS come testo (**non esiste `node --check` in CI**) — usare `node --check` localmente come sanity.
- Suite completa verde dopo ogni task (baseline **1809**).
- Commit per task. Nessun merge/tag senza conferma esplicita utente.
- **WONTFIX confermati** (non toccare, già documentati come deferral deliberati): chiave on-disk `usage.json` `per_agent`; literal proposal-type `"hiris_agent"` (l'etichetta utente è già corretta). Entrambi sono persistiti su disco e invisibili all'utente: rinominarli non dà nulla e rischia perdita silenziosa di dati o righe orfane.

---

## Task 1: `/api/entities` — una sola forma canonica (chiude il bug più grave)

**Il bug:** esistono due implementazioni. `handlers_entities.filter_entities` (registrata su `/api/entities`) risponde `{"entities": [{entity_id, friendly_name, domain, device_class}]}` e onora `?domain=`/`?device_class=`. `handlers_chatbots.handle_list_entities` (**irraggiungibile**, mai registrata) risponde con un **array piatto** `[{id, name, state, domain}]` e onora `?q=`. Tre front-end la chiamano: `chatbot-editor.js:365` e `permessi.js:125` si aspettano l'array piatto (`items.length` su un oggetto → `undefined` → early-return → **il dropdown non appare mai**); `agentbot-route.js:160` si aspetta `data.entities` ma passa `?domain=`/`?device_class=` che l'handler registrato onora — però la sua datalist resta comunque vuota perché il filtro non combacia con ciò che serve.

**Files:**
- Modify: `hiris/app/api/handlers_entities.py` (unica forma canonica: aggiunge `?q=`)
- Modify: `hiris/app/api/handlers_chatbots.py` (elimina la copia irraggiungibile)
- Modify: `hiris/app/static/config/chatbot-editor.js`, `hiris/app/static/config/permessi.js`, `hiris/app/static/config/agentbot-route.js` (consumano la forma canonica)
- Test: `tests/test_handlers_entities.py` (o esistente), `tests/test_handlers_chatbots.py` (sposta/rimuove i 5 test della copia morta)

**Interfaces:**
- Produces: `GET /api/entities` → **sempre** `{"entities": [{entity_id, friendly_name, domain, device_class, state}]}`; query supportate: `?q=` (substring case-insensitive su entity_id/friendly_name), `?domain=` (CSV), `?device_class=` (CSV), cap 1000. È la forma che il Piano B riuserà per il picker istanziabile.

- [ ] **Step 1: Test che fallisce (backend `q`)**

```python
# tests/test_handlers_entities.py  (aggiungi)
import pytest
from aiohttp import web
from hiris.app.api.handlers_entities import handle_list_entities


class _Cache:
    def all_states(self):
        return [
            {"id": "light.salotto", "name": "Luce Salotto", "state": "on",
             "domain": "light", "device_class": None},
            {"id": "sensor.porta_bat", "name": "Batteria Porta", "state": "80",
             "domain": "sensor", "device_class": "battery"},
        ]


def _app():
    app = web.Application()
    app["entity_cache"] = _Cache()
    app.router.add_get("/api/entities", handle_list_entities)
    return app


@pytest.mark.asyncio
async def test_q_filters_by_id_and_name(aiohttp_client):
    client = await aiohttp_client(_app())
    r = await client.get("/api/entities?q=salotto")
    body = await r.json()
    ids = [e["entity_id"] for e in body["entities"]]
    assert ids == ["light.salotto"]

    r2 = await client.get("/api/entities?q=BATTERIA")   # case-insensitive, su friendly_name
    assert [e["entity_id"] for e in (await r2.json())["entities"]] == ["sensor.porta_bat"]


@pytest.mark.asyncio
async def test_shape_is_always_wrapped_with_entities_key(aiohttp_client):
    client = await aiohttp_client(_app())
    body = await (await client.get("/api/entities")).json()
    assert isinstance(body, dict) and "entities" in body
    e = body["entities"][0]
    assert {"entity_id", "friendly_name", "domain"} <= set(e)


@pytest.mark.asyncio
async def test_q_combines_with_domain(aiohttp_client):
    client = await aiohttp_client(_app())
    body = await (await client.get("/api/entities?q=a&domain=sensor")).json()
    assert [e["entity_id"] for e in body["entities"]] == ["sensor.porta_bat"]
```

- [ ] **Step 2: Verifica che fallisca**

Run: `pytest tests/test_handlers_entities.py -v`
Expected: FAIL sui test `q` (il filtro non esiste).

- [ ] **Step 3: Implementa `q` nella forma canonica**

In `hiris/app/api/handlers_entities.py`, estendi `filter_entities`/`handle_list_entities` per accettare `q` oltre a `domain`/`device_class` (leggi il file: mantieni il cap 1000 e le chiavi esistenti, aggiungi `state` se non c'è già):

```python
def filter_entities(states, domain=None, device_class=None, q=None, limit=1000):
    """Filtra l'inventario entità. `q` = substring case-insensitive su id/nome."""
    out = []
    q_low = (q or "").strip().lower()[:100] or None
    doms = {d.strip() for d in domain.split(",")} if domain else None
    dcs = {d.strip() for d in device_class.split(",")} if device_class else None
    for e in states or []:
        eid = e.get("id") or e.get("entity_id") or ""
        name = e.get("name") or ""
        if doms and (e.get("domain") or eid.split(".", 1)[0]) not in doms:
            continue
        if dcs and e.get("device_class") not in dcs:
            continue
        if q_low and q_low not in eid.lower() and q_low not in name.lower():
            continue
        out.append({
            "entity_id": eid,
            "friendly_name": name,
            "domain": e.get("domain") or (eid.split(".", 1)[0] if "." in eid else ""),
            "device_class": e.get("device_class"),
            "state": e.get("state"),
        })
        if len(out) >= limit:
            break
    return out
```
e nell'handler leggi `request.rel_url.query.get("q")` passandolo a `filter_entities`.

- [ ] **Step 4: Elimina la copia irraggiungibile**

Rimuovi `handle_list_entities` da `hiris/app/api/handlers_chatbots.py` (è morta: `server.py` importa quella di `handlers_entities`). Sposta i suoi 5 test da `tests/test_handlers_chatbots.py` su `tests/test_handlers_entities.py` **riscrivendoli sulla forma canonica** (erano verdi su codice irraggiungibile: davano falsa sicurezza).

- [ ] **Step 5: Allinea i 3 chiamanti FE alla forma canonica**

In `chatbot-editor.js` (~riga 365) e `permessi.js` (~riga 125), il pattern attuale è:
```javascript
        .then(function(items) {
          sg.innerHTML = '';
          if (!items.length) { sg.style.display = 'none'; return; }
          items.slice(0, 20).forEach(function(item) {
            ... escHtml(item.id) ... escHtml(nm) ...
```
diventa:
```javascript
        .then(function(data) {
          var items = (data && data.entities) || [];
          sg.innerHTML = '';
          if (!items.length) { sg.style.display = 'none'; return; }
          items.slice(0, 20).forEach(function(item) {
            ... escHtml(item.entity_id) ... escHtml(item.friendly_name || '') ...
```
(adatta ai nomi reali delle variabili nei due file — leggili prima). In `agentbot-route.js` (~riga 160) `entityField` legge già `data.entities`/`e.entity_id`/`e.friendly_name`: verifica che ora si popoli davvero e che i suoi filtri (`domain=`, `device_class=`) combacino con l'handler canonico.

- [ ] **Step 6: Test di wiring FE (la rete che mancava)**

```python
# tests/test_entities_frontend_wiring.py  (aggiorna/aggiungi)
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_entity_search_consumers_read_canonical_shape():
    """I consumatori devono leggere data.entities/entity_id, non un array piatto."""
    for fname in ("config/chatbot-editor.js", "config/permessi.js", "config/agentbot-route.js"):
        js = (BASE / fname).read_text(encoding="utf-8")
        if "api/entities" not in js:
            continue
        assert "entities" in js, f"{fname} non legge data.entities"
        assert "entity_id" in js, f"{fname} non legge entity_id"
```

- [ ] **Step 7: Verifica**

Run: `pytest tests/test_handlers_entities.py tests/test_entities_frontend_wiring.py tests/test_handlers_chatbots.py -v` poi `pytest -q --maxfail=10`
Expected: verde. Poi `node --check` sui 3 JS toccati.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "fix(entities): una sola forma canonica per /api/entities (+q) — ripristina la ricerca entità in editor e permessi"
```

---

## Task 2: liste Chatbot sempre vuote (`type === 'chat'`)

**Il bug:** `index.html:297` e `hiris-chat-card.js:1254` filtrano i chatbot con `a.type === 'chat'`, ma lo Slice 5 ha eliminato il campo `type` — ogni persona **è** un chatbot. Risultato: la lista in `index.html` e il **selettore di chatbot nell'editor della card Lovelace** sono sempre vuoti (e mostrano lo stato "nessun chatbot", non un errore).

**Files:**
- Modify: `hiris/app/static/index.html`, `hiris/app/static/hiris-chat-card.js`
- Test: `tests/test_fe_rename_regression.py` (o nuovo wiring test)

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_chatbot_list_filter.py
from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_no_filter_on_nonexistent_type_field():
    """Chatbot non ha piu' il campo `type` (Slice 5): filtrarci svuota le liste."""
    for fname in ("index.html", "hiris-chat-card.js"):
        js = (BASE / fname).read_text(encoding="utf-8")
        assert "type === 'chat'" not in js, f"{fname} filtra su un campo inesistente"
        assert 'type === "chat"' not in js, f"{fname} filtra su un campo inesistente"
```

- [ ] **Step 2: Verifica che fallisca** — `pytest tests/test_chatbot_list_filter.py -v` → FAIL (2 occorrenze).

- [ ] **Step 3: Rimuovi i filtri**

`index.html:297`: `var chatAgents = agents.filter(function(a) { return a.type === 'chat'; });` → usa direttamente la lista (`var chatAgents = agents;`), adattando il nome variabile al contesto reale.
`hiris-chat-card.js:1254`: `this._chatbots = Array.isArray(result) ? result.filter(a => a.type === 'chat') : [];` → `this._chatbots = Array.isArray(result) ? result : [];`

Nota: NON filtrare su `enabled` — la sidebar di config mostra volutamente anche i disabilitati con il pallino grigio.

- [ ] **Step 4: Verifica** — `pytest tests/test_chatbot_list_filter.py -v` poi `pytest -q --maxfail=10`; `node --check hiris/app/static/hiris-chat-card.js`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(chatbot): rimuove il filtro su type inesistente — liste e selettore card non piu' vuoti"
```

---

## Task 3: MQTT — entità comando orfane + marker da rigenerare

**Il bug:** `cleanup_legacy_discovery` ritira i topic discovery **sensor** vecchi (`homeassistant/sensor/hiris_<id>_<metric>/config`) e i vecchi state topic, ma NON le entità **comando** con schema vecchio: `homeassistant/switch/hiris_<id>_enabled/config` e `homeassistant/button/hiris_<id>_run_now/config` (le ritira solo `publish_discovery`, e col nome NUOVO). Restano due entità morte per chatbot in HA. **Complicazione:** chi ha già avviato la 0.102.0 ha il marker `.mqtt_discovery_migrated` scritto → la nuova pulizia non girerebbe. Serve un marker **versionato**.

**Files:**
- Modify: `hiris/app/mqtt_publisher.py`, `hiris/app/server.py`
- Test: `tests/test_mqtt_publisher.py`

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_mqtt_publisher.py  (aggiungi)
@pytest.mark.asyncio
async def test_cleanup_retracts_legacy_command_entities(tmp_path):
    """Le vecchie switch/button (schema hiris_<id>_*) devono essere ritirate."""
    pub = _make_publisher()          # usa l'helper esistente nel file
    await pub.cleanup_legacy_discovery(["cb1"], pub._DISCOVERY_METRICS)
    topics = _drain_topics(pub)      # helper esistente: raccoglie (topic, payload) da _pending
    assert "homeassistant/switch/hiris_cb1_enabled/config" in topics
    assert "homeassistant/button/hiris_cb1_run_now/config" in topics
    for t, payload in topics.items():
        if t.endswith("/config"):
            assert payload == "", "il ritiro deve essere un payload vuoto retained"
```
(adatta agli helper realmente presenti nel file di test; leggilo prima.)

- [ ] **Step 2: Verifica che fallisca** — FAIL: i topic switch/button non ci sono.

- [ ] **Step 3: Ritira anche le entità comando**

In `cleanup_legacy_discovery`, dopo il loop sui metric, aggiungi:

```python
        for metric, component in self._RETIRED_COMMAND_ENTITIES:
            topic = f"{_DISCOVERY_PREFIX}/{component}/{self._OLD_ID_FMT.format(id=cid)}_{metric}/config"
            await self._pending.put((topic, ""))
```
(usa i nomi reali degli attributi: leggi il file.)

- [ ] **Step 4: Marker versionato**

In `server.py`, il marker `.mqtt_discovery_migrated` diventa versionato — es. `.mqtt_discovery_migrated_v2` — così l'utente che ha già avviato la 0.102.0 esegue comunque la nuova pulizia. Mantieni la logica introdotta prima (scrivi il marker **solo** dopo `wait_drained()` riuscito; se fallisce, log e ritenta al boot successivo).

- [ ] **Step 5: Verifica** — `pytest tests/test_mqtt_publisher.py -v` poi `pytest -q --maxfail=10`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "fix(mqtt): ritira anche switch/button vecchio schema + marker versionato v2"
```

---

## Task 4: home del Brain — etichetta proposta errata + severità advisory

**I bug:** (a) `dashboard.js:228` etichetta **ogni** proposta come `'→ automazione HA'` ignorando `p.type`: una proposta Agentbot viene mostrata come automazione HA (`proposals.js:28-32` lo fa correttamente con `TYPE_LABELS`). (b) `dashboard.js` non legge mai `a.severity`: una segnalazione `high` è visivamente identica a una `info`. (c) advisory e proposte condividono la classe `.prop-card` — va separata ora che le advisory prendono uno stile per severità.

**Files:**
- Modify: `hiris/app/static/config/dashboard.js`, `hiris/app/static/hiris-config.css`
- Test: `tests/test_brain_frontend_wiring.py`

- [ ] **Step 1: Test che fallisce**

```python
# tests/test_brain_frontend_wiring.py  (aggiungi)
def test_dashboard_renders_advisory_severity_and_real_proposal_type():
    js = (BASE / "config" / "dashboard.js").read_text(encoding="utf-8")
    assert "severity" in js, "la home non distingue le segnalazioni per gravita'"
    assert "adv-card" in js, "le advisory devono avere una classe propria (non .prop-card)"
    assert "automazione HA" not in js or "TYPE_LABELS" in js or "p.type" in js, \
        "l'etichetta della proposta non deve essere hardcodata"
```

- [ ] **Step 2: Verifica che fallisca.**

- [ ] **Step 3: Implementa**

In `dashboard.js`: (a) sostituisci l'etichetta hardcodata con una mappa per tipo, allineata a `proposals.js`:
```javascript
  var PROPOSAL_LABELS = {
    ha_automation: '→ automazione HA',
    ha_dashboard: '→ dashboard HA',
    ha_script: '→ script HA',
    ha_scene: '→ scena HA',
    hiris_agent: '→ Agentbot'
  };
  // uso: PROPOSAL_LABELS[p.type] || ('→ ' + escHtml(p.type || ''))
```
(b) rendi visibile la severità e dai alle advisory una classe propria:
```javascript
        return '<div class="adv-card adv-' + escHtml(a.severity || 'info') + '" id="adv-' + escHtml(String(a.id)) + '">' +
          '<div class="adv-sev">' + escHtml((a.severity || 'info').toUpperCase()) + '</div>' +
          '<div class="adv-title">' + escHtml(a.title || '') + '</div>' +
```
In `hiris-config.css` aggiungi `.adv-card` (che può ereditare il look di `.prop-card`) + un bordo/chip per `.adv-info`, `.adv-warn`, `.adv-high` usando le variabili tema esistenti.

- [ ] **Step 4: Verifica** — test mirato, poi `pytest -q --maxfail=10`, poi `node --check hiris/app/static/config/dashboard.js`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(brain-home): etichetta proposta per tipo reale + severita' visibile sulle segnalazioni"
```

---

## Task 5: rename moduli watcher + refresh documentazione

**Il debito:** `hiris/app/watcher/lenses.py` e `lens_runner.py` contengono ormai **solo** simboli Agentbot (`validate_agentbot`, `load_agentbots`, `run_agentbot`, …): i nomi file contraddicono il contenuto. E i doc di architettura sono **fattualmente sbagliati**, non solo stantii.

**Files:**
- Rename: `hiris/app/watcher/lenses.py`→`agentbots.py`, `hiris/app/watcher/lens_runner.py`→`agentbot_runner.py`
- Modify (8 import): `hiris/app/api/handlers_agentbots.py:37`, `hiris/app/server.py:65,70,1476,1569`, `tests/test_agentbots_api.py:30`, `tests/test_run_agentbot.py:25`, `tests/test_scheduled_agentbots.py:37`, `tests/test_user_agentbots_store.py:3`
- Modify (docs): `docs/architettura.md`, `docs/architecture.md`, `docs/come-funziona.md`, `docs/how-it-works.md`

- [ ] **Step 1: Rename moduli**

```bash
git mv hiris/app/watcher/lenses.py hiris/app/watcher/agentbots.py
git mv hiris/app/watcher/lens_runner.py hiris/app/watcher/agentbot_runner.py
```
Aggiorna gli 8 import + i riferimenti in prosa/docstring (`detectors.py`, `guardian.py`, `server.py`). **NON rinominare** la costante `_LEGACY_PATH = "sentinel_lenses.json"` (è la sorgente della migrazione su disco). Nessun rischio di collisione: non esiste altro `agentbots.py` (quello in `api/` è `handlers_agentbots.py`, package diverso).

- [ ] **Step 2: Verifica rename** — `pytest -q --maxfail=10` verde; grep `grep -rn "watcher.lenses\|watcher import lenses\|lens_runner" hiris/ tests/` → zero.

- [ ] **Step 3: Correggi i doc di architettura** (IT+EN, mantenerli speculari)

In `docs/architettura.md` e `docs/architecture.md`:
- **rimuovi `routes.py`** dalla mappa moduli: non esiste (le route sono inline in `server.py`).
- **`brain/`**: elencare i moduli reali (oggi ne compare 1 su 21) — almeno `knowledge_store, advisory_store, reasoning_log, health_scan, health_checks, feed, cognitive_loop, briefing, suggestions, coverage_review, brain_trace, reasoner_memory, memory_migration, history_digest, mayan_ingest, privacy`.
- **`api/`**: elencare gli handler reali (oggi 9 su 21) — aggiungere almeno `handlers_brain, handlers_entities, handlers_agentbots, handlers_reasoning, handlers_suggestions, handlers_knowledge, handlers_gateway_pending, handlers_gateway_policy, handlers_history_policy, handlers_config, handlers_execute, handlers_sentinel, handlers_tasks, middleware_csrf, middleware_internal_auth`.
- **`static/`**: non sono "due file HTML" ma una SPA a moduli sotto `static/config/`.
- **Data store**: aggiungere `advisory.db` e la tabella `brain_reasoning`.
- Aggiungere una **tabella delle route FE** reali: `#/`, `#/chatbots`, `#/chatbots/new`, `#/chatbots/{id}`, `#/agentbots`, `#/models`, `#/proposals`, `#/usage`, `#/tasks`, `#/gateway`, `#/history`.
- Aggiornare i nomi moduli watcher rinominati allo Step 1.

In `docs/come-funziona.md` e `docs/how-it-works.md` (già buoni sulla Brain home): aggiungere una sezione sul **layer Modelli / `#/models`** (SP-2) e nominare `feed` e `health_scan` dove si descrive la home del Brain.

- [ ] **Step 4: Verifica** — `pytest -q --maxfail=10` verde.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(watcher): lenses->agentbots, lens_runner->agentbot_runner + doc architettura allineati al reale"
```

---

## Verifica finale & handoff (conferma utente prima di merge)

- [ ] `pytest -q` verde (atteso ≥1809 + i nuovi test).
- [ ] Review indipendente whole-branch: i 4 bug chiusi hanno ciascuno un test che sarebbe fallito prima; nessuna regressione sulle pagine non toccate.
- [ ] **Live-verify utente:** nell'editor Chatbot la ricerca entità mostra suggerimenti; il selettore chatbot nell'editor della card Lovelace non è più vuoto; su HA non restano switch/button HIRIS morti; nella home del Brain le segnalazioni mostrano la gravità e le proposte l'etichetta giusta.
- [ ] Conferma esplicita → merge; il bump versione va **insieme al Piano B** (unico rilascio verso 1.0) salvo diversa indicazione.

## Copertura (self-review)

- Bug ricerca entità (2 superfici) → Task 1 ✓ · Liste chatbot vuote (2 superfici) → Task 2 ✓ · Datalist Agentbot → Task 1 Step 5 ✓ · Etichetta proposta → Task 4 ✓
- Entità MQTT orfane + marker → Task 3 ✓ · Severità advisory + classe CSS → Task 4 ✓
- Rename moduli watcher → Task 5 ✓ · Doc architettura fattualmente errati → Task 5 ✓
- WONTFIX (`per_agent`, `hiris_agent`) → Global Constraints ✓
- `AdvisoryStore` senza prune → **no-action**: la tabella è strutturalmente limitata da `source_ref UNIQUE` (le righe si riaprono, non si duplicano). Da confermare in Task 4 con un'occhiata a `health_checks.py`: nessun `source_ref` deve contenere timestamp o valori ad alta cardinalità.
