from hiris.app.watcher.situations import (
    situation_hot_and_away, situation_away_alarm_off, SITUATIONS)

def _snap(present=None, temp=None, rain=None, alarm=None):
    return {"presence": {"present": present}, "outside_temp_c": temp,
            "weather": {"rain_soon": rain}, "alarm_state": alarm}

def test_hot_and_away_fires():
    cfg = {"hot_threshold_c": 32, "valve_entity": "switch.irr", "run_minutes": 5, "skip_if_rain": True}
    sig = situation_hot_and_away(_snap(present=False, temp=34, rain=False), cfg)
    assert sig and sig.kind == "hot_and_away"
    assert sig.suggested_action["entity_id"] == "switch.irr"
    assert sig.suggested_action["off_after_min"] == 5

def test_hot_and_away_skips_if_rain():
    cfg = {"hot_threshold_c": 32, "valve_entity": "switch.irr", "run_minutes": 5, "skip_if_rain": True}
    assert situation_hot_and_away(_snap(present=False, temp=34, rain=True), cfg) is None

def test_hot_and_away_needs_absence_and_heat():
    cfg = {"hot_threshold_c": 32, "valve_entity": "switch.irr", "run_minutes": 5}
    assert situation_hot_and_away(_snap(present=True, temp=34), cfg) is None
    assert situation_hot_and_away(_snap(present=False, temp=20), cfg) is None
    assert situation_hot_and_away(_snap(present=False, temp=None), cfg) is None  # dato mancante

def test_away_alarm_off_fires():
    sig = situation_away_alarm_off(_snap(present=False, alarm="disarmed"),
                                   {"disarmed_states": ["disarmed"]})
    assert sig and sig.kind == "away_alarm_off" and sig.suggested_action is None

def test_away_alarm_off_no_fire_when_present_or_armed():
    cfg = {"disarmed_states": ["disarmed"]}
    assert situation_away_alarm_off(_snap(present=True, alarm="disarmed"), cfg) is None
    assert situation_away_alarm_off(_snap(present=False, alarm="armed_away"), cfg) is None

def test_registry():
    assert set(SITUATIONS) == {"hot_and_away", "away_alarm_off"}
