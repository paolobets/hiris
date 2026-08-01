# Visione e salute del sistema — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dare a HIRIS una visione completa dello stato di casa e sistema — esponendo alla chat ciò che il Brain già sa, e aggiungendo le fonti che oggi non legge affatto (system_health, Supervisor, logbook, template) — tutto in sola lettura, con segnalazione e notifica per le sole condizioni gravi.

**Architecture:** I dati periodici costosi entrano come nuove sezioni del `HealthMonitor` esistente (cache + refresh ogni 30 min), così il tool che le legge non tocca mai Home Assistant. I dati parametrici (logbook, template) sono tool a sé. Gli advisory del Brain, oggi visibili solo nella dashboard, ottengono un tool di lettura che chiude anche una duplicazione della logica batterie.

**Tech Stack:** Python 3.11+ / aiohttp / pytest + pytest-asyncio (backend); JS in IIFE + `node --test` con jsdom (frontend).

**Design doc:** `docs/design/2026-08-01-design-visione-salute-sistema.md`

## Global Constraints

- **LINEA ROSSA — sola lettura.** Nessun tool, metodo o handler introdotto da questo piano può fermare, avviare, riavviare o aggiornare add-on, Supervisor, core o sistema operativo. Nessuna proposta di aggiornamento. Se un task sembra richiederlo, fermati e chiedi.
- **Nessun tool nuovo deve colpire Home Assistant a ogni domanda dell'LLM.** I dati periodici passano da `HealthMonitor` (job ogni 30 min). Solo `get_logbook` e `render_template` chiamano HA su richiesta, perché sono parametrici.
- **Cap espliciti.** Ogni sezione dello snapshot e ogni tool di lettura ha un limite dichiarato come costante in cima al file, e dichiara quando ha troncato.
- **Degrado silenzioso.** Ogni fonte esterna che fallisce (Supervisor assente, WS non disponibile, endpoint 404) vale come "dato non disponibile": si logga e si prosegue. HIRIS deve funzionare su installazioni senza Supervisor.
- **Mai `raise` verso il chiamante** dai tool: si ritorna `{"error": "..."}`. Mai fare echo di `str(exc)` al chiamante; i log server-side possono portare lo stacktrace.
- **Commenti, docstring, descrizioni dei tool e testi UI in italiano. Nessun emoji.**
- **Test sempre con `tmp_path`**, mai percorsi di default: in questo repo un test che scriveva su un data_dir di default ha realmente sovrascritto file sotto `C:\data`.
- **Suite:** `python -m pytest -q` impiega oltre 3 minuti — usarla solo nell'ultimo task. Nei task usare selezioni mirate. `npm test` è veloce (~14s).
- **Baseline:** pytest 2110 passed, npm 98/98.

---

## File Structure

| File | Responsabilità | Azione |
|---|---|---|
| `hiris/app/proxy/supervisor_client.py` | client Supervisor, sola lettura | **Create** |
| `hiris/app/proxy/ha_client.py` | +`get_system_health`, +`get_logbook`, +`render_template` | Modify |
| `hiris/app/proxy/health_monitor.py` | +2 sezioni, +cap su tutte | Modify |
| `hiris/app/tools/health_tools.py` | enum sezioni esteso | Modify |
| `hiris/app/tools/advisory_tools.py` | tool di lettura advisory | **Create** |
| `hiris/app/tools/diagnostics_tools.py` | `get_logbook` + `render_template` | **Create** |
| `hiris/app/brain/health_checks.py` | +3 controlli di sistema | Modify |
| `hiris/app/brain/health_scan.py` | wiring dei nuovi controlli + notifica | Modify |
| `hiris/app/brain/advisory_store.py` | `reconcile` riporta *quali* sono nuovi | Modify |
| `hiris/app/brain/briefing.py` | legge gli advisory invece di ricalcolare le batterie | Modify |
| `hiris/app/tools/dispatcher.py`, `claude_runner.py`, `server.py` | registrazione e wiring | Modify |
| `hiris/app/static/config/templates.js` | catalogo tool allineato | Modify |

---

## Task 1: `SupervisorClient` — lettura dello stato di sistema

**Files:**
- Create: `hiris/app/proxy/supervisor_client.py`
- Test: `tests/test_supervisor_client.py` (create)

