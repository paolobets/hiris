import math

from hiris.app.brain.learned_thresholds import LEARNABLE, learned_threshold


def test_learnable_v1_contains_only_power():
    assert set(LEARNABLE.keys()) == {"power"}
    assert callable(LEARNABLE["power"])


def test_power_baseline_mean_800_current_3000_applies_new_threshold():
    baseline = {"mean": 800.0, "on_hours": None, "n_days": 14}
    current_cfg = {"max_watt": 3000}
    out = learned_threshold("power", baseline, current_cfg)
    assert out == {"max_watt": 1600}


def test_power_below_min_days_returns_none():
    baseline = {"mean": 800.0, "on_hours": None, "n_days": 5}
    current_cfg = {"max_watt": 3000}
    assert learned_threshold("power", baseline, current_cfg) is None


def test_power_huge_mean_clamps_to_upper_bound():
    # raw = 1e9 * 2 = 2e9, clamp upper = min(3000*3, 20000) = 9000
    baseline = {"mean": 1_000_000_000.0, "on_hours": None, "n_days": 14}
    current_cfg = {"max_watt": 3000}
    out = learned_threshold("power", baseline, current_cfg)
    assert out == {"max_watt": 9000}


def test_power_diff_within_hysteresis_returns_none():
    # new = 1600 * 2 = 3200, within [1500, 9000], but diff vs 3000 is 6.7% (<=15%)
    baseline = {"mean": 1600.0, "on_hours": None, "n_days": 14}
    current_cfg = {"max_watt": 3000}
    assert learned_threshold("power", baseline, current_cfg) is None


def test_non_learnable_detector_returns_none():
    baseline = {"mean": 800.0, "on_hours": None, "n_days": 14}
    assert learned_threshold("humidity", baseline, {"max_watt": 3000}) is None


def test_power_uses_default_max_watt_when_absent():
    baseline = {"mean": 800.0, "on_hours": None, "n_days": 14}
    out = learned_threshold("power", baseline, {})
    assert out == {"max_watt": 1600}


def test_power_respects_absolute_floor():
    # current_max very small so current_max*3 stays below abs floor -> lower bound is abs floor 100
    baseline = {"mean": 1.0, "on_hours": None, "n_days": 14}
    current_cfg = {"max_watt": 40}
    out = learned_threshold("power", baseline, current_cfg)
    # raw new = 2, clamp lower = max(40*0.5, 100) = 100; diff vs 40 = 150% -> applies
    assert out == {"max_watt": 100}


def test_power_respects_absolute_cap():
    baseline = {"mean": 50000.0, "on_hours": None, "n_days": 14}
    current_cfg = {"max_watt": 15000}
    out = learned_threshold("power", baseline, current_cfg)
    # raw new = 100000, clamp upper = min(45000, 20000) = 20000
    assert out == {"max_watt": 20000}


def test_power_mean_nan_returns_none():
    baseline = {"mean": float("nan"), "on_hours": None, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}) is None


def test_power_mean_inf_returns_none():
    baseline = {"mean": float("inf"), "on_hours": None, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}) is None


def test_power_mean_none_returns_none():
    baseline = {"mean": None, "on_hours": None, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}) is None


def test_power_mean_zero_or_negative_returns_none():
    assert learned_threshold("power", {"mean": 0.0, "n_days": 14}, {}) is None
    assert learned_threshold("power", {"mean": -5.0, "n_days": 14}, {}) is None


def test_power_n_days_missing_returns_none():
    baseline = {"mean": 800.0, "on_hours": None}
    assert learned_threshold("power", baseline, {"max_watt": 3000}) is None


def test_power_n_days_none_returns_none():
    baseline = {"mean": 800.0, "on_hours": None, "n_days": None}
    assert learned_threshold("power", baseline, {"max_watt": 3000}) is None


def test_factor_nan_returns_none():
    baseline = {"mean": 800.0, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}, factor=float("nan")) is None


def test_factor_inf_returns_none():
    baseline = {"mean": 800.0, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}, factor=float("inf")) is None


def test_factor_non_positive_returns_none():
    baseline = {"mean": 800.0, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 3000}, factor=0) is None
    assert learned_threshold("power", baseline, {"max_watt": 3000}, factor=-2.0) is None


def test_current_cfg_none_falls_back_to_default_and_does_not_crash():
    baseline = {"mean": 800.0, "n_days": 14}
    out = learned_threshold("power", baseline, None)
    assert out == {"max_watt": 1600}


def test_current_cfg_not_a_dict_does_not_crash():
    baseline = {"mean": 800.0, "n_days": 14}
    out = learned_threshold("power", baseline, "garbage")
    assert out == {"max_watt": 1600}


def test_max_watt_nan_in_current_cfg_falls_back_to_default():
    baseline = {"mean": 800.0, "n_days": 14}
    out = learned_threshold("power", baseline, {"max_watt": float("nan")})
    assert out == {"max_watt": 1600}


def test_max_watt_zero_or_negative_in_current_cfg_falls_back_to_default():
    baseline = {"mean": 800.0, "n_days": 14}
    assert learned_threshold("power", baseline, {"max_watt": 0}) == {"max_watt": 1600}
    assert learned_threshold("power", baseline, {"max_watt": -100}) == {"max_watt": 1600}


def test_baseline_none_does_not_crash():
    assert learned_threshold("power", None, {"max_watt": 3000}) is None


def test_baseline_missing_mean_key_does_not_crash():
    assert learned_threshold("power", {"n_days": 14}, {"max_watt": 3000}) is None


def test_result_never_nan_or_inf():
    baseline = {"mean": float("inf"), "n_days": 14}
    out = learned_threshold("power", baseline, {"max_watt": 3000})
    assert out is None or math.isfinite(out["max_watt"])
