"""Task 5A: apply_brain_tuning / remove_brain_tuning -- detector-level tuning
primitive with previous-value snapshot, so undo restores the user's ORIGINAL
threshold (not just the last pre-tune value chain). See
.superpowers/sdd/task-5A-brief.md.
"""
from __future__ import annotations

import json

from hiris.app.watcher.policy import (
    apply_brain_detector,
    apply_brain_tuning,
    load_policy,
    remove_brain_detector,
    remove_brain_tuning,
    save_policy,
)


def _brain_file(dd):
    return dd / "sentinel_brain.json"


def test_apply_brain_tuning_snapshots_previous_value(tmp_path):
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                              "max_watt": 3000}}})

    delta = apply_brain_tuning(dd, "power", {"max_watt": 1600})
    assert delta == {"detector": "power"}

    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1600

    sidecar = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    assert sidecar["tunings"]["power"] == {"max_watt": 3000}


def test_second_tune_keeps_original_snapshot(tmp_path):
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                              "max_watt": 3000}}})

    apply_brain_tuning(dd, "power", {"max_watt": 1600})
    apply_brain_tuning(dd, "power", {"max_watt": 1800})

    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 1800

    sidecar = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    # Still the ORIGINAL pre-tune value, not overwritten by the second tune.
    assert sidecar["tunings"]["power"] == {"max_watt": 3000}


def test_remove_brain_tuning_restores_and_noops_second_time(tmp_path):
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                              "max_watt": 3000}}})
    apply_brain_tuning(dd, "power", {"max_watt": 1600})
    apply_brain_tuning(dd, "power", {"max_watt": 1800})

    assert remove_brain_tuning(dd, "power") is True

    pol = load_policy(dd)
    assert pol["detectors"]["power"]["max_watt"] == 3000

    sidecar = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    assert "power" not in sidecar.get("tunings", {})

    # Second call is a no-op.
    assert remove_brain_tuning(dd, "power") is False


def test_apply_brain_tuning_never_touches_entities_or_enabled_or_denied_keys(tmp_path):
    dd = str(tmp_path)
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": ["sensor.p"],
                                              "max_watt": 3000}}})

    apply_brain_tuning(dd, "power", {
        "max_watt": 1600, "enabled": False, "entities": ["sensor.evil"], "foo": "bar",
    })

    pol = load_policy(dd)
    det = pol["detectors"]["power"]
    assert det["max_watt"] == 1600
    assert det["enabled"] is True
    assert det["entities"] == ["sensor.p"]
    assert "foo" not in det

    sidecar = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    # Only the allowed, actually-touched key was snapshotted.
    assert sidecar["tunings"]["power"] == {"max_watt": 3000}


def test_retro_compat_interleaved_with_brain_detector_registry(tmp_path):
    dd = str(tmp_path)
    # A pre-existing sidecar in the OLD format (no "tunings" key at all).
    _brain_file(tmp_path).write_text(
        json.dumps({"detectors": {"power": ["sensor.x"]}}), encoding="utf-8"
    )
    save_policy(dd, {"detectors": {"power": {"enabled": True, "entities": ["sensor.x"],
                                              "max_watt": 3000}}})

    # apply_brain_tuning must not corrupt the old-format detectors registry.
    apply_brain_tuning(dd, "power", {"max_watt": 1600})
    sidecar = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    assert sidecar["detectors"]["power"] == ["sensor.x"]
    assert sidecar["tunings"]["power"] == {"max_watt": 3000}

    # apply_brain_detector/remove_brain_detector keep working after tunings exist.
    apply_brain_detector(dd, "power", "sensor.y")
    pol = load_policy(dd)
    assert "sensor.y" in pol["detectors"]["power"]["entities"]

    sidecar2 = json.loads(_brain_file(tmp_path).read_text(encoding="utf-8"))
    assert sorted(sidecar2["detectors"]["power"]) == ["sensor.x", "sensor.y"]
    # tunings snapshot from before is undisturbed by apply_brain_detector.
    assert sidecar2["tunings"]["power"] == {"max_watt": 3000}

    assert remove_brain_detector(dd, "power", "sensor.y") is True
    pol2 = load_policy(dd)
    assert "sensor.y" not in pol2["detectors"]["power"]["entities"]
    assert "sensor.x" in pol2["detectors"]["power"]["entities"]

    # And remove_brain_tuning still restores correctly afterwards.
    assert remove_brain_tuning(dd, "power") is True
    assert load_policy(dd)["detectors"]["power"]["max_watt"] == 3000
