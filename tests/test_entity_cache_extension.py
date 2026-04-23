import pytest
from hiris.app.proxy.entity_cache import _to_minimal


def test_to_minimal_adds_domain():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"friendly_name": "Temperatura Bagno", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["domain"] == "sensor"


def test_to_minimal_adds_device_class():
    raw = {"entity_id": "sensor.temp_bagno", "state": "21.5",
           "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}}
    result = _to_minimal(raw)
    assert result["device_class"] == "temperature"


def test_to_minimal_device_class_none_when_absent():
    raw = {"entity_id": "light.sala", "state": "on", "attributes": {}}
    result = _to_minimal(raw)
    assert result["device_class"] is None


def test_to_minimal_climate_attributes():
    raw = {
        "entity_id": "climate.bagno", "state": "heat",
        "attributes": {
            "hvac_mode": "heat", "hvac_action": "heating",
            "current_temperature": 21.5, "temperature": 22.0, "preset_mode": "home",
        },
    }
    result = _to_minimal(raw)
    assert result["attributes"]["hvac_mode"] == "heat"
    assert result["attributes"]["current_temperature"] == 21.5
    assert result["attributes"]["preset_mode"] == "home"


def test_to_minimal_light_attributes():
    raw = {
        "entity_id": "light.soggiorno", "state": "on",
        "attributes": {"brightness": 200, "color_temp": 3000},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["brightness"] == 200
    assert result["attributes"]["color_temp"] == 3000


def test_to_minimal_cover_attributes():
    raw = {
        "entity_id": "cover.tapparella_salotto", "state": "open",
        "attributes": {"current_position": 75},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["current_position"] == 75


def test_to_minimal_media_player_attributes():
    raw = {
        "entity_id": "media_player.tv_salotto", "state": "playing",
        "attributes": {"media_title": "Netflix", "volume_level": 0.5, "source": "HDMI1"},
    }
    result = _to_minimal(raw)
    assert result["attributes"]["media_title"] == "Netflix"
    assert result["attributes"]["volume_level"] == 0.5


def test_to_minimal_no_extra_attrs_for_binary_sensor():
    raw = {
        "entity_id": "binary_sensor.porta_ingresso", "state": "off",
        "attributes": {"device_class": "door"},
    }
    result = _to_minimal(raw)
    assert result.get("attributes", {}) == {}
