from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS advisories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id      TEXT NOT NULL,
    ts_created    TEXT NOT NULL,
    ts_updated    TEXT NOT NULL,
    severity      TEXT NOT NULL,
    title         TEXT NOT NULL,
    evidence      TEXT NOT NULL,
    suggested_fix TEXT NOT NULL,
    fix_kind      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',
    source_ref    TEXT NOT NULL UNIQUE,
    resolved_auto INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_adv_status ON advisories(status, ts_updated DESC);
"""

_SETTABLE = frozenset({"acknowledged", "dismissed"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(r) -> dict:
    d = dict(r)
    try:
        d["evidence"] = json.loads(d["evidence"])
    except (ValueError, TypeError):
        d["evidence"] = {}
    return d


class AdvisoryStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def reconcile(self, candidates: list[dict], check_ids: set,
                  *, now: str | None = None) -> dict:
        now = now or _now_iso()
        res = {"inserted": 0, "updated": 0, "reopened": 0, "resolved": 0}

        # Dedupe candidates by source_ref (last-wins)
        _seen = {}
        for c in candidates:
            _seen[c["source_ref"]] = c
        candidates = list(_seen.values())

        with self._lock:
            try:
                existing = {
                    r["source_ref"]: r
                    for r in self._conn.execute(
                        "SELECT id, source_ref, status, check_id FROM advisories"
                    ).fetchall()
                }
                cand_refs = set()
                for c in candidates:
                    ref = c["source_ref"]
                    cand_refs.add(ref)
                    ev = json.dumps(c.get("evidence") or {}, ensure_ascii=False)
                    row = existing.get(ref)
                    if row is None:
                        self._conn.execute(
                            "INSERT INTO advisories(check_id, ts_created, ts_updated, "
                            "severity, title, evidence, suggested_fix, fix_kind, status, "
                            "source_ref, resolved_auto) VALUES(?,?,?,?,?,?,?,?, 'open', ?, 0)",
                            (c["check_id"], now, now, c["severity"], c["title"], ev,
                             c["suggested_fix"], c["fix_kind"], ref),
                        )
                        res["inserted"] += 1
                    elif row["status"] in ("open", "acknowledged"):
                        self._conn.execute(
                            "UPDATE advisories SET ts_updated=?, severity=?, title=?, "
                            "evidence=?, suggested_fix=? WHERE id=?",
                            (now, c["severity"], c["title"], ev, c["suggested_fix"], row["id"]),
                        )
                        res["updated"] += 1
                    elif row["status"] == "resolved":
                        self._conn.execute(
                            "UPDATE advisories SET status='open', resolved_auto=0, "
                            "ts_updated=?, severity=?, title=?, evidence=?, suggested_fix=? "
                            "WHERE id=?",
                            (now, c["severity"], c["title"], ev, c["suggested_fix"], row["id"]),
                        )
                        res["reopened"] += 1
                    # status == 'dismissed' -> suppressed, skip
                for ref, row in existing.items():
                    if (row["status"] in ("open", "acknowledged")
                            and row["check_id"] in check_ids
                            and ref not in cand_refs):
                        self._conn.execute(
                            "UPDATE advisories SET status='resolved', resolved_auto=1, "
                            "ts_updated=? WHERE id=?",
                            (now, row["id"]),
                        )
                        res["resolved"] += 1
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return res

    def list(self, *, status: str | None = None) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM advisories WHERE status=? ORDER BY ts_updated DESC",
                    (status,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM advisories ORDER BY ts_updated DESC"
                ).fetchall()
        return [_row(r) for r in rows]

    def get(self, advisory_id: int) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM advisories WHERE id=?", (int(advisory_id),)
            ).fetchone()
        return _row(r) if r is not None else None

    def set_status(self, advisory_id: int, status: str) -> bool:
        if status not in _SETTABLE:
            return False
        with self._lock:
            rc = self._conn.execute(
                "UPDATE advisories SET status=?, ts_updated=? WHERE id=?",
                (status, _now_iso(), int(advisory_id)),
            ).rowcount
            self._conn.commit()
        return rc > 0
