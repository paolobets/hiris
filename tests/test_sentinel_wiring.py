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
    await g.on_state_changed({"entity_id": "sensor.b",
                              "old_state": {"state": "50"}, "new_state": {"state": "5"}})
    assert len(woke) == 1
    store.close()


def test_create_app_registers_sentinel_routes():
    from hiris.app.server import create_app
    app = create_app()
    paths = {r.resource.canonical for r in app.router.routes()}
    assert "/api/sentinel/policy" in paths
    assert "/api/sentinel/timeline" in paths


def test_evaluator_and_off_task_wired(tmp_path):
    """Task 8 wiring smoke test: evaluator + off_task modules import cleanly and
    are usable, without reloading hiris.app.server (which has import-time side
    effects — see test_create_app_registers_sentinel_routes for that coverage).
    The real startup wiring (server.py's _on_startup) is verified separately via
    `python -c "import hiris.app.server"` and manual/integration checks, same as
    fetta 1's guardian wiring."""
    from hiris.app.watcher.evaluator import SituationEvaluator
    from hiris.app.watcher.off_task import build_off_task

    store = SentinelStore(str(tmp_path / "s.db"))

    async def _build_snapshot():
        return {}

    async def _on_situation(wake, suggested):
        return None

    async def _holistic_reason(snapshot):
        return None

    evaluator = SituationEvaluator(
        store, lambda: {"situations": {}},
        build_snapshot=_build_snapshot, on_situation=_on_situation,
        holistic_reason=_holistic_reason)
    assert evaluator is not None
    store.close()

    # build_off_task: only builds a delayed turn_off for turn_on + off_after_min.
    off = build_off_task({
        "domain": "switch", "service": "turn_on", "entity_id": "switch.irrigation",
        "off_after_min": 10,
    })
    assert off is not None
    assert off["trigger"] == {"type": "delay", "minutes": 10}
    assert off["actions"] == [{
        "type": "call_ha_service", "domain": "switch",
        "service": "turn_off", "data": {"entity_id": "switch.irrigation"},
    }]

    # No off-task for actions without off_after_min (e.g. plain notify/toggle).
    assert build_off_task({"domain": "switch", "service": "turn_on", "entity_id": "switch.x"}) is None
    assert build_off_task({"domain": "light", "service": "turn_off", "entity_id": "light.x", "off_after_min": 5}) is None
