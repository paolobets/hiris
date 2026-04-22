import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.tools.ha_tools import get_entity_states
from hiris.app.tools.energy_tools import get_energy_history


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[
        {"entity_id": "light.living", "state": "on", "attributes": {"brightness": 200}}
    ])
    ha.get_history = AsyncMock(return_value=[
        {"entity_id": "sensor.energy_consumption", "state": "1.5", "last_changed": "2026-04-17T10:00:00"},
        {"entity_id": "sensor.solar_production", "state": "2.0", "last_changed": "2026-04-17T10:00:00"},
        {"entity_id": "sensor.grid_import", "state": "0.5", "last_changed": "2026-04-17T10:00:00"},
        {"entity_id": "sensor.grid_export", "state": "0.0", "last_changed": "2026-04-17T10:00:00"},
    ])
    ha.call_service = AsyncMock(return_value=True)
    ha.get_automations = AsyncMock(return_value=[])
    return ha


@pytest.mark.asyncio
async def test_get_entity_states_returns_list(mock_ha):
    result = await get_entity_states(mock_ha, ["light.living"])
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "light.living"
    assert result[0]["state"] == "on"
    assert set(result[0].keys()) == {"id", "state", "name", "unit"}


@pytest.mark.asyncio
async def test_get_energy_history_returns_compressed_format(mock_ha, tmp_path):
    from hiris.app.proxy.semantic_map import SemanticMap
    smap = SemanticMap(data_dir=str(tmp_path))
    smap._add_entity("sensor.energy_consumption", "energy_meter", "Consumption", unit="kWh", classified_by="rules")
    smap._add_entity("sensor.solar_production", "solar_production", "Solar", unit="W", classified_by="rules")
    smap._add_entity("sensor.grid_import", "grid_import", "Grid Import", unit="kWh", classified_by="rules")
    smap._add_entity("sensor.grid_export", "grid_import", "Grid Export", unit="kWh", classified_by="rules")

    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert len(result) == 4
    ids = [r["id"] for r in result]
    assert "sensor.energy_consumption" in ids
    assert "sensor.solar_production" in ids
    rec = next(r for r in result if r["id"] == "sensor.energy_consumption")
    assert rec["day"] == "2026-04-17"
    assert rec["start"] == "1.5"
    assert rec["end"] == "1.5"
    assert rec["n"] == 1


@pytest.mark.asyncio
async def test_get_energy_history_uses_semantic_map(mock_ha, tmp_path):
    from hiris.app.proxy.semantic_map import SemanticMap
    smap = SemanticMap(data_dir=str(tmp_path))
    smap._add_entity("sensor.real_power", "energy_meter", "Real meter", unit="W", classified_by="rules")
    smap._add_entity("sensor.real_solar", "solar_production", "Solar", unit="W", classified_by="rules")

    from unittest.mock import AsyncMock
    mock_ha.get_history = AsyncMock(return_value=[
        {"entity_id": "sensor.real_power", "state": "250.0", "last_changed": "2026-04-22T10:00:00"},
    ])

    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "sensor.real_power"
    called_ids = mock_ha.get_history.call_args[1]["entity_ids"]
    assert "sensor.real_power" in called_ids
    assert "sensor.real_solar" in called_ids
    assert "sensor.energy_consumption" not in called_ids


@pytest.mark.asyncio
async def test_get_energy_history_returns_error_if_no_map_entities(mock_ha, tmp_path):
    from hiris.app.proxy.semantic_map import SemanticMap
    smap = SemanticMap(data_dir=str(tmp_path))  # empty map
    result = await get_energy_history(mock_ha, days=1, semantic_map=smap)
    assert isinstance(result, dict)
    assert "error" in result


from hiris.app.tools.weather_tools import get_weather_forecast


@pytest.mark.asyncio
async def test_get_weather_forecast_returns_compact_hourly():
    """hours <= 48 → compact hourly format, no lat/lon."""
    mock_resp_data = {
        "hourly": {
            "time": ["2026-04-18T12:00", "2026-04-18T13:00"],
            "temperature_2m": [22.1, 23.5],
            "cloudcover": [10, 20],
            "precipitation": [0.0, 0.1],
        }
    }

    async def fake_fetch(url: str) -> dict:
        return mock_resp_data

    result = await get_weather_forecast(hours=2, _fetch=fake_fetch)
    assert "latitude" not in result
    assert "longitude" not in result
    assert "hourly" in result
    assert len(result["hourly"]) == 2
    h0 = result["hourly"][0]
    assert h0["h"] == "2026-04-18T12"   # truncated to hour
    assert h0["t"] == 22.1
    assert h0["cc"] == 10
    assert h0["r"] == 0.0


