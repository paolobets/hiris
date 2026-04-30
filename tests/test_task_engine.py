import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from hiris.app.task_engine import Task, TaskEngine


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.call_service = AsyncMock(return_value=True)
    return ha


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.get_state = MagicMock(return_value={"state": "15.0"})
    return cache


@pytest.fixture
def engine(tmp_path, mock_ha, mock_cache):
    te = TaskEngine(
        ha_client=mock_ha,
        entity_cache=mock_cache,
        notify_config={},
        data_path=str(tmp_path / "tasks.json"),
    )
    te._scheduler = MagicMock()  # prevent real scheduling
    return te


# ── Task 1: Core operations ────────────────────────────────────────────────


def test_add_task_returns_pending(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    assert task.status == "pending"
    assert task.agent_id == "hiris-default"
    assert task.id is not None


def test_cancel_pending_task(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    result = engine.cancel_task(task.id)
    assert result is True
    assert engine._tasks[task.id].status == "cancelled"


def test_cancel_nonexistent_task(engine):
    assert engine.cancel_task("does-not-exist") is False


def test_cancel_done_task_returns_false(engine):
    task = engine.add_task(
        {"label": "Test", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    engine._tasks[task.id].status = "done"
    assert engine.cancel_task(task.id) is False


def test_list_tasks_filter_by_status(engine):
    engine.add_task(
        {"label": "A", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-1",
    )
    t2 = engine.add_task(
        {"label": "B", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-2",
    )
    engine._tasks[t2.id].status = "done"
    pending = engine.list_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0]["label"] == "A"


def test_list_tasks_filter_by_agent(engine):
    engine.add_task(
        {"label": "A", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-1",
    )
    engine.add_task(
        {"label": "B", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="agent-2",
    )
    result = engine.list_tasks(agent_id="agent-1")
    assert len(result) == 1
    assert result[0]["label"] == "A"


def test_cleanup_removes_old_terminal_tasks(engine):
    task = engine.add_task(
        {"label": "Old", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    engine._tasks[task.id].status = "done"
    engine._tasks[task.id].executed_at = old_ts
    engine._cleanup()
    assert task.id not in engine._tasks


def test_cleanup_keeps_recent_terminal_tasks(engine):
    task = engine.add_task(
        {"label": "Recent", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="hiris-default",
    )
    engine._tasks[task.id].status = "done"
    engine._tasks[task.id].executed_at = datetime.now(timezone.utc).isoformat()
    engine._cleanup()
    assert task.id in engine._tasks


def test_persistence_roundtrip(tmp_path, mock_ha, mock_cache):
    path = str(tmp_path / "tasks.json")
    te1 = TaskEngine(ha_client=mock_ha, entity_cache=mock_cache, notify_config={}, data_path=path)
    te1._scheduler = MagicMock()
    task = te1.add_task(
        {"label": "Persist me", "trigger": {"type": "delay", "minutes": 10}, "actions": []},
        agent_id="hiris-default",
    )

    te2 = TaskEngine(ha_client=mock_ha, entity_cache=mock_cache, notify_config={}, data_path=path)
    te2._scheduler = MagicMock()
    te2._load()
    assert task.id in te2._tasks
    assert te2._tasks[task.id].label == "Persist me"


# ── Task 2: Condition evaluation + execution ───────────────────────────────


def test_evaluate_condition_numeric_lt_passes(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "15.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is True


def test_evaluate_condition_numeric_lt_fails(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "22.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is False


def test_evaluate_condition_string_eq(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "on"})
    assert engine._evaluate_condition(
        {"entity_id": "binary_sensor.door", "operator": "=", "value": "on"}
    ) is True


def test_evaluate_condition_entity_missing(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value=None)
    assert engine._evaluate_condition(
        {"entity_id": "sensor.missing", "operator": "<", "value": 10}
    ) is False


@pytest.mark.asyncio
async def test_execute_task_done_on_success(engine, mock_ha):
    task = engine.add_task({
        "label": "Turn on",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on",
                     "data": {"entity_id": "light.test"}}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    mock_ha.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.test"})


@pytest.mark.asyncio
async def test_execute_task_skipped_when_condition_false(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "25.0"})
    task = engine.add_task({
        "label": "Cond task",
        "trigger": {"type": "delay", "minutes": 1},
        "condition": {"entity_id": "sensor.temp", "operator": "<", "value": 19},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on", "data": {}}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "skipped"


@pytest.mark.asyncio
async def test_execute_task_failed_on_ha_error(engine, mock_ha):
    mock_ha.call_service = AsyncMock(side_effect=Exception("HA error"))
    task = engine.add_task({
        "label": "Fail task",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on", "data": {}, "on_fail": "stop"}],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "failed"
    assert "HA error" in engine._tasks[task.id].error


@pytest.mark.asyncio
async def test_execute_task_chain_creates_child(engine):
    task = engine.add_task({
        "label": "Parent",
        "trigger": {"type": "delay", "minutes": 1},
        "actions": [{
            "type": "create_task",
            "task": {
                "label": "Child",
                "trigger": {"type": "delay", "minutes": 60},
                "actions": [],
            }
        }],
    }, agent_id="hiris-default")
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "done"
    children = [t for t in engine._tasks.values() if t.parent_task_id == task.id]
    assert len(children) == 1
    assert children[0].label == "Child"


# ── Task 3: Additional coverage ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_time_window_within_window(engine, mock_ha):
    now = datetime.now()
    from_time = (now - timedelta(hours=1)).strftime("%H:%M")
    to_time = (now + timedelta(hours=1)).strftime("%H:%M")
    task = engine.add_task(
        {
            "label": "Window task",
            "trigger": {
                "type": "time_window",
                "from": from_time,
                "to": to_time,
                "check_interval_minutes": 5,
            },
            "actions": [
                {
                    "type": "call_ha_service",
                    "domain": "light",
                    "service": "turn_on",
                    "data": {"entity_id": "light.test"},
                }
            ],
        },
        agent_id="hiris-default",
    )
    await engine._check_time_window(task.id)
    assert engine._tasks[task.id].status == "done"


def test_at_datetime_schedules_correct_run_date(engine):
    future = datetime.now() + timedelta(hours=2)
    future_iso = future.replace(microsecond=0).isoformat()
    task = engine.add_task(
        {"label": "Future", "trigger": {"type": "at_datetime", "datetime": future_iso}, "actions": []},
        agent_id="hiris-default",
    )
    run_date = engine._scheduler.add_job.call_args[1]["run_date"]
    assert abs((run_date - future).total_seconds()) < 2


def test_at_time_rollover(engine):
    task = engine.add_task(
        {"label": "Night", "trigger": {"type": "at_time", "time": "00:01"}, "actions": []},
        agent_id="hiris-default",
    )
    run_date = engine._scheduler.add_job.call_args[1]["run_date"]
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    assert run_date.date() == tomorrow


@pytest.mark.asyncio
async def test_unknown_action_marks_failed(engine):
    task = engine.add_task(
        {
            "label": "Bad action",
            "trigger": {"type": "delay", "minutes": 1},
            "actions": [{"type": "unknown_action", "foo": "bar", "on_fail": "stop"}],
        },
        agent_id="hiris-default",
    )
    await engine._execute_task(task.id)
    assert engine._tasks[task.id].status == "failed"
    assert "unknown_action" in engine._tasks[task.id].error


def test_cancel_removes_scheduler_job(engine):
    task = engine.add_task(
        {"label": "Cancel me", "trigger": {"type": "delay", "minutes": 5}, "actions": []},
        agent_id="hiris-default",
    )
    engine.cancel_task(task.id)
    removed = [c[0][0] for c in engine._scheduler.remove_job.call_args_list]
    assert f"task_{task.id}" in removed


def test_cleanup_keeps_tasks_within_7_days(engine):
    """Tasks terminali più vecchi di 7gg vengono rimossi; quelli entro 7gg no."""
    from hiris.app.task_engine import _CLEANUP_AFTER_HOURS

    assert _CLEANUP_AFTER_HOURS == 168, "Expected 7 days (168h)"

    old_task = engine.add_task(
        {"label": "old", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="test",
    )
    old_task.status = "done"
    old_task.created_at = (
        datetime.now(timezone.utc) - timedelta(hours=169)
    ).isoformat()
    engine._tasks[old_task.id] = old_task

    recent_task = engine.add_task(
        {"label": "recent", "trigger": {"type": "delay", "minutes": 1}, "actions": []},
        agent_id="test",
    )
    recent_task.status = "done"
    recent_task.created_at = (
        datetime.now(timezone.utc) - timedelta(hours=10)
    ).isoformat()
    engine._tasks[recent_task.id] = recent_task

    engine._cleanup()

    assert old_task.id not in engine._tasks
    assert recent_task.id in engine._tasks
