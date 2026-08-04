# Storico via MCP — Fase 1 (`get_history` su HA recorder + statistics) — Piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Esporre via MCP un tool `get_history` che dà a Claude dati storici compressi (trend numerici, min/max/media) leggendo il recorder HA (recente) e le Long-Term Statistics HA (mesi), senza nuovo storage.

**Architecture:** Un tool unico `get_history(entity_ids, days, resolution)` instrada per-entità tra recorder REST (recente/raw) e statistics WS (range lungo, numerico). La logica di scelta layer, aggregazione e compressione è in funzioni pure testabili; l'I/O HA sta in `ha_client`. Il tool è tier READ: niente semaforo, e con il fix v0.14.9 le letture vedono tutte le entità.

**Tech Stack:** Python 3, aiohttp, pytest/pytest-asyncio, SQLite (non in Fase 1), HA WebSocket API (`recorder/statistics_during_period`), HA REST `/api/history`.

**Spec di riferimento:** `docs/design/2026-06-27-storico-dati-mcp-design.md`

**Fuori scope Fase 1:** HistoryStore/cattura (Fase 2), durate on/off long-term (Fase 2), digest second brain (Fase 3). In Fase 1 le entità non-numeriche dal recorder tornano come campioni grezzi downsamplati (non aggregati in on_seconds).

---

### Task 1: `ha_client` — `get_statistics` + round-trip WS generalizzato

**Files:**
- Modify: `hiris/app/proxy/ha_client.py` (aggiungi `_ws_request`, rifattorizza `_ws_call`, aggiungi `get_statistics`)
- Test: `tests/test_ha_client_statistics.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ha_client_statistics.py
import pytest
from hiris.app.proxy.ha_client import HAClient


@pytest.mark.asyncio
async def test_get_statistics_returns_dict(monkeypatch):
    ha = HAClient("http://ha.local:8123", "tok")
    captured = {}

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        captured["msg_type"] = msg_type
        captured["extra"] = extra
        return {"sensor.temp": [{"start": "2026-06-20T00:00:00+00:00",
                                 "mean": 21.6, "min": 19.1, "max": 24.3}]}

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.get_statistics(["sensor.temp"], period="day", days=30)
    assert captured["msg_type"] == "recorder/statistics_during_period"
    assert captured["extra"]["statistic_ids"] == ["sensor.temp"]
    assert captured["extra"]["period"] == "day"
    assert "sensor.temp" in out


@pytest.mark.asyncio
async def test_get_statistics_non_dict_result_is_empty(monkeypatch):
    ha = HAClient("http://ha.local:8123", "tok")

    async def fake_ws_request(msg_type, extra=None, timeout=10.0):
        return None

    monkeypatch.setattr(ha, "_ws_request", fake_ws_request)
    out = await ha.get_statistics(["sensor.temp"], period="hour", days=1)
    assert out == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ha_client_statistics.py -v`
Expected: FAIL with `AttributeError: 'HAClient' object has no attribute 'get_statistics'`

- [ ] **Step 3: Implement `_ws_request`, refactor `_ws_call`, add `get_statistics`**

In `hiris/app/proxy/ha_client.py`, replace the existing `_ws_call` method (currently around lines 167-191) with the generalized request plus a thin `_ws_call` wrapper, and add `get_statistics`:

