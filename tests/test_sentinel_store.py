import pytest
from hiris.app.watcher.sentinel_store import SentinelStore

@pytest.fixture
def store(tmp_path):
    s = SentinelStore(str(tmp_path / "sentinel.db"))
    yield s
    s.close()

def test_timer_open_idempotent(store):
    store.open_timer("opening:binary_sensor.porta", 100.0)
    store.open_timer("opening:binary_sensor.porta", 200.0)  # non sovrascrive
    assert store.timer_started_at("opening:binary_sensor.porta") == 100.0
    store.clear_timer("opening:binary_sensor.porta")
    assert store.timer_started_at("opening:binary_sensor.porta") is None

def test_cooldown(store):
    assert store.last_wake("k") is None
    store.mark_wake("k", 500.0)
    assert store.last_wake("k") == 500.0

def test_daily_counter(store):
    assert store.wakes_today("2026-07-20") == 0
    assert store.incr_wakes_today("2026-07-20") == 1
    assert store.incr_wakes_today("2026-07-20") == 2
    assert store.wakes_today("2026-07-20") == 2
    assert store.wakes_today("2026-07-21") == 0

def test_events_timeline(store):
    store.record_event({"ts": 1.0, "kind": "battery", "entity_id": "sensor.b",
                        "verdict": "anomalia", "severity": "info",
                        "outcome": "notify", "message": "batteria 8%"})
    rows = store.recent_events(10)
    assert len(rows) == 1 and rows[0]["kind"] == "battery"
