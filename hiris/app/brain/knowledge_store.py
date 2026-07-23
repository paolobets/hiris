from __future__ import annotations
import os
import sqlite3
import threading
import json
from datetime import datetime, timezone
from ..backends.embeddings import vec_to_blob, blob_to_vec, cosine_similarity
from ..storage import connect, init_schema

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
    updated_at   TEXT NOT NULL,
    lens         TEXT
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

CREATE TABLE IF NOT EXISTS document_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       INTEGER NOT NULL,
    mayan_doc_id  TEXT NOT NULL,
    chunk_index   INTEGER NOT NULL,
    content       TEXT NOT NULL,
    embedding     BLOB,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dc_item ON document_chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_dc_doc  ON document_chunks(mayan_doc_id);
"""


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: knowledge_items gains a nullable `lens` column (per-agent scope,
    used to unify per-agent RAG memory with shared knowledge in Slice 3)."""
    conn.execute("ALTER TABLE knowledge_items ADD COLUMN lens TEXT")


class KnowledgeStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._mu = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=2, migrations={2: _migrate_v2})

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
        valid_until: str | None = None, lens: str | None = None,
    ) -> int:
        now = self._now()
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO knowledge_items"
                "(kind, owner, title, content, data, amount, due_date, category,"
                " embedding, sensitivity, source, source_ref, confidence, status,"
                " valid_from, valid_until, created_at, updated_at, lens)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (kind, owner, title, content, json.dumps(data or {}), amount,
                 due_date, category, blob, sensitivity, source, source_ref,
                 confidence, status, valid_from, valid_until, now, now, lens),
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
        owner: str | None = None, lens: str | None = None,
        allow_sensitive: bool = False,
        kinds: list[str] | str | None = None,
    ) -> list[dict]:
        clauses = ["status='approved'", "embedding IS NOT NULL"]
        bind: dict = {}
        if owner is not None:
            # Unified scope (Slice 3): a row must always be scoped to this
            # owner (or shared as 'home') -- the owner check applies whether
            # or not the row carries a lens. On top of that, lens rows are
            # further restricted to the caller's own lens (or knowledge rows
            # with no lens at all). This prevents two different HA users
            # chatting with the SAME agent (same lens) from seeing each
            # other's save_memory items: owner is no longer ignored just
            # because lens matched. With lens=None this reduces to the
            # pre-Slice3 filter `(owner=? OR owner='home')` restricted to
            # un-lensed (knowledge) rows, preserving backward compatibility.
            clauses.append(
                "(owner = :owner OR owner = 'home') AND (lens = :lens OR lens IS NULL)"
            )
            bind["lens"] = lens
            bind["owner"] = owner
        elif lens is not None:
            # No owner passed but a lens was: don't fail open and expose all
            # lens memory across owners -- still scope by lens (or knowledge
            # rows with no lens). Current production callers always pass
            # owner alongside lens; this branch only guards future callers.
            clauses.append("(lens = :lens OR lens IS NULL)")
            bind["lens"] = lens
        if not allow_sensitive:
            clauses.append("sensitivity='normal'")
        if isinstance(kinds, str):
            # A plain string like "fact" must be treated as a single-kind
            # filter (["fact"]), not iterated char-by-char (which would
            # produce `kind IN ('f','a','c','t')` and match nothing).
            kinds = None if kinds == "all" else [kinds]
        if kinds is not None:
            if not kinds:
                # An explicitly empty list is the deny-all sentinel (e.g. an
                # agent configured with knowledge_access.kinds=[] meaning "no
                # knowledge access"). `kind IN ()` is invalid SQL, so short-
                # circuit with an always-false predicate instead of falling
                # through to "no filter" (which `if kinds:` used to do).
                clauses.append("1=0")
            else:
                placeholders = []
                for i, kind_val in enumerate(kinds):
                    key = f"kind{i}"
                    placeholders.append(f":{key}")
                    bind[key] = kind_val
                clauses.append("kind IN (%s)" % ",".join(placeholders))
        clauses.append("(valid_until IS NULL OR valid_until >= :valid_now)")
        bind["valid_now"] = self._now()
        sql = "SELECT * FROM knowledge_items WHERE " + " AND ".join(clauses)
        scored = []
        with self._mu:
            rows = self._conn.execute(sql, bind).fetchall()
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
            d = dict(r); d.pop("embedding", None)
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                d["data"] = {}
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

    def add_document_chunk(self, *, item_id: int, mayan_doc_id: str,
                           chunk_index: int, content: str,
                           embedding: list[float] | None = None) -> int:
        blob = vec_to_blob(embedding) if embedding else None
        with self._mu:
            cur = self._conn.execute(
                "INSERT INTO document_chunks"
                "(item_id, mayan_doc_id, chunk_index, content, embedding, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (item_id, mayan_doc_id, chunk_index, content, blob, self._now()),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def document_exists(self, mayan_doc_id: str) -> bool:
        with self._mu:
            row = self._conn.execute(
                "SELECT 1 FROM knowledge_items"
                " WHERE kind='document' AND source='mayan' AND source_ref=? LIMIT 1",
                (mayan_doc_id,),
            ).fetchone()
        return row is not None

    def search_chunks(self, *, query_vec: list[float], k: int = 5,
                      owner: str | None = None, allow_sensitive: bool = False) -> list[dict]:
        clauses = ["c.embedding IS NOT NULL", "i.status='approved'"]
        params: list = []
        if owner is not None:
            clauses.append("(i.owner=? OR i.owner='home')"); params.append(owner)
        if not allow_sensitive:
            clauses.append("i.sensitivity='normal'")
        sql = ("SELECT c.id, c.content, c.embedding, c.mayan_doc_id, c.item_id,"
               " i.sensitivity, i.owner FROM document_chunks c"
               " JOIN knowledge_items i ON i.id = c.item_id"
               " WHERE " + " AND ".join(clauses))
        with self._mu:
            rows = self._conn.execute(sql, params).fetchall()
            scored = [(cosine_similarity(query_vec, blob_to_vec(r["embedding"])), r)
                      for r in rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for sim, r in scored[:k]:
            out.append({"id": r["id"], "content": r["content"],
                        "mayan_doc_id": r["mayan_doc_id"], "item_id": r["item_id"],
                        "sensitivity": r["sensitivity"], "score": sim})
        return out

    def delete_by_lens(self, lens: str) -> int:
        """Delete every row scoped to this lens (an agent's own working
        memory), regardless of expiry. Used when an agent is deleted, to
        clean up its orphaned memory -- the KnowledgeStore equivalent of the
        legacy MemoryStore.delete_by_agent (Slice 3 Task 4)."""
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM knowledge_items WHERE lens = ?", (lens,),
            )
            self._conn.commit()
            return cur.rowcount

    def purge_expired_lens(self) -> int:
        """Delete lens-scoped rows (per-agent working memory) whose retention
        has elapsed. Rows with lens IS NULL (shared knowledge) or with no
        valid_until (no retention set) are never touched here."""
        now = self._now()
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM knowledge_items"
                " WHERE lens IS NOT NULL AND valid_until IS NOT NULL AND valid_until < ?",
                (now,),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._mu:
            self._conn.close()
