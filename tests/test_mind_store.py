"""L'archivio dell'osservatore: due tabelle, due vite.

I cambi vivono 21 giorni di promessa -- TRE MERCOLEDI', l'unita' dell'esempio
da cui nasce il cervello -- ma la soglia tecnica e' 22: il ventiduesimo e' una
guardia che riconcilia la promessa con l'aritmetica dei secondi assoluti.
Gli oggetti restano.
"""
import json
import os
import sqlite3

import pytest

from hiris.app.mind.store import (
    ATTEMPTS_SHOWN,
    READING_RETENTION_S,
    SCHEMA_VERSION,
    ObservationsStore,
)

ADESSO = 1787572800.0  # 24 agosto 2026, 12:00 UTC


@pytest.fixture()
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def test_un_cambio_si_rilegge_intero(archivio):
    archivio.record(quando_ts=ADESSO, source="entita",
                    subject="climate.camera_t", da="off", a="heat")
    righe = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)
    assert righe == [{"quando_ts": ADESSO, "fonte": "entita",
                      "soggetto": "climate.camera_t", "da": "off", "a": "heat",
                      "device_class": None,
                      "domain": None, "title": None, "friendly_name": None,
                      "attributes": None,
                      "first_occurred": None}]


def test_annota_scrive_la_classe_quando_c_e(archivio):
    """Tre classi arrivarono col Task 3, punto 0, quando decidevano il
    pavimento e la gamba -- entrambi usciti (11/09 e 17/09/2026). Resta solo
    `device_class`, l'unica con un lettore vivo: senza di lei, `genre_for` non
    puo' ricostruire il genere di un rilevatore di fumo o di un allagamento
    quando l'aggregazione rilegge il grezzo. Le altre due sono uscite con
    `_migration_15`."""
    archivio.record(quando_ts=ADESSO, source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke")
    riga = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)[0]
    assert riga["device_class"] == "smoke"


def test_annota_senza_classe_scrive_none(archivio):
    """Le condizioni di sistema, e il grezzo scritto prima di questa
    correzione, non portano la classe: deve rileggersi come `None`, non
    far sollevare `record`."""
    archivio.record(quando_ts=ADESSO, source="sistema",
                    subject="problema:sonos.x", da=None, a="aperto")
    riga = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)[0]
    assert riga["device_class"] is None


def test_i_cambi_tornano_dal_PIU_VECCHIO(archivio):
    """L'aggregazione ricostruisce cose che cominciano e finiscono: le vuole
    in ordine di accadimento, non a rovescio come la cronaca degli atti."""
    for ts in (ADESSO + 30, ADESSO, ADESSO + 10):
        archivio.record(quando_ts=ts, source="entita", subject="x", da=None, a="1")
    assert [r["quando_ts"] for r in archivio.readings(from_ts=0.0, to_ts=ADESSO + 99)] == \
        [ADESSO, ADESSO + 10, ADESSO + 30]


def test_cambi_finestra_semiaperta_da_incluso_a_escluso(archivio):
    """La finestra e' [from_ts, to_ts): from_ts dentro, to_ts fuori. E' la
    convenzione che fa combaciare i giorni adiacenti senza sovrapporli --
    altrimenti il cambio esattamente a mezzanotte finirebbe in entrambi."""
    archivio.record(quando_ts=ADESSO, source="entita", subject="x", da=None, a="sul-da_ts")
    archivio.record(quando_ts=ADESSO + 100, source="entita", subject="x", da=None, a="sul-a_ts")
    righe = archivio.readings(from_ts=ADESSO, to_ts=ADESSO + 100)
    assert [r["a"] for r in righe] == ["sul-da_ts"]


def test_la_potatura_tiene_ventidue_giorni(archivio):
    assert READING_RETENTION_S == 22 * 86400
    vecchio = ADESSO - READING_RETENTION_S - 1
    dentro = ADESSO - READING_RETENTION_S + 1
    archivio.record(quando_ts=vecchio, source="entita", subject="x", da=None, a="1")
    archivio.record(quando_ts=dentro, source="entita", subject="x", da=None, a="1")
    assert archivio.prune(ADESSO) == 1
    assert [r["quando_ts"] for r in archivio.readings(from_ts=0.0, to_ts=ADESSO)] == [dentro]


def test_la_potatura_non_tocca_la_riga_esattamente_alla_soglia(archivio):
    """Si prova solo a piu' o meno un secondo lascia passare `<` mutato in
    `<=`: la riga esattamente sulla soglia deve sopravvivere."""
    soglia = ADESSO - READING_RETENTION_S
    archivio.record(quando_ts=soglia, source="entita", subject="x", da=None, a="soglia")
    archivio.prune(ADESSO)
    righe = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)
    assert [r["a"] for r in righe] == ["soglia"]


def test_fonte_invalida_solleva(archivio):
    """Un refuso dello scrittore futuro ('sistemi' per 'sistema') non deve
    entrare in silenzio: l'aggregazione lo perderebbe senza dirlo."""
    with pytest.raises(sqlite3.IntegrityError):
        archivio.record(quando_ts=ADESSO, source="sistemi", subject="x", da=None, a="1")


def test_ENTRAMBE_le_fonti_ammesse_entrano(archivio):
    """Il CHECK ha due valori: se un test prova solo che un terzo e' rifiutato,
    meta' dell'elenco resta non provata ammissibile.

    `sistema` e' la fonte delle condizioni di Home Assistant, e nessun altro
    test la scrive: un restringimento del CHECK resterebbe verde in suite e
    l'osservatore comincerebbe a sollevare dal vivo, in silenzio fino alla casa.
    """
    archivio.record(quando_ts=ADESSO, source="entita",
                    subject="climate.camera", da="off", a="heat")
    archivio.record(quando_ts=ADESSO + 1, source="sistema",
                    subject="problema:sonos.subscriptions_failed", da=None, a="aperto")
    assert ([r["fonte"] for r in archivio.readings(from_ts=0.0, to_ts=ADESSO + 2)]
            == ["entita", "sistema"])


# -- D1: il filtro per fonte deve entrare nella query SQL -------------------
#
# `rebuild_conditions` chiedeva TUTTI i cambi senza `limit`: col LIMIT
# di default sopravvivono i piu' VECCHI, e sui 320.000 cambi/22gg misurati
# (spec §9②) questo perdeva gli ultimi otto giorni. La correzione e' filtrare
# per `source="sistema"` -- poche centinaia di righe -- PRIMA del LIMIT.

def test_cambi_filtro_per_fonte(archivio):
    """La mutazione e' togliere il filtro dalla query: con righe di entrambe
    le fonti nell'archivio, `readings(source="sistema")` deve tornare SOLO quelle
    di sistema."""
    archivio.record(quando_ts=ADESSO, source="entita",
                    subject="climate.camera", da="off", a="heat")
    archivio.record(quando_ts=ADESSO + 1, source="sistema",
                    subject="problema:sonos.subscriptions_failed", da=None, a="aperto")
    archivio.record(quando_ts=ADESSO + 2, source="entita",
                    subject="light.salotto", da="off", a="on")
    righe = archivio.readings(from_ts=0.0, to_ts=ADESSO + 3, source="sistema")
    assert [r["soggetto"] for r in righe] == ["problema:sonos.subscriptions_failed"]


