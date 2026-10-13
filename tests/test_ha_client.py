from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.proxy.ha_client import HAClient


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


@pytest.mark.asyncio
async def test_get_states_returns_list(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(
        return_value=[{"entity_id": "light.living", "state": "on", "attributes": {}}]
    )
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        await client.start()
        result = await client.get_states()
        await client.stop()

    assert result == [{"entity_id": "light.living", "state": "on", "attributes": {}}]


def test_get_states_legge_tutti_gli_stati_senza_filtro():
    """M-55 (F1 della Chiusura, 13/10/2026): il filtro per `entity_ids` non
    aveva chiamanti in produzione ed e' uscito; chi vuole uno stato per id lo
    chiede allo specchio. Mutazione ESEGUITA e ripristinata: il parametro
    rimesso -- rossa."""
    import inspect
    assert list(inspect.signature(HAClient.get_states).parameters) == ["self"]
