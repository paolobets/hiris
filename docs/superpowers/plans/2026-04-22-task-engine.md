# TaskEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared deferred-task system to HIRIS that all agent types can use via Claude tool calls (`create_task`, `list_tasks`, `cancel_task`), with persistence, 4 trigger types, optional conditions, action chaining, and a UI monitoring section.

**Architecture:** `TaskEngine` is a new standalone service wired at startup alongside `AgentEngine`. It owns an `AsyncIOScheduler`, persists tasks to `/data/tasks.json`, executes actions directly (no Claude call), and exposes 3 Claude tools registered in `ClaudeRunner._dispatch_tool`. A new UI tab shows active and recent tasks with auto-refresh.

**Tech Stack:** Python 3.11 · APScheduler · aiohttp · existing `HAClient`, `EntityCache`, `send_notification`

---

## File map

| File | Op | Responsibility |
|---|---|---|
| `hiris/app/task_engine.py` | Create | `Task` dataclass, `TaskEngine` (persist, schedule, execute, cleanup) |
| `hiris/app/tools/task_tools.py` | Create | Claude tool defs + thin wrappers for 3 task tools |
| `hiris/app/api/handlers_tasks.py` | Create | REST: `GET /api/tasks`, `GET /api/tasks/{id}`, `DELETE /api/tasks/{id}` |
| `hiris/app/server.py` | Modify | Startup wiring + 3 new routes |
| `hiris/app/claude_runner.py` | Modify | `set_task_engine()`, pass `agent_id` to `_dispatch_tool`, dispatch 3 task tools |
| `hiris/app/static/index.html` | Modify | Task tab with badge, active list, recent list, 30s poll |
| `tests/test_task_engine.py` | Create | Unit tests for `TaskEngine` logic |
| `tests/test_api_tasks.py` | Create | Integration tests for task REST API |

---

## Task 1: `Task` dataclass + `TaskEngine` core (persist, add, cancel, list, cleanup)

**Files:**
- Create: `hiris/app/task_engine.py`
- Create: `tests/test_task_engine.py`

- [ ] **Step 1: Write failing tests for Task dataclass and core TaskEngine operations**

```python
# tests/test_task_engine.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd hiris && pytest ../tests/test_task_engine.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'TaskEngine' from 'hiris.app.task_engine'`

- [ ] **Step 3: Write `task_engine.py`**

