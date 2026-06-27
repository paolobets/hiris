from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
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

    # --- test helper ---
    def _daily(self, entity_id: str) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM history_daily WHERE entity_id=? ORDER BY day", (entity_id,))
            return [dict(r) for r in cur.fetchall()]
