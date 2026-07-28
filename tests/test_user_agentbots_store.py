import os

from hiris.app.watcher.agentbots import (
    validate_agentbot, load_agentbots, save_agentbots, upsert_agentbot, delete_agentbot,
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
# validate_agentbot
# ---------------------------------------------------------------------------

def test_validate_well_formed_event_lens():
    cleaned = validate_agentbot(VALID_EVENT_LENS)
    assert cleaned is not None
    assert cleaned["id"] == "a1a1a1a1a1a1"
    assert cleaned["trigger"]["type"] == "event"
    assert cleaned["trigger"]["operator"] == ">"
    assert cleaned["action"]["type"] == "notify"
    assert cleaned["severity"] == "warn"


def test_validate_well_formed_schedule_lens():
    cleaned = validate_agentbot(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["trigger"]["cron"] == "0 9 * * *"
    assert cleaned["trigger"]["condition"]["operator"] == "=="
    assert cleaned["action"]["domain"] == "notify"


def test_validate_never_raises_on_garbage():
    assert validate_agentbot(None) is None
    assert validate_agentbot({}) is None
    assert validate_agentbot("not a dict") is None
    assert validate_agentbot(12345) is None
    assert validate_agentbot([1, 2, 3]) is None


def test_validate_rejects_invalid_operator():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "operator": "~="}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_unknown_trigger_type():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "type": "polling"}}
    assert validate_agentbot(raw) is None


def test_validate_drops_unknown_extra_fields():
    raw = {**VALID_EVENT_LENS, "totally_unknown_field": "hax", "trigger":
           {**VALID_EVENT_LENS["trigger"], "extra_junk": 42}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert "totally_unknown_field" not in cleaned
    assert "extra_junk" not in cleaned["trigger"]


def test_validate_rejects_unknown_action_type():
    raw = {**VALID_EVENT_LENS, "action": {"type": "explode"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_unknown_severity_defaults_to_info():
    raw = {**VALID_EVENT_LENS}
    del raw["severity"]
    cleaned = validate_agentbot(raw)
    assert cleaned["severity"] == "info"


def test_validate_service_action_requires_domain_service_entity():
    raw = {**VALID_EVENT_LENS, "action": {"type": "service", "domain": "notify"}}
    assert validate_agentbot(raw) is None

    raw2 = {**VALID_EVENT_LENS, "action": {"type": "service", "domain": "notify",
             "service": "mobile_app", "entity_id": "notify.x"}}
    cleaned = validate_agentbot(raw2)
    assert cleaned is not None
    assert cleaned["action"]["entity_id"] == "notify.x"


def test_validate_event_trigger_requires_entity_operator_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {"type": "event", "operator": ">", "threshold": 8}}
    assert validate_agentbot(raw) is None  # missing entity_id

    raw2 = {**VALID_EVENT_LENS, "trigger": {"type": "event", "entity_id": "sensor.x", "threshold": 8}}
    assert validate_agentbot(raw2) is None  # missing operator

    raw3 = {**VALID_EVENT_LENS, "trigger": {"type": "event", "entity_id": "sensor.x", "operator": ">"}}
    assert validate_agentbot(raw3) is None  # missing threshold


def test_validate_schedule_trigger_requires_cron_xor_interval():
    both = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 9 * * *", "interval_min": 5}}
    assert validate_agentbot(both) is None  # both present -> invalid

    neither = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule"}}
    assert validate_agentbot(neither) is None  # neither present -> invalid

    only_interval = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 30}}
    cleaned = validate_agentbot(only_interval)
    assert cleaned is not None
    assert cleaned["trigger"]["interval_min"] == 30


def test_validate_truncates_name_and_prompt():
    raw = {**VALID_SCHEDULE_LENS, "name": "x" * 200,
           "reasoning": {"enabled": True, "prompt": "y" * 3000}}
    cleaned = validate_agentbot(raw)
    assert len(cleaned["name"]) == 80
    assert len(cleaned["reasoning"]["prompt"]) == 2000


