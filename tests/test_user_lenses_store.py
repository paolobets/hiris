from hiris.app.watcher.lenses import (
    validate_lens, load_lenses, save_lenses, upsert_lens, delete_lens,
)


VALID_EVENT_LENS = {
    "id": "a1a1a1a1a1a1",
    "name": "Freezer troppo caldo",
    "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.freezer_temp",
                "operator": ">", "threshold": 8, "duration_min": 15},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "Freezer troppo caldo!"},
    "severity": "warn",
}

VALID_SCHEDULE_LENS = {
    "id": "b2b2b2b2b2b2",
    "name": "Check giornaliero",
    "enabled": True,
    "trigger": {"type": "schedule", "cron": "0 9 * * *",
                "condition": {"entity_id": "sensor.away", "operator": "==", "threshold": 1}},
    "reasoning": {"enabled": True, "prompt": "Valuta la situazione"},
    "action": {"type": "service", "domain": "notify", "service": "mobile_app",
               "entity_id": "notify.mobile_app_paolo"},
    "severity": "info",
}


# ---------------------------------------------------------------------------
# validate_lens
# ---------------------------------------------------------------------------

def test_validate_well_formed_event_lens():
    cleaned = validate_lens(VALID_EVENT_LENS)
    assert cleaned is not None
    assert cleaned["id"] == "a1a1a1a1a1a1"
    assert cleaned["trigger"]["type"] == "event"
    assert cleaned["trigger"]["operator"] == ">"
    assert cleaned["action"]["type"] == "notify"
    assert cleaned["severity"] == "warn"


def test_validate_well_formed_schedule_lens():
    cleaned = validate_lens(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["trigger"]["cron"] == "0 9 * * *"
    assert cleaned["trigger"]["condition"]["operator"] == "=="
    assert cleaned["action"]["domain"] == "notify"


def test_validate_never_raises_on_garbage():
    assert validate_lens(None) is None
    assert validate_lens({}) is None
    assert validate_lens("not a dict") is None
    assert validate_lens(12345) is None
    assert validate_lens([1, 2, 3]) is None


def test_validate_rejects_invalid_operator():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "operator": "~="}}
    assert validate_lens(raw) is None


def test_validate_rejects_unknown_trigger_type():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "type": "polling"}}
    assert validate_lens(raw) is None


def test_validate_drops_unknown_extra_fields():
    raw = {**VALID_EVENT_LENS, "totally_unknown_field": "hax", "trigger":
           {**VALID_EVENT_LENS["trigger"], "extra_junk": 42}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert "totally_unknown_field" not in cleaned
    assert "extra_junk" not in cleaned["trigger"]


def test_validate_rejects_unknown_action_type():
    raw = {**VALID_EVENT_LENS, "action": {"type": "explode"}}
    assert validate_lens(raw) is None


def test_validate_rejects_unknown_severity_defaults_to_info():
    raw = {**VALID_EVENT_LENS}
    del raw["severity"]
    cleaned = validate_lens(raw)
    assert cleaned["severity"] == "info"


def test_validate_service_action_requires_domain_service_entity():
    raw = {**VALID_EVENT_LENS, "action": {"type": "service", "domain": "notify"}}
    assert validate_lens(raw) is None

    raw2 = {**VALID_EVENT_LENS, "action": {"type": "service", "domain": "notify",
             "service": "mobile_app", "entity_id": "notify.x"}}
    cleaned = validate_lens(raw2)
    assert cleaned is not None
    assert cleaned["action"]["entity_id"] == "notify.x"


def test_validate_event_trigger_requires_entity_operator_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {"type": "event", "operator": ">", "threshold": 8}}
    assert validate_lens(raw) is None  # missing entity_id

    raw2 = {**VALID_EVENT_LENS, "trigger": {"type": "event", "entity_id": "sensor.x", "threshold": 8}}
    assert validate_lens(raw2) is None  # missing operator

    raw3 = {**VALID_EVENT_LENS, "trigger": {"type": "event", "entity_id": "sensor.x", "operator": ">"}}
    assert validate_lens(raw3) is None  # missing threshold


def test_validate_schedule_trigger_requires_cron_xor_interval():
    both = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 9 * * *", "interval_min": 5}}
    assert validate_lens(both) is None  # both present -> invalid

    neither = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule"}}
    assert validate_lens(neither) is None  # neither present -> invalid

    only_interval = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 30}}
    cleaned = validate_lens(only_interval)
    assert cleaned is not None
    assert cleaned["trigger"]["interval_min"] == 30


