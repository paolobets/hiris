from __future__ import annotations
import json, secrets, threading
from typing import Optional
from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reasoning_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    wake_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    nonce TEXT,
    deadline_ts REAL NOT NULL,
    created_ts REAL NOT NULL,
    claimed_ts REAL, decided_ts REAL,
    decision_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reasoning_status ON reasoning_jobs(status, created_ts);
"""

def _row(r) -> dict:
    return {"job_id": r["job_id"], "kind": r["kind"], "status": r["status"],
            "nonce": r["nonce"], "wake": json.loads(r["wake_json"]),
            "context": json.loads(r["context_json"]), "deadline_ts": r["deadline_ts"]}

class ReasoningQueue:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def enqueue(self, kind: str, wake: dict, context: dict, deadline_ts: float,
                *, job_id: Optional[str] = None, now: float) -> str:
        jid = job_id or secrets.token_urlsafe(12)
        with self._lock:
            self._conn.execute(
                "INSERT INTO reasoning_jobs(job_id,kind,wake_json,context_json,status,deadline_ts,created_ts) "
                "VALUES(?,?,?,?, 'pending', ?, ?)",
                (jid, kind, json.dumps(wake), json.dumps(context), deadline_ts, now))
            self._conn.commit()
        return jid

    def claim(self, now: float) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status='pending' AND deadline_ts > ? "
                "ORDER BY created_ts ASC, id ASC LIMIT 1", (now,)).fetchone()
            if r is None:
                return None
            nonce = secrets.token_urlsafe(16)
            self._conn.execute(
                "UPDATE reasoning_jobs SET status='claimed', nonce=?, claimed_ts=? WHERE job_id=?",
                (nonce, now, r["job_id"]))
            self._conn.commit()
        out = _row(r); out["nonce"] = nonce; out["status"] = "claimed"
        return out

    def submit(self, job_id: str, nonce: str, decision: dict, now: float) -> bool:
        with self._lock:
            r = self._conn.execute("SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)).fetchone()
            if (r is None or r["status"] != "claimed" or r["nonce"] != nonce
                    or r["deadline_ts"] <= now):
                return False
            self._conn.execute(
                "UPDATE reasoning_jobs SET status='decided', decided_ts=?, decision_json=?, nonce=NULL WHERE job_id=?",
                (now, json.dumps(decision), job_id))
            self._conn.commit()
        return True

    def sweep_expired(self, now: float) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reasoning_jobs WHERE status IN ('pending','claimed') AND deadline_ts <= ?",
                (now,)).fetchall()
            for r in rows:
                self._conn.execute("UPDATE reasoning_jobs SET status='expired' WHERE job_id=?", (r["job_id"],))
            self._conn.commit()
        return [_row(r) for r in rows]

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM reasoning_jobs WHERE job_id=?", (job_id,)).fetchone()
        if r is None:
            return None
        out = _row(r)
        out["decision"] = json.loads(r["decision_json"]) if r["decision_json"] else None
        return out

    def prune(self, before_ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM reasoning_jobs WHERE status IN ('decided','expired','failed') AND created_ts < ?",
                (before_ts,))
            self._conn.commit()
            return cur.rowcount
