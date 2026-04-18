from ..proxy.ha_client import HAClient

GET_AUTOMATIONS_TOOL_DEF = {
    "name": "get_ha_automations",
    "description": "List all Home Assistant automations with their state (enabled/disabled).",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

TRIGGER_TOOL_DEF = {
    "name": "trigger_automation",
    "description": "Immediately trigger a Home Assistant automation by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "automation_id": {"type": "string", "description": "Automation ID (without 'automation.' prefix)"}
        },
        "required": ["automation_id"],
    },
}

TOGGLE_TOOL_DEF = {
    "name": "toggle_automation",
    "description": "Enable or disable a Home Assistant automation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "automation_id": {"type": "string", "description": "Automation ID"},
            "enabled": {"type": "boolean", "description": "True to enable, False to disable"},
        },
        "required": ["automation_id", "enabled"],
    },
}


async def get_ha_automations(ha: HAClient) -> list[dict]:
    """Get list of all Home Assistant automations with their states."""
    return await ha.get_automations()


async def trigger_automation(ha: HAClient, automation_id: str) -> bool:
    """Immediately trigger an automation by calling automation.trigger service."""
    entity_id = f"automation.{automation_id}" if not automation_id.startswith("automation.") else automation_id
    return await ha.call_service("automation", "trigger", {"entity_id": entity_id})


async def toggle_automation(ha: HAClient, automation_id: str, enabled: bool) -> bool:
    """Enable or disable an automation."""
    entity_id = f"automation.{automation_id}" if not automation_id.startswith("automation.") else automation_id
    service = "turn_on" if enabled else "turn_off"
    return await ha.call_service("automation", service, {"entity_id": entity_id})