def test_validate_truncates_name_and_prompt():
    raw = {**VALID_SCHEDULE_LENS, "name": "x" * 200,
           "reasoning": {"enabled": True, "prompt": "y" * 3000}}
    cleaned = validate_lens(raw)
    assert len(cleaned["name"]) == 80
    assert len(cleaned["reasoning"]["prompt"]) == 2000


def test_validate_reasoning_enabled_passes_through_real_bools():
    raw = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": True}}
    cleaned = validate_lens(raw)
    assert cleaned["reasoning"]["enabled"] is True

    raw2 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": False}}
    cleaned2 = validate_lens(raw2)
    assert cleaned2["reasoning"]["enabled"] is False


def test_validate_reasoning_enabled_non_bool_falls_back_to_default_false():
    # FIX 4: bool("false") is True in Python -- a client sending the STRING
    # "false" must NOT silently flip reasoning on. Any non-bool value falls
    # back to the safe default (False), it is never coerced via bool().
    raw = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": "false"}}
    cleaned = validate_lens(raw)
    assert cleaned["reasoning"]["enabled"] is False

    raw2 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": "yes"}}
    cleaned2 = validate_lens(raw2)
    assert cleaned2["reasoning"]["enabled"] is False

    raw3 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": 1}}
    cleaned3 = validate_lens(raw3)
    assert cleaned3["reasoning"]["enabled"] is False


def test_validate_enabled_real_bools_pass_through():
    raw = {**VALID_EVENT_LENS, "enabled": True}
    cleaned = validate_lens(raw)
    assert cleaned["enabled"] is True

    raw2 = {**VALID_EVENT_LENS, "enabled": False}
    cleaned2 = validate_lens(raw2)
    assert cleaned2["enabled"] is False


def test_validate_mints_id_when_missing():
    raw = {**VALID_EVENT_LENS}
    del raw["id"]
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert isinstance(cleaned["id"], str) and len(cleaned["id"]) > 0


# ---------------------------------------------------------------------------
# FIX 1: reject non-finite numbers (NaN / Infinity) everywhere _is_number is used
# ---------------------------------------------------------------------------

def test_validate_rejects_nan_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "threshold": float("nan")}}
    assert validate_lens(raw) is None


def test_validate_rejects_infinite_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "threshold": float("inf")}}
    assert validate_lens(raw) is None


def test_validate_rejects_nan_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": float("nan")}}
    assert validate_lens(raw) is None


def test_validate_rejects_infinite_interval_min():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": float("inf")}}
    assert validate_lens(raw) is None


def test_validate_rejects_nan_off_after_min():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "off_after_min": float("nan")}}
    assert validate_lens(raw) is None


def test_validate_rejects_nan_condition_threshold():
    bad_condition = {"entity_id": "sensor.away", "operator": "==", "threshold": float("nan")}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_lens(raw) is None


# ---------------------------------------------------------------------------
# FIX 2: present-but-invalid optional fields REJECT the lens (fail-closed),
# absent optionals still fall back to their default.
# ---------------------------------------------------------------------------

def test_validate_rejects_present_invalid_severity():
    raw = {**VALID_EVENT_LENS, "severity": "alerta"}
    assert validate_lens(raw) is None


def test_validate_absent_severity_still_defaults_to_info():
    raw = {**VALID_EVENT_LENS}
    del raw["severity"]
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["severity"] == "info"


def test_validate_rejects_present_invalid_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": "quindici"}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_negative_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": -5}}
    assert validate_lens(raw) is None


def test_validate_absent_duration_min_is_fine():
    raw = {**VALID_EVENT_LENS, "trigger": {k: v for k, v in VALID_EVENT_LENS["trigger"].items()
                                            if k != "duration_min"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert "duration_min" not in cleaned["trigger"]


def test_validate_rejects_present_invalid_off_after_min():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "off_after_min": "5"}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_invalid_schedule_condition():
    bad_condition = {"entity_id": "sensor.away", "operator": "~=", "threshold": 1}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_invalid_interval_min():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": "trenta"}}
    assert validate_lens(raw) is None


def test_validate_rejects_cron_present_with_invalid_interval_min():
    # Before the fix: cron present + a garbage interval_min was silently
    # accepted as "cron-only" (has_interval evaluated False for a non-number
    # without rejecting), letting the malformed interval_min through
    # unnoticed. It must now reject the whole lens instead.
    raw = {**VALID_SCHEDULE_LENS,
           "trigger": {"type": "schedule", "cron": "0 9 * * *", "interval_min": "trenta"}}
    assert validate_lens(raw) is None


# ---------------------------------------------------------------------------
# FIX 3: charset-validate domain / service / entity_id / cron (HA grammar)
# ---------------------------------------------------------------------------

def test_validate_rejects_domain_path_traversal():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "domain": "light/../.."}}
    assert validate_lens(raw) is None


