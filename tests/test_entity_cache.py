import pytest
from unittest.mock import AsyncMock
from hiris.app.proxy.entity_cache import EntityCache, NOISE_DOMAINS


@pytest.mark.asyncio
async def test_load_calls_get_states_once():
    mock_ha = AsyncMock()
    mock_ha.get_states.return_value = []
    cache = EntityCache()
    await cache.load(mock_ha)
    mock_ha.get_states.assert_called_once_with([])


@pytest.mark.asyncio
async def test_load_builds_minimal_state():
    mock_ha = AsyncMock()
    mock_ha.get_states.return_value = [
        {
            "entity_id": "light.soggiorno",
            "state": "on",
            "attributes": {"friendly_name": "Luce Soggiorno", "unit_of_measurement": ""},
        },
        {
            "entity_id": "sensor.temp",
            "state": "21.5",
            "attributes": {"friendly_name": "Temperatura", "unit_of_measurement": "°C"},
        },
    ]
    cache = EntityCache()
    await cache.load(mock_ha)

    assert cache.get_minimal(["light.soggiorno"]) == [
        {"id": "light.soggiorno", "state": "on", "name": "Luce Soggiorno", "unit": ""}
    ]
    assert cache.get_minimal(["sensor.temp"]) == [
        {"id": "sensor.temp", "state": "21.5", "name": "Temperatura", "unit": "°C"}
    ]


def test_get_minimal_skips_missing_ids():
    cache = EntityCache()
    cache._states = {"light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""}}
    result = cache.get_minimal(["light.a", "light.missing"])
    assert len(result) == 1
    assert result[0]["id"] == "light.a"


def test_get_on_returns_only_on_state():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "light.b": {"id": "light.b", "state": "off", "name": "B", "unit": ""},
        "switch.c": {"id": "switch.c", "state": "on", "name": "C", "unit": ""},
    }
    result = cache.get_on()
    assert len(result) == 2
    assert all(e["state"] == "on" for e in result)
    assert {e["id"] for e in result} == {"light.a", "switch.c"}


def test_get_all_useful_excludes_noise_domains():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "button.b": {"id": "button.b", "state": "available", "name": "B", "unit": ""},
        "update.c": {"id": "update.c", "state": "on", "name": "C", "unit": ""},
        "select.d": {"id": "select.d", "state": "option1", "name": "D", "unit": ""},
        "sensor.e": {"id": "sensor.e", "state": "21", "name": "E", "unit": "°C"},
    }
    result = cache.get_all_useful()
    assert {e["id"] for e in result} == {"light.a", "sensor.e"}


def test_noise_domains_constant():
    assert NOISE_DOMAINS == {"button", "update", "number", "select", "tag",
                             "event", "ai_task", "todo", "conversation"}


def test_get_by_domain():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "light.b": {"id": "light.b", "state": "off", "name": "B", "unit": ""},
        "switch.c": {"id": "switch.c", "state": "on", "name": "C", "unit": ""},
    }
    cache._by_domain = {"light": ["light.a", "light.b"], "switch": ["switch.c"]}

    result = cache.get_by_domain("light")
    assert len(result) == 2
    assert all(e["id"].startswith("light.") for e in result)

    assert cache.get_by_domain("nonexistent") == []


def test_on_state_changed_updates_existing_entity():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "off", "name": "Luce", "unit": ""},
    }
    cache._by_domain = {"light": ["light.a"]}

    cache.on_state_changed({
        "new_state": {
            "entity_id": "light.a",
            "state": "on",
            "attributes": {"friendly_name": "Luce Aggiornata"},
        }
    })

    assert cache._states["light.a"]["state"] == "on"
    assert cache._states["light.a"]["name"] == "Luce Aggiornata"


def test_on_state_changed_adds_new_entity():
    cache = EntityCache()
    cache._states = {}
    cache._by_domain = {}

    cache.on_state_changed({
        "new_state": {
            "entity_id": "light.new",
            "state": "on",
            "attributes": {"friendly_name": "New Light"},
        }
    })

    assert "light.new" in cache._states
    assert cache._states["light.new"]["state"] == "on"
    assert "light.new" in cache._by_domain.get("light", [])


def test_on_state_changed_ignores_none_new_state():
    cache = EntityCache()
    cache._states = {}
    cache.on_state_changed({"new_state": None})
    assert cache._states == {}


def test_on_state_changed_ignores_missing_entity_id():
    cache = EntityCache()
    cache._states = {}
    cache._by_domain = {}
    cache.on_state_changed({
        "new_state": {
            "state": "on",
            "attributes": {"friendly_name": "Ghost"},
        }
    })
    assert cache._states == {}


def test_get_all_returns_all_states():
    cache = EntityCache()
    cache._states = {
        "light.a": {"id": "light.a", "state": "on", "name": "A", "unit": ""},
        "button.b": {"id": "button.b", "state": "available", "name": "B", "unit": ""},
    }
    assert len(cache.get_all()) == 2


def test_on_state_changed_handles_none_attributes():
    cache = EntityCache()
    cache._states = {}
    cache._by_domain = {}
    cache.on_state_changed({
        "new_state": {
            "entity_id": "sensor.weird",
            "state": "unavailable",
            "attributes": None,
        }
    })
    assert "sensor.weird" in cache._states
    assert cache._states["sensor.weird"]["name"] == ""


@pytest.mark.asyncio
async def test_load_area_registry_builds_area_map():
    mock_ha = AsyncMock()
    mock_ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina_id", "name": "Cucina"},
        {"area_id": "soggiorno_id", "name": "Soggiorno"},
    ])
    mock_ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.luce_cucina",    "area_id": "cucina_id"},
        {"entity_id": "switch.presa_cucina",  "area_id": "cucina_id"},
        {"entity_id": "light.luce_soggiorno", "area_id": "soggiorno_id"},
        {"entity_id": "sensor.no_area",       "area_id": None},
    ])
    cache = EntityCache()
    await cache.load_area_registry(mock_ha)
    area_map = cache.get_area_map()
    assert "Cucina" in area_map
    assert "light.luce_cucina" in area_map["Cucina"]
    assert "switch.presa_cucina" in area_map["Cucina"]
    assert "Soggiorno" in area_map
    assert "light.luce_soggiorno" in area_map["Soggiorno"]
    assert "__no_area__" in area_map
    assert "sensor.no_area" in area_map["__no_area__"]


def test_get_area_map_returns_empty_before_load():
    cache = EntityCache()
    assert cache.get_area_map() == {}


@pytest.mark.asyncio
async def test_load_area_registry_survives_empty_registries():
    mock_ha = AsyncMock()
    mock_ha.get_area_registry = AsyncMock(return_value=[])
    mock_ha.get_entity_registry = AsyncMock(return_value=[])
    cache = EntityCache()
    await cache.load_area_registry(mock_ha)
    assert cache.get_area_map() == {}
