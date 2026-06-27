from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

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


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _day_offset(day: str, delta_days: int) -> str:
    d = datetime.fromisoformat(day + "T00:00:00+00:00") + timedelta(days=delta_days)
    return d.strftime("%Y-%m-%d")


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


def _rollup_events(events: list[dict]) -> dict:
    """Aggregate one entity's events for a single day into a daily summary.

    events: ordered list of {ts, state, num}. Computes numeric stats over the
    numeric samples (min/max/mean/n), and on/off durations.

    on_seconds accounting model: time is attributed only to the interval BETWEEN
    two consecutive events within this list. The tail segment after the last
    event (until end of day) and any segment before the first event (an entity
    already 'on' at midnight) are NOT counted here. Completing open segments
    across day boundaries is a capture-layer concern (Phase 2b); within a single
    day this under-counts a state that spans the day edges. Non-'off' states
    ('off'/'unavailable'/'unknown'/''/'none' are treated as off) count as 'on'.
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
        "n": len(nums) if nums else len(events),
        "min": min(nums) if nums else None,
        "max": max(nums) if nums else None,
        "mean": round(sum(nums) / len(nums), 3) if nums else None,
        "on_seconds": round(on_seconds, 1) if any(
            str(e.get("state", "")).lower() not in off_states for e in events) else 0.0,
        "transitions": transitions,
        "last_state": events[-1]["state"] if events else None,
    }
    return agg


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
            try:
                self.rollup_day(entity_id, day)
            except Exception:
                logger.exception("history rollup failed for %s %s; skipping", entity_id, day)
        cutoff = _day_offset(today, -retention_days)
        with self._lock:
            self._conn.execute(
                "DELETE FROM history_events WHERE substr(ts,1,10) < ?", (cutoff,))
            self._conn.commit()

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
        raw_by_day: dict[str, list[dict]] = {}
        for e in raw:
            raw_by_day.setdefault(e["ts"][:10], []).append(e)
        for day, events in raw_by_day.items():
            by_day[day] = _bucket_from_daily(dict(_rollup_events(events), day=day, entity_id=entity_id))
        buckets = [by_day[d] for d in sorted(by_day)]
        return {"id": entity_id, "source": "store", "unit": None, "buckets": buckets}

    # --- test helper ---
    def _daily(self, entity_id: str) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM history_daily WHERE entity_id=? ORDER BY day", (entity_id,))
            return [dict(r) for r in cur.fetchall()]
