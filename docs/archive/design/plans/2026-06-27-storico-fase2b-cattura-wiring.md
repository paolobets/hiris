# Storico — Fase 2b: cattura + policy + wiring `get_history` — Piano

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development o executing-plans. Step in checkbox (`- [ ]`).

**Goal:** Rendere lo storico proprietario operativo: catturare gli stati delle entità selezionate (policy opt-in) nello `HistoryStore`, compattarli ogni notte, e far leggere a `get_history` lo store per le entità storicizzate — il tutto cablato in `server.py`.

**Architecture:** Un `HistoryPolicy` (file `history_policy.json`) decide cosa storicizzare (per-dominio + allowlist/exclude). Un `HistoryCapture` registrato come `add_state_listener` filtra gli eventi `state_changed` e chiama `store.append`. Un job APScheduler notturno chiama `store.compact`. `get_history` riceve `store` + `today` e instrada le entità presenti nello store alla `store.query` (buckets giornalieri), mantenendo recorder/statistics per il resto. Default: nessuna entità catturata (opt-in).

**Tech Stack:** Python 3, aiohttp, APScheduler (`engine._scheduler`), sqlite3, pytest.

**Dipende da:** Fase 2a (`hiris/app/history/store.py` con `HistoryStore.append/compact/has_entity/query`).
**Fuori scope:** la pagina UI "Storicizzazione" è Fase 2c (qui la policy si scrive via API/file).

---

### Task 1: `HistoryPolicy` — decisione "cosa storicizzare" + API

**Files:**
- Create: `hiris/app/api/handlers_history_policy.py`
- Test: `tests/test_history_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_policy.py
import json
import os
import pytest
from aiohttp import web

from hiris.app.api.handlers_history_policy import (
    should_capture, load_policy, save_policy,
    handle_get_history_policy, handle_save_history_policy, DEFAULT_RETENTION_DAYS,
)


def test_should_capture_domain_and_allowlist_and_exclude():
    pol = {"domains": {"climate": True, "switch": False},
           "entities": ["valve.irrigazione"], "exclude": ["sensor.noise"],
           "retention_days": 90}
    assert should_capture("climate.salotto", pol) is True       # domain on
    assert should_capture("switch.x", pol) is False             # domain off
    assert should_capture("valve.irrigazione", pol) is True     # explicit allow
    assert should_capture("light.x", pol) is False              # domain absent -> off
    assert should_capture("sensor.noise", pol) is False         # excluded even if...
    pol2 = dict(pol, domains={"sensor": True})
    assert should_capture("sensor.noise", pol2) is False        # exclude wins over domain


def test_empty_policy_captures_nothing():
    assert should_capture("light.any", {}) is False
    assert should_capture("climate.any", {"domains": {}}) is False


def test_load_default_and_roundtrip(tmp_path):
    d = str(tmp_path)
    pol = load_policy(d)
    assert pol["domains"] == {} and pol["entities"] == [] and pol["exclude"] == []
    assert pol["retention_days"] == DEFAULT_RETENTION_DAYS
    save_policy(d, {"domains": {"climate": True}, "entities": ["valve.a"],
                    "exclude": [], "retention_days": 30})
    pol2 = load_policy(d)
    assert pol2["domains"] == {"climate": True}
    assert pol2["entities"] == ["valve.a"]
    assert pol2["retention_days"] == 30


def test_save_clamps_retention(tmp_path):
    d = str(tmp_path)
    save_policy(d, {"retention_days": 5000})
    assert load_policy(d)["retention_days"] == 365      # clamped to max
    save_policy(d, {"retention_days": 0})
    assert load_policy(d)["retention_days"] == 1        # clamped to min


@pytest.mark.asyncio
async def test_get_and_save_handlers(aiohttp_client, tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app.router.add_get("/api/history/policy", handle_get_history_policy)
    app.router.add_post("/api/history/policy", handle_save_history_policy)
    client = await aiohttp_client(app)
    r = await client.get("/api/history/policy")
    assert r.status == 200
    body = await r.json()
    assert "domains" in body and "categories" in body     # categories list for UI
    r2 = await client.post("/api/history/policy",
                           json={"domains": {"climate": True}, "retention_days": 45})
    assert r2.status == 200
    assert (await r2.json())["ok"] is True
    r3 = await client.get("/api/history/policy")
    assert (await r3.json())["domains"] == {"climate": True}
```

- [ ] **Step 2: Run, confirm FAIL** (module missing).
Run: `python -m pytest tests/test_history_policy.py -v`

