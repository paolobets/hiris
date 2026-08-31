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


def _make_ws_registry_mock(msg_type: str, result_data: list) -> tuple:
    """Build a minimal WS session mock that returns result_data for the given msg_type."""
    it = iter([
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {"id": 1, "type": "result", "success": True, "result": result_data},
    ])

    async def _receive_json():
        return next(it)

    ws = AsyncMock()
    ws.receive_json = _receive_json
    ws.send_json = AsyncMock()
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.ws_connect = MagicMock(return_value=ws)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session, ws
