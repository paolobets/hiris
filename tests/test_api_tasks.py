import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.task_engine import Task, TaskEngine


def _make_task(task_id="t-001", label="Test task", status="pending"):
    return Task(
        id=task_id, label=label, agent_id="hiris-default",
        created_at=datetime.now(timezone.utc).isoformat(),
        trigger={"type": "delay", "minutes": 5}, actions=[],
        status=status,
    )


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    mock_task_engine = MagicMock(spec=TaskEngine)
    mock_task_engine.list_tasks = MagicMock(return_value=[])
    mock_task_engine.get_task = MagicMock(return_value=None)
    mock_task_engine.cancel_task = MagicMock(return_value=False)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = None
    app["task_engine"] = mock_task_engine
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()

    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_list_tasks_empty(client):
    resp = await client.get("/api/tasks")
    assert resp.status == 200
    data = await resp.json()
    assert data == []


@pytest.mark.asyncio
async def test_list_tasks_returns_all(client):
    task = _make_task()
    from dataclasses import asdict
    client.app["task_engine"].list_tasks = MagicMock(return_value=[asdict(task)])
    resp = await client.get("/api/tasks")
    assert resp.status == 200
    data = await resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "t-001"


@pytest.mark.asyncio
async def test_get_task_not_found(client):
    resp = await client.get("/api/tasks/nonexistent")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_get_task_found(client):
    task = _make_task()
    client.app["task_engine"].get_task = MagicMock(return_value=task)
    resp = await client.get("/api/tasks/t-001")
    assert resp.status == 200
    data = await resp.json()
    assert data["id"] == "t-001"


@pytest.mark.asyncio
async def test_cancel_task_not_found(client):
    client.app["task_engine"].cancel_task = MagicMock(return_value=False)
    resp = await client.delete("/api/tasks/nonexistent")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_cancel_task_pending(client):
    client.app["task_engine"].cancel_task = MagicMock(return_value=True)
    resp = await client.delete("/api/tasks/t-001")
    assert resp.status == 204