- [ ] **Step 3: Implement `hiris/app/api/handlers_history_policy.py`**

```python
"""Storicizzazione policy — UI/file-managed, per-domain + explicit allow/exclude.

Decides which entities the HistoryStore captures. Default empty => capture nothing
(opt-in). Mirrors the gateway-policy pattern (handlers_gateway_policy.py)."""
from __future__ import annotations

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 90
_MIN_RETENTION, _MAX_RETENTION = 1, 365

# Domains offered in the UI (id + Italian label). Capture is opt-in per domain.
HISTORY_CATEGORIES = [
    {"id": "sensor", "label": "Sensori (temperatura, umidità, …)"},
    {"id": "binary_sensor", "label": "Sensori on/off (presenza, porte, …)"},
    {"id": "climate", "label": "Climatizzazione"},
    {"id": "switch", "label": "Interruttori / Prese"},
    {"id": "light", "label": "Luci"},
    {"id": "valve", "label": "Valvole / Irrigazione"},
    {"id": "cover", "label": "Tapparelle / Tende"},
    {"id": "lock", "label": "Serrature"},
    {"id": "fan", "label": "Ventilazione"},
    {"id": "media_player", "label": "Media / TV"},
    {"id": "device_tracker", "label": "Presenza persone"},
    {"id": "person", "label": "Persone"},
    {"id": "alarm_control_panel", "label": "Allarme"},
]
_VALID_DOMAINS = {c["id"] for c in HISTORY_CATEGORIES}


def _path(data_dir: str) -> str:
    return os.path.join(data_dir, "history_policy.json")


def load_policy(data_dir: str) -> dict:
    try:
        with open(_path(data_dir), encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = {}
    except Exception as exc:
        logger.warning("history_policy.json unreadable (%s) — using empty", exc)
        raw = {}
    domains = raw.get("domains") if isinstance(raw.get("domains"), dict) else {}
    domains = {k: bool(v) for k, v in domains.items() if k in _VALID_DOMAINS}
    entities = [e for e in raw.get("entities", []) if isinstance(e, str)]
    exclude = [e for e in raw.get("exclude", []) if isinstance(e, str)]
    ret = raw.get("retention_days", DEFAULT_RETENTION_DAYS)
    if not isinstance(ret, int) or isinstance(ret, bool):
        ret = DEFAULT_RETENTION_DAYS
    ret = max(_MIN_RETENTION, min(_MAX_RETENTION, ret))
    return {"domains": domains, "entities": entities, "exclude": exclude,
            "retention_days": ret}


def save_policy(data_dir: str, data: dict) -> dict:
    clean = {
        "domains": {k: bool(v) for k, v in (data.get("domains") or {}).items()
                    if k in _VALID_DOMAINS},
        "entities": [e for e in (data.get("entities") or []) if isinstance(e, str)],
        "exclude": [e for e in (data.get("exclude") or []) if isinstance(e, str)],
        "retention_days": data.get("retention_days", DEFAULT_RETENTION_DAYS),
    }
    if not isinstance(clean["retention_days"], int) or isinstance(clean["retention_days"], bool):
        clean["retention_days"] = DEFAULT_RETENTION_DAYS
    clean["retention_days"] = max(_MIN_RETENTION, min(_MAX_RETENTION, clean["retention_days"]))
    path = _path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    os.replace(tmp, path)
    return clean


def should_capture(entity_id: str, policy: dict) -> bool:
    """True if this entity should be recorded into the HistoryStore."""
    if entity_id in (policy.get("exclude") or []):
        return False
    if entity_id in (policy.get("entities") or []):
        return True
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return bool((policy.get("domains") or {}).get(domain, False))


async def handle_get_history_policy(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    return web.json_response(dict(load_policy(data_dir), categories=HISTORY_CATEGORIES))


async def handle_save_history_policy(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_policy(data_dir, body if isinstance(body, dict) else {})
    # Hot-reload the live capture filter if present.
    cap = request.app.get("history_capture")
    if cap is not None:
        cap.set_policy(clean)
    return web.json_response({"ok": True, **clean})
```

- [ ] **Step 4: Run, confirm PASS.**
Run: `python -m pytest tests/test_history_policy.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/api/handlers_history_policy.py tests/test_history_policy.py
git commit -m "feat(history): storicizzazione policy (should_capture + GET/POST API)"
```

---

### Task 2: `HistoryCapture` — listener di cattura

