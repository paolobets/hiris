import json
import math

import pytest

from hiris.app.watcher.policy import (
    load_policy, save_policy, validate_detector_value, PolicyValidationError,
    DEFAULT_POLICY, SENTINEL_DETECTORS,
)

def test_load_defaults_when_absent(tmp_path):
    pol = load_policy(str(tmp_path))
    assert pol["detectors"]["battery"]["enabled"] is False
    assert pol["detectors"]["opening"]["open_minutes"] == 10

def test_save_then_load_roundtrip(tmp_path):
    body = {"detectors": {"battery": {"enabled": True, "entities": ["sensor.b"], "min_pct": 15}}}
    clean = save_policy(str(tmp_path), body)
    assert clean["detectors"]["battery"]["enabled"] is True
    reloaded = load_policy(str(tmp_path))
    assert reloaded["detectors"]["battery"]["entities"] == ["sensor.b"]
    # detector non citato resta a default
    assert reloaded["detectors"]["power"]["enabled"] is False

def test_save_ignores_unknown_detector(tmp_path):
    clean = save_policy(str(tmp_path), {"detectors": {"bogus": {"enabled": True}}})
    assert "bogus" not in clean["detectors"]

def test_detectors_metadata_complete():
    ids = {d["id"] for d in SENTINEL_DETECTORS}
    assert ids == {"opening", "fridge_temp", "power", "battery"}

def test_situations_defaults_present():
    assert "situations" in DEFAULT_POLICY
    assert DEFAULT_POLICY["situations"]["hot_and_away"]["enabled"] is False
    assert DEFAULT_POLICY["situations"]["ronda_minutes"] == 15

def test_save_situations_roundtrip(tmp_path):
    body = {"situations": {"presence_entity": "person.p",
            "hot_and_away": {"enabled": True, "valve_entity": "switch.irr", "run_minutes": 7}}}
    clean = save_policy(str(tmp_path), body)
    assert clean["situations"]["hot_and_away"]["enabled"] is True
    reloaded = load_policy(str(tmp_path))
    assert reloaded["situations"]["hot_and_away"]["run_minutes"] == 7
    assert reloaded["situations"]["away_alarm_off"]["enabled"] is False  # default preservato

def test_preparation_defaults():
    assert "preparation" in DEFAULT_POLICY
    assert DEFAULT_POLICY["preparation"]["evening_arrival"]["enabled"] is False
    assert DEFAULT_POLICY["preparation"]["evening_arrival"]["after_hour"] == 18

def test_save_preparation_roundtrip(tmp_path):
    body = {"preparation": {"evening_arrival": {"enabled": True, "target_entity": "scene.r", "after_hour": 19}}}
    clean = save_policy(str(tmp_path), body)
    assert clean["preparation"]["evening_arrival"]["enabled"] is True
    reloaded = load_policy(str(tmp_path))
    assert reloaded["preparation"]["evening_arrival"]["target_entity"] == "scene.r"
    assert reloaded["preparation"]["evening_arrival"]["sun_entity"] == "sun.sun"  # default preservato


# --- Review C/#8: type + range validation ----------------------------------

def test_validate_detector_value_type_and_range():
    assert validate_detector_value("enabled", True) is True
    assert validate_detector_value("enabled", "true") is False   # string, not bool
    assert validate_detector_value("enabled", 1) is False        # int, not bool

    assert validate_detector_value("entities", ["light.x"]) is True
    assert validate_detector_value("entities", []) is True
    assert validate_detector_value("entities", "light.x") is False   # string, not list
    assert validate_detector_value("entities", [1, 2]) is False      # not all str

    assert validate_detector_value("max_watt", 2500) is True
    assert validate_detector_value("max_watt", "high") is False     # non-numeric
    assert validate_detector_value("max_watt", True) is False       # bool masquerades as int
    assert validate_detector_value("max_watt", math.nan) is False   # NaN
    assert validate_detector_value("max_watt", math.inf) is False   # inf
    assert validate_detector_value("max_watt", 999999999) is False  # out of range -> reject at this layer
    assert validate_detector_value("max_watt", 50) is False         # below _PARAM_BOUNDS lower bound


def test_save_rejects_string_max_watt(tmp_path):
    with pytest.raises(PolicyValidationError):
        save_policy(str(tmp_path), {"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                                             "max_watt": "high"}}})
    # Nothing persisted -- a subsequent load still sees defaults.
    pol = load_policy(str(tmp_path))
    assert pol["detectors"]["power"]["max_watt"] == 3000
    assert pol["detectors"]["power"]["enabled"] is False


def test_save_rejects_string_entities(tmp_path):
    with pytest.raises(PolicyValidationError):
        save_policy(str(tmp_path), {"detectors": {"power": {"enabled": True, "entities": "light.x"}}})


def test_save_rejects_nan_threshold(tmp_path):
    with pytest.raises(PolicyValidationError):
        save_policy(str(tmp_path), {"detectors": {"power": {"max_watt": math.nan}}})


def test_save_accepts_valid_numeric_threshold(tmp_path):
    clean = save_policy(str(tmp_path), {"detectors": {"power": {"enabled": True,
                                                                 "entities": ["sensor.p"],
                                                                 "max_watt": 2500}}})
    assert clean["detectors"]["power"]["max_watt"] == 2500
    reloaded = load_policy(str(tmp_path))
    assert reloaded["detectors"]["power"]["max_watt"] == 2500


def test_load_falls_back_to_default_on_corrupt_stored_value(tmp_path):
    """load_policy must never crash on an already-corrupt file (e.g. hand-
    edited, or written by a version predating validation) -- a malformed key
    falls back to the DEFAULT_POLICY value instead."""
    policy_file = tmp_path / "sentinel_policy.json"
    corrupt = json.loads(json.dumps(DEFAULT_POLICY))
    corrupt["detectors"]["power"]["max_watt"] = "not-a-number"
    corrupt["detectors"]["power"]["enabled"] = True
    corrupt["detectors"]["power"]["entities"] = ["sensor.legit"]
    policy_file.write_text(json.dumps(corrupt), encoding="utf-8")

    pol = load_policy(str(tmp_path))
    assert pol["detectors"]["power"]["max_watt"] == 3000  # default, corrupt value dropped
    assert pol["detectors"]["power"]["enabled"] is True    # valid keys still loaded
    assert pol["detectors"]["power"]["entities"] == ["sensor.legit"]