def test_validate_reasoning_enabled_passes_through_real_bools():
    raw = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": True}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["enabled"] is True

    raw2 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": False}}
    cleaned2 = validate_agentbot(raw2)
    assert cleaned2["reasoning"]["enabled"] is False


def test_validate_reasoning_enabled_non_bool_falls_back_to_default_false():
    # FIX 4: bool("false") is True in Python -- a client sending the STRING
    # "false" must NOT silently flip reasoning on. Any non-bool value falls
    # back to the safe default (False), it is never coerced via bool().
    raw = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": "false"}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["enabled"] is False

    raw2 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": "yes"}}
    cleaned2 = validate_agentbot(raw2)
    assert cleaned2["reasoning"]["enabled"] is False

    raw3 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": 1}}
    cleaned3 = validate_agentbot(raw3)
    assert cleaned3["reasoning"]["enabled"] is False


# ---------------------------------------------------------------------------
# reasoning.model (Task 4B: per-Agentbot model, threaded end-to-end)
# ---------------------------------------------------------------------------

def test_reasoning_model_defaults_to_auto():
    raw = {**VALID_EVENT_LENS, "reasoning": {"enabled": True, "prompt": "controlla"}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["model"] == "auto"


def test_reasoning_model_explicit_preserved():
    raw = {**VALID_EVENT_LENS, "reasoning": {"enabled": True, "model": "gpt-4o"}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["model"] == "gpt-4o"


def test_reasoning_model_non_string_falls_back():
    raw = {**VALID_EVENT_LENS, "reasoning": {"enabled": True, "model": 123}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["model"] == "auto"


def test_reasoning_model_empty_string_falls_back():
    raw = {**VALID_EVENT_LENS, "reasoning": {"enabled": True, "model": ""}}
    cleaned = validate_agentbot(raw)
    assert cleaned["reasoning"]["model"] == "auto"


def test_validate_enabled_real_bools_pass_through():
    raw = {**VALID_EVENT_LENS, "enabled": True}
    cleaned = validate_agentbot(raw)
    assert cleaned["enabled"] is True

    raw2 = {**VALID_EVENT_LENS, "enabled": False}
    cleaned2 = validate_agentbot(raw2)
    assert cleaned2["enabled"] is False


def test_validate_mints_id_when_missing():
    raw = {**VALID_EVENT_LENS}
    del raw["id"]
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert isinstance(cleaned["id"], str) and len(cleaned["id"]) > 0


# ---------------------------------------------------------------------------
# FIX 1: reject non-finite numbers (NaN / Infinity) everywhere _is_number is used
# ---------------------------------------------------------------------------

def test_validate_rejects_nan_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "threshold": float("nan")}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_infinite_threshold():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "threshold": float("inf")}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_nan_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": float("nan")}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_infinite_interval_min():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": float("inf")}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_nan_off_after_min():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "off_after_min": float("nan")}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_nan_condition_threshold():
    bad_condition = {"entity_id": "sensor.away", "operator": "==", "threshold": float("nan")}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_agentbot(raw) is None


# ---------------------------------------------------------------------------
# FIX 2: present-but-invalid optional fields REJECT the Agentbot (fail-closed),
# absent optionals still fall back to their default.
# ---------------------------------------------------------------------------

def test_validate_rejects_present_invalid_severity():
    raw = {**VALID_EVENT_LENS, "severity": "alerta"}
    assert validate_agentbot(raw) is None


def test_validate_absent_severity_still_defaults_to_info():
    raw = {**VALID_EVENT_LENS}
    del raw["severity"]
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["severity"] == "info"


def test_validate_rejects_present_invalid_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": "quindici"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_negative_duration_min():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "duration_min": -5}}
    assert validate_agentbot(raw) is None