def test_validate_rejects_action_entity_id_missing_dot():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "entity_id": "lightkitchen"}}
    assert validate_lens(raw) is None


def test_validate_rejects_service_invalid_charset():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "service": "mobile-app!"}}
    assert validate_lens(raw) is None


def test_validate_rejects_event_trigger_entity_id_missing_dot():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "entity_id": "sensorfreezertemp"}}
    assert validate_lens(raw) is None


def test_validate_rejects_condition_entity_id_missing_dot():
    bad_condition = {"entity_id": "sensoraway", "operator": "==", "threshold": 1}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_lens(raw) is None


def test_validate_rejects_malformed_cron():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "not a cron"}}
    assert validate_lens(raw) is None

    raw2 = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 9 * *"}}  # only 4 fields
    assert validate_lens(raw2) is None


def test_validate_accepts_well_formed_cron():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "*/5 1,2 * * 1-5"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["cron"] == "*/5 1,2 * * 1-5"


def test_validate_accepts_valid_domain_service_entity_id():
    cleaned = validate_lens(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["action"]["domain"] == "notify"
    assert cleaned["action"]["service"] == "mobile_app"
    assert cleaned["action"]["entity_id"] == "notify.mobile_app_paolo"


# ---------------------------------------------------------------------------
# FIX 4: message cap, strict nonempty str (reject whitespace-only), id re-mint
# ---------------------------------------------------------------------------

def test_validate_caps_message_length():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "message": "m" * 2000}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert len(cleaned["action"]["message"]) == 1000


def test_validate_rejects_whitespace_only_entity_id():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "entity_id": "   "}}
    assert validate_lens(raw) is None


def test_validate_remints_id_with_bad_shape():
    raw = {**VALID_EVENT_LENS, "id": "not-a-valid-id!!"}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["id"] != "not-a-valid-id!!"
    assert len(cleaned["id"]) == 12


def test_validate_keeps_id_matching_shape():
    raw = {**VALID_EVENT_LENS, "id": "0123456789ab"}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["id"] == "0123456789ab"


# ---------------------------------------------------------------------------
# load_lenses / save_lenses persistence + fail-safe
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_empty_list(tmp_path):
    assert load_lenses(str(tmp_path)) == []


def test_save_then_load_roundtrip(tmp_path):
    saved = save_lenses(str(tmp_path), [VALID_EVENT_LENS, VALID_SCHEDULE_LENS])
    assert len(saved) == 2
    reloaded = load_lenses(str(tmp_path))
    assert len(reloaded) == 2
    ids = {l["id"] for l in reloaded}
    assert ids == {"a1a1a1a1a1a1", "b2b2b2b2b2b2"}


def test_save_drops_invalid_lenses(tmp_path):
    bad = {"id": "bad1", "trigger": {"type": "nonsense"}, "action": {"type": "notify"}}
    saved = save_lenses(str(tmp_path), [VALID_EVENT_LENS, bad])
    assert len(saved) == 1
    assert saved[0]["id"] == "a1a1a1a1a1a1"


def test_load_corrupted_json_returns_empty_list(tmp_path):
    p = tmp_path / "sentinel_lenses.json"
    p.write_text("{not valid json!!!", encoding="utf-8")
    assert load_lenses(str(tmp_path)) == []


def test_load_non_list_json_returns_empty_list(tmp_path):
    p = tmp_path / "sentinel_lenses.json"
    p.write_text('{"not": "a list"}', encoding="utf-8")
    assert load_lenses(str(tmp_path)) == []