```python
    async def _ws_request(self, msg_type: str, extra: dict | None = None,
                          timeout: float = 10.0) -> Any:
        """Single WebSocket command → raw `result` (dict OR list, per command)."""
        ws_url = (
            self._base_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )
        token = self._headers["Authorization"].removeprefix("Bearer ")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    handshake = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                    if handshake.get("type") == "auth_required":
                        await ws.send_json({"type": "auth", "access_token": token})
                        auth_resp = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if auth_resp.get("type") != "auth_ok":
                            logger.warning("HA WS auth failed in _ws_request(%s)", msg_type)
                            return None
                    payload = {"id": 1, "type": msg_type}
                    if extra:
                        payload.update(extra)
                    await ws.send_json(payload)
                    while True:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
                        if msg.get("id") == 1:
                            return msg.get("result")
        except Exception as exc:
            logger.debug("_ws_request(%s) failed: %s", msg_type, exc)
            return None

    async def _ws_call(self, msg_type: str, timeout: float = 10.0) -> list[dict]:
        """Back-compat wrapper: WS command whose result is a list (registry, etc.)."""
        result = await self._ws_request(msg_type, timeout=timeout)
        return result if isinstance(result, list) else []

    async def get_statistics(self, statistic_ids: list[str], period: str,
                             days: int) -> dict:
        """HA Long-Term Statistics for measurement sensors over the last N days.

        period: "5minute" | "hour" | "day" | "week" | "month".
        Returns {statistic_id: [{start, mean, min, max, sum?}, ...]} ({} on failure).
        """
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await self._ws_request(
            "recorder/statistics_during_period",
            extra={"start_time": start,
                   "statistic_ids": list(statistic_ids),
                   "period": period},
        )
        return result if isinstance(result, dict) else {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ha_client_statistics.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Verify existing WS callers still work**

Run: `python -m pytest tests/ -k "registry or area or ws or health" -q`
Expected: PASS (no regressions in WS-based callers)

- [ ] **Step 6: Commit**

```bash
git add hiris/app/proxy/ha_client.py tests/test_ha_client_statistics.py
git commit -m "feat(history): ha_client.get_statistics via generalized WS request"
```

---

### Task 2: `history_tools` — funzioni pure + TOOL_DEF

**Files:**
- Create: `hiris/app/tools/history_tools.py`
- Test: `tests/test_history_tools.py` (create)

- [ ] **Step 1: Write the failing test (pure helpers)**

```python
# tests/test_history_tools.py
from hiris.app.tools import history_tools as H


def test_validate_inputs_ok():
    assert H.validate_inputs(["sensor.a"], 7, "auto") is None


def test_validate_inputs_rejects_empty_and_too_many():
    assert H.validate_inputs([], 7, "auto") is not None
    assert H.validate_inputs(["x"] * 21, 7, "auto") is not None


def test_validate_inputs_rejects_bad_days_and_resolution():
    assert H.validate_inputs(["x"], 0, "auto") is not None
    assert H.validate_inputs(["x"], 400, "auto") is not None
    assert H.validate_inputs(["x"], 7, "weekly") is not None


def test_classify_numeric_vs_state():
    numeric = [{"state": "21.5"}, {"state": "22.0"}, {"state": "bad"}]
    state = [{"state": "on"}, {"state": "off"}, {"state": "on"}]
    assert H.classify(numeric) == "numeric"   # majority parse as float
    assert H.classify(state) == "state"


def test_aggregate_numeric_daily():
    samples = [
        {"t": "2026-06-20T01:00:00+00:00", "state": "19.0"},
        {"t": "2026-06-20T13:00:00+00:00", "state": "24.0"},
        {"t": "2026-06-21T08:00:00+00:00", "state": "20.0"},
    ]
    out = H.aggregate_numeric(samples, "daily")
    assert out[0] == {"t": "2026-06-20", "min": 19.0, "max": 24.0, "mean": 21.5, "n": 2}
    assert out[1]["t"] == "2026-06-21" and out[1]["n"] == 1


def test_downsample_caps_points():
    pts = [{"t": str(i), "state": str(i)} for i in range(1000)]
    out = H.downsample(pts, 100)
    assert len(out) <= 100
    assert out[0] == pts[0] and out[-1] == pts[-1]   # endpoints preserved


def test_normalize_statistics_rows():
    rows = [{"start": "2026-06-20T00:00:00+00:00", "mean": 21.6, "min": 19.1, "max": 24.3},
            {"start": 1750464000000, "mean": 22.0, "min": 20.0, "max": 25.0}]  # ms epoch
    out = H.normalize_statistics(rows)
    assert out[0] == {"t": "2026-06-20", "min": 19.1, "max": 24.3, "mean": 21.6, "n": 1}
    assert out[1]["t"] == "2026-06-21"   # ms epoch parsed to date
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_history_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: hiris.app.tools.history_tools`

- [ ] **Step 3: Implement the module**

```python
# hiris/app/tools/history_tools.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

