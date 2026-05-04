from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from ..backends.embeddings import blob_to_vec, cosine_similarity, vec_to_blob

if TYPE_CHECKING:
    from ..backends.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    embedding   BLOB,
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_agent ON agent_memories(agent_id, created_at DESC);
"""


class MemoryStore:
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

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def save(
        self,
        agent_id: str,
        content: str,
        tags: list[str],
        embedder: "EmbeddingProvider",
        retention_days: int | None,
    ) -> int:
        embedding: list[float] = []
        try:
            embedding = await embedder.embed(content)
        except Exception as exc:
            logger.warning("MemoryStore.save: embedding failed, saving without vector: %s", exc)

        blob = vec_to_blob(embedding) if embedding else None
        now = self._now()
        expires_at: str | None = None
        if retention_days and retention_days > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=retention_days)
            ).strftime(_TS_FMT)

        tags_json = json.dumps(tags)

        def _write() -> int:
            with self._mu:
                cur = self._conn.execute(
                    "INSERT INTO agent_memories"
                    "(agent_id, content, tags, embedding, created_at, expires_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (agent_id, content, tags_json, blob, now, expires_at),
                )
                self._conn.commit()
                return cur.lastrowid or 0

        return await asyncio.get_running_loop().run_in_executor(None, _write)

    async def search(
        self,
        agent_id: str,
        query: str,
        k: int,
        tags: list[str] | None,
        embedder: "EmbeddingProvider",
    ) -> list[dict]:
        query_vec: list[float] = []
        try:
            query_vec = await embedder.embed(query)
        except Exception as exc:
            logger.warning("MemoryStore.search: embedding failed, recency fallback: %s", exc)

        return await asyncio.get_running_loop().run_in_executor(
            None, self._search_sync, agent_id, query_vec, k, tags
        )

    # ------------------------------------------------------------------
    # Sync helpers (run in executor or called from retention job thread)
    # ------------------------------------------------------------------

    def _search_sync(
        self,
        agent_id: str,
        query_vec: list[float],
        k: int,
        tags: list[str] | None,
    ) -> list[dict]:
        now_str = self._now()
        with self._mu:
            rows = self._conn.execute(
                "SELECT id, content, tags, embedding, created_at FROM agent_memories"
                " WHERE agent_id = ? AND (expires_at IS NULL OR expires_at > ?)"
                " ORDER BY created_at DESC",
                (agent_id, now_str),
            ).fetchall()
        # Parse tags once per row up front
        parsed: list[tuple[dict, list]] = []
        for r in rows:
            row_dict = dict(r)
            try:
                row_tags: list = json.loads(row_dict["tags"])
            except Exception as exc:
                logger.debug("memory tags JSON parse failed for id=%s: %s",
                             row_dict.get("id"), exc)
                row_tags = []
            parsed.append((row_dict, row_tags))

        if tags:
            tag_set = set(tags)
            parsed = [(r, t) for r, t in parsed if tag_set.intersection(t)]

        if not query_vec:
            result = parsed[:k]
        else:
            scored = [
                (
                    cosine_similarity(query_vec, blob_to_vec(r["embedding"])) if r["embedding"] else 0.0,
                    r,
                    t,
                )
                for r, t in parsed
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            result = [(r, t) for _, r, t in scored[:k]]

        return [
            {"id": r["id"], "content": r["content"], "tags": t, "created_at": r["created_at"]}
            for r, t in result
        ]

    def delete_expired(self) -> int:
        now_str = self._now()
        with self._mu:
            cur = self._conn.execute(
                "DELETE FROM agent_memories"
                " WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now_str,),
            )
            self._conn.commit()
            return cur.rowcount

    def delete_by_agent(self, agent_id: str) -> None:
        with self._mu:
            self._conn.execute(
                "DELETE FROM agent_memories WHERE agent_id = ?", (agent_id,)
            )
            self._conn.commit()

    def close(self) -> None:
        with self._mu:
            self._conn.close()