def test_a_change_carries_the_domain_and_the_title(tmp_path):
    """Il grezzo dev'essere autosufficiente: fra tre settimane la voce di
    configurazione potrebbe non esistere piu', e la riga deve dire ancora
    cosa si era rotto.

    Mutazione: non passare `domain`/`title` alla INSERT -- il test torna
    rosso su `assert row["domain"] == "lifx"`.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    store.record(quando_ts=1000.0, source="sistema",
                 subject="integrazione:01ABC", da=None, a="setup_retry",
                 domain="lifx", title="Abat-jour")
    row = store.readings(from_ts=0, to_ts=2000)[0]
    assert row["domain"] == "lifx"
    assert row["title"] == "Abat-jour"
    assert row["a"] == "setup_retry"
    store.close()


def test_migration_3_adds_the_columns_to_an_old_archive(tmp_path):
    """Il caso che conta e' l'archivio del proprietario al primo avvio dopo
    l'aggiornamento, non uno nato oggi.

    Mutazione: togliere `3: _migration_3` dal dizionario `migrations`
    passato a `init_schema` in `ObservationsStore.__init__` (`mind/store.py`)
    -- il test torna rosso su `assert "domain" in columns`.
    """
    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " quando_ts REAL NOT NULL, fonte TEXT NOT NULL, soggetto TEXT NOT NULL,"
        " da TEXT, a TEXT, device_class TEXT, state_class TEXT, source_type TEXT);"
        "CREATE TABLE oggetti (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " giorno TEXT NOT NULL, genere TEXT NOT NULL, protagonista TEXT NOT NULL,"
        " inizio_ts REAL NOT NULL, fine_ts REAL, corpo_json TEXT NOT NULL);"
        "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a)"
        " VALUES(900.0,'sistema','integrazione:01OLD',NULL,'aperto');"
        "PRAGMA user_version = 2;")
    conn.commit()
    conn.close()

    store = ObservationsStore(path)
    columns = [r[1] for r in store._conn.execute("PRAGMA table_info(cambi)")]
    assert "domain" in columns
    assert "title" in columns
    assert columns.count("domain") == 1
    old = store.readings(from_ts=0, to_ts=2000)[0]
    assert old["domain"] is None          # la riga vecchia resta leggibile
    assert old["a"] == "aperto"
    store.close()


def test_a_log_condition_carries_first_occurred_as_a_float(tmp_path):
    """`first_occurred` e' un ISTANTE (Task 2, «le tracce e il log»), non un
    testo: la colonna e' `TEXT` (stessa forma di `_add_missing_columns`, vedi
    il suo docstring), ma `readings()` lo rilegge come `float | None` --
    l'unica delle colonne nuove per cui serve una conversione, perche' e'
    l'unica numerica.

    Mutazione: tornare la stringa grezza di SQLite invece di convertirla
    (`"first_occurred": r["first_occurred"]` senza `float(...)`) -- il test
    torna rosso su `assert row["first_occurred"] == 1700000000.0` (diventa
    la stringa `'1700000000.0'`, che Python non considera mai uguale al
    float `1700000000.0`).
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    store.record(quando_ts=1000.0, source="sistema",
                 subject="log:homeassistant.core@core.py:10", da=None, a="ERROR",
                 domain="homeassistant.core", title="boom", first_occurred=1700000000.0)
    row = store.readings(from_ts=0, to_ts=2000)[0]
    assert row["first_occurred"] == 1700000000.0
    assert isinstance(row["first_occurred"], float)
    store.close()


def test_first_occurred_is_null_when_not_given(tmp_path):
    """Un *repair* o un'integrazione non dichiarano mai `first_occurred`:
    `None` resta `None`, non zero -- e' l'assenza di un fatto, non un fatto
    che vale zero.

    Mutazione: passare `0.0` come default invece di `None` in `record()` --
    il test torna rosso su `assert row["first_occurred"] is None`.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    store.record(quando_ts=1000.0, source="sistema",
                 subject="integrazione:01ABC", da=None, a="setup_retry",
                 domain="lifx", title="Abat-jour")
    row = store.readings(from_ts=0, to_ts=2000)[0]
    assert row["first_occurred"] is None
    store.close()


def test_migration_4_adds_first_occurred_to_an_old_archive(tmp_path):
    """Il caso che conta e' l'archivio del proprietario al primo avvio dopo
    l'aggiornamento -- gia' alla v3 (con `domain`/`title`, senza
    `first_occurred`), non uno nato oggi.

    Mutazione: togliere `4: _migration_4` dal dizionario `migrations`
    passato a `init_schema` in `ObservationsStore.__init__` (`mind/store.py`)
    -- il test torna rosso su `assert "first_occurred" in columns`.
    """
    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " quando_ts REAL NOT NULL, fonte TEXT NOT NULL, soggetto TEXT NOT NULL,"
        " da TEXT, a TEXT, device_class TEXT, state_class TEXT, source_type TEXT,"
        " domain TEXT, title TEXT);"
        "CREATE TABLE oggetti (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " giorno TEXT NOT NULL, genere TEXT NOT NULL, protagonista TEXT NOT NULL,"
        " inizio_ts REAL NOT NULL, fine_ts REAL, corpo_json TEXT NOT NULL);"
        "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a,domain,title)"
        " VALUES(900.0,'sistema','integrazione:01OLD',NULL,'aperto','lifx','Abat-jour');"
        "PRAGMA user_version = 3;")
    conn.commit()
    conn.close()

    store = ObservationsStore(path)
    columns = [r[1] for r in store._conn.execute("PRAGMA table_info(cambi)")]
    assert "first_occurred" in columns
    assert columns.count("first_occurred") == 1
    old = store.readings(from_ts=0, to_ts=2000)[0]
    assert old["first_occurred"] is None   # la riga vecchia resta leggibile
    assert old["domain"] == "lifx"
    store.close()


def test_un_archivio_vecchio_si_migra_senza_perdere_le_righe(tmp_path):
    """Una riga scritta dallo schema v1 (senza le tre colonne di classe) deve
    continuare a rileggersi: la migrazione aggiunge colonne, non riscrive la
    tabella. E' la stessa garanzia gia' provata per `Journal`."""
    percorso = os.path.join(str(tmp_path), "vecchio.db")
    conn = sqlite3.connect(percorso)
    conn.executescript(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " quando_ts REAL NOT NULL,"
        " fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),"
        " soggetto TEXT NOT NULL, da TEXT, a TEXT);")
    conn.execute(
        "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a) VALUES(?,?,?,?,?)",
        (ADESSO, "entita", "climate.vecchio", "off", "heat"))
    conn.commit()
    conn.close()

    a = ObservationsStore(percorso)
    try:
        riga = a.readings(from_ts=0.0, to_ts=ADESSO + 1)[0]
        assert riga["soggetto"] == "climate.vecchio"
        assert riga["device_class"] is None
        # E la scrittura nuova, con le classi, deve funzionare sullo stesso db.
        a.record(quando_ts=ADESSO + 1, source="entita",
                subject="binary_sensor.fumo", da="off", a="on",
                device_class="smoke")
        riga_nuova = next(r for r in a.readings(from_ts=0.0, to_ts=ADESSO + 2)
                          if r["soggetto"] == "binary_sensor.fumo")
        assert riga_nuova["device_class"] == "smoke"
    finally:
        a.close()


# ---------------------------------------------------------------------------
# Il nome amichevole: si SALVA al momento dell'evento (fetta «il nome»,
# 07/09/2026, docs .superpowers/sdd/collaudo-3.22/indagine-nomi-e-stati.md §5)
# ---------------------------------------------------------------------------

def test_a_change_carries_the_friendly_name(tmp_path):
    """Il grezzo deve dire ancora DI CHE COSA si parlava anche fra sei mesi,
    quando quell'entita' potrebbe non esistere piu': stessa ragione di
    `domain`/`title`, piu' quella propria di questa colonna (gli `oggetti`
    vivono piu' a lungo dei `cambi`, e un nome risolto dopo non si
    troverebbe piu').

    Mutazione ESEGUITA: scrivere `None` al posto di `friendly_name` fra i
    valori dell'INSERT in `record()` (`mind/store.py`) -- il test torna
    rosso su `assert row["friendly_name"] == "Termostato Bagno"` (diventa
    `None`).
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    store.record(quando_ts=1000.0, source="entita",
                 subject="climate.bagno_1p_t_bagno_1p_t", da="off", a="heat",
                 device_class=None, friendly_name="Termostato Bagno")
    row = store.readings(from_ts=0, to_ts=2000)[0]
    assert row["friendly_name"] == "Termostato Bagno"
    assert row["soggetto"] == "climate.bagno_1p_t_bagno_1p_t"
    store.close()


