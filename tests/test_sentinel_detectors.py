from hiris.app.watcher.detectors import (
    detect_open, detect_fridge_temp, detect_power_anomaly, detect_low_battery, DETECTORS, _num,
)

def _st(state, **attrs):
    return {"state": state, "attributes": attrs}

def test_num_rejects_unavailable():
    assert _num(_st("unavailable")) is None
    assert _num(_st("unknown")) is None
    assert _num(_st("12.5")) == 12.5

def test_detect_open_fires_on_on_state():
    sig = detect_open("binary_sensor.porta", _st("off"), _st("on"),
                      {"open_minutes": 10}, now=1000.0)
    assert sig is not None
    assert sig.kind == "opening"
    assert sig.evidence["needs_duration"] is True
    assert sig.evidence["threshold_min"] == 10

def test_detect_open_ignores_off_and_unavailable():
    assert detect_open("binary_sensor.porta", _st("on"), _st("off"), {"open_minutes": 10}, 1.0) is None
    assert detect_open("binary_sensor.porta", _st("off"), _st("unavailable"), {"open_minutes": 10}, 1.0) is None

def test_detect_fridge_temp_over_threshold():
    sig = detect_fridge_temp("sensor.frigo", _st("4"), _st("9.2"),
                             {"max_temp_c": 8, "duration_min": 30}, now=1.0)
    assert sig and sig.kind == "fridge_temp"
    assert sig.evidence["temp"] == 9.2
    assert sig.evidence["needs_duration"] is True

def test_detect_fridge_temp_ok_when_below():
    assert detect_fridge_temp("sensor.frigo", _st("4"), _st("6"),
                              {"max_temp_c": 8, "duration_min": 30}, 1.0) is None

def test_detect_low_battery_instant():
    sig = detect_low_battery("sensor.batt", _st("50"), _st("8"), {"min_pct": 10}, 1.0)
    assert sig and sig.kind == "battery" and sig.evidence["pct"] == 8.0
    assert "needs_duration" not in sig.evidence

def test_detect_power_anomaly_instant():
    sig = detect_power_anomaly("sensor.p", _st("100"), _st("3500"), {"max_watt": 3000}, 1.0)
    assert sig and sig.kind == "power" and sig.evidence["watt"] == 3500.0

def test_registry_complete():
    assert set(DETECTORS) == {"opening", "fridge_temp", "power", "battery"}