from hiris.app.tools.notify_tools import send_notification
from hiris.app.tools.automation_tools import get_ha_automations, trigger_automation, toggle_automation


@pytest.mark.asyncio
async def test_send_notification_ha_push(mock_ha):
    config = {"ha_notify_service": "notify.mobile_app"}
    result = await send_notification(mock_ha, "Test message", "ha_push", config)
    assert result is True
    mock_ha.call_service.assert_awaited_with(
        "notify", "mobile_app", {"message": "Test message"}
    )


@pytest.mark.asyncio
async def test_get_ha_automations_returns_list(mock_ha):
    mock_ha.get_automations = AsyncMock(return_value=[
        {"entity_id": "automation.morning", "state": "on", "attributes": {"alias": "Morning routine"}}
    ])
    result = await get_ha_automations(mock_ha)
    assert len(result) == 1
    assert result[0]["entity_id"] == "automation.morning"


@pytest.mark.asyncio
async def test_trigger_automation(mock_ha):
    mock_ha.call_service = AsyncMock(return_value=True)
    result = await trigger_automation(mock_ha, "auto1")
    assert result is True
    mock_ha.call_service.assert_awaited_with(
        "automation", "trigger", {"entity_id": "automation.auto1"}
    )


@pytest.mark.asyncio
async def test_toggle_automation_enable(mock_ha):
    mock_ha.call_service = AsyncMock(return_value=True)
    result = await toggle_automation(mock_ha, "auto1", enabled=True)
    assert result is True
    mock_ha.call_service.assert_awaited_with(
        "automation", "turn_on", {"entity_id": "automation.auto1"}
    )


@pytest.mark.asyncio
async def test_send_notification_telegram(mock_ha):
    config = {"telegram_token": "test_token", "telegram_chat_id": "123456"}
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        result = await send_notification(mock_ha, "Hello Telegram", "telegram", config)

    assert result is True


@pytest.mark.asyncio
async def test_send_notification_telegram_missing_credentials(mock_ha):
    config = {}  # no token, no chat_id
    result = await send_notification(mock_ha, "Hello", "telegram", config)
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_retropanel(mock_ha):
    config = {"retropanel_url": "http://retropanel:8098"}
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        result = await send_notification(mock_ha, "Hello kiosk", "retropanel", config)

    assert result is True


@pytest.mark.asyncio
async def test_toggle_automation_disable(mock_ha):
    mock_ha.call_service = AsyncMock(return_value=True)
    result = await toggle_automation(mock_ha, "auto1", enabled=False)
    assert result is True
    mock_ha.call_service.assert_awaited_with(
        "automation", "turn_off", {"entity_id": "automation.auto1"}
    )


@pytest.mark.asyncio
async def test_trigger_automation_already_prefixed(mock_ha):
    mock_ha.call_service = AsyncMock(return_value=True)
    result = await trigger_automation(mock_ha, "automation.auto1")
    assert result is True
    mock_ha.call_service.assert_awaited_with(
        "automation", "trigger", {"entity_id": "automation.auto1"}
    )


from hiris.app.tools.ha_tools import get_area_entities


@pytest.mark.asyncio
async def test_get_entity_states_includes_friendly_name():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[{
        "entity_id": "light.cucina",
        "state": "on",
        "attributes": {"brightness": 200, "friendly_name": "Luce Cucina"},
        "last_changed": "2026-04-19T10:00:00",
    }])
    result = await get_entity_states(ha, ["light.cucina"])
    assert isinstance(result, list)
    assert result[0]["name"] == "Luce Cucina"
    assert result[0]["state"] == "on"


@pytest.mark.asyncio
async def test_get_entity_states_friendly_name_none_when_missing():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[{
        "entity_id": "sensor.temp",
        "state": "22.5",
        "attributes": {},
        "last_changed": "2026-04-19T10:00:00",
    }])
    result = await get_entity_states(ha, ["sensor.temp"])
    assert isinstance(result, list)
    assert result[0]["name"] == ""
    assert "state" in result[0]


@pytest.mark.asyncio
async def test_get_area_entities_uses_cache_when_populated():
    """When cache is populated, no HTTP calls should be made."""
    cache = MagicMock()
    cache.get_area_map.return_value = {"Cucina": ["light.cucina", "switch.presa"]}
    ha = AsyncMock()
    result = await get_area_entities(ha, entity_cache=cache)
    ha.get_area_registry.assert_not_called()
    ha.get_entity_registry.assert_not_called()
    assert result == {"Cucina": ["light.cucina", "switch.presa"]}


