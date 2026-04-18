import pytest
from unittest.mock import AsyncMock
from hiris.app.tools.ha_tools import get_entity_states
from hiris.app.tools.energy_tools import get_energy_history


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[
        {"entity_id": "light.living", "state": "on", "attributes": {"brightness": 200}}
    ])
    ha.get_history = AsyncMock(return_value=[
        {"entity_id": "sensor.power", "state": "1.5", "last_changed": "2026-04-17T10:00:00"}
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
    assert len(result) == 1
    assert result[0]["entity_id"] == "sensor.power"
    mock_ha.get_history.assert_awaited_once()
