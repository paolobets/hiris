"""TDD for Slice 5b Task 2 -- make_generic_detector.

A user lens's event trigger (already whitelist-validated by
watcher.lenses.validate_lens: operator in {>,<,>=,<=,==,!=}, threshold a
finite number, duration_min a finite non-negative number if present) must
produce a callable with the SAME signature as the built-in detectors
(`fn(entity_id, old, new, cfg, now) -> Optional[Signal]`), so the Guardian
(Task 4) can dispatch user lenses through the existing DETECTORS machinery.
"""
from hiris.app.watcher.detectors import make_generic_detector, _num
from hiris.app.watcher.signals import Signal


def _st(state, **attrs):
    return {"state": state, "attributes": attrs}


# ---------------------------------------------------------------------------
# Signature compatibility
# ---------------------------------------------------------------------------

def test_signature_matches_builtin_detectors():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 10})
    # Must be callable exactly like detect_open/detect_fridge_temp/etc.
    sig = fn("sensor.x", _st("5"), _st("15"), {}, 100.0)
    assert sig is None or isinstance(sig, Signal)


# ---------------------------------------------------------------------------
# Numeric operators: >, <, >=, <=
# ---------------------------------------------------------------------------

def test_operator_gt_fires_above_threshold():
    fn = make_generic_detector({"entity_id": "sensor.temp", "operator": ">", "threshold": 8})
    sig = fn("sensor.temp", _st("4"), _st("9.2"), {}, 1.0)
    assert sig is not None
    assert sig.entity_id == "sensor.temp"
    assert sig.evidence["value"] == 9.2


def test_operator_gt_does_not_fire_at_or_below_threshold():
    fn = make_generic_detector({"entity_id": "sensor.temp", "operator": ">", "threshold": 8})
    assert fn("sensor.temp", _st("4"), _st("8"), {}, 1.0) is None
    assert fn("sensor.temp", _st("4"), _st("6"), {}, 1.0) is None


def test_operator_lt_fires_below_threshold():
    fn = make_generic_detector({"entity_id": "sensor.batt", "operator": "<", "threshold": 10})
    sig = fn("sensor.batt", _st("50"), _st("8"), {}, 1.0)
    assert sig is not None
    assert sig.evidence["value"] == 8.0


def test_operator_lt_does_not_fire_at_or_above_threshold():
    fn = make_generic_detector({"entity_id": "sensor.batt", "operator": "<", "threshold": 10})
    assert fn("sensor.batt", _st("50"), _st("10"), {}, 1.0) is None
    assert fn("sensor.batt", _st("50"), _st("20"), {}, 1.0) is None


def test_operator_gte_fires_at_boundary():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">=", "threshold": 100})
    sig = fn("sensor.x", _st("50"), _st("100"), {}, 1.0)
    assert sig is not None


def test_operator_gte_does_not_fire_below_boundary():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">=", "threshold": 100})
    assert fn("sensor.x", _st("50"), _st("99.9"), {}, 1.0) is None


def test_operator_lte_fires_at_boundary():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "<=", "threshold": 5})
    sig = fn("sensor.x", _st("50"), _st("5"), {}, 1.0)
    assert sig is not None


def test_operator_lte_does_not_fire_above_boundary():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "<=", "threshold": 5})
    assert fn("sensor.x", _st("50"), _st("5.1"), {}, 1.0) is None


# ---------------------------------------------------------------------------
# Equality operators: ==, != -- numeric AND string (non-numeric state)
# ---------------------------------------------------------------------------

def test_operator_eq_fires_numeric_match():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "==", "threshold": 5})
    sig = fn("sensor.x", _st("1"), _st("5"), {}, 1.0)
    assert sig is not None


def test_operator_eq_does_not_fire_numeric_mismatch():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "==", "threshold": 5})
    assert fn("sensor.x", _st("1"), _st("6"), {}, 1.0) is None


def test_operator_neq_fires_numeric_mismatch():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "!=", "threshold": 5})
    sig = fn("sensor.x", _st("1"), _st("6"), {}, 1.0)
    assert sig is not None


def test_operator_neq_does_not_fire_numeric_match():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": "!=", "threshold": 5})
    assert fn("sensor.x", _st("1"), _st("5"), {}, 1.0) is None


def test_operator_eq_matches_non_numeric_state_as_string():
    # threshold is stored as a number by the lens schema, but the compared
    # *value* (state or attribute) can be non-numeric (e.g. "on"); == must
    # fall back to a string comparison instead of crashing on float(str).
    fn = make_generic_detector({"entity_id": "binary_sensor.door", "operator": "==", "threshold": "on"})
    sig = fn("binary_sensor.door", _st("off"), _st("on"), {}, 1.0)
    assert sig is not None
    assert sig.evidence["value"] == "on"


