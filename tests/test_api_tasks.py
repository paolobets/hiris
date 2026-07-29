import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.chatbot_engine import ChatbotEngine
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

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
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
async def test_get_task_response_carries_both_keys(client):
    """_with_legacy_alias e' applicato sia a handle_list_tasks sia a
    handle_get_task: questo test copre il SECONDO handler, che
    test_task_response_carries_both_keys (solo /api/tasks) non esercita --
    una regressione che tolga l'alias dal solo endpoint per-id passerebbe la
    suite senza questo test."""
    task = _make_task()
    client.app["task_engine"].get_task = MagicMock(return_value=task)
    resp = await client.get("/api/tasks/t-001")
    assert resp.status == 200
    data = await resp.json()
    assert "agent_id" in data, "chiave nuova assente"
    assert "chatbot_id" in data, "alias deprecato assente sull'endpoint per-id"
    assert data["agent_id"] == data["chatbot_id"]


@pytest.mark.asyncio
async def test_list_tasks_query_param_agent_id_and_legacy_chatbot_id_both_accepted(client):
    """Pinna la precedenza non ancora testata (gap 3, minore): agent_id e
    chatbot_id come query-param sono entrambi accettati e, quando presenti
    insieme, la chiave nuova vince."""
    calls = []

    def _list_tasks(agent_id=None, status=None):
        calls.append(agent_id)
        return []

    client.app["task_engine"].list_tasks = MagicMock(side_effect=_list_tasks)

    resp = await client.get("/api/tasks", params={"chatbot_id": "legacy-agent"})
    assert resp.status == 200
    assert calls[-1] == "legacy-agent"

    resp = await client.get("/api/tasks", params={"agent_id": "new-agent"})
    assert resp.status == 200
    assert calls[-1] == "new-agent"

    resp = await client.get("/api/tasks", params={"agent_id": "new-agent", "chatbot_id": "legacy-agent"})
    assert resp.status == 200
    assert calls[-1] == "new-agent", "quando entrambi presenti deve vincere agent_id"


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


@pytest.mark.asyncio
async def test_task_response_carries_both_keys(client):
    """Il corpo di risposta emetteva chatbot_id verbatim, senza alias:
    rinominare senza shim romperebbe in silenzio ogni consumatore esterno."""
    task = _make_task()
    from dataclasses import asdict
    client.app["task_engine"].list_tasks = MagicMock(return_value=[asdict(task)])
    resp = await client.get("/api/tasks")
    body = await resp.json()
    assert body, "il fixture deve produrre almeno un task"
    t = body[0]
    assert "agent_id" in t, "chiave nuova assente"
    assert "chatbot_id" in t, "alias deprecato rimosso troppo presto"
    assert t["agent_id"] == t["chatbot_id"]
