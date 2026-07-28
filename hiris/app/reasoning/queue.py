from __future__ import annotations
import json, secrets, threading, time
from datetime import datetime
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

    def has_pending_chat(self, chatbot_id: Optional[str], now: Optional[float] = None) -> bool:
        """True if a kind="chat" job for this chatbot_id is still in flight
        (status 'pending' or 'claimed') AND its deadline hasn't passed yet.
        Slice 4b Task 3 -- "one answer in flight per conversation" guard on
        the async subscription path.

        Task 5 fix (Task 3 review, MEDIUM): a job whose deadline_ts is
        already in the past is excluded even if its status is still
        'pending'/'claimed' -- e.g. because the ponte-push sweep
        (server.py's _reasoning_sweep, gated on BRIDGE_ENABLED) never ran or
        is off. Without this, an expired-but-unswept job would 409 the
        conversation forever with no way to clear it. Takes an explicit
        `now`, like every other method on this class (enqueue/claim/submit/
        sweep_expired/count_chat_today), defaulting to time.time() only when
        the caller (production code) doesn't pass one.

        Chat jobs have no dedicated conversation_id column: Task 2 put
        chatbot_id inside context_json (a conversation IS a chatbot's active
        session, keyed by chatbot_id -- there's no separate concept). So this
        scans the in-flight chat-kind rows (typically a handful -- bounded by
        chat_daily_cap and by the fact that most turns resolve quickly) and
        parses each row's context to match chatbot_id, rather than adding a
        dedicated indexed column for a query this cheap in practice."""
        if not chatbot_id:
            return False
        ts = time.time() if now is None else now
        with self._lock:
            rows = self._conn.execute(
                "SELECT context_json FROM reasoning_jobs "
                "WHERE kind='chat' AND status IN ('pending','claimed') "
                "AND deadline_ts > ?", (ts,)).fetchall()
        for r in rows:
            try:
                ctx = json.loads(r["context_json"])
            except (TypeError, ValueError):
                continue
            # Retro-compat (one-deploy window): jobs enqueued before the
            # agent_id->chatbot_id rename still carry the legacy key. Fall
            # back to it so an in-flight pre-deploy job is still recognized.
            if isinstance(ctx, dict) and (ctx.get("chatbot_id") or ctx.get("agent_id")) == chatbot_id:
                return True
        return False

    def count_chat_today(self, now: Optional[float] = None) -> int:
        """Count of kind="chat" jobs enqueued (created_ts) on the same local
        calendar day as `now`. Slice 4b Task 3's separate daily chat cap --
        counts every chat turn enqueued today regardless of its current
        status (resolved/expired turns still consumed the day's budget).

        Takes an explicit `now`, like every other method on this class
        (enqueue/claim/submit/sweep_expired), defaulting to time.time() only
        when the caller (production code) doesn't pass one -- tests can pin
        an exact day boundary instead of depending on wall clock."""
        ts = time.time() if now is None else now
        dt = datetime.fromtimestamp(ts)
        day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        day_end = day_start + 86400
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) AS c FROM reasoning_jobs "
                "WHERE kind='chat' AND created_ts >= ? AND created_ts < ?",
                (day_start, day_end)).fetchone()
        return r["c"]

    def prune(self, before_ts: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM reasoning_jobs WHERE status IN ('decided','expired','failed') AND created_ts < ?",
                (before_ts,))
            self._conn.commit()
            return cur.rowcount
