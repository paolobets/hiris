import pytest
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


class _FakeHA:
    def __init__(self, history=None, stats=None):
        self._history = history or {}
        self._stats = stats or {}

    async def get_history(self, entity_ids, days):
        eid = entity_ids[0]
        return [dict(s, entity_id=eid) for s in self._history.get(eid, [])]

    async def get_statistics(self, statistic_ids, period, days):
        return {k: v for k, v in self._stats.items() if k in statistic_ids}


@pytest.mark.asyncio
async def test_get_history_recent_numeric_aggregates_recorder():
    ha = _FakeHA(history={"sensor.temp": [
        {"last_changed": "2026-06-26T01:00:00+00:00", "state": "19.0"},
        {"last_changed": "2026-06-26T13:00:00+00:00", "state": "24.0"},
    ]})
    out = await H.get_history(ha, ["sensor.temp"], days=3, resolution="auto")
    series = out[0]
    assert series["id"] == "sensor.temp"
    assert series["resolution"] == "daily"
    assert series["buckets"][0] == {"t": "2026-06-26", "min": 19.0, "max": 24.0,
                                    "mean": 21.5, "n": 2}


@pytest.mark.asyncio
async def test_get_history_long_range_uses_statistics():
    ha = _FakeHA(stats={"sensor.temp": [
        {"start": "2026-05-01T00:00:00+00:00", "mean": 18.0, "min": 15.0, "max": 21.0},
    ]})
    out = await H.get_history(ha, ["sensor.temp"], days=60, resolution="auto")
    series = out[0]
    assert series["source"] == "statistics"
    assert series["buckets"][0]["mean"] == 18.0


@pytest.mark.asyncio
async def test_get_history_long_range_falls_back_to_recorder_with_note():
    # No statistics for this entity -> fall back to recorder window + partial note.
    ha = _FakeHA(history={"binary_sensor.door": [
        {"last_changed": "2026-06-26T09:00:00+00:00", "state": "on"},
        {"last_changed": "2026-06-26T09:05:00+00:00", "state": "off"},
    ]})
    out = await H.get_history(ha, ["binary_sensor.door"], days=60, resolution="auto")
    series = out[0]
    assert series["source"] == "recorder"
    assert series["partial"] is True            # range exceeds recorder window
    assert series["resolution"] == "raw"        # non-numeric -> raw samples
    assert series["samples"][0]["state"] == "on"


@pytest.mark.asyncio
async def test_get_history_rejects_bad_input():
    ha = _FakeHA()
    out = await H.get_history(ha, [], days=7, resolution="auto")
    assert "error" in out


@pytest.mark.asyncio
async def test_get_history_statistics_hourly_label():
    ha = _FakeHA(stats={"sensor.power": [
        {"start": "2026-06-10T00:00:00+00:00", "mean": 120.0, "min": 80.0, "max": 200.0},
    ]})
    out = await H.get_history(ha, ["sensor.power"], days=20, resolution="hourly")
    series = out[0]
    assert series["source"] == "statistics"
    assert series["resolution"] == "hourly"     # normalized vocab, not HA's "hour"
    assert series["unit"] is None