def test_the_friendly_name_is_null_when_not_given(tmp_path):
    """Una condizione di sistema non e' un'entita' e non porta un nome, e su
    un'entita' Home Assistant scrive l'attributo solo se il nome composto
    non e' vuoto (`helpers/entity.py:1166-1167` @ `2026.9.1`). `None` e' un
    campo vuoto DICHIARATO, non una stringa vuota travestita da nome.

    Mutazione ESEGUITA: mettere `friendly_name: str | None = ""` come
    default in `record()` -- il test torna rosso su
    `assert row["friendly_name"] is None`.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    store.record(quando_ts=1000.0, source="sistema",
                 subject="integrazione:01ABC", da=None, a="setup_retry",
                 domain="lifx", title="Abat-jour")
    row = store.readings(from_ts=0, to_ts=2000)[0]
    assert row["friendly_name"] is None
    store.close()


def test_migration_5_adds_friendly_name_to_an_old_archive(tmp_path):
    """**Questa non e' una formalita': e' l'archivio del proprietario.** Un
    archivio scritto dalla versione precedente (v4: con `first_occurred`,
    senza `friendly_name`) deve aprirsi, rileggersi, e continuare a
    scrivere -- e le sue righe vecchie devono restare vecchie, cioe' senza
    nome, perche' riempirle dall'anagrafe di oggi vorrebbe dire attribuire
    a ieri il nome di oggi.

    Mutazione ESEGUITA: togliere `5: _migration_5` dal dizionario
    `migrations` passato a `init_schema` in `ObservationsStore.__init__`
    (`mind/store.py`) -- il test torna rosso su
    `assert "friendly_name" in columns`.
    """
    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " quando_ts REAL NOT NULL,"
        " fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),"
        " soggetto TEXT NOT NULL, da TEXT, a TEXT,"
        " device_class TEXT, state_class TEXT, source_type TEXT,"
        " domain TEXT, title TEXT, first_occurred TEXT);"
        "CREATE TABLE oggetti (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " giorno TEXT NOT NULL, genere TEXT NOT NULL, protagonista TEXT NOT NULL,"
        " inizio_ts REAL NOT NULL, fine_ts REAL, corpo_json TEXT NOT NULL);"
        "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a,device_class)"
        " VALUES(900.0,'entita','climate.vecchio','off','heat','temperature');"
        # Dal 15/09/2026 l'archivio vecchio porta un RESOCONTO, non un
        # oggetto: la tabella e' uscita con la migrazione 10, e la prova
        # verifica la stessa cosa -- una riga scritta prima della colonna
        # `friendly_name` non prende il nome di oggi.
        "CREATE TABLE IF NOT EXISTS resoconto (giorno TEXT PRIMARY KEY,"
        " corpo_json TEXT NOT NULL, scritto_ts REAL NOT NULL);"
        "INSERT INTO resoconto(giorno,corpo_json,scritto_ts)"
        " VALUES('2026-09-01',"
        "'{\"giorno\": \"2026-09-01\", \"cronaca\": "
        "[{\"chi\": \"climate.vecchio\", \"cosa\": \"heat\"}]}', 1.0);"
        "PRAGMA user_version = 4;")
    conn.commit()
    conn.close()

    store = ObservationsStore(path)
    try:
        columns = [r[1] for r in store._conn.execute("PRAGMA table_info(cambi)")]
        assert "friendly_name" in columns
        assert columns.count("friendly_name") == 1
        assert (store._conn.execute("PRAGMA user_version").fetchone()[0]
                == SCHEMA_VERSION)

        # La riga vecchia si rilegge intera, e il suo nome e' ASSENTE -- non
        # riempito a posteriori.
        old = store.readings(from_ts=0, to_ts=2000)[0]
        assert old["friendly_name"] is None
        assert old["a"] == "heat"
        assert old["device_class"] == "temperature"

        # E l'oggetto scritto prima della colonna si rilegge ancora: la
        # migrazione aggiunge una colonna a `cambi`, non tocca `oggetti`.
        voce = (store.report("2026-09-01") or {})["cronaca"][0]
        assert voce["cosa"] == "heat"
        assert "nome" not in voce, (
            "una riga scritta prima della colonna `friendly_name` non prende "
            "il nome di oggi: non si riempie a posteriori dall'anagrafe")

        # E la scrittura NUOVA, col nome, funziona sullo stesso archivio.
        store.record(quando_ts=1000.0, source="entita", subject="person.paolo",
                     da="home", a="not_home", friendly_name="Paolo")
        nuova = next(r for r in store.readings(from_ts=0, to_ts=2000)
                     if r["soggetto"] == "person.paolo")
        assert nuova["friendly_name"] == "Paolo"
    finally:
        store.close()


def test_l_ultima_notizia_di_un_soggetto_e_la_sua_riga_piu_recente_di_qualunque_stato(archivio):
    """`last_seen`: l'ultima volta che Home Assistant ha parlato di un
    soggetto, anche con un `unavailable` e anche dopo un giorno qualunque --
    e' il quando con cui la cronaca chiude l'episodio di una fonte finita
    (Task 1.4 degli attori). Le condizioni di sistema non sono fonti della
    casa e non entrano. Mutazione ESEGUITA: `MAX` -> `MIN` -- rossa."""
    archivio.record(quando_ts=100.0, source="entita", subject="switch.pompa",
                    da="off", a="on")
    archivio.record(quando_ts=300.0, source="entita", subject="switch.pompa",
                    da="on", a="unavailable")
    archivio.record(quando_ts=200.0, source="entita", subject="light.b",
                    da="off", a="on")
    archivio.record(quando_ts=900.0, source="sistema", subject="switch.pompa",
                    da=None, a="setup_error")

    assert archivio.last_seen(["switch.pompa", "light.b", "light.mai"]) == {
        "switch.pompa": 300.0, "light.b": 200.0}
    assert archivio.last_seen([]) == {}


def test_l_ultima_riga_prima_di_un_istante_c_e_una_per_soggetto(archivio):
    """Lo stato in cui un soggetto ERA quando il giorno e' cominciato.

    Senza, l'aggregazione di un giorno vede solo cio' che e' cambiato DENTRO
    quel giorno, e un termostato acceso da quattro giorni non esiste: misurato
    sulla casa vera il 10/09/2026, gli otto termostati hanno prodotto otto
    oggetti il 06/09 (il giorno del loro ultimo cambio vero) e **zero** il 07,
    l'08 e il 09.

    Mutazione che la uccide: togliere il `ROW_NUMBER()`/`rn = 1` e tornare
    tutte le righe -- il soggetto comparirebbe con la sua riga piu' VECCHIA,
    cioe' con lo stato sbagliato.
    """
    archivio.record(quando_ts=100.0, source="entita", subject="climate.camera",
                    da="off", a="heat")
    archivio.record(quando_ts=200.0, source="entita", subject="climate.camera",
                    da="heat", a="cool")
    archivio.record(quando_ts=150.0, source="entita", subject="light.cucina",
                    da="off", a="on")
    archivio.record(quando_ts=900.0, source="entita", subject="light.cucina",
                    da="on", a="off")

    ultime = archivio.last_before(500.0, since_ts=0.0)

    assert {r["soggetto"]: r["a"] for r in ultime} == {
        "climate.camera": "cool", "light.cucina": "on"}


def test_l_ultima_riga_prima_resta_dentro_la_finestra_dichiarata(archivio):
    """La finestra la dichiara chi chiede (Task 1.4 degli attori): una riga
    piu' vecchia di `since_ts` non torna, anche se la potatura non l'ha
    ancora tolta -- misurato: 4 voci di cronaca da una riga di settimane
    prima. Mutazione ESEGUITA: tolto `quando_ts >= ?` dalla query (e il suo
    argomento) -- rossa."""
    archivio.record(quando_ts=100.0, source="entita", subject="device_tracker.vecchio",
                    da="home", a="not_home")
    archivio.record(quando_ts=300.0, source="entita", subject="light.cucina",
                    da="off", a="on")

    assert [r["soggetto"] for r in archivio.last_before(500.0, since_ts=200.0)] == [
        "light.cucina"]


def test_le_transizioni_sono_i_cambi_di_STATO_dei_soggetti_chiesti(archivio):
    """`transitions`: cio' che `facts` rigioca per sapere da quando e' in corso
    cio' che e' in corso a mezzanotte. Dal piu' vecchio, solo i soggetti
    chiesti, solo dentro la finestra, senza le righe di solo attributo (che
    non aprono e non chiudono niente) e senza le condizioni di sistema.
    Mutazione ESEGUITA: tolto `da IS NOT a` -- rossa (entra la riga di
    attributo delle 250)."""
    archivio.record(quando_ts=50.0, source="entita", subject="climate.camera",
                    da="off", a="heat")
    archivio.record(quando_ts=200.0, source="entita", subject="climate.camera",
                    da="heat", a="unavailable")
    archivio.record(quando_ts=100.0, source="entita", subject="climate.camera",
                    da="off", a="heat")
    archivio.record(quando_ts=250.0, source="entita", subject="climate.camera",
                    da="heat", a="heat", attributes='{"hvac_action": "idle"}')
    archivio.record(quando_ts=300.0, source="entita", subject="light.cucina",
                    da="off", a="on")
    archivio.record(quando_ts=320.0, source="sistema", subject="climate.camera",
                    da=None, a="setup_error")
    archivio.record(quando_ts=600.0, source="entita", subject="climate.camera",
                    da="unavailable", a="heat")

    righe = archivio.transitions(["climate.camera"], from_ts=60.0, to_ts=500.0)

    assert [(r["quando_ts"], r["a"]) for r in righe] == [(100.0, "heat"),
                                                          (200.0, "unavailable")]
    assert archivio.transitions([], from_ts=0.0, to_ts=1000.0) == []


def test_le_transizioni_portano_la_prima_riga_di_ciascuno_anche_di_attributo(archivio):
    """La prima riga di un soggetto nella finestra entra anche se e' di solo
    attributo: dice in che stato la finestra comincia (un termostato acceso
    prima della finestra, la riga che l'ha acceso potata). Le righe di
    attributo DOPO la prima restano fuori (revisione cloud, giro 3)."""
    for quando in (100.0, 200.0, 300.0):
        archivio.record(quando_ts=quando, source="entita", subject="climate.camera",
                        da="heat", a="heat", attributes='{"hvac_action": "heating"}')
    archivio.record(quando_ts=150.0, source="entita", subject="light.cucina",
                    da="off", a="on")

    righe = archivio.transitions(["climate.camera", "light.cucina"],
                                 from_ts=50.0, to_ts=500.0)

    assert [(r["soggetto"], r["quando_ts"]) for r in righe] == [
        ("climate.camera", 100.0), ("light.cucina", 150.0)]


def test_l_ultima_riga_prima_non_guarda_le_condizioni_di_sistema(archivio):
    """Le condizioni di sistema (`problema:`, `integrazione:`, `log:`) hanno
    gia' un meccanismo loro che le tiene aperte fra i riavvii
    (`watcher.rebuild_conditions`): riseminarle anche da qui vorrebbe dire due
    risposte alla stessa domanda, e la prima a divergere e' quella che nessuno
    guarda."""
    archivio.record(quando_ts=100.0, source="sistema",
                    subject="integrazione:abc", da=None, a="setup_error")

    assert archivio.last_before(500.0, since_ts=0.0) == []


# ── Il tentativo: «ci ho provato, ed e' andata cosi'» ───────────────────────
#
# Fetta «l'osservatore chiede a chi risponde davvero» (11/09/2026). La tabella
# `reconsideration` conserva i giri RIUSCITI; quelli falliti non lasciavano
# traccia da nessuna parte, e la pagina dello scope diceva «non e' mai stata
# fatta» -- vero alla lettera, e falso come racconto. Misurato sulla casa vera
# l'11/09: l'osservatore aveva provato e fallito ogni dieci minuti per
# quaranta minuti, HIRIS non registrava piu' una riga sulla casa, e nessuna
# porta lo diceva.
#
# E' la distinzione a tre stati che questo prodotto difende ovunque e che
# `api/handlers_mind.py` dichiara per iscritto: **un guasto non si appiattisce
# su un'assenza.**


def test_un_tentativo_fallito_lascia_la_sua_traccia(archivio):
    """Prima di questa riga il fallimento era indistinguibile dal «non ancora
    successo»: due stati diversi appiattiti su un `null`.

    Mutazione che la uccide: non scrivere il dettaglio.
    """
    archivio.record_attempt(when_ts=1000.0, outcome="non_riuscito",
                            detail="il modello non ha risposto: RuntimeError")

    ultimo = archivio.recent_attempts()[0]
    assert ultimo["quando_ts"] == 1000.0
    assert ultimo["esito"] == "non_riuscito"
    assert ultimo["dettaglio"] == "il modello non ha risposto: RuntimeError"


def test_l_ultimo_tentativo_e_l_ULTIMO(archivio):
    """La domanda e' «com'e' andata l'ultima volta», e la prima riga della
    tabella e' la piu' vecchia -- stessa regola di `last_reconsideration`.

    Mutazione che la uccide: ordinare crescente.
    """
    archivio.record_attempt(when_ts=1000.0, outcome="non_riuscito", detail="vecchio")
    archivio.record_attempt(when_ts=2000.0, outcome="riuscito", detail="nuovo")

    assert archivio.recent_attempts()[0]["dettaglio"] == "nuovo"


def test_senza_nessun_tentativo_e_None_non_un_esito_finto(archivio):
    """`None` e' «nessuno ci ha mai provato». Un esito di fabbrica sarebbe
    un'affermazione che nessuno ha verificato."""
    assert archivio.recent_attempts() == []


def test_l_archivio_del_proprietario_prende_la_tabella_nuova_riaprendosi(tmp_path):
    """**Non e' una formalita': e' l'archivio vero, con 22 giorni di grezzo
    dentro.** Un archivio scritto dalla 3.26.0 non ha `scope_attempt`. Se non
    comparisse all'apertura, la pagina dello scope morirebbe su «no such
    table» proprio sulla casa che ha gia' una storia -- cioe' su tutte quelle
    che contano.

    Mutazione ESEGUITA l'11/09/2026, vista rossa e ripristinata: togliere
    `CREATE TABLE IF NOT EXISTS scope_attempt` da `_SCHEMA`; il test fallisce
    con `sqlite3.OperationalError: no such table: scope_attempt`.

    La `PRAGMA user_version` e' **5**, quella che la 3.26.0 scrive davvero
    (`init_schema(..., version=5)`): la prima stesura ne dichiarava 6, una
    versione mai esistita che `init_schema` avrebbe comunque retrocesso --
    rilievo della review indipendente, 11/09/2026.
    """
    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " quando_ts REAL NOT NULL,"
        " fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),"
        " soggetto TEXT NOT NULL, da TEXT, a TEXT,"
        " device_class TEXT, state_class TEXT, source_type TEXT,"
        " domain TEXT, title TEXT, first_occurred TEXT, friendly_name TEXT);"
        "CREATE TABLE reconsideration (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " done_ts REAL NOT NULL, window_s REAL, cadence_s REAL, reason TEXT);"
        "INSERT INTO reconsideration(done_ts,window_s,cadence_s,reason)"
        " VALUES(900.0, 604800.0, 302400.0, 'mai fatta');"
        "PRAGMA user_version = 5;")
    conn.commit()
    conn.close()

    archivio = ObservationsStore(path)
    try:
        assert archivio.recent_attempts() == [], (
            "nessun tentativo annotato non e' un guasto: e' un archivio che "
            "viene da prima che i tentativi si annotassero")
        archivio.record_attempt(when_ts=1000.0, outcome="non_riuscito",
                                detail="il piano non ha risposto")
        assert archivio.recent_attempts()[0]["esito"] == "non_riuscito"
        # La storia che c'era resta dov'era: la tabella nuova si aggiunge, non
        # sostituisce.
        assert archivio.last_reconsideration()["motivo"] == "mai fatta"
    finally:
        archivio.close()


