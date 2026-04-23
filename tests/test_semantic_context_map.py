import pytest
from unittest.mock import MagicMock
from hiris.app.proxy.semantic_context_map import (
    SemanticContextMap, classify_entity, ENTITY_TYPE_SCHEMA, CONCEPT_TO_TYPES,
)


def test_classify_climate():
    et, label = classify_entity("climate", None)
    assert et == "climate"
    assert label == "Termostato"


def test_classify_temperature_sensor():
    et, label = classify_entity("sensor", "temperature")
    assert et == "temperature"
    assert label == "Temperatura"


def test_classify_motion_binary_sensor():
    et, label = classify_entity("binary_sensor", "motion")
    assert et == "motion"
    assert label == "Presenza"


def test_classify_door_sensor():
    et, label = classify_entity("binary_sensor", "door")
    assert et == "door"
    assert label == "Porta"


def test_classify_light():
    et, label = classify_entity("light", None)
    assert et == "light"
    assert label == "Luce"


def test_classify_sensor_no_device_class():
    et, label = classify_entity("sensor", None)
    assert et == "sensor"
    assert label == "Sensore"


def test_classify_unknown_domain_returns_other():
    et, _ = classify_entity("unknown_xyz", None)
    assert et == "other"


def _make_cache(entities: list[dict], area_map: dict) -> MagicMock:
    cache = MagicMock()
    cache._states = {e["id"]: e for e in entities}
    cache.get_area_map.return_value = area_map
    return cache


def test_build_places_entities_by_area():
    cache = _make_cache(
        [
            {"id": "climate.bagno", "state": "heat", "name": "Termostato Bagno",
             "domain": "climate", "device_class": None, "unit": "", "attributes": {}},
            {"id": "light.bagno", "state": "off", "name": "Luce Bagno",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Bagno": ["climate.bagno", "light.bagno"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    assert "Bagno" in scm._map
    assert "climate" in scm._map["Bagno"]
    assert "climate.bagno" in scm._map["Bagno"]["climate"]
    assert "light.bagno" in scm._map["Bagno"]["light"]


def test_build_unassigned_entities_go_to_none_area():
    cache = _make_cache(
        [{"id": "sensor.power", "state": "1200", "name": "Potenza",
          "domain": "sensor", "device_class": "power", "unit": "W", "attributes": {}}],
        {"__no_area__": ["sensor.power"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    assert None in scm._map
    assert "power" in scm._map[None]


def test_build_excludes_noise_domains():
    cache = _make_cache(
        [
            {"id": "button.reset", "state": "unknown", "name": "Reset",
             "domain": "button", "device_class": None, "unit": "", "attributes": {}},
            {"id": "light.sala", "state": "on", "name": "Luce Sala",
             "domain": "light", "device_class": None, "unit": "", "attributes": {}},
        ],
        {"Soggiorno": ["button.reset", "light.sala"]},
    )
    scm = SemanticContextMap()
    scm.build(cache)
    all_ids = [
        eid for types in scm._map.values() for eids in types.values() for eid in eids
    ]
    assert "button.reset" not in all_ids
    assert "light.sala" in all_ids