MAX_ENTITIES = 20
MAX_DAYS = 365
MAX_RAW_POINTS = 500            # per-entity cap before downsampling
RECORDER_WINDOW_DAYS = 10       # routing threshold (HA recorder default retention)
_VALID_RESOLUTION = ("auto", "raw", "hourly", "daily")

GET_HISTORY_TOOL_DEF = {
    "name": "get_history",
    "description": (
        "Historical/time-series data for entities (trends, min/max/avg). READ-only. "
        "Returns COMPRESSED per-entity daily/hourly buckets, never raw point dumps. "
        "Use for: 'temperature trend last week', 'energy this month', sensor history. "
        "Args: entity_ids (1-20), days (1-365, default 7), "
        "resolution ('auto'|'raw'|'hourly'|'daily')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_ids": {"type": "array", "items": {"type": "string"},
                           "minItems": 1, "maxItems": MAX_ENTITIES},
            "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS},
            "resolution": {"type": "string", "enum": list(_VALID_RESOLUTION)},
        },
        "required": ["entity_ids"],
    },
}


def validate_inputs(entity_ids: Any, days: int, resolution: str) -> Optional[str]:
    if not isinstance(entity_ids, list) or not (1 <= len(entity_ids) <= MAX_ENTITIES):
        return f"entity_ids must be a list of 1..{MAX_ENTITIES} ids"
    if not all(isinstance(e, str) and e for e in entity_ids):
        return "entity_ids must be non-empty strings"
    if not isinstance(days, int) or not (1 <= days <= MAX_DAYS):
        return f"days must be an integer 1..{MAX_DAYS}"
    if resolution not in _VALID_RESOLUTION:
        return f"resolution must be one of {_VALID_RESOLUTION}"
    return None


def _to_float(s: Any) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def classify(samples: list[dict]) -> str:
    """'numeric' if the majority of states parse as float, else 'state'."""
    if not samples:
        return "state"
    numeric = sum(1 for s in samples if _to_float(s.get("state")) is not None)
    return "numeric" if numeric * 2 >= len(samples) else "state"


def _bucket_key(ts: str, resolution: str) -> str:
    # ts is ISO8601; daily -> YYYY-MM-DD, hourly -> YYYY-MM-DDTHH
    return ts[:13] if resolution == "hourly" else ts[:10]


def aggregate_numeric(samples: list[dict], resolution: str) -> list[dict]:
    """Group numeric samples (each {'t','state'}) into min/max/mean/n per bucket."""
    buckets: dict[str, list[float]] = {}
    for s in samples:
        v = _to_float(s.get("state"))
        if v is None:
            continue
        key = _bucket_key(s.get("t", ""), resolution)
        buckets.setdefault(key, []).append(v)
    out = []
    for key in sorted(buckets):
        vals = buckets[key]
        out.append({"t": key, "min": min(vals), "max": max(vals),
                    "mean": round(sum(vals) / len(vals), 3), "n": len(vals)})
    return out


def downsample(points: list[dict], cap: int) -> list[dict]:
    """Evenly thin a point list to <= cap, always keeping first and last."""
    if len(points) <= cap or cap < 2:
        return points
    step = (len(points) - 1) / (cap - 1)
    idxs = sorted({round(i * step) for i in range(cap)})
    idxs = [min(i, len(points) - 1) for i in idxs]
    return [points[i] for i in idxs]


def _stat_ts_to_day(start: Any) -> str:
    if isinstance(start, (int, float)):
        return datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(start)[:10]


