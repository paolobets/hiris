from hiris.app.history.store import HistoryStore
from hiris.app.history.capture import HistoryCapture
from hiris.app.api.handlers_history_policy import load_policy


def test_capture_appends_into_real_store(tmp_path):
    s = HistoryStore(str(tmp_path / "history.db"))
    cap = HistoryCapture(s, {"domains": {"climate": True}})
    cap.on_state_changed({"entity_id": "climate.x",
                          "new_state": {"state": "21.0",
                                        "last_changed": "2026-06-20T10:00:00+00:00"}})
    out = s.query("climate.x", days=7, today="2026-06-20")
    assert out is not None and out["buckets"][0]["mean"] == 21.0


def test_compact_callable_with_policy_retention(tmp_path):
    s = HistoryStore(str(tmp_path / "history.db"))
    s.append("climate.x", "2026-06-10T10:00:00+00:00", "10.0")
    pol = load_policy(str(tmp_path))
    s.compact(today="2026-06-20", retention_days=pol["retention_days"])
    assert s.has_entity("climate.x") is True
