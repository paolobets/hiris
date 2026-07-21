from hiris.app.watcher.policy import load_policy, save_policy, DEFAULT_POLICY, SENTINEL_DETECTORS

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
