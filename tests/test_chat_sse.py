import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
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
    mock_runner.chat = AsyncMock(return_value="SSE test response text")
    mock_runner.last_tool_calls = []
    mock_runner.get_agent_usage = MagicMock(return_value={"cost_usd": 0.0})

    async def fake_chat_stream(**kwargs):
        import json
        yield f'data: {json.dumps({"type": "token", "text": "SSE test"})}\n\n'
        yield f'data: {json.dumps({"type": "done", "agent_id": None, "tool_calls": []})}\n\n'

    mock_runner.chat_stream = fake_chat_stream
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
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_chat_sse_via_stream_body_param(client):
    resp = await client.post("/api/chat", json={"message": "Test SSE", "stream": True})
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_chat_sse_via_accept_header(client):
    resp = await client.post(
        "/api/chat",
        json={"message": "Test SSE"},
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_chat_json_still_works(client):
    """Non-SSE requests still return JSON."""
    resp = await client.post("/api/chat", json={"message": "Hello"})
    assert resp.status == 200
    data = await resp.json()
    assert "response" in data
    assert data["response"] == "SSE test response text"


@pytest.mark.asyncio
async def test_chat_sse_body_contains_events(client):
    resp = await client.post("/api/chat", json={"message": "Test", "stream": True})
    body = await resp.text()
    assert "data:" in body
    assert '"type"' in body
