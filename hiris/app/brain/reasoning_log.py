from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from ..storage import connect, init_schema
from ..proxy._sanitize import sanitize_text

_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_reasoning (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts   TEXT NOT NULL,
    mode TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reasoning_id ON brain_reasoning(id DESC);
"""

_JSON_FENCE_RE = re.compile(r"```json.*?```", re.DOTALL | re.IGNORECASE)
_MAX_LEN = 4000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReasoningLog:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def capture(self, *, mode: str, text: str, ts: str | None = None) -> int:
        stripped = _JSON_FENCE_RE.sub("", text or "").strip()
        clean = sanitize_text(stripped, _MAX_LEN)
        if not clean:
            return 0
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO brain_reasoning(ts, mode, text) VALUES(?,?,?)",
                (ts or _now_iso(), str(mode)[:32], clean),
            )
            self._conn.commit()
            return cur.lastrowid

    def list(self, *, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, mode, text FROM brain_reasoning ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, *, max_rows: int = 500, max_age_days: int = 30) -> int:
        cutoff = (
            datetime.now(timezone.utc).timestamp() - max_age_days * 86400
        )
        removed = 0
        with self._lock:
            # by age
            rows = self._conn.execute("SELECT id, ts FROM brain_reasoning").fetchall()
            old_ids = []
            for r in rows:
                try:
                    t = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    ).timestamp()
                except ValueError:
                    continue
                if t < cutoff:
                    old_ids.append(r["id"])
            for _id in old_ids:
                self._conn.execute("DELETE FROM brain_reasoning WHERE id=?", (_id,))
                removed += 1
            # by count (keep newest max_rows)
            cur = self._conn.execute(
                "DELETE FROM brain_reasoning WHERE id NOT IN "
                "(SELECT id FROM brain_reasoning ORDER BY id DESC LIMIT ?)",
                (int(max_rows),),
            )
            removed += cur.rowcount
            self._conn.commit()
        return removed
