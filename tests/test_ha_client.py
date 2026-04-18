import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.ha_client import HAClient


@pytest.fixture
def client():
    return HAClient(base_url="http://supervisor/core", token="test-token")


@pytest.mark.asyncio
async def test_get_states_returns_list(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=[{"entity_id": "light.living", "state": "on", "attributes": {}}])
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        await client.start()
        result = await client.get_states(["light.living"])
        await client.stop()

    assert result == [{"entity_id": "light.living", "state": "on", "attributes": {}}]


@pytest.mark.asyncio
async def test_get_history_returns_list(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=[[{"entity_id": "sensor.power", "state": "1.2", "last_changed": "2026-04-17T10:00:00"}]])
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        await client.start()
        result = await client.get_history(entity_ids=["sensor.power"], days=1)
        await client.stop()

    assert len(result) == 1
    assert result[0]["entity_id"] == "sensor.power"


@pytest.mark.asyncio
async def test_call_service_returns_true(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        await client.start()
        result = await client.call_service("light", "turn_on", {"entity_id": "light.living"})
        await client.stop()

    assert result is True


@pytest.mark.asyncio
async def test_get_states_filters_correctly(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
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


@pytest.mark.asyncio
async def test_call_service_returns_false_on_error(client):
    mock_resp = AsyncMock()
    mock_resp.status = 400
    mock_resp.text = AsyncMock(return_value="Bad request")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        await client.start()
        result = await client.call_service("light", "turn_on", {"entity_id": "light.bad"})
        await client.stop()

    assert result is False
