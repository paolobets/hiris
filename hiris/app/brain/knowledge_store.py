from __future__ import annotations
import os
import sqlite3
import threading
import json
from datetime import datetime, timezone
from ..backends.embeddings import vec_to_blob, blob_to_vec, cosine_similarity

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    owner        TEXT NOT NULL DEFAULT 'home',
    title        TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}',
    amount       REAL,
    due_date     TEXT,
    category     TEXT,
    embedding    BLOB,
    sensitivity  TEXT NOT NULL DEFAULT 'normal',
    source       TEXT NOT NULL DEFAULT 'manual',
    source_ref   TEXT,
    confidence   REAL NOT NULL DEFAULT 1.0,
    status       TEXT NOT NULL DEFAULT 'approved',
    valid_from   TEXT,
    valid_until  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ki_owner    ON knowledge_items(owner);
CREATE INDEX IF NOT EXISTS idx_ki_kind     ON knowledge_items(kind);
CREATE INDEX IF NOT EXISTS idx_ki_due      ON knowledge_items(due_date);
CREATE INDEX IF NOT EXISTS idx_ki_status   ON knowledge_items(status);
CREATE INDEX IF NOT EXISTS idx_ki_category ON knowledge_items(category);

CREATE TABLE IF NOT EXISTS knowledge_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL,
    dst_id      INTEGER NOT NULL,
    relation    TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    UNIQUE(src_id, dst_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_kl_src ON knowledge_links(src_id);
CREATE INDEX IF NOT EXISTS idx_kl_dst ON knowledge_links(dst_id);
"""


class KnowledgeStore:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mu = threading.Lock()
        with self._mu:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime(_TS_FMT)

    def add_item(
        self, *, kind: str, content: str, owner: str = "home",
        title: str = "", data: dict | None = None,
        amount: float | None = None, due_date: str | None = None,
        category: str | None = None, embedding: list[float] | None = None,
        sensitivity: str = "normal", source: str = "manual",
        source_ref: str | None = None, confidence: float = 1.0,
        status: str = "approved", valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> int:
        now = self._now()
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO knowledge_items"
                "(kind, owner, title, content, data, amount, due_date, category,"
                " embedding, sensitivity, source, source_ref, confidence, status,"
                " valid_from, valid_until, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kind, owner, title, content, json.dumps(data or {}), amount,
                 due_date, category, blob, sensitivity, source, source_ref,
                 confidence, status, valid_from, valid_until, now, now),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def get_item(self, item_id: int) -> dict | None:
        with self._mu:
            row = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE id=?", (item_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d.pop("embedding", None)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        return d

    def list_items(
        self, *, status: str | None = None, owner: str | None = None,
        kind: str | None = None, limit: int = 100,
    ) -> list[dict]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status=?"); params.append(status)
        if owner is not None:
            clauses.append("owner=?"); params.append(owner)
        if kind is not None:
            clauses.append("kind=?"); params.append(kind)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items" + where
                + " ORDER BY created_at DESC LIMIT ?", (*params, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def approve(self, item_id: int) -> None:
        with self._mu:
            self._conn.execute(
                "UPDATE knowledge_items SET status='approved', updated_at=? WHERE id=?",
                (self._now(), item_id),
            )
            self._conn.commit()

    def delete_item(self, item_id: int) -> None:
        with self._mu:
            self._conn.execute("DELETE FROM knowledge_items WHERE id=?", (item_id,))
            self._conn.execute(
                "DELETE FROM knowledge_links WHERE src_id=? OR dst_id=?",
                (item_id, item_id),
            )
            self._conn.commit()

    def search(
        self, *, query_vec: list[float], k: int = 5,
        owner: str | None = None, allow_sensitive: bool = False,
        kinds: list[str] | None = None,
    ) -> list[dict]:
        clauses = ["status='approved'", "embedding IS NOT NULL"]
        params: list = []
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        if not allow_sensitive:
            clauses.append("sensitivity='normal'")
        if kinds:
            clauses.append("kind IN (%s)" % ",".join("?" * len(kinds)))
            params.extend(kinds)
        sql = "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
        with self._mu:
            rows = self._conn.execute(sql, params).fetchall()
        scored = []
        for r in rows:
            sim = cosine_similarity(query_vec, blob_to_vec(r["embedding"]))
            scored.append((sim, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, r in scored[:k]:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            d["score"] = sim
            out.append(d)
        return out

    def upcoming_obligations(
        self, *, before: str, owner: str | None = None,
    ) -> list[dict]:
        clauses = ["kind='obligation'", "status='approved'",
                   "due_date IS NOT NULL", "due_date <= ?"]
        params: list = [before]
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
                + " ORDER BY due_date ASC", params,
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None); d.pop("data", None)
            out.append(d)
        return out

    def expenses_by_category(self, *, owner: str | None = None) -> dict[str, float]:
        clauses = ["kind='expense'", "status='approved'", "amount IS NOT NULL"]
        params: list = []
        if owner is not None:
            clauses.append("(owner=? OR owner='home')"); params.append(owner)
        with self._mu:
            rows = self._conn.execute(
                "SELECT COALESCE(category,'(nessuna)') AS cat, SUM(amount) AS tot"
                " FROM knowledge_items WHERE " + " AND ".join(clauses)
                + " GROUP BY cat", params,
            ).fetchall()
        return {r["cat"]: float(r["tot"]) for r in rows}

    def add_link(
        self, *, src_id: int, dst_id: int, relation: str,
        weight: float = 1.0, source: str = "manual",
    ) -> None:
        with self._mu:
            self._conn.execute(
                "INSERT OR IGNORE INTO knowledge_links"
                "(src_id, dst_id, relation, weight, source, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (src_id, dst_id, relation, weight, source, self._now()),
            )
            self._conn.commit()

    def neighbors(self, item_id: int) -> list[dict]:
        with self._mu:
            rows = self._conn.execute(
                "SELECT i.* FROM knowledge_items i"
                " JOIN knowledge_links l ON l.dst_id = i.id"
                " WHERE l.src_id = ? AND i.status='approved'", (item_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
            out.append(d)
        return out

    def close(self) -> None:
        with self._mu:
            self._conn.close()
