import pytest
from hiris.app.watcher.evaluator import SituationEvaluator
from hiris.app.watcher.sentinel_store import SentinelStore

@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db")); yield s; s.close()

def _cfg():
    return {"situations": {
        "presence_entity": "person.p",
        "hot_and_away": {"enabled": True, "outside_temp_entity": "sensor.t",
                         "hot_threshold_c": 32, "valve_entity": "switch.irr", "run_minutes": 5, "skip_if_rain": True},
        "away_alarm_off": {"enabled": False},
        "holistic": {"enabled": False, "per_day": 1}}}

@pytest.mark.asyncio
async def test_situation_fires_and_calls_on_situation(store):
    calls = []
    async def build_snapshot():
        return {"presence": {"present": False}, "outside_temp_c": 34,
                "weather": {"rain_soon": False}, "alarm_state": None}
    async def on_situation(wake, suggested):
        calls.append((wake.signal_kind, suggested))
    async def holistic(snap): calls.append(("holistic", None))
    ev = SituationEvaluator(store, _cfg, build_snapshot=build_snapshot,
                            on_situation=on_situation, holistic_reason=holistic,
                            clock=lambda: 1.0, today=lambda: "2026-07-21")
    await ev.run_evaluation()
    assert ("hot_and_away", {"domain": "switch", "service": "turn_on",
            "entity_id": "switch.irr", "data": {}, "off_after_min": 5}) in calls
    # holistic disabilitato → non chiamato
    assert ("holistic", None) not in calls

@pytest.mark.asyncio
async def test_never_raises_on_bad_snapshot(store):
    async def build_snapshot(): raise RuntimeError("boom")
    async def on_situation(w, s): pass
    async def holistic(s): pass
    ev = SituationEvaluator(store, _cfg, build_snapshot=build_snapshot,
                            on_situation=on_situation, holistic_reason=holistic,
                            clock=lambda: 1.0, today=lambda: "2026-07-21")
    await ev.run_evaluation()  # nessun crash

@pytest.mark.asyncio
async def test_two_situations_fire_without_action_cross_contamination(store):
    calls = {}
    async def build_snapshot():
        return {"presence": {"present": False}, "outside_temp_c": 34,
                "weather": {"rain_soon": False}, "alarm_state": "disarmed"}
    async def on_situation(wake, suggested):
        calls[wake.signal_kind] = suggested
    async def holistic(snap): pass
    cfg = lambda: {"situations": {"presence_entity": "person.p",
        "hot_and_away": {"enabled": True, "outside_temp_entity": "sensor.t", "hot_threshold_c": 32,
                         "valve_entity": "switch.irr", "run_minutes": 5, "skip_if_rain": True},
        "away_alarm_off": {"enabled": True, "alarm_entity": "alarm_control_panel.casa",
                           "disarmed_states": ["disarmed"]},
        "holistic": {"enabled": False}}}
    ev = SituationEvaluator(store, cfg, build_snapshot=build_snapshot, on_situation=on_situation,
                            holistic_reason=holistic, clock=lambda: 1.0, today=lambda: "2026-07-21")
    await ev.run_evaluation()
    # each situation must carry ITS OWN suggested_action, not the last loop iteration's
    assert calls["hot_and_away"] is not None and calls["hot_and_away"]["entity_id"] == "switch.irr"
    assert calls["away_alarm_off"] is None