def test_i_tentativi_recenti_raccontano_se_sta_fallendo_da_un_po(archivio):
    """**La domanda vera del proprietario non e' «com'e' andata l'ultima
    volta», e' «sta funzionando?».** Un tentativo solo non la distingue: dopo
    un fallimento il giro richiede subito, quindi l'ultimo esito e' sempre
    «accodata» e il guasto sparirebbe dalla vista in pochi secondi.

    Misurato l'11/09/2026: l'osservatore ha fallito quattro volte di fila in
    quaranta minuti. Quella e' la riga che serviva, e non esisteva.

    Mutazione che la uccide: tornare il piu' vecchio invece del piu' recente.
    """
    archivio.record_attempt(when_ts=1000.0, outcome="non_riuscito", detail="primo")
    archivio.record_attempt(when_ts=2000.0, outcome="non_riuscito", detail="secondo")
    archivio.record_attempt(when_ts=3000.0, outcome="accodata", detail="terzo")

    assert [t["dettaglio"] for t in archivio.recent_attempts()] == [
        "terzo", "secondo", "primo"]


def test_i_tentativi_recenti_si_fermano_al_tetto(archivio):
    """La pagina ne mostra una manciata: la storia intera di una casa accesa
    da mesi sarebbe migliaia di righe per rispondere a «sta funzionando?»."""
    for n in range(ATTEMPTS_SHOWN + 2):
        archivio.record_attempt(when_ts=float(n), outcome="riuscito")

    # `== ATTEMPTS_SHOWN`, non `<= 10`: un `<=` passa anche con un tetto di
    # tre, e il numero copiato a mano sarebbe il doppione che il commento
    # della pagina si vanta di non avere (rilievo della review indipendente).
    assert len(archivio.recent_attempts()) == ATTEMPTS_SHOWN


