from __future__ import annotations
from typing import Any

GET_HA_HEALTH_TOOL_DEF = {
    "name": "get_ha_health",
    "description": (
        "Get a structured health report of the Home Assistant system. "
        "Returns cached data updated in real-time (WebSocket) and every 30 minutes. "
        "Sections: 'unavailable' (entities in unavailable/unknown state), "
        "'integrations' (config entries with errors), "
        "'logs' (error log summary with top errors), "
        "'updates' (available updates for HA core and integrations), "
        "'system' (HA version, config state). "
        "Use 'all' to include everything. After showing the report, suggest "
        "possible fixes for any issues found."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["unavailable", "integrations", "logs", "updates", "system", "all"],
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
