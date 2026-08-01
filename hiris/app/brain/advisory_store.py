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
CREATE TABLE IF NOT EXISTS advisory_notifications (
    source_ref  TEXT PRIMARY KEY,
    ts_notified TEXT NOT NULL
);
"""

# Versione dello schema. La 2 aggiunge `advisory_notifications`, la memoria di
# "per questo problema ho gia' avvisato": pura aggiunta, nessuna trasformazione
# di dati, quindi il `CREATE TABLE IF NOT EXISTS` qui sopra basta sia per un
# archivio nuovo sia per uno gia' esistente e non serve alcuna migrazione.
_VERSIONE_SCHEMA = 2

_SETTABLE = frozenset({"acknowledged", "dismissed"})

# Stati di una segnalazione ancora viva: `open` (nessuno l'ha guardata) e
# `acknowledged` (l'utente ne ha preso atto ma il problema non e' rientrato).
# `resolved` e' rientrata da sola, `dismissed` e' stata messa a tacere
# dall'utente e non deve riemergere da nessuna parte. Definita qui, dove vive
# la colonna `status`, cosi' che chi legge le segnalazioni (tool della chat,
# feed, briefing quotidiano) usi tutto la stessa nozione di "attiva".
STATI_ATTIVI = ("open", "acknowledged")

# Severita' che qualifica una segnalazione come grave. Definita qui, accanto
# alla colonna `severity`, cosi' che chi decide cosa e' degno di una notifica
# non se la ricopi come stringa sparsa nel codice.
SEVERITA_GRAVE = "high"


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
        init_schema(self._conn, _SCHEMA, version=_VERSIONE_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def reconcile(self, candidates: list[dict], check_ids: set,
                  *, now: str | None = None) -> dict:
        """Allinea le segnalazioni sul disco ai candidati di questa scansione.

        Oltre ai contatori storici (`inserted`, `updated`, `reopened`,
        `resolved`, invariati) riporta *quali* segnalazioni sono cambiate in
        modo notificabile, perche' il chiamante da soli i numeri non puo'
        sapere di cosa parlare:

        - `inserted_items`: candidati mai visti prima;
        - `reopened_items`: candidati rientrati e che si ripresentano;
        - `escalated_items`: candidati gia' aperti la cui severita' sale a
          `high` (contati anche in `updated`, per non alterare i contatori).
          Senza questo elenco un add-on che l'utente aveva spento (avviso) e
          che poi si guasta davvero (grave) resterebbe muto: il riferimento
          di deduplica non cambia, quindi e' un semplice aggiornamento.

        Le voci sono i dizionari candidato passati in ingresso, da leggere e
        non modificare. Un aggiornamento che NON alza la severita' non compare
        da nessuna parte: il titolo del disco pieno cambia a ogni scansione, e
        notificarlo significherebbe una notifica ogni 30 minuti.
        """
        now = now or _now_iso()
        res: dict = {"inserted": 0, "updated": 0, "reopened": 0, "resolved": 0,
                     "escalated": 0,
                     "inserted_items": [], "reopened_items": [], "escalated_items": []}

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
                        "SELECT id, source_ref, status, check_id, severity FROM advisories"
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
                        res["inserted_items"].append(c)
                    elif row["status"] in STATI_ATTIVI:
                        self._conn.execute(
                            "UPDATE advisories SET ts_updated=?, severity=?, title=?, "
                            "evidence=?, suggested_fix=? WHERE id=?",
                            (now, c["severity"], c["title"], ev, c["suggested_fix"], row["id"]),
                        )
                        res["updated"] += 1
                        if c["severity"] == SEVERITA_GRAVE and row["severity"] != SEVERITA_GRAVE:
                            res["escalated"] += 1
                            res["escalated_items"].append(c)
                    elif row["status"] == "resolved":
                        self._conn.execute(
                            "UPDATE advisories SET status='open', resolved_auto=0, "
                            "ts_updated=?, severity=?, title=?, evidence=?, suggested_fix=? "
                            "WHERE id=?",
                            (now, c["severity"], c["title"], ev, c["suggested_fix"], row["id"]),
                        )
                        res["reopened"] += 1
                        res["reopened_items"].append(c)
                    # status == 'dismissed' -> suppressed, skip
                for ref, row in existing.items():
                    if (row["status"] in STATI_ATTIVI
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

    # ── Memoria delle notifiche gia' inviate ─────────────────────────────
    # `reconcile` sa dire cosa e' cambiato rispetto alla scansione precedente,
    # ma non se per quel problema l'utente e' gia' stato avvisato. Senza questa
    # memoria un valore che oscilla attorno a una soglia (il disco al 10%
    # libero, un add-on in ciclo di riavvio) torna "nuovo o riaperto" a ogni
    # giro e produce notifiche a ripetizione. Sta qui, nello stesso archivio
    # delle segnalazioni, perche' deve sopravvivere ai riavvii come loro.

    def notificati_dopo(self, refs, ts_min: str) -> set:
        """Quali fra `refs` hanno gia' prodotto una notifica da `ts_min` in poi.

        I timestamp sono ISO UTC a lunghezza fissa, quindi il confronto
        lessicale di SQLite coincide con quello cronologico. La chiave e' il
        riferimento di deduplica: il silenzio su un problema non copre mai un
        problema diverso.
        """
        elenco = [r for r in (refs or []) if r]
        if not elenco:
            return set()
        segnaposto = ",".join("?" * len(elenco))
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_ref FROM advisory_notifications "
                f"WHERE ts_notified >= ? AND source_ref IN ({segnaposto})",
                [ts_min, *elenco],
            ).fetchall()
        return {r["source_ref"] for r in rows}

    def registra_notifica(self, source_ref: str, *, now: str | None = None) -> None:
        """Annota che per questo riferimento e' partita una notifica.

        Una riga per riferimento, riscritta a ogni nuova notifica: il periodo
        di silenzio riparte dall'ultima volta che l'utente e' stato avvisato.
        """
        if not source_ref:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO advisory_notifications(source_ref, ts_notified) "
                "VALUES(?,?)",
                (source_ref, now or _now_iso()),
            )
            self._conn.commit()

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
