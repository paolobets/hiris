import pytest
from unittest.mock import MagicMock, AsyncMock
from hiris.app.tools.task_tools import (
    CREATE_TASK_TOOL_DEF, LIST_TASKS_TOOL_DEF, CANCEL_TASK_TOOL_DEF,
    create_task_tool, list_tasks_tool, cancel_task_tool,
)


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    from hiris.app.task_engine import Task
    from datetime import datetime, timezone
    fake_task = Task(
        id="task-001", label="Test", agent_id="hiris-default",
        created_at=datetime.now(timezone.utc).isoformat(),
        trigger={"type": "delay", "minutes": 5},
        actions=[],
    )
    engine.add_task = MagicMock(return_value=fake_task)
    engine.cancel_task = MagicMock(return_value=True)
    engine.list_tasks = MagicMock(return_value=[])
    return engine


def test_create_task_tool_returns_id(mock_engine):
    result = create_task_tool(
        task_engine=mock_engine,
        label="Test",
        trigger={"type": "delay", "minutes": 5},
        actions=[],
        agent_id="hiris-default",
    )
    assert result["task_id"] == "task-001"
    assert result["status"] == "pending"


def test_list_tasks_tool_returns_list(mock_engine):
    result = list_tasks_tool(task_engine=mock_engine)
    assert isinstance(result, list)


def test_cancel_task_tool_success(mock_engine):
    result = cancel_task_tool(task_engine=mock_engine, task_id="task-001")
    assert result["cancelled"] is True


def test_cancel_task_tool_failure(mock_engine):
    mock_engine.cancel_task = MagicMock(return_value=False)
    result = cancel_task_tool(task_engine=mock_engine, task_id="bad-id")
    assert "error" in result


def test_tool_defs_have_required_fields():
    for defn in (CREATE_TASK_TOOL_DEF, LIST_TASKS_TOOL_DEF, CANCEL_TASK_TOOL_DEF):
        assert "name" in defn
        assert "description" in defn
        assert "input_schema" in defn
