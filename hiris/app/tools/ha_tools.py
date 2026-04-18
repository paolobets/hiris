from typing import Any
from ..proxy.ha_client import HAClient

TOOL_DEF = {
    "name": "get_entity_states",
    "description": "Get current states of one or more Home Assistant entities. Returns state, attributes, and last_changed for each entity.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of entity IDs, e.g. ['light.living_room', 'sensor.temperature']",
            }
        },
        "required": ["ids"],
    },
}


async def get_entity_states(ha: HAClient, ids: list[str]) -> dict[str, Any]:
    states = await ha.get_states(ids)
    return {
        s["entity_id"]: {
            "state": s["state"],
            "attributes": s.get("attributes", {}),
            "last_changed": s.get("last_changed", ""),
        }
        for s in states
    }
