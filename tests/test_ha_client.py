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
    mock_resp.raise_for_status = MagicMock()
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
    mock_resp.raise_for_status = MagicMock()
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


@pytest.mark.asyncio
async def test_get_area_registry_returns_list(client):
    areas = [
        {"area_id": "cucina", "name": "Cucina", "floor_id": None},
        {"area_id": "soggiorno", "name": "Soggiorno", "floor_id": None},
    ]
    session, _ = _make_ws_registry_mock("config/area_registry/list", areas)
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_area_registry()
    assert len(result) == 2
    assert result[0]["area_id"] == "cucina"


@pytest.mark.asyncio
async def test_get_area_registry_returns_empty_on_error(client):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.ws_connect = MagicMock(side_effect=OSError("refused"))
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_area_registry()
    assert result == []


@pytest.mark.asyncio
async def test_get_entity_registry_returns_list(client):
    entities = [
        {"entity_id": "light.luce_cucina", "area_id": "cucina", "name": "Luce cucina"},
        {"entity_id": "sensor.temp", "area_id": None, "name": "Temperatura"},
    ]
    session, _ = _make_ws_registry_mock("config/entity_registry/list", entities)
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_entity_registry()
    assert len(result) == 2
    assert result[0]["entity_id"] == "light.luce_cucina"
    assert result[0]["area_id"] == "cucina"


@pytest.mark.asyncio
async def test_get_entity_registry_returns_empty_on_error(client):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.ws_connect = MagicMock(side_effect=OSError("refused"))
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_entity_registry()
    assert result == []


def test_add_registry_listener():
    ha = HAClient("http://supervisor/core", "token")
    callback = MagicMock()
    ha.add_registry_listener(callback)
    assert callback in ha._registry_listeners


@pytest.mark.asyncio
async def test_get_error_log_parses_counts(client):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = AsyncMock(return_value=(
        "2026-01-01 ERROR (MainThread) [homeassistant] Something broke\n"
        "2026-01-01 WARNING (MainThread) [sensor] Minor issue\n"
        "2026-01-01 WARNING (MainThread) [sensor] Another\n"
    ))
    client._session = MagicMock()
    client._session.get = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_resp),
        __aexit__=AsyncMock(return_value=False),
    ))
    result = await client.get_error_log(limit=50)
    assert result["errors"] == 1
    assert result["warnings"] == 2
    assert len(result["top_errors"]) == 1


@pytest.mark.asyncio
async def test_get_system_info_extracts_version(client):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value={
        "version": "2025.1.0",
        "config_dir": "/config",
        "state": "RUNNING",
    })
    client._session = MagicMock()
    client._session.get = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_resp),
        __aexit__=AsyncMock(return_value=False),
    ))
    result = await client.get_system_info()
    assert result["ha_version"] == "2025.1.0"
    assert "state" in result


@pytest.mark.asyncio
async def test_get_updates_returns_update_entities(client):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=[
        {
            "entity_id": "update.home_assistant_core_update",
            "state": "on",
            "attributes": {
                "friendly_name": "Home Assistant Core Update",
                "installed_version": "2024.12.1",
                "latest_version": "2025.1.0",
            },
        },
        {
            "entity_id": "sensor.temperature",
            "state": "21.5",
            "attributes": {},
        },
    ])
    client._session = MagicMock()
    client._session.get = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_resp),
        __aexit__=AsyncMock(return_value=False),
    ))
    result = await client.get_updates()
    assert len(result) == 1
    assert result[0]["name"] == "Home Assistant Core Update"
    assert result[0]["current"] == "2024.12.1"
    assert result[0]["available"] == "2025.1.0"


@pytest.mark.asyncio
async def test_get_config_entries_filters_loaded(client):
    """Entries with state 'loaded' should be excluded; error states should be returned."""
    entries = [
        {
            "domain": "hue",
            "title": "Philips Hue",
            "state": "loaded",
            "reason": "",
        },
        {
            "domain": "zwave_js",
            "title": "Z-Wave JS",
            "state": "setup_error",
            "reason": "Connection refused",
        },
        {
            "domain": "mqtt",
            "title": "MQTT",
            "state": "not_loaded",
            "reason": "",
        },
    ]
    session, _ = _make_ws_registry_mock("config/config_entries/get_entries", entries)
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_config_entries()

    # "loaded" and "not_loaded" are both filtered out; only "setup_error" survives
    assert len(result) == 1
    assert result[0]["integration"] == "zwave_js"
    assert result[0]["title"] == "Z-Wave JS"
    assert result[0]["state"] == "setup_error"
    assert result[0]["error"] == "Connection refused"


@pytest.mark.asyncio
async def test_get_config_entries_returns_empty_on_ws_error(client):
    """When the WebSocket call fails, get_config_entries() should return []."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.ws_connect = MagicMock(side_effect=OSError("refused"))
    with patch("hiris.app.proxy.ha_client.aiohttp.ClientSession", return_value=session):
        result = await client.get_config_entries()
    assert result == []
