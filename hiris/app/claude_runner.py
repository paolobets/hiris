import fnmatch
import json
import logging
from typing import Any, Optional
import anthropic
from .proxy.ha_client import HAClient
from .tools.ha_tools import get_entity_states, TOOL_DEF as HA_TOOL, get_area_entities, GET_AREA_ENTITIES_TOOL_DEF
from .tools.energy_tools import get_energy_history, TOOL_DEF as ENERGY_TOOL
from .tools.weather_tools import get_weather_forecast, TOOL_DEF as WEATHER_TOOL
from .tools.notify_tools import send_notification, TOOL_DEF as NOTIFY_TOOL
from .tools.automation_tools import (
    get_ha_automations, GET_AUTOMATIONS_TOOL_DEF,
    trigger_automation, TRIGGER_TOOL_DEF,
    toggle_automation, TOGGLE_TOOL_DEF,
)

logger = logging.getLogger(__name__)

CALL_SERVICE_TOOL_DEF = {
    "name": "call_ha_service",
    "description": "Call a Home Assistant service to control devices (light, switch, climate, etc.).",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Service domain, e.g. 'light', 'switch'"},
            "service": {"type": "string", "description": "Service name, e.g. 'turn_on', 'turn_off'"},
            "data": {"type": "object", "description": "Service call data, e.g. {entity_id: 'light.living'}"},
        },
        "required": ["domain", "service"],
    },
}

ALL_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    ENERGY_TOOL,
    WEATHER_TOOL,
    NOTIFY_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    TRIGGER_TOOL_DEF,
    TOGGLE_TOOL_DEF,
    CALL_SERVICE_TOOL_DEF,
]

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_TOOL_ITERATIONS = 10

RESTRICT_PROMPT = (
    "Sei HIRIS, assistente per la smart home. "
    "Rispondi SOLO a domande relative alla casa, domotica, energia, clima, sicurezza. "
    "Per qualsiasi altro argomento, rispondi educatamente che non puoi aiutare su quel tema."
)


class ClaudeRunner:
    def __init__(
        self,
        api_key: str,
        ha_client: HAClient,
        notify_config: dict,
        restrict_to_home: bool = False,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._ha = ha_client
        self._notify_config = notify_config
        self._restrict_to_home = restrict_to_home
        self.last_tool_calls: list[dict] = []

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
    ) -> str:
        self.last_tool_calls = []
        effective_system = system_prompt
        if self._restrict_to_home:
            effective_system = f"{system_prompt}\n\n---\n\n{RESTRICT_PROMPT}"
        tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
        messages: list[dict] = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                response = await self._client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=effective_system,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.APIError as exc:
                logger.error("Claude API error: %s", exc)
                return f"Claude API error: {exc}"

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = await self._dispatch_tool(
                            block.name, block.input,
                            allowed_entities=allowed_entities,
                            allowed_services=allowed_services,
                        )
                        self.last_tool_calls.append({"tool": block.name, "input": block.input})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks) if text_blocks else f"Stopped: {response.stop_reason}"

        return "Max tool iterations reached."

    async def _dispatch_tool(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
    ) -> Any:
        logger.info("Tool call: %s(%s)", name, inputs)
        try:
            if name == "get_area_entities":
                return await get_area_entities(self._ha)
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if allowed_entities:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                    logger.info("Filtered entity ids to: %s", ids)
                return await get_entity_states(self._ha, ids)
            if name == "get_energy_history":
                return await get_energy_history(self._ha, inputs["days"])
            if name == "get_weather_forecast":
                return await get_weather_forecast(inputs["hours"])
            if name == "send_notification":
                return await send_notification(self._ha, inputs["message"], inputs["channel"], self._notify_config)
            if name == "get_ha_automations":
                return await get_ha_automations(self._ha)
            if name == "trigger_automation":
                return await trigger_automation(self._ha, inputs["automation_id"])
            if name == "toggle_automation":
                return await toggle_automation(self._ha, inputs["automation_id"], inputs["enabled"])
            if name == "call_ha_service":
                domain = inputs["domain"]
                service = inputs["service"]
                if allowed_services:
                    service_key = f"{domain}.{service}"
                    if not any(fnmatch.fnmatch(service_key, pat) for pat in allowed_services):
                        logger.warning("Service %s.%s blocked by policy", domain, service)
                        return {"error": f"Service {domain}.{service} not permitted by policy"}
                return await self._ha.call_service(domain, service, inputs.get("data", {}))
            logger.warning("Unknown tool: %s", name)
            return {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return {"error": str(exc)}
