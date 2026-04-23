from __future__ import annotations
from ..proxy.ha_client import HAClient
from ..proxy.entity_cache import EntityCache

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


async def get_entity_states(
    ha: HAClient,
    ids: list[str],
    entity_cache: EntityCache | None = None,
) -> list[dict]:
    if entity_cache is not None:
        return entity_cache.get_minimal(ids)
    states = await ha.get_states(ids)
    result = []
    for s in states:
        eid = s.get("entity_id", "unknown")
        attrs = s.get("attributes") or {}
        result.append({
            "id": eid,
            "state": s.get("state", "unknown"),
            "name": attrs.get("friendly_name") or "",
            "unit": attrs.get("unit_of_measurement") or "",
        })
    return result


async def get_area_entities(
    ha: HAClient,
    entity_cache: EntityCache | None = None,
) -> dict[str, list[str]]:
    """Return area→[entity_id] map. Uses EntityCache if populated, else HTTP fallback."""
    if entity_cache is not None:
        cached = entity_cache.get_area_map()
        if cached is not None:
            return cached

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


def get_home_status(entity_cache, semantic_map=None) -> list[dict]:
    """Return all useful entity states, enriched with semantic labels if map is available."""
    entities = entity_cache.get_all_useful() if entity_cache else []
    if semantic_map is None:
        return entities
    enriched = []
    for e in entities:
        eid = e["id"]
        meta = semantic_map.get_entity_meta(eid)
        if meta and meta.get("label"):
            e = dict(e)
            e["semantic_label"] = meta["label"]
            e["semantic_role"] = meta.get("role", "")
        enriched.append(e)
    return enriched


def get_entities_on(entity_cache: EntityCache) -> list[dict]:
    return entity_cache.get_on()


def get_entities_by_domain(domain: str, entity_cache: EntityCache) -> list[dict]:
    return entity_cache.get_by_domain(domain)
