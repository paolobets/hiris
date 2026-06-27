# Storico — Fase 2a: `HistoryStore` (data layer) — Piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Un archivio time-series locale di proprietà di HIRIS (`HistoryStore`, SQLite) che memorizza eventi di stato per entità selezionate, li compatta in rollup giornalieri permanenti, pota i grezzi oltre la retention, e risponde a query in forma di bucket uniformi — senza alcuna dipendenza da HA o MCP (testabile in isolamento).

**Architecture:** Una sola classe `HistoryStore` su SQLite (`/data/history.db`) con due tabelle: `history_events` (grezzi, finestra retention) e `history_daily` (rollup permanente ~1 riga/entità/giorno). Tratta a runtime un'entità come numerica (min/max/mean) o come stato on/off (on_seconds/transitions) a seconda della parsabilità del valore. Nessun wiring qui: cattura, policy e integrazione `get_history` sono Fase 2b.

**Tech Stack:** Python 3, sqlite3 (stdlib), pytest. Pattern di riferimento: `hiris/app/brain/knowledge_store.py` (sqlite3, `check_same_thread=False`, schema string, lock per thread-safety).

**Spec:** `docs/design/2026-06-27-storico-dati-mcp-design.md` (sezione "Schema HistoryStore").

**Fuori scope (Fase 2b/2c):** il listener di cattura, il filtro policy, l'API `/api/history/policy`, l'integrazione in `get_history`, la pagina UI. Qui si costruisce SOLO la classe store + i suoi test.

---

### Task 1: Schema + `append`

**Files:**
- Create: `hiris/app/history/__init__.py` (vuoto)
- Create: `hiris/app/history/store.py`
- Test: `tests/test_history_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_store.py
import os
from hiris.app.history.store import HistoryStore


def _store(tmp_path):
    return HistoryStore(os.path.join(str(tmp_path), "history.db"))


def test_append_numeric_and_state(tmp_path):
    s = _store(tmp_path)
    s.append("sensor.temp", "2026-06-26T10:00:00+00:00", "21.5")
    s.append("binary_sensor.door", "2026-06-26T10:00:01+00:00", "on")
    rows = s._all_events()  # test helper
    assert rows[0]["entity_id"] == "sensor.temp"
    assert rows[0]["num"] == 21.5
    assert rows[1]["entity_id"] == "binary_sensor.door"
    assert rows[1]["num"] is None     # non-numeric -> NULL


def test_append_ignores_unparseable_timestamp_gracefully(tmp_path):
    s = _store(tmp_path)
    # empty/short ts is stored as-is; never raises (capture must be crash-proof)
    s.append("sensor.x", "", "5")
    assert len(s._all_events()) == 1
```

- [ ] **Step 2: Run, confirm FAIL** — `ModuleNotFoundError: hiris.app.history`.
Run: `python -m pytest tests/test_history_store.py -v`

- [ ] **Step 3: Implement schema + append**

Create `hiris/app/history/__init__.py` (empty file).

Create `hiris/app/history/store.py`:

```python
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    ts        TEXT NOT NULL,
    state     TEXT NOT NULL,
    num       REAL
);
CREATE INDEX IF NOT EXISTS idx_he_eid_ts ON history_events(entity_id, ts);

CREATE TABLE IF NOT EXISTS history_daily (
    entity_id   TEXT NOT NULL,
    day         TEXT NOT NULL,
    n           INTEGER NOT NULL,
    min         REAL,
    max         REAL,
    mean        REAL,
    on_seconds  REAL,
    transitions INTEGER,
    last_state  TEXT,
    PRIMARY KEY (entity_id, day)
);
"""


def _to_float(s: object) -> Optional[float]:
    try:
        return float(s)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class HistoryStore:
    """Local time-series store. Thread-safe via a single lock (writes come from
    the WS capture callback; reads from request handlers)."""

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def append(self, entity_id: str, ts: str, state: str) -> None:
        """Record one state change. Never raises on bad data (capture must not crash)."""
        try:
            num = _to_float(state)
            with self._lock:
                self._conn.execute(
                    "INSERT INTO history_events (entity_id, ts, state, num) VALUES (?,?,?,?)",
                    (entity_id, ts, state, num),
                )
                self._conn.commit()
        except Exception:
            pass

    # --- test helper ---
    def _all_events(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute("SELECT entity_id, ts, state, num FROM history_events ORDER BY id")
            return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Run, confirm PASS** (2 passed).
Run: `python -m pytest tests/test_history_store.py -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/__init__.py hiris/app/history/store.py tests/test_history_store.py
git commit -m "feat(history-store): schema + append (events table)"
```

---

### Task 2: Rollup giornaliero (numerico + on/off)

**Files:**
- Modify: `hiris/app/history/store.py` (aggiungi `rollup_day` + pure helper `_rollup_events`)
- Test: `tests/test_history_store.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_store.py
from hiris.app.history.store import _rollup_events


