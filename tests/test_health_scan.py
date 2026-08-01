import pytest
from datetime import datetime, timezone
from hiris.app.brain.health_scan import run_health_scan
from hiris.app.brain.advisory_store import AdvisoryStore
from hiris.app.brain.health_checks import CHECK_IDS


class _FakeHA:
    def __init__(self, states, automations):
        self._states = states
        self._automations = automations
    async def get_states(self, ids):
        return self._states
    async def get_automations(self):
        return self._automations


class _FakeCache:
    def __init__(self, minimal, area_map):
        self._minimal = minimal
        self._area_map = area_map
    def all_states(self):
        return self._minimal
    def get_area_map(self):
        return self._area_map


@pytest.mark.asyncio
async def test_run_health_scan_populates_advisories(tmp_path):
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    ha = _FakeHA(
        states=[{"entity_id": "sensor.old", "state": "unavailable",
                 "last_changed": "2026-07-01T00:00:00+00:00", "attributes": {}}],
        automations=[{"entity_id": "automation.x", "state": "off", "attributes": {}}],
    )
    cache = _FakeCache(
        minimal=[{"id": "sensor.bat", "state": "5", "name": "Bat", "unit": "%", "device_class": "battery"}],
        area_map={"__no_area__": ["light.a"]},
    )
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=ha, entity_cache=cache,
        tiers={"lock": "green"}, entity_tiers={}, store=store, now=now,
    )
    assert res["inserted"] == 5  # unavailable, battery, automation, dangerous, no_area
    checks = {a["check_id"] for a in store.list()}
    assert checks == {"entity_unavailable", "low_battery", "automation_broken",
                      "dangerous_domain_green", "entity_no_area"}
    store.close()


@pytest.mark.asyncio
async def test_run_health_scan_survives_fetch_error(tmp_path):
    class _Boom:
        async def get_states(self, ids):
            raise RuntimeError("ha down")
        async def get_automations(self):
            return []
    cache = _FakeCache(minimal=[], area_map={})
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=_Boom(), entity_cache=cache,
        tiers={}, entity_tiers={}, store=store,
        now=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )
    assert res["inserted"] == 0  # no crash
    store.close()


class _FakeSupervisor:
    """Supervisor finto: ritorna i dati preimpostati, senza I/O."""

    def __init__(self, addons=None, host_info=None, updates=None):
        self._addons = addons if addons is not None else []
        self._host_info = host_info if host_info is not None else {}
        self._updates = updates if updates is not None else []

    async def get_addons(self):
        return self._addons

    async def get_host_info(self):
        return self._host_info

    async def get_available_updates(self):
        return self._updates


@pytest.mark.asyncio
async def test_run_health_scan_include_controlli_di_sistema(tmp_path):
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    ha = _FakeHA(states=[], automations=[])
    cache = _FakeCache(minimal=[], area_map={})
    supervisor = _FakeSupervisor(
        addons=[{"slug": "core_samba", "name": "Samba", "state": "error"}],
        host_info={"disk_total": 100, "disk_used": 95, "disk_free": 5},
        updates=[{"name": "Core", "update_type": "core", "version_latest": "2026.8"}],
    )
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=ha, entity_cache=cache, tiers={}, entity_tiers={},
        store=store, now=now, supervisor_client=supervisor,
    )
    assert res["inserted"] == 3
    checks = {a["check_id"] for a in store.list()}
    assert checks == {"addon_down", "disk_space", "updates_available"}
    # Senza questo, reconcile non chiuderebbe mai le segnalazioni nuove
    assert checks <= set(CHECK_IDS)
    store.close()


@pytest.mark.asyncio
async def test_run_health_scan_senza_supervisor(tmp_path):
    """Installazione senza Supervisor: nessun controllo di sistema, nessun errore."""
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=_FakeHA(states=[], automations=[]),
        entity_cache=_FakeCache(minimal=[], area_map={}),
        tiers={}, entity_tiers={}, store=store, now=now,
        supervisor_client=None,
    )
    assert res["inserted"] == 0
    assert store.list() == []
    store.close()


@pytest.mark.asyncio
async def test_run_health_scan_survives_supervisor_error(tmp_path):
    class _SupervisorBoom:
        async def get_addons(self):
            raise RuntimeError("supervisor down")

        async def get_host_info(self):
            raise RuntimeError("supervisor down")

        async def get_available_updates(self):
            return [{"name": "Core", "update_type": "core", "version_latest": "2026.8"}]

    store = AdvisoryStore(str(tmp_path / "a.db"))
    res = await run_health_scan(
        ha_client=_FakeHA(states=[], automations=[]),
        entity_cache=_FakeCache(minimal=[], area_map={}),
        tiers={}, entity_tiers={}, store=store,
        now=datetime(2026, 7, 28, tzinfo=timezone.utc),
        supervisor_client=_SupervisorBoom(),
    )
    # I blocchi sono indipendenti: gli aggiornamenti passano lo stesso
    assert res["inserted"] == 1
    assert {a["check_id"] for a in store.list()} == {"updates_available"}
    store.close()


@pytest.mark.asyncio
async def test_run_health_scan_idempotente_su_due_giri(tmp_path):
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    supervisor = _FakeSupervisor(
        addons=[{"slug": "core_samba", "name": "Samba", "state": "stopped"}],
        host_info={"disk_total": 100, "disk_used": 95, "disk_free": 5},
        updates=[{"name": "Core", "update_type": "core", "version_latest": "2026.8"}],
    )
    store = AdvisoryStore(str(tmp_path / "a.db"))
    kwargs = dict(ha_client=_FakeHA(states=[], automations=[]),
                  entity_cache=_FakeCache(minimal=[], area_map={}),
                  tiers={}, entity_tiers={}, store=store, now=now,
                  supervisor_client=supervisor)
    primo = await run_health_scan(**kwargs)
    secondo = await run_health_scan(**kwargs)
    assert primo["inserted"] == 3
    assert secondo["inserted"] == 0
    assert len(store.list()) == 3
    store.close()