```python
# hiris/app/task_engine.py
import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_TERMINAL = frozenset({"done", "skipped", "failed", "expired", "cancelled"})
_CLEANUP_AFTER_HOURS = 24


@dataclass
class Task:
    id: str
    label: str
    agent_id: str
    created_at: str
    trigger: dict
    actions: list
    condition: Optional[dict] = None
    one_shot: bool = True
    status: str = "pending"
    executed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    parent_task_id: Optional[str] = None


class TaskEngine:
    def __init__(
        self,
        ha_client: Any,
        entity_cache: Any,
        notify_config: dict,
        data_path: str = "/data/tasks.json",
    ) -> None:
        self._ha = ha_client
        self._cache = entity_cache
        self._notify_config = notify_config
        self._data_path = data_path
        self._tasks: dict[str, Task] = {}
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        self._scheduler.start()
        self._load()
        self._cleanup()
        self._scheduler.add_job(
            self._cleanup, "interval", hours=1, id="task_engine_cleanup", replace_existing=True
        )
        logger.info("TaskEngine started with %d tasks", len(self._tasks))

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    # ── Public API ─────────────────────────────────────────────────────────

    def add_task(self, data: dict, agent_id: str, parent_task_id: Optional[str] = None) -> Task:
        task = Task(
            id=str(uuid.uuid4()),
            label=data["label"],
            agent_id=agent_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            trigger=data["trigger"],
            actions=list(data.get("actions", [])),
            condition=data.get("condition"),
            one_shot=bool(data.get("one_shot", True)),
            parent_task_id=parent_task_id,
        )
        self._tasks[task.id] = task
        self._schedule_task(task)
        self._save()
        return task

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None or task.status != "pending":
            return False
        task.status = "cancelled"
        task.executed_at = datetime.now(timezone.utc).isoformat()
        self._remove_job(task_id)
        self._save()
        return True

    def list_tasks(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        result = []
        for t in self._tasks.values():
            if agent_id and t.agent_id != agent_id:
                continue
            if status and t.status != status:
                continue
            result.append(asdict(t))
        return sorted(result, key=lambda x: x["created_at"], reverse=True)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    # ── Persistence ────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            data = {"schema_version": 1, "tasks": [asdict(t) for t in self._tasks.values()]}
            tmp = self._data_path + ".tmp"
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, self._data_path)
        except Exception as exc:
            logger.error("Failed to save tasks: %s", exc)

    def _load(self) -> None:
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("tasks", []):
                task = Task(
                    id=raw["id"],
                    label=raw["label"],
                    agent_id=raw.get("agent_id", "hiris-default"),
                    created_at=raw["created_at"],
                    trigger=raw["trigger"],
                    actions=raw.get("actions", []),
                    condition=raw.get("condition"),
                    one_shot=raw.get("one_shot", True),
                    status=raw.get("status", "pending"),
                    executed_at=raw.get("executed_at"),
                    result=raw.get("result"),
                    error=raw.get("error"),
                    parent_task_id=raw.get("parent_task_id"),
                )
                self._tasks[task.id] = task
                if task.status == "pending":
                    self._schedule_task(task)
        except Exception as exc:
            logger.error("Failed to load tasks: %s", exc)

    # ── Cleanup ────────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_CLEANUP_AFTER_HOURS)
        to_remove = []
        for task_id, task in self._tasks.items():
            if task.status not in _TERMINAL:
                continue
            ts_str = task.executed_at or task.created_at
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    to_remove.append(task_id)
            except Exception:
                pass
        for task_id in to_remove:
            del self._tasks[task_id]
        if to_remove:
            self._save()
            logger.info("TaskEngine cleanup: removed %d terminal tasks", len(to_remove))

    # ── Scheduling ─────────────────────────────────────────────────────────

    def _schedule_task(self, task: Task) -> None:
        trigger = task.trigger
        t_type = trigger.get("type")
        try:
            if t_type == "delay":
                run_dt = datetime.now(timezone.utc) + timedelta(minutes=int(trigger["minutes"]))
                self._scheduler.add_job(
                    self._run_task_async, "date", run_date=run_dt,
                    args=[task.id], id=f"task_{task.id}", replace_existing=True,
                )
            elif t_type == "at_time":
                h, m = (int(x) for x in trigger["time"].split(":"))
                run_dt = datetime.now(timezone.utc).replace(
                    hour=h, minute=m, second=0, microsecond=0
                )
                if run_dt <= datetime.now(timezone.utc):
                    run_dt += timedelta(days=1)
                self._scheduler.add_job(
                    self._run_task_async, "date", run_date=run_dt,
                    args=[task.id], id=f"task_{task.id}", replace_existing=True,
                )
            elif t_type == "at_datetime":
                run_dt = datetime.fromisoformat(trigger["datetime"])
                self._scheduler.add_job(
                    self._run_task_async, "date", run_date=run_dt,
                    args=[task.id], id=f"task_{task.id}", replace_existing=True,
                )
            elif t_type == "time_window":
                interval = int(trigger.get("check_interval_minutes", 5))
                self._scheduler.add_job(
                    self._poll_time_window, "interval", minutes=interval,
                    args=[task.id], id=f"task_{task.id}", replace_existing=True,
                )
            else:
                logger.warning("Unknown trigger type: %s", t_type)
        except Exception as exc:
            logger.error("Failed to schedule task %s: %s", task.id, exc)

    def _remove_job(self, task_id: str) -> None:
        for job_id in (f"task_{task_id}", f"task_expire_{task_id}"):
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

    def _run_task_async(self, task_id: str) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self._execute_task(task_id))

    def _poll_time_window(self, task_id: str) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self._check_time_window(task_id))
```

- [ ] **Step 4: Run tests**

```
cd hiris && pytest ../tests/test_task_engine.py -v
```
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/task_engine.py tests/test_task_engine.py
git commit -m "feat: TaskEngine core — Task dataclass, persist, add, cancel, list, cleanup"
```

---

## Task 2: Condition evaluator + action executor

**Files:**
- Modify: `hiris/app/task_engine.py` (add `_evaluate_condition`, `_execute_task`, `_check_time_window`)
- Modify: `tests/test_task_engine.py` (add execution tests)

- [ ] **Step 1: Add execution tests**

Add these tests at the bottom of `tests/test_task_engine.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_evaluate_condition_numeric_lt_passes(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "15.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is True


@pytest.mark.asyncio
async def test_evaluate_condition_numeric_lt_fails(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "22.0"})
    assert engine._evaluate_condition(
        {"entity_id": "sensor.temp", "operator": "<", "value": 19}
    ) is False


