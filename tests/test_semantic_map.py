import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock
from hiris.app.proxy.semantic_map import SemanticMap, classify_by_rules

def test_classify_by_rules_energy_meter():
    assert classify_by_rules("sensor.shellyem3_xxx_power") == "energy_meter"
    assert classify_by_rules("sensor.casa_energy_consumption") == "energy_meter"
    assert classify_by_rules("sensor.main_watt") == "energy_meter"

def test_classify_by_rules_solar():
    assert classify_by_rules("sensor.solaredge_pv_power") == "solar_production"
    assert classify_by_rules("sensor.solar_output") == "solar_production"

def test_classify_by_rules_grid():
    assert classify_by_rules("sensor.tibber_grid_import") == "grid_import"
    assert classify_by_rules("sensor.rete_export") == "grid_import"

def test_classify_by_rules_climate():
    assert classify_by_rules("climate.heatpump_salotto") == "climate_sensor"
    assert classify_by_rules("sensor.aqara_temperature") == "climate_sensor"

def test_classify_by_rules_lighting():
    assert classify_by_rules("light.salotto") == "lighting"
    assert classify_by_rules("light.cucina_led") == "lighting"

def test_classify_by_rules_presence():
    assert classify_by_rules("binary_sensor.motion_salotto") == "presence"
    assert classify_by_rules("binary_sensor.presence_home") == "presence"

def test_classify_by_rules_door_window():
    assert classify_by_rules("binary_sensor.door_front") == "door_window"
    assert classify_by_rules("binary_sensor.window_bedroom") == "door_window"

def test_classify_by_rules_appliance():
    assert classify_by_rules("switch.lavatrice") == "appliance"
    assert classify_by_rules("switch.lavastoviglie_cucina") == "appliance"

def test_classify_by_rules_diagnostic():
    assert classify_by_rules("sensor.shelly_cfgchanged") == "diagnostic"
    assert classify_by_rules("update.hiris_firmware") == "diagnostic"

def test_classify_by_rules_unknown():
    assert classify_by_rules("sensor.opaque_34945479_ch1_weird") is None


def test_semantic_map_get_category_empty():
    m = SemanticMap(data_dir=tempfile.gettempdir())
    assert m.get_category("energy_meter") == []


def test_semantic_map_add_and_get_category():
    m = SemanticMap(data_dir=tempfile.gettempdir())
    m._add_entity("sensor.power_main", "energy_meter", "Contatore principale", classified_by="rules")
    assert "sensor.power_main" in m.get_category("energy_meter")


