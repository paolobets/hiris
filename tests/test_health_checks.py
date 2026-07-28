from datetime import datetime, timezone, timedelta
from hiris.app.brain import health_checks as hc


def test_entity_unavailable_flags_old_only():
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    states = [
        {"entity_id": "sensor.old", "state": "unavailable",
         "last_changed": "2026-07-20T00:00:00+00:00", "attributes": {"friendly_name": "Vecchio"}},
        {"entity_id": "sensor.recent", "state": "unavailable",
         "last_changed": "2026-07-27T23:00:00+00:00", "attributes": {}},
        {"entity_id": "sensor.ok", "state": "22.5",
         "last_changed": "2026-07-01T00:00:00+00:00", "attributes": {}},
    ]
    out = hc.check_entity_unavailable(states, now=now, days=2)
    refs = {o["source_ref"] for o in out}
    assert refs == {"entity_unavailable:sensor.old"}
    assert out[0]["fix_kind"] == "manual" and out[0]["severity"] == "warn"


def test_low_battery():
    states = [
        {"id": "sensor.door_bat", "state": "8", "name": "Porta", "unit": "%", "device_class": "battery"},
        {"id": "sensor.full", "state": "90", "name": "Pieno", "unit": "%", "device_class": "battery"},
        {"id": "sensor.temp", "state": "5", "name": "Temp", "unit": "C", "device_class": "temperature"},
    ]
    out = hc.check_low_battery(states, threshold=15)
    assert {o["source_ref"] for o in out} == {"low_battery:sensor.door_bat"}


def test_automation_broken_severity():
    autos = [
        {"entity_id": "automation.a", "state": "off", "attributes": {"friendly_name": "A"}},
        {"entity_id": "automation.b", "state": "unavailable", "attributes": {}},
        {"entity_id": "automation.c", "state": "on", "attributes": {}},
    ]
    out = {o["source_ref"]: o for o in hc.check_automation_broken(autos)}
    assert set(out) == {"automation_broken:automation.a", "automation_broken:automation.b"}
    assert out["automation_broken:automation.a"]["severity"] == "warn"
    assert out["automation_broken:automation.b"]["severity"] == "high"


def test_dangerous_domain_green_domain_and_entity():
    tiers = {"lock": "green", "cover": "yellow", "light": "green"}
    entity_tiers = {"alarm_control_panel.home": "green", "light.k": "green"}
    out = {o["source_ref"] for o in hc.check_dangerous_domain_green(tiers, entity_tiers)}
    assert out == {
        "dangerous_domain_green:domain:lock",
        "dangerous_domain_green:entity:alarm_control_panel.home",
    }


def test_entity_no_area_aggregates():
    out = hc.check_entity_no_area(["light.a", "light.b"])
    assert len(out) == 1
    assert out[0]["severity"] == "info"
    assert out[0]["evidence"]["count"] == 2
    assert out[0]["source_ref"] == "entity_no_area:all"
    assert hc.check_entity_no_area([]) == []
