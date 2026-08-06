import asyncio
from unittest.mock import AsyncMock

import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.server import programma_ricostruzione_anagrafe

_VUOTI = {"piani": [], "aree": [], "dispositivi": [], "entita": [],
          "etichette": [], "categorie": [], "integrazioni": []}


@pytest.fixture
def archivio(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    yield a
    a.chiudi()


@pytest.mark.asyncio
async def test_una_raffica_di_eventi_ricostruisce_una_volta_sola(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=(_VUOTI, []))
    innesca = programma_ricostruzione_anagrafe(client, archivio, ritardo=0.05)
    for _ in range(10):
        innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert client.leggi_registri.await_count == 1


@pytest.mark.asyncio
async def test_due_raffiche_distanti_ricostruiscono_due_volte(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(return_value=_VUOTI)
    innesca = programma_ricostruzione_anagrafe(client, archivio, ritardo=0.05)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    innesca("floor_registry_updated")
    await asyncio.sleep(0.2)
    assert client.leggi_registri.await_count == 2


@pytest.mark.asyncio
async def test_una_ricostruzione_fallita_non_uccide_l_ascoltatore(archivio):
    client = AsyncMock()
    client.leggi_registri = AsyncMock(side_effect=[OSError("HA giu'"), (_VUOTI, [])])
    innesca = programma_ricostruzione_anagrafe(client, archivio, ritardo=0.05)
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    innesca("area_registry_updated")
    await asyncio.sleep(0.2)
    assert client.leggi_registri.await_count == 2


def test_si_ascoltano_tutti_i_registri():
    """Prima se ne ascoltava UNO su dieci, e solo alla creazione."""
    from hiris.app.proxy.ha_client import EVENTI_ANAGRAFE
    assert set(EVENTI_ANAGRAFE) == {
        "area_registry_updated",
        "device_registry_updated",
        "entity_registry_updated",
        "floor_registry_updated",
        "label_registry_updated",
        "category_registry_updated",
    }
