import pytest
from datetime import datetime, timezone
from hiris.app.brain.health_scan import run_health_scan
from hiris.app.brain.advisory_store import AdvisoryStore


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