def test_un_tentativo_porta_la_VERSIONE_su_cui_e_avvenuto(archivio):
    """**Un aggiornamento e' un fatto nuovo**: i fallimenti di prima
    riguardavano un altro programma. Senza la versione accanto, il freno che
    rallenta i tentativi conterebbe i guasti di una versione riparata e
    ritarderebbe la verifica della riparazione di ore (misurato l'11/09/2026:
    quattro fallimenti sulla 3.27.0 tenevano fermo l'osservatore per ottanta
    minuti dopo l'aggiornamento alla 3.27.1).

    Mutazione che la uccide: non scrivere la versione.
    """
    archivio.record_attempt(when_ts=1000.0, outcome="non_riuscito",
                            detail="x", version="3.27.0")

    assert archivio.recent_attempts()[0]["versione"] == "3.27.0"


def test_un_tentativo_di_un_archivio_VECCHIO_non_ha_versione_e_non_mente(archivio):
    """Le righe scritte prima della colonna rileggono `None`: e' vero, quella
    versione non l'hanno mai portata. Non si riempie a posteriori con quella di
    oggi -- sarebbe attribuire a ieri un fatto di adesso."""
    archivio.record_attempt(when_ts=1000.0, outcome="riuscito", detail="x")

    assert archivio.recent_attempts()[0]["versione"] is None


def test_migrazione_6_aggiunge_la_versione_a_un_archivio_gia_scritto(tmp_path):
    """L'archivio della 3.27.0 ha `scope_attempt` SENZA la colonna: senza
    migrazione il primo `record_attempt` dopo l'aggiornamento fallirebbe, e
    l'osservatore smetterebbe di annotare i propri tentativi -- cioe' proprio
    la porta che serve a vedere se sta funzionando.

    Mutazione ESEGUITA l'11/09/2026, vista rossa e ripristinata: togliere
    `6: _migration_6` dal dizionario passato a `init_schema`.
    """
    path = str(tmp_path / "oss.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE scope_attempt (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " tried_ts REAL NOT NULL, outcome TEXT NOT NULL, detail TEXT);"
        "INSERT INTO scope_attempt(tried_ts,outcome,detail)"
        " VALUES(900.0,'non_riuscito','di prima');"
        "PRAGMA user_version = 5;")
    conn.commit()
    conn.close()

    archivio = ObservationsStore(path)
    try:
        archivio.record_attempt(when_ts=1000.0, outcome="riuscito",
                                detail="dopo", version="3.27.1")
        esiti = archivio.recent_attempts()
        assert [e["versione"] for e in esiti] == ["3.27.1", None]
        assert esiti[1]["dettaglio"] == "di prima"
    finally:
        archivio.close()


def test_una_base_dati_VECCHIA_prende_la_colonna_degli_attributi(tmp_path):
    """**La migrazione v6 -> v7, provata su una base dati alla versione 6.**

    La base dati e' COSTRUITA QUI con lo schema di prima -- non e' una copia di
    quella del proprietario, e la parola «vera» che stava in questa riga era
    imprecisa (Fable 5.1, 13/09/2026). Quello che prova e' comunque il caso che
    conta: una nuova nasce gia' completa (`init_schema` timbra la versione e
    non esegue nessuna migrazione), quindi provare solo quella lascerebbe la
    migrazione non esercitata -- mentre e' il ramo che gira
    sull'installazione del proprietario, dove `osservazioni.db` esiste da
    settimane.

    Si controlla anche che la riga scritta PRIMA resti leggibile e legga
    `None`: e' vero, quella riga quegli attributi non li aveva.

    Mutazione ESEGUITA: togliere `7: _migration_7` dalla mappa delle
    migrazioni -- rossa, `KeyError: 'attributes'` alla rilettura.
    """
    from hiris.app.storage import connect

    db = str(tmp_path / "vecchia.db")
    vecchia = connect(db)
    vecchia.executescript("""
CREATE TABLE cambi (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quando_ts REAL NOT NULL,
    fonte TEXT NOT NULL CHECK(fonte IN ('entita','sistema')), soggetto TEXT NOT NULL,
    da TEXT, a TEXT, device_class TEXT, state_class TEXT, source_type TEXT,
    domain TEXT, title TEXT, first_occurred TEXT, friendly_name TEXT);
""")
    vecchia.execute("INSERT INTO cambi(quando_ts,fonte,soggetto,da,a) "
                    "VALUES(1,'entita','climate.x','off','heat')")
    vecchia.execute("PRAGMA user_version = 6")
    vecchia.commit()
    vecchia.close()

    archivio = ObservationsStore(db)
    try:
        [riga] = archivio.readings(from_ts=0, to_ts=2e9)
        assert riga["soggetto"] == "climate.x"
        assert riga["attributes"] is None
        assert (archivio._conn.execute("PRAGMA user_version").fetchone()[0]
                == SCHEMA_VERSION)
    finally:
        archivio.close()

