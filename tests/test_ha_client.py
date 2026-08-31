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
        result = await client.get_states(["light.living"])
        await client.stop()

    assert result == [{"entity_id": "light.living", "state": "on", "attributes": {}}]


@pytest.mark.asyncio
async def test_get_states_filters_correctly(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=[
        {"entity_id": "light.living", "state": "on", "attributes": {}},
        {"entity_id": "light.kitchen", "state": "off", "attributes": {}},
        {"entity_id": "sensor.temp", "state": "22.5", "attributes": {}},
    ])
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        await client.start()
        result = await client.get_states(["light.living", "sensor.temp"])
        await client.stop()

    assert len(result) == 2
    entity_ids = [r["entity_id"] for r in result]
    assert "light.living" in entity_ids
    assert "sensor.temp" in entity_ids
    assert "light.kitchen" not in entity_ids