def normalize_statistics(rows: list[dict]) -> list[dict]:
    """HA statistics rows -> uniform numeric buckets {t,min,max,mean,n}."""
    out = []
    for r in rows:
        out.append({
            "t": _stat_ts_to_day(r.get("start")),
            "min": r.get("min"), "max": r.get("max"), "mean": r.get("mean"),
            "n": 1,
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history_tools.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/history_tools.py tests/test_history_tools.py
git commit -m "feat(history): pure helpers + GET_HISTORY_TOOL_DEF"
```

---

### Task 3: `history_tools.get_history` — orchestratore con routing

**Files:**
- Modify: `hiris/app/tools/history_tools.py` (aggiungi `get_history`)
- Test: `tests/test_history_tools.py` (estendi)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_tools.py
import pytest


class _FakeHA:
    def __init__(self, history=None, stats=None):
        self._history = history or {}
        self._stats = stats or {}

    async def get_history(self, entity_ids, days):
        eid = entity_ids[0]
        return [dict(s, entity_id=eid) for s in self._history.get(eid, [])]

    async def get_statistics(self, statistic_ids, period, days):
        return {k: v for k, v in self._stats.items() if k in statistic_ids}


@pytest.mark.asyncio
async def test_get_history_recent_numeric_aggregates_recorder():
    ha = _FakeHA(history={"sensor.temp": [
        {"last_changed": "2026-06-26T01:00:00+00:00", "state": "19.0"},
        {"last_changed": "2026-06-26T13:00:00+00:00", "state": "24.0"},
    ]})
    out = await H.get_history(ha, ["sensor.temp"], days=3, resolution="auto")
    series = out[0]
    assert series["id"] == "sensor.temp"
    assert series["resolution"] == "daily"
    assert series["buckets"][0] == {"t": "2026-06-26", "min": 19.0, "max": 24.0,
                                    "mean": 21.5, "n": 2}


@pytest.mark.asyncio
async def test_get_history_long_range_uses_statistics():
    ha = _FakeHA(stats={"sensor.temp": [
        {"start": "2026-05-01T00:00:00+00:00", "mean": 18.0, "min": 15.0, "max": 21.0},
    ]})
    out = await H.get_history(ha, ["sensor.temp"], days=60, resolution="auto")
    series = out[0]
    assert series["source"] == "statistics"
    assert series["buckets"][0]["mean"] == 18.0


@pytest.mark.asyncio
async def test_get_history_long_range_falls_back_to_recorder_with_note():
    # No statistics for this entity -> fall back to recorder window + partial note.
    ha = _FakeHA(history={"binary_sensor.door": [
        {"last_changed": "2026-06-26T09:00:00+00:00", "state": "on"},
        {"last_changed": "2026-06-26T09:05:00+00:00", "state": "off"},
    ]})
    out = await H.get_history(ha, ["binary_sensor.door"], days=60, resolution="auto")
    series = out[0]
    assert series["source"] == "recorder"
    assert series["partial"] is True            # range exceeds recorder window
    assert series["resolution"] == "raw"        # non-numeric -> raw samples
    assert series["samples"][0]["state"] == "on"


@pytest.mark.asyncio
async def test_get_history_rejects_bad_input():
    ha = _FakeHA()
    out = await H.get_history(ha, [], days=7, resolution="auto")
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_history_tools.py -k get_history -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'get_history'`

- [ ] **Step 3: Implement the orchestrator**

Append to `hiris/app/tools/history_tools.py`:

```python
def _ts_of(sample: dict) -> str:
    return sample.get("last_changed") or sample.get("last_updated") or ""


def _period_for(days: int, resolution: str) -> str:
    if resolution == "hourly":
        return "hour"
    if resolution == "daily":
        return "day"
    return "hour" if days <= 35 else "day"


def _resolution_for(days: int, resolution: str) -> str:
    if resolution != "auto":
        return resolution
    return "daily" if days > 2 else "raw"


async def _entity_series(ha: Any, eid: str, days: int, resolution: str) -> dict:
    long_range = days > RECORDER_WINDOW_DAYS
    want_raw = resolution == "raw"

    # Long numeric range -> try HA statistics first.
    if long_range and not want_raw:
        stats = await ha.get_statistics([eid], period=_period_for(days, resolution), days=days)
        rows = stats.get(eid) or []
        if rows:
            return {"id": eid, "source": "statistics",
                    "resolution": _period_for(days, resolution),
                    "buckets": normalize_statistics(rows)}

    # Recorder path (recent, or statistics-less fallback).
    raw = await ha.get_history([eid], days)
    samples = [{"t": _ts_of(s), "state": s.get("state")} for s in raw
               if s.get("entity_id", eid) == eid]
    series: dict = {"id": eid, "source": "recorder"}
    if long_range:
        series["partial"] = True   # recorder retains only ~RECORDER_WINDOW_DAYS days

    eff = _resolution_for(days, resolution)
    if eff != "raw" and classify(samples) == "numeric":
        series["resolution"] = eff
        series["buckets"] = aggregate_numeric(samples, eff)
    else:
        series["resolution"] = "raw"
        series["samples"] = downsample(samples, MAX_RAW_POINTS)
    return series


async def get_history(ha: Any, entity_ids: list[str], days: int = 7,
                      resolution: str = "auto") -> Any:
    err = validate_inputs(entity_ids, days, resolution)
    if err:
        return {"error": err}
    return [await _entity_series(ha, eid, days, resolution) for eid in entity_ids]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history_tools.py -v`
Expected: PASS (all, incl. 4 new get_history tests)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/history_tools.py tests/test_history_tools.py
git commit -m "feat(history): get_history orchestrator (recorder/statistics routing)"
```

---

### Task 4: Dispatcher — esponi `get_history` (tier READ)

**Files:**
- Modify: `hiris/app/tools/dispatcher.py` (import + branch in `dispatch`)
- Test: `tests/test_tools.py` (estendi, oppure crea `tests/test_dispatcher_history.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatcher_history.py
import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    async def get_history(self, entity_ids, days):
        return [{"entity_id": entity_ids[0], "last_changed": "2026-06-26T10:00:00+00:00",
                 "state": "21.0"}]

    async def get_statistics(self, statistic_ids, period, days):
        return {}


@pytest.mark.asyncio
async def test_dispatch_get_history_returns_series():
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history",
                           {"entity_ids": ["sensor.temp"], "days": 3})
    assert isinstance(out, list)
    assert out[0]["id"] == "sensor.temp"


@pytest.mark.asyncio
async def test_dispatch_get_history_ignores_action_whitelist():
    # Reads must NOT be filtered by allowed_entities (action whitelist).
    d = ToolDispatcher(_FakeHA(), notify_config={})
    out = await d.dispatch("get_history", {"entity_ids": ["sensor.temp"], "days": 3},
                           allowed_entities=["light.*"])
    assert out[0]["id"] == "sensor.temp"   # not blocked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dispatcher_history.py -v`
Expected: FAIL — dispatch returns the "Unknown tool" error dict, assertion fails.

- [ ] **Step 3: Implement the dispatch branch**

In `hiris/app/tools/dispatcher.py`, add to the imports block (near the other `from .` tool imports, around line 12):

```python
from .history_tools import get_history as _get_history
```

Then add this branch inside `dispatch`, immediately after the `get_entity_states` branch (after line 131, before the `get_home_status` branch). `get_history` deliberately ignores `allowed_entities` — it is a non-destructive READ:

```python
            if name == "get_history":
                return await _get_history(
                    self._ha,
                    inputs.get("entity_ids", []),
                    days=int(inputs.get("days", 7)),
                    resolution=inputs.get("resolution", "auto"),
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dispatcher_history.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/dispatcher.py tests/test_dispatcher_history.py
git commit -m "feat(history): dispatch get_history (READ, ignores action whitelist)"
```

---

### Task 5: Registra il tool per i runner LLM (chat HIRIS)

**Files:**
- Modify: `hiris/app/claude_runner.py` (import, `ALL_TOOL_DEFS`, `EVALUATION_ONLY_TOOLS`)
- Test: `tests/test_history_tools.py` (estendi con un check di registrazione)

`openai_compat_runner.py` importa `ALL_TOOL_DEFS` ed `EVALUATION_ONLY_TOOLS` da `claude_runner`, quindi una sola modifica copre entrambi i runner.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_tools.py
def test_get_history_registered_in_runner():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_history" in names
    assert "get_history" in EVALUATION_ONLY_TOOLS    # read-only, injection-safe
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_history_tools.py -k registered -v`
Expected: FAIL — `get_history` not in `ALL_TOOL_DEFS`.

- [ ] **Step 3: Implement the registration**

In `hiris/app/claude_runner.py`:

Add the import next to the energy tool import (line 16):

```python
from .tools.energy_tools import TOOL_DEF as ENERGY_TOOL
from .tools.history_tools import GET_HISTORY_TOOL_DEF
```

Add to the `ALL_TOOL_DEFS` list, right after `ENERGY_TOOL,` (line 111):

```python
    ENERGY_TOOL,
    GET_HISTORY_TOOL_DEF,
```

Add `"get_history"` to the `EVALUATION_ONLY_TOOLS` frozenset, on the `get_energy_history` line (line 141):

```python
    "get_energy_history", "get_weather_forecast", "get_history",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history_tools.py -k registered -v`
Expected: PASS

- [ ] **Step 5: Run the runner import smoke test**

Run: `python -m pytest tests/test_claude_runner.py tests/test_openai_compat_runner.py -q`
Expected: PASS (both runners import and build tool lists cleanly)

- [ ] **Step 6: Commit**

```bash
git add hiris/app/claude_runner.py tests/test_history_tools.py
git commit -m "feat(history): register get_history for both LLM runners"
```

---

### Task 6: Allowlist execute-API + gateway READ_TOOLS

**Files:**
- Modify: `hiris/app/api/handlers_gateway_policy.py:23` (`READ_TOOLS`)
- Test: `tests/test_gateway_policy.py` (estendi), `tests/test_execute_api.py` (estendi)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_gateway_policy.py
from hiris.app.api.handlers_gateway_policy import READ_TOOLS, derive_execute_policy


def test_get_history_is_a_read_tool():
    assert "get_history" in READ_TOOLS


def test_derived_policy_exposes_get_history():
    pol = derive_execute_policy({"light": "green"})
    assert "get_history" in pol["tools"]
```

```python
# append to tests/test_execute_api.py
@pytest.mark.asyncio
async def test_execute_get_history_bypasses_action_whitelist(aiohttp_client):
    policy = {"tools": ["get_history"], "allowed_entities": ["light.*"],
              "allowed_services": ["light.*"]}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_history",
                                "input": {"entity_ids": ["sensor.temp"], "days": 3}})
    assert resp.status == 200
    name, inputs, ents, svcs = app["tool_dispatcher"].calls[0]
    assert name == "get_history"
    assert ents is None and svcs is None     # read sees everything
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gateway_policy.py -k get_history tests/test_execute_api.py -k get_history -v`
Expected: FAIL — `get_history` not in `READ_TOOLS`; execute test fails because the handler does not yet treat `get_history` as a read (it is once added to READ_TOOLS, which the handler imports).

- [ ] **Step 3: Implement — add `get_history` to READ_TOOLS**

In `hiris/app/api/handlers_gateway_policy.py`, line 23:

```python
# Read tools are always available to the gateway (non-destructive).
READ_TOOLS = ["get_home_status", "get_area_entities", "get_entity_states",
              "get_history", "recall_knowledge"]
```

(No change needed in `handlers_execute.py`: it already imports `READ_TOOLS` and routes reads to bypass the whitelist as of v0.14.9.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gateway_policy.py tests/test_execute_api.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/api/handlers_gateway_policy.py tests/test_gateway_policy.py tests/test_execute_api.py
git commit -m "feat(history): expose get_history via execute-API READ allowlist"
```

---

### Task 7: Catalogo MCP del gateway

**Files:**
- Modify: `C:/Work/Sviluppo/hiris-mcp-gateway/app/tiers.py` (aggiungi `ToolDef`)
- Test: `C:/Work/Sviluppo/hiris-mcp-gateway/tests/test_tiers.py` (create o estendi)

- [ ] **Step 1: Write the failing test**

```python
# hiris-mcp-gateway/tests/test_tiers.py
from app.tiers import get_tool, Tier, TOOLS


def test_get_history_is_registered_as_read():
    t = get_tool("get_history")
    assert t.tier == Tier.READ
    assert t.hiris_tool == "get_history"
    assert t.requires_confirmation is False     # READ never gated by the semaforo


def test_get_history_in_catalog():
    assert any(t.name == "get_history" for t in TOOLS)
```

- [ ] **Step 2: Run test to verify it fails**

Run (from the gateway repo): `python -m pytest tests/test_tiers.py -v`
Expected: FAIL with `KeyError: 'get_history'`

- [ ] **Step 3: Implement — add the ToolDef**

In `hiris-mcp-gateway/app/tiers.py`, inside the `TOOLS` list under the `# --- READ ---` section (after the `get_entity_states` entry):

```python
    ToolDef("get_history", Tier.READ, "get_history",
            "Historical/time-series data for entities (trends, min/max/avg, "
            "sensor history). READ-only; returns compressed buckets."),
```

- [ ] **Step 4: Run test to verify it passes**

Run (from the gateway repo): `python -m pytest tests/test_tiers.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the gateway suite**

Run (from the gateway repo): `python -m pytest -q`
Expected: PASS (no regressions; `register_tools` now exposes one more READ tool)

- [ ] **Step 6: Commit (gateway repo)**

```bash
git add app/tiers.py tests/test_tiers.py
git commit -m "feat: expose get_history READ tool in MCP catalog"
```

---

### Task 8: Release HIRIS + verifica deploy

**Files:**
- Modify: `hiris/config.yaml` (version bump), `CHANGELOG.md`

- [ ] **Step 1: Run the full HIRIS suite**

Run: `python -m pytest -q`
Expected: PASS (tutti, inclusi i nuovi test storico)

- [ ] **Step 2: Bump versione + changelog**

`hiris/config.yaml`: `version: "0.15.0"` (nuova capability → minor bump).
`CHANGELOG.md`: nuova sezione in cima:

```markdown
## v0.15.0 — Storico via MCP: get_history (recorder + statistics) (2026-06-27)

- Nuovo tool **get_history(entity_ids, days, resolution)** esposto via MCP e nella
  chat HIRIS: trend storici compressi (min/max/media) leggendo il recorder HA
  (recente) e le Long-Term Statistics HA (mesi), senza nuovo storage.
- Tier **READ** → fuori dal semaforo; con il fix v0.14.9 vede tutte le entità.
- Output sempre aggregato/downsamplato (cap punti) per non esplodere i token.
- Fase 1 dello storico ibrido (HistoryStore proprietario + cattura = Fase 2).
```

- [ ] **Step 3: Verifica allowlist deploy (nota operativa)**

Se l'ambiente NON usa la policy UI del semaforo, `execute_policy["tools"]` viene da
`EXECUTE_API_TOOLS` (env add-on): aggiungere `get_history`. Se invece la policy UI è
salvata (caso del deploy attuale), `derive_execute_policy` la include in automatico
via `READ_TOOLS` — nessuna azione. Verificare quale dei due casi è attivo prima del
rilascio.

- [ ] **Step 4: Commit + push (previa conferma utente)**

```bash
git add hiris/config.yaml CHANGELOG.md
git commit -m "release: v0.15.0 — get_history storico via MCP (Fase 1)"
git push origin master
```

- [ ] **Step 5: Verifica live**

Aggiornare l'addon su HA a 0.15.0; da Claude/MCP chiedere "andamento temperatura
del salotto ultima settimana" e "consumo energia ultimo mese" → devono tornare
buckets aggregati (non vuoto, non errore).

---

## Self-Review (compilata)

**Spec coverage:**
- Tool MCP unificato `get_history` + routing 3-layer → Task 2/3 (recorder+statistics; il 3° layer HistoryStore è Fase 2, dichiarato fuori scope).
- `ha_client.get_statistics` via WS → Task 1.
- Output compresso uniforme + cap/downsampling → Task 2 (`aggregate_numeric`, `downsample`, `normalize_statistics`).
- Tier READ + bypass whitelist azioni → Task 4 (dispatcher) + Task 6 (execute-API) + Task 7 (gateway READ).
- Esposizione anche nella chat HIRIS → Task 5.
- Test unit/handler/integrazione → presenti in ogni task.
- HistoryStore, cattura, config "Storicizzazione", digest second brain → **Fase 2/3** (fuori scope, dichiarato).

**Placeholder scan:** nessun TBD/TODO; ogni step ha codice/comandi concreti.

**Type consistency:** `get_history(ha, entity_ids, days, resolution)` usato identico in Task 3/4; helper `validate_inputs/classify/aggregate_numeric/downsample/normalize_statistics` definiti in Task 2 e usati in Task 3; `GET_HISTORY_TOOL_DEF` definito in Task 2, importato in Task 5; `READ_TOOLS` esteso in Task 6 e già consumato da `handlers_execute` (v0.14.9). Output series keys (`id`,`source`,`resolution`,`buckets`/`samples`,`partial`) coerenti tra Task 3 e i test.
