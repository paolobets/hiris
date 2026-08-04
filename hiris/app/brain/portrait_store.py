"""Memoria dello stato notevole della casa, e del suo cambiamento.

Questo store e' l'UNICO scrittore del delta. Il delta risponde a "cosa e'
cambiato dall'ultima volta che HIRIS ha guardato", e per essere una risposta
sensata ha bisogno di un solo osservatore: se ogni consumatore aggiornasse la
linea di base, ciascuno vedrebbe solo cio' che e' cambiato dopo il precedente.
L'osservazione e' quindi un job dedicato (server.py), i consumatori LEGGONO.

Un'entita' SPARITA non produce un cambiamento: e' un buco di lettura, non un
fatto sulla casa, e segnalarla riempirebbe il delta a ogni riavvio di HA.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from ..storage import connect, init_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notable (
    entity_id TEXT PRIMARY KEY,
    state     TEXT NOT NULL,
    since     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS last_delta (
    entity_id TEXT PRIMARY KEY,
    was       TEXT,
    now_state TEXT NOT NULL,
    since     TEXT NOT NULL
);
"""

_VERSIONE_SCHEMA = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PortraitStore:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=_VERSIONE_SCHEMA)

    def observe(self, current: dict[str, str], *, now: str | None = None) -> list[dict]:
        """Confronta `current` con la linea di base, aggiorna entrambe le tabelle,
        ritorna i cambiamenti. Transazione unica con rollback esplicito."""
        ts = now or _now_iso()
        current = {str(k): str(v) for k, v in (current or {}).items()}
        with self._lock:
            try:
                prev = {
                    r["entity_id"]: {"state": r["state"], "since": r["since"]}
                    for r in self._conn.execute(
                        "SELECT entity_id, state, since FROM notable"
                    ).fetchall()
                }
                changes: list[dict] = []
                for eid, state in current.items():
                    old = prev.get(eid)
                    if old is None:
                        changes.append({"entity_id": eid, "was": None,
                                        "now": state, "since": ts})
                    elif old["state"] != state:
                        changes.append({"entity_id": eid, "was": old["state"],
                                        "now": state, "since": ts})
                # La primissima osservazione non e' un cambiamento: e' l'inizio.
                if not prev:
                    changes = []

                self._conn.execute("DELETE FROM notable")
                self._conn.executemany(
                    "INSERT INTO notable (entity_id, state, since) VALUES (?,?,?)",
                    [
                        (
                            eid,
                            state,
                            ts if (prev.get(eid) or {}).get("state") != state
                            else prev[eid]["since"],
                        )
                        for eid, state in current.items()
                    ],
                )
                self._conn.execute("DELETE FROM last_delta")
                self._conn.executemany(
                    "INSERT INTO last_delta (entity_id, was, now_state, since)"
                    " VALUES (?,?,?,?)",
                    [(c["entity_id"], c["was"], c["now"], c["since"]) for c in changes],
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return changes

    def last_changes(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT entity_id, was, now_state, since FROM last_delta"
                " ORDER BY entity_id"
            ).fetchall()
        return [
            {"entity_id": r["entity_id"], "was": r["was"],
             "now": r["now_state"], "since": r["since"]}
            for r in rows
        ]

    def baseline(self) -> dict[str, dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT entity_id, state, since FROM notable"
            ).fetchall()
        return {r["entity_id"]: {"state": r["state"], "since": r["since"]} for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
