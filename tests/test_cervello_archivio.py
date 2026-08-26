"""L'archivio dell'osservatore: due tabelle, due vite.

I cambi vivono 21 giorni -- TRE MERCOLEDI', l'unita' dell'esempio da cui nasce
il cervello -- perche' il modo di costruire gli oggetti cambiera', e con una
notte sola ogni miglioramento varrebbe solo da domani. Gli oggetti restano.
"""
import os

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


def test_la_potatura_tiene_ventun_giorni(archivio):
    assert CONSERVAZIONE_CAMBI_S == 21 * 86400
    vecchio = ADESSO - CONSERVAZIONE_CAMBI_S - 1
    dentro = ADESSO - CONSERVAZIONE_CAMBI_S + 1
    archivio.annota(quando_ts=vecchio, fonte="entita", soggetto="x", da=None, a="1")
    archivio.annota(quando_ts=dentro, fonte="entita", soggetto="x", da=None, a="1")
    assert archivio.pota(ADESSO) == 1
    assert [r["quando_ts"] for r in archivio.cambi(da_ts=0.0, a_ts=ADESSO)] == [dentro]


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


def test_dimenticare_un_giorno_lo_svuota_e_non_tocca_gli_altri(archivio):
    """Rifare l'aggregazione di un giorno deve poter essere idempotente:
    altrimenti ogni ritentativo raddoppia gli oggetti in silenzio."""
    for g in ("2026-08-24", "2026-08-25"):
        archivio.salva_oggetto(giorno=g, genere="funzionamento", protagonista="x",
                               inizio_ts=ADESSO, fine_ts=None, corpo={})
    assert archivio.dimentica_oggetti("2026-08-24") == 1
    assert [o["giorno"] for o in archivio.oggetti()] == ["2026-08-25"]