def test_rollup_events_numeric():
    events = [
        {"ts": "2026-06-20T01:00:00+00:00", "state": "19.0", "num": 19.0},
        {"ts": "2026-06-20T13:00:00+00:00", "state": "24.0", "num": 24.0},
    ]
    agg = _rollup_events(events)
    assert agg["n"] == 2
    assert agg["min"] == 19.0 and agg["max"] == 24.0 and agg["mean"] == 21.5
    assert agg["transitions"] == 1            # 19->24 is one change
    assert agg["last_state"] == "24.0"


def test_rollup_events_onoff_durations():
    # on at 09:00:00, off at 09:05:00 -> 300s on; ends 'off'
    events = [
        {"ts": "2026-06-20T09:00:00+00:00", "state": "on", "num": None},
        {"ts": "2026-06-20T09:05:00+00:00", "state": "off", "num": None},
    ]
    agg = _rollup_events(events)
    assert agg["on_seconds"] == 300.0
    assert agg["transitions"] == 1
    assert agg["last_state"] == "off"
    assert agg["mean"] is None                # non-numeric -> no numeric stats


def test_rollup_day_persists_and_is_idempotent(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    s.append("sensor.t", "2026-06-20T01:00:00+00:00", "19.0")
    s.append("sensor.t", "2026-06-20T13:00:00+00:00", "24.0")
    s.rollup_day("sensor.t", "2026-06-20")
    s.rollup_day("sensor.t", "2026-06-20")    # idempotent (REPLACE)
    rows = s._daily("sensor.t")
    assert len(rows) == 1
    assert rows[0]["day"] == "2026-06-20" and rows[0]["mean"] == 21.5
```

- [ ] **Step 2: Run, confirm FAIL** (`_rollup_events`/`rollup_day`/`_daily` undefined).
Run: `python -m pytest tests/test_history_store.py -k rollup -v`

- [ ] **Step 3: Implement**

Add to `hiris/app/history/store.py` (module-level pure helper + methods). Add `from datetime import datetime, timezone` to imports.

```python
def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _rollup_events(events: list[dict]) -> dict:
    """Aggregate one entity's events for a single day into a daily summary.

    events: ordered list of {ts, state, num}. Computes numeric stats when values
    are numeric, and on/off durations (state != 'off'/'unavailable'/'unknown' is
    treated as 'on') in all cases.
    """
    nums = [e["num"] for e in events if e.get("num") is not None]
    transitions = 0
    prev_state = None
    on_seconds = 0.0
    prev_dt = None
    off_states = {"off", "unavailable", "unknown", "", "none"}
    for e in events:
        st = e.get("state", "")
        dt = _parse_ts(e.get("ts", ""))
        if prev_state is not None and st != prev_state:
            transitions += 1
        if prev_dt is not None and prev_state is not None:
            if str(prev_state).lower() not in off_states:
                on_seconds += max(0.0, (dt - prev_dt).total_seconds()) if dt and prev_dt else 0.0
        prev_state = st
        prev_dt = dt
    agg = {
        "n": len(events),
        "min": min(nums) if nums else None,
        "max": max(nums) if nums else None,
        "mean": round(sum(nums) / len(nums), 3) if nums else None,
        "on_seconds": round(on_seconds, 1) if any(
            str(e.get("state", "")).lower() not in off_states for e in events) else 0.0,
        "transitions": transitions,
        "last_state": events[-1]["state"] if events else None,
    }
    return agg
```

Add methods to `HistoryStore`:

```python
    def rollup_day(self, entity_id: str, day: str) -> None:
        """Aggregate that entity's events for `day` (YYYY-MM-DD) into history_daily.
        Idempotent (REPLACE). No-op if the day has no events."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, state, num FROM history_events "
                "WHERE entity_id=? AND substr(ts,1,10)=? ORDER BY ts",
                (entity_id, day),
            )
            events = [dict(r) for r in cur.fetchall()]
        if not events:
            return
        a = _rollup_events(events)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO history_daily "
                "(entity_id, day, n, min, max, mean, on_seconds, transitions, last_state) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (entity_id, day, a["n"], a["min"], a["max"], a["mean"],
                 a["on_seconds"], a["transitions"], a["last_state"]),
            )
            self._conn.commit()

    # --- test helper ---
    def _daily(self, entity_id: str) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM history_daily WHERE entity_id=? ORDER BY day", (entity_id,))
            return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Run, confirm PASS.**
Run: `python -m pytest tests/test_history_store.py -k rollup -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/store.py tests/test_history_store.py
git commit -m "feat(history-store): daily rollup (numeric + on/off durations)"
```

---

### Task 3: Compaction notturna (rollup completi + prune retention)

**Files:**
- Modify: `hiris/app/history/store.py` (aggiungi `compact`)
- Test: `tests/test_history_store.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_store.py
def test_compact_rolls_complete_days_and_prunes_old_raw(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    # day -5 and day -1 relative to a fixed "today"
    s.append("sensor.t", "2026-06-15T10:00:00+00:00", "10.0")
    s.append("sensor.t", "2026-06-19T10:00:00+00:00", "20.0")
    s.append("sensor.t", "2026-06-20T10:00:00+00:00", "30.0")   # 'today' -> not rolled
    s.compact(today="2026-06-20", retention_days=3)
    # complete days (15, 19) rolled into daily; today (20) left raw
    days = {r["day"] for r in s._daily("sensor.t")}
    assert "2026-06-15" in days and "2026-06-19" in days
    assert "2026-06-20" not in days
    # raw older than retention (today-3 = 2026-06-17) pruned: 15 gone, 19 & 20 kept
    remaining = {e["ts"][:10] for e in s._all_events()}
    assert "2026-06-15" not in remaining
    assert "2026-06-19" in remaining and "2026-06-20" in remaining
```

- [ ] **Step 2: Run, confirm FAIL** (`compact` undefined).
Run: `python -m pytest tests/test_history_store.py -k compact -v`

- [ ] **Step 3: Implement**

Add to `HistoryStore`:

```python
    def compact(self, today: str, retention_days: int) -> None:
        """Roll up every complete day (< today) that has raw events, then delete
        raw events older than `retention_days` days before `today`. The daily
        rollups are permanent; only raw events are pruned."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT DISTINCT entity_id, substr(ts,1,10) AS day FROM history_events "
                "WHERE substr(ts,1,10) < ?", (today,))
            pairs = [(r["entity_id"], r["day"]) for r in cur.fetchall()]
        for entity_id, day in pairs:
            self.rollup_day(entity_id, day)
        cutoff = _day_offset(today, -retention_days)
        with self._lock:
            self._conn.execute(
                "DELETE FROM history_events WHERE substr(ts,1,10) < ?", (cutoff,))
            self._conn.commit()
