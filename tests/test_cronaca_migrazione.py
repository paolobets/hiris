"""La migrazione 3 -> 4 della cronaca (Tappa 8, Task 5; A-17, D8): il
soggetto copiato intero in `soggetto_json` diventa la sua chiave
(`subject_key`), e la frase che confermava (B-5) la sua colonna.

Si prova su un archivio alla versione 3 con le righe com'erano, due volte: la
prima apertura migra, la seconda non cambia niente."""
import json
import os

from hiris.app.action.journal import SCHEMA_VERSION, Journal
from hiris.app.storage import connect

_SCHEMA_V3 = """
CREATE TABLE esecuzioni (
    id TEXT PRIMARY KEY, quando_ts REAL NOT NULL, origine TEXT NOT NULL,
    servizio TEXT NOT NULL, entita_json TEXT NOT NULL, eseguito INTEGER NOT NULL,
    cambiato_json TEXT, errore TEXT, avviso TEXT,
    genere TEXT NOT NULL DEFAULT 'comando', oggetto TEXT, soggetto_json TEXT);
CREATE INDEX idx_esecuzioni_quando ON esecuzioni(quando_ts DESC);
PRAGMA user_version = 3;
"""

_RIGHE = (
    ("persona", {"specie": "persona", "id": "u-42", "nome": "Paolo",
                 "utente": "paolo", "ruolo": None}),
    ("confermata", {"specie": "persona", "id": "u-42", "nome": "Paolo",
                    "confirm_phrase": "sì, procedi"}),
    ("solo-frase", {"confirm_phrase": "fallo"}),
    ("nessuno", None),
    ("storta", "{non e' json"),
)


def _archivio_v3(path: str) -> None:
    conn = connect(path)
    conn.executescript(_SCHEMA_V3)
    for n, (ident, soggetto) in enumerate(_RIGHE):
        scritto = (soggetto if isinstance(soggetto, str) or soggetto is None
                   else json.dumps(soggetto))
        conn.execute(
            "INSERT INTO esecuzioni(id,quando_ts,origine,servizio,entita_json,"
            "eseguito,soggetto_json) VALUES(?,?,'chat','light.turn_on','[]',1,?)",
            (ident, 100.0 + n, scritto))
    conn.commit()
    conn.close()


def test_il_soggetto_diventa_chiave_e_la_frase_resta(tmp_path):
    """Mutazione ESEGUITA (08/10/2026): la frase non travasata nella sua
    colonna -- rossa, «confermata» perde il «sì, procedi»."""
    path = os.path.join(str(tmp_path), "azioni.db")
    _archivio_v3(path)
    for _apertura in range(2):
        cronaca = Journal(path)
        try:
            righe = {r["id"]: r for r in cronaca.list(from_ts=0, to_ts=1000)}
            assert len(righe) == len(_RIGHE)
            assert righe["persona"]["soggetto"] == {
                "specie": "persona", "id": "u-42", "nome": None, "utente": None,
                "ruolo": None}
            assert righe["persona"]["confirm_phrase"] is None
            assert righe["confermata"]["soggetto"]["id"] == "u-42"
            assert righe["confermata"]["confirm_phrase"] == "sì, procedi"
            assert (righe["solo-frase"]["soggetto"],
                    righe["solo-frase"]["confirm_phrase"]) == (None, "fallo")
            assert righe["nessuno"]["soggetto"] is None
            assert righe["storta"]["soggetto"] is None
            colonne = {r[1] for r in cronaca._conn.execute(
                "PRAGMA table_info(esecuzioni)")}
            assert "soggetto_json" not in colonne
            assert {"subject_key", "confirm_phrase"} <= colonne
            assert cronaca._conn.execute(
                "PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            cronaca.close()


def test_un_archivio_nuovo_nasce_con_la_chiave(tmp_path):
    cronaca = Journal(os.path.join(str(tmp_path), "nuova.db"))
    try:
        colonne = {r[1] for r in cronaca._conn.execute("PRAGMA table_info(esecuzioni)")}
        assert {"subject_key", "confirm_phrase"} <= colonne
        assert "soggetto_json" not in colonne
    finally:
        cronaca.close()
