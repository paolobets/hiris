import logging
import re
from datetime import datetime, timezone, timedelta
from ..proxy.ha_client import HAClient

_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
logger = logging.getLogger(__name__)

GET_CALENDAR_EVENTS_TOOL_DEF = {
    "name": "get_calendar_events",
    "description": (
        "Get upcoming calendar events from Home Assistant calendar integrations. "
        "Returns events across all calendars (or a specific one) within the next N hours."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "Number of hours ahead to fetch events (1–168, default 24).",
                "minimum": 1,
                "maximum": 168,
            },
            "calendar_entity": {
                "type": "string",
                "description": "Specific calendar entity ID (e.g. 'calendar.home'). Omit to fetch all calendars.",
            },
        },
        "required": [],
    },
}


async def get_calendar_events(
    ha: HAClient,
    hours: int = 24,
    calendar_entity: str | None = None,
) -> list[dict]:
    """Fetch upcoming events from HA calendar integrations.

    Args:
        ha: HAClient instance for Home Assistant REST API calls.
        hours: Number of hours ahead to fetch events (1–168, clamped).
        calendar_entity: Specific calendar entity ID, or None to fetch all calendars.

    Returns:
        List of event dicts, each augmented with a ``calendar`` key, sorted by start time.
    """
    hours = max(1, min(168, int(hours)))
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    start_str = now.isoformat()
    end_str = end.isoformat()

    if calendar_entity:
        entity_ids = [calendar_entity]
    else:
        try:
            cals = await ha.get_calendars()
            entity_ids = [c["entity_id"] for c in cals if "entity_id" in c]
        except Exception as exc:
            logger.warning("get_calendars failed: %s", exc)
            entity_ids = []

    events: list[dict] = []
    for eid in entity_ids:
        try:
            raw = await ha.get_calendar_events_range(eid, start_str, end_str)
            for ev in raw:
                ev["calendar"] = eid
                events.append(ev)
        except Exception:
            continue

    events.sort(
        key=lambda e: (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date") or ""
    )
    return events


SET_INPUT_HELPER_TOOL_DEF = {
    "name": "set_input_helper",
    "description": (
        "Set the value of a Home Assistant input helper entity "
        "(input_boolean, input_number, input_text, or input_select). "
        "Use this to update variables, toggles, sliders, or dropdowns managed in HA."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "Full entity ID of the input helper (e.g. 'input_boolean.guest_mode', 'input_number.target_temp').",
            },
            "value": {
                "description": "New value. For input_boolean: true/false or 'on'/'off'. For input_number: a number. For input_text: a string. For input_select: the option label string.",
            },
        },
        "required": ["entity_id", "value"],
    },
}