**Interfaces:**
- Produces:
  - `SupervisorClient(token: str, base_url: str = "http://supervisor")`
  - `async start() -> None` / `async stop() -> None`
  - `async get_addons() -> list[dict]` — `[{slug, name, state, version, update_available}]`, `[]` se non disponibile
  - `async get_host_info() -> dict` — `{disk_total, disk_used, disk_free}` (GB), `{}` se non disponibile
  - `async get_available_updates() -> list[dict]` — `[{name, update_type, version_latest}]`, `[]` se non disponibile

Endpoint verificati sulla documentazione ufficiale: `GET /addons`, `GET /host/info`, `GET /available_updates`. Autenticazione: header `Authorization: Bearer <SUPERVISOR_TOKEN>`. Le risposte del Supervisor hanno forma `{"result": "ok", "data": {...}}`: i dati stanno sotto `data`.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_supervisor_client.py`:

```python
import pytest
from hiris.app.proxy.supervisor_client import SupervisorClient


class FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Registra le GET e risponde con code preimpostate per path."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.headers_seen = []

    def get(self, url, **kw):
        self.calls.append(url)
        self.headers_seen.append(kw.get("headers") or {})
        for path, resp in self.routes.items():
            if url.endswith(path):
                return resp
        return FakeResp(404, {})


def _client(session):
    c = SupervisorClient.__new__(SupervisorClient)
    c._token = "tok"
    c._base = "http://supervisor"
    c._session = session
    return c


@pytest.mark.asyncio
async def test_get_addons_estrae_i_campi_utili():
    session = FakeSession({"/addons": FakeResp(200, {"result": "ok", "data": {"addons": [
        {"slug": "core_mosquitto", "name": "Mosquitto", "state": "started",
         "version": "6.4", "update_available": False, "irrilevante": 1},
    ]}})})
    out = await _client(session).get_addons()
    assert out == [{"slug": "core_mosquitto", "name": "Mosquitto", "state": "started",
                    "version": "6.4", "update_available": False}]


