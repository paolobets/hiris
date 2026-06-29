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


async def get_automation_config(ha: HAClient, automation_id: str) -> dict:
    """Return a UI-managed automation's config dict (or an error dict)."""
    return await ha.get_automation_config(automation_id)
