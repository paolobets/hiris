"""PortraitStore: memoria dello stato notevole e calcolo del delta.

Convenzioni ereditate da tests/test_advisory_store.py: DB reale su tmp_path,
close() esplicito, timestamp passati espliciti per rendere i test deterministici.
"""
from hiris.app.brain.portrait_store import PortraitStore


def test_first_observation_reports_no_changes(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    changes = s.observe({"light.cucina": "on"}, now="2026-08-04T08:00:00Z")
    assert changes == []
    assert s.baseline() == {
        "light.cucina": {"state": "on", "since": "2026-08-04T08:00:00Z"}
    }
    s.close()


def test_changed_state_is_reported_and_since_resets(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.cucina": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"light.cucina": "off"}, now="2026-08-04T09:00:00Z")
    assert changes == [{
        "entity_id": "light.cucina", "was": "on", "now": "off",
        "since": "2026-08-04T09:00:00Z",
    }]
    assert s.baseline()["light.cucina"]["since"] == "2026-08-04T09:00:00Z"
    s.close()


def test_unchanged_state_keeps_original_since(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"binary_sensor.porta": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"binary_sensor.porta": "on"}, now="2026-08-04T09:00:00Z")
    assert changes == []
    assert s.baseline()["binary_sensor.porta"]["since"] == "2026-08-04T08:00:00Z"
    s.close()


def test_appeared_entity_is_a_change_with_was_none(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe(
        {"light.a": "on", "lock.porta": "locked"}, now="2026-08-04T09:00:00Z"
    )
    assert changes == [{
        "entity_id": "lock.porta", "was": None, "now": "locked",
        "since": "2026-08-04T09:00:00Z",
    }]
    s.close()


def test_disappeared_entity_is_dropped_from_baseline_without_a_change(tmp_path):
    """Un'entità sparita non è un cambiamento di stato: è un buco di lettura.
    Segnalarla produrrebbe rumore a ogni riavvio di HA."""
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on", "light.b": "on"}, now="2026-08-04T08:00:00Z")
    changes = s.observe({"light.a": "on"}, now="2026-08-04T09:00:00Z")
    assert changes == []
    assert "light.b" not in s.baseline()
    s.close()


def test_last_changes_returns_the_most_recent_observation_only(tmp_path):
    s = PortraitStore(str(tmp_path / "p.db"))
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    s.observe({"light.a": "off"}, now="2026-08-04T09:00:00Z")
    assert [c["entity_id"] for c in s.last_changes()] == ["light.a"]
    s.observe({"light.a": "off"}, now="2026-08-04T10:00:00Z")
    assert s.last_changes() == []
    s.close()


def test_survives_reopen(tmp_path):
    path = str(tmp_path / "p.db")
    s = PortraitStore(path)
    s.observe({"light.a": "on"}, now="2026-08-04T08:00:00Z")
    s.close()
    s2 = PortraitStore(path)
    changes = s2.observe({"light.a": "off"}, now="2026-08-04T09:00:00Z")
    assert changes[0]["was"] == "on"
    s2.close()
