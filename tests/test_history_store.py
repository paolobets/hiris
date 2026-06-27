import os
from hiris.app.history.store import HistoryStore


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