def test_operator_eq_non_numeric_mismatch_does_not_fire():
    fn = make_generic_detector({"entity_id": "binary_sensor.door", "operator": "==", "threshold": "on"})
    assert fn("binary_sensor.door", _st("on"), _st("off"), {}, 1.0) is None


def test_operator_neq_non_numeric_fires_on_mismatch():
    fn = make_generic_detector({"entity_id": "binary_sensor.door", "operator": "!=", "threshold": "on"})
    sig = fn("binary_sensor.door", _st("on"), _st("off"), {}, 1.0)
    assert sig is not None


def test_operator_ordering_on_non_numeric_value_does_not_fire_and_does_not_crash():
    fn = make_generic_detector({"entity_id": "binary_sensor.door", "operator": ">", "threshold": 5})
    assert fn("binary_sensor.door", _st("off"), _st("on"), {}, 1.0) is None


# ---------------------------------------------------------------------------
# attribute-based comparison
# ---------------------------------------------------------------------------

def test_attribute_reads_from_attributes_dict_not_state():
    fn = make_generic_detector({
        "entity_id": "climate.living", "attribute": "current_temperature",
        "operator": ">", "threshold": 25,
    })
    new = _st("heat", current_temperature=27.5)
    sig = fn("climate.living", _st("heat", current_temperature=20), new, {}, 1.0)
    assert sig is not None
    assert sig.evidence["value"] == 27.5
    assert sig.evidence["attribute"] == "current_temperature"


def test_attribute_missing_does_not_crash_and_does_not_fire():
    fn = make_generic_detector({
        "entity_id": "climate.living", "attribute": "current_temperature",
        "operator": ">", "threshold": 25,
    })
    new = _st("heat")  # no current_temperature attribute at all
    assert fn("climate.living", _st("heat"), new, {}, 1.0) is None


# ---------------------------------------------------------------------------
# duration_min -> needs_duration evidence (reuse of the guardian's gating)
# ---------------------------------------------------------------------------

def test_duration_min_present_sets_needs_duration_evidence():
    fn = make_generic_detector({
        "entity_id": "sensor.temp", "operator": ">", "threshold": 8, "duration_min": 15,
    })
    sig = fn("sensor.temp", _st("4"), _st("9"), {}, 1.0)
    assert sig is not None
    assert sig.evidence["needs_duration"] is True
    assert sig.evidence["threshold_min"] == 15


def test_duration_min_absent_does_not_set_needs_duration():
    fn = make_generic_detector({"entity_id": "sensor.temp", "operator": ">", "threshold": 8})
    sig = fn("sensor.temp", _st("4"), _st("9"), {}, 1.0)
    assert sig is not None
    assert "needs_duration" not in sig.evidence


# ---------------------------------------------------------------------------
# no-crash on odd input
# ---------------------------------------------------------------------------

def test_new_state_none_does_not_crash():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    assert fn("sensor.x", None, None, {}, 1.0) is None


def test_new_state_not_a_dict_does_not_crash():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    assert fn("sensor.x", None, "garbage", {}, 1.0) is None


def test_new_state_unavailable_does_not_fire():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    assert fn("sensor.x", _st("4"), _st("unavailable"), {}, 1.0) is None


def test_cfg_none_does_not_crash():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    sig = fn("sensor.x", None, _st("9"), None, 1.0)
    assert sig is not None
    assert sig.severity == "warn"  # safe default when cfg has no severity


# ---------------------------------------------------------------------------
# severity + kind
# ---------------------------------------------------------------------------

def test_severity_read_from_cfg():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    sig = fn("sensor.x", None, _st("9"), {"severity": "critico"}, 1.0)
    assert sig.severity == "critico"


def test_kind_identifies_user_lens():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    sig = fn("sensor.x", None, _st("9"), {}, 1.0)
    assert sig.kind == "user_lens"


def test_ts_is_the_now_argument():
    fn = make_generic_detector({"entity_id": "sensor.x", "operator": ">", "threshold": 8})
    sig = fn("sensor.x", None, _st("9"), {}, 12345.5)
    assert sig.ts == 12345.5


# ---------------------------------------------------------------------------
# reuse of _num
# ---------------------------------------------------------------------------

def test_reuses_num_helper_for_unavailable_and_unknown():
    assert _num(_st("unavailable")) is None
    assert _num(_st("unknown")) is None