def test_save_is_atomic_no_tmp_file_left(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    assert (tmp_path / "sentinel_lenses.json").exists()
    assert not (tmp_path / "sentinel_lenses.json.tmp").exists()


# ---------------------------------------------------------------------------
# upsert_lens / delete_lens
# ---------------------------------------------------------------------------

def test_upsert_adds_new_lens(tmp_path):
    result = upsert_lens(str(tmp_path), VALID_EVENT_LENS)
    assert len(result) == 1
    assert result[0]["id"] == "a1a1a1a1a1a1"


def test_upsert_replaces_existing_lens(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    updated = {**VALID_EVENT_LENS, "name": "Nome aggiornato"}
    result = upsert_lens(str(tmp_path), updated)
    assert len(result) == 1
    assert result[0]["name"] == "Nome aggiornato"


def test_upsert_ignores_invalid_lens(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    bad = {"id": "bad1", "trigger": {"type": "nonsense"}, "action": {"type": "notify"}}
    result = upsert_lens(str(tmp_path), bad)
    assert len(result) == 1
    assert result[0]["id"] == "a1a1a1a1a1a1"


def test_delete_removes_lens(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS, VALID_SCHEDULE_LENS])
    result = delete_lens(str(tmp_path), "a1a1a1a1a1a1")
    assert len(result) == 1
    assert result[0]["id"] == "b2b2b2b2b2b2"


def test_delete_nonexistent_id_is_noop(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    result = delete_lens(str(tmp_path), "does-not-exist")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# FIX 1 (Task 2 review): string thresholds for ==/!= (state-matching lenses),
# still numeric-only for ordering operators.
# ---------------------------------------------------------------------------

def test_validate_accepts_string_threshold_for_eq_state_matching():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "person.paolo", "operator": "==", "threshold": "home"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["threshold"] == "home"


def test_validate_accepts_string_threshold_for_neq_state_matching():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "person.paolo", "operator": "!=", "threshold": "home"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["threshold"] == "home"


def test_validate_rejects_string_threshold_for_ordering_operator():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": ">", "threshold": "home"}}
    assert validate_lens(raw) is None


def test_validate_truncates_long_string_threshold_to_64_chars():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": "x" * 100}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert len(cleaned["trigger"]["threshold"]) == 64


def test_validate_rejects_whitespace_only_string_threshold_for_eq():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": "   "}}
    assert validate_lens(raw) is None


def test_validate_still_rejects_bool_threshold_for_eq():
    # bool is a subclass of int/str-adjacent trap: True/False must not leak
    # through as a threshold via either the numeric or the new string path.
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": True}}
    assert validate_lens(raw) is None


def test_validate_condition_accepts_string_threshold_for_eq():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "lock.porta", "operator": "==", "threshold": "unlocked"}}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == "unlocked"


def test_validate_condition_accepts_string_threshold_for_neq():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "person.paolo", "operator": "!=", "threshold": "home"}}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == "home"


def test_validate_condition_rejects_string_threshold_for_ordering_operator():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "sensor.away", "operator": ">", "threshold": "far"}}}
    assert validate_lens(raw) is None


def test_validate_condition_still_accepts_numeric_threshold_for_eq():
    # Numeric == must keep working after adding the string branch.
    cleaned = validate_lens(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == 1


# ---------------------------------------------------------------------------
# FIX 5 (review mediums batch 2): present-but-invalid `attribute` REJECTS the
# lens instead of being silently dropped (mirrors duration_min's own gate);
# present-but-invalid top-level `enabled` REJECTS instead of defaulting to
# True (mirrors severity's absent-vs-present convention); `interval_min` has
# a sane floor.
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_attribute():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "current_temperature"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["attribute"] == "current_temperature"


def test_validate_absent_attribute_is_fine():
    raw = {**VALID_EVENT_LENS, "trigger": {k: v for k, v in VALID_EVENT_LENS["trigger"].items()
                                            if k != "attribute"}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert "attribute" not in cleaned["trigger"]


def test_validate_rejects_present_invalid_attribute_wrong_type():
    # Before the fix: a non-string attribute was silently dropped by
    # _clean_nonempty_str (returns None) instead of rejecting the lens --
    # the trigger would then silently rebind to the entity's main state.
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": 42}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_invalid_attribute_charset():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "current-temp!"}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_invalid_attribute_whitespace_only():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "   "}}
    assert validate_lens(raw) is None


def test_validate_rejects_present_invalid_enabled():
    # Before the fix: a present-but-non-bool `enabled` (e.g. the string
    # "false", which is truthy under bool()) silently defaulted to True,
    # inverting the user's disable intent. It must now reject the lens.
    raw = {**VALID_EVENT_LENS, "enabled": "false"}
    assert validate_lens(raw) is None

    raw2 = {**VALID_EVENT_LENS, "enabled": 0}
    assert validate_lens(raw2) is None

    raw3 = {**VALID_EVENT_LENS, "enabled": "no"}
    assert validate_lens(raw3) is None


def test_validate_absent_enabled_still_defaults_to_true():
    raw = {**VALID_EVENT_LENS}
    del raw["enabled"]
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["enabled"] is True


def test_validate_rejects_interval_min_below_minimum():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 0.5}}
    assert validate_lens(raw) is None

    raw2 = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 0}}
    assert validate_lens(raw2) is None


def test_validate_accepts_interval_min_at_minimum():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 1}}
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["interval_min"] == 1
