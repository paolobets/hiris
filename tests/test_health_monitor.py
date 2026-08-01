import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.proxy.health_monitor import (
    HealthMonitor,
    MAX_ADDONS,
    MAX_INTEGRATION_ERRORS,
    MAX_SUPERVISOR_UPDATES,
    MAX_SYSTEM_HEALTH_DOMAINS,
    MAX_TOP_ERRORS,
    MAX_UNAVAILABLE_ENTITIES,
    MAX_UPDATES,
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


@pytest.mark.asyncio
async def test_supervisor_che_risponde_vuoto_non_produce_la_sezione(mock_ha, tmp_path):
    """Caso REALE su installazione standalone: il client c'e' (server.py lo
    costruisce), ma il Supervisor non risponde. SupervisorClient non solleva
    mai: degrada a [], {}, []. Il dict a tre chiavi vuote e' truthy e farebbe
    comparire `supervisor: {addons: []}`, da cui l'LLM concluderebbe "non hai
    add-on installati" -- falso. La sezione non deve comparire affatto."""
    sup_vuoto = AsyncMock()
    sup_vuoto.get_addons = AsyncMock(return_value=[])
    sup_vuoto.get_host_info = AsyncMock(return_value={})
    sup_vuoto.get_available_updates = AsyncMock(return_value=[])
    m = HealthMonitor(
        ha_client=mock_ha,
        data_path=str(tmp_path / "ha_health.json"),
        scheduler=MagicMock(),
        supervisor_client=sup_vuoto,
    )
    await m.refresh()
    snap = m.get_snapshot(["all"])
    assert "supervisor" not in snap
    # Le altre sezioni restano popolate.
    assert snap["system"]["ha_version"] == "2025.1.0"
    assert m.get_snapshot(["supervisor"]) == {"last_updated": snap["last_updated"]}


def test_supervisor_vuoto_su_disco_non_produce_la_sezione(monitor):
    """Difensiva: un file scritto da una versione precedente puo' contenere
    la sezione a tre chiavi vuote. In lettura si comporta come assente,
    coerentemente con system_health (che e' gia' {} falsy)."""
    monitor._snapshot_data["supervisor"] = {"addons": [], "disk": {}, "updates": []}
    monitor._snapshot_data["system_health"] = {}
    snap = monitor.get_snapshot(["all"])
    assert "supervisor" not in snap
    assert "system_health" not in snap


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
    assert snap["truncated"]["unavailable"]["shown"] == MAX_UNAVAILABLE_ENTITIES
    assert snap["truncated"]["unavailable"]["total"] == 50
    # L'ordine va dichiarato: altrimenti l'LLM non sa QUALI 25 delle 50 vede.
    assert snap["truncated"]["unavailable"]["order"] == "most_recent_first"


def test_unavailable_mostra_le_cadute_piu_recenti(monitor):
    """La lista e' mantenuta solo in append e sopravvive ai riavvii: e'
    ordinata dalla caduta piu' vecchia. Tagliare le prime N mostrerebbe i
    dispositivi morti da mesi e nasconderebbe per sempre una rottura appena
    avvenuta -- esattamente lo scenario che il cap deve servire."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    vecchie = [
        {
            "entity_id": f"sensor.vecchia{i}",
            "domain": "sensor",
            "since": (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for i in range(MAX_UNAVAILABLE_ENTITIES + 10)
    ]
    appena_rotta = {
        "entity_id": "sensor.appena_rotta",
        "domain": "sensor",
        "since": (base + timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # Ordine di arrivo: prima le vecchie, in coda quella appena caduta.
    monitor._snapshot_data["unavailable_entities"] = vecchie + [appena_rotta]

    snap = monitor.get_snapshot(["unavailable"])
    mostrate = [e["entity_id"] for e in snap["unavailable"]]
    assert len(mostrate) == MAX_UNAVAILABLE_ENTITIES
    assert "sensor.appena_rotta" == mostrate[0]
    # Le piu' vecchie sono quelle escluse, non quelle mostrate.
    assert "sensor.vecchia0" not in mostrate
    attese = [e["entity_id"] for e in
              ([appena_rotta] + list(reversed(vecchie)))[:MAX_UNAVAILABLE_ENTITIES]]
    assert mostrate == attese
    # Nessuna mutazione del dato interno: resta l'ordine di arrivo, completo.
    interno = monitor._snapshot_data["unavailable_entities"]
    assert len(interno) == MAX_UNAVAILABLE_ENTITIES + 11
    assert interno[0]["entity_id"] == "sensor.vecchia0"


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
    # Il dato interno non viene mutato dal troncamento in lettura: verificato
    # dall'esterno, con una lettura non cappata che li deve vedere ancora tutti.
    completo = monitor_sup.get_snapshot(["supervisor"], capped=False)
    assert len(completo["supervisor"]["addons"]) == MAX_ADDONS + 7


def test_dashboard_ottiene_lo_snapshot_completo(monitor):
    """Il cap protegge il prompt dell'LLM, non la dashboard di configurazione."""
    monitor._snapshot_data["unavailable_entities"] = _entita(50)
    snap = monitor.get_snapshot(["unavailable"], capped=False)
    assert len(snap["unavailable"]) == 50
    assert "truncated" not in snap


def test_file_su_disco_resta_completo(monitor, tmp_path):
    """Sequenza vera: leggo in forma troncata, POI salvo, POI rileggo il file.
    Senza la lettura in mezzo l'asserzione sarebbe una tautologia su _save_sync
    e passerebbe identica anche se get_snapshot mutasse il dato interno."""
    monitor._snapshot_data["unavailable_entities"] = _entita(50)

    troncato = monitor.get_snapshot(["unavailable"])
    assert len(troncato["unavailable"]) == MAX_UNAVAILABLE_ENTITIES

    monitor._save_sync()
    with open(str(tmp_path / "ha_health.json"), encoding="utf-8") as f:
        salvato = json.load(f)
    assert len(salvato["unavailable_entities"]) == 50

    # Osservabile dall'esterno: una lettura non cappata li vede ancora tutti.
    completo = monitor.get_snapshot(["unavailable"], capped=False)
    assert len(completo["unavailable"]) == 50


# --- Cap: copertura di tutte le sezioni --------------------------------------


def _voci(n):
    return [{"id": f"v{i}"} for i in range(n)]


CASI_CAP = [
    pytest.param(
        {"integration_errors": _voci(MAX_INTEGRATION_ERRORS + 3)},
        "integrations", "integrations", MAX_INTEGRATION_ERRORS,
        MAX_INTEGRATION_ERRORS + 3, lambda snap: snap["integrations"],
        id="integrations",
    ),
    pytest.param(
        {"error_log_summary": {"errors": 9, "warnings": 4,
                               "top_errors": _voci(MAX_TOP_ERRORS + 4)}},
        "logs", "logs.top_errors", MAX_TOP_ERRORS,
        MAX_TOP_ERRORS + 4, lambda snap: snap["logs"]["top_errors"],
        id="logs.top_errors",
    ),
    pytest.param(
        {"updates_available": _voci(MAX_UPDATES + 2)},
        "updates", "updates", MAX_UPDATES,
        MAX_UPDATES + 2, lambda snap: snap["updates"],
        id="updates",
    ),
    pytest.param(
        {"system_health": {f"dominio{i}": {"ok": True}
                           for i in range(MAX_SYSTEM_HEALTH_DOMAINS + 5)}},
        "system_health", "system_health", MAX_SYSTEM_HEALTH_DOMAINS,
        MAX_SYSTEM_HEALTH_DOMAINS + 5, lambda snap: snap["system_health"],
        id="system_health",
    ),
    pytest.param(
        {"supervisor": {"addons": [], "disk": {"disk_free": 60},
                        "updates": _voci(MAX_SUPERVISOR_UPDATES + 6)}},
        "supervisor", "supervisor.updates", MAX_SUPERVISOR_UPDATES,
        MAX_SUPERVISOR_UPDATES + 6, lambda snap: snap["supervisor"]["updates"],
        id="supervisor.updates",
    ),
]


@pytest.mark.parametrize("dati,sezione,chiave,limite,totale,estrai", CASI_CAP)
def test_ogni_sezione_e_troncata_e_lo_dichiara(
    monitor, dati, sezione, chiave, limite, totale, estrai
):
    """Il design chiedeva che i cap troncassero E lo dichiarassero, al plurale:
    ogni sezione cappata deve comportarsi allo stesso modo."""
    monitor._snapshot_data.update(dati)

    snap = monitor.get_snapshot([sezione])
    assert len(estrai(snap)) == limite
    assert snap["truncated"][chiave]["shown"] == limite
    assert snap["truncated"][chiave]["total"] == totale

    # La dashboard (capped=False) vede tutto e nulla viene dichiarato troncato.
    completo = monitor.get_snapshot([sezione], capped=False)
    assert len(estrai(completo)) == totale
    assert "truncated" not in completo
    # Il troncamento in lettura non muta mai il dato interno.
    assert len(estrai(monitor.get_snapshot([sezione], capped=False))) == totale


def test_logs_conserva_i_conteggi_reali_quando_tronca(monitor):
    """Il cap taglia solo l'elenco dei top errori: errors/warnings restano i
    conteggi veri, altrimenti l'LLM riferirebbe meno problemi di quanti sono."""
    monitor._snapshot_data["error_log_summary"] = {
        "errors": 137, "warnings": 41, "top_errors": _voci(MAX_TOP_ERRORS + 5),
    }
    snap = monitor.get_snapshot(["logs"])
    assert snap["logs"]["errors"] == 137
    assert snap["logs"]["warnings"] == 41
    assert len(snap["logs"]["top_errors"]) == MAX_TOP_ERRORS