@pytest.mark.asyncio
async def test_get_area_entities_falls_back_to_http_when_cache_not_loaded():
    """When cache has not been loaded yet (returns None), HTTP calls should be made."""
    cache = MagicMock()
    cache.get_area_map.return_value = None  # None = not loaded yet
    ha = AsyncMock()
    ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina_id", "name": "Cucina"},
    ])
    ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.cucina", "area_id": "cucina_id"},
    ])
    result = await get_area_entities(ha, entity_cache=cache)
    ha.get_area_registry.assert_awaited_once()
    assert "Cucina" in result


@pytest.fixture
def mock_ha_with_areas():
    ha = AsyncMock()
    ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina", "name": "Cucina"},
        {"area_id": "soggiorno", "name": "Soggiorno"},
    ])
    ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.luce_cucina", "area_id": "cucina"},
        {"entity_id": "switch.presa_cucina", "area_id": "cucina"},
        {"entity_id": "light.luce_soggiorno", "area_id": "soggiorno"},
        {"entity_id": "sensor.no_area", "area_id": None},
    ])
    return ha


@pytest.mark.asyncio
async def test_get_area_entities_groups_by_area(mock_ha_with_areas):
    result = await get_area_entities(mock_ha_with_areas)
    assert "Cucina" in result
    assert "light.luce_cucina" in result["Cucina"]
    assert "switch.presa_cucina" in result["Cucina"]
    assert "Soggiorno" in result
    assert "light.luce_soggiorno" in result["Soggiorno"]


@pytest.mark.asyncio
async def test_get_area_entities_no_area_sentinel(mock_ha_with_areas):
    result = await get_area_entities(mock_ha_with_areas)
    assert "__no_area__" in result
    assert "sensor.no_area" in result["__no_area__"]


@pytest.mark.asyncio
async def test_get_area_entities_empty_when_registries_unavailable():
    ha = AsyncMock()
    ha.get_area_registry = AsyncMock(return_value=[])
    ha.get_entity_registry = AsyncMock(return_value=[])
    result = await get_area_entities(ha)
    assert "Cucina" not in result
    assert "Soggiorno" not in result


# ── New tests for Task 4 optimized tools ────────────────────────────────────

from hiris.app.tools.ha_tools import (
    get_home_status,
    get_entities_on,
    search_entities,
    get_entities_by_domain,
)


def test_get_home_status_delegates_to_cache():
    cache = MagicMock()
    cache.get_all_useful.return_value = [{"id": "light.test", "state": "on", "name": "Test", "unit": ""}]
    result = get_home_status(cache)
    cache.get_all_useful.assert_called_once()
    assert result == [{"id": "light.test", "state": "on", "name": "Test", "unit": ""}]


def test_get_entities_on_delegates_to_cache():
    cache = MagicMock()
    cache.get_on.return_value = [{"id": "switch.test", "state": "on", "name": "Switch", "unit": ""}]
    result = get_entities_on(cache)
    cache.get_on.assert_called_once()
    assert result == [{"id": "switch.test", "state": "on", "name": "Switch", "unit": ""}]


def test_search_entities_uses_embedding_index():
    cache = MagicMock()
    index = MagicMock()
    index.search.return_value = ["light.living_room"]
    cache.get_minimal.return_value = [{"id": "light.living_room", "state": "on", "name": "Living Room", "unit": ""}]
    result = search_entities("living room lights", cache, index, top_k=5)
    index.search.assert_called_once_with("living room lights", top_k=5, domain_filter=None)
    cache.get_minimal.assert_called_once_with(["light.living_room"])
    assert result == [{"id": "light.living_room", "state": "on", "name": "Living Room", "unit": ""}]


def test_get_entities_by_domain_delegates_to_cache():
    cache = MagicMock()
    cache.get_by_domain.return_value = [{"id": "light.test", "state": "on", "name": "Test", "unit": ""}]
    result = get_entities_by_domain("light", cache)
    cache.get_by_domain.assert_called_once_with("light")
    assert result == [{"id": "light.test", "state": "on", "name": "Test", "unit": ""}]


