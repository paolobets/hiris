import pytest
from unittest.mock import MagicMock
from hiris.app.tools.health_tools import get_ha_health, GET_HA_HEALTH_TOOL_DEF


@pytest.fixture
def mock_monitor():
    m = MagicMock()
    m.get_snapshot = MagicMock(return_value={
        "system": {"ha_version": "2025.1.0"},
        "logs": {"errors": 0, "warnings": 1, "top_errors": []},
        "last_updated": "2026-04-30T08:00:00Z",
    })
    return m


def test_tool_def_has_required_fields():
    assert GET_HA_HEALTH_TOOL_DEF["name"] == "get_ha_health"
    assert "sections" in GET_HA_HEALTH_TOOL_DEF["input_schema"]["properties"]


def test_get_ha_health_passes_sections_to_monitor(mock_monitor):
    result = get_ha_health(mock_monitor, sections=["system", "logs"])
    mock_monitor.get_snapshot.assert_called_once_with(["system", "logs"])
    assert result["system"]["ha_version"] == "2025.1.0"


def test_get_ha_health_defaults_to_all(mock_monitor):
    result = get_ha_health(mock_monitor, sections=None)
    mock_monitor.get_snapshot.assert_called_once_with(["all"])


def test_get_ha_health_no_monitor_returns_error():
    result = get_ha_health(None, sections=["all"])
    assert "error" in result
