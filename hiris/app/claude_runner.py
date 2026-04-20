import asyncio
import fnmatch
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
import anthropic
from .proxy.ha_client import HAClient
from .tools.ha_tools import (
    get_entity_states, TOOL_DEF as HA_TOOL,
    get_area_entities, GET_AREA_ENTITIES_TOOL_DEF,
    get_home_status, GET_HOME_STATUS_TOOL_DEF,
    get_entities_on, GET_ENTITIES_ON_TOOL_DEF,
    search_entities, SEARCH_ENTITIES_TOOL_DEF,
    get_entities_by_domain, GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
)
from .tools.energy_tools import get_energy_history, TOOL_DEF as ENERGY_TOOL
from .tools.weather_tools import get_weather_forecast, TOOL_DEF as WEATHER_TOOL
from .tools.notify_tools import send_notification, TOOL_DEF as NOTIFY_TOOL
from .tools.automation_tools import (
    get_ha_automations, GET_AUTOMATIONS_TOOL_DEF,
    trigger_automation, TRIGGER_TOOL_DEF,
    toggle_automation, TOGGLE_TOOL_DEF,
)
from .proxy.home_profile import generate_home_profile, get_cached_home_profile

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
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    SEARCH_ENTITIES_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
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
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]

AUTO_MODEL_MAP: dict[str, str] = {
    "chat": "claude-sonnet-4-6",
    "monitor": "claude-haiku-4-5-20251001",
    "reactive": "claude-haiku-4-5-20251001",
    "preventive": "claude-haiku-4-5-20251001",
}

_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}


def resolve_model(model: str, agent_type: str) -> str:
    if model == "auto":
        return AUTO_MODEL_MAP.get(agent_type, MODEL)
    return model

RESTRICT_PROMPT = (
    "Sei HIRIS, assistente per la smart home. "
    "Rispondi SOLO a domande relative alla casa, domotica, energia, clima, sicurezza. "
    "Per qualsiasi altro argomento, rispondi educatamente che non puoi aiutare su quel tema."
)

REQUIRE_CONFIRMATION_PROMPT = (
    "Prima di chiamare call_ha_service per eseguire un'azione reale, "
    "descrivi l'azione che intendi eseguire e chiedi conferma con il formato: "
    "'Proposta: [descrizione azione]. Confermi? (sì/no)'. "
    "Esegui call_ha_service SOLO se il messaggio più recente dell'utente "
    "contiene 'sì', 'si', 'ok', 'conferma' o 'yes' (case insensitive)."
)


class ClaudeRunner:
    def __init__(
        self,
        api_key: str,
        ha_client: HAClient,
        notify_config: dict,
        usage_path: str = "",
        entity_cache=None,
        embedding_index=None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._ha = ha_client
        self._notify_config = notify_config
        self._usage_path = usage_path
        self._cache = entity_cache
        self._index = embedding_index
        self.last_tool_calls: list[dict] = []
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._load_usage()

    def _load_usage(self) -> None:
        if not self._usage_path or not os.path.exists(self._usage_path):
            return
        try:
            with open(self._usage_path, encoding="utf-8") as f:
                data = json.load(f)
            self.total_input_tokens = data.get("total_input_tokens", 0)
            self.total_output_tokens = data.get("total_output_tokens", 0)
            self.total_requests = data.get("total_requests", 0)
            self.usage_last_reset = data.get("last_reset", self.usage_last_reset)
            self.total_cost_usd = data.get("total_cost_usd", 0.0)
            self.total_rate_limit_errors = data.get("total_rate_limit_errors", 0)
        except Exception as exc:
            logger.warning("Failed to load usage from %s: %s", self._usage_path, exc)

    def _save_usage(self) -> None:
        if not self._usage_path:
            return
        try:
            data = {
                "schema_version": 1,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_requests": self.total_requests,
                "last_reset": self.usage_last_reset,
                "total_cost_usd": self.total_cost_usd,
                "total_rate_limit_errors": self.total_rate_limit_errors,
            }
            tmp = self._usage_path + ".tmp"
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._usage_path)
        except Exception as exc:
            logger.error("Failed to save usage to %s: %s", self._usage_path, exc)

    def reset_usage(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.total_cost_usd = 0.0
        self.total_rate_limit_errors = 0
        self.usage_last_reset = datetime.now(timezone.utc).isoformat()
        self._save_usage()

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
    ) -> str:
        self.last_tool_calls = []
        effective_system = system_prompt
        if restrict_to_home:
            effective_system = f"{system_prompt}\n\n---\n\n{RESTRICT_PROMPT}"
        if require_confirmation:
            effective_system = f"{effective_system}\n\n---\n\n{REQUIRE_CONFIRMATION_PROMPT}"
        if self._cache is not None:
            effective_system = f"{effective_system}\n\n---\n\n{get_cached_home_profile(self._cache)}"
        effective_model = resolve_model(model, agent_type)
        tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
        messages: list[dict] = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                response = await self._call_api(
                    model=effective_model,
                    max_tokens=max_tokens,
                    system=effective_system,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.APIError as exc:
                logger.error("Claude API error: %s", exc)
                return f"Claude API error: {exc}"

            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            self.total_input_tokens += inp
            self.total_output_tokens += out
            self.total_requests += 1
            prices = _PRICING.get(effective_model, _PRICING["claude-sonnet-4-6"])
            self.total_cost_usd += (inp * prices["input"] + out * prices["output"]) / 1_000_000
            self._save_usage()

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

    async def _call_api(self, **kwargs) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if exc.status_code in (429, 529) and attempt < MAX_RETRIES:
                    self.total_rate_limit_errors += 1
                    delay = RETRY_DELAYS[attempt]
                    logger.warning("Rate limit (attempt %d/%d), retry in %ds", attempt + 1, MAX_RETRIES, delay)
                    await asyncio.sleep(delay)
                else:
                    raise

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
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
            if name == "get_home_status":
                return get_home_status(self._cache) if self._cache else []
            if name == "get_entities_on":
                return get_entities_on(self._cache) if self._cache else []
            if name == "search_entities":
                if self._cache is None or self._index is None:
                    return []
                return search_entities(
                    inputs["query"],
                    self._cache,
                    self._index,
                    top_k=inputs.get("top_k", 10),
                    domain=inputs.get("domain"),
                )
            if name == "get_entities_by_domain":
                return get_entities_by_domain(inputs["domain"], self._cache) if self._cache else []
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
