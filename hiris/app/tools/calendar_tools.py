from datetime import datetime, timezone, timedelta
from ..proxy.ha_client import HAClient

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
