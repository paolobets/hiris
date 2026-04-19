from typing import Any
from ..proxy.ha_client import HAClient

TOOL_DEF = {
    "name": "get_entity_states",
    "description": (
        "Get current states of one or more Home Assistant entities. "
        "Returns state, attributes, friendly_name, and last_changed for each entity. "
        "Use get_area_entities first if you need to know which entities belong to a room."
    ),
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
            "friendly_name": s.get("attributes", {}).get("friendly_name"),
        }
        for s in states
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


async def get_area_entities(ha: HAClient) -> dict[str, list[str]]:
    areas = await ha.get_area_registry()
    entities = await ha.get_entity_registry()

    area_lookup: dict[str, str] = {a["area_id"]: a["name"] for a in areas}
    result: dict[str, list[str]] = {}
    no_area: list[str] = []

    for entry in entities:
        eid = entry.get("entity_id", "")
        if not eid:
            continue
        area_id = entry.get("area_id")
        if area_id and area_id in area_lookup:
            result.setdefault(area_lookup[area_id], []).append(eid)
        else:
            no_area.append(eid)

    if no_area:
        result["__no_area__"] = no_area

    return result