def test_validate_absent_duration_min_is_fine():
    raw = {**VALID_EVENT_LENS, "trigger": {k: v for k, v in VALID_EVENT_LENS["trigger"].items()
                                            if k != "duration_min"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert "duration_min" not in cleaned["trigger"]


def test_validate_rejects_present_invalid_off_after_min():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "off_after_min": "5"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_invalid_schedule_condition():
    bad_condition = {"entity_id": "sensor.away", "operator": "~=", "threshold": 1}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_invalid_interval_min():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": "trenta"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_cron_present_with_invalid_interval_min():
    # Before the fix: cron present + a garbage interval_min was silently
    # accepted as "cron-only" (has_interval evaluated False for a non-number
    # without rejecting), letting the malformed interval_min through
    # unnoticed. It must now reject the whole Agentbot instead.
    raw = {**VALID_SCHEDULE_LENS,
           "trigger": {"type": "schedule", "cron": "0 9 * * *", "interval_min": "trenta"}}
    assert validate_agentbot(raw) is None


# ---------------------------------------------------------------------------
# FIX 3: charset-validate domain / service / entity_id / cron (HA grammar)
# ---------------------------------------------------------------------------

def test_validate_rejects_domain_path_traversal():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "domain": "light/../.."}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_action_entity_id_missing_dot():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "entity_id": "lightkitchen"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_service_invalid_charset():
    raw = {**VALID_SCHEDULE_LENS, "action": {**VALID_SCHEDULE_LENS["action"], "service": "mobile-app!"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_event_trigger_entity_id_missing_dot():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "entity_id": "sensorfreezertemp"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_condition_entity_id_missing_dot():
    bad_condition = {"entity_id": "sensoraway", "operator": "==", "threshold": 1}
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"], "condition": bad_condition}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_malformed_cron():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "not a cron"}}
    assert validate_agentbot(raw) is None

    raw2 = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 9 * *"}}  # only 4 fields
    assert validate_agentbot(raw2) is None


def test_validate_accepts_well_formed_cron():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "*/5 1,2 * * 1-5"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["cron"] == "*/5 1,2 * * 1-5"


# ---------------------------------------------------------------------------
# Task L/1: shape-valid but VALUE-invalid cron (e.g. hour=99) must be
# rejected at creation (validate_agentbot -> None -> handlers_agentbots.py 400),
# not silently accepted at 201 only to fail later, invisibly, at
# `register_agentbot_schedules` time (server.py's CronTrigger.from_crontab).
# ---------------------------------------------------------------------------

def test_validate_rejects_value_invalid_cron_hour():
    # "0 99 * * *" passes _CRON_RE (shape: 5 numeric/`*` fields) but hour=99
    # is outside APScheduler's 0-23 range -- must reject at validate_agentbot,
    # not just fail silently later at schedule-registration time.
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 99 * * *"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_value_invalid_cron_minute():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "60 3 * * *"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_value_invalid_cron_day_of_week():
    # 8 is out of range even under the app's own 0-7 (standard crontab)
    # day_of_week convention (0/7 = Sunday).
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 3 * * 8"}}
    assert validate_agentbot(raw) is None


def test_validate_accepts_cron_day_of_week_7_as_sunday():
    # 7 is POSIX-legal for Sunday (the app's documented convention,
    # `server._translate_cron_dow`/`to_apscheduler_crontab`) even though
    # APScheduler's own day_of_week field tops out at 6 -- validate_agentbot
    # must translate before checking, not reject a legitimately-authored
    # "Sunday as 7" cron.
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "cron": "0 3 * * 7"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["cron"] == "0 3 * * 7"


def test_validate_accepts_valid_domain_service_entity_id():
    cleaned = validate_agentbot(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["action"]["domain"] == "notify"
    assert cleaned["action"]["service"] == "mobile_app"
    assert cleaned["action"]["entity_id"] == "notify.mobile_app_paolo"


# ---------------------------------------------------------------------------
# FIX 4: message cap, strict nonempty str (reject whitespace-only), id re-mint
# ---------------------------------------------------------------------------

def test_validate_caps_message_length():
    raw = {**VALID_EVENT_LENS, "action": {**VALID_EVENT_LENS["action"], "message": "m" * 2000}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert len(cleaned["action"]["message"]) == 1000


def test_validate_rejects_whitespace_only_entity_id():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"], "entity_id": "   "}}
    assert validate_agentbot(raw) is None


def test_validate_remints_id_with_bad_shape():
    raw = {**VALID_EVENT_LENS, "id": "not-a-valid-id!!"}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["id"] != "not-a-valid-id!!"
    assert len(cleaned["id"]) == 12


def test_validate_keeps_id_matching_shape():
    raw = {**VALID_EVENT_LENS, "id": "0123456789ab"}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["id"] == "0123456789ab"


# ---------------------------------------------------------------------------
# load_agentbots / save_agentbots persistence + fail-safe
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_empty_list(tmp_path):
    assert load_agentbots(str(tmp_path)) == []


def test_save_then_load_roundtrip(tmp_path):
    saved = save_agentbots(str(tmp_path), [VALID_EVENT_LENS, VALID_SCHEDULE_LENS])
    assert len(saved) == 2
    reloaded = load_agentbots(str(tmp_path))
    assert len(reloaded) == 2
    ids = {l["id"] for l in reloaded}
    assert ids == {"a1a1a1a1a1a1", "b2b2b2b2b2b2"}


def test_save_drops_invalid_lenses(tmp_path):
    bad = {"id": "bad1", "trigger": {"type": "nonsense"}, "action": {"type": "notify"}}
    saved = save_agentbots(str(tmp_path), [VALID_EVENT_LENS, bad])
    assert len(saved) == 1
    assert saved[0]["id"] == "a1a1a1a1a1a1"


def test_load_corrupted_json_returns_empty_list(tmp_path):
    p = tmp_path / "agentbots.json"
    p.write_text("{not valid json!!!", encoding="utf-8")
    assert load_agentbots(str(tmp_path)) == []


def test_load_non_list_json_returns_empty_list(tmp_path):
    p = tmp_path / "agentbots.json"
    p.write_text('{"not": "a list"}', encoding="utf-8")
    assert load_agentbots(str(tmp_path)) == []


def test_save_is_atomic_no_tmp_file_left(tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS])
    assert (tmp_path / "agentbots.json").exists()
    assert not (tmp_path / "agentbots.json.tmp").exists()


# ---------------------------------------------------------------------------
# upsert_agentbot / delete_agentbot
# ---------------------------------------------------------------------------

def test_upsert_adds_new_lens(tmp_path):
    result = upsert_agentbot(str(tmp_path), VALID_EVENT_LENS)
    assert len(result) == 1
    assert result[0]["id"] == "a1a1a1a1a1a1"


def test_upsert_replaces_existing_lens(tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS])
    updated = {**VALID_EVENT_LENS, "name": "Nome aggiornato"}
    result = upsert_agentbot(str(tmp_path), updated)
    assert len(result) == 1
    assert result[0]["name"] == "Nome aggiornato"


def test_upsert_ignores_invalid_lens(tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS])
    bad = {"id": "bad1", "trigger": {"type": "nonsense"}, "action": {"type": "notify"}}
    result = upsert_agentbot(str(tmp_path), bad)
    assert len(result) == 1
    assert result[0]["id"] == "a1a1a1a1a1a1"


def test_delete_removes_lens(tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS, VALID_SCHEDULE_LENS])
    result = delete_agentbot(str(tmp_path), "a1a1a1a1a1a1")
    assert len(result) == 1
    assert result[0]["id"] == "b2b2b2b2b2b2"


def test_delete_nonexistent_id_is_noop(tmp_path):
    save_agentbots(str(tmp_path), [VALID_EVENT_LENS])
    result = delete_agentbot(str(tmp_path), "does-not-exist")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# FIX 1 (Task 2 review): string thresholds for ==/!= (state-matching lenses),
# still numeric-only for ordering operators.
# ---------------------------------------------------------------------------

def test_validate_accepts_string_threshold_for_eq_state_matching():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "person.paolo", "operator": "==", "threshold": "home"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["threshold"] == "home"


def test_validate_accepts_string_threshold_for_neq_state_matching():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "person.paolo", "operator": "!=", "threshold": "home"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["threshold"] == "home"


def test_validate_rejects_string_threshold_for_ordering_operator():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": ">", "threshold": "home"}}
    assert validate_agentbot(raw) is None


def test_validate_truncates_long_string_threshold_to_64_chars():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": "x" * 100}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert len(cleaned["trigger"]["threshold"]) == 64


def test_validate_rejects_whitespace_only_string_threshold_for_eq():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": "   "}}
    assert validate_agentbot(raw) is None


def test_validate_still_rejects_bool_threshold_for_eq():
    # bool is a subclass of int/str-adjacent trap: True/False must not leak
    # through as a threshold via either the numeric or the new string path.
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "operator": "==", "threshold": True}}
    assert validate_agentbot(raw) is None


