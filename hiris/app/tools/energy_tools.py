from ..proxy.ha_client import HAClient

ENERGY_ENTITY_IDS = [
    "sensor.energy_consumption",
    "sensor.solar_production",
    "sensor.grid_import",
    "sensor.grid_export",
]

TOOL_DEF = {
    "name": "get_energy_history",
    "description": "Get energy consumption and production history for the last N days from Home Assistant.",
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


async def get_energy_history(ha: HAClient, days: int) -> list[dict]:
    return await ha.get_history(entity_ids=ENERGY_ENTITY_IDS, days=days)
