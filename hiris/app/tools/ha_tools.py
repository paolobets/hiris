"""Definizioni dei cinque strumenti di lettura sullo stato della casa.

fetta E2 Task 8 ("escono i trentaquattro"): le funzioni esecutrici
(`get_entity_states`, `get_area_entities`, `get_home_status`,
`get_entities_on`, `get_entities_by_domain`) sono uscite -- erano orfane da
quando il `ToolDispatcher` che le chiamava e' uscito (fetta E2 Task 7): nessun
chiamante di produzione le invocava piu', solo i test. Le cinque definizioni
qui sotto restano invece: `EVALUATION_ONLY_TOOLS` (claude_runner.py), l'unico
catalogo rimasto in piedi -- lo usa la Sentinella -- le nomina tutte e cinque.
"""
from __future__ import annotations

TOOL_DEF = {
    "name": "get_entity_states",
    "description": "Get current state of specific Home Assistant entities by ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of entity IDs to query.",
            }
        },
        "required": ["ids"],
    },
}

GET_AREA_ENTITIES_TOOL_DEF = {
    "name": "get_area_entities",
    "description": (
        "Discover all Home Assistant areas (rooms/zones) and their assigned entities. "
        "Returns a dict mapping area_name -> [entity_ids]. "
        "Entities without an area are listed under '__no_area__'. "
        "Use this when the user refers to a room (e.g. 'kitchen lights', "
        "'turn off everything in the living room')."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_HOME_STATUS_TOOL_DEF = {
    "name": "get_home_status",
    "description": (
        "Get a compact summary of all useful home entities (excludes noise domains "
        "like buttons, updates). Use this as the first call to understand the current home state."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_ENTITIES_ON_TOOL_DEF = {
    "name": "get_entities_on",
    "description": "Get all entities currently in 'on' state (lights, switches, etc.).",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_ENTITIES_BY_DOMAIN_TOOL_DEF = {
    "name": "get_entities_by_domain",
    "description": "Get all entities for a specific domain (e.g. 'light', 'sensor', 'switch').",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Entity domain, e.g. 'light'"},
        },
        "required": ["domain"],
    },
}
