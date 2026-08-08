# hiris/app/tools/history_tools.py
"""Definizione dello strumento di lettura dello storico numerico/temporale.

fetta E2 Task 8: `get_history` e tutte le funzioni di supporto (validazione,
aggregazione, downsampling) sono uscite -- orfane dal Task 7 (il
`ToolDispatcher` che le chiamava e' uscito), nessun chiamante di produzione le
invocava piu'. La definizione resta: e' nominata da `EVALUATION_ONLY_TOOLS`
(claude_runner.py), l'unico catalogo rimasto in piedi -- lo usa la Sentinella.
"""
from __future__ import annotations

MAX_ENTITIES = 20
MAX_DAYS = 365
_VALID_RESOLUTION = ("auto", "raw", "hourly", "daily")

GET_HISTORY_TOOL_DEF = {
    "name": "get_history",
    "description": (
        "Historical/time-series data for entities (trends, min/max/avg). READ-only. "
        "Numeric entities return COMPRESSED daily/hourly 'buckets'; non-numeric "
        "entities (on/off) return downsampled 'samples'. Never unbounded raw dumps. "
        "Use for: 'temperature trend last week', 'energy this month', sensor history. "
        "Args: entity_ids (1-20), days (1-365, default 7), "
        "resolution ('auto'|'raw'|'hourly'|'daily')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_ids": {"type": "array", "items": {"type": "string"},
                           "minItems": 1, "maxItems": MAX_ENTITIES},
            "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS},
            "resolution": {"type": "string", "enum": list(_VALID_RESOLUTION)},
        },
        "required": ["entity_ids"],
    },
}
