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
        except Exception:
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
