"""Brain suggestion store + auto-apply of validated coverage + undo.

Security core: the brain proposes detector coverage (kind="coverage") and
management ideas (kind="management"). Coverage suggestions that pass
validation are auto-applied to the Sentinella policy (source=brain, tracked
via the sidecar registry in watcher.policy) up to a per-call cap. Applying
and undoing coverage NEVER touches an entity the user configured themselves
-- see watcher.policy.apply_brain_detector/remove_brain_detector.
"""
from __future__ import annotations

import json
import threading
from typing import Callable, Optional

from ..storage import connect, init_schema
from ..watcher.detectors import DETECTORS
from ..watcher.policy import apply_brain_detector, remove_brain_detector

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT,
    rationale TEXT,
    config TEXT,
    status TEXT NOT NULL,
    delta TEXT
);
"""


class SuggestionStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record(self, kind: str, title: str, rationale: str, config: dict,
               status: str, delta: Optional[dict]) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO suggestions(kind, title, rationale, config, status, delta) "
                "VALUES(?,?,?,?,?,?)",
                (kind, title, rationale, json.dumps(config, ensure_ascii=False),
                 status, json.dumps(delta, ensure_ascii=False) if delta is not None else None))
            self._conn.commit()
            return cur.lastrowid

    def list(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, title, rationale, config, status, delta "
                "FROM suggestions ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]

    def get(self, suggestion_id: int) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute(
                "SELECT id, kind, title, rationale, config, status, delta "
                "FROM suggestions WHERE id=?", (suggestion_id,)).fetchone()
        return _row_to_dict(r) if r else None

    def set_status(self, suggestion_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE suggestions SET status=? WHERE id=?", (status, suggestion_id))
            self._conn.commit()


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["config"] = json.loads(d["config"]) if d.get("config") else {}
    d["delta"] = json.loads(d["delta"]) if d.get("delta") else None
    return d


def validate_coverage(sugg: dict, inventory_ids: set, current_config: dict) -> bool:
    """True iff the coverage suggestion targets a real, known entity/detector
    that is not already covered (by user OR brain -- both live in the same
    policy entities list, so this check is source-agnostic by design).
    Never raises: any malformed input yields False."""
    try:
        config = sugg.get("config")
        if not isinstance(config, dict):
            return False
        detector = config.get("detector")
        entity = config.get("entity")
        if not isinstance(detector, str) or not isinstance(entity, str):
            return False
        if detector not in DETECTORS:
            return False
        if entity not in inventory_ids:
            return False
        detectors_cfg = current_config.get("detectors") if isinstance(current_config, dict) else None
        det_cfg = (detectors_cfg or {}).get(detector) if isinstance(detectors_cfg, dict) else None
        existing = det_cfg.get("entities") if isinstance(det_cfg, dict) else None
        if isinstance(existing, list) and entity in existing:
            return False
        return True
    except Exception:
        return False


def apply_suggestions(suggs: list[dict], *, data_dir: str, store: SuggestionStore,
                       inventory_ids: set, current_config: dict,
                       create_proposal: Callable[[dict], None], cap: int) -> list[dict]:
    """Apply validated coverage suggestions (up to `cap` auto-applies) and
    forward management suggestions to create_proposal. Returns the list of
    suggestions that were actually auto-applied (as stored rows)."""
    applied: list[dict] = []
    applied_count = 0
    for sugg in suggs:
        kind = sugg.get("kind")
        title = sugg.get("title", "")
        rationale = sugg.get("rationale", "")
        config = sugg.get("config") if isinstance(sugg.get("config"), dict) else {}

        if kind == "coverage":
            if applied_count >= cap or not validate_coverage(sugg, inventory_ids, current_config):
                continue
            detector = config["detector"]
            entity = config["entity"]
            # Belt-and-suspenders: structural keys are stripped again inside
            # apply_brain_detector (source of truth), but never let an
            # untrusted config forward "enabled"/"entities" as params at all.
            params = {k: v for k, v in config.items()
                      if k not in ("detector", "entity", "enabled", "entities")}
            delta = apply_brain_detector(data_dir, detector, entity, params)
            suggestion_id = store.record(kind, title, rationale, config, "applied", delta)
            applied_count += 1
            row = store.get(suggestion_id)
            if row is not None:
                applied.append(row)
        elif kind == "management":
            create_proposal(config)
            store.record(kind, title, rationale, config, "proposed", None)
        # unknown kind -> skip silently
    return applied


def undo(store: SuggestionStore, data_dir: str, suggestion_id: int) -> bool:
    """Undo a previously auto-applied coverage suggestion. Only ever reverses
    a suggestion that IS an applied coverage row with a delta; remove_brain_detector
    additionally refuses to touch anything not in the brain sidecar registry."""
    row = store.get(suggestion_id)
    if row is None:
        return False
    if row.get("kind") != "coverage" or row.get("status") != "applied":
        return False
    delta = row.get("delta")
    if not isinstance(delta, dict) or "detector" not in delta or "entity" not in delta:
        return False
    ok = remove_brain_detector(data_dir, delta["detector"], delta["entity"])
    store.set_status(suggestion_id, "dismissed")
    return ok