@pytest.mark.asyncio
async def test_autenticazione_bearer():
    session = FakeSession({"/addons": FakeResp(200, {"data": {"addons": []}})})
    await _client(session).get_addons()
    assert session.headers_seen[0]["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_get_host_info_riporta_lo_spazio_disco():
    session = FakeSession({"/host/info": FakeResp(200, {"data": {
        "disk_total": 32.0, "disk_used": 20.0, "disk_free": 12.0, "altro": "x"}})})
    out = await _client(session).get_host_info()
    assert out == {"disk_total": 32.0, "disk_used": 20.0, "disk_free": 12.0}


@pytest.mark.asyncio
async def test_get_available_updates():
    session = FakeSession({"/available_updates": FakeResp(200, {"data": {"available_updates": [
        {"name": "Home Assistant Core", "update_type": "core", "version_latest": "2026.8.0"},
    ]}})})
    out = await _client(session).get_available_updates()
    assert out == [{"name": "Home Assistant Core", "update_type": "core",
                    "version_latest": "2026.8.0"}]


@pytest.mark.asyncio
async def test_supervisor_non_disponibile_degrada_a_vuoto():
    """Installazione senza Supervisor: 404 su tutto, nessuna eccezione."""
    client = _client(FakeSession({}))
    assert await client.get_addons() == []
    assert await client.get_host_info() == {}
    assert await client.get_available_updates() == []


@pytest.mark.asyncio
async def test_errore_di_rete_degrada_a_vuoto():
    class BoomSession:
        def get(self, url, **kw):
            raise OSError("connessione rifiutata")
    assert await _client(BoomSession()).get_addons() == []


@pytest.mark.asyncio
async def test_payload_malformato_degrada_a_vuoto():
    session = FakeSession({"/addons": FakeResp(200, {"data": "non-un-dict"})})
    assert await _client(session).get_addons() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_supervisor_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hiris.app.proxy.supervisor_client'`

- [ ] **Step 3: Write minimal implementation**

Crea `hiris/app/proxy/supervisor_client.py`. Requisiti:
- costruttore `(token, base_url="http://supervisor")`, `start()` crea `aiohttp.ClientSession()`, `stop()` la chiude;
- un helper privato `_get(path) -> dict` che fa la GET con l'header Bearer, timeout esplicito (10s), e ritorna il contenuto di `data` come dict; **qualunque** problema (status != 200, JSON non valido, `data` non dict, eccezione di rete) → `{}` con `logger.debug`, mai un'eccezione verso il chiamante;
- i tre metodi pubblici costruiscono la loro risposta prendendo **solo** i campi elencati nelle Interfaces, ignorando il resto (il Supervisor restituisce payload molto ampi: non vanno propagati);
- **nessun metodo di scrittura**: niente POST, niente restart, niente update. È la linea rossa del piano.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_supervisor_client.py -v`
Expected: PASS (7 test)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/supervisor_client.py tests/test_supervisor_client.py
git commit -m "feat(supervisor): client di sola lettura per addon, disco e aggiornamenti"
```

---

## Task 2: `ha_client` — system_health, logbook, template

**Files:**
- Modify: `hiris/app/proxy/ha_client.py`
- Test: `tests/test_ha_client_diagnostics.py` (create)

**Interfaces:**
- Produces:
  - `async get_system_health() -> dict` — WS `system_health/info`; mappa dominio → dict di informazioni; `{}` se non disponibile.
  - `async get_logbook(entity_id: str | None, hours: int) -> list[dict]` — GET `/api/logbook/<ISO start>` con `entity=` e `end_time=`; voci `{when, name, message, entity_id}`; `[]` se non disponibile.
  - `async render_template(template: str) -> dict` — POST `/api/template`; `{"result": "<testo>"}` oppure `{"error": "..."}`.

Endpoint verificati sulla documentazione ufficiale. `/api/template` risponde **testo semplice, non JSON**. Il formato di `system_health/info` non è documentato in dettaglio: leggerlo in modo difensivo, esponendo ciò che si riconosce e ignorando il resto.

Usa le primitive già presenti: `_ws_request(msg_type, extra, timeout)` per il WebSocket, `self._session`/`self._headers` per REST (guarda `get_error_log` a `ha_client.py:333` come modello di gestione dei fallimenti).

- [ ] **Step 1: Write the failing test**

Crea `tests/test_ha_client_diagnostics.py` con i casi:
- `get_system_health` ritorna la mappa dominio→info quando il WS risponde; `{}` quando il WS fallisce o ritorna una forma inattesa.
- `get_logbook` costruisce l'URL con il timestamp di inizio corretto rispetto a `hours` e include `entity=` **solo** quando `entity_id` è passato; estrae i quattro campi; `[]` su status != 200 o payload non-lista.
- `render_template` fa POST con body `{"template": ...}` e ritorna il testo; su errore HTTP ritorna `{"error": ...}` **senza** propagare il corpo grezzo della risposta se contiene un traceback (HA restituisce il messaggio di errore del template: va troncato a un limite dichiarato).

Segui lo stile di `tests/test_ha_client_config.py` per il fake della sessione e l'asserzione sull'URL esatto chiamato.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ha_client_diagnostics.py -v`
Expected: FAIL — `AttributeError: 'HAClient' object has no attribute 'get_system_health'`

- [ ] **Step 3: Write minimal implementation**

Aggiungi i tre metodi in `hiris/app/proxy/ha_client.py`, accanto a `get_error_log`. Costanti in cima al file per: numero massimo di voci di logbook restituite, lunghezza massima del template accettato, lunghezza massima della risposta del template.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ha_client_diagnostics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_ha_client_diagnostics.py
git commit -m "feat(ha): system_health, logbook e render template"
```

---

## Task 3: `HealthMonitor` — due sezioni nuove e cap su tutte

**Files:**
- Modify: `hiris/app/proxy/health_monitor.py`
- Modify: `hiris/app/tools/health_tools.py` (enum sezioni)
- Modify: `hiris/app/server.py` (iniezione del `SupervisorClient`)
- Test: `tests/test_health_monitor.py` (estendere)

**Interfaces:**
- Consumes: `SupervisorClient` (Task 1), `ha_client.get_system_health` (Task 2).
- Produces: `get_snapshot(["system_health"])` e `get_snapshot(["supervisor"])`; sezione `supervisor` = `{addons: [...], disk: {...}, updates: [...]}`.

`HealthMonitor.__init__` è a `health_monitor.py:24` e riceve `(ha_client, data_path, scheduler)`; `_snapshot_data` ha 6 chiavi a riga 28; `refresh()` a riga 79 fa 4 chiamate ognuna in `try/except`; `get_snapshot()` a riga 137 rinomina le chiavi in uscita. Istanziato in `server.py:1190-1196`.

- [ ] **Step 1: Write the failing test**

Estendi `tests/test_health_monitor.py` (segui lo stile esistente: `AsyncMock` per il client, `tmp_path` per la persistenza, `MagicMock()` per lo scheduler):
- dopo `refresh()` lo snapshot contiene `system_health` e `supervisor` popolati;
- **un fallimento del Supervisor non azzera le altre sezioni** (è il comportamento già garantito per le altre fonti: va esteso, non riscritto);
- `get_snapshot(["supervisor"])` ritorna solo quella sezione più `last_updated`;
- **cap**: con 50 entità non disponibili lo snapshot ne espone al massimo il limite dichiarato e riporta il totale reale (es. un campo che dice quante ce ne sono in tutto);
- il monitor funziona con `supervisor_client=None` (installazione senza Supervisor): nessuna eccezione, sezione assente o vuota.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_health_monitor.py -v`
Expected: FAIL sui test nuovi.

- [ ] **Step 3: Write minimal implementation**

- `HealthMonitor.__init__` accetta un `supervisor_client=None` opzionale (retro-compatibile: i test esistenti lo costruiscono senza).
- Due chiavi nuove in `_snapshot_data`, due blocchi `try/except` in `refresh()` sul modello dei quattro esistenti, due voci nella mappa di rinomina di `get_snapshot()`.
- **Cap**: costanti in cima al file (una per sezione). Il troncamento avviene alla lettura in `get_snapshot`, non alla scrittura, così il file su disco resta completo per la dashboard. Ogni sezione troncata dichiara il totale.
- `hiris/app/tools/health_tools.py`: aggiungi i due valori all'enum delle sezioni (riga ~24) e citali nella descrizione del tool.
- `server.py`: costruisci il `SupervisorClient` con `SUPERVISOR_TOKEN` (già letto a riga 1130) e passalo al `HealthMonitor`; avvialo e fermalo insieme agli altri client.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_health_monitor.py tests/test_health_tools.py -v`
Expected: PASS

- [ ] **Step 5: Verifica che l'app parta**

Run: `python -c "from hiris.app import server; print('import ok')"`
Expected: `import ok`

- [ ] **Step 6: Commit**

```bash
git add hiris/app/proxy/health_monitor.py hiris/app/tools/health_tools.py hiris/app/server.py tests/test_health_monitor.py
git commit -m "feat(health): sezioni system_health e supervisor nello snapshot, con cap"
```

---

## Task 4: Il ponte — gli advisory diventano visibili in chat

**Files:**
- Create: `hiris/app/tools/advisory_tools.py`
- Modify: `hiris/app/tools/dispatcher.py`, `hiris/app/claude_runner.py`, `hiris/app/server.py`
- Test: `tests/test_advisory_tools.py` (create), `tests/test_advisory_tool_registered.py` (create)

**Interfaces:**
- Consumes: `AdvisoryStore.list(status="open")` (`brain/advisory_store.py:119`).
- Produces: `GET_ADVISORIES_TOOL_DEF`, `get_advisories(advisory_store, severity=None) -> dict`.

`AdvisoryStore` è in `app["advisory_store"]` (creato in `server.py:1567-1571`). Il dispatcher riceve le dipendenze nel costruttore (`dispatcher.py:129`, assegnate a `:146`, iniettate da `server.py:1530`).

**Procedura completa di registrazione di un tool** (traccia verificata su `get_ha_health`): 1) tool def + funzione nel file del tool; 2) import in `claude_runner.py`; 3) voce in `ALL_TOOL_DEFS`; 4) voce in `EVALUATION_ONLY_TOOLS` **se** il tool è di sola lettura e deve essere usabile dagli agenti; 5) import + branch nel dispatcher; 6) parametro nel costruttore del dispatcher se serve una dipendenza; 7) voce nel catalogo `static/config/templates.js`; 8) `mcp/tiers.py` se va esposto al gateway; 9) `api/handlers_gateway_policy.py` `READ_TOOLS` se deve passare dall'execute-API.