@pytest.mark.asyncio
async def test_evaluate_condition_string_eq(engine, mock_cache):
    mock_cache.get_state = MagicMock(return_value={"state": "on"})
    assert engine._evaluate_condition(
        {"entity_id": "binary_sensor.door", "operator": "=", "value": "on"}
    ) is True


@pytest.mark.asyncio
async def test_evaluate_condition_entity_missing(engine, mock_cache):
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
        "actions": [{"type": "call_ha_service", "domain": "light", "service": "turn_on", "data": {}}],
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd hiris && pytest ../tests/test_task_engine.py::test_execute_task_done_on_success -v
```
Expected: `AttributeError: 'TaskEngine' object has no attribute '_execute_task'`

- [ ] **Step 3: Add `_evaluate_condition`, `_execute_task`, `_check_time_window` to `task_engine.py`**

Add these methods inside the `TaskEngine` class, after `_poll_time_window`:

```python
    # ── Condition evaluation ────────────────────────────────────────────────

    def _evaluate_condition(self, condition: dict) -> bool:
        if not condition:
            return True
        if self._cache is None:
            return True
        entity_id = condition["entity_id"]
        operator = condition["operator"]
        threshold = condition["value"]
        state_data = self._cache.get_state(entity_id)
        if state_data is None:
            return False
        raw_state = state_data.get("state", "")
        try:
            actual_num = float(raw_state)
            threshold_num = float(threshold)
            if operator == "<":
                return actual_num < threshold_num
            if operator == "<=":
                return actual_num <= threshold_num
            if operator == ">":
                return actual_num > threshold_num
            if operator == ">=":
                return actual_num >= threshold_num
        except (ValueError, TypeError):
            pass
        if operator in ("=", "=="):
            return str(raw_state) == str(threshold)
        if operator == "!=":
            return str(raw_state) != str(threshold)
        return False

    # ── Execution ──────────────────────────────────────────────────────────

    async def _execute_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None or task.status != "pending":
            return
        task.status = "running"
        task.executed_at = datetime.now(timezone.utc).isoformat()
        if task.condition and not self._evaluate_condition(task.condition):
            task.status = "skipped"
            task.result = "Condition not met"
            self._remove_job(task_id)
            self._save()
            logger.info("Task %s skipped (condition not met)", task.label)
            return
        results = []
        try:
            for action in task.actions:
                action_result = await self._run_action(action, task)
                results.append(str(action_result))
            task.status = "done"
            task.result = "; ".join(results)
            logger.info("Task %s done", task.label)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            logger.error("Task %s failed: %s", task.label, exc)
        finally:
            self._remove_job(task_id)
            self._save()

    async def _run_action(self, action: dict, task: Task) -> Any:
        a_type = action.get("type")
        if a_type == "call_ha_service":
            return await self._ha.call_service(
                action["domain"], action["service"], action.get("data", {})
            )
        if a_type == "send_notification":
            from .tools.notify_tools import send_notification
            return await send_notification(
                self._ha, action["message"], action.get("channel", "ha_push"), self._notify_config
            )
        if a_type == "create_task":
            child = self.add_task(action["task"], agent_id=task.agent_id, parent_task_id=task.id)
            return f"created child task {child.id}"
        raise ValueError(f"Unknown action type: {a_type!r}")

    async def _check_time_window(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None or task.status != "pending":
            self._remove_job(task_id)
            return
        trigger = task.trigger
        now = datetime.now(timezone.utc)
        from_h, from_m = (int(x) for x in trigger["from"].split(":"))
        to_h, to_m = (int(x) for x in trigger["to"].split(":"))
        from_dt = now.replace(hour=from_h, minute=from_m, second=0, microsecond=0)
        to_dt = now.replace(hour=to_h, minute=to_m, second=0, microsecond=0)
        if now > to_dt:
            task.status = "expired"
            task.executed_at = now.isoformat()
            task.result = "Time window expired without condition being met"
            self._remove_job(task_id)
            self._save()
            return
        if now < from_dt:
            return
        if task.condition and not self._evaluate_condition(task.condition):
            return
        await self._execute_task(task_id)
```

- [ ] **Step 4: Run all task engine tests**

```
cd hiris && pytest ../tests/test_task_engine.py -v
```
Expected: all 19 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/task_engine.py tests/test_task_engine.py
git commit -m "feat: TaskEngine — condition evaluator, action executor, time_window poller"
```

---

## Task 3: Claude tool definitions + wrappers

**Files:**
- Create: `hiris/app/tools/task_tools.py`
- Create: `tests/test_task_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_task_tools.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd hiris && pytest ../tests/test_task_tools.py -v 2>&1 | head -5
```
Expected: `ImportError: cannot import name 'CREATE_TASK_TOOL_DEF'`

- [ ] **Step 3: Write `task_tools.py`**

```python
# hiris/app/tools/task_tools.py
from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..task_engine import TaskEngine

CREATE_TASK_TOOL_DEF = {
    "name": "create_task",
    "description": (
        "Schedule a deferred task with a trigger, optional condition, and a list of actions. "
        "Returns the created task ID. "
        "Trigger types: "
        "'delay' (minutes from now, e.g. {type: delay, minutes: 30}), "
        "'at_time' (today at HH:MM, e.g. {type: at_time, time: '18:00'}), "
        "'at_datetime' (ISO datetime, e.g. {type: at_datetime, datetime: '2026-04-23T18:00:00'}), "
        "'time_window' (poll every N min between HH:MM and HH:MM, "
        "e.g. {type: time_window, from: '18:00', to: '20:00', check_interval_minutes: 5}). "
        "Condition (optional): {entity_id, operator (<|<=|>|>=|=|!=), value}. "
        "Action types: "
        "call_ha_service ({type: call_ha_service, domain, service, data}), "
        "send_notification ({type: send_notification, message, channel: ha_push|telegram}), "
        "create_task ({type: create_task, task: {...}}) for chaining. "
        "HA scripts: use call_ha_service with domain='script', service='<script_name>'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Human-readable description of the task"},
            "trigger": {"type": "object", "description": "Trigger definition"},
            "actions": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of actions to execute in sequence",
            },
            "condition": {
                "type": "object",
                "description": "Optional condition checked at trigger time: {entity_id, operator, value}",
            },
            "one_shot": {
                "type": "boolean",
                "description": "Remove task after execution (default true)",
                "default": True,
            },
        },
        "required": ["label", "trigger", "actions"],
    },
}

LIST_TASKS_TOOL_DEF = {
    "name": "list_tasks",
    "description": (
        "List scheduled tasks. Returns active tasks (pending, running) and recent completed "
        "tasks (done/failed/skipped in the last 24h). "
        "Optionally filter by agent_id or status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Filter by agent ID (optional)"},
            "status": {
                "type": "string",
                "description": "Filter by status: pending|running|done|skipped|failed|expired|cancelled",
            },
        },
    },
}

CANCEL_TASK_TOOL_DEF = {
    "name": "cancel_task",
    "description": "Cancel a pending task by ID. Returns error if the task is already running or completed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID to cancel"},
        },
        "required": ["task_id"],
    },
}


def create_task_tool(
    task_engine: "TaskEngine",
    label: str,
    trigger: dict,
    actions: list,
    condition: dict | None = None,
    one_shot: bool = True,
    agent_id: str = "hiris-default",
) -> dict:
    task = task_engine.add_task(
        {"label": label, "trigger": trigger, "actions": actions,
         "condition": condition, "one_shot": one_shot},
        agent_id=agent_id,
    )
    return {"task_id": task.id, "label": task.label, "status": task.status}


def list_tasks_tool(
    task_engine: "TaskEngine",
    agent_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    return task_engine.list_tasks(agent_id=agent_id, status=status)


def cancel_task_tool(task_engine: "TaskEngine", task_id: str) -> dict:
    success = task_engine.cancel_task(task_id)
    if success:
        return {"cancelled": True, "task_id": task_id}
    return {"error": f"Task {task_id!r} not found or not in pending state"}
```

- [ ] **Step 4: Run tests**

```
cd hiris && pytest ../tests/test_task_tools.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add hiris/app/tools/task_tools.py tests/test_task_tools.py
git commit -m "feat: task_tools — Claude tool defs and wrappers for create/list/cancel"
```

---

## Task 4: Wire `TaskEngine` into `ClaudeRunner`

**Files:**
- Modify: `hiris/app/claude_runner.py`
- Modify: `tests/test_api.py` (add 2 tests)

- [ ] **Step 1: Write failing tests — add at bottom of `tests/test_api.py`**

```python
@pytest.mark.asyncio
async def test_create_task_tool_via_chat(client):
    from hiris.app.agent_engine import DEFAULT_AGENT_ID, Agent
    from hiris.app.task_engine import TaskEngine
    from unittest.mock import MagicMock, AsyncMock

    engine = client.app["engine"]
    engine._agents[DEFAULT_AGENT_ID] = Agent(
        id=DEFAULT_AGENT_ID, name="HIRIS", type="chat",
        trigger={"type": "manual"}, system_prompt="test",
        allowed_tools=["create_task"], enabled=True, is_default=True,
    )

    mock_task_engine = MagicMock()
    from hiris.app.task_engine import Task
    from datetime import datetime, timezone
    fake_task = Task(
        id="t-001", label="Test", agent_id=DEFAULT_AGENT_ID,
        created_at=datetime.now(timezone.utc).isoformat(),
        trigger={"type": "delay", "minutes": 5}, actions=[],
    )
    mock_task_engine.add_task = MagicMock(return_value=fake_task)
    client.app["task_engine"] = mock_task_engine

    runner = client.app["claude_runner"]
    runner.set_task_engine(mock_task_engine)
    runner.chat = AsyncMock(return_value="Task scheduled")

    resp = await client.post("/api/chat", json={"message": "schedule something"})
    assert resp.status == 200


@pytest.mark.asyncio
async def test_list_tasks_api_empty(client):
    from hiris.app.task_engine import TaskEngine
    mock_te = MagicMock()
    mock_te.list_tasks = MagicMock(return_value=[])
    client.app["task_engine"] = mock_te
    resp = await client.get("/api/tasks")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd hiris && pytest ../tests/test_api.py::test_list_tasks_api_empty -v 2>&1 | head -10
```
Expected: `404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Add `set_task_engine` to `ClaudeRunner` and wire 3 tool dispatchers**

In `hiris/app/claude_runner.py`, make these changes:

**3a. Add imports at top of file (after existing tool imports):**

```python
from .tools.task_tools import (
    create_task_tool, list_tasks_tool, cancel_task_tool,
    CREATE_TASK_TOOL_DEF, LIST_TASKS_TOOL_DEF, CANCEL_TASK_TOOL_DEF,
)
```

**3b. Add 3 task tool defs to `ALL_TOOL_DEFS` list (after `CALL_SERVICE_TOOL_DEF`):**

```python
ALL_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    SEARCH_ENTITIES_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
    ENERGY_TOOL,
    WEATHER_TOOL,
    NOTIFY_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
    CALL_SERVICE_TOOL_DEF,
    CREATE_TASK_TOOL_DEF,
    LIST_TASKS_TOOL_DEF,
    CANCEL_TASK_TOOL_DEF,
]
```

**3c. Add `set_task_engine` method and `_task_engine` attribute to `ClaudeRunner.__init__`:**

In `__init__`, after `self._semantic_map = semantic_map`, add:
```python
        self._task_engine = None
