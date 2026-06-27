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
