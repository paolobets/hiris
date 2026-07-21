from hiris.app.watcher.signals import Signal, WakeEvent, Decision, wake_from_signal

def test_wake_from_signal_copies_fields():
    sig = Signal(kind="fridge_temp", entity_id="sensor.frigo", severity="warn",
                 evidence={"temp": 9.1, "minutes": 33}, ts=1000.0)
    we = wake_from_signal(sig)
    assert isinstance(we, WakeEvent)
    assert we.signal_kind == "fridge_temp"
    assert we.entity_id == "sensor.frigo"
    assert we.severity_hint == "warn"
    assert we.evidence == {"temp": 9.1, "minutes": 33}
    assert we.ts == 1000.0

def test_decision_defaults_action_none():
    d = Decision(verdict="anomalia", severity="warn", message="x")
    assert d.action is None
