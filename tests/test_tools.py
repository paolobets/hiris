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


from unittest.mock import patch
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
    assert len(result["hourly"]) == 2
    assert result["hourly"][0]["temperature"] == 22.1
    assert result["hourly"][0]["cloudcover"] == 10
