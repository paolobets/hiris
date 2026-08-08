"""Definizione dello strumento di lettura del calendario.

fetta E2 Task 8: `get_calendar_events` (la funzione esecutrice) e le
definizioni `set_input_helper`/`create_calendar_event` (che ATTUANO, quindi
non fanno parte di `EVALUATION_ONLY_TOOLS` per costruzione -- vedi
claude_runner.py) sono uscite, insieme alle rispettive funzioni. Erano orfane
dal Task 7 (il `ToolDispatcher` che le chiamava e' uscito): nessun chiamante
di produzione le invocava piu'. La definizione di sola lettura resta: e'
nominata da `EVALUATION_ONLY_TOOLS`, l'unico catalogo rimasto in piedi -- lo
usa la Sentinella.
"""
from __future__ import annotations

GET_CALENDAR_EVENTS_TOOL_DEF = {
    "name": "get_calendar_events",
    "description": (
        "Get upcoming calendar events from Home Assistant calendar integrations. "
        "Returns events across all calendars (or a specific one) within the next N hours. "
        "The reply is an object with 'events'. If it also carries 'error' (and "
        "'unavailable_calendars'), one or more calendars could not be read: the list "
        "is incomplete, so tell the user what could not be checked instead of saying "
        "there is nothing scheduled."
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
