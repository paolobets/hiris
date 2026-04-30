import glob as _glob
import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_AGENT_ID_RE = re.compile(r'^[\w\-]{1,64}$')

# 0 = unlimited; overridable at startup via configure()
HISTORY_RETENTION_DAYS: int = int(os.environ.get("HISTORY_RETENTION_DAYS", "90"))
SESSION_GAP_HOURS = 2
PAST_SESSIONS_LIMIT = 3
SUMMARY_MAX_CHARS = 200
_DIGEST_TURNS = 3       # user+assistant pairs to include in the session digest
_DIGEST_MSG_LEN = 120   # max chars per message in the digest
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_stores: dict[str, "ChatStore"] = {}
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    last_msg_at TEXT NOT NULL,
    summary     TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_agent  ON chat_messages(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sess_agent ON chat_sessions(agent_id, last_msg_at);
"""


class ChatStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mu = threading.Lock()
        with self._mu:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers (called with self._mu already held)
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime(_TS_FMT)

    def _fresh_session_id(self, agent_id: str) -> str | None:
        """Return the open session_id only if within the gap window — no side effects."""
        row = self._conn.execute(
            "SELECT session_id, last_msg_at FROM chat_sessions "
            "WHERE agent_id = ? AND summary IS NULL ORDER BY last_msg_at DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        if not row:
            return None
        try:
            last = datetime.strptime(row["last_msg_at"], _TS_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            return row["session_id"]
        if (datetime.now(timezone.utc) - last).total_seconds() < SESSION_GAP_HOURS * 3600:
            return row["session_id"]
        return None

    def _active_session(self, agent_id: str) -> str | None:
        """Return fresh session_id, closing stale ones as side effect (write path only)."""
        sid = self._fresh_session_id(agent_id)
        if sid:
            return sid
        row = self._conn.execute(
            "SELECT session_id FROM chat_sessions "
            "WHERE agent_id = ? AND summary IS NULL ORDER BY last_msg_at DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
        if row:
            self._close_session(agent_id, row["session_id"])
        return None

    def _close_session(self, agent_id: str, session_id: str) -> None:
        rows = self._conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, _DIGEST_TURNS * 2),
        ).fetchall()
        if rows:
            # Rows are newest-first; reverse to chronological order, then build digest
            pairs: list[str] = []
            turns: list[tuple[str, str]] = []
            cur: dict[str, str] = {}
            for r in reversed(rows):
                role, content = r["role"], r["content"]
                if role == "user":
                    cur = {"u": content}
                elif role == "assistant" and cur:
                    cur["a"] = content
                    turns.append((cur["u"], cur["a"]))
                    cur = {}
            for u, a in turns[-_DIGEST_TURNS:]:
                u_trunc = u[:_DIGEST_MSG_LEN] + "…" if len(u) > _DIGEST_MSG_LEN else u
                a_trunc = a[:_DIGEST_MSG_LEN] + "…" if len(a) > _DIGEST_MSG_LEN else a
                pairs.append(f"U: {u_trunc}\nA: {a_trunc}")
            summary = "\n---\n".join(pairs) if pairs else rows[0]["content"][:SUMMARY_MAX_CHARS]
        else:
            summary = "(nessuna risposta)"
        self._conn.execute(
            "UPDATE chat_sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )

    def _new_session(self, agent_id: str) -> str:
        session_id = str(uuid.uuid4())
        ts = self._now()
        self._conn.execute(
            "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at) VALUES(?,?,?,?)",
            (session_id, agent_id, ts, ts),
        )
        return session_id

    def _get_or_create_session(self, agent_id: str) -> str:
        sid = self._active_session(agent_id)
        if sid:
            return sid
        return self._new_session(agent_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, agent_id: str, messages: list[dict]) -> None:
        with self._mu:
            sid = self._get_or_create_session(agent_id)
            ts = self._now()
            for m in messages:
                self._conn.execute(
                    "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) "
                    "VALUES(?,?,?,?,?)",
                    (agent_id, sid, m["role"], m["content"], ts),
                )
            self._conn.execute(
                "UPDATE chat_sessions SET last_msg_at = ? WHERE session_id = ?", (ts, sid)
            )
            self._conn.commit()

    def load_context(self, agent_id: str, max_turns: int = 30) -> list[dict]:
        """Return last max_turns pairs from the active (non-stale) session."""
        with self._mu:
            sid = self._fresh_session_id(agent_id)
            if not sid:
                return []
            if HISTORY_RETENTION_DAYS > 0:
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
                ).strftime(_TS_FMT)
                rows = self._conn.execute(
                    "SELECT role, content FROM chat_messages "
                    "WHERE session_id = ? AND timestamp >= ? ORDER BY id",
                    (sid, cutoff),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT role, content FROM chat_messages "
                    "WHERE session_id = ? ORDER BY id",
                    (sid,),
                ).fetchall()
            messages = [{"role": r["role"], "content": r["content"]} for r in rows]
            if len(messages) > max_turns * 2:
                messages = messages[-(max_turns * 2):]
            return messages

    def get_past_summaries(self, agent_id: str, n: int = PAST_SESSIONS_LIMIT) -> list[dict]:
        """Return closed sessions with summaries, most recent first."""
        with self._mu:
            rows = self._conn.execute(
                "SELECT session_id, started_at, last_msg_at, summary FROM chat_sessions "
                "WHERE agent_id = ? AND summary IS NOT NULL ORDER BY last_msg_at DESC LIMIT ?",
                (agent_id, n),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_user_turns(self, agent_id: str) -> int:
        """Count user messages in the active (non-stale) session."""
        with self._mu:
            sid = self._fresh_session_id(agent_id)
            if not sid:
                return 0
            cnt = self._conn.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'user'",
                (sid,),
            ).fetchone()
            return cnt[0] if cnt else 0

    def clear(self, agent_id: str) -> None:
        with self._mu:
            sessions = self._conn.execute(
                "SELECT session_id FROM chat_sessions WHERE agent_id = ?", (agent_id,)
            ).fetchall()
            for s in sessions:
                self._conn.execute(
                    "DELETE FROM chat_messages WHERE session_id = ?", (s["session_id"],)
                )
            self._conn.execute("DELETE FROM chat_sessions WHERE agent_id = ?", (agent_id,))
            self._conn.commit()

    def delete_old_messages(self, retention_days: int) -> int:
        """Hard-delete chat messages older than retention_days. Returns row count deleted."""
        if retention_days <= 0:
            return 0
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).strftime(_TS_FMT)
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM chat_messages WHERE timestamp < ?", (cutoff,)
            )
            self._conn.execute(
                "DELETE FROM chat_sessions WHERE session_id NOT IN "
                "(SELECT DISTINCT session_id FROM chat_messages)"
            )
            self._conn.commit()
            return cur.rowcount

    def migrate_from_json(self, data_dir: str) -> None:
        """One-time import of legacy chat_history_*.json files into SQLite."""
        for path in _glob.glob(os.path.join(data_dir, "chat_history_*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                agent_id = data.get("agent_id") or (
                    os.path.basename(path)[len("chat_history_"):-len(".json")]
                )
                if not _AGENT_ID_RE.match(agent_id):
                    logger.warning("migrate_from_json: skipping %s — invalid agent_id %r", path, agent_id)
                    continue
                messages = data.get("messages", [])
                if not messages:
                    continue
                with self._mu:
                    existing = self._conn.execute(
                        "SELECT COUNT(*) FROM chat_sessions WHERE agent_id = ?", (agent_id,)
                    ).fetchone()[0]
                    if existing > 0:
                        continue
                    session_id = str(uuid.uuid4())
                    ts_start = messages[0].get("timestamp", self._now())
                    ts_end = messages[-1].get("timestamp", self._now())
                    self._conn.execute(
                        "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at) "
                        "VALUES(?,?,?,?)",
                        (session_id, agent_id, ts_start, ts_end),
                    )
                    for m in messages:
                        role = m.get("role")
                        if role not in {"user", "assistant", "system"}:
                            logger.warning("migrate_from_json: skipping message with invalid role %r", role)
                            continue
                        content = m.get("content", "")
                        if len(content) > 32768:
                            logger.warning("migrate_from_json: truncating message content from %d chars", len(content))
                            content = content[:32768]
                        self._conn.execute(
                            "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) "
                            "VALUES(?,?,?,?,?)",
                            (agent_id, session_id, role, content, m.get("timestamp", ts_end)),
                        )
                    last_asst = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
                    text = last_asst["content"] if last_asst else "(migrated)"
                    summary = text[:SUMMARY_MAX_CHARS] + "…" if len(text) > SUMMARY_MAX_CHARS else text
                    self._conn.execute(
                        "UPDATE chat_sessions SET summary = ? WHERE session_id = ?",
                        (summary, session_id),
                    )
                    self._conn.commit()
            except Exception as exc:
                logger.warning("Failed to migrate %s: %s", path, exc)

    def close(self) -> None:
        with self._mu:
            self._conn.close()


# ---------------------------------------------------------------------------
# Module-level lazy init keyed by data_dir (supports multiple test fixtures)
# ---------------------------------------------------------------------------

def _get_store(data_dir: str) -> ChatStore:
    if data_dir not in _stores:
        with _lock:
            if data_dir not in _stores:
                db_path = os.path.join(data_dir, "chat_history.db")
                store = ChatStore(db_path)
                store.migrate_from_json(data_dir)
                _stores[data_dir] = store
    return _stores[data_dir]


# ---------------------------------------------------------------------------
# Backward-compatible public functions (same signatures as old JSON store)
# ---------------------------------------------------------------------------

def load_history(agent_id: str, data_dir: str) -> list[dict]:
    """Return [{role, content}] for the active session (Claude API format)."""
    return _get_store(data_dir).load_context(agent_id)


def append_messages(agent_id: str, messages: list[dict], data_dir: str) -> None:
    """Append [{role, content}] to the active session."""
    _get_store(data_dir).append(agent_id, messages)


def clear_history(agent_id: str, data_dir: str) -> None:
    """Delete all history and sessions for the given agent."""
    _get_store(data_dir).clear(agent_id)


def get_past_summaries(agent_id: str, data_dir: str, n: int = PAST_SESSIONS_LIMIT) -> list[dict]:
    """Return up to n closed session summaries, most recent first."""
    return _get_store(data_dir).get_past_summaries(agent_id, n)


def count_user_turns(agent_id: str, data_dir: str) -> int:
    """Count user turns in the active session (used for max_chat_turns enforcement)."""
    return _get_store(data_dir).count_user_turns(agent_id)


def delete_old_messages(data_dir: str, retention_days: int) -> int:
    """Hard-delete chat messages older than retention_days days."""
    return _get_store(data_dir).delete_old_messages(retention_days)


def close_all_stores() -> None:
    """Close all SQLite connections (call on app shutdown)."""
    with _lock:
        for store in _stores.values():
            store.close()
        _stores.clear()