def test_il_grezzo_dice_da_quando_comincia(tmp_path):
    """Il recupero dei resoconti mancanti deve sapere **fin dove indietro ha
    senso andare**: non oltre il grezzo, perche' un giorno si rifa' solo
    finche' il suo grezzo esiste. E' l'archivio a saperlo, non chi lo usa.

    Mutazione: tornare `MAX(quando_ts)` invece di `MIN` -- rossa.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    assert store.oldest_reading_ts() is None, "un archivio vuoto non ha un primo giorno"
    store.record(quando_ts=2000.0, source="entita", subject="light.a", da="off", a="on")
    store.record(quando_ts=1000.0, source="entita", subject="light.b", da="off", a="on")
    assert store.oldest_reading_ts() == 1000.0
    store.close()

def test_migration_8_disinnesca_i_numeri_calcolati_con_un_operazione_ritirata(tmp_path):
    """**Un numero sbagliato, gia' archiviato sulla casa vera**: il resoconto
    del 26/08 portava `energia_consumata = -0,98 kWh`, calcolata con
    `primo_ultimo_differenza` su una serie di cambi orari invece che sulle
    letture cumulate di un contatore.

    La ricetta si toglie dal sapere (migrazione del sapere), ma **il numero
    resta scritto nel resoconto** e nessuno lo rifa': un giorno si rifa' solo
    finche' il suo grezzo esiste, e l'analista legge i resoconti, non le
    ricette. Un numero sbagliato che vive per sempre in un archivio che esiste
    per non dirne.

    Quindi la riga diventa un **«non calcolabile» col suo perche'** -- il posto
    dove l'analista guarda cio' che manca -- e la cronaca **non si tocca**:
    cancellare il resoconto perderebbe l'unica copia di un giorno il cui grezzo
    e' scaduto.

    Mutazione: togliere `8: _migration_8` dal dizionario `migrations` -- rossa
    su `assert "valore" not in riga`.
    """
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    store.replace_report("2026-08-26", {
        "giorno": "2026-08-26",
        "misure": [
            {"soggetto": "dev1", "misura": "energia_consumata",
             "operazione": "primo_ultimo_differenza", "valore": -0.98,
             "unita": "kWh", "copertura": 1.0},
            {"soggetto": "dev2", "misura": "produzione",
             "operazione": "somma_periodo", "valore": 23.8,
             "unita": "kWh", "copertura": 1.0}],
        "forme": [],
        "cronaca": [{"chi": "light.x", "cosa": "on"}]})
    store._conn.execute("PRAGMA user_version = 7")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    scritto = riaperto.report("2026-08-26")
    ritirata, buona = scritto["misure"]
    assert "valore" not in ritirata
    assert "primo_ultimo_differenza" in ritirata["non_calcolabile"]
    assert ritirata["misura"] == "energia_consumata", "la riga resta al suo posto"
    # Cio' che si calcola ancora non si tocca.
    assert buona["valore"] == 23.8
    # E la cronaca nemmeno: e' l'unica copia di quel giorno.
    assert scritto["cronaca"] == [{"chi": "light.x", "cosa": "on"}]
    riaperto.close()


def test_migration_8_non_tocca_un_resoconto_tutto_buono(tmp_path):
    """Una migrazione che riscrive cio' che non deve e' peggio del difetto che
    ripara: un resoconto sano resta **il byte che era**.

    **La prima stesura di questa prova non poteva fallire**, e l'ha detto la
    mutazione: confrontava `scritto_ts`, che la migrazione non tocca nemmeno
    quando riscrive -- quindi `if changed:` -> `if True:` restava verde. E
    confrontare il dizionario riletto non servirebbe: `json.dumps` dello stesso
    dizionario da' sempre gli stessi byte, quindi una riscrittura sarebbe
    invisibile.

    Si scrive la riga a mano con una **spaziatura sua**: se la migrazione la
    riscrive, la normalizza, e il confronto cade. E' l'unica differenza che
    sopravvive a un giro completo di `json`.

    Mutazione: riscrivere ogni resoconto invece dei soli toccati -- rossa.
    """
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    # `obiettivo` c'e' gia': cosi' nemmeno `_migration_9` ha ragione di
    # toccarlo, e resta in piedi la proprieta' che questa prova sorveglia --
    # un resoconto SANO non si riscrive.
    grezzo = ('{"giorno": "2026-09-13",   "obiettivo": {"testo": "x", '
              '"scritto_ts": 1.0},   "misure": [{"soggetto": "dev2", '
              '"misura": "produzione", "operazione": "somma_periodo", '
              '"valore": 23.31, "unita": "kWh", "copertura": 1.0}], '
              '"forme": [],   "cronaca": []}')
    store._conn.execute(
        "INSERT INTO resoconto(giorno,corpo_json,scritto_ts) VALUES(?,?,?)",
        ("2026-09-13", grezzo, 1.0))
    store._conn.execute("PRAGMA user_version = 7")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    dopo = riaperto._conn.execute(
        "SELECT corpo_json FROM resoconto WHERE giorno = '2026-09-13'"
    ).fetchone()["corpo_json"]
    assert dopo == grezzo, "un resoconto sano non si riscrive"
    riaperto.close()

def test_migration_9_scrive_l_obiettivo_sui_resoconti_gia_archiviati(tmp_path):
    """I 19 giorni gia' archiviati sulla casa vera (26/08 -> 13/09, misurati il
    14/09/2026) non portano l'obiettivo: la riga e' nata dopo di loro. Ma
    l'archivio sa ancora quale valeva -- `objective_at` legge la stessa base
    dati -- quindi si puo' scrivere senza inventare niente.

    **Si legge alla fine del giorno**, la stessa istante che usa
    `aggregate_day`: due strade sullo stesso giorno devono dare la stessa
    risposta.

    Mutazione: togliere `9: _migration_9` dal dizionario `migrations` -- rossa.
    """
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    store.set_objective("la domanda di allora", when_ts=1787000000.0)
    store.replace_report("2026-09-13", {
        "giorno": "2026-09-13", "misure": [], "forme": [], "cronaca": []})
    store._conn.execute("PRAGMA user_version = 8")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    scritto = riaperto.report("2026-09-13")
    assert scritto["obiettivo"]["testo"] == "la domanda di allora"
    riaperto.close()


def test_migration_9_non_tocca_un_resoconto_che_l_obiettivo_ce_l_ha_gia(tmp_path):
    """Un resoconto scritto dopo porta gia' il suo, e puo' essere DIVERSO da
    quello di adesso: sovrascriverlo con l'obiettivo di oggi sarebbe dire che
    quel giorno rispondeva a una domanda che non era la sua.

    Mutazione: riscrivere sempre -- rossa.
    """
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    store.set_objective("quella di adesso", when_ts=1787000000.0)
    store.replace_report("2026-09-13", {
        "giorno": "2026-09-13",
        "obiettivo": {"testo": "quella di allora", "scritto_ts": 1.0},
        "misure": [], "forme": [], "cronaca": []})
    store._conn.execute("PRAGMA user_version = 8")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    assert riaperto.report("2026-09-13")["obiettivo"]["testo"] == "quella di allora"
    riaperto.close()

def test_l_analisi_di_un_giorno_si_scrive_e_si_rilegge(tmp_path):
    """L'analista produce una cosa al giorno, e si sostituisce come il
    resoconto: rifare un giorno lo rifa', non lo accoda.

    Mutazione: `INSERT` nudo invece di `INSERT OR REPLACE` -- rossa sul
    secondo `replace_analysis`.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        assert store.analysis("2026-09-15") is None
        store.replace_analysis("2026-09-15", {"osservazioni": [{"cosa": "x"}]})
        assert store.analysis("2026-09-15")["osservazioni"] == [{"cosa": "x"}]
        store.replace_analysis("2026-09-15", {"osservazioni": []})
        assert store.analysis("2026-09-15")["osservazioni"] == []
    finally:
        store.close()


