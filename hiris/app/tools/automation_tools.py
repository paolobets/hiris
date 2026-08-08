"""Definizioni degli strumenti di lettura sulle automazioni.

fetta E2 Task 8: `get_ha_automations`/`get_automation_config` (le funzioni
esecutrici) e le definizioni `trigger_automation`/`toggle_automation` (che
ATTUANO, quindi non fanno parte di `EVALUATION_ONLY_TOOLS` per costruzione --
vedi claude_runner.py) sono uscite. Le funzioni erano orfane dal Task 7 (il
`ToolDispatcher` che le chiamava e' uscito): nessun chiamante di produzione le
invocava piu'. Le due definizioni di sola lettura restano: sono nominate da
`EVALUATION_ONLY_TOOLS`, l'unico catalogo rimasto in piedi -- lo usa la
Sentinella.
"""
from __future__ import annotations

GET_AUTOMATIONS_TOOL_DEF = {
    "name": "get_ha_automations",
    "description": "List all Home Assistant automations with their state (enabled/disabled).",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

GET_AUTOMATION_CONFIG_TOOL_DEF = {
    "name": "get_automation_config",
    "description": (
        "Read the full configuration (YAML-equivalent) of a Home Assistant "
        "automation created via the HA UI. Pass its entity_id (automation.foo), "
        "object_id (foo), or numeric id. Use get_ha_automations first to list them. "
        "Returns an error for automations defined by hand in YAML."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "automation_id": {"type": "string",
                              "description": "entity_id, object_id, or numeric unique id"},
        },
        "required": ["automation_id"],
    },
}
