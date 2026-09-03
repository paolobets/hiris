"""La migrazione 1 -> 2 dell'archivio delle promesse.

Il difetto che queste prove esistono per impedire non e' «la colonna manca»:
e' che la colonna ci sia e sia tutta NULL. Su una casa vera lo storico
contiene fino a 90 giorni di promesse concluse (`promise.py::CONSERVAZIONE_S`);
senza il travaso il pallino degli Impegni si accenderebbe, al primo avvio dopo
l'aggiornamento, col numero di TUTTE. Un allarme per fatti di settimane fa.

Mutazione che `test_travaso` deve uccidere: una `_migration_2` che fa solo
l'`ALTER TABLE` e si ferma li'. E' l'implementazione che viene naturale, ed e'
quella sbagliata.

Mutazione che `test_archivio_nuovo_nasce_gia_a_posto` deve uccidere: mettere la
colonna nella sola migrazione e non in `_SCHEMA`. Un archivio esistente
funzionerebbe e uno nuovo no -- cioe' il proprietario non vedrebbe niente, e
chi installa da zero troverebbe l'add-on rotto.
"""
import os

from hiris.app.keeper.store import AgendaStore
from hiris.app.storage import connect

# Lo schema com'era a version=1 -- ricopiato QUI apposta, e non importato da
# `store.py`: importarlo lo farebbe seguire ogni modifica futura, e la prova
# smetterebbe di descrivere un archivio VECCHIO. Questa e' la fotografia di
# cio' che sta sul disco del proprietario prima dell'aggiornamento, e una
# fotografia non si aggiorna.
_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS promesse (
    id TEXT PRIMARY KEY,
    specie TEXT NOT NULL,
    frase TEXT NOT NULL,
    quando_ts REAL NOT NULL,
    quando_detto TEXT,
    fuso TEXT,
    chiamata_json TEXT,
    domanda TEXT,
    istantanea_json TEXT,
    recapito TEXT,
    stato TEXT NOT NULL DEFAULT 'in_attesa',
    motivo TEXT,
    esecuzione_id TEXT,
    testo TEXT,
    avvisare INTEGER,
    nata_ts REAL NOT NULL,
    risvegliata_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_promesse_scadenza ON promesse(stato, quando_ts);
"""

ADESSO = 1_755_600_000.0


def _archivio_vecchio(path: str, righe: list[tuple[str, str]]) -> None:
    """Un archivio a `version=1` con dentro `righe` di (id, stato)."""
    conn = connect(path)
    conn.executescript(_SCHEMA_V1)
    for ident, stato in righe:
        conn.execute(
            "INSERT INTO promesse(id,specie,frase,quando_ts,stato,nata_ts) "
            "VALUES(?,'fai',?,?,?,?)",
            (ident, "frase " + ident, ADESSO, stato, ADESSO - 100))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def _per_id(store: AgendaStore) -> dict:
    return {r["id"]: r for r in store.list(limit=50)}


def test_travaso(tmp_path):
    """Le concluse gia' in archivio nascono LETTE: non sono una notizia.

    Le due `mantenuta`/`fallita` sono lo storico del proprietario; la
    `in_attesa` e' meta' archivio nel caso normale, e non ha ancora nessun
    esito da leggere -- deve restare NULL, o il pallino conterebbe impegni
    futuri (spec §4.1).
    """
    db = os.path.join(str(tmp_path), "promesse.db")
    _archivio_vecchio(db, [("a", "mantenuta"), ("b", "fallita"), ("c", "in_attesa")])

    store = AgendaStore(db)
    try:
        righe = _per_id(store)
        assert righe["a"]["esito_letto_ts"] is not None
        assert righe["b"]["esito_letto_ts"] is not None
        assert righe["c"]["esito_letto_ts"] is None
    finally:
        store.close()


def test_migrazione_idempotente(tmp_path):
    """Aprire due volte non solleva e non ri-timbra niente.

    `PRAGMA table_info` protegge dal secondo `ALTER TABLE`; il fatto che
    l'ora non cambi protegge dal secondo `UPDATE`, che falserebbe il momento
    in cui l'esito e' stato letto.
    """
    db = os.path.join(str(tmp_path), "promesse.db")
    _archivio_vecchio(db, [("a", "mantenuta")])

    primo = AgendaStore(db)
    letto_ts = _per_id(primo)["a"]["esito_letto_ts"]
    primo.close()

    secondo = AgendaStore(db)
    try:
        assert _per_id(secondo)["a"]["esito_letto_ts"] == letto_ts
    finally:
        secondo.close()


def test_archivio_nuovo_nasce_gia_a_posto(tmp_path):
    """Su un archivio nuovo `init_schema` NON fa girare le migrazioni.

    Lo dichiara `storage.py`: un DB senza tabelle e' 'fresh', `schema_sql`
    produce gia' l'ultimo assetto, si timbra `version` e non si migra niente.
    Quindi la colonna deve stare anche in `_SCHEMA`, non solo nella
    migrazione.
    """
    store = AgendaStore(os.path.join(str(tmp_path), "nuova.db"))
    try:
        colonne = {r["name"] for r in store._conn.execute("PRAGMA table_info(promesse)")}
        assert "esito_letto_ts" in colonne
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        store.close()
