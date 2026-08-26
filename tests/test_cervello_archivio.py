"""L'archivio dell'osservatore: due tabelle, due vite.

I cambi vivono 21 giorni di promessa -- TRE MERCOLEDI', l'unita' dell'esempio
da cui nasce il cervello -- ma la soglia tecnica e' 22: il ventiduesimo e' una
guardia che riconcilia la promessa con l'aritmetica dei secondi assoluti.
Gli oggetti restano.
"""
import os
import sqlite3

import pytest

from hiris.app.cervello.archivio import (
    CONSERVAZIONE_CAMBI_S, ArchivioOsservazioni,
)

ADESSO = 1787572800.0  # 24 agosto 2026, 12:00 UTC


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioOsservazioni(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def test_un_cambio_si_rilegge_intero(archivio):
    archivio.annota(quando_ts=ADESSO, fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    righe = archivio.cambi(da_ts=0.0, a_ts=ADESSO + 1)
    assert righe == [{"quando_ts": ADESSO, "fonte": "entita",
                      "soggetto": "climate.camera_t", "da": "off", "a": "heat"}]


def test_i_cambi_tornano_dal_PIU_VECCHIO(archivio):
    """L'aggregazione ricostruisce cose che cominciano e finiscono: le vuole
    in ordine di accadimento, non a rovescio come la cronaca degli atti."""
    for ts in (ADESSO + 30, ADESSO, ADESSO + 10):
        archivio.annota(quando_ts=ts, fonte="entita", soggetto="x", da=None, a="1")
    assert [r["quando_ts"] for r in archivio.cambi(da_ts=0.0, a_ts=ADESSO + 99)] == \
        [ADESSO, ADESSO + 10, ADESSO + 30]


def test_si_puo_chiedere_un_soggetto_solo(archivio):
    archivio.annota(quando_ts=ADESSO, fonte="entita", soggetto="a", da=None, a="1")
    archivio.annota(quando_ts=ADESSO, fonte="entita", soggetto="b", da=None, a="1")
    righe = archivio.cambi(da_ts=0.0, a_ts=ADESSO + 1, soggetto="a")
    assert [r["soggetto"] for r in righe] == ["a"]


def test_cambi_finestra_semiaperta_da_incluso_a_escluso(archivio):
    """La finestra e' [da_ts, a_ts): da_ts dentro, a_ts fuori. E' la
    convenzione che fa combaciare i giorni adiacenti senza sovrapporli --
    altrimenti il cambio esattamente a mezzanotte finirebbe in entrambi."""
    archivio.annota(quando_ts=ADESSO, fonte="entita", soggetto="x", da=None, a="sul-da_ts")
    archivio.annota(quando_ts=ADESSO + 100, fonte="entita", soggetto="x", da=None, a="sul-a_ts")
    righe = archivio.cambi(da_ts=ADESSO, a_ts=ADESSO + 100)
    assert [r["a"] for r in righe] == ["sul-da_ts"]


def test_la_potatura_tiene_ventidue_giorni(archivio):
    assert CONSERVAZIONE_CAMBI_S == 22 * 86400
    vecchio = ADESSO - CONSERVAZIONE_CAMBI_S - 1
    dentro = ADESSO - CONSERVAZIONE_CAMBI_S + 1
    archivio.annota(quando_ts=vecchio, fonte="entita", soggetto="x", da=None, a="1")
    archivio.annota(quando_ts=dentro, fonte="entita", soggetto="x", da=None, a="1")
    assert archivio.pota(ADESSO) == 1
    assert [r["quando_ts"] for r in archivio.cambi(da_ts=0.0, a_ts=ADESSO)] == [dentro]


def test_la_potatura_non_tocca_la_riga_esattamente_alla_soglia(archivio):
    """Si prova solo a piu' o meno un secondo lascia passare `<` mutato in
    `<=`: la riga esattamente sulla soglia deve sopravvivere."""
    soglia = ADESSO - CONSERVAZIONE_CAMBI_S
    archivio.annota(quando_ts=soglia, fonte="entita", soggetto="x", da=None, a="soglia")
    archivio.pota(ADESSO)
    righe = archivio.cambi(da_ts=0.0, a_ts=ADESSO + 1)
    assert [r["a"] for r in righe] == ["soglia"]


def test_la_potatura_NON_tocca_gli_oggetti(archivio):
    """Le due tabelle hanno due vite: il grezzo si butta, cio' che si e' capito
    resta. Una potatura che si portasse via gli oggetti cancellerebbe mesi di
    osservazione per liberare qualche megabyte."""
    archivio.salva_oggetto(giorno="2026-07-01", genere="funzionamento",
                           protagonista="climate.camera_t",
                           inizio_ts=ADESSO - 60 * 86400, fine_ts=ADESSO - 60 * 86400 + 3600,
                           corpo={"nota": "vecchissimo"})
    archivio.pota(ADESSO)
    assert len(archivio.oggetti()) == 1


def test_un_oggetto_si_rilegge_col_suo_corpo(archivio):
    ident = archivio.salva_oggetto(
        giorno="2026-08-24", genere="funzionamento", protagonista="climate.camera_t",
        inizio_ts=ADESSO, fine_ts=ADESSO + 5700,
        corpo={"comprimari": ["sensor.camera_temperatura"],
               "misure": {"temperatura": {"da": 18.2, "a": 21.0}}})
    assert isinstance(ident, int)
    o = archivio.oggetti(giorno="2026-08-24")[0]
    assert o["protagonista"] == "climate.camera_t"
    assert o["corpo"]["misure"]["temperatura"]["a"] == 21.0
    assert o["fine_ts"] == ADESSO + 5700


def test_un_oggetto_ancora_aperto_non_ha_fine(archivio):
    """A mezzanotte una cosa puo' essere ancora in corso. `None` dice «non e'
    finita», che e' un fatto -- zero direbbe «e' finita subito»."""
    archivio.salva_oggetto(giorno="2026-08-24", genere="guasto",
                           protagonista="integrazione:sonos", inizio_ts=ADESSO,
                           fine_ts=None, corpo={})
    assert archivio.oggetti()[0]["fine_ts"] is None


def test_oggetti_tornano_dal_PIU_RECENTE(archivio):
    """Il docstring lo afferma: con al piu' una riga per giorno la mutazione
    DESC->ASC non si nota. Ci vogliono piu' righe nello stesso giorno."""
    for protagonista, ts in (("primo", ADESSO), ("terzo", ADESSO + 200), ("secondo", ADESSO + 100)):
        archivio.salva_oggetto(giorno="2026-08-24", genere="funzionamento",
                               protagonista=protagonista, inizio_ts=ts, fine_ts=None, corpo={})
    assert [o["protagonista"] for o in archivio.oggetti(giorno="2026-08-24")] == \
        ["terzo", "secondo", "primo"]


def test_dimenticare_un_giorno_lo_svuota_e_non_tocca_gli_altri(archivio):
    """Rifare l'aggregazione di un giorno deve poter essere idempotente:
    altrimenti ogni ritentativo raddoppia gli oggetti in silenzio."""
    for g in ("2026-08-24", "2026-08-25"):
        archivio.salva_oggetto(giorno=g, genere="funzionamento", protagonista="x",
                               inizio_ts=ADESSO, fine_ts=None, corpo={})
    assert archivio.dimentica_oggetti("2026-08-24") == 1
    assert [o["giorno"] for o in archivio.oggetti()] == ["2026-08-25"]


def test_sostituisci_giorno_sostituisce_non_accoda(archivio):
    """`salva_oggetto` da solo e' un INSERT nudo: rifare un giorno chiamandolo
    due volte accoderebbe. `sostituisci_giorno` e' l'operazione che rifa'
    un giorno per intero, e deve lasciare UNA copia, non due."""
    archivio.sostituisci_giorno("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "vecchio",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    archivio.sostituisci_giorno("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "nuovo",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    righe = archivio.oggetti(giorno="2026-08-24")
    assert len(righe) == 1
    assert righe[0]["protagonista"] == "nuovo"


def test_sostituisci_giorno_fallito_a_meta_non_lascia_il_giorno_mezzo_scritto(archivio):
    """Se l'inserimento fallisce a meta' (un oggetto che rompe davvero
    l'INSERT: `genere` NOT NULL violato), il giorno deve restare quello di
    prima -- non mezzo riscritto e non svuotato."""
    archivio.sostituisci_giorno("2026-08-24", [
        {"genere": "funzionamento", "protagonista": "originale",
         "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
    ])
    with pytest.raises(sqlite3.IntegrityError):
        archivio.sostituisci_giorno("2026-08-24", [
            {"genere": "funzionamento", "protagonista": "primo-scritto",
             "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
            {"genere": None, "protagonista": "rompe-insert",
             "inizio_ts": ADESSO, "fine_ts": None, "corpo": {}},
        ])
    righe = archivio.oggetti(giorno="2026-08-24")
    assert len(righe) == 1
    assert righe[0]["protagonista"] == "originale"


def test_fonte_invalida_solleva(archivio):
    """Un refuso dello scrittore futuro ('sistemi' per 'sistema') non deve
    entrare in silenzio: l'aggregazione lo perderebbe senza dirlo."""
    with pytest.raises(sqlite3.IntegrityError):
        archivio.annota(quando_ts=ADESSO, fonte="sistemi", soggetto="x", da=None, a="1")
