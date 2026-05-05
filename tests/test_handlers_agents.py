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


# ---------------------------------------------------------------------------
# Regression: PUT/POST agent rejects non-tool-capable OpenRouter model (v0.9.9)
# ---------------------------------------------------------------------------

from hiris.app.api.handlers_agents import handle_create_agent, handle_update_agent


@pytest.mark.asyncio
async def test_create_agent_rejects_broken_openrouter_model(monkeypatch):
    """Saving an agent with hermes-3 must return 400, not silently accept."""
    body = {
        "name": "test",
        "type": "chat",
        "model": "openrouter:nousresearch/hermes-3-llama-3.1-405b:free",
    }

    async def fake_capability(model, key):
        return False  # broken model

    monkeypatch.setattr(
        "hiris.app.api.handlers_models.is_openrouter_model_tool_capable",
        fake_capability,
    )

    engine = MagicMock()
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: {
        "openrouter_api_key": "sk-or-test",
    }.get(k, d))
    app.__getitem__ = MagicMock(side_effect=lambda k: {"engine": engine}[k])

    req = make_mocked_request("POST", "/api/agents", app=app)
    req.json = AsyncMock(return_value=body)

    resp = await handle_create_agent(req)
    assert resp.status == 400
    payload = json.loads(resp.body)
    assert "tool" in payload["error"].lower()
    assert "hermes-3" in payload["error"]
    engine.create_agent.assert_not_called()


@pytest.mark.asyncio
async def test_update_agent_accepts_tool_capable_openrouter_model(monkeypatch):
    """Tool-capable OpenRouter model passes validation cleanly."""
    body = {"name": "x", "type": "chat", "model": "openrouter:anthropic/claude-sonnet-4-6"}

    async def fake_capability(model, key):
        return True

    monkeypatch.setattr(
        "hiris.app.api.handlers_models.is_openrouter_model_tool_capable",
        fake_capability,
    )

    from dataclasses import dataclass
    @dataclass
    class _Agent:
        id: str = "a-uuid"
        name: str = "x"
        type: str = "chat"

    engine = MagicMock()
    engine.update_agent = MagicMock(return_value=_Agent())
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: {
        "openrouter_api_key": "sk-or-test",
    }.get(k, d))
    app.__getitem__ = MagicMock(side_effect=lambda k: {"engine": engine}[k])

    aid = "550e8400-e29b-41d4-a716-446655440000"
    req = make_mocked_request(
        "PUT", f"/api/agents/{aid}",
        match_info={"agent_id": aid},
        app=app,
    )
    req.json = AsyncMock(return_value=body)
    resp = await handle_update_agent(req)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_update_agent_skips_check_for_non_openrouter_models(monkeypatch):
    """Claude / OpenAI / Ollama models must NOT trigger an OpenRouter API call."""
    body = {"name": "x", "type": "chat", "model": "claude-sonnet-4-6"}

    cap_called = {"n": 0}
    async def fake_capability(model, key):
        cap_called["n"] += 1
        return None

    monkeypatch.setattr(
        "hiris.app.api.handlers_models.is_openrouter_model_tool_capable",
        fake_capability,
    )

    from dataclasses import dataclass
    @dataclass
    class _Agent:
        id: str = "a-uuid"
        name: str = "x"
        type: str = "chat"

    engine = MagicMock()
    engine.update_agent = MagicMock(return_value=_Agent())
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: {}.get(k, d))
    app.__getitem__ = MagicMock(side_effect=lambda k: {"engine": engine}[k])

    aid = "550e8400-e29b-41d4-a716-446655440000"
    req = make_mocked_request(
        "PUT", f"/api/agents/{aid}",
        match_info={"agent_id": aid},
        app=app,
    )
    req.json = AsyncMock(return_value=body)
    resp = await handle_update_agent(req)
    assert resp.status == 200
    assert cap_called["n"] == 0  # No OpenRouter call for Claude models


# ---------------------------------------------------------------------------
# Regression: warn at save when an autonomous (scheduled) agent is configured
# with a :free OpenRouter model (v0.9.10). User can override with
# confirm_free_for_agent: true. Chat agents on :free are fine.
# ---------------------------------------------------------------------------

from hiris.app.api.handlers_agents import _validate_free_model_for_agent_type


def test_free_model_warning_blocks_autonomous_agent_by_default():
    body = {
        "name": "monitor",
        "type": "agent",
        "model": "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    }
    err = _validate_free_model_for_agent_type(body)
    assert err is not None
    assert "free" in err.lower()
    assert "confirm_free_for_agent" in err


def test_free_model_warning_passes_with_explicit_confirm():
    body = {
        "name": "monitor",
        "type": "agent",
        "model": "openrouter:meta-llama/llama-3.3-70b-instruct:free",
        "confirm_free_for_agent": True,
    }
    assert _validate_free_model_for_agent_type(body) is None


def test_free_model_warning_skipped_for_chat_agent():
    body = {
        "name": "chat",
        "type": "chat",
        "model": "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    }
    assert _validate_free_model_for_agent_type(body) is None


def test_free_model_warning_skipped_for_paid_model():
    body = {
        "name": "monitor",
        "type": "agent",
        "model": "openrouter:anthropic/claude-sonnet-4-6",
    }
    assert _validate_free_model_for_agent_type(body) is None


def test_free_model_warning_skipped_for_non_free_suffix():
    body = {"name": "monitor", "type": "agent", "model": "claude-sonnet-4-6"}
    assert _validate_free_model_for_agent_type(body) is None


@pytest.mark.asyncio
async def test_create_agent_blocks_autonomous_on_free_without_confirm(monkeypatch):
    """End-to-end: POST /api/agents rejects autonomous agent on :free model."""
    body = {
        "name": "monitor",
        "type": "agent",
        "model": "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    }

    async def fake_capability(model, key):
        return True

    monkeypatch.setattr(
        "hiris.app.api.handlers_models.is_openrouter_model_tool_capable",
        fake_capability,
    )

    engine = MagicMock()
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: {}.get(k, d))
    app.__getitem__ = MagicMock(side_effect=lambda k: {"engine": engine}[k])

    req = make_mocked_request("POST", "/api/agents", app=app)
    req.json = AsyncMock(return_value=body)

    resp = await handle_create_agent(req)
    assert resp.status == 400
    payload = json.loads(resp.body)
    assert "free" in payload["error"].lower()
    engine.create_agent.assert_not_called()
