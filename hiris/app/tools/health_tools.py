from __future__ import annotations
from typing import Any

GET_HA_HEALTH_TOOL_DEF = {
    "name": "get_ha_health",
    "description": (
        "Get a structured health report of the Home Assistant system. "
        "Returns cached data updated in real-time (WebSocket) and every 30 minutes. "
        "Sections: 'unavailable' (entities NOT RESPONDING RIGHT NOW -- "
        "unavailable/unknown state -- each with 'since', the moment Home "
        "Assistant recorded the drop; a brief drop after an HA restart shows "
        "up here too, while the Brain's advisories only cover entities missing "
        "for more than two days and are always a subset of this list), "
        "'integrations' (config entries with errors), "
        "'logs' (error log summary with top errors), "
        "'updates' (available updates for HA core and integrations), "
        "'system' (HA version, config state), "
        "'system_health' (native per-integration health: database, cloud, ...), "
        "'supervisor' (add-on states, host disk space, available updates for "
        "core/OS/Supervisor/add-ons; absent on installations without Supervisor). "
        "Use 'all' to include everything. Sections are capped: if the response "
        "contains 'truncated', that section was shortened -- always tell the user "
        "the real total reported there ('shown' of 'total'), and note the 'order' "
        "field when present ('unavailable' shows the most recently failed "
        "entities first, so older failures may be omitted). Read-only: this tool "
        "cannot start, stop or update anything. After showing the report, suggest "
        "possible fixes for any issues found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "unavailable", "integrations", "logs", "updates", "system",
                        "system_health", "supervisor", "all",
                    ],
                },
                "default": ["all"],
                "description": "Sections to include. Use ['all'] for the full report.",
            }
        },
        "required": [],
    },
}


def get_ha_health(health_monitor: Any, sections: list[str] | None) -> dict:
    if health_monitor is None:
        return {"error": "HealthMonitor not available — check server startup logs"}
    return health_monitor.get_snapshot(sections or ["all"])
