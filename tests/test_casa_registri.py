from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.proxy.ha_client import HAClient


def _client():
    return HAClient(base_url="http://ha.test", token="t")


def _msg(risultato):
    return {"id": 1, "type": "result", "success": True, "result": risultato}


@pytest.mark.asyncio
async def test_leggi_registri_chiede_tutti_i_registri_in_un_colpo():
    client = _client()
    finto = AsyncMock(return_value=[_msg([{"a": 1}]) for _ in range(10)])
    with patch.object(HAClient, "_ws_batch", finto):
        registri, _ = await client.leggi_registri()
    (comandi,), _ = finto.call_args
    tipi = [t for t, _ in comandi]
    assert tipi == [
        "config/floor_registry/list",
        "config/area_registry/list",
        "config/device_registry/list",
        "config/entity_registry/list",
        "config/label_registry/list",
        "config/config_entries/get_entries",
        "config/category_registry/list",
        "config/category_registry/list",
        "config/category_registry/list",
        "config/category_registry/list",
    ]
    assert set(registri) == {"piani", "aree", "dispositivi", "entita",
                             "etichette", "categorie", "integrazioni"}


@pytest.mark.asyncio
async def test_un_registro_mancante_diventa_lista_vuota_non_un_guasto():
    """Un HA senza piani risponde comunque: il resto dell'anagrafe deve reggere."""
    risposte = [None] + [_msg([{"a": 1}]) for _ in range(9)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, _ = await _client().leggi_registri()
    assert registri["piani"] == []
    assert registri["aree"] == [{"a": 1}]


@pytest.mark.asyncio
async def test_un_registro_caduto_si_distingue_da_uno_vuoto():
    """La casa senza piani e il registro dei piani caduto danno la stessa lista
    vuota: solo `non_disponibili` dice quale dei due e' successo."""
    risposte = [None] + [_msg([]) for _ in range(9)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, non_disponibili = await _client().leggi_registri()
    assert registri["piani"] == []
    assert "piani" in non_disponibili
    assert "aree" not in non_disponibili


@pytest.mark.asyncio
async def test_una_casa_sana_non_ha_registri_non_disponibili():
    with patch.object(HAClient, "_ws_batch",
                      AsyncMock(return_value=[_msg([{"a": 1}]) for _ in range(10)])):
        _, non_disponibili = await _client().leggi_registri()
    assert non_disponibili == []


@pytest.mark.asyncio
async def test_le_categorie_si_chiedono_per_tutti_gli_ambiti():
    finto = AsyncMock(return_value=[_msg([]) for _ in range(10)])
    with patch.object(HAClient, "_ws_batch", finto):
        await _client().leggi_registri()
    (comandi,), _ = finto.call_args
    ambiti = [extra["scope"] for tipo, extra in comandi
              if tipo == "config/category_registry/list"]
    assert ambiti == ["automation", "script", "scene", "helpers"]


@pytest.mark.asyncio
async def test_ogni_categoria_porta_il_proprio_ambito():
    risposte = [_msg([]) for _ in range(6)]                       # i sei registri non-categoria
    risposte += [_msg([{"category_id": f"c{i}", "name": f"C{i}"}]) for i in range(4)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri, _ = await _client().leggi_registri()
    assert [c["ambito"] for c in registri["categorie"]] == [
        "automation", "script", "scene", "helpers"]


@pytest.mark.asyncio
async def test_un_ambito_di_categorie_caduto_si_dice_quale():
    risposte = [_msg([]) for _ in range(6)]
    risposte += [_msg([]), None, _msg([]), _msg([])]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        _, non_disponibili = await _client().leggi_registri()
    assert non_disponibili == ["categorie:script"]


# fetta E3 Task 11: test_il_monitor_di_salute_filtra_da_se_gli_errori e'
# cancellato -- importava `errori_di_integrazione` da
# `hiris.app.proxy.health_monitor`, cancellato per intero insieme
# all'HealthMonitor (il suo unico lettore rimasto). Verificato che cade per
# costruzione: `ModuleNotFoundError: No module named
# 'hiris.app.proxy.health_monitor'`, prima della cancellazione. Nessun
# successore: quel filtro non ha piu' alcun consumatore.
#
# fetta E3 Task 12: test_get_config_entries_restituisce_tutto_non_solo_gli_
# errori e' cancellato -- testava `HAClient.get_config_entries()` in
# isolamento, un metodo diverso da `leggi_registri()` sopra (che chiede
# "config/config_entries/get_entries" direttamente nel proprio batch WS, non
# passando da `get_config_entries`). `get_config_entries` era gia' ORFANO
# DICHIARATO dal Task 11 (l'HealthMonitor che lo leggeva e' uscito):
# verificato che cade per costruzione (`AttributeError: 'HAClient' object
# has no attribute 'get_config_entries'`), poi cancellato insieme al metodo.