def test_il_SILENZIO_si_scrive_e_non_si_confonde_col_non_aver_girato(tmp_path):
    """*\u00abIl silenzio e' un esito legittimo\u00bb* (spec §10). Ma \u00abho guardato e non
    c'era niente da dire\u00bb e \u00abnon ho guardato\u00bb sono due cose diverse, ed e' la
    stessa legge del resoconto vuoto: la prima si scrive.

    Mutazione: non scrivere quando l'elenco e' vuoto -- rossa (`None` invece
    di un'analisi con zero osservazioni).
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        store.replace_analysis("2026-09-15", {"osservazioni": []})
        scritta = store.analysis("2026-09-15")
        assert scritta is not None, "il silenzio si archivia"
        assert scritta["osservazioni"] == []
    finally:
        store.close()


def test_le_analisi_tornano_dalla_piu_recente(tmp_path):
    """Una cronaca si legge da adesso all'indietro, come gli obiettivi e i
    resoconti.

    Mutazione: ordinare crescente -- rossa.
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for g in ("2026-09-13", "2026-09-15", "2026-09-14"):
            store.replace_analysis(g, {"osservazioni": []})
        assert [a["giorno"] for a in store.analyses(limit=10)] == [
            "2026-09-15", "2026-09-14", "2026-09-13"]
    finally:
        store.close()


def _archive_v13(tmp_path, analisi: dict):
    """Un archivio fermo alla versione 13 con un'analisi scritta a mano: la
    forma che il vecchio attuatore lasciava (`attuazione`)."""
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    store.replace_analysis("2026-09-20", analisi)
    store._conn.execute("PRAGMA user_version = 13")
    store._conn.commit()
    store.close()
    return percorso


def test_migration_14_porta_gli_esiti_del_vecchio_attuatore_alla_chiave_del_proponente(tmp_path):
    """Le analisi archiviate prima del 06/10/2026 portano gli esiti sotto
    `attuazione`; quelle nuove sotto `proposer_turn.OUTCOMES_KEY`. Due chiavi
    vorrebbero due lettori (fondamenta 2): la migrazione le porta a una.

    - un'**indagine** e una **riparazione** non proponevano niente: diventano
      «niente», col perche' che l'attuatore aveva scritto;
    - una **proposta da fare a mano** diventa «a_mano» e cita la riga che il
      giro di allora aveva messo in `proposte` (per impronta);
    - una **proposta costruibile** diventa «costruita»: l'id della costruzione
      allora non si scriveva, e non si inventa;
    - un esito senza impronta non si legava a nessuna osservazione e non
      compariva: non si porta.

    Mutazione ESEGUITA: `_migration_14` che torna subito -- rossa (togliere
    la voce dal dizionario fa rosso per un'altra ragione: `init_schema` rifiuta
    il buco).
    """
    from hiris.app.mind import proposer_turn

    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    ident = store.add_proposal(text="sposta la lavatrice", perche="x",
                               fingerprint="imp-mano", prova={"v": 1},
                               stakes=None, now_ts=1.0)
    store.replace_analysis("2026-09-20", {
        "osservazioni": [],
        "attuazione": {"su_fondamento": "aaa", "esiti": [
            {"gesto": "indagine", "trovato": "fra le 19 e le 22", "impronta": "imp-ind"},
            {"gesto": "riparazione", "riscritta": True, "trovato": "ricetta riscritta",
             "impronta": "imp-rip"},
            {"gesto": "proposta", "trovato": "sposta la lavatrice", "impronta": "imp-mano"},
            {"gesto": "proposta", "costruibile": True, "trovato": "un'automazione",
             "impronta": "imp-cos"},
            {"gesto": "indagine", "trovato": "orfano"}]}})
    store._conn.execute("PRAGMA user_version = 13")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    try:
        analisi = riaperto.analysis("2026-09-20")
        assert "attuazione" not in analisi
        assert proposer_turn.outcomes_of(analisi) == [
            {"impronta": "imp-ind", "esito": proposer_turn.NOTHING,
             "perche": "fra le 19 e le 22"},
            {"impronta": "imp-rip", "esito": proposer_turn.NOTHING,
             "perche": "ricetta riscritta"},
            {"impronta": "imp-mano", "esito": proposer_turn.BY_HAND, "proposta_id": ident},
            {"impronta": "imp-cos", "esito": proposer_turn.BUILT},
        ]
    finally:
        riaperto.close()


def test_migration_14_non_scavalca_un_esito_del_proponente_gia_scritto(tmp_path):
    """Un giorno puo' avere tutte e due le chiavi: l'attuatore ha girato la
    mattina, il proponente dopo l'aggiornamento. Per la stessa impronta vale
    l'esito del proponente, che e' il piu' recente.

    Mutazione ESEGUITA: accodare gli esiti vecchi senza guardare quelli nuovi
    -- rossa."""
    from hiris.app.mind import proposer_turn

    nuovo = {"impronta": "imp", "esito": proposer_turn.NOTHING, "perche": "di oggi"}
    percorso = _archive_v13(tmp_path, {
        "osservazioni": [], proposer_turn.OUTCOMES_KEY: [nuovo],
        "attuazione": {"esiti": [{"gesto": "indagine", "trovato": "di ieri",
                                  "impronta": "imp"}]}})

    riaperto = ObservationsStore(percorso)
    try:
        assert proposer_turn.outcomes_of(riaperto.analysis("2026-09-20")) == [nuovo]
    finally:
        riaperto.close()


def test_migration_14_non_tocca_un_analisi_senza_attuazione(tmp_path):
    """Una migrazione che riscrive cio' che non deve e' peggio del difetto che
    ripara: la riga scritta a mano con una spaziatura sua resta il byte che
    era (stessa tecnica di `test_migration_8_non_tocca_un_resoconto_tutto_buono`).

    Mutazione ESEGUITA: riscrivere ogni analisi -- rossa."""
    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    grezzo = '{"osservazioni":   [],   "proponente": []}'
    store._conn.execute(
        "INSERT INTO analisi(giorno,corpo_json,scritto_ts) VALUES(?,?,?)",
        ("2026-09-21", grezzo, 1.0))
    store._conn.execute("PRAGMA user_version = 13")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    try:
        dopo = riaperto._conn.execute(
            "SELECT corpo_json FROM analisi WHERE giorno = '2026-09-21'"
        ).fetchone()["corpo_json"]
        assert dopo == grezzo
    finally:
        riaperto.close()


