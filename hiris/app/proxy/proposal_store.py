from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_proposals (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    config          TEXT NOT NULL,
    routing_reason  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    archived_at     TEXT,
    applied_at      TEXT,
    rejected_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_prop_status ON automation_proposals(status, created_at DESC);
"""

_REQUIRED_FIELDS = frozenset({"type", "name", "description", "config", "routing_reason"})


class ProposalStore:
    """Persistence SQLite per le proposte automazione.

    Ciclo di vita:
    - pending  → dopo 7 giorni → archived
    - archived → dopo 30 giorni totali dalla creazione → DELETE
    - applied / rejected → permanenti (mai eliminati automaticamente)
    """

    def __init__(self, db_path: str, scheduler: Any) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._mu = threading.Lock()
        with self._mu:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        if scheduler is not None:
            scheduler.add_job(
                self._run_lifecycle,
                "interval",
                hours=1,
                id="proposal_store_lifecycle",
                replace_existing=True,
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime(_TS_FMT)

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["config"] = json.loads(d["config"])
        return d

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def save(self, proposal: dict) -> str:
        """Salva una nuova proposta. Ritorna l'id generato."""
        missing = _REQUIRED_FIELDS - proposal.keys()
        if missing:
            raise ValueError(f"Proposal missing required fields: {missing}")
        pid = str(uuid.uuid4())
        return await asyncio.get_running_loop().run_in_executor(
            None, self._save_sync, proposal, pid
        )

    async def get(self, proposal_id: str) -> dict | None:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._get_sync, proposal_id
        )

    async def list(self, status: str | None = None) -> list[dict]:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._list_sync, status
        )

    async def apply(self, proposal_id: str) -> bool:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._apply_sync, proposal_id
        )

    async def reject(self, proposal_id: str) -> bool:
        return await asyncio.get_running_loop().run_in_executor(
            None, self._reject_sync, proposal_id
        )

    # ------------------------------------------------------------------
    # Sync helpers — run in executor or called from lifecycle thread
    # ------------------------------------------------------------------

    def _save_sync(self, proposal: dict, pid: str) -> str:
        with self._mu:
            self._conn.execute(
                """INSERT INTO automation_proposals
                   (id, type, name, description, config, routing_reason, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    pid,
                    proposal["type"],
                    proposal["name"],
                    proposal["description"],
                    json.dumps(proposal["config"], ensure_ascii=False),
                    proposal["routing_reason"],
                    self._now(),
                ),
            )
            self._conn.commit()
        logger.info("ProposalStore: saved proposal %s (%s)", pid, proposal["name"])
        return pid

    def _get_sync(self, proposal_id: str) -> dict | None:
        with self._mu:
            row = self._conn.execute(
                "SELECT * FROM automation_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def _list_sync(self, status: str | None) -> list[dict]:
        with self._mu:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM automation_proposals WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM automation_proposals ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _apply_sync(self, proposal_id: str) -> bool:
        with self._mu:
            rowcount = self._conn.execute(
                "UPDATE automation_proposals SET status='applied', applied_at=? "
                "WHERE id=? AND status='pending'",
                (self._now(), proposal_id),
            ).rowcount
            self._conn.commit()
        return rowcount > 0

    def _reject_sync(self, proposal_id: str) -> bool:
        with self._mu:
            rowcount = self._conn.execute(
                "UPDATE automation_proposals SET status='rejected', rejected_at=? "
                "WHERE id=? AND status='pending'",
                (self._now(), proposal_id),
            ).rowcount
            self._conn.commit()
        return rowcount > 0

    def _lifecycle_sync(self) -> None:
        """pending > 7gg → archived. archived > 30gg totali dalla creazione → DELETE."""
        now = datetime.now(timezone.utc)
        archive_cutoff = (now - timedelta(days=7)).strftime(_TS_FMT)
        # 30 days from creation (not from archive date)
        delete_cutoff = (now - timedelta(days=30)).strftime(_TS_FMT)
        with self._mu:
            archived = self._conn.execute(
                "UPDATE automation_proposals SET status='archived', archived_at=? "
                "WHERE status='pending' AND created_at < ?",
                (now.strftime(_TS_FMT), archive_cutoff),
            ).rowcount
            deleted = self._conn.execute(
                "DELETE FROM automation_proposals WHERE status='archived' AND created_at < ?",
                (delete_cutoff,),
            ).rowcount
            self._conn.commit()
        if archived or deleted:
            logger.info(
                "ProposalStore lifecycle: archived=%d deleted=%d", archived, deleted
            )

    # ------------------------------------------------------------------
    # APScheduler job — sync, runs in threadpool, does NOT block event loop
    # ------------------------------------------------------------------

    def _run_lifecycle(self) -> None:
        try:
            self._lifecycle_sync()
        except Exception as exc:
            logger.error("ProposalStore lifecycle error: %s", exc)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._mu:
            self._conn.close()