**Files:**
- Create: `hiris/app/history/capture.py`
- Test: `tests/test_history_capture.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_capture.py
from hiris.app.history.capture import HistoryCapture


class _FakeStore:
    def __init__(self):
        self.appended = []
    def append(self, entity_id, ts, state):
        self.appended.append((entity_id, ts, state))


def _evt(entity_id, state, last_changed="2026-06-26T10:00:00+00:00"):
    # shape of HA state_changed event data
    return {"entity_id": entity_id,
            "new_state": {"entity_id": entity_id, "state": state,
                          "last_changed": last_changed}}


def test_captures_only_policy_matching_entities():
    store = _FakeStore()
    cap = HistoryCapture(store, {"domains": {"climate": True}, "entities": [],
                                 "exclude": [], "retention_days": 90})
    cap.on_state_changed(_evt("climate.salotto", "21.0"))
    cap.on_state_changed(_evt("light.cucina", "on"))      # domain off -> skipped
    assert store.appended == [("climate.salotto", "2026-06-26T10:00:00+00:00", "21.0")]


def test_ignores_missing_new_state_and_never_raises():
    store = _FakeStore()
    cap = HistoryCapture(store, {"domains": {"sensor": True}})
    cap.on_state_changed({"entity_id": "sensor.x", "new_state": None})   # removed entity
    cap.on_state_changed({})                                             # garbage
    assert store.appended == []                                          # no crash, nothing stored


def test_set_policy_hot_reload():
    store = _FakeStore()
    cap = HistoryCapture(store, {})
    cap.on_state_changed(_evt("climate.x", "1"))          # nothing yet
    cap.set_policy({"domains": {"climate": True}})
    cap.on_state_changed(_evt("climate.x", "2"))
    assert store.appended == [("climate.x", "2026-06-26T10:00:00+00:00", "2")]
```

- [ ] **Step 2: Run, confirm FAIL.**
Run: `python -m pytest tests/test_history_capture.py -v`

- [ ] **Step 3: Implement `hiris/app/history/capture.py`**

```python
from __future__ import annotations

import logging
from typing import Any

from ..api.handlers_history_policy import should_capture

logger = logging.getLogger(__name__)


class HistoryCapture:
    """Registered as a HA state_changed listener. Filters by policy and appends
    matching state changes to the HistoryStore. Never raises (capture must not
    crash the WS loop)."""

    def __init__(self, store: Any, policy: dict) -> None:
        self._store = store
        self._policy = policy or {}

    def set_policy(self, policy: dict) -> None:
        self._policy = policy or {}

    def on_state_changed(self, data: dict) -> None:
        try:
            entity_id = (data or {}).get("entity_id")
            new_state = (data or {}).get("new_state")
            if not entity_id or not isinstance(new_state, dict):
                return
            if not should_capture(entity_id, self._policy):
                return
            state = new_state.get("state", "")
            ts = new_state.get("last_changed") or new_state.get("last_updated") or ""
            self._store.append(entity_id, ts, state)
        except Exception as exc:
            logger.debug("history capture skipped an event: %s", exc)
```

- [ ] **Step 4: Run, confirm PASS.**
Run: `python -m pytest tests/test_history_capture.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/capture.py tests/test_history_capture.py
git commit -m "feat(history): HistoryCapture state listener (policy-filtered append)"
```

---

### Task 3: `get_history` legge dallo store per entità storicizzate

**Files:**
- Modify: `hiris/app/tools/history_tools.py` (`_entity_series` + `get_history` signatures)
- Modify: `hiris/app/tools/dispatcher.py` (constructor + get_history branch)
- Test: `tests/test_history_tools.py` (append), `tests/test_dispatcher_history.py` (append)

- [ ] **Step 1: Write the failing test (history_tools)**

```python
# append to tests/test_history_tools.py
class _FakeStore:
    def __init__(self, entities):
        self._e = entities
    def has_entity(self, eid):
        return eid in self._e
    def query(self, eid, days, today):
        if eid not in self._e:
            return None
        return {"id": eid, "source": "store", "unit": None,
                "buckets": [{"t": "2026-06-19", "min": 1.0, "max": 3.0, "mean": 2.0, "n": 5}]}


@pytest.mark.asyncio
async def test_get_history_uses_store_for_captured_entity():
    ha = _FakeHA()                         # ha would be empty; store must win
    store = _FakeStore({"climate.salotto"})
    out = await H.get_history(ha, ["climate.salotto"], days=30, resolution="auto",
                              store=store, today="2026-06-20")
    series = out[0]
    assert series["source"] == "store"
    assert series["resolution"] == "daily"
    assert series["buckets"][0]["mean"] == 2.0


@pytest.mark.asyncio
async def test_get_history_store_skipped_for_raw_resolution():
    # raw wants finest recorder data even for captured entities
    ha = _FakeHA(history={"climate.salotto": [
        {"last_changed": "2026-06-20T10:00:00+00:00", "state": "21.0"}]})
    store = _FakeStore({"climate.salotto"})
    out = await H.get_history(ha, ["climate.salotto"], days=3, resolution="raw",
                              store=store, today="2026-06-20")
    assert out[0]["source"] == "recorder"
```