def test_search_entities_falls_back_when_index_not_ready():
    cache = MagicMock()
    index = MagicMock()
    index.ready = False
    cache.get_all_useful.return_value = [
        {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        {"id": "light.b", "state": "off", "name": "B", "unit": ""},
    ]
    result = search_entities("lights", cache, index, top_k=1)
    index.search.assert_not_called()
    assert result == [{"id": "light.a", "state": "on", "name": "A", "unit": ""}]


@pytest.mark.asyncio
async def test_get_entity_states_uses_cache_when_provided():
    ha = AsyncMock()
    ha.get_states = AsyncMock()
    cache = MagicMock()
    cache.get_minimal.return_value = [{"id": "light.x", "state": "on", "name": "X", "unit": ""}]
    result = await get_entity_states(ha, ["light.x"], entity_cache=cache)
    ha.get_states.assert_not_called()
    assert result == [{"id": "light.x", "state": "on", "name": "X", "unit": ""}]


from hiris.app.tools.energy_tools import _compress_energy_history


def test_compress_energy_history_groups_by_entity_and_day():
    raw = [
        {"entity_id": "sensor.e", "state": "100.0", "last_changed": "2026-04-17T08:00:00"},
        {"entity_id": "sensor.e", "state": "102.0", "last_changed": "2026-04-17T12:00:00"},
        {"entity_id": "sensor.e", "state": "105.0", "last_changed": "2026-04-17T20:00:00"},
        {"entity_id": "sensor.e", "state": "107.0", "last_changed": "2026-04-18T09:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 2
    day17 = next(r for r in result if r["day"] == "2026-04-17")
    assert day17["id"] == "sensor.e"
    assert day17["start"] == "100.0"
    assert day17["end"] == "105.0"
    assert day17["n"] == 3
    day18 = next(r for r in result if r["day"] == "2026-04-18")
    assert day18["start"] == "107.0"
    assert day18["n"] == 1


def test_compress_energy_history_handles_unavailable_state():
    raw = [
        {"entity_id": "sensor.e", "state": "unavailable", "last_changed": "2026-04-17T08:00:00"},
        {"entity_id": "sensor.e", "state": "unavailable", "last_changed": "2026-04-17T09:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 1
    assert result[0]["start"] == "unavailable"


def test_compress_energy_history_multiple_entities():
    raw = [
        {"entity_id": "sensor.a", "state": "10", "last_changed": "2026-04-17T10:00:00"},
        {"entity_id": "sensor.b", "state": "20", "last_changed": "2026-04-17T10:00:00"},
    ]
    result = _compress_energy_history(raw)
    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"sensor.a", "sensor.b"}


def test_compress_energy_history_empty_input():
    assert _compress_energy_history([]) == []


from hiris.app.tools.weather_tools import _compress_weather


def test_compress_weather_hourly_for_short_forecast():
    hourly = {
        "time": ["2026-04-18T10:00", "2026-04-18T11:00"],
        "temperature_2m": [20.0, 21.0],
        "cloudcover": [30, 40],
        "precipitation": [0.0, 0.5],
    }
    result = _compress_weather(hourly, hours=2)
    assert "hourly" in result
    assert "daily" not in result
    assert result["hourly"][0] == {"h": "2026-04-18T10", "t": 20.0, "cc": 30, "r": 0.0}
    assert result["hourly"][1] == {"h": "2026-04-18T11", "t": 21.0, "cc": 40, "r": 0.5}


def test_compress_weather_daily_for_long_forecast():
    times = (
        ["2026-04-18T00:00", "2026-04-18T06:00", "2026-04-18T12:00", "2026-04-18T18:00"] +
        ["2026-04-19T00:00", "2026-04-19T12:00"]
    )
    temps = [10.0, 15.0, 22.0, 18.0, 8.0, 20.0]
    clouds = [10, 20, 30, 40, 50, 60]
    rain   = [0.0, 0.0, 0.5, 0.2, 0.0, 1.0]
    hourly = {
        "time": times,
        "temperature_2m": temps,
        "cloudcover": clouds,
        "precipitation": rain,
    }
    result = _compress_weather(hourly, hours=72)
    assert "daily" in result
    assert "hourly" not in result
    days = {d["day"]: d for d in result["daily"]}
    assert "2026-04-18" in days
    d18 = days["2026-04-18"]
    assert d18["t_lo"] == 10.0
    assert d18["t_hi"] == 22.0
    assert abs(d18["r"] - 0.7) < 0.001
    assert "2026-04-19" in days


def test_compress_weather_handles_empty_hourly():
    result = _compress_weather({"time": [], "temperature_2m": [], "cloudcover": [], "precipitation": []}, hours=24)
    assert result == {"hourly": []}


def test_compress_weather_daily_empty_for_long():
    result = _compress_weather({"time": [], "temperature_2m": [], "cloudcover": [], "precipitation": []}, hours=72)
    assert result == {"daily": []}
