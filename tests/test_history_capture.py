from hiris.app.history.capture import HistoryCapture


class _FakeStore:
    def __init__(self):
        self.appended = []
    def append(self, entity_id, ts, state):
        self.appended.append((entity_id, ts, state))


def _evt(entity_id, state, last_changed="2026-06-26T10:00:00+00:00"):
    return {"entity_id": entity_id,
            "new_state": {"entity_id": entity_id, "state": state,
                          "last_changed": last_changed}}


def test_captures_only_policy_matching_entities():
    store = _FakeStore()
    cap = HistoryCapture(store, {"domains": {"climate": True}, "entities": [],
                                 "exclude": [], "retention_days": 90})
    cap.on_state_changed(_evt("climate.salotto", "21.0"))
    cap.on_state_changed(_evt("light.cucina", "on"))
    assert store.appended == [("climate.salotto", "2026-06-26T10:00:00+00:00", "21.0")]


def test_ignores_missing_new_state_and_never_raises():
    store = _FakeStore()
    cap = HistoryCapture(store, {"domains": {"sensor": True}})
    cap.on_state_changed({"entity_id": "sensor.x", "new_state": None})
    cap.on_state_changed({})
    assert store.appended == []


def test_set_policy_hot_reload():
    store = _FakeStore()
    cap = HistoryCapture(store, {})
    cap.on_state_changed(_evt("climate.x", "1"))
    cap.set_policy({"domains": {"climate": True}})
    cap.on_state_changed(_evt("climate.x", "2"))
    assert store.appended == [("climate.x", "2026-06-26T10:00:00+00:00", "2")]
