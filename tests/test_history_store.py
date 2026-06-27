import os
from hiris.app.history.store import HistoryStore
from hiris.app.history.store import _rollup_events


def _store(tmp_path):
    return HistoryStore(os.path.join(str(tmp_path), "history.db"))


def test_append_numeric_and_state(tmp_path):
    s = _store(tmp_path)
    s.append("sensor.temp", "2026-06-26T10:00:00+00:00", "21.5")
    s.append("binary_sensor.door", "2026-06-26T10:00:01+00:00", "on")
    rows = s._all_events()  # test helper
    assert rows[0]["entity_id"] == "sensor.temp"
    assert rows[0]["num"] == 21.5
    assert rows[1]["entity_id"] == "binary_sensor.door"
    assert rows[1]["num"] is None     # non-numeric -> NULL


def test_append_ignores_unparseable_timestamp_gracefully(tmp_path):
    s = _store(tmp_path)
    # empty/short ts is stored as-is; never raises (capture must be crash-proof)
    s.append("sensor.x", "", "5")
    assert len(s._all_events()) == 1


def test_rollup_events_numeric():
    events = [
        {"ts": "2026-06-20T01:00:00+00:00", "state": "19.0", "num": 19.0},
        {"ts": "2026-06-20T13:00:00+00:00", "state": "24.0", "num": 24.0},
    ]
    agg = _rollup_events(events)
    assert agg["n"] == 2
    assert agg["min"] == 19.0 and agg["max"] == 24.0 and agg["mean"] == 21.5
    assert agg["transitions"] == 1            # 19->24 is one change
    assert agg["last_state"] == "24.0"


def test_rollup_events_onoff_durations():
    # on at 09:00:00, off at 09:05:00 -> 300s on; ends 'off'
    events = [
        {"ts": "2026-06-20T09:00:00+00:00", "state": "on", "num": None},
        {"ts": "2026-06-20T09:05:00+00:00", "state": "off", "num": None},
    ]
    agg = _rollup_events(events)
    assert agg["on_seconds"] == 300.0
    assert agg["transitions"] == 1
    assert agg["last_state"] == "off"
    assert agg["mean"] is None                # non-numeric -> no numeric stats


def test_rollup_day_persists_and_is_idempotent(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    s.append("sensor.t", "2026-06-20T01:00:00+00:00", "19.0")
    s.append("sensor.t", "2026-06-20T13:00:00+00:00", "24.0")
    s.rollup_day("sensor.t", "2026-06-20")
    s.rollup_day("sensor.t", "2026-06-20")    # idempotent (REPLACE)
    rows = s._daily("sensor.t")
    assert len(rows) == 1
    assert rows[0]["day"] == "2026-06-20" and rows[0]["mean"] == 21.5


def test_compact_rolls_complete_days_and_prunes_old_raw(tmp_path):
    import os
    from hiris.app.history.store import HistoryStore
    s = HistoryStore(os.path.join(str(tmp_path), "h.db"))
    s.append("sensor.t", "2026-06-15T10:00:00+00:00", "10.0")
    s.append("sensor.t", "2026-06-19T10:00:00+00:00", "20.0")
    s.append("sensor.t", "2026-06-20T10:00:00+00:00", "30.0")   # 'today' -> not rolled
    s.compact(today="2026-06-20", retention_days=3)
    # complete days (15, 19) rolled into daily; today (20) left raw
    days = {r["day"] for r in s._daily("sensor.t")}
    assert "2026-06-15" in days and "2026-06-19" in days
    assert "2026-06-20" not in days
    # raw older than retention (today-3 = 2026-06-17) pruned: 15 gone, 19 & 20 kept
    remaining = {e["ts"][:10] for e in s._all_events()}
    assert "2026-06-15" not in remaining
    assert "2026-06-19" in remaining and "2026-06-20" in remaining