Per **questo** tool: sì ai punti 1-7. `get_advisories` è di sola lettura e **deve** stare in `EVALUATION_ONLY_TOOLS` (un Agentbot che sorveglia la casa ha senso che veda i problemi noti). Punti 8-9: sì, è lettura pura.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_advisory_tools.py` sul modello di `tests/test_health_tools.py` (34 righe, quattro test: TOOL_DEF valido, pass-through degli argomenti, default, dipendenza assente → `{"error": ...}`). In più:
- il filtro per severità funziona;
- il numero di voci restituite è limitato dal cap dichiarato, e la risposta dice quante ce ne sono in tutto;
- ogni voce espone i campi utili all'LLM (titolo, severità, evidenza, rimedio suggerito) e **non** i dettagli interni dello store.

Crea `tests/test_advisory_tool_registered.py` sul modello di `tests/test_automation_config_registered.py` (5 righe): il nome è in `ALL_TOOL_DEFS` ed è presente in `EVALUATION_ONLY_TOOLS`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_advisory_tools.py tests/test_advisory_tool_registered.py -v`
Expected: FAIL — modulo inesistente.

- [ ] **Step 3: Write minimal implementation**

Crea `hiris/app/tools/advisory_tools.py` seguendo la convenzione di `health_tools.py`: costante `GET_ADVISORIES_TOOL_DEF` con `name`/`description`/`input_schema`, poi la funzione con lo stesso nome del tool, primo parametro la dipendenza. La funzione è **sincrona** (lo store è SQLite locale, come `get_ha_health` è sincrono sullo snapshot). Cap come costante in cima al file.

