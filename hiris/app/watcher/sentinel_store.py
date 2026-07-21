from __future__ import annotations
import threading
from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS timers (
    key TEXT PRIMARY KEY,
    started_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cooldowns (
    key TEXT PRIMARY KEY,
    last_wake REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS wake_counts (
    day TEXT PRIMARY KEY,
    n INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, kind TEXT, entity_id TEXT,
    verdict TEXT, severity TEXT, outcome TEXT, message TEXT
);
"""

class SentinelStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def open_timer(self, key: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO timers(key, started_at) VALUES(?, ?) "
                "ON CONFLICT(key) DO NOTHING", (key, ts))
            self._conn.commit()

    def timer_started_at(self, key: str):
        with self._lock:
            r = self._conn.execute("SELECT started_at FROM timers WHERE key=?", (key,)).fetchone()
        return r["started_at"] if r else None

    def clear_timer(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM timers WHERE key=?", (key,))
            self._conn.commit()

    def last_wake(self, key: str):
        with self._lock:
            r = self._conn.execute("SELECT last_wake FROM cooldowns WHERE key=?", (key,)).fetchone()
        return r["last_wake"] if r else None

    def mark_wake(self, key: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cooldowns(key, last_wake) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET last_wake=excluded.last_wake", (key, ts))
            self._conn.commit()

    def wakes_today(self, day: str) -> int:
        with self._lock:
            r = self._conn.execute("SELECT n FROM wake_counts WHERE day=?", (day,)).fetchone()
        return r["n"] if r else 0

    def incr_wakes_today(self, day: str) -> int:
        with self._lock:
            self._conn.execute(
                "INSERT INTO wake_counts(day, n) VALUES(?, 1) "
                "ON CONFLICT(day) DO UPDATE SET n = n + 1", (day,))
            self._conn.commit()
            r = self._conn.execute("SELECT n FROM wake_counts WHERE day=?", (day,)).fetchone()
        return r["n"]

    def reset_wakes(self, before_day: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM wake_counts WHERE day < ?", (before_day,))
            self._conn.commit()

    def record_event(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(ts, kind, entity_id, verdict, severity, outcome, message) "
                "VALUES(?,?,?,?,?,?,?)",
                (row.get("ts"), row.get("kind"), row.get("entity_id"), row.get("verdict"),
                 row.get("severity"), row.get("outcome"), row.get("message")))
            self._conn.commit()

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, kind, entity_id, verdict, severity, outcome, message "
                "FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
