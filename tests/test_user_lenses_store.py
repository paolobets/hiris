from hiris.app.watcher.lenses import (
    validate_lens, load_lenses, save_lenses, upsert_lens, delete_lens,
)


VALID_EVENT_LENS = {
    "id": "abc123",
    "name": "Freezer troppo caldo",
    "enabled": True,
    "trigger": {"type": "event", "entity_id": "sensor.freezer_temp",
                "operator": ">", "threshold": 8, "duration_min": 15},
    "reasoning": {"enabled": False},
    "action": {"type": "notify", "message": "Freezer troppo caldo!"},
    "severity": "warn",
}

VALID_SCHEDULE_LENS = {
    "id": "sched1",
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
    assert cleaned["id"] == "abc123"
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


def test_validate_coerces_reasoning_enabled_to_bool():
    raw = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": "yes"}}
    cleaned = validate_lens(raw)
    assert cleaned["reasoning"]["enabled"] is True

    raw2 = {**VALID_SCHEDULE_LENS, "reasoning": {"enabled": 0}}
    cleaned2 = validate_lens(raw2)
    assert cleaned2["reasoning"]["enabled"] is False


def test_validate_mints_id_when_missing():
    raw = {**VALID_EVENT_LENS}
    del raw["id"]
    cleaned = validate_lens(raw)
    assert cleaned is not None
    assert isinstance(cleaned["id"], str) and len(cleaned["id"]) > 0


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
    assert ids == {"abc123", "sched1"}


def test_save_drops_invalid_lenses_from_batch():
    pass  # covered by test_save_drops_invalid below with tmp_path


def test_save_drops_invalid_lenses(tmp_path):
    bad = {"id": "bad1", "trigger": {"type": "nonsense"}, "action": {"type": "notify"}}
    saved = save_lenses(str(tmp_path), [VALID_EVENT_LENS, bad])
    assert len(saved) == 1
    assert saved[0]["id"] == "abc123"


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
    assert result[0]["id"] == "abc123"


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
    assert result[0]["id"] == "abc123"


def test_delete_removes_lens(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS, VALID_SCHEDULE_LENS])
    result = delete_lens(str(tmp_path), "abc123")
    assert len(result) == 1
    assert result[0]["id"] == "sched1"


def test_delete_nonexistent_id_is_noop(tmp_path):
    save_lenses(str(tmp_path), [VALID_EVENT_LENS])
    result = delete_lens(str(tmp_path), "does-not-exist")
    assert len(result) == 1
