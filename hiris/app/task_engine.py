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
