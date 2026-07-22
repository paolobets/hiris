# tests/test_sentinel_smoke.py
import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore
from hiris.app.watcher.reasoner import reason
from hiris.app.watcher.executor import execute
from hiris.app.watcher.signals import Decision
from hiris.app.watcher.evaluator import SituationEvaluator

@pytest.mark.asyncio
async def test_battery_anomaly_end_to_end(tmp_path):
    store = SentinelStore(str(tmp_path / "s.db"))
    notified = []
    async def fake_llm(system, user, *, model, max_tokens):
        return '```json\n{"verdict":"anomalia","severity":"info","message":"Batteria all\'8%","action":null}\n```'
    async def notify(message, *, title): notified.append(message)
    async def act(a): raise AssertionError("non deve agire")
    async def propose(d, w): raise AssertionError("non deve proporre")

    async def on_wake(wake):
        d = await reason(wake, gather_context=lambda w: {"friendly_name": "Batt"}, llm_reason=fake_llm)
        out = await execute(d, wake, tiers={}, entity_tiers={},
                            notify=notify, act=act, propose=propose, allow_green_auto=False)
        store.record_event({"ts": 1.0, "kind": wake.signal_kind, "entity_id": wake.entity_id,
                            "verdict": d.verdict, "severity": d.severity, "outcome": out, "message": d.message})

    pol = {"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 10}}}
    g = Guardian(store, lambda: pol, on_wake, clock=lambda: 1.0, today=lambda: "2026-07-20")
    await g.on_state_changed({"entity_id": "sensor.b",
                              "old_state": {"state": "50"}, "new_state": {"state": "8"}})
    assert notified == ["Batteria all'8%"]
    assert store.recent_events(1)[0]["outcome"] == "notify"
    store.close()


@pytest.mark.asyncio
async def test_situation_hot_away_end_to_end(tmp_path):
    store = SentinelStore(str(tmp_path / "s.db"))
    acted, notified = [], []
    async def build_snapshot():
        return {"presence": {"present": False}, "outside_temp_c": 35,
                "weather": {"rain_soon": False}, "alarm_state": None}
    async def notify(m, *, title): notified.append(m)
    async def act(a): acted.append(a)
    async def propose(d, w): raise AssertionError("non proporre: verde+optin")
    async def on_situation(wake, suggested):
        d = Decision("anomalia", "info", "Fa caldo, irrigo", None)
        if suggested: d.action = suggested
        out = await execute(d, wake, tiers={"switch": "green"}, entity_tiers={},
                            notify=notify, act=act, propose=propose, allow_green_auto=True)
        store.record_event({"ts": 1.0, "kind": wake.signal_kind, "entity_id": "switch.irr",
                            "verdict": d.verdict, "severity": d.severity, "outcome": out, "message": d.message})
    async def holistic(s): pass
    cfg = lambda: {"situations": {"presence_entity": "person.p",
        "hot_and_away": {"enabled": True, "outside_temp_entity": "sensor.t", "hot_threshold_c": 32,
                         "valve_entity": "switch.irr", "run_minutes": 5, "skip_if_rain": True},
        "away_alarm_off": {"enabled": False}, "holistic": {"enabled": False}}}
    ev = SituationEvaluator(store, cfg, build_snapshot=build_snapshot, on_situation=on_situation,
                            holistic_reason=holistic, clock=lambda: 1.0, today=lambda: "2026-07-21")
    await ev.run_evaluation()
    assert acted and acted[0]["entity_id"] == "switch.irr" and notified
    store.close()


@pytest.mark.asyncio
async def test_evening_arrival_end_to_end(tmp_path):
    from hiris.app.watcher.arrival import ArrivalWatcher
    store = SentinelStore(str(tmp_path / "s.db"))
    acted, notified = [], []
    async def get_states(ids):
        return [{"entity_id": "sun.sun", "state": "below_horizon"}] if "sun.sun" in ids else []
    deps = {"get_states": get_states, "now_hour": lambda: 21}
    async def notify(m, *, title): notified.append(m)
    async def act(a): acted.append(a)
    async def propose(d, w): raise AssertionError("verde+optin: non proporre")
    async def on_arrival(wake, suggested):
        d = Decision("anomalia", "info", "Bentornato, accendo la scena", None)
        if suggested: d.action = suggested
        out = await execute(d, wake, tiers={"scene": "green"}, entity_tiers={},
                            notify=notify, act=act, propose=propose, allow_green_auto=True)
        store.record_event({"ts": 1.0, "kind": wake.signal_kind, "entity_id": "scene.rientro",
                            "verdict": d.verdict, "severity": d.severity, "outcome": out, "message": d.message})
    cfg = lambda: {"situations": {"presence_entity": "person.p"},
                   "preparation": {"evening_arrival": {"enabled": True, "target_entity": "scene.rientro",
                       "sun_entity": "sun.sun", "after_hour": 18}}}
    w = ArrivalWatcher(store, cfg, deps=deps, on_arrival=on_arrival,
                       clock=lambda: 1.0, today=lambda: "2026-07-22")
    await w.on_state_changed({"entity_id": "person.p", "old_state": {"state": "not_home"},
                              "new_state": {"state": "home"}})
    assert acted and acted[0]["entity_id"] == "scene.rientro" and notified
    store.close()