```

After `__init__`, add:
```python
    def set_task_engine(self, engine: Any) -> None:
        self._task_engine = engine
```

**3d. Pass `agent_id` to `_dispatch_tool` in `chat()` method:**

Find the line `result = await self._dispatch_tool(` in `chat()` and change to:

```python
                        result = await self._dispatch_tool(
                            block.name, block.input,
                            allowed_entities=allowed_entities,
                            allowed_services=allowed_services,
                            agent_id=agent_id,
                        )
```

**3e. Add `agent_id` parameter to `_dispatch_tool` signature:**

Change:
```python
    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
    ) -> Any:
```
To:
```python
    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        agent_id: Optional[str] = None,
    ) -> Any:
```

**3f. Add task tool dispatch at end of `_dispatch_tool`, before the final `logger.warning("Unknown tool")`:**

```python
            if name == "create_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return create_task_tool(
                    task_engine=self._task_engine,
                    label=inputs["label"],
                    trigger=inputs["trigger"],
                    actions=inputs["actions"],
                    condition=inputs.get("condition"),
                    one_shot=inputs.get("one_shot", True),
                    agent_id=agent_id or "hiris-default",
                )
            if name == "list_tasks":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return list_tasks_tool(
                    task_engine=self._task_engine,
                    agent_id=inputs.get("agent_id"),
                    status=inputs.get("status"),
                )
            if name == "cancel_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return cancel_task_tool(
                    task_engine=self._task_engine,
                    task_id=inputs["task_id"],
                )
