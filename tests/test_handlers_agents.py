import json
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
    entities = json.loads(resp.body)
    assert all("light" in e["id"] or "light" in e["name"].lower() for e in entities)


@pytest.mark.asyncio
async def test_list_entities_empty_cache():
    cache = MagicMock()
    cache.get_all.return_value = []
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities", app=app)

    resp = await handle_list_entities(request)
    entities = json.loads(resp.body)
    assert entities == []


@pytest.mark.asyncio
async def test_list_entities_missing_name_field():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "sensor.weird", "state": "unavailable"},  # no "name" or "unit"
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities", app=app)

    resp = await handle_list_entities(request)
    entities = json.loads(resp.body)
    assert len(entities) == 1
    assert entities[0]["name"] == ""
    assert entities[0]["domain"] == "sensor"


@pytest.mark.asyncio
async def test_list_entities_search_case_insensitive():
    cache = MagicMock()
    cache.get_all.return_value = [
        {"id": "light.salon", "state": "on", "name": "Luce Soggiorno", "unit": ""},
    ]
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: cache if k == "entity_cache" else None)
    request = make_mocked_request("GET", "/api/entities?q=SOGGIORNO", app=app)

    resp = await handle_list_entities(request)
    entities = json.loads(resp.body)
    assert len(entities) == 1
    assert entities[0]["id"] == "light.salon"


@pytest.mark.asyncio
async def test_get_agent_usage_returns_stats():
    from hiris.app.api.handlers_agents import handle_get_agent_usage

    runner = MagicMock()
    runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 1000, "output_tokens": 400,
        "requests": 5, "cost_usd": 0.005, "last_run": "2026-04-21T10:00:00Z",
    })
    engine = MagicMock()
    engine.get_agent.return_value = MagicMock(id="agent-1")

    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: engine if k == "engine" else None)
    app.get = MagicMock(side_effect=lambda k, *args: runner if k == "claude_runner" else None)

    request = make_mocked_request(
        "GET", "/api/agents/agent-1/usage", app=app,
        match_info={"agent_id": "agent-1"},
    )

    resp = await handle_get_agent_usage(request)
    data = json.loads(resp.body)
    assert data["requests"] == 5
    assert data["input_tokens"] == 1000
    assert "cost_eur" in data
    assert data["cost_eur"] == round(0.005 * 0.92, 6)


@pytest.mark.asyncio
async def test_reset_agent_usage():
    from hiris.app.api.handlers_agents import handle_reset_agent_usage

    runner = MagicMock()
    runner.reset_agent_usage = MagicMock()
    engine = MagicMock()
    engine.get_agent.return_value = MagicMock(id="agent-1")

    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: engine if k == "engine" else None)
    app.get = MagicMock(side_effect=lambda k, *args: runner if k == "claude_runner" else None)

    request = make_mocked_request(
        "POST", "/api/agents/agent-1/usage/reset", app=app,
        match_info={"agent_id": "agent-1"},
    )

    resp = await handle_reset_agent_usage(request)
    assert resp.status == 200
    runner.reset_agent_usage.assert_called_once_with("agent-1")