Poi i punti 2-7 della procedura di registrazione.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_advisory_tools.py tests/test_advisory_tool_registered.py -v`
Expected: PASS

- [ ] **Step 5: Non regressione**

Run: `python -m pytest tests/ -q -k "dispatcher or advisory or health"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/advisory_tools.py hiris/app/tools/dispatcher.py hiris/app/claude_runner.py hiris/app/server.py hiris/app/static/config/templates.js tests/test_advisory_tools.py tests/test_advisory_tool_registered.py
git commit -m "feat(brain): le segnalazioni del Brain sono leggibili dalla chat"
```

---

## Task 5: Tool di diagnosi — logbook e template

**Files:**
- Create: `hiris/app/tools/diagnostics_tools.py`
- Modify: `hiris/app/tools/dispatcher.py`, `hiris/app/claude_runner.py`, `hiris/app/static/config/templates.js`
- Test: `tests/test_diagnostics_tools.py` (create), `tests/test_dispatcher_diagnostics.py` (create)

**Interfaces:**
- Consumes: `ha_client.get_logbook`, `ha_client.render_template` (Task 2).
- Produces: `GET_LOGBOOK_TOOL_DEF`, `RENDER_TEMPLATE_TOOL_DEF`, e le funzioni corrispondenti.

**Decisione di sicurezza vincolante:** `get_logbook` va in `EVALUATION_ONLY_TOOLS` (lettura utile a un sorvegliante). `render_template` **NON** ci va: un template può leggere qualunque stato ed è un vettore di prompt injection per un agente reattivo che legge lo stato di HA. È chat-only. Il commento nel codice deve dire perché.

Se il tool riceve `entity_id` dall'LLM vanno replicati i controlli di visibilità già applicati altrove: guarda `tests/test_dispatcher_history.py`, che copre `allowed_entities` e `visible_entity_ids` — se `get_logbook` accetta un'entità, quei due test vanno replicati per esso.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_diagnostics_tools.py`: validazione degli input (ore fuori intervallo, entity_id malformato, template troppo lungo → errore senza chiamare HA), cap sul numero di voci, dipendenza assente. E `tests/test_dispatcher_diagnostics.py` sul modello di `tests/test_dispatcher_history.py`: il branch del dispatcher instrada correttamente e rispetta le whitelist di entità.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_diagnostics_tools.py tests/test_dispatcher_diagnostics.py -v`
Expected: FAIL — modulo inesistente.

- [ ] **Step 3: Write minimal implementation**

Crea il file con le due definizioni, le costanti di limite in cima (finestra massima in ore, numero massimo di voci, lunghezza massima del template) e una funzione di validazione separata e testabile, come fa `history_tools.py:38-47`. Poi registra entrambi i tool.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_diagnostics_tools.py tests/test_dispatcher_diagnostics.py -v`
Expected: PASS

- [ ] **Step 5: Verifica esplicita della decisione di sicurezza**

Run: `python -c "from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS as E; assert 'get_logbook' in E; assert 'render_template' not in E; print('gating ok')"`
Expected: `gating ok`

- [ ] **Step 6: Commit**

