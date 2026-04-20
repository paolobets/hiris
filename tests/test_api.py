import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Test response")
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"

    app.on_startup.clear()
    app.on_cleanup.clear()

    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.3"


@pytest.mark.asyncio
async def test_status_endpoint(client):
    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "agents" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_chat_endpoint(client):
    resp = await client.post("/api/chat", json={"message": "Ciao"})
    assert resp.status == 200
    data = await resp.json()
    assert "response" in data


@pytest.mark.asyncio
async def test_agents_crud(client):
    payload = {
        "name": "Test Monitor",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "Monitor test",
        "allowed_tools": ["get_entity_states"],
        "enabled": False,
    }
    create_resp = await client.post("/api/agents", json=payload)
    assert create_resp.status == 201
    agent = await create_resp.json()
    agent_id = agent["id"]

    list_resp = await client.get("/api/agents")
    assert list_resp.status == 200
    agents = await list_resp.json()
    assert any(a["id"] == agent_id for a in agents)

    get_resp = await client.get(f"/api/agents/{agent_id}")
    assert get_resp.status == 200

    del_resp = await client.delete(f"/api/agents/{agent_id}")
    assert del_resp.status == 204


@pytest.mark.asyncio
async def test_chat_missing_message(client):
    resp = await client.post("/api/chat", json={})
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_chat_no_runner(aiohttp_client):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    from hiris.app.agent_engine import AgentEngine
    engine = AgentEngine(ha_client=mock_ha)
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = None
    app.on_startup.clear()
    app.on_cleanup.clear()

    c = await aiohttp_client(app)
    resp = await c.post("/api/chat", json={"message": "Hello"})
    assert resp.status == 503


@pytest.mark.asyncio
async def test_agent_not_found(client):
    resp = await client.get("/api/agents/nonexistent-id")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_agent_update(client):
    # Create
    payload = {
        "name": "Update Test",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "original",
        "allowed_tools": [],
        "enabled": False,
    }
    create_resp = await client.post("/api/agents", json=payload)
    agent_id = (await create_resp.json())["id"]

    # Update
    update_resp = await client.put(f"/api/agents/{agent_id}", json={"system_prompt": "updated"})
    assert update_resp.status == 200
    data = await update_resp.json()
    assert data["system_prompt"] == "updated"


@pytest.mark.asyncio
async def test_agent_run(client):
    payload = {
        "name": "Run Test",
        "type": "monitor",
        "trigger": {"type": "schedule", "interval_minutes": 5},
        "system_prompt": "run test",
        "allowed_tools": [],
        "enabled": False,
    }
    create_resp = await client.post("/api/agents", json=payload)
    agent_id = (await create_resp.json())["id"]

    run_resp = await client.post(f"/api/agents/{agent_id}/run")
    assert run_resp.status == 200
    data = await run_resp.json()
    assert "result" in data


@pytest.mark.asyncio
async def test_delete_default_agent_returns_409(client):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    engine = client.app["engine"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"}, system_prompt="",
        allowed_tools=[], enabled=True, is_default=True,
    )
    resp = await client.delete(f"/api/agents/{DEFAULT_AGENT_ID}")
    assert resp.status == 409
    data = await resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_chat_with_agent_id_uses_agent_system_prompt(client):
    from hiris.app.agent_engine import Agent
    engine = client.app["engine"]
    engine._agents["agent-chat-001"] = Agent(
        id="agent-chat-001", name="Energia", type="chat",
        trigger={"type": "manual"},
        system_prompt="Sei un esperto di energia.",
        allowed_tools=[], enabled=True, is_default=False,
        strategic_context="Contesto: casa a Milano.",
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta energia")

    resp = await client.post("/api/chat", json={
        "message": "quanto consumo?",
        "agent_id": "agent-chat-001",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["response"] == "risposta energia"
    call_kwargs = runner.chat.call_args.kwargs
    assert "Contesto: casa a Milano." in call_kwargs["system_prompt"]
    assert "esperto di energia" in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_chat_without_agent_id_uses_default_agent(client):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    engine = client.app["engine"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"},
        system_prompt="Prompt default HIRIS.",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta default")

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert "Prompt default HIRIS." in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_chat_with_unknown_agent_id_fallback_to_default(client):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    engine = client.app["engine"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"},
        system_prompt="Fallback prompt.",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="fallback")

    resp = await client.post("/api/chat", json={
        "message": "ciao",
        "agent_id": "non-esiste-123",
    })
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert "Fallback prompt." in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_config_endpoint_returns_theme(client):
    resp = await client.get("/api/config")
    assert resp.status == 200
    data = await resp.json()
    assert "theme" in data
    assert data["theme"] == "auto"


@pytest.mark.asyncio
async def test_chat_passes_model_to_runner(client):
    from hiris.app.agent_engine import Agent
    engine = client.app["engine"]
    engine._agents["agent-haiku-001"] = Agent(
        id="agent-haiku-001", name="Haiku Agent", type="monitor",
        trigger={"type": "manual"}, system_prompt="Monitor test",
        allowed_tools=[], enabled=True, is_default=False,
        model="claude-haiku-4-5-20251001", max_tokens=1024, restrict_to_home=False,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="ok")

    await client.post("/api/chat", json={"message": "test", "agent_id": "agent-haiku-001"})

    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 1024
    assert call_kwargs["agent_type"] == "monitor"
