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

    def close(self) -> None:
        with self._mu:
            self._conn.close()