- [ ] **Step 2: Run, confirm FAIL** (get_history has no `store`/`today` params).
Run: `python -m pytest tests/test_history_tools.py -k "uses_store or store_skipped" -v`

- [ ] **Step 3: Implement in `hiris/app/tools/history_tools.py`**

Change `_entity_series` signature and add the store branch at the very top of its body (before the statistics block):

```python
async def _entity_series(ha: Any, eid: str, days: int, resolution: str,
                         store: Any = None, today: Optional[str] = None) -> dict:
    long_range = days > RECORDER_WINDOW_DAYS
    want_raw = resolution == "raw"

    # Captured entities: the HIRIS store is authoritative for aggregated history.
    if store is not None and not want_raw and store.has_entity(eid):
        res = store.query(eid, days, today)
        if res and res.get("buckets"):
            res["resolution"] = "daily"
            return res

    # (existing statistics + recorder logic unchanged below)
    if long_range and not want_raw:
        ...
```

Change `get_history` to accept and forward `store`/`today` (computing `today` if not given):

```python
async def get_history(ha: Any, entity_ids: list[str], days: int = 7,
                      resolution: str = "auto", store: Any = None,
                      today: Optional[str] = None) -> Any:
    err = validate_inputs(entity_ids, days, resolution)
    if err:
        return {"error": err}
    if today is None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [await _entity_series(ha, eid, days, resolution, store=store, today=today)
            for eid in entity_ids]
```

- [ ] **Step 4: Implement dispatcher wiring in `hiris/app/tools/dispatcher.py`**

Add a `history_store` parameter to `ToolDispatcher.__init__` (default None), store it as `self._history_store = history_store` next to the other assignments. Then change the `get_history` dispatch branch to pass the store:

```python
            if name == "get_history":
                return await _get_history(
                    self._ha,
                    inputs.get("entity_ids", []),
                    days=int(inputs.get("days", 7)),
                    resolution=inputs.get("resolution", "auto"),
                    store=self._history_store,
                )
```

- [ ] **Step 5: Write the failing test (dispatcher)**

```python
# append to tests/test_dispatcher_history.py
class _StoreFake:
    def has_entity(self, eid): return True
    def query(self, eid, days, today):
        return {"id": eid, "source": "store", "unit": None,
                "buckets": [{"t": "2026-06-19", "mean": 2.0, "min": 1.0, "max": 3.0, "n": 4}]}


@pytest.mark.asyncio
async def test_dispatch_get_history_prefers_store_when_present():
    d = ToolDispatcher(_FakeHA(), notify_config={}, history_store=_StoreFake())
    out = await d.dispatch("get_history", {"entity_ids": ["climate.x"], "days": 30})
    assert out[0]["source"] == "store"
```

- [ ] **Step 6: Run all, confirm PASS + full suite.**
Run: `python -m pytest tests/test_history_tools.py tests/test_dispatcher_history.py -v`
Run: `python -m pytest -q`

- [ ] **Step 7: Commit (LOCAL ONLY)**

```bash
git add hiris/app/tools/history_tools.py hiris/app/tools/dispatcher.py tests/test_history_tools.py tests/test_dispatcher_history.py
git commit -m "feat(history): get_history reads HistoryStore for captured entities"
```

---

### Task 4: Wiring in `server.py` (store + cattura + compact notturno + route + dispatcher)

**Files:**
- Modify: `hiris/app/server.py`
- Test: `tests/test_history_wiring.py` (smoke)

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/test_history_wiring.py
from hiris.app.history.store import HistoryStore
from hiris.app.history.capture import HistoryCapture
from hiris.app.api.handlers_history_policy import load_policy


def test_capture_appends_into_real_store(tmp_path):
    s = HistoryStore(str(tmp_path / "history.db"))
    cap = HistoryCapture(s, {"domains": {"climate": True}})
    cap.on_state_changed({"entity_id": "climate.x",
                          "new_state": {"state": "21.0",
                                        "last_changed": "2026-06-20T10:00:00+00:00"}})
    out = s.query("climate.x", days=7, today="2026-06-20")
    assert out is not None and out["buckets"][0]["mean"] == 21.0


