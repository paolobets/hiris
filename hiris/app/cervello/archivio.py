"""L'archivio dell'osservatore: i cambi e gli oggetti.

**Due tabelle, due vite.** I cambi grezzi vivono 21 giorni; gli oggetti --
cio' che di quei cambi si e' capito -- restano finche' l'utente non li
cancella.

**Perche' 21 giorni e non una notte.** La proprieta' che rende buono lo schema
a due strati e' che sbagliare l'aggregazione costa un GIORNO, non tutto: finche'
il grezzo c'e', gli oggetti si rifanno. Ma il modo di costruirli cambiera' --
le prime settimane sono quelle in cui si sta ancora imparando -- e con una notte
sola ogni miglioramento varrebbe solo da domani. Ventuno giorni sono TRE
MERCOLEDI', l'unita' dell'esempio da cui nasce tutto il cervello.

**Perche' non e' il ritorno di `history.db`.** Quello scriveva e nessuno
leggeva, e l'avvio lo tratta ancora oggi come un residuo da rimuovere. La
differenza non e' di forma, e' di destino: quello nasceva senza lettore, questo
nasce col lettore -- l'analista e' la fetta successiva, e senza gli oggetti non
puo' esistere. **Se l'analista non venisse costruito, questo archivio va
cancellato**, non lasciato a scrivere: e' la stessa regola che ha condannato il
primo.
"""
from __future__ import annotations

import json
import threading

from ..storage import connect, init_schema

# Ventuno giorni: tre mercoledi'. Vedi il docstring del modulo.
CONSERVAZIONE_CAMBI_S = 21 * 86400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cambi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando_ts REAL NOT NULL,
    fonte TEXT NOT NULL,
    soggetto TEXT NOT NULL,
    da TEXT,
    a TEXT
);
CREATE INDEX IF NOT EXISTS idx_cambi_quando ON cambi(quando_ts);
CREATE INDEX IF NOT EXISTS idx_cambi_soggetto ON cambi(soggetto, quando_ts);

CREATE TABLE IF NOT EXISTS oggetti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    giorno TEXT NOT NULL,
    genere TEXT NOT NULL,
    protagonista TEXT NOT NULL,
    inizio_ts REAL NOT NULL,
    fine_ts REAL,
    corpo_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oggetti_giorno ON oggetti(giorno, inizio_ts);
"""


def _riga_cambio(r) -> dict:
    return {"quando_ts": r["quando_ts"], "fonte": r["fonte"],
            "soggetto": r["soggetto"], "da": r["da"], "a": r["a"]}


def _riga_oggetto(r) -> dict:
    return {"id": r["id"], "giorno": r["giorno"], "genere": r["genere"],
            "protagonista": r["protagonista"], "inizio_ts": r["inizio_ts"],
            "fine_ts": r["fine_ts"], "corpo": json.loads(r["corpo_json"])}


class ArchivioOsservazioni:
    """La memoria dell'osservatore. Il lock e' lo stesso delle scritture anche
    in lettura: la connessione e' condivisa fra thread (`check_same_thread=
    False`), ed e' il pattern gia' consolidato in `azione/cronaca.py`."""

    def __init__(self, db_path: str) -> None:
        self._conn = connect(db_path)
        self._lock = threading.Lock()
        init_schema(self._conn, _SCHEMA, version=1)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- i cambi -------------------------------------------------------

    def annota(self, *, quando_ts: float, fonte: str, soggetto: str,
               da, a) -> None:
        """Un cambio, cosi' com'e'. **Nessun giudizio in scrittura**: e' la
        condizione da cui dipende tutto il resto -- una decisione presa qui non
        si corregge piu', una presa in aggregazione si'."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a) VALUES(?,?,?,?,?)",
                (float(quando_ts), fonte, soggetto,
                 None if da is None else str(da), None if a is None else str(a)))
            self._conn.commit()

    def cambi(self, *, da_ts: float, a_ts: float, soggetto: str | None = None,
              limite: int = 200_000) -> list[dict]:
        """I cambi di una finestra, **dal piu' vecchio**.

        Al contrario della cronaca degli atti, che torna dal piu' recente:
        qui chi legge ricostruisce cose che cominciano e finiscono, e le vuole
        in ordine di accadimento.

        Il tetto e' alto apposta: misurato sulla casa vera, una giornata fa
        ~14.600 cambi, e l'aggregazione deve vederla intera.
        """
        sql = "SELECT * FROM cambi WHERE quando_ts >= ? AND quando_ts <= ?"
        args: list = [float(da_ts), float(a_ts)]
        if soggetto is not None:
            sql += " AND soggetto = ?"
            args.append(soggetto)
        sql += " ORDER BY quando_ts ASC, id ASC LIMIT ?"
        args.append(int(max(1, limite)))
        with self._lock:
            righe = self._conn.execute(sql, tuple(args)).fetchall()
        return [_riga_cambio(r) for r in righe]

    def pota(self, adesso_ts: float) -> int:
        """Butta i cambi oltre la conservazione. **Non tocca gli oggetti**: le
        due tabelle hanno due vite, e una potatura che si portasse via cio' che
        si e' capito cancellerebbe mesi per liberare qualche megabyte."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM cambi WHERE quando_ts < ?",
                                     (float(adesso_ts) - CONSERVAZIONE_CAMBI_S,))
            self._conn.commit()
            return cur.rowcount or 0

    # -- gli oggetti ---------------------------------------------------

    def salva_oggetto(self, *, giorno: str, genere: str, protagonista: str,
                      inizio_ts: float, fine_ts: float | None,
                      corpo: dict) -> int:
        """`fine_ts` a `None` significa **ancora aperto**, ed e' un fatto: a
        mezzanotte una cosa puo' essere in corso. Zero direbbe «finita
        subito»."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO oggetti(giorno,genere,protagonista,inizio_ts,fine_ts,corpo_json)"
                " VALUES(?,?,?,?,?,?)",
                (giorno, genere, protagonista, float(inizio_ts),
                 None if fine_ts is None else float(fine_ts),
                 json.dumps(corpo, ensure_ascii=False)))
            self._conn.commit()
            return int(cur.lastrowid)

    def oggetti(self, *, giorno: str | None = None, limite: int = 200) -> list[dict]:
        """Gli oggetti, dal piu' recente."""
        sql = "SELECT * FROM oggetti"
        args: list = []
        if giorno is not None:
            sql += " WHERE giorno = ?"
            args.append(giorno)
        sql += " ORDER BY inizio_ts DESC, id DESC LIMIT ?"
        args.append(int(max(1, limite)))
        with self._lock:
            righe = self._conn.execute(sql, tuple(args)).fetchall()
        return [_riga_oggetto(r) for r in righe]

    def dimentica_oggetti(self, giorno: str) -> int:
        """Svuota un giorno perche' l'aggregazione lo possa rifare.

        Senza, ogni ritentativo raddoppierebbe gli oggetti in silenzio -- e
        rifare un giorno e' esattamente cio' per cui il grezzo resta 21 giorni.
        """
        with self._lock:
            cur = self._conn.execute("DELETE FROM oggetti WHERE giorno = ?", (giorno,))
            self._conn.commit()
            return cur.rowcount or 0