```

- [ ] **Step 4: Run tests**

```
cd hiris && pytest ../tests/test_api.py::test_create_task_tool_via_chat ../tests/test_task_tools.py -v
```
Expected: both tests PASS (note: `test_list_tasks_api_empty` needs the route — handled in Task 6)

- [ ] **Step 5: Commit**

```bash
git add hiris/app/claude_runner.py
git commit -m "feat: wire create_task/list_tasks/cancel_task into ClaudeRunner dispatch"
```

---

## Task 5: REST API handlers

**Files:**
- Create: `hiris/app/api/handlers_tasks.py`
- Create: `tests/test_api_tasks.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api_tasks.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd hiris && pytest ../tests/test_api_tasks.py -v 2>&1 | head -10
```
Expected: `404` for all routes (not yet registered)

- [ ] **Step 3: Write `handlers_tasks.py`**

```python
# hiris/app/api/handlers_tasks.py
from dataclasses import asdict
from aiohttp import web


async def handle_list_tasks(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response([])
    agent_id = request.rel_url.query.get("agent_id")
    status = request.rel_url.query.get("status")
    tasks = task_engine.list_tasks(agent_id=agent_id or None, status=status or None)
    return web.json_response(tasks)


async def handle_get_task(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response({"error": "Not found"}, status=404)
    task = task_engine.get_task(request.match_info["task_id"])
    if task is None:
        return web.json_response({"error": "Not found"}, status=404)
    return web.json_response(asdict(task))


async def handle_cancel_task(request: web.Request) -> web.Response:
    task_engine = request.app.get("task_engine")
    if task_engine is None:
        return web.json_response({"error": "Not found"}, status=404)
    cancelled = task_engine.cancel_task(request.match_info["task_id"])
    if not cancelled:
        return web.json_response({"error": "Task not found or not cancellable"}, status=404)
    return web.Response(status=204)
```

- [ ] **Step 4: Run tests**

```
cd hiris && pytest ../tests/test_api_tasks.py -v
```
Expected: all 6 tests FAIL (routes not yet registered in `server.py`) — OK for now

- [ ] **Step 5: Commit the handler file**

```bash
git add hiris/app/api/handlers_tasks.py tests/test_api_tasks.py
git commit -m "feat: REST handlers for task list/get/cancel"
```

---

## Task 6: Wire `TaskEngine` in `server.py` + register routes

**Files:**
- Modify: `hiris/app/server.py`

- [ ] **Step 1: Add imports and routes to `server.py`**

**1a. Add import at top of `server.py` (after existing handler imports):**

```python
from .api.handlers_tasks import handle_list_tasks, handle_get_task, handle_cancel_task
from .task_engine import TaskEngine
```

**1b. In `_on_startup`, after the `engine = AgentEngine(...)` block and `await engine.start()`, add:**

```python
    tasks_data_path = os.environ.get("TASKS_DATA_PATH", "/data/tasks.json")
    task_engine = TaskEngine(
        ha_client=ha_client,
        entity_cache=entity_cache,
        notify_config=notify_config,
        data_path=tasks_data_path,
    )
    await task_engine.start()
    app["task_engine"] = task_engine
```

**1c. In `_on_startup`, after `engine.set_claude_runner(router)`, add:**

```python
        runner.set_task_engine(task_engine)
```

**1d. In `_on_cleanup`, add `task_engine` stop:**

```python
async def _on_cleanup(app: web.Application) -> None:
    if "task_engine" in app:
        await app["task_engine"].stop()
    await app["engine"].stop()
    await app["ha_client"].stop()
```

**1e. In `create_app()`, add 3 routes after the agent routes:**

```python
    app.router.add_get("/api/tasks", handle_list_tasks)
    app.router.add_get("/api/tasks/{task_id}", handle_get_task)
    app.router.add_delete("/api/tasks/{task_id}", handle_cancel_task)
```

- [ ] **Step 2: Run all tests**

```
cd hiris && pytest ../tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all existing tests pass + all 6 `test_api_tasks.py` tests pass

- [ ] **Step 3: Commit**

```bash
git add hiris/app/server.py
git commit -m "feat: wire TaskEngine in server.py startup + register /api/tasks routes"
```

---

## Task 7: UI — Task section in `index.html`

**Files:**
- Modify: `hiris/app/static/index.html`

The goal: add a "Task" tab in the sidebar that shows active tasks (pending/running) and recent completed tasks (done/failed/skipped in last 24h). Badge with count in sidebar. Auto-refresh every 30s.

- [ ] **Step 1: Add CSS variables and task-specific styles**

In `index.html`, find the `</style>` closing tag. Add immediately before it:

```css
    /* ── Task section ─────────────────────────────── */
    .task-badge {
      display: inline-flex; align-items: center; justify-content: center;
      min-width: 18px; height: 18px; border-radius: 9px;
      background: var(--accent); color: #fff;
      font-size: 11px; font-weight: 700; padding: 0 5px; margin-left: 6px;
    }
    .task-badge:empty, .task-badge[data-count="0"] { display: none; }
    .task-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 14px; margin-bottom: 8px;
    }
    .task-card-header {
      display: flex; align-items: center; justify-content: space-between;
      gap: 8px; margin-bottom: 4px;
    }
    .task-label { font-weight: 600; font-size: 14px; color: var(--text); flex: 1; }
    .task-status {
      font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 6px;
    }
    .task-status.pending  { background: var(--badge-monitor-bg);    color: var(--badge-monitor-text); }
    .task-status.running  { background: var(--badge-reactive-bg);   color: var(--badge-reactive-text); }
    .task-status.done     { background: var(--badge-reactive-bg);   color: var(--badge-reactive-text); }
    .task-status.skipped  { background: var(--badge-off-bg);        color: var(--text-muted); }
    .task-status.failed   { background: #FEE2E2;                    color: #DC2626; }
    .task-status.expired  { background: var(--badge-off-bg);        color: var(--text-muted); }
    .task-status.cancelled{ background: var(--badge-off-bg);        color: var(--text-muted); }
    .task-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
    .task-cancel-btn {
      background: none; border: 1px solid var(--border); color: var(--text-muted);
      border-radius: 6px; padding: 3px 10px; font-size: 12px; cursor: pointer;
    }
    .task-cancel-btn:hover { background: var(--surface-hover); color: var(--text); }
    .task-section-title {
      font-size: 12px; font-weight: 700; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: 0.06em; margin: 16px 0 8px;
    }
    #task-panel { display: none; flex-direction: column; flex: 1; overflow-y: auto; padding: 16px; }
    #task-panel.active { display: flex; }
    .task-empty { color: var(--text-muted); font-size: 14px; text-align: center; padding: 32px 0; }
```

- [ ] **Step 2: Add Task nav item to sidebar**

Find the sidebar nav. Look for the line with the "Config" nav link (contains `/config` href or similar). Add a new nav item for Tasks in the same sidebar. Find the `<nav` element in the sidebar and add after the existing nav items:

```html
          <a href="#" class="nav-item" id="nav-tasks" onclick="showPanel('tasks'); return false;">
            Task
            <span class="task-badge" id="task-badge" data-count="0"></span>
          </a>
```

- [ ] **Step 3: Add task panel HTML**

Find the main content area where the chat panel sits. Add after the closing `</div>` of the chat panel or agent panel, a new task panel:

```html
      <!-- Task panel -->
      <div id="task-panel">
        <div class="task-section-title">Task attive</div>
        <div id="task-active-list"></div>
        <div class="task-section-title">Task recenti (24h)</div>
        <div id="task-recent-list"></div>
      </div>
```

- [ ] **Step 4: Add `showPanel` and task JavaScript**

Find the `<script>` block in `index.html`. Add `tasks` to the `showPanel` function logic, then add the task-specific functions. Find where `showPanel` or panel switching is defined and add:

```javascript
    function showPanel(name) {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      const panel = document.getElementById(name + '-panel');
      const nav = document.getElementById('nav-' + name);
      if (panel) panel.classList.add('active');
      if (nav) nav.classList.add('active');
      if (name === 'tasks') loadTasks();
    }

    function formatTrigger(trigger) {
      if (!trigger) return '';
      if (trigger.type === 'delay') return `tra ${trigger.minutes} min`;
      if (trigger.type === 'at_time') return `alle ${trigger.time}`;
      if (trigger.type === 'at_datetime') return trigger.datetime;
      if (trigger.type === 'time_window') return `finestra ${trigger.from}–${trigger.to}`;
      return trigger.type;
    }

    function renderTask(task) {
      const isPending = task.status === 'pending';
      const cancelBtn = isPending
        ? `<button class="task-cancel-btn" onclick="cancelTask('${task.id}')">Annulla</button>`
        : '';
      const meta = task.result || task.error || formatTrigger(task.trigger);
      return `
        <div class="task-card" id="task-${task.id}">
          <div class="task-card-header">
            <span class="task-label">${task.label}</span>
            <span class="task-status ${task.status}">${task.status}</span>
            ${cancelBtn}
          </div>
          <div class="task-meta">${meta}</div>
        </div>`;
    }

    async function loadTasks() {
      try {
        const resp = await fetch('/api/tasks');
        const tasks = await resp.json();
        const active = tasks.filter(t => ['pending', 'running'].includes(t.status));
        const recent = tasks.filter(t => !['pending', 'running'].includes(t.status));
        const activeEl = document.getElementById('task-active-list');
        const recentEl = document.getElementById('task-recent-list');
        if (activeEl) activeEl.innerHTML = active.length
          ? active.map(renderTask).join('')
          : '<div class="task-empty">Nessuna task attiva</div>';
        if (recentEl) recentEl.innerHTML = recent.length
          ? recent.map(renderTask).join('')
          : '<div class="task-empty">Nessuna task recente</div>';
        const badge = document.getElementById('task-badge');
        if (badge) {
          badge.textContent = active.length || '';
          badge.dataset.count = active.length;
        }
      } catch (e) { console.error('loadTasks failed', e); }
    }

    async function cancelTask(taskId) {
      if (!confirm('Annullare questa task?')) return;
      try {
        const resp = await fetch(`/api/tasks/${taskId}`, {method: 'DELETE'});
        if (resp.ok || resp.status === 204) loadTasks();
      } catch (e) { console.error('cancelTask failed', e); }
    }

    // Auto-refresh task badge every 30s
    setInterval(() => {
      loadTasks();
    }, 30000);

    // Load badge count on page load
    loadTasks();
```

- [ ] **Step 5: Run all tests to confirm nothing broke**

```
cd hiris && pytest ../tests/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests PASS

- [ ] **Step 6: Also update `_seed_default_agent` to include task tools in the default agent's `allowed_tools`**

In `hiris/app/agent_engine.py`, find `_seed_default_agent` where `Agent` is created with `allowed_tools=[]`. The default agent's `allowed_tools` list is empty (meaning all tools are available — the empty list means no filter in `claude_runner.py`). No change needed — `allowed_tools=[]` in Claude runner means all tools are passed.

Verify this by reading `claude_runner.py` line:
```python
tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
```
`allowed_tools` passed from handlers is `agent.allowed_tools or None` — empty list `[]` becomes `None` → all tools available. No change needed.

- [ ] **Step 7: Commit**

```bash
git add hiris/app/static/index.html
git commit -m "feat: Task UI — sidebar tab, badge, active/recent task lists, auto-refresh"
```

---

## Task 8: Version bump + full test run

**Files:**
- Modify: `hiris/app/server.py` (version string)
- Modify: `hiris/config.yaml`
- Modify: `tests/test_api.py` (version assertion)

- [ ] **Step 1: Run the full test suite**

```
cd hiris && pytest ../tests/ -v 2>&1 | tail -30
```
Expected: all tests PASS

- [ ] **Step 2: Bump version to `0.2.3` in all 3 places**

In `hiris/app/server.py`:
```python
async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": "0.2.3"})
```

In `hiris/config.yaml`:
```yaml
name: "HIRIS"
version: "0.2.3"
```

In `tests/test_api.py` (line `assert data["version"] == "0.2.2"`):
```python
    assert data["version"] == "0.2.3"
```

- [ ] **Step 3: Run tests again to confirm version test passes**

```
cd hiris && pytest ../tests/test_api.py::test_health_endpoint -v
```
Expected: PASS

- [ ] **Step 4: Commit + tag**

```bash
git add hiris/app/server.py hiris/config.yaml tests/test_api.py
git commit -m "chore: bump version to 0.2.3"
git tag v0.2.3
git push origin master --tags
```

---

## Self-review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| 4 trigger types: at_time, delay, at_datetime, time_window | Task 1 (_schedule_task), Task 2 (_check_time_window) |
| Condition optional, operators <,<=,>,>=,=,!= | Task 2 (_evaluate_condition) |
| Actions: call_ha_service, send_notification, create_task chain | Task 2 (_run_action) |
| one_shot flag | Task 1 (Task dataclass, _execute_task removes job) |
| Persistence /data/tasks.json | Task 1 (_save, _load) |
| Reschedule pending on restart | Task 1 (_load calls _schedule_task) |
| Cleanup every hour after 24h | Task 1 (_cleanup + APScheduler job) |
| 3 Claude tools: create_task, list_tasks, cancel_task | Task 3 |
| Tools in ALL_TOOL_DEFS + dispatch | Task 4 |
| agent_id passed to dispatch | Task 4 |
| REST: GET /api/tasks, GET /api/tasks/{id}, DELETE /api/tasks/{id} | Task 5 |
| Server startup wiring | Task 6 |
| UI task tab + badge + auto-refresh | Task 7 |
| script.* via call_ha_service documented | Task 3 (tool description) |

All spec requirements covered. No placeholders. Types consistent across tasks.
