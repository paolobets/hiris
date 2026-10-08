"""La migrazione 1 -> 2 dell'archivio delle promesse.

Il difetto che queste prove esistono per impedire non e' «la colonna manca»:
e' che la colonna ci sia e sia tutta NULL. Su una casa vera lo storico
contiene fino a 90 giorni di promesse concluse (`keeper/store.py::CONSERVAZIONE`);
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

from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.store import SCHEMA_VERSION, AgendaStore, _migration_2
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
PAOLO = ChatThread("persona:paolo", "pannello")


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
    """Le righe di un archivio vecchio sono ORFANE (senza filo, spec
    2026-09-26 §2): nessuno le vede finche' il proprietario non le adotta.
    Si leggono come le leggera' lui -- adottate, poi elencate nel suo filo --
    cosi' che il conteggio del pallino qui sotto misuri il travaso e non
    l'invisibilita' delle orfane (che darebbe zero comunque)."""
    store.adopt_orphans(PAOLO)
    return {r["id"]: r for r in store.list(thread=PAOLO, limit=50)}


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
    """`_migration_2` chiamata DUE VOLTE non solleva e non ri-timbra.

    **La prima stesura di questa prova non poteva fallire**, ed e' stata una
    review indipendente a dirlo: apriva due volte `AgendaStore` e si
    aspettava lo stesso timbro -- ma alla seconda apertura `init_schema`
    legge `user_version == 2` e **non chiama affatto** la migrazione
    (`storage.py`: `range(current + 1, version + 1)` e' vuoto). Provava il
    timbro di versione, non la funzione. Provata per mutazione: sostituendo
    `_migration_2` con una versione senza guardia -- che ri-emette
    `ALTER TABLE` e ri-timbra l'ora -- restava verde.

    Qui la funzione si chiama a mano, che e' l'unico modo di misurare cio'
    che il nome del test promette.
    """
    db = os.path.join(str(tmp_path), "promesse.db")
    _archivio_vecchio(db, [("a", "mantenuta"), ("b", "in_attesa")])

    store = AgendaStore(db)
    try:
        primo_giro = _per_id(store)["a"]["esito_letto_ts"]
        assert primo_giro is not None

        _migration_2(store._conn)
        store._conn.commit()

        righe = _per_id(store)
        assert righe["a"]["esito_letto_ts"] == primo_giro, (
            "il secondo giro ha ri-timbrato una riga gia' segnata: l'ora in "
            "cui l'esito e' stato letto e' diventata falsa")
        assert righe["b"]["esito_letto_ts"] is None
    finally:
        store.close()


def test_caduta_fra_l_alter_e_il_travaso(tmp_path):
    """La colonna c'e' ma il travaso no: il giro dopo lo completa.

    Lo scenario e' reale e non teorico. In questo modulo `ALTER TABLE` si
    auto-committa (misurato: `conn.in_transaction` e' `False` subito dopo)
    mentre l'`UPDATE` no, e `init_schema` fa un solo `commit()` in fondo. Se
    il Raspberry si spegne fra i due, sul disco resta una colonna nuova con
    `user_version` ancora a 1 -- ed e' precisamente questo stato che si
    ricostruisce qui.

    **Mutazione che questa prova deve uccidere**: rimettere l'`UPDATE`
    dentro `if "esito_letto_ts" not in existing`. Con la colonna gia'
    presente quella versione salta il travaso, `init_schema` timbra 2, e lo
    storico resta non letto PER SEMPRE -- nessun altro codice lo rifarebbe.
    Il pallino degli Impegni si accenderebbe con novanta giorni di storico,
    cioe' il difetto per cui il travaso esiste.
    """
    db = os.path.join(str(tmp_path), "promesse.db")
    _archivio_vecchio(db, [("a", "mantenuta"), ("b", "fallita"), ("c", "in_attesa")])

    # Lo stato dopo la caduta: colonna sul disco, travaso mai fatto,
    # `user_version` ancora 1.
    conn = connect(db)
    conn.execute("ALTER TABLE promesse ADD COLUMN esito_letto_ts REAL")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    store = AgendaStore(db)
    try:
        righe = _per_id(store)
        assert righe["a"]["esito_letto_ts"] is not None
        assert righe["b"]["esito_letto_ts"] is not None
        assert righe["c"]["esito_letto_ts"] is None
        assert store.count_unread(PAOLO) == 0, (
            "il travaso non e' stato completato: al primo avvio il pallino "
            "si accenderebbe con tutto lo storico")
    finally:
        store.close()


def test_una_disdetta_non_e_un_esito_da_leggere(tmp_path):
    """Disdire e' un ordine dell'utente, non una notizia per lui.

    `STATES_CONCLUSI` include `disdetta`; `STATES_ESITO` no, e questa e'
    l'intera ragione per cui i due insiemi esistono separati. Contarla
    faceva accendere il pallino per richiamare l'utente a leggere cio' che
    aveva appena ordinato (review indipendente, rilievo 5).
    """
    db = os.path.join(str(tmp_path), "promesse.db")
    store = AgendaStore(db)
    try:
        ident = store.create(
            {"specie": "chiedi", "frase": "x", "quando_ts": ADESSO + 3600,
             "domanda": "y?"}, thread=PAOLO, now=ADESSO)["promessa"]["id"]
        store.cancel(ident, thread=PAOLO, now=ADESSO + 1)

        assert store.read(ident)["stato"] == "disdetta"
        assert store.count_unread(PAOLO) == 0
        # E non si puo' nemmeno segnare letta: non e' fra gli esiti.
        assert store.mark_read([ident], thread=PAOLO, now=ADESSO + 2) == 0
    finally:
        store.close()


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
        # Lo stesso vale per il filo (versione 4, spec 2026-09-26 §2): nello
        # schema, non solo nella migrazione.
        assert {"subject_key", "entry_point"} <= colonne
        assert "closed_ts" in colonne and "recapito" not in colonne
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        store.close()


# -- v4 -> v5 (Tappa 8, Task 5): esce `recapito`, nasce `closed_ts` (G-20) --

_SCHEMA_V4 = """
CREATE TABLE promesse (
    id TEXT PRIMARY KEY, specie TEXT NOT NULL, frase TEXT NOT NULL,
    quando_ts REAL NOT NULL, quando_detto TEXT, fuso TEXT, chiamata_json TEXT,
    domanda TEXT, istantanea_json TEXT, recapito TEXT,
    stato TEXT NOT NULL DEFAULT 'in_attesa', motivo TEXT, esecuzione_id TEXT,
    testo TEXT, avvisare INTEGER, nata_ts REAL NOT NULL, risvegliata_ts REAL,
    esito_letto_ts REAL, entities_at_birth INTEGER, subject_key TEXT,
    entry_point TEXT);
CREATE INDEX idx_promesse_scadenza ON promesse(stato, quando_ts);
PRAGMA user_version = 4;
"""


def _archivio_v4(path: str) -> None:
    """Le righe com'erano sul disco alla versione 4: una presa e mantenuta,
    una disdetta e una saltata (che `risvegliata_ts` lo portavano come
    chiusura), una in attesa col `recapito` scelto dal modello."""
    conn = connect(path)
    conn.executescript(_SCHEMA_V4)
    for ident, stato, presa in (("mantenuta", "mantenuta", ADESSO - 50),
                                ("disdetta", "disdetta", ADESSO - 40),
                                ("saltata", "saltata", ADESSO - 30),
                                ("attesa", "in_attesa", None)):
        conn.execute(
            "INSERT INTO promesse(id,specie,frase,quando_ts,recapito,stato,nata_ts,"
            "risvegliata_ts,subject_key,entry_point) VALUES(?,'fai',?,?,?,?,?,?,?,?)",
            (ident, "frase " + ident, ADESSO, "notify.mobile_app_x", stato,
             ADESSO - 100, presa, PAOLO.subject_key, PAOLO.entry_point))
    conn.commit()
    conn.close()


def test_la_migrazione_5_toglie_il_recapito_e_scrive_la_chiusura(tmp_path):
    """Due aperture: la prima migra, la seconda non cambia niente.

    Mutazione ESEGUITA (08/10/2026): `closed_ts` non riempito dalla
    migrazione -- rossa, la mantenuta resta senza chiusura e la potatura non
    la toglierebbe mai."""
    path = os.path.join(str(tmp_path), "promesse.db")
    _archivio_v4(path)
    for _apertura in range(2):
        store = AgendaStore(path)
        try:
            colonne = {r[1] for r in store._conn.execute("PRAGMA table_info(promesse)")}
            assert "recapito" not in colonne and "closed_ts" in colonne
            righe = {r["id"]: r for r in store.list(thread=PAOLO)}
            assert (righe["mantenuta"]["risvegliata_ts"],
                    righe["mantenuta"]["closed_ts"]) == (ADESSO - 50, ADESSO - 50)
            assert (righe["disdetta"]["risvegliata_ts"],
                    righe["disdetta"]["closed_ts"]) == (None, ADESSO - 40)
            assert (righe["saltata"]["risvegliata_ts"],
                    righe["saltata"]["closed_ts"]) == (None, ADESSO - 30)
            assert (righe["attesa"]["risvegliata_ts"],
                    righe["attesa"]["closed_ts"]) == (None, None)
            assert store._conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='index' "
                "AND name='idx_promesse_scadenza'").fetchone()[0] == 1
            assert store._conn.execute(
                "PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            store.close()
