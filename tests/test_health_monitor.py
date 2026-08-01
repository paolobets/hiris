import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.health_monitor import (
    HealthMonitor,
    MAX_ADDONS,
    MAX_UNAVAILABLE_ENTITIES,
)


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_error_log = AsyncMock(return_value={"errors": 0, "warnings": 1, "top_errors": []})
    ha.get_config_entries = AsyncMock(return_value=[])
    ha.get_system_info = AsyncMock(return_value={"ha_version": "2025.1.0", "state": "RUNNING"})
    ha.get_updates = AsyncMock(return_value=[])
    ha.get_system_health = AsyncMock(return_value={"recorder": {"oldest_recorder_run": "2026-01-01"}})
    ha.add_state_listener = MagicMock()
    return ha


@pytest.fixture
def mock_supervisor():
    sup = AsyncMock()
    sup.get_addons = AsyncMock(return_value=[
        {"slug": "core_ssh", "name": "SSH", "state": "started",
         "version": "1.0", "update_available": False},
    ])
    sup.get_host_info = AsyncMock(return_value={
        "disk_total": 100, "disk_used": 40, "disk_free": 60,
    })
    sup.get_available_updates = AsyncMock(return_value=[
        {"name": "Home Assistant Core", "update_type": "core", "version_latest": "2026.8.0"},
    ])
    return sup


@pytest.fixture
def monitor(mock_ha, tmp_path):
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
    )
    return m


@pytest.fixture
def monitor_sup(mock_ha, mock_supervisor, tmp_path):
    return HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
        supervisor_client=mock_supervisor,
    )


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


@pytest.mark.asyncio
async def test_start_registers_listener_and_schedules_job(mock_ha, tmp_path):
    sched = MagicMock()
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=sched,
    )
    await m.start()
    mock_ha.add_state_listener.assert_called_once_with(m.on_state_changed)
    sched.add_job.assert_called_once()
    call_kwargs = sched.add_job.call_args
    assert call_kwargs[1]["minutes"] == 30
    assert call_kwargs[1]["id"] == "health_monitor_poll"


# --- Sezioni nuove: system_health e supervisor -------------------------------


@pytest.mark.asyncio
async def test_refresh_popola_system_health_e_supervisor(monitor_sup):
    await monitor_sup.refresh()
    snap = monitor_sup.get_snapshot(["all"])
    assert snap["system_health"]["recorder"]["oldest_recorder_run"] == "2026-01-01"
    assert snap["supervisor"]["addons"][0]["slug"] == "core_ssh"
    assert snap["supervisor"]["disk"]["disk_free"] == 60
    assert snap["supervisor"]["updates"][0]["update_type"] == "core"


@pytest.mark.asyncio
async def test_get_snapshot_filtra_sezione_supervisor(monitor_sup):
    await monitor_sup.refresh()
    snap = monitor_sup.get_snapshot(["supervisor"])
    assert "supervisor" in snap
    assert "last_updated" in snap
    assert "system_health" not in snap
    assert "system" not in snap
    assert "unavailable" not in snap


@pytest.mark.asyncio
async def test_fallimento_supervisor_non_azzera_le_altre_sezioni(
    mock_ha, mock_supervisor, tmp_path
):
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
        supervisor_client=mock_supervisor,
    )
    await m.refresh()
    # Il Supervisor smette di rispondere: la sua sezione mantiene il valore
    # precedente e le altre restano popolate.
    mock_supervisor.get_addons = AsyncMock(side_effect=RuntimeError("boom"))
    await m.refresh()
    snap = m.get_snapshot(["all"])
    assert snap["system"]["ha_version"] == "2025.1.0"
    assert snap["system_health"]["recorder"]["oldest_recorder_run"] == "2026-01-01"
    assert snap["supervisor"]["addons"][0]["slug"] == "core_ssh"


@pytest.mark.asyncio
async def test_fallimento_system_health_non_azzera_le_altre_sezioni(
    mock_ha, mock_supervisor, tmp_path
):
    mock_ha.get_system_health = AsyncMock(side_effect=RuntimeError("boom"))
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
        supervisor_client=mock_supervisor,
    )
    await m.refresh()
    snap = m.get_snapshot(["all"])
    assert snap["system"]["ha_version"] == "2025.1.0"
    assert snap["supervisor"]["disk"]["disk_free"] == 60
    assert "system_health" not in snap


@pytest.mark.asyncio
async def test_senza_supervisor_client_nessuna_eccezione(monitor):
    """Installazione standalone: nessun Supervisor, sezione assente."""
    await monitor.refresh()
    snap = monitor.get_snapshot(["all"])
    assert "supervisor" not in snap
    assert snap["system"]["ha_version"] == "2025.1.0"
    assert monitor.get_snapshot(["supervisor"]) == {
        "last_updated": snap["last_updated"]
    }


# --- Cap per sezione ---------------------------------------------------------


def _entita(n):
    return [
        {"entity_id": f"sensor.s{i}", "domain": "sensor", "since": "2026-01-01T00:00:00Z"}
        for i in range(n)
    ]


def test_unavailable_troncata_e_totale_dichiarato(monitor):
    monitor._snapshot_data["unavailable_entities"] = _entita(50)
    snap = monitor.get_snapshot(["unavailable"])
    assert len(snap["unavailable"]) == MAX_UNAVAILABLE_ENTITIES
    assert snap["truncated"]["unavailable"] == {
        "shown": MAX_UNAVAILABLE_ENTITIES,
        "total": 50,
    }


def test_nessun_troncamento_nessuna_dichiarazione(monitor):
    monitor._snapshot_data["unavailable_entities"] = _entita(3)
    snap = monitor.get_snapshot(["unavailable"])
    assert len(snap["unavailable"]) == 3
    assert "truncated" not in snap


def test_addons_troncati_e_totale_dichiarato(monitor_sup):
    monitor_sup._snapshot_data["supervisor"] = {
        "addons": [{"slug": f"a{i}", "state": "started"} for i in range(MAX_ADDONS + 7)],
        "disk": {"disk_free": 60},
        "updates": [],
    }
    snap = monitor_sup.get_snapshot(["supervisor"])
    assert len(snap["supervisor"]["addons"]) == MAX_ADDONS
    assert snap["truncated"]["supervisor.addons"] == {
        "shown": MAX_ADDONS,
        "total": MAX_ADDONS + 7,
    }
    # Il dato interno non viene mutato dal troncamento in lettura.
    assert len(monitor_sup._snapshot_data["supervisor"]["addons"]) == MAX_ADDONS + 7


def test_dashboard_ottiene_lo_snapshot_completo(monitor):
    """Il cap protegge il prompt dell'LLM, non la dashboard di configurazione."""
    monitor._snapshot_data["unavailable_entities"] = _entita(50)
    snap = monitor.get_snapshot(["unavailable"], capped=False)
    assert len(snap["unavailable"]) == 50
    assert "truncated" not in snap


def test_file_su_disco_resta_completo(monitor, tmp_path):
    monitor._snapshot_data["unavailable_entities"] = _entita(50)
    monitor._save_sync()
    with open(str(tmp_path / "ha_health.json"), encoding="utf-8") as f:
        salvato = json.load(f)
    assert len(salvato["unavailable_entities"]) == 50