def test_validate_condition_accepts_string_threshold_for_eq():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "lock.porta", "operator": "==", "threshold": "unlocked"}}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == "unlocked"


def test_validate_condition_accepts_string_threshold_for_neq():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "person.paolo", "operator": "!=", "threshold": "home"}}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == "home"


def test_validate_condition_rejects_string_threshold_for_ordering_operator():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {**VALID_SCHEDULE_LENS["trigger"],
           "condition": {"entity_id": "sensor.away", "operator": ">", "threshold": "far"}}}
    assert validate_agentbot(raw) is None


def test_validate_condition_still_accepts_numeric_threshold_for_eq():
    # Numeric == must keep working after adding the string branch.
    cleaned = validate_agentbot(VALID_SCHEDULE_LENS)
    assert cleaned is not None
    assert cleaned["trigger"]["condition"]["threshold"] == 1


# ---------------------------------------------------------------------------
# FIX 5 (review mediums batch 2): present-but-invalid `attribute` REJECTS the
# Agentbot instead of being silently dropped (mirrors duration_min's own
# gate); present-but-invalid top-level `enabled` REJECTS instead of
# defaulting to True (mirrors severity's absent-vs-present convention);
# `interval_min` has a sane floor.
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_attribute():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "current_temperature"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["attribute"] == "current_temperature"