def test_add_entity_reclassification_removes_old_category(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("sensor.x", "unknown", "X", classified_by="pending")
    assert "sensor.x" in m.get_category("unknown")
    m._add_entity("sensor.x", "energy_meter", "X meter", classified_by="claude")
    assert "sensor.x" in m.get_category("energy_meter")
    assert "sensor.x" not in m.get_category("unknown")


def test_semantic_map_save_load_roundtrip(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Luce salotto", classified_by="rules")
    m._add_entity("sensor.power_main", "energy_meter", "Contatore", classified_by="rules")
    m.save()

    m2 = SemanticMap(data_dir=str(tmp_path))
    m2.load()
    assert "light.salotto" in m2.get_category("lighting")
    assert "sensor.power_main" in m2.get_category("energy_meter")


def test_semantic_map_get_all_entity_ids(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.a", "lighting", "A", classified_by="rules")
    m._add_entity("sensor.b", "energy_meter", "B", classified_by="rules")
    ids = m.get_all_entity_ids()
    assert "light.a" in ids
    assert "sensor.b" in ids


def _make_cache(entity_ids: list[str]):
    """Create a minimal mock EntityCache."""
    cache = MagicMock()
    minimal = [{"id": eid, "state": "on", "name": eid.split(".")[-1], "unit": ""} for eid in entity_ids]
    cache.get_all_useful.return_value = minimal
    return cache


def test_build_from_cache_classifies_known(tmp_path):
    cache = _make_cache([
        "light.salotto",
        "sensor.shellyem3_xxx_power",
        "climate.heatpump",
    ])
    m = SemanticMap(data_dir=str(tmp_path))
    new_ids = m.build_from_cache(cache)
    assert "light.salotto" in m.get_category("lighting")
    assert "sensor.shellyem3_xxx_power" in m.get_category("energy_meter")
    assert "climate.heatpump" in m.get_category("climate_sensor")


def test_build_from_cache_returns_unknown_for_ambiguous(tmp_path):
    cache = _make_cache(["sensor.opaque_34945479_ch1_weird"])
    m = SemanticMap(data_dir=str(tmp_path))
    new_ids = m.build_from_cache(cache)
    assert "sensor.opaque_34945479_ch1_weird" in new_ids  # returned as needs-LLM


def test_build_from_cache_skips_existing(tmp_path):
    cache = _make_cache(["light.salotto", "sensor.new_sensor_power"])
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Luce", classified_by="rules")
    new_ids = m.build_from_cache(cache)
    # light.salotto already in map — not returned as new
    assert "light.salotto" not in new_ids
    # new sensor is classified by rules (power pattern), not ambiguous
    assert "sensor.new_sensor_power" not in new_ids


def test_on_entity_added_classifies_by_rules(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m.on_entity_added("light.new_light", {"friendly_name": "New Light"})
    assert "light.new_light" in m.get_category("lighting")


def test_on_entity_added_marks_unknown_if_ambiguous(tmp_path):
    m = SemanticMap(data_dir=str(tmp_path))
    m.on_entity_added("sensor.opaque_xyz_weird", {})
    assert "sensor.opaque_xyz_weird" in m.get_category("unknown")


def _make_state(state: str = "on", attrs: dict | None = None) -> dict:
    return {"state": state, "attributes": attrs or {}}


def test_get_prompt_snippet_contains_sections(tmp_path):
    state_map = {
        "climate.heatpump": _make_state("heat", {"current_temperature": 20.5, "temperature": 21.0, "hvac_action": "heating"}),
        "binary_sensor.presence_home": _make_state("home"),
        "sensor.shellyem3_power": _make_state("1200"),
        "light.salotto": _make_state("on"),
    }
    cache = _make_cache([
        "sensor.shellyem3_power", "light.salotto", "climate.heatpump",
        "binary_sensor.presence_home",
    ])
    cache.get_state = lambda eid: state_map.get(eid, _make_state())
    m = SemanticMap(data_dir=str(tmp_path))
    m.build_from_cache(cache)
    snippet = m.get_prompt_snippet(cache)
    assert "CASA" in snippet
    assert "sensor.shellyem3_power" in snippet
    assert "Luci" in snippet


def test_get_prompt_snippet_empty_map(tmp_path):
    cache = _make_cache([])
    cache.get_state = lambda eid: _make_state()
    m = SemanticMap(data_dir=str(tmp_path))
    snippet = m.get_prompt_snippet(cache)
    assert isinstance(snippet, str)


def test_get_prompt_snippet_luci_includes_stanze(tmp_path):
    cache = _make_cache(["light.salotto", "light.cucina", "light.camera"])
    cache.get_state = lambda eid: _make_state()
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Salotto", area="Salotto", classified_by="rules")
    m._add_entity("light.cucina", "lighting", "Cucina", area="Cucina", classified_by="rules")
    m._add_entity("light.camera", "lighting", "Camera", area="Salotto", classified_by="rules")
    snippet = m.get_prompt_snippet(cache)
    assert "Luci: 3 entità / 2 stanze" in snippet


def test_get_prompt_snippet_luci_zero_stanze_when_no_areas(tmp_path):
    cache = _make_cache(["light.salotto"])
    cache.get_state = lambda eid: _make_state()
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("light.salotto", "lighting", "Salotto", area="", classified_by="rules")
    snippet = m.get_prompt_snippet(cache)
    assert "Luci: 1 entità / 0 stanze" in snippet


def test_get_prompt_snippet_sconosciuti_label(tmp_path):
    cache = _make_cache(["sensor.opaque_xyz_weird"])
    cache.get_state = lambda eid: _make_state()
    m = SemanticMap(data_dir=str(tmp_path))
    m.build_from_cache(cache)
    snippet = m.get_prompt_snippet(cache)
    assert "Sconosciuti:" in snippet
    assert "in attesa classificazione" in snippet
    assert "In classificazione:" not in snippet


def test_get_prompt_snippet_climate_entity_id_format(tmp_path):
    state_map = {
        "climate.heatpump": _make_state("heat", {"current_temperature": 22.5, "temperature": 21.0, "hvac_action": "heating"}),
    }
    cache = _make_cache(["climate.heatpump"])
    cache.get_state = lambda eid: state_map.get(eid, _make_state())
    m = SemanticMap(data_dir=str(tmp_path))
    m.build_from_cache(cache)
    snippet = m.get_prompt_snippet(cache)
    assert "climate.heatpump(22.5°→21.0°C heating)" in snippet


def test_get_prompt_snippet_climate_sensor_format(tmp_path):
    state_map = {
        "sensor.aqara_temp_salotto": _make_state("19.8"),
    }
    cache = _make_cache(["sensor.aqara_temp_salotto"])
    cache.get_state = lambda eid: state_map.get(eid, _make_state())
    m = SemanticMap(data_dir=str(tmp_path))
    m.build_from_cache(cache)
    snippet = m.get_prompt_snippet(cache)
    assert "sensor.aqara_temp_salotto(19.8°C)" in snippet


def test_get_prompt_snippet_appliances_use_entity_ids(tmp_path):
    cache = _make_cache(["switch.lavatrice", "switch.lavastoviglie"])
    cache.get_state = lambda eid: _make_state()
    m = SemanticMap(data_dir=str(tmp_path))
    m._add_entity("switch.lavatrice", "appliance", "Washing Machine", classified_by="rules")
    m._add_entity("switch.lavastoviglie", "appliance", "Dishwasher", classified_by="rules")
    snippet = m.get_prompt_snippet(cache)
    assert "switch.lavatrice" in snippet
    assert "switch.lavastoviglie" in snippet
    assert "Washing Machine" not in snippet
    assert "Dishwasher" not in snippet
