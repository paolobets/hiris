from hiris.app.brain.history_digest import (
    compute_insights, _sensitivity_for, _pct_delta,
)


def _numeric_buckets(start_day, vals):
    out = []
    for i, v in enumerate(vals):
        d = "2026-06-%02d" % (start_day + i)
        out.append({"t": d, "min": v - 1, "max": v + 1, "mean": v, "n": 24})
    return out


def test_pct_delta():
    assert _pct_delta(112.0, 100.0) == 12.0
    assert _pct_delta(100.0, 0.0) is None
    assert _pct_delta(90.0, 100.0) == -10.0


def test_sensitivity_for():
    assert _sensitivity_for("binary_sensor.porta") == "sensitive"
    assert _sensitivity_for("device_tracker.paolo") == "sensitive"
    assert _sensitivity_for("sensor.temp") == "normal"
    assert _sensitivity_for("climate.salotto") == "normal"


def test_compute_insights_numeric_delta():
    buckets = _numeric_buckets(7, [20, 20, 20, 20, 20, 20, 20, 24, 24, 24, 24, 24, 24, 24])
    ins = compute_insights("sensor.temp_salotto", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["entity_id"] == "sensor.temp_salotto"
    assert i["source_ref"] == "history-digest:sensor.temp_salotto:weekly"
    assert i["sensitivity"] == "normal"
    assert "20%" in i["text"] or "+20" in i["text"]
    assert "sensor.temp_salotto" in i["text"]


def test_compute_insights_onoff_summary():
    buckets = []
    for d in range(14, 21):
        buckets.append({"t": "2026-06-%02d" % d, "on_seconds": 3600, "transitions": 4})
    ins = compute_insights("binary_sensor.movimento", buckets, today="2026-06-21")
    assert len(ins) == 1
    i = ins[0]
    assert i["sensitivity"] == "sensitive"
    assert "ore" in i["text"].lower()


def test_compute_insights_insufficient_data_returns_none():
    buckets = [{"t": "2026-06-20", "mean": 20.0, "min": 19, "max": 21, "n": 5}]
    assert compute_insights("sensor.x", buckets, today="2026-06-21") == []