```bash
git add hiris/app/tools/diagnostics_tools.py hiris/app/tools/dispatcher.py hiris/app/claude_runner.py hiris/app/static/config/templates.js tests/test_diagnostics_tools.py tests/test_dispatcher_diagnostics.py
git commit -m "feat(diagnostica): logbook e valutazione template dalla chat"
```

---

## Task 6: Tre controlli di sistema nel Brain

**Files:**
- Modify: `hiris/app/brain/health_checks.py`
- Modify: `hiris/app/brain/health_scan.py`
- Modify: `hiris/app/server.py` (il job passa i dati Supervisor)
- Test: `tests/test_health_checks.py`, `tests/test_health_scan.py` (estendere)

**Interfaces:**
- Consumes: `SupervisorClient` (Task 1).
- Produces: `check_addon_down(addons)`, `check_disk_space(host_info)`, `check_updates_available(updates)` — stessa forma dei cinque esistenti: funzioni **pure**, nessun I/O, che ritornano dict con `{check_id, severity, title, evidence, suggested_fix, fix_kind, source_ref}`.

`CHECK_IDS` è a `health_checks.py:7` e va esteso: `health_scan.py:58` lo passa a `reconcile`, che lo usa per decidere quali segnalazioni auto-risolvere. Un `check_id` nuovo non incluso lì produrrebbe segnalazioni che non si chiudono mai da sole.

Severità: add-on fermo = `high`; disco sotto il 10% libero = `high`, sotto il 20% = `warn`; aggiornamenti = `info`. Soglie come costanti dichiarate.

- [ ] **Step 1: Write the failing test**

Estendi `tests/test_health_checks.py` seguendo lo stile esistente (tabelle di stati inline, asserzioni su `source_ref` e `severity`): un add-on `started` non produce nulla, uno `stopped`/`error` sì; il disco produce `high` sotto il 10%, `warn` sotto il 20%, nulla sopra; gli aggiornamenti producono una sola voce aggregata di severità `info`; input vuoti o malformati non sollevano.

Estendi `tests/test_health_scan.py`: i nuovi controlli entrano nei candidati; un Supervisor assente non rompe la scansione (il test "sopravvive all'errore di fetch" esiste già: estendilo).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_health_checks.py tests/test_health_scan.py -v`
Expected: FAIL sui test nuovi.

- [ ] **Step 3: Write minimal implementation**

Le tre funzioni in `health_checks.py`, l'estensione di `CHECK_IDS`, le tre righe di `candidates +=` in `health_scan.py` (righe 52-56), e il passaggio dei dati Supervisor dal job in `server.py:2255-2270`. Il fetch dei dati Supervisor dentro lo scan va in `try/except` come gli altri (righe 25-49).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_health_checks.py tests/test_health_scan.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/health_checks.py hiris/app/brain/health_scan.py hiris/app/server.py tests/test_health_checks.py tests/test_health_scan.py
git commit -m "feat(brain): controlli su addon, spazio disco e aggiornamenti"
```

---

## Task 7: Notifica per le sole segnalazioni gravi e nuove

**Files:**
- Modify: `hiris/app/brain/advisory_store.py` (`reconcile` riporta *quali*)
- Modify: `hiris/app/brain/health_scan.py` (invio)
- Modify: `hiris/config.yaml` (opzione di disattivazione)
- Test: `tests/test_advisory_store.py`, `tests/test_health_scan_notify.py` (create)

**Interfaces:**
- Consumes: `notify_tools.send_notification(ha, message, channel, config, *, title=None, notification_id=None) -> bool` (`tools/notify_tools.py:86`).
- Produces: `reconcile` ritorna, oltre ai contatori attuali, l'elenco delle segnalazioni **inserite** e **riaperte**.

**Vincolo che questo task esiste per garantire:** la scansione gira ogni 30 minuti, cioè 48 volte al giorno. Se la notifica partisse per ogni segnalazione *aperta* invece che per ogni segnalazione *nuova*, l'utente riceverebbe la stessa notifica 48 volte e disattiverebbe le notifiche, perdendo anche quelle utili. La notifica parte **solo** su inserimento o riapertura, e **solo** per severità alta.

