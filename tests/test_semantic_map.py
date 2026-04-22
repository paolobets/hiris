import json
import os
import pytest
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
    m = SemanticMap(data_dir="/tmp")
    assert m.get_category("energy_meter") == []


def test_semantic_map_add_and_get_category():
    m = SemanticMap(data_dir="/tmp")
    m._add_entity("sensor.power_main", "energy_meter", "Contatore principale", classified_by="rules")
    assert "sensor.power_main" in m.get_category("energy_meter")


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
