import pytest
from unittest.mock import MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_agents import handle_list_entities


@pytest.mark.asyncio
async def test_list_entities_returns_sorted_entities():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "switch.relay", "state": "off",  "name": "Relay",   "unit": ""},
        {"id": "light.salon",  "state": "on",   "name": "Salon",   "unit": ""},
        {"id": "sensor.temp",  "state": "21.5", "name": "Temp",    "unit": "°C"},
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities", app=app)

    resp = await handle_list_entities(request)
    import json
    entities = json.loads(resp.body)

    assert len(entities) == 3
    ids = [e["id"] for e in entities]
    assert ids == sorted(ids)
    assert entities[0]["domain"] == entities[0]["id"].split(".")[0]


@pytest.mark.asyncio
async def test_list_entities_search_filter():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "light.salon",   "state": "on",  "name": "Salon Light", "unit": ""},
        {"id": "sensor.temp",   "state": "21",  "name": "Temperature", "unit": "°C"},
        {"id": "light.kitchen", "state": "off", "name": "Kitchen",     "unit": ""},
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities?q=light", app=app)

    resp = await handle_list_entities(request)
    import json
    entities = json.loads(resp.body)
    assert all("light" in e["id"] or "light" in e["name"].lower() for e in entities)
