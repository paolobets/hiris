"""L'archivio dell'osservatore: due tabelle, due vite.

I cambi vivono 21 giorni di promessa -- TRE MERCOLEDI', l'unita' dell'esempio
da cui nasce il cervello -- ma la soglia tecnica e' 22: il ventiduesimo e' una
guardia che riconcilia la promessa con l'aritmetica dei secondi assoluti.
Gli oggetti restano.
"""
import os
import sqlite3

import pytest

from hiris.app.mind.store import (
    READING_RETENTION_S,
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
                      "device_class": None, "state_class": None, "source_type": None}]


def test_annota_scrive_le_tre_classi_quando_ci_sono(archivio):
    """Il pavimento decide la gamba di `sensor`/`binary_sensor` da queste tre
    classi (Task 3, punto 0): senza, l'aggregazione non puo' mai ricostruire
    la gamba di un rilevatore di fumo o di un contatore di energia."""
    archivio.record(quando_ts=ADESSO, source="entita",
                    subject="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke", state_class=None, source_type=None)
    riga = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)[0]
    assert riga["device_class"] == "smoke"
    assert riga["state_class"] is None
    assert riga["source_type"] is None


def test_annota_senza_classi_scrive_none(archivio):
    """Le condizioni di sistema, e il grezzo scritto prima di questa
    correzione, non portano le tre classi: devono rileggersi come `None`, non
    far sollevare `record`."""
    archivio.record(quando_ts=ADESSO, source="sistema",
                    subject="problema:sonos.x", da=None, a="aperto")
    riga = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1)[0]
    assert riga["device_class"] is None
    assert riga["state_class"] is None
    assert riga["source_type"] is None


def test_i_cambi_tornano_dal_PIU_VECCHIO(archivio):
    """L'aggregazione ricostruisce cose che cominciano e finiscono: le vuole
    in ordine di accadimento, non a rovescio come la cronaca degli atti."""
    for ts in (ADESSO + 30, ADESSO, ADESSO + 10):
        archivio.record(quando_ts=ts, source="entita", subject="x", da=None, a="1")
    assert [r["quando_ts"] for r in archivio.readings(from_ts=0.0, to_ts=ADESSO + 99)] == \
        [ADESSO, ADESSO + 10, ADESSO + 30]


def test_si_puo_chiedere_un_soggetto_solo(archivio):
    archivio.record(quando_ts=ADESSO, source="entita", subject="a", da=None, a="1")
    archivio.record(quando_ts=ADESSO, source="entita", subject="b", da=None, a="1")
    righe = archivio.readings(from_ts=0.0, to_ts=ADESSO + 1, subject="a")
    assert [r["soggetto"] for r in righe] == ["a"]


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


def test_la_potatura_NON_tocca_gli_oggetti(archivio):
    """Le due tabelle hanno due vite: il grezzo si butta, cio' che si e' capito
    resta. Una potatura che si portasse via gli oggetti cancellerebbe mesi di
    osservazione per liberare qualche megabyte."""
    archivio.replace_day("2026-07-01", [
        {"genere": "funzionamento", "protagonista": "climate.camera_t",
         "inizio_ts": ADESSO - 60 * 86400, "fine_ts": ADESSO - 60 * 86400 + 3600,
         "corpo": {"nota": "vecchissimo"}},
    ])
    archivio.prune(ADESSO)
    assert len(archivio.facts()) == 1


def test_un_oggetto_si_rilegge_col_suo_corpo(archivio):
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "climate.camera_t",
         "inizio_ts": ADESSO, "fine_ts": ADESSO + 5700,
         "corpo": {"comprimari": ["sensor.camera_temperatura"],
                   "misure": {"temperatura": {"da": 18.2, "a": 21.0}}}},
    ])
    o = archivio.facts(day="2026-08-24")[0]
    assert isinstance(o["id"], int)
    assert o["protagonista"] == "climate.camera_t"
    assert o["corpo"]["misure"]["temperatura"]["a"] == 21.0
    assert o["fine_ts"] == ADESSO + 5700


def test_un_oggetto_ancora_aperto_non_ha_fine(archivio):
    """A mezzanotte una cosa puo' essere ancora in corso. `None` dice «non e'
    finita», che e' un fatto -- zero direbbe «e' finita subito»."""
    archivio.replace_day("2026-08-24", [
        {"genere": "guasto", "protagonista": "integrazione:sonos",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    assert archivio.facts()[0]["fine_ts"] is None


def test_oggetti_tornano_dal_PIU_RECENTE(archivio):
    """Il docstring lo afferma: con al piu' una riga per giorno la mutazione
    DESC->ASC non si nota. Ci vogliono piu' righe nello stesso giorno."""
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": protagonista,
         "inizio_ts": ts, "fine_ts": None, "corpo": {}}
        for protagonista, ts in (("primo", ADESSO), ("terzo", ADESSO + 200),
                                 ("secondo", ADESSO + 100))
    ])
    assert [o["protagonista"] for o in archivio.facts(day="2026-08-24")] == \
        ["terzo", "secondo", "primo"]


def test_sostituisci_giorno_sostituisce_non_accoda(archivio):
    """Un INSERT nudo, ripetuto sullo stesso giorno, accoderebbe una seconda
    copia senza errore. `replace_day` e' l'operazione che rifa' un
    giorno per intero, in una transazione sola, e deve lasciare UNA copia,
    non due."""
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "vecchio",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "nuovo",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    righe = archivio.facts(day="2026-08-24")
    assert len(righe) == 1
    assert righe[0]["protagonista"] == "nuovo"


def test_sostituisci_giorno_NON_tocca_gli_altri_giorni(archivio):
    """La cancellazione dentro `replace_day` deve essere circoscritta
    al giorno che si rifa'.

    Senza questo test una DELETE allargata per errore spazzerebbe via TUTTI
    gli oggetti -- mesi di comprensione, che oltre la ritenzione del grezzo non
    si rifanno piu' -- e la suite resterebbe verde.
    """
    archivio.replace_day("2026-08-23", [
        {"genere": "funzionamento", "protagonista": "l-altro-giorno",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "il-giorno-rifatto",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    assert ([o["protagonista"] for o in archivio.facts(day="2026-08-23")]
            == ["l-altro-giorno"])


def test_sostituisci_giorno_fallito_a_meta_non_lascia_il_giorno_mezzo_scritto(archivio):
    """Se l'inserimento fallisce a meta' (un oggetto che rompe davvero
    l'INSERT: `genere` NOT NULL violato), il giorno deve restare quello di
    prima -- non mezzo riscritto e non svuotato."""
    archivio.replace_day("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "originale",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    with pytest.raises(sqlite3.IntegrityError):
        archivio.replace_day("2026-08-24", [
            {"genere": "funzionamento", "protagonista": "primo-scritto",
             "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
            {"genere": None, "protagonista": "rompe-insert",
             "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
        ])
    righe = archivio.facts(day="2026-08-24")
    assert len(righe) == 1
    assert righe[0]["protagonista"] == "originale"


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
        riga_nuova = a.readings(from_ts=0.0, to_ts=ADESSO + 2, subject="binary_sensor.fumo")[0]
        assert riga_nuova["device_class"] == "smoke"
    finally:
        a.close()
