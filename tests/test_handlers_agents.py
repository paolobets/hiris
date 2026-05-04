import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
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


# ---- Dashboard field tests (Task 2) ----

@pytest.fixture
def _dashboard_app(tmp_path):
    """Shared app factory for dashboard-field tests."""
    from hiris.app.server import create_app
    from hiris.app.agent_engine import AgentEngine
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.get_agent_usage = MagicMock(return_value={
        "input_tokens": 100, "output_tokens": 50,
        "requests": 2, "cost_usd": 0.13, "last_run": None,
    })
    engine.set_claude_runner(mock_runner)
    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["llm_router"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = ""
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def dashboard_client(aiohttp_client, _dashboard_app):
    from hiris.app.chat_store import close_all_stores
    yield await aiohttp_client(_dashboard_app)
    close_all_stores()


@pytest.mark.asyncio
async def test_list_agents_has_status_field(dashboard_client):
    resp = await dashboard_client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    assert isinstance(agents, list)
    for agent in agents:
        assert "status" in agent
        assert agent["status"] in ("idle", "running", "error")


@pytest.mark.asyncio
async def test_list_agents_has_budget_fields(dashboard_client):
    resp = await dashboard_client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    for agent in agents:
        assert "budget_eur" in agent
        assert "budget_limit_eur" in agent
        assert isinstance(agent["budget_eur"], float)
        assert isinstance(agent["budget_limit_eur"], float)


@pytest.mark.asyncio
async def test_list_agents_budget_computed_from_usage(dashboard_client):
    resp = await dashboard_client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    # mock_runner returns cost_usd=0.13, EUR rate=0.92 → 0.1196
    for agent in agents:
        assert agent["budget_eur"] == round(0.13 * 0.92, 4)


@pytest.mark.asyncio
async def test_created_agent_has_all_dashboard_fields(dashboard_client):
    resp = await dashboard_client.post("/api/agents", json={
        "name": "Test",
        "type": "chat",
        "trigger": {"type": "manual"},
        "system_prompt": "test",
    })
    assert resp.status == 201

    resp = await dashboard_client.get("/api/agents")
    assert resp.status == 200
    agents = await resp.json()
    required = {"id", "name", "type", "enabled", "status", "last_run",
                "budget_eur", "budget_limit_eur", "is_default"}
    for agent in agents:
        missing = required - set(agent.keys())
        assert not missing, f"Missing fields: {missing}"


# ---------------------------------------------------------------------------
# delete_agent must clean up orphaned data (memory + chat history)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_agent_cleans_memory_and_chat_history():
    """handle_delete_agent must call memory_store.delete_by_agent + clear_history."""
    from hiris.app.api.handlers_agents import handle_delete_agent

    engine = MagicMock()
    fake_agent = MagicMock()
    fake_agent.is_default = False
    engine.get_agent.return_value = fake_agent
    engine.delete_agent.return_value = True

    memory_store = MagicMock()
    memory_store.delete_by_agent = MagicMock()

    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, default=None: {
        "memory_store": memory_store,
        "data_dir": "/tmp/hiris_test_data",
    }.get(k, default))
    app.__getitem__ = MagicMock(side_effect=lambda k: {
        "engine": engine,
    }[k])

    aid = "550e8400-e29b-41d4-a716-446655440000"
    request = make_mocked_request(
        "DELETE", f"/api/agents/{aid}",
        match_info={"agent_id": aid},
        app=app,
    )

    # clear_history is imported lazily inside the handler — patch in chat_store
    with pytest.MonkeyPatch.context() as mp:
        called = {"clear": None}
        def fake_clear(agent_id, data_dir):
            called["clear"] = (agent_id, data_dir)
        mp.setattr("hiris.app.chat_store.clear_history", fake_clear)
        resp = await handle_delete_agent(request)

    assert resp.status == 204
    memory_store.delete_by_agent.assert_called_once_with(aid)
    assert called["clear"] == (aid, "/tmp/hiris_test_data")
