from unittest.mock import AsyncMock

import pytest

from hiris.app.casa.anagrafe import gerarchia, ricostruisci
from hiris.app.casa.archivio import ArchivioCasa

_REGISTRI = {
    "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
    "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"},
             {"area_id": "solaio", "name": "Solaio", "floor_id": None}],
    "dispositivi": [{"id": "d1", "name": "Frigo", "area_id": "cucina"}],
    "entita": [
        # senza area propria: la eredita dal dispositivo
        {"entity_id": "sensor.frigo_temp", "device_id": "d1", "area_id": None},
        # con area propria: la sua vince su quella del dispositivo
        {"entity_id": "light.faretto", "device_id": "d1", "area_id": "solaio"},
        # senza area e senza dispositivo: senza casa
        {"entity_id": "sensor.orfana", "device_id": None, "area_id": None},
        # disabilitata: non entra nella gerarchia
        {"entity_id": "sensor.spenta", "device_id": "d1", "area_id": None,
         "disabled_by": "user"},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


@pytest.mark.asyncio
async def test_ricostruisci_riempie_l_archivio_e_riepiloga(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(_REGISTRI, []))
    esito = await ricostruisci(client, archivio)
    assert esito["conteggi"]["aree"] == 2
    assert esito["conteggi"]["entita"] == 4
    assert esito["non_disponibili"] == []
    assert archivio.aggiornata_il() is not None


@pytest.mark.asyncio
async def test_ricostruisci_riporta_i_registri_caduti(archivio):
    """Un registro caduto non ferma l'anagrafe, ma non deve sparire: la casa
    senza piani e il registro dei piani caduto danno la stessa lista vuota."""
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(dict(_REGISTRI, piani=[]), ["piani"]))
    esito = await ricostruisci(client, archivio)
    assert esito["non_disponibili"] == ["piani"]
    assert esito["conteggi"]["aree"] == 2   # il resto e' passato lo stesso


def test_l_entita_eredita_l_area_dal_proprio_dispositivo(archivio):
    archivio.sostituisci(_REGISTRI)
    aree = {a["nome"]: a for a in gerarchia(archivio.leggi())[0]["aree"]}
    assert "sensor.frigo_temp" in [e["id"] for e in aree["Cucina"]["entita"]]


def test_l_area_dell_entita_vince_su_quella_del_dispositivo(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    solaio = [a for p in piani for a in p["aree"] if a["nome"] == "Solaio"][0]
    assert [e["id"] for e in solaio["entita"]] == ["light.faretto"]


def test_le_aree_senza_piano_stanno_in_un_piano_senza_nome(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    senza = [p for p in piani if p["id"] is None][0]
    assert [a["nome"] for a in senza["aree"]] == ["Solaio"]


def test_le_entita_disabilitate_non_entrano_nella_gerarchia(archivio):
    archivio.sostituisci(_REGISTRI)
    tutte = [e["id"] for p in gerarchia(archivio.leggi())
             for a in p["aree"] for e in a["entita"]]
    assert "sensor.spenta" not in tutte


def test_le_entita_senza_casa_sono_raccolte_a_parte(archivio):
    archivio.sostituisci(_REGISTRI)
    piani = gerarchia(archivio.leggi())
    fuori = [a for p in piani for a in p["aree"] if a["id"] is None]
    assert [e["id"] for a in fuori for e in a["entita"]] == ["sensor.orfana"]
