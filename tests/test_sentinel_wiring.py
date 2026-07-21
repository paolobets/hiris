import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore


async def _noop():
    return None


@pytest.mark.asyncio
async def test_guardian_set_policy_live(tmp_path):
    store = SentinelStore(str(tmp_path / "s.db"))
    pol = {"detectors": {"battery": {"enabled": False, "entities": ["sensor.b"], "min_pct": 10}}}
    g = Guardian(store, lambda: pol, lambda we: _noop(),
                 clock=lambda: 1.0, today=lambda: "2026-07-20")
    g.set_policy({"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 10}}})
    woke = []
    g._on_wake = lambda we: woke.append(we) or _noop()
    await g.on_state_changed({"data": {"entity_id": "sensor.b",
                             "old_state": {"state": "50"}, "new_state": {"state": "5"}}})
    assert len(woke) == 1
    store.close()


def test_create_app_registers_sentinel_routes():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/api/sentinel/policy" in paths
    assert "/api/sentinel/timeline" in paths