**Stato attuale accertato:** `reconcile` (`advisory_store.py:53`) ritorna oggi **solo contatori** (`{"inserted": N, "updated": N, "reopened": N, "resolved": N}`), quindi il chiamante non sa *quali* segnalazioni siano nuove. Va esteso in modo retro-compatibile: le chiavi esistenti restano, se ne aggiungono di nuove con gli elenchi. `run_health_scan` (`health_scan.py:58`) ritorna direttamente l'esito di `reconcile`: chi lo consuma non deve rompersi.

- [ ] **Step 1: Write the failing test**

In `tests/test_advisory_store.py`: `reconcile` riporta le voci inserite e quelle riaperte, e i contatori esistenti restano invariati (retro-compatibilità).

Crea `tests/test_health_scan_notify.py`:
- una segnalazione **grave e nuova** fa partire una notifica, con il titolo della segnalazione nel messaggio;
- la **stessa** segnalazione a una scansione successiva (quindi solo aggiornata) **non** fa partire nulla — è il cuore del task;
- una segnalazione **riaperta** notifica di nuovo (il problema si è ripresentato: è un evento);
- una segnalazione di severità **non alta** non notifica;
- con l'opzione disattivata non parte nulla;
- un fallimento dell'invio non fa fallire la scansione.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_advisory_store.py tests/test_health_scan_notify.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- `reconcile`: accumula le voci inserite/riaperte mentre le processa e le riporta nel dizionario di ritorno.
- `run_health_scan`: dopo `reconcile`, se l'invio è abilitato, per ogni segnalazione grave nuova o riaperta invia una notifica riusando `send_notification`. L'invio è in `try/except`: la scansione non deve fallire per una notifica non partita.
- `hiris/config.yaml`: nuova opzione booleana per abilitare/disabilitare, con default **attivo** (l'utente ha scelto "segnala e notifica") e la voce corrispondente in `schema:`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_advisory_store.py tests/test_health_scan_notify.py tests/test_health_scan.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/advisory_store.py hiris/app/brain/health_scan.py hiris/config.yaml tests/
git commit -m "feat(brain): notifica solo per le segnalazioni gravi nuove o riaperte"
```

---

## Task 8: Il briefing smette di ricalcolare le batterie

**Files:**
- Modify: `hiris/app/brain/briefing.py`
- Test: `tests/test_daily_briefing_tool.py` (estendere)

**Interfaces:**
- Consumes: `AdvisoryStore.list(status="open")`.

La logica delle batterie oggi vive in due posti con soglie diverse: `brain/health_checks.py:46` (`check_low_battery`, soglia 15) e `brain/briefing.py:93-138` (`_collect_home_status`, soglia da `policy.detectors.battery.min_pct`). Questo task elimina la seconda: il briefing legge le segnalazioni già prodotte dal Brain.

**Attenzione a non cambiare comportamento visibile oltre il dovuto:** `_collect_home_status` calcola *due* cose, le aperture (`open_now`) e le batterie. Solo la seconda va sostituita; le aperture restano come sono.

- [ ] **Step 1: Write the failing test**

Estendi `tests/test_daily_briefing_tool.py`: il briefing riporta le batterie scariche **prese dalle segnalazioni** (con uno store che ne contiene una, il briefing la cita) e **non** interroga la cache delle entità per le batterie; le aperture continuano a funzionare come prima.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_daily_briefing_tool.py -v`
Expected: FAIL sui test nuovi.

- [ ] **Step 3: Write minimal implementation**

Sostituisci il calcolo delle batterie in `briefing.py` con la lettura degli advisory di tipo batteria. Se lo store non è disponibile, il briefing degrada a "nessuna batteria da segnalare" invece di ricalcolare: una sola fonte di verità, anche quando è vuota.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_daily_briefing_tool.py tests/test_health_checks.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/brain/briefing.py tests/test_daily_briefing_tool.py
git commit -m "refactor(brain): una sola fonte per le batterie scariche"
```

---

## Task 9: Il catalogo strumenti della UI torna vero

**Files:**
- Modify: `hiris/app/static/config/templates.js`
- Test: `tests/test_tools_catalog_sync.py` (create)

`templates.js` (righe ~61-78) elenca `search_entities`, che **non esiste in nessun file Python**, e omette molti tool reali (`get_ha_health`, `get_history`, `get_calendar_events`, `create_task`, …). Non esiste alcun test che tenga allineate le due liste, quindi il disallineamento è cresciuto in silenzio. Un Chatbot configurato con una whitelist esplicita non può selezionare i tool mancanti.

- [ ] **Step 1: Write the failing test**

Crea `tests/test_tools_catalog_sync.py`: estrae gli identificativi dal catalogo JS (lettura del file come testo ed estrazione con una regex sugli `id`) e verifica che **ogni id del catalogo esista** in `ALL_TOOL_DEFS`. Il test deve fallire subito, per via di `search_entities`.

Verifica anche il verso opposto — ogni tool di `ALL_TOOL_DEFS` è nel catalogo — ma se il divario è ampio, dichiara nel test una lista di eccezioni note **con un commento che spiega perché** ciascuna è esclusa (per esempio i tool interni che non ha senso spuntare). Una lista di eccezioni vuota è preferibile; una lista lunga e non commentata è un modo per far passare il test senza sistemare nulla.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools_catalog_sync.py -v`
Expected: FAIL — `search_entities` non esiste fra i tool.

- [ ] **Step 3: Write minimal implementation**

Correggi `templates.js`: rimuovi l'id inesistente, aggiungi i tool mancanti con `{id, label, desc}` nella forma già usata, in italiano.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tools_catalog_sync.py -v && npm test`
Expected: PASS entrambi (il catalogo è letto anche da `tests/js/chatbot-editor.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add hiris/app/static/config/templates.js tests/test_tools_catalog_sync.py
git commit -m "fix(ui): il catalogo strumenti riflette i tool reali, con test"
```

---

## Task 10: Documentazione, changelog e versione

**Files:**
- Modify: `CHANGELOG.md`, `hiris/config.yaml`, `docs/`

- [ ] **Step 1: Suite complete**

Run: `python -m pytest -q` (oltre 3 minuti) e `npm test`
Expected: entrambe verdi. Annota i totali. Baseline: pytest 2110, npm 98.

- [ ] **Step 2: Documentazione**

Run: `grep -rln "get_ha_health\|strumenti\|tool" docs/*.md | head`
Aggiorna i documenti che descrivono le capacità correnti (`docs/come-funziona.md`, `docs/how-it-works.md`, `docs/architettura.md` citano l'elenco dei tool). Non riscrivere le voci storiche del changelog né i design doc datati.

- [ ] **Step 3: Bump versione**

`hiris/config.yaml`: porta `version` a `"1.1.0-beta.13"`.

- [ ] **Step 4: Voce di changelog**

In cima a `CHANGELOG.md`, in italiano e rivolta all'utente finale: HIRIS ora sa rispondere su cosa non va in casa (le segnalazioni del Brain sono leggibili in chat), vede lo stato del sistema (add-on, spazio disco, aggiornamenti di core/OS/Supervisor/add-on, salute delle integrazioni), sa raccontare cosa è successo (logbook) e valutare una condizione al volo (template). Per i problemi gravi arriva una notifica, **una sola volta**, quando il problema compare. Dichiara che è tutto in sola lettura: HIRIS segnala, non aggiorna.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md hiris/config.yaml docs/
git commit -m "docs(release): 1.1.0-beta.13 — visione e salute del sistema"
```

---

## Verifica finale (prima della review di branch)

- [ ] `python -m pytest -q` verde
- [ ] `npm test` verde
- [ ] Nessun metodo di scrittura nel `SupervisorClient`: `grep -nE "post|put|delete|restart|update" hiris/app/proxy/supervisor_client.py` non trova chiamate HTTP di scrittura
- [ ] `render_template` NON è in `EVALUATION_ONLY_TOOLS`; `get_advisories` e `get_logbook` lo sono
- [ ] Ogni sezione dello snapshot ha un cap dichiarato
- [ ] La notifica non parte per una segnalazione già aperta

## Live-verify (utente, sull'addon)

1. «ci sono problemi in casa?» → deve elencare le segnalazioni del Brain (batterie, entità morte, automazioni rotte).
2. «come sta il sistema?» → add-on, spazio disco, aggiornamenti disponibili, salute integrazioni.
3. «cosa è successo ieri sera in salotto?» → cronologia dal logbook.
4. Provocare una condizione grave (per esempio fermare un add-on non critico) → entro 30 minuti deve arrivare **una** notifica; alla scansione successiva **nessuna** seconda notifica.
5. Riavviare l'add-on → la segnalazione si chiude da sola.
6. Verificare che HIRIS **non** possa aggiornare né riavviare nulla: chiederglielo esplicitamente e controllare che dica di non poterlo fare.