def test_validate_absent_attribute_is_fine():
    raw = {**VALID_EVENT_LENS, "trigger": {k: v for k, v in VALID_EVENT_LENS["trigger"].items()
                                            if k != "attribute"}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert "attribute" not in cleaned["trigger"]


def test_validate_rejects_present_invalid_attribute_wrong_type():
    # Before the fix: a non-string attribute was silently dropped by
    # _clean_nonempty_str (returns None) instead of rejecting the Agentbot --
    # the trigger would then silently rebind to the entity's main state.
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": 42}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_invalid_attribute_charset():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "current-temp!"}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_invalid_attribute_whitespace_only():
    raw = {**VALID_EVENT_LENS, "trigger": {**VALID_EVENT_LENS["trigger"],
           "entity_id": "climate.living", "attribute": "   "}}
    assert validate_agentbot(raw) is None


def test_validate_rejects_present_invalid_enabled():
    # Before the fix: a present-but-non-bool `enabled` (e.g. the string
    # "false", which is truthy under bool()) silently defaulted to True,
    # inverting the user's disable intent. It must now reject the Agentbot.
    raw = {**VALID_EVENT_LENS, "enabled": "false"}
    assert validate_agentbot(raw) is None

    raw2 = {**VALID_EVENT_LENS, "enabled": 0}
    assert validate_agentbot(raw2) is None

    raw3 = {**VALID_EVENT_LENS, "enabled": "no"}
    assert validate_agentbot(raw3) is None


def test_validate_absent_enabled_still_defaults_to_true():
    raw = {**VALID_EVENT_LENS}
    del raw["enabled"]
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["enabled"] is True


def test_validate_rejects_interval_min_below_minimum():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 0.5}}
    assert validate_agentbot(raw) is None

    raw2 = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 0}}
    assert validate_agentbot(raw2) is None


