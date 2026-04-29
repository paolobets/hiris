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
    allowed_entities: list | None = None,
    allowed_services: list | None = None,
) -> dict:
    task = task_engine.add_task(
        {"label": label, "trigger": trigger, "actions": actions,
         "condition": condition, "one_shot": one_shot},
        agent_id=agent_id,
        allowed_entities=allowed_entities,
        allowed_services=allowed_services,
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
