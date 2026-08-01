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


# --- Controlli di sistema (Supervisor) -------------------------------------

def test_addon_down_stato_e_severita():
    addons = [
        {"slug": "core_mosquitto", "name": "Mosquitto", "state": "started"},
        {"slug": "a0d7b954_nodered", "name": "Node-RED", "state": "error"},
        {"slug": "core_samba", "name": "Samba", "state": "stopped"},
        {"slug": "core_ssh", "name": "SSH", "state": "unknown"},
        {"slug": "core_zwave", "name": "Z-Wave", "state": "startup"},
    ]
    out = {o["source_ref"]: o for o in hc.check_addon_down(addons)}
    assert set(out) == {"addon_down:a0d7b954_nodered", "addon_down:core_samba"}
    rotto = out["addon_down:a0d7b954_nodered"]
    fermo = out["addon_down:core_samba"]
    assert rotto["severity"] == "high"
    assert fermo["severity"] == "warn"
    assert rotto["check_id"] == "addon_down" and rotto["fix_kind"] == "manual"
    assert fermo["evidence"] == {"slug": "core_samba", "state": "stopped"}
    assert "Samba" in fermo["title"]


def test_addon_down_idempotente_e_input_malformato():
    addons = [{"slug": "core_samba", "name": "Samba", "state": "stopped"}]
    primo = hc.check_addon_down(addons)
    secondo = hc.check_addon_down(addons)
    assert [o["source_ref"] for o in primo] == [o["source_ref"] for o in secondo]
    assert hc.check_addon_down(None) == []
    assert hc.check_addon_down([]) == []
    # Voci non-dict, senza slug o senza stato non devono sollevare
    assert hc.check_addon_down(["non un dict", {}, {"state": "error"},
                                {"slug": "x"}, None]) == []


def test_disk_space_soglie():
    alto = hc.check_disk_space({"disk_total": 100, "disk_used": 95, "disk_free": 5})
    assert len(alto) == 1
    assert alto[0]["severity"] == "high"
    assert alto[0]["check_id"] == "disk_space"
    assert alto[0]["source_ref"] == "disk_space:host"
    assert alto[0]["evidence"]["free_pct"] == 5.0
    assert alto[0]["fix_kind"] == "manual"

    avviso = hc.check_disk_space({"disk_total": 200, "disk_used": 170, "disk_free": 30})
    assert len(avviso) == 1 and avviso[0]["severity"] == "warn"
    assert avviso[0]["source_ref"] == "disk_space:host"

    # Esattamente sulle soglie: "sotto" e' stretto
    assert hc.check_disk_space({"disk_total": 100, "disk_free": 20}) == []
    assert hc.check_disk_space({"disk_total": 100, "disk_free": 10})[0]["severity"] == "warn"
    # Ampiamente sopra: nessuna segnalazione
    assert hc.check_disk_space({"disk_total": 100, "disk_used": 40, "disk_free": 60}) == []


def test_disk_space_input_malformato():
    assert hc.check_disk_space(None) == []
    assert hc.check_disk_space({}) == []
    assert hc.check_disk_space("non un dict") == []
    assert hc.check_disk_space({"disk_total": 0, "disk_free": 0}) == []
    assert hc.check_disk_space({"disk_total": "x", "disk_free": "y"}) == []
    assert hc.check_disk_space({"disk_total": 100, "disk_free": -1}) == []
    # disk_free assente si ricava da totale - usato
    ricavato = hc.check_disk_space({"disk_total": 100, "disk_used": 96})
    assert len(ricavato) == 1 and ricavato[0]["severity"] == "high"


def test_updates_available_voce_unica_aggregata():
    updates = [{"name": f"Add-on {i}", "update_type": "addon", "version_latest": "1.0"}
               for i in range(12)]
    out = hc.check_updates_available(updates)
    assert len(out) == 1
    voce = out[0]
    assert voce["severity"] == "info"
    assert voce["check_id"] == "updates_available"
    assert voce["source_ref"] == "updates_available:all"
    assert voce["evidence"]["count"] == 12
    assert len(voce["evidence"]["items"]) == hc.MAX_UPDATES_EVIDENZA
    assert hc.MAX_UPDATES_EVIDENZA < 12


def test_updates_available_input_vuoto_o_malformato():
    assert hc.check_updates_available(None) == []
    assert hc.check_updates_available([]) == []
    assert hc.check_updates_available(["x", None]) == []
    out = hc.check_updates_available(["x", {"name": "Core", "update_type": "core"}])
    assert len(out) == 1 and out[0]["evidence"]["count"] == 1
    assert out[0]["title"] == "1 aggiornamento disponibile"
