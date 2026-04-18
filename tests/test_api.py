import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine


@pytest_asyncio.fixture
async def client(aiohttp_client):
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha)
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Test response")
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner

    app.on_startup.clear()
    app.on_cleanup.clear()

    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.0.2"


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
