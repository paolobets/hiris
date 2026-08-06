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
    finto = AsyncMock(return_value=[_msg([{"a": 1}]) for _ in range(7)])
    with patch.object(HAClient, "_ws_batch", finto):
        registri = await client.leggi_registri()
    (comandi,), _ = finto.call_args
    tipi = [t for t, _ in comandi]
    assert tipi == [
        "config/floor_registry/list",
        "config/area_registry/list",
        "config/device_registry/list",
        "config/entity_registry/list",
        "config/label_registry/list",
        "config/category_registry/list",
        "config/config_entries/get_entries",
    ]
    assert set(registri) == {"piani", "aree", "dispositivi", "entita",
                             "etichette", "categorie", "integrazioni"}


@pytest.mark.asyncio
async def test_un_registro_mancante_diventa_lista_vuota_non_un_guasto():
    """Un HA senza piani risponde comunque: il resto dell'anagrafe deve reggere."""
    risposte = [None] + [_msg([{"a": 1}]) for _ in range(6)]
    with patch.object(HAClient, "_ws_batch", AsyncMock(return_value=risposte)):
        registri = await _client().leggi_registri()
    assert registri["piani"] == []
    assert registri["aree"] == [{"a": 1}]


@pytest.mark.asyncio
async def test_get_config_entries_restituisce_tutto_non_solo_gli_errori():
    voci = [
        {"domain": "hue", "title": "Hue", "state": "loaded"},
        {"domain": "rotto", "title": "Rotto", "state": "setup_error", "reason": "boom"},
    ]
    with patch.object(HAClient, "_ws_call", AsyncMock(return_value=voci)):
        assert await _client().get_config_entries() == voci


@pytest.mark.asyncio
async def test_il_monitor_di_salute_filtra_da_se_gli_errori():
    """Il filtro e' passato dal client al consumatore: l'esito non cambia."""
    from hiris.app.proxy.health_monitor import errori_di_integrazione
    voci = [
        {"domain": "hue", "title": "Hue", "state": "loaded"},
        {"domain": "rotto", "title": "Rotto", "state": "setup_error", "reason": "boom"},
        {"domain": "attesa", "title": "Attesa", "state": "setup_in_progress"},
    ]
    assert errori_di_integrazione(voci) == [
        {"integration": "rotto", "title": "Rotto", "state": "setup_error", "error": "boom"}
    ]
