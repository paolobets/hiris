from hiris.app.tools import history_tools as H


def test_validate_inputs_ok():
    assert H.validate_inputs(["sensor.a"], 7, "auto") is None


def test_validate_inputs_rejects_empty_and_too_many():
    assert H.validate_inputs([], 7, "auto") is not None
    assert H.validate_inputs(["x"] * 21, 7, "auto") is not None


def test_validate_inputs_rejects_bad_days_and_resolution():
    assert H.validate_inputs(["x"], 0, "auto") is not None
    assert H.validate_inputs(["x"], 400, "auto") is not None
    assert H.validate_inputs(["x"], 7, "weekly") is not None


def test_classify_numeric_vs_state():
    numeric = [{"state": "21.5"}, {"state": "22.0"}, {"state": "bad"}]
    state = [{"state": "on"}, {"state": "off"}, {"state": "on"}]
    assert H.classify(numeric) == "numeric"   # majority parse as float
    assert H.classify(state) == "state"


def test_aggregate_numeric_daily():
    samples = [
        {"t": "2026-06-20T01:00:00+00:00", "state": "19.0"},
        {"t": "2026-06-20T13:00:00+00:00", "state": "24.0"},
        {"t": "2026-06-21T08:00:00+00:00", "state": "20.0"},
    ]
    out = H.aggregate_numeric(samples, "daily")
    assert out[0] == {"t": "2026-06-20", "min": 19.0, "max": 24.0, "mean": 21.5, "n": 2}
    assert out[1]["t"] == "2026-06-21" and out[1]["n"] == 1


def test_downsample_caps_points():
    pts = [{"t": str(i), "state": str(i)} for i in range(1000)]
    out = H.downsample(pts, 100)
    assert len(out) <= 100
    assert out[0] == pts[0] and out[-1] == pts[-1]   # endpoints preserved


def test_normalize_statistics_rows():
    rows = [{"start": "2026-06-20T00:00:00+00:00", "mean": 21.6, "min": 19.1, "max": 24.3},
            {"start": 1782000000000, "mean": 22.0, "min": 20.0, "max": 25.0}]  # ms epoch
    out = H.normalize_statistics(rows)
    assert out[0] == {"t": "2026-06-20", "min": 19.1, "max": 24.3, "mean": 21.6, "n": 1}
    assert out[1]["t"] == "2026-06-21"   # ms epoch parsed to date


def test_aggregate_numeric_skips_samples_without_timestamp():
    samples = [
        {"state": "21.0"},                                  # missing 't'
        {"t": "", "state": "22.0"},                         # empty 't'
        {"t": "2026-06-20T10:00:00+00:00", "state": "23.0"},
    ]
    out = H.aggregate_numeric(samples, "daily")
    assert out == [{"t": "2026-06-20", "min": 23.0, "max": 23.0, "mean": 23.0, "n": 1}]


def test_aggregate_numeric_all_invalid_states_returns_empty():
    samples = [{"t": "2026-06-20T01:00:00+00:00", "state": "unavailable"},
               {"t": "2026-06-20T02:00:00+00:00", "state": "unknown"}]
    assert H.aggregate_numeric(samples, "daily") == []


def test_normalize_statistics_skips_rows_without_start():
    rows = [{"mean": 1.0, "min": 0.0, "max": 2.0},          # no 'start'
            {"start": None, "mean": 1.0},                    # null start
            {"start": "2026-06-20T00:00:00+00:00", "mean": 21.6, "min": 19.1, "max": 24.3}]
    out = H.normalize_statistics(rows)
    assert out == [{"t": "2026-06-20", "min": 19.1, "max": 24.3, "mean": 21.6, "n": 1}]


def test_validate_inputs_rejects_bool_days():
    assert H.validate_inputs(["x"], True, "auto") is not None


def test_classify_empty_is_state():
    assert H.classify([]) == "state"