def test_validate_accepts_interval_min_at_minimum():
    raw = {**VALID_SCHEDULE_LENS, "trigger": {"type": "schedule", "interval_min": 1}}
    cleaned = validate_agentbot(raw)
    assert cleaned is not None
    assert cleaned["trigger"]["interval_min"] == 1


# ---------------------------------------------------------------------------
# SP-4 Fase A Task 3: one-time migration sentinel_lenses.json -> agentbots.json
# ---------------------------------------------------------------------------

def test_load_agentbots_migrates_legacy_sentinel_lenses_json(tmp_path):
    """A pre-rename `sentinel_lenses.json` sidecar is renamed in place (not
    copied) to `agentbots.json` the first time `load_agentbots` runs against
    that data_dir, and its (validated) contents are returned."""
    legacy_path = tmp_path / "sentinel_lenses.json"
    legacy_path.write_text(
        __import__("json").dumps([VALID_EVENT_LENS, VALID_SCHEDULE_LENS]), encoding="utf-8")

    result = load_agentbots(str(tmp_path))

    assert {a["id"] for a in result} == {"a1a1a1a1a1a1", "b2b2b2b2b2b2"}
    assert (tmp_path / "agentbots.json").exists()
    assert not legacy_path.exists()  # os.replace, not a copy


def test_load_agentbots_migration_is_one_time_and_idempotent(tmp_path):
    """A second `load_agentbots` call after the migration has already run
    must not raise, and must not resurrect the (now-gone) legacy file."""
    legacy_path = tmp_path / "sentinel_lenses.json"
    legacy_path.write_text(__import__("json").dumps([VALID_EVENT_LENS]), encoding="utf-8")

    first = load_agentbots(str(tmp_path))
    second = load_agentbots(str(tmp_path))

    assert first == second
    assert not legacy_path.exists()


def test_load_agentbots_does_not_migrate_when_agentbots_json_already_exists(tmp_path):
    """If `agentbots.json` already exists, a stray legacy file is left alone
    (no silent overwrite of the current store with stale legacy data)."""
    save_agentbots(str(tmp_path), [VALID_SCHEDULE_LENS])
    legacy_path = tmp_path / "sentinel_lenses.json"
    legacy_path.write_text(__import__("json").dumps([VALID_EVENT_LENS]), encoding="utf-8")

    result = load_agentbots(str(tmp_path))

    assert {a["id"] for a in result} == {"b2b2b2b2b2b2"}  # agentbots.json wins
    assert legacy_path.exists()  # untouched, not migrated over


def test_load_agentbots_no_legacy_file_no_migration_needed(tmp_path):
    """Missing legacy file and missing agentbots.json -> plain empty store,
    same as before the migration code existed (no crash, no side effects)."""
    assert load_agentbots(str(tmp_path)) == []
    assert not (tmp_path / "sentinel_lenses.json").exists()
    assert not (tmp_path / "agentbots.json").exists()


def test_load_agentbots_migration_failure_is_non_fatal(tmp_path, monkeypatch):
    """A migration failure (e.g. os.replace raising) must be swallowed and
    logged, never propagated -- the caller still gets a usable (here, empty,
    since the legacy file couldn't be moved into place) result instead of a
    crash."""
    legacy_path = tmp_path / "sentinel_lenses.json"
    legacy_path.write_text(__import__("json").dumps([VALID_EVENT_LENS]), encoding="utf-8")

    def _boom(*a, **kw):
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", _boom)

    result = load_agentbots(str(tmp_path))  # must not raise

    assert result == []  # agentbots.json still doesn't exist; legacy untouched
    assert legacy_path.exists()
