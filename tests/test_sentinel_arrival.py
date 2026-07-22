import pytest
from hiris.app.watcher.arrival import is_evening, ArrivalWatcher
from hiris.app.watcher.sentinel_store import SentinelStore

@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "s.db")); yield s; s.close()

def _cfg(enabled=True):
    return {"situations": {"presence_entity": "person.p"},
            "preparation": {"evening_arrival": {"enabled": enabled,
                "target_entity": "scene.rientro", "sun_entity": "sun.sun", "after_hour": 18}}}

def _evt(eid, old, new):
    return {"entity_id": eid, "old_state": {"state": old}, "new_state": {"state": new}}

def _deps(sun_state="below_horizon", hour=20):
    async def get_states(ids):
        return [{"entity_id": "sun.sun", "state": sun_state}] if "sun.sun" in ids else []
    return {"get_states": get_states, "now_hour": lambda: hour}

@pytest.mark.asyncio
async def test_is_evening_sun_below():
    assert await is_evening(_deps(sun_state="below_horizon"), {"sun_entity": "sun.sun"}) is True

@pytest.mark.asyncio
async def test_is_evening_sun_above_uses_hour_fallback():
    assert await is_evening(_deps(sun_state="above_horizon", hour=20), {"sun_entity": "sun.sun", "after_hour": 18}) is False
    # sun above → non è sera anche se ora tarda? spec: below_horizon è il segnale primario; se sun leggibile e above → NON sera
    # (il fallback all'ora vale solo quando sun NON è leggibile)

@pytest.mark.asyncio
async def test_is_evening_sun_absent_hour_fallback():
    async def get_states(ids): return []
    deps = {"get_states": get_states, "now_hour": lambda: 20}
    assert await is_evening(deps, {"sun_entity": "sun.sun", "after_hour": 18}) is True
    deps2 = {"get_states": get_states, "now_hour": lambda: 9}
    assert await is_evening(deps2, {"sun_entity": "sun.sun", "after_hour": 18}) is False

@pytest.mark.asyncio
async def test_arrival_fires_on_away_to_home_evening(store):
    calls = []
    async def on_arrival(wake, suggested): calls.append((wake.signal_kind, suggested))
    w = ArrivalWatcher(store, lambda: _cfg(), deps=_deps(), on_arrival=on_arrival,
                       clock=lambda: 1000.0, today=lambda: "2026-07-22")
    await w.on_state_changed(_evt("person.p", "not_home", "home"))
    assert len(calls) == 1
    assert calls[0][0] == "evening_arrival"
    assert calls[0][1] == {"domain": "scene", "service": "turn_on", "entity_id": "scene.rientro", "data": {}}

@pytest.mark.asyncio
async def test_arrival_ignores_non_edges_and_daytime(store):
    calls = []
    async def on_arrival(w, s): calls.append(1)
    # giorno (sun above, ora presto) → no
    w_day = ArrivalWatcher(store, lambda: _cfg(), deps=_deps(sun_state="above_horizon", hour=9),
                           on_arrival=on_arrival, clock=lambda: 1.0, today=lambda: "2026-07-22")
    await w_day.on_state_changed(_evt("person.p", "not_home", "home"))
    assert calls == []
    w = ArrivalWatcher(store, lambda: _cfg(), deps=_deps(), on_arrival=on_arrival,
                       clock=lambda: 1.0, today=lambda: "2026-07-22")
    await w.on_state_changed(_evt("person.p", "home", "home"))     # non-edge
    await w.on_state_changed(_evt("person.p", "unknown", "home"))  # None→home ignorato
    await w.on_state_changed(_evt("light.x", "not_home", "home"))  # entità diversa
    assert calls == []

@pytest.mark.asyncio
async def test_arrival_disabled_and_cooldown(store):
    calls = []
    async def on_arrival(w, s): calls.append(1)
    # disabilitato
    wd = ArrivalWatcher(store, lambda: _cfg(enabled=False), deps=_deps(), on_arrival=on_arrival,
                        clock=lambda: 1.0, today=lambda: "2026-07-22")
    await wd.on_state_changed(_evt("person.p", "not_home", "home"))
    assert calls == []
    # cooldown: due arrivi ravvicinati → un solo risveglio
    t = {"v": 1000.0}
    w = ArrivalWatcher(store, lambda: _cfg(), deps=_deps(), on_arrival=on_arrival,
                       clock=lambda: t["v"], today=lambda: "2026-07-22", cooldown_sec=1800)
    await w.on_state_changed(_evt("person.p", "not_home", "home"))
    t["v"] = 1000.0 + 600
    await w.on_state_changed(_evt("person.p", "not_home", "home"))
    assert len(calls) == 1

@pytest.mark.asyncio
async def test_never_raises(store):
    async def on_arrival(w, s): pass
    w = ArrivalWatcher(store, lambda: _cfg(), deps=_deps(), on_arrival=on_arrival,
                       clock=lambda: 1.0, today=lambda: "2026-07-22")
    await w.on_state_changed({})           # malformato
    await w.on_state_changed({"entity_id": "person.p"})  # senza stati
