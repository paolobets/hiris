import pytest
from hiris.app.watcher.guardian import Guardian
from hiris.app.watcher.sentinel_store import SentinelStore

@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db")); yield s; s.close()

def _policy():
    return {"detectors": {
        "battery": {"enabled": True, "entities": ["sensor.batt"], "min_pct": 10},
        "opening": {"enabled": True, "entities": ["binary_sensor.porta"], "open_minutes": 10},
    }}

# Shape pinned to the REAL contract: ha_client.py:490 dispatches state
# listeners as `cb(event["data"])` — the unwrapped HA state_changed event
# data, with entity_id/old_state/new_state at the top level (see also
# entity_cache.on_state_changed which reads event_data.get("new_state")
# directly). Do NOT wrap this in another {"data": ...} layer.
def _evt(eid, old, new):
    return {"entity_id": eid,
            "old_state": {"state": old, "attributes": {}},
            "new_state": {"state": new, "attributes": {}}}

@pytest.mark.asyncio
async def test_instant_detector_wakes(store):
    woke = []
    g = Guardian(store, _policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-20")
    await g.on_state_changed(_evt("sensor.batt", "50", "8"))
    assert len(woke) == 1 and woke[0].signal_kind == "battery"

@pytest.mark.asyncio
async def test_cooldown_suppresses_second(store):
    woke = []
    t = {"v": 1000.0}
    g = Guardian(store, _policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-20", cooldown_sec=1800)
    await g.on_state_changed(_evt("sensor.batt", "50", "8"))
    t["v"] = 1000.0 + 600  # <1800s dopo
    await g.on_state_changed(_evt("sensor.batt", "9", "7"))
    assert len(woke) == 1  # secondo soppresso da cooldown

@pytest.mark.asyncio
async def test_duration_detector_waits(store):
    woke = []
    t = {"v": 0.0}
    g = Guardian(store, _policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-20")
    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))  # apre timer
    assert woke == []
    t["v"] = 11 * 60  # oltre 10 min
    await g.on_state_changed(_evt("binary_sensor.porta", "on", "on"))
    assert len(woke) == 1 and woke[0].signal_kind == "opening"

@pytest.mark.asyncio
async def test_daily_cap_blocks_ai(store):
    woke = []
    g = Guardian(store, _policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: 1000.0, today=lambda: "2026-07-20", daily_cap=0)
    await g.on_state_changed(_evt("sensor.batt", "50", "8"))
    assert woke == []  # cap 0 → nessun risveglio AI
    assert store.recent_events(5)[0]["outcome"] == "cap"

@pytest.mark.asyncio
async def test_never_raises_on_bad_event(store):
    g = Guardian(store, _policy, lambda we: _noop(),
                 clock=lambda: 1.0, today=lambda: "2026-07-20")
    await g.on_state_changed({"entity_id": None})  # nessun crash
    await g.on_state_changed({})                   # nessun crash

@pytest.mark.asyncio
async def test_duration_timer_cleared_when_condition_clears(store):
    woke = []
    t = {"v": 0.0}
    g = Guardian(store, _policy, lambda we: woke.append(we) or _noop(),
                 clock=lambda: t["v"], today=lambda: "2026-07-20")
    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))   # apre timer
    assert store.timer_started_at("opening:binary_sensor.porta") == 0.0
    await g.on_state_changed(_evt("binary_sensor.porta", "on", "off"))   # rientra → detector None
    assert store.timer_started_at("opening:binary_sensor.porta") is None # timer azzerato
    t["v"] = 20 * 60                                                     # oltre soglia
    await g.on_state_changed(_evt("binary_sensor.porta", "off", "on"))   # riparte da capo
    assert woke == []                                                    # non sveglia (timer riaperto ora)

async def _noop():
    return None