```

And the module-level helper (next to `_parse_ts`):

```python
from datetime import timedelta   # add to the datetime import line

def _day_offset(day: str, delta_days: int) -> str:
    d = datetime.fromisoformat(day + "T00:00:00+00:00") + timedelta(days=delta_days)
    return d.strftime("%Y-%m-%d")
```

- [ ] **Step 4: Run, confirm PASS.**
Run: `python -m pytest tests/test_history_store.py -k compact -v`

- [ ] **Step 5: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/store.py tests/test_history_store.py
git commit -m "feat(history-store): nightly compaction (rollup complete days + prune raw)"
```

---

### Task 4: `query` — bucket uniformi per `get_history`

**Files:**
- Modify: `hiris/app/history/store.py` (aggiungi `has_entity` + `query`)
- Test: `tests/test_history_store.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_history_store.py
def test_has_entity(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    assert s.has_entity("sensor.t") is False
    s.append("sensor.t", "2026-06-20T10:00:00+00:00", "30.0")
    assert s.has_entity("sensor.t") is True


def test_query_numeric_buckets_from_daily_and_today(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    # an older complete day, rolled up
    s.append("sensor.t", "2026-06-18T10:00:00+00:00", "10.0")
    s.append("sensor.t", "2026-06-18T12:00:00+00:00", "20.0")
    s.rollup_day("sensor.t", "2026-06-18")
    # plus live events for 'today'
    s.append("sensor.t", "2026-06-20T08:00:00+00:00", "30.0")
    out = s.query("sensor.t", days=7, today="2026-06-20")
    assert out["id"] == "sensor.t"
    assert out["source"] == "store"
    days = [b["t"] for b in out["buckets"]]
    assert "2026-06-18" in days and "2026-06-20" in days
    b18 = next(b for b in out["buckets"] if b["t"] == "2026-06-18")
    assert b18["mean"] == 15.0


def test_query_onoff_buckets(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    s.append("binary_sensor.d", "2026-06-20T09:00:00+00:00", "on")
    s.append("binary_sensor.d", "2026-06-20T09:05:00+00:00", "off")
    out = s.query("binary_sensor.d", days=7, today="2026-06-20")
    b = out["buckets"][0]
    assert b["t"] == "2026-06-20"
    assert b["on_seconds"] == 300.0 and b["transitions"] == 1
    assert "mean" not in b           # non-numeric bucket omits numeric keys


def test_query_returns_none_when_no_data(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    assert s.query("sensor.absent", days=7, today="2026-06-20") is None
```

- [ ] **Step 2: Run, confirm FAIL** (`has_entity`/`query` undefined).
Run: `python -m pytest tests/test_history_store.py -k "has_entity or query" -v`

- [ ] **Step 3: Implement**

