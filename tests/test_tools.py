import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.ha_tools import get_entity_states
from hiris.app.tools.energy_tools import get_energy_history, ENERGY_ENTITY_IDS


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
async def test_get_entity_states_returns_dict(mock_ha):
    result = await get_entity_states(mock_ha, ["light.living"])
    assert "light.living" in result
    assert result["light.living"]["state"] == "on"
    assert result["light.living"]["attributes"]["brightness"] == 200


@pytest.mark.asyncio
async def test_get_energy_history_returns_list(mock_ha):
    result = await get_energy_history(mock_ha, days=1)
    assert len(result) == 4
    entity_ids = [r["entity_id"] for r in result]
    assert "sensor.energy_consumption" in entity_ids
    assert "sensor.solar_production" in entity_ids
    mock_ha.get_history.assert_awaited_once_with(entity_ids=ENERGY_ENTITY_IDS, days=1)


from hiris.app.tools.weather_tools import get_weather_forecast


@pytest.mark.asyncio
async def test_get_weather_forecast_returns_forecast():
    mock_resp_data = {
        "hourly": {
            "time": ["2026-04-18T12:00", "2026-04-18T13:00"],
            "temperature_2m": [22.1, 23.5],
            "cloudcover": [10, 20],
            "precipitation": [0.0, 0.0],
        }
    }

    async def fake_fetch(url: str) -> dict:
        return mock_resp_data

    result = await get_weather_forecast(hours=2, _fetch=fake_fetch)
    assert result["latitude"] is not None
    assert result["longitude"] is not None
    assert len(result["hourly"]) == 2
    assert result["hourly"][0]["time"] == "2026-04-18T12:00"
    assert result["hourly"][0]["temperature"] == 22.1
    assert result["hourly"][0]["cloudcover"] == 10


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
