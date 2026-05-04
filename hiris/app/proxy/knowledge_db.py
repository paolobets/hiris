from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_classifications (
    entity_id     TEXT PRIMARY KEY,
    area          TEXT,
    entity_type   TEXT NOT NULL,
    label_it      TEXT NOT NULL,
    friendly_name TEXT NOT NULL DEFAULT '',
    domain        TEXT NOT NULL,
    device_class  TEXT,
    classified_by TEXT NOT NULL DEFAULT 'schema',
    confidence    REAL NOT NULL DEFAULT 1.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_annotations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    annotation  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_correlations (
    entity_a         TEXT NOT NULL,
    entity_b         TEXT NOT NULL,
    correlation_type TEXT NOT NULL,
    confidence       REAL NOT NULL DEFAULT 0.5,
    observed_count   INTEGER NOT NULL DEFAULT 1,
    last_observed    TEXT NOT NULL,
    PRIMARY KEY (entity_a, entity_b, correlation_type)
);
CREATE TABLE IF NOT EXISTS query_patterns (
    entity_id    TEXT NOT NULL,
    concept_type TEXT NOT NULL,
    hit_count    INTEGER NOT NULL DEFAULT 1,
    last_hit     TEXT NOT NULL,
    PRIMARY KEY (entity_id, concept_type)
);
"""


class KnowledgeDB:
    def __init__(self, db_path: str = "/data/hiris_knowledge.db") -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save_classification(
        self,
        entity_id: str,
        area: Optional[str],
        entity_type: str,
        label_it: str,
        friendly_name: str,
        domain: str,
        device_class: Optional[str],
        classified_by: str = "schema",
        confidence: float = 1.0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO entity_classifications
                (entity_id, area, entity_type, label_it, friendly_name,
                 domain, device_class, classified_by, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                area=excluded.area, entity_type=excluded.entity_type,
                label_it=excluded.label_it, friendly_name=excluded.friendly_name,
                classified_by=excluded.classified_by, confidence=excluded.confidence,
                updated_at=excluded.updated_at
            """,
            (entity_id, area, entity_type, label_it, friendly_name,
             domain, device_class, classified_by, confidence, now, now),
        )
        self._conn.commit()

    def load_classifications(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT * FROM entity_classifications").fetchall()
        return {r["entity_id"]: dict(r) for r in rows}

    def add_annotation(self, entity_id: str, source: str, annotation: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO entity_annotations (entity_id, source, annotation, created_at)"
            " VALUES (?, ?, ?, ?)",
            (entity_id, source, annotation, now),
        )
        self._conn.commit()

    def get_annotations(self, entity_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM entity_annotations WHERE entity_id=? ORDER BY created_at DESC",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "KnowledgeDB":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