def test_migration_14_cita_la_proposta_nata_PRIMA_dell_analisi(tmp_path):
    """Due proposte con la stessa impronta: quella del giro di allora, e una
    nata dopo che l'analisi era gia' scritta (la prova e' cambiata, la domanda
    e' tornata). L'esito migrato cita la prima: la seconda risponde a
    un'altra analisi. Revisione, giro 74, N74-1: senza questa prova il filtro
    su `scritto_ts` non era sorvegliato.

    Mutazione ESEGUITA: `creata_ts <= ? + 1e12` -- rossa (cita la seconda)."""
    from hiris.app.mind import proposer_turn

    percorso = str(tmp_path / "oss.db")
    store = ObservationsStore(percorso)
    allora = store.add_proposal(text="a", perche="x", fingerprint="imp",
                                prova={"v": 1}, stakes=None, now_ts=1.0)
    store.add_proposal(text="b", perche="x", fingerprint="imp",
                       prova={"v": 2}, stakes=None, now_ts=3.0)
    store._conn.execute(
        "INSERT INTO analisi(giorno,corpo_json,scritto_ts) VALUES(?,?,?)",
        ("2026-09-20", json.dumps({"osservazioni": [], "attuazione": {"esiti": [
            {"gesto": "proposta", "trovato": "a", "impronta": "imp"}]}}), 2.0))
    store._conn.execute("PRAGMA user_version = 13")
    store._conn.commit()
    store.close()

    riaperto = ObservationsStore(percorso)
    try:
        assert proposer_turn.outcomes_of(riaperto.analysis("2026-09-20")) == [
            {"impronta": "imp", "esito": proposer_turn.BY_HAND, "proposta_id": allora}]
    finally:
        riaperto.close()


def test_migration_14_non_porta_una_proposta_a_mano_senza_riga(tmp_path):
    """Un «a_mano» senza la riga in `proposte` farebbe dire alla pagina «la
    trovi in Proposte» dove non c'e' niente: come l'esito senza impronta, non
    si porta. Revisione, giro 74, N74-2.

    Mutazione ESEGUITA: portarlo senza `proposta_id` -- rossa."""
    from hiris.app.mind import proposer_turn

    percorso = _archive_v13(tmp_path, {
        "osservazioni": [], "attuazione": {"esiti": [
            {"gesto": "proposta", "trovato": "a", "impronta": "orfana"}]}})

    riaperto = ObservationsStore(percorso)
    try:
        analisi = riaperto.analysis("2026-09-20")
        assert "attuazione" not in analisi
        assert proposer_turn.outcomes_of(analisi) == []
    finally:
        riaperto.close()


#: La `cambi` di un archivio alla versione 14, con le due colonne che nessuno
#: leggeva: e' la forma che la migrazione 15 trova sul disco del proprietario.
_CAMBI_V14 = (
    "CREATE TABLE cambi (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " quando_ts REAL NOT NULL,"
    " fonte TEXT NOT NULL CHECK(fonte IN ('entita', 'sistema')),"
    " soggetto TEXT NOT NULL, da TEXT, a TEXT, device_class TEXT,"
    " state_class TEXT, source_type TEXT, domain TEXT, title TEXT,"
    " first_occurred TEXT, friendly_name TEXT, attributes TEXT);"
    "CREATE INDEX idx_cambi_quando ON cambi(quando_ts);"
    "CREATE INDEX idx_cambi_soggetto ON cambi(soggetto, quando_ts);")


def _archive_v14(tmp_path) -> str:
    """Un archivio alla 14 con tre cambi veri, e il piu' vecchio gia' potato:
    la potatura toglie dal fondo."""
    percorso = str(tmp_path / "oss.db")
    ObservationsStore(percorso).close()
    conn = sqlite3.connect(percorso)
    conn.executescript(
        "DROP TABLE cambi;" + _CAMBI_V14
        + "INSERT INTO cambi(quando_ts,fonte,soggetto,da,a,device_class,state_class,"
          "source_type,domain,title,first_occurred,friendly_name,attributes) VALUES"
          "(800.0,'entita','light.potata','on','off',NULL,NULL,NULL,NULL,NULL,NULL,"
          "NULL,NULL),"
          "(900.0,'entita','sensor.contatore','1','2','energy','total_increasing',"
          "NULL,NULL,NULL,NULL,'Contatore','{\"x\": 1}'),"
          "(901.0,'sistema','log:abc',NULL,'aperto',NULL,NULL,NULL,'sonos',"
          "'Errore',  '880.5',NULL,NULL),"
          "(902.0,'entita','device_tracker.tel','home','not_home',NULL,NULL,'gps',"
          "NULL,NULL,NULL,'Telefono',NULL);"
          "DELETE FROM cambi WHERE id = 1;"
          "PRAGMA user_version = 14;")
    conn.commit()
    conn.close()
    return percorso


def _shape(percorso) -> tuple:
    conn = sqlite3.connect(percorso)
    try:
        return (
            [r[1] for r in conn.execute("PRAGMA table_info(cambi)")],
            conn.execute("SELECT * FROM cambi ORDER BY id").fetchall(),
            sorted(r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name = 'cambi' AND name LIKE 'idx_%'")),
            conn.execute("PRAGMA user_version").fetchone()[0],
            [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'cambi_v%'")])
    finally:
        conn.close()


def test_migration_15_toglie_le_due_colonne_mai_lette_senza_perdere_i_cambi(tmp_path):
    """`cambi.state_class` e `source_type` si scrivevano a ogni cambio e
    nessuno le leggeva (Tappa 8, G-06): escono ricostruendo la tabella, come
    `_migration_12`. Le righe restano coi loro id e con ogni colonna che
    resta, gli indici tornano, e la riga nuova prende l'id dopo l'ultimo. Una
    seconda apertura non cambia niente.

    Mutazioni ESEGUITE: `_MIGRATION_15_STEPS` vuoto -- rossa sulle colonne;
    senza ricreare gli indici -- rossa sugli indici.
    """
    percorso = _archive_v14(tmp_path)

    store = ObservationsStore(percorso)
    try:
        store.record(quando_ts=903.0, source="entita", subject="light.x",
                     da="off", a="on")
        righe = store.readings(from_ts=0.0, to_ts=2000.0)
    finally:
        store.close()

    colonne, tabella, indici, versione, avanzi = _shape(percorso)
    assert "state_class" not in colonne and "source_type" not in colonne
    assert colonne == ["id", "quando_ts", "fonte", "soggetto", "da", "a",
                       "device_class", "domain", "title", "first_occurred",
                       "friendly_name", "attributes"]
    assert [r[0] for r in tabella] == [2, 3, 4, 5]
    assert [(r["soggetto"], r["device_class"], r["friendly_name"], r["attributes"],
             r["domain"], r["title"], r["first_occurred"]) for r in righe] == [
        ("sensor.contatore", "energy", "Contatore", '{"x": 1}', None, None, None),
        ("log:abc", None, None, None, "sonos", "Errore", 880.5),
        ("device_tracker.tel", None, "Telefono", None, None, None, None),
        ("light.x", None, None, None, None, None, None)]
    assert indici == ["idx_cambi_quando", "idx_cambi_soggetto"]
    assert versione == SCHEMA_VERSION
    assert avanzi == []

    prima = _shape(percorso)
    ObservationsStore(percorso).close()
    assert _shape(percorso) == prima


def test_migration_15_rifiuta_ancora_una_fonte_sconosciuta(tmp_path):
    """La tabella ricostruita porta il `CHECK` su `fonte`: senza, un refuso
    dello scrittore entrerebbe in silenzio (vedi `test_fonte_invalida_solleva`).

    Mutazione ESEGUITA: il `CHECK` tolto dalla ricostruzione -- rossa."""
    store = ObservationsStore(_archive_v14(tmp_path))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.record(quando_ts=1.0, source="altro", subject="x", da=None, a="1")
    finally:
        store.close()
