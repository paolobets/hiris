import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.health_monitor import HealthMonitor


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_error_log = AsyncMock(return_value={"errors": 0, "warnings": 1, "top_errors": []})
    ha.get_config_entries = AsyncMock(return_value=[])
    ha.get_system_info = AsyncMock(return_value={"ha_version": "2025.1.0", "state": "RUNNING"})
    ha.get_updates = AsyncMock(return_value=[])
    ha.add_state_listener = MagicMock()
    return ha


@pytest.fixture
def monitor(mock_ha, tmp_path):
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
    )
    return m


@pytest.mark.asyncio
async def test_refresh_populates_snapshot(monitor, mock_ha):
    await monitor.refresh()
    snap = monitor.get_snapshot(["system"])
    assert snap["system"]["ha_version"] == "2025.1.0"


@pytest.mark.asyncio
async def test_get_snapshot_filters_sections(monitor, mock_ha):
    await monitor.refresh()
    snap = monitor.get_snapshot(["system", "logs"])
    assert "system" in snap
    assert "logs" in snap
    assert "unavailable" not in snap
    assert "updates" not in snap


def test_on_state_changed_tracks_unavailable(monitor):
    monitor._snapshot_data["unavailable_entities"] = []
    monitor.on_state_changed({
        "entity_id": "sensor.temp",
        "new_state": {"state": "unavailable", "entity_id": "sensor.temp"},
    })
    unavailable = monitor._snapshot_data["unavailable_entities"]
    assert any(e["entity_id"] == "sensor.temp" for e in unavailable)


def test_on_state_changed_removes_recovered_entity(monitor):
    monitor._snapshot_data["unavailable_entities"] = [
        {"entity_id": "sensor.temp", "domain": "sensor", "since": "2026-01-01T00:00:00Z"}
    ]
    monitor.on_state_changed({
        "entity_id": "sensor.temp",
        "new_state": {"state": "21.5", "entity_id": "sensor.temp"},
    })
    unavailable = monitor._snapshot_data["unavailable_entities"]
    assert not any(e["entity_id"] == "sensor.temp" for e in unavailable)


@pytest.mark.asyncio
async def test_snapshot_persisted_and_loaded(monitor, mock_ha, tmp_path):
    await monitor.refresh()
    # Crea un nuovo monitor sullo stesso path — deve caricare dal file
    monitor2 = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
    )
    snap = monitor2.get_snapshot(["system"])
    assert snap["system"]["ha_version"] == "2025.1.0"