def test_compact_callable_with_policy_retention(tmp_path):
    s = HistoryStore(str(tmp_path / "history.db"))
    s.append("climate.x", "2026-06-10T10:00:00+00:00", "10.0")
    pol = load_policy(str(tmp_path))
    s.compact(today="2026-06-20", retention_days=pol["retention_days"])
    assert s.has_entity("climate.x") is True   # rolled into daily
```

- [ ] **Step 2: Run, confirm PASS already** (these exercise 2a+2b units, no server). This is a guard test — if it fails, an earlier task regressed.
Run: `python -m pytest tests/test_history_wiring.py -v`

- [ ] **Step 3: Wire into `create_app` in `hiris/app/server.py`**

(a) Near the other stores (after the `knowledge_store = KnowledgeStore(...)` block ~line 429), add:

```python
    from .history.store import HistoryStore
    from .history.capture import HistoryCapture
    from .api.handlers_history_policy import load_policy as _load_history_policy

    history_store = HistoryStore(os.path.join(data_dir, "history.db"))
    app["history_store"] = history_store
    history_capture = HistoryCapture(history_store, _load_history_policy(data_dir))
    app["history_capture"] = history_capture
    ha_client.add_state_listener(history_capture.on_state_changed)
```

(b) Add the nightly compaction job next to the other `engine._scheduler.add_job(...)` calls (after the retention job, ~line 458):

```python
    def _run_history_compact() -> None:
        from datetime import datetime, timezone
        pol = _load_history_policy(data_dir)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            history_store.compact(today=today, retention_days=pol["retention_days"])
        except Exception as exc:
            logger.error("History compaction failed: %s", exc, exc_info=True)

    engine._scheduler.add_job(
        _run_history_compact,
        trigger="cron", hour=3, minute=30,
        id="hiris_history_compact", replace_existing=True, misfire_grace_time=3600,
    )
```

(c) Pass `history_store` into the `ToolDispatcher(...)` constructor (the call ~line 560): add the kwarg
```python
        history_store=history_store,
```

(d) Register the policy API routes. Find where other API routes are registered (grep for `add_get("/api/` / `handle_get_gateway_policy`) and add, alongside them:
```python
    from .api.handlers_history_policy import (
        handle_get_history_policy, handle_save_history_policy,
    )
    app.router.add_get("/api/history/policy", handle_get_history_policy)
    app.router.add_post("/api/history/policy", handle_save_history_policy)
```

- [ ] **Step 4: Verify the app still imports/builds and the suite is green.**
Run: `python -m pytest tests/test_api.py tests/test_security.py -q`  (route registration smoke)
Run: `python -m pytest -q`  (full suite)

- [ ] **Step 5: Manual import sanity (no syntax/wiring error in create_app):**
Run: `python -c "import hiris.app.server"`
Expected: no exception.

- [ ] **Step 6: Commit (LOCAL ONLY)**

```bash
git add hiris/app/server.py tests/test_history_wiring.py
git commit -m "feat(history): wire HistoryStore + capture + nightly compaction + policy API"
```

---

## Self-Review (compilata)

**Spec coverage:** cattura via state listener filtrato da policy (Task 1/2/4); compact notturno schedulato (Task 4); `get_history` legge lo store per le entità storicizzate, recorder/statistics per il resto (Task 3); policy opt-in per-dominio + allowlist/exclude + retention con clamp (Task 1); hot-reload della policy sul salvataggio (Task 1+2). UI = Fase 2c.

**Placeholder scan:** nessun TBD; ogni step ha codice/comando. Lo Step 3 della Task 4(d) richiede di individuare il punto di registrazione route esistente — istruzione esplicita (grep `handle_get_gateway_policy`).

**Type consistency:** `should_capture(entity_id, policy)->bool` usato da `HistoryCapture` e testato; `load_policy/save_policy(data_dir)->dict{domains,entities,exclude,retention_days}` coerenti; `HistoryCapture(store, policy)` con `set_policy`/`on_state_changed`; `get_history(..., store=None, today=None)` e `_entity_series(..., store, today)` coerenti col contratto Fase 1/2a (`store.query`-> `{id,source:"store",unit,buckets}`); `ToolDispatcher(history_store=None)` -> `self._history_store` passato a `get_history`. Job APScheduler via `engine._scheduler.add_job` come gli altri.

**Nota:** lo store viene istanziato sempre, ma con policy vuota (default) non cattura nulla → nessun impatto finché l'utente non abilita domini dalla UI (2c) o via API. Sicuro da rilasciare.