async def set_input_helper(ha: HAClient, entity_id: str, value) -> dict:
    """Set value on an HA input helper entity, dispatching the correct service per domain.

    Args:
        ha: HAClient instance for Home Assistant REST API calls.
        entity_id: Full entity ID of the input helper (e.g. 'input_boolean.guest_mode').
        value: New value. Semantics depend on the domain:
            - input_boolean: bool or truthy/falsy string ('on'/'off'/'true'/'false').
            - input_number: numeric value (int or float).
            - input_text: any string value.
            - input_select: option label string.

    Returns:
        Dict with ``entity_id``, ``service``, and ``ok: True`` on success,
        or ``{"error": ...}`` on validation or call failure.
    """
    if not _ENTITY_ID_RE.match(entity_id):
        return {"error": f"Invalid entity_id format: {entity_id!r}"}

    domain = entity_id.split(".")[0]
    supported = {"input_boolean", "input_number", "input_text", "input_select"}
    if domain not in supported:
        return {"error": f"Unsupported domain {domain!r}. Supported: {sorted(supported)}"}

    data: dict = {"entity_id": entity_id}

    if domain == "input_boolean":
        if isinstance(value, bool):
            service = "turn_on" if value else "turn_off"
        elif str(value).lower() in ("true", "on", "1", "yes"):
            service = "turn_on"
        else:
            service = "turn_off"
    elif domain == "input_number":
        try:
            data["value"] = float(value)
        except (TypeError, ValueError):
            return {"error": f"value must be numeric for input_number, got {value!r}"}
        service = "set_value"
    elif domain == "input_text":
        data["value"] = str(value)
        service = "set_value"
    elif domain == "input_select":
        data["option"] = str(value)
        service = "select_option"

    ok = await ha.call_service(domain, service, data)
    if ok:
        return {"entity_id": entity_id, "service": f"{domain}.{service}", "ok": True}
    return {"error": f"call_service {domain}.{service} failed"}


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CREATE_CALENDAR_EVENT_TOOL_DEF = {
    "name": "create_calendar_event",
    "description": (
        "Create a calendar event in a Home Assistant calendar integration. "
        "Supports timed events (start_date_time/end_date_time) and all-day events (start_date/end_date). "
        "For all-day events, end_date is EXCLUSIVE (set it to the day after the last day of the event)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "calendar_entity": {
                "type": "string",
                "description": "Calendar entity ID (e.g. 'calendar.home'). Required.",
            },
            "summary": {
                "type": "string",
                "description": "Event title/summary.",
            },
            "event_type": {
                "type": "string",
                "enum": ["datetime", "allday"],
                "description": (
                    "Event type. Use 'datetime' with start_date_time/end_date_time; "
                    "use 'allday' with start_date/end_date."
                ),
            },
            "start_date_time": {
                "type": "string",
                "description": "Start datetime ISO 8601 (e.g. '2025-06-01T10:00:00'). Required for datetime events.",
            },
            "end_date_time": {
                "type": "string",
                "description": "End datetime ISO 8601. Required for datetime events. Must be after start_date_time.",
            },
            "start_date": {
                "type": "string",
                "description": "Start date YYYY-MM-DD. Required for all-day events.",
            },
            "end_date": {
                "type": "string",
                "description": "End date YYYY-MM-DD (exclusive). Required for all-day events.",
            },
            "description": {
                "type": "string",
                "description": "Optional event description/notes.",
            },
            "location": {
                "type": "string",
                "description": "Optional event location.",
            },
        },
        "required": ["calendar_entity", "summary", "event_type"],
    },
}


async def create_calendar_event(
    ha: HAClient,
    calendar_entity: str,
    summary: str,
    event_type: str,
    start_date_time: str | None = None,
    end_date_time: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    if not _ENTITY_ID_RE.match(calendar_entity):
        return {"error": f"Invalid entity_id format: {calendar_entity!r}"}
    if calendar_entity.split(".")[0] != "calendar":
        return {"error": f"Entity {calendar_entity!r} is not a calendar entity"}
    if event_type not in ("datetime", "allday"):
        return {"error": f"event_type must be 'datetime' or 'allday', got {event_type!r}"}

    data: dict = {"entity_id": calendar_entity, "summary": summary}

    if event_type == "datetime":
        if not start_date_time or not end_date_time:
            return {"error": "start_date_time and end_date_time are required for datetime events"}
        try:
            dt_start = datetime.fromisoformat(start_date_time)
            dt_end = datetime.fromisoformat(end_date_time)
        except ValueError as exc:
            return {"error": f"Invalid datetime format: {exc}"}
        if dt_end <= dt_start:
            return {"error": "end_date_time must be after start_date_time"}
        data["start_date_time"] = start_date_time
        data["end_date_time"] = end_date_time
    else:  # allday
        if not start_date or not end_date:
            return {"error": "start_date and end_date are required for all-day events"}
        if not _DATE_RE.match(start_date) or not _DATE_RE.match(end_date):
            return {"error": "Dates must be in YYYY-MM-DD format"}
        if end_date <= start_date:
            return {"error": "end_date must be after start_date (end_date is exclusive)"}
        data["start_date"] = start_date
        data["end_date"] = end_date

    if description:
        data["description"] = description
    if location:
        data["location"] = location

    ok = await ha.call_service("calendar", "create_event", data)
    if ok:
        return {"ok": True, "calendar": calendar_entity, "summary": summary}
    return {"error": "call_service calendar.create_event failed"}