Add to `HistoryStore`. `query` merges permanent daily rollups with a live aggregation of in-range raw events (so the current, not-yet-rolled day is included without double counting rolled days):

```python
    def has_entity(self, entity_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM history_events WHERE entity_id=? LIMIT 1", (entity_id,))
            if cur.fetchone():
                return True
            cur = self._conn.execute(
                "SELECT 1 FROM history_daily WHERE entity_id=? LIMIT 1", (entity_id,))
            return cur.fetchone() is not None

    def query(self, entity_id: str, days: int, today: str) -> Optional[dict]:
        """Return uniform daily buckets for an entity, or None if it has no data.

        Daily rollups are authoritative for past days; any day still present in
        raw events (typically 'today') is aggregated live and overrides the
        rollup for that day, so there is never double counting."""
        if not self.has_entity(entity_id):
            return None
        cutoff = _day_offset(today, -days)
        by_day: dict[str, dict] = {}
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM history_daily WHERE entity_id=? AND day>=? ORDER BY day",
                (entity_id, cutoff))
            for r in cur.fetchall():
                by_day[r["day"]] = _bucket_from_daily(dict(r))
            cur = self._conn.execute(
                "SELECT ts, state, num FROM history_events "
                "WHERE entity_id=? AND substr(ts,1,10)>=? ORDER BY ts",
                (entity_id, cutoff))
            raw = [dict(r) for r in cur.fetchall()]
        # live-aggregate raw events grouped by day -> overrides rollup for those days
        raw_by_day: dict[str, list[dict]] = {}
        for e in raw:
            raw_by_day.setdefault(e["ts"][:10], []).append(e)
        for day, events in raw_by_day.items():
            by_day[day] = _bucket_from_daily(dict(_rollup_events(events), day=day, entity_id=entity_id))
        buckets = [by_day[d] for d in sorted(by_day)]
        return {"id": entity_id, "source": "store", "unit": None, "buckets": buckets}
```

Add the module-level shaper (next to the other helpers):

```python
def _bucket_from_daily(row: dict) -> dict:
    """Shape a history_daily row (or a _rollup_events result + day) into a bucket.
    Numeric entities expose min/max/mean; non-numeric expose on_seconds/transitions."""
    b = {"t": row["day"]}
    if row.get("mean") is not None:
        b["min"] = row["min"]
        b["max"] = row["max"]
        b["mean"] = row["mean"]
        b["n"] = row["n"]
    else:
        b["on_seconds"] = row.get("on_seconds") or 0.0
        b["transitions"] = row.get("transitions") or 0
        b["last_state"] = row.get("last_state")
    return b
```

Note: `_rollup_events` returns a dict without `day`/`entity_id`; the `query` code wraps it with `dict(_rollup_events(events), day=day, entity_id=entity_id)` before `_bucket_from_daily`, so the shaper always finds `row["day"]`.

- [ ] **Step 4: Run, confirm PASS** (all query/has_entity tests).
Run: `python -m pytest tests/test_history_store.py -v`

- [ ] **Step 5: Full-suite sanity.**
Run: `python -m pytest -q`  (expect all pass)

- [ ] **Step 6: Commit (LOCAL ONLY)**

```bash
git add hiris/app/history/store.py tests/test_history_store.py
git commit -m "feat(history-store): query -> uniform daily buckets (store source)"
```

---

## Self-Review (compilata)

**Spec coverage:** schema `history_events`+`history_daily` (Task 1/2), retention/compaction con rollup permanente (Task 3), query a bucket uniformi numerico/on-off (Task 4), trattamento numerico-vs-stato a runtime via `num` (Task 1/2/4). Wiring/cattura/policy/UI esplicitamente Fase 2b/2c.

**Placeholder scan:** nessun TBD; ogni step ha codice e comandi concreti.

**Type consistency:** `_rollup_events(events)->dict{n,min,max,mean,on_seconds,transitions,last_state}` usato da `rollup_day` e da `query`; `_bucket_from_daily(row)` consuma sia righe `history_daily` sia `dict(_rollup_events(...), day=...)`; `query(entity_id, days, today)->dict|None` con shape `{id,source:"store",unit,buckets[]}` coerente col contratto Fase 1 (`get_history`), con bucket numerici `{t,min,max,mean,n}` o on/off `{t,on_seconds,transitions,last_state}`. `compact(today, retention_days)` e `_day_offset(day, delta)` coerenti. `append` non solleva mai (cattura crash-proof).

**Nota di integrazione (per Fase 2b):** `get_history` dovrà passare `today` (data UTC corrente) a `store.query`. Poiché gli script/funzioni evitano `datetime.now()` solo nei workflow, qui in runtime normale `datetime.now(timezone.utc)` è lecito; il piano 2b lo calcola nell'orchestratore e lo passa, mantenendo `query` deterministico e testabile.
