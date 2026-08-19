"""Il battito: mai in ritardo, mai due volte, e il silenzio e' un esito riuscito."""
import os

import pytest

from hiris.app.schedulatore.archivio import ArchivioPromesse
from hiris.app.schedulatore.orologio import Orologio
from hiris.app.schedulatore.promessa import TOLLERANZA_S

ADESSO = 1_755_600_000.0
pytestmark = pytest.mark.asyncio


class PortaFinta:
    """Una porta che sa RIUSCIRE e sa FALLIRE: se sapesse solo riuscire, i test
    sul fallimento non potrebbero diventare rossi."""

    def __init__(self, esito=None):
        self.chiamate = []
        self._esito = esito or {"eseguito": True, "cambiato": ["light.studio"],
                                "esecuzione_id": "e1"}

    async def __call__(self, chiamata, *, origine):
        self.chiamate.append((chiamata, origine))
        return self._esito


class TurnoFinto:
    def __init__(self, risposta=None):
        self.viste = []
        self._risposta = risposta or {"avvisare": True, "testo": "e' salita di 2 gradi"}

    async def __call__(self, promessa):
        self.viste.append(promessa)
        return self._risposta


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _crea_fai(archivio, *, quando, recapito=None):
    return archivio.crea({
        "specie": "fai", "frase": "alle 17 accendi lo studio", "quando_ts": quando,
        "chiamata": {"servizio": "light.turn_on", "bersaglio": {"entita": ["light.studio"]}},
        "recapito": recapito,
    }, adesso=ADESSO)["promessa"]["id"]


def _crea_chiedi(archivio, *, quando, recapito=None):
    return archivio.crea({
        "specie": "chiedi", "frase": "fra un'ora verifica la temperatura",
        "quando_ts": quando, "domanda": "e' aumentata?", "recapito": recapito,
    }, adesso=ADESSO)["promessa"]["id"]


async def test_un_fai_scaduto_passa_dalla_porta_con_origine_schedulatore(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Orologio(archivio, esegui=porta, interpreta=TurnoFinto()).batti(ADESSO + 11)

    assert len(porta.chiamate) == 1
    assert porta.chiamate[0][1] == "schedulatore"
    p = archivio.leggi(ident)
    assert p["stato"] == "mantenuta"
    assert p["esecuzione_id"] == "e1"


async def test_oltre_la_tolleranza_non_si_esegue_mai_e_il_motivo_misura(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Orologio(archivio, esegui=porta, interpreta=TurnoFinto()).batti(
        ADESSO + 10 + TOLLERANZA_S + 60)

    assert porta.chiamate == []          # la luce NON si accende in ritardo
    p = archivio.leggi(ident)
    assert p["stato"] == "saltata"
    assert "non eseguita" in p["motivo"]


async def test_dentro_la_tolleranza_si_esegue(archivio):
    """Il confine dall'altro lato: senza questo, «tolleranza» potrebbe essere zero."""
    _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    await Orologio(archivio, esegui=porta, interpreta=TurnoFinto()).batti(
        ADESSO + 10 + TOLLERANZA_S - 1)
    assert len(porta.chiamate) == 1


async def test_due_battiti_ravvicinati_non_la_mantengono_due_volte(archivio):
    _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta()
    orologio = Orologio(archivio, esegui=porta, interpreta=TurnoFinto())
    await orologio.batti(ADESSO + 11)
    await orologio.batti(ADESSO + 12)
    assert len(porta.chiamate) == 1


async def test_una_porta_che_fallisce_lascia_la_promessa_fallita_col_motivo(archivio):
    ident = _crea_fai(archivio, quando=ADESSO + 10)
    porta = PortaFinta({"eseguito": False, "errore": "quel servizio non esiste"})
    await Orologio(archivio, esegui=porta, interpreta=TurnoFinto()).batti(ADESSO + 11)

    p = archivio.leggi(ident)
    assert p["stato"] == "fallita"
    assert "non esiste" in p["motivo"]


async def test_una_porta_che_solleva_non_ferma_il_battito(archivio):
    """Un guasto su una promessa non deve impedire alle altre di essere mantenute."""
    rotta = _crea_fai(archivio, quando=ADESSO + 10)
    sana = _crea_fai(archivio, quando=ADESSO + 11)

    chiamate = []

    async def porta(chiamata, *, origine):
        chiamate.append(chiamata)
        if len(chiamate) == 1:
            raise RuntimeError("la rete e' caduta")
        return {"eseguito": True, "cambiato": [], "esecuzione_id": "e2"}

    await Orologio(archivio, esegui=porta, interpreta=TurnoFinto()).batti(ADESSO + 12)

    assert archivio.leggi(rotta)["stato"] == "fallita"
    assert archivio.leggi(sana)["stato"] == "mantenuta"


async def test_un_chiedi_con_recapito_notifica_e_registra_cio_che_ha_detto(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    porta = PortaFinta()
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})
    await Orologio(archivio, esegui=porta, interpreta=turno).batti(ADESSO + 11)

    assert len(porta.chiamate) == 1
    chiamata, origine = porta.chiamate[0]
    assert chiamata["servizio"] == "notify.mobile_app_x"
    assert "2 gradi" in chiamata["dati"]["message"]
    assert origine == "schedulatore"

    p = archivio.leggi(ident)
    assert (p["stato"], p["avvisare"], p["testo"]) == ("mantenuta", True, "e' salita di 2 gradi")


async def test_il_silenzio_non_notifica_ma_resta_scritto(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito="notify.mobile_app_x")
    porta = PortaFinta()
    turno = TurnoFinto({"avvisare": False, "testo": "non e' cambiata: 21,4 gradi come prima"})
    await Orologio(archivio, esegui=porta, interpreta=turno).batti(ADESSO + 11)

    assert porta.chiamate == []          # nessuno e' stato disturbato
    p = archivio.leggi(ident)
    assert p["stato"] == "mantenuta"     # il silenzio e' un esito RIUSCITO
    assert p["avvisare"] is False
    assert "21,4" in p["testo"]


async def test_avvisare_senza_recapito_non_inventa_un_canale_e_lo_dichiara(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10, recapito=None)
    porta = PortaFinta()
    await Orologio(archivio, esegui=porta,
                   interpreta=TurnoFinto({"avvisare": True, "testo": "fa caldo"})).batti(ADESSO + 11)

    assert porta.chiamate == []
    p = archivio.leggi(ident)
    assert p["stato"] == "mantenuta"
    assert "nessun modo" in p["motivo"]


async def test_un_turno_che_non_conclude_lascia_la_promessa_fallita(archivio):
    ident = _crea_chiedi(archivio, quando=ADESSO + 10)
    await Orologio(archivio, esegui=PortaFinta(),
                   interpreta=TurnoFinto({"errore": "il turno non ha concluso"})).batti(ADESSO + 11)

    p = archivio.leggi(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]
