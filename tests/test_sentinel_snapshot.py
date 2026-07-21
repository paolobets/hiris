import pytest
from hiris.app.watcher.snapshot import interpret_presence, build_snapshot

def test_interpret_presence():
    assert interpret_presence("home") is True
    assert interpret_presence("on") is True
    assert interpret_presence("2") is True
    assert interpret_presence("not_home") is False
    assert interpret_presence("unavailable") is None
    assert interpret_presence(None) is None

@pytest.mark.asyncio
async def test_build_snapshot_reads_configured_entities():
    async def get_states(ids):
        m = {"person.p": {"state": "not_home"}, "sensor.temp": {"state": "34.5"},
             "alarm_control_panel.casa": {"state": "disarmed"}}
        return [m[i] | {"entity_id": i} for i in ids if i in m]
    async def get_weather():
        return {"hourly": [{"h": "2026-07-21T12", "t": 34.0, "cc": 10, "r": 0.0},
                           {"h": "2026-07-21T13", "t": 35.0, "cc": 10, "r": 0.0}]}
    def get_health():
        return {"status": "ok"}
    deps = {"get_states": get_states, "get_weather": get_weather, "get_health": get_health}
    cfg = {"presence_entity": "person.p", "hot_and_away": {"outside_temp_entity": "sensor.temp"},
           "away_alarm_off": {"alarm_entity": "alarm_control_panel.casa"}}
    snap = await build_snapshot(deps, cfg)
    assert snap["presence"]["present"] is False
    assert snap["outside_temp_c"] == 34.5
    assert snap["alarm_state"] == "disarmed"
    assert snap["weather"]["rain_soon"] is False
    assert snap["ha_health"] == {"status": "ok"}

@pytest.mark.asyncio
async def test_build_snapshot_missing_entities_are_none():
    async def get_states(ids): return []
    async def get_weather(): raise RuntimeError("no net")
    def get_health(): return None
    snap = await build_snapshot(
        {"get_states": get_states, "get_weather": get_weather, "get_health": get_health},
        {"presence_entity": "person.x"})
    assert snap["presence"]["present"] is None
    assert snap["outside_temp_c"] is None
    assert snap["weather"]["rain_soon"] is None
