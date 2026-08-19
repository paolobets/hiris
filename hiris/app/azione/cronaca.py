"""Il registro delle esecuzioni -- una riga leggibile per ogni azione, e per
ogni origine.

La fetta «comandare» lo aveva promesso e non l'ha costruito: `porta.py`
scriveva una riga di `logger.info` e basta. Per la fondamenta n.4 quel
registro NON esisteva -- nessuno poteva chiederlo.

Vive ACCANTO alla porta, e non dentro lo schedulatore, per una ragione sola:
un'azione eseguita e' lo stesso fatto qualunque sia l'origine. Un registro
delle sole promesse avrebbe dato allo stesso fatto due trattamenti a seconda
di chi l'ha chiesto -- fondamenta n.3 -- e i due registri sarebbero andati
fusi dopo.

**Il nome non e' `registro.py`**: in questa cartella quel nome e' gia' il
registro dei SERVIZI (cosa Home Assistant sa fare). Due cose diverse non
possono chiamarsi allo stesso modo in due file vicini.

Registra i tentativi che hanno superato la verifica -- riusciti o falliti. Un
rifiuto della verifica non e' un'esecuzione: e' un errore del modello, gia'
detto al modello, e riempirebbe il registro di cose che non sono successe.
"""
from __future__ import annotations

import json
import secrets
import threading

from ..storage import connect, init_schema

# Novanta giorni, la stessa conservazione delle promesse concluse: sono due
# facce dello stesso registro, e due soglie diverse sarebbero due politiche da
# tenere allineate a mano.
CONSERVAZIONE_S = 90 * 86400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS esecuzioni (
    id TEXT PRIMARY KEY,
    quando_ts REAL NOT NULL,
    origine TEXT NOT NULL,
    servizio TEXT NOT NULL,
    entita_json TEXT NOT NULL,
    eseguito INTEGER NOT NULL,
    cambiato_json TEXT,
    errore TEXT,
    avviso TEXT
);
CREATE INDEX IF NOT EXISTS idx_esecuzioni_quando ON esecuzioni(quando_ts DESC);
"""


def _riga(r) -> dict:
    return {
        "id": r["id"],
        "quando_ts": r["quando_ts"],
        "origine": r["origine"],
        "servizio": r["servizio"],
        "entita": json.loads(r["entita_json"]),
        "eseguito": bool(r["eseguito"]),
        "cambiato": None if r["cambiato_json"] is None else json.loads(r["cambiato_json"]),
        "errore": r["errore"],
        "avviso": r["avviso"],
    }


class Cronaca:
    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def registra(self, *, origine: str, servizio: str, entita: list[str],
                 eseguito: bool, adesso: float, cambiato: list[str] | None = None,
                 errore: str | None = None, avviso: str | None = None) -> str:
        ident = secrets.token_urlsafe(9)
        with self._lock:
            self._conn.execute(
                "DELETE FROM esecuzioni WHERE quando_ts < ?",
                (adesso - CONSERVAZIONE_S,))
            self._conn.execute(
                "INSERT INTO esecuzioni(id,quando_ts,origine,servizio,entita_json,"
                "eseguito,cambiato_json,errore,avviso) VALUES(?,?,?,?,?,?,?,?,?)",
                (ident, adesso, origine, servizio, json.dumps(list(entita)),
                 int(bool(eseguito)),
                 None if cambiato is None else json.dumps(list(cambiato)),
                 errore, avviso))
            self._conn.commit()
        return ident

    def leggi(self, esecuzione_id: str) -> dict | None:
        # Lettura, ma sulla stessa connessione condivisa (`check_same_thread=
        # False`) delle scritture: senza lock qui una `registra` in corso su
        # un altro thread potrebbe intrecciarsi con questa query. E' il
        # pattern appena consolidato in `schedulatore/archivio.py`.
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM esecuzioni WHERE id=?", (esecuzione_id,)).fetchone()
        return None if r is None else _riga(r)

    def elenca(self, *, limite: int = 50) -> list[dict]:
        with self._lock:
            righe = self._conn.execute(
                "SELECT * FROM esecuzioni ORDER BY quando_ts DESC, rowid DESC LIMIT ?",
                (int(limite),)).fetchall()
        return [_riga(r) for r in righe]
