"""Definizione dello strumento di lettura della cronologia energetica.

fetta E2 Task 8: `get_energy_history` e `_compress_energy_history` (le
funzioni esecutrici) sono uscite -- orfane dal Task 7 (il `ToolDispatcher` che
le chiamava e' uscito), nessun chiamante di produzione le invocava piu'. La
definizione resta: e' nominata da `EVALUATION_ONLY_TOOLS` (claude_runner.py),
l'unico catalogo rimasto in piedi -- lo usa la Sentinella.
"""
from __future__ import annotations

TOOL_DEF = {
    "name": "get_energy_history",
    "description": (
        "Get energy history for the last N days. "
        "Returns compressed daily records: "
        "[{id, day (YYYY-MM-DD), start (first reading), end (last reading), n (samples)}]. "
        "Use start/end to compute daily delta. "
        "Source entities: consumption meters, solar production, grid import/export."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days of history to retrieve (1-30)",
                "minimum": 1,
                "maximum": 30,
            }
        },
        "required": ["days"],
    },
}
