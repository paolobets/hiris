import os

from hiris.app.history.store import HistoryStore


def _store(tmp_path):
    return HistoryStore(os.path.join(str(tmp_path), "history.db"))


def test_baseline_for_numeric_buckets_averages_mean(tmp_path):
    s = _store(tmp_path)
    s.append("sensor.temp", "2026-06-18T10:00:00+00:00", "10.0")
    s.append("sensor.temp", "2026-06-18T12:00:00+00:00", "20.0")
    s.rollup_day("sensor.temp", "2026-06-18")   # daily mean = 15.0
    s.append("sensor.temp", "2026-06-19T10:00:00+00:00", "30.0")
    s.rollup_day("sensor.temp", "2026-06-19")   # daily mean = 30.0
    out = s.baseline_for("sensor.temp", days=7, today="2026-06-20")
    assert out["mean"] == 22.5   # avg(15.0, 30.0)
    assert out["on_hours"] is None
    assert out["n_days"] == 2


def test_baseline_for_onoff_buckets_computes_on_hours(tmp_path):
    s = _store(tmp_path)
    # day 1: 3600s on
    s.append("binary_sensor.door", "2026-06-18T09:00:00+00:00", "on")
    s.append("binary_sensor.door", "2026-06-18T10:00:00+00:00", "off")
    s.rollup_day("binary_sensor.door", "2026-06-18")
    # day 2: 7200s on
    s.append("binary_sensor.door", "2026-06-19T09:00:00+00:00", "on")
    s.append("binary_sensor.door", "2026-06-19T11:00:00+00:00", "off")
    s.rollup_day("binary_sensor.door", "2026-06-19")
    out = s.baseline_for("binary_sensor.door", days=7, today="2026-06-20")
    assert out["mean"] is None
    assert out["on_hours"] == 1.5   # avg(1h, 2h)
    assert out["n_days"] == 2


def test_baseline_for_no_history_returns_zeros(tmp_path):
    s = _store(tmp_path)
    out = s.baseline_for("sensor.absent", days=14, today="2026-06-20")
    assert out == {"mean": None, "on_hours": None, "n_days": 0}


def test_baseline_for_defaults_today_to_now(tmp_path):
    s = _store(tmp_path)
    # no history -> must not crash even without an explicit `today`
    out = s.baseline_for("sensor.absent")
    assert out == {"mean": None, "on_hours": None, "n_days": 0}


def test_baseline_for_days_default_is_14(tmp_path, monkeypatch):
    s = _store(tmp_path)
    captured = {}
    orig_query = s.query

    def spy(entity_id, days, today):
        captured["days"] = days
        return orig_query(entity_id, days, today)

    monkeypatch.setattr(s, "query", spy)
    s.baseline_for("sensor.absent", today="2026-06-20")
    assert captured["days"] == 14
