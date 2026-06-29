from __future__ import annotations
import fnmatch
import logging
import re
from typing import Any, Optional

# HA automation IDs are slug-style: lowercase alphanumeric + underscore.
# Reject anything else before composing entity_id, to avoid injection through
# automation.{id} in case HA's downstream parser is lenient.
_AUTOMATION_ID_RE = re.compile(r"^[a-z0-9_]+$")

from .ha_tools import (
    get_entity_states, get_area_entities, get_home_status,
    get_entities_on, get_entities_by_domain,
)
from .energy_tools import get_energy_history
from .weather_tools import get_weather_forecast
from .notify_tools import send_notification
from .automation_tools import get_ha_automations, get_automation_config, trigger_automation, toggle_automation
from .task_tools import create_task_tool, list_tasks_tool, cancel_task_tool
from .calendar_tools import get_calendar_events, set_input_helper, create_calendar_event
from .http_tools import http_request
from .memory_tools import recall_memory as _recall_memory, save_memory as _save_memory
from .history_tools import get_history as _get_history
from .health_tools import get_ha_health
from .proposal_tools import create_automation_proposal
from .knowledge_tools import (
    handle_save_knowledge, handle_recall_knowledge, handle_link_knowledge,
)

logger = logging.getLogger(__name__)


def _filter_entities(entities: list[dict], allowed_entities: list[str] | None) -> list[dict]:
    """Return only entities whose ID matches any allowed_entities glob pattern."""
    if not allowed_entities:
        return entities
    return [
        e for e in entities
        if any(fnmatch.fnmatch(e.get("id", e.get("entity_id", "")), pat) for pat in allowed_entities)
    ]


def _check_service_allowed(
    service_key: str, allowed_services: list[str] | None
) -> dict | None:
    """Return error dict if service blocked, None if allowed."""
    if allowed_services and not any(
        fnmatch.fnmatch(service_key, pat) for pat in allowed_services
    ):
        logger.warning("Service %s blocked by policy", service_key)
        return {"error": f"Service {service_key} not permitted by policy"}
    return None


def _check_entity_allowed(
    entity_id: str, allowed_entities: list[str] | None
) -> dict | None:
    """Return error dict if entity blocked, None if allowed."""
    if allowed_entities and not any(
        fnmatch.fnmatch(entity_id, pat) for pat in allowed_entities
    ):
        logger.warning("Entity %s blocked by allowed_entities policy", entity_id)
        return {"error": f"Entity {entity_id!r} not permitted by policy"}
    return None


class ToolDispatcher:
    """Executes HIRIS tools. Shared across LLM runners so HA integration stays in one place."""

    def __init__(
        self,
        ha_client: Any,
        notify_config: dict,
        entity_cache: Any = None,
        semantic_map: Any = None,
        memory_store: Any = None,
        embedding_provider: Any = None,
        memory_retention_days: int | None = None,
        health_monitor: Any = None,
        proposal_store: Any = None,
        knowledge_store: Any = None,
        embedder: Any = None,
        pseudonymizer: Any = None,
        history_store: Any = None,
    ) -> None:
        self._ha = ha_client
        self._notify_config = notify_config
        self._cache = entity_cache
        self._semantic_map = semantic_map
        self._memory_store = memory_store
        self._embedder = embedding_provider
        self._memory_retention_days = memory_retention_days
        self._health_monitor = health_monitor
        self._proposal_store = proposal_store
        self._knowledge_store = knowledge_store
        # Use dedicated embedder if provided, otherwise fall back to the memory embedder
        self._knowledge_embedder = embedder if embedder is not None else embedding_provider
        self._pseudonymizer = pseudonymizer
        self._history_store = history_store
        self._task_engine: Any = None

    def set_task_engine(self, engine: Any) -> None:
        self._task_engine = engine

    @property
    def has_memory(self) -> bool:
        return self._memory_store is not None and self._embedder is not None

    async def dispatch(
        self,
        name: str,
        inputs: dict,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        agent_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
        knowledge_allow_sensitive: bool = False,
        cloud: bool = True,
    ) -> Any:
        _REDACT_KEYS = frozenset({"api_key", "token", "password", "secret", "authorization"})
        _log_inputs = {k: "***" if k.lower() in _REDACT_KEYS else v for k, v in inputs.items()}
        logger.info("Tool call: %s(%s)", name, _log_inputs)
        try:
            if name == "get_area_entities":
                return await get_area_entities(self._ha, entity_cache=self._cache)
            if name == "get_entity_states":
                ids = inputs.get("ids", [])
                if visible_entity_ids:
                    ids = [eid for eid in ids if eid in visible_entity_ids]
                if allowed_entities:
                    ids = [eid for eid in ids if any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities)]
                return await get_entity_states(self._ha, ids, entity_cache=self._cache)
            if name == "get_history":
                return await _get_history(
                    self._ha,
                    inputs.get("entity_ids", []),
                    days=int(inputs.get("days", 7)),
                    resolution=inputs.get("resolution", "auto"),
                    store=self._history_store,
                )
            if name == "get_home_status":
                result = get_home_status(self._cache, semantic_map=self._semantic_map) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_entities_on":
                result = get_entities_on(self._cache) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_entities_by_domain":
                result = get_entities_by_domain(inputs["domain"], self._cache) if self._cache else []
                return _filter_entities(result, allowed_entities)
            if name == "get_energy_history":
                return await get_energy_history(self._ha, inputs["days"], semantic_map=self._semantic_map)
            if name == "get_weather_forecast":
                return await get_weather_forecast(inputs["hours"])
            if name == "send_notification":
                return await send_notification(self._ha, inputs["message"], inputs["channel"], self._notify_config)
            if name == "get_ha_automations":
                return await get_ha_automations(self._ha)
            if name == "get_automation_config":
                return await get_automation_config(self._ha, inputs.get("automation_id", ""))
            if name == "trigger_automation":
                automation_id = inputs["automation_id"]
                bare_id = (
                    automation_id[len("automation."):]
                    if automation_id.startswith("automation.") else automation_id
                )
                if not _AUTOMATION_ID_RE.match(bare_id):
                    return {"error": f"invalid automation_id: {automation_id!r}"}
                entity_id = f"automation.{bare_id}"
                err = _check_service_allowed("automation.trigger", allowed_services)
                if err is not None:
                    return err
                err = _check_entity_allowed(entity_id, allowed_entities)
                if err is not None:
                    return err
                return await trigger_automation(self._ha, automation_id)
            if name == "toggle_automation":
                automation_id = inputs["automation_id"]
                enabled = inputs["enabled"]
                bare_id = (
                    automation_id[len("automation."):]
                    if automation_id.startswith("automation.") else automation_id
                )
                if not _AUTOMATION_ID_RE.match(bare_id):
                    return {"error": f"invalid automation_id: {automation_id!r}"}
                entity_id = f"automation.{bare_id}"
                service_key = "automation.turn_on" if enabled else "automation.turn_off"
                err = _check_service_allowed(service_key, allowed_services)
                if err is not None:
                    return err
                err = _check_entity_allowed(entity_id, allowed_entities)
                if err is not None:
                    return err
                return await toggle_automation(self._ha, automation_id, enabled)
            if name == "call_ha_service":
                domain = inputs["domain"]
                service = inputs["service"]
                data = inputs.get("data", {})
                target = inputs.get("target", {}) or {}
                if allowed_services:
                    service_key = f"{domain}.{service}"
                    if not any(fnmatch.fnmatch(service_key, pat) for pat in allowed_services):
                        logger.warning("Service %s.%s blocked by policy", domain, service)
                        return {"error": f"Service {domain}.{service} not permitted by policy"}
                if allowed_entities:
                    raw_eid = (
                        data.get("entity_id") if isinstance(data, dict) else None
                    ) or target.get("entity_id")
                    eids = (
                        [raw_eid] if isinstance(raw_eid, str)
                        else list(raw_eid) if isinstance(raw_eid, list)
                        else []
                    )
                    for eid in eids:
                        if not any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities):
                            logger.warning("Entity %s blocked by allowed_entities policy", eid)
                            return {"error": f"Entity {eid!r} not permitted by policy"}
                return await self._ha.call_service(domain, service, data)
            if name == "create_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                if allowed_services:
                    for action in inputs.get("actions", []):
                        if action.get("type") == "call_ha_service":
                            svc_key = f"{action.get('domain', '')}.{action.get('service', '')}"
                            if not any(fnmatch.fnmatch(svc_key, pat) for pat in allowed_services):
                                logger.warning("create_task blocked: action %s not permitted", svc_key)
                                return {"error": f"Action {svc_key} not permitted by policy"}
                return create_task_tool(
                    task_engine=self._task_engine,
                    label=inputs["label"],
                    trigger=inputs["trigger"],
                    actions=inputs["actions"],
                    condition=inputs.get("condition"),
                    one_shot=inputs.get("one_shot", True),
                    agent_id=agent_id or "hiris-default",
                    allowed_entities=allowed_entities,
                    allowed_services=allowed_services,
                )
            if name == "list_tasks":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return list_tasks_tool(
                    task_engine=self._task_engine,
                    agent_id=inputs.get("agent_id"),
                    status=inputs.get("status"),
                )
            if name == "cancel_task":
                if self._task_engine is None:
                    return {"error": "TaskEngine not available"}
                return cancel_task_tool(
                    task_engine=self._task_engine,
                    task_id=inputs["task_id"],
                )
            if name == "get_calendar_events":
                return await get_calendar_events(
                    self._ha,
                    hours=inputs.get("hours", 24),
                    calendar_entity=inputs.get("calendar_entity"),
                )
            if name == "set_input_helper":
                eid = inputs.get("entity_id", "")
                if "value" not in inputs:
                    return {"error": "Missing required parameter: value"}
                ih_domain = eid.split(".")[0] if "." in eid else ""
                if allowed_services and ih_domain:
                    if not any(
                        fnmatch.fnmatch(f"{ih_domain}.turn_on", pat)
                        or fnmatch.fnmatch(f"{ih_domain}.set_value", pat)
                        or fnmatch.fnmatch(f"{ih_domain}.select_option", pat)
                        for pat in allowed_services
                    ):
                        logger.warning("set_input_helper on %r blocked by allowed_services policy", ih_domain)
                        return {"error": f"Domain {ih_domain!r} not permitted by allowed_services policy"}
                if allowed_entities and eid:
                    if not any(fnmatch.fnmatch(eid, pat) for pat in allowed_entities):
                        logger.warning("set_input_helper on %r blocked by allowed_entities policy", eid)
                        return {"error": f"Entity {eid!r} not permitted by policy"}
                return await set_input_helper(self._ha, entity_id=eid, value=inputs.get("value"))
            if name == "create_calendar_event":
                return await create_calendar_event(
                    self._ha,
                    calendar_entity=inputs["calendar_entity"],
                    summary=inputs["summary"],
                    event_type=inputs["event_type"],
                    start_date_time=inputs.get("start_date_time"),
                    end_date_time=inputs.get("end_date_time"),
                    start_date=inputs.get("start_date"),
                    end_date=inputs.get("end_date"),
                    description=inputs.get("description"),
                    location=inputs.get("location"),
                )
            if name == "http_request":
                return await http_request(
                    url=inputs["url"],
                    method=inputs.get("method", "GET"),
                    headers=inputs.get("headers"),
                    body=inputs.get("body"),
                    allowed_endpoints=allowed_endpoints,
                )
            if name == "recall_memory":
                if self._memory_store is None:
                    return {"error": "Memory store not configured"}
                return await _recall_memory(
                    memory_store=self._memory_store,
                    embedder=self._embedder,
                    agent_id=agent_id or "hiris-default",
                    query=inputs["query"],
                    k=int(inputs.get("k", 5)),
                    tags=inputs.get("tags") or None,
                )
            if name == "save_memory":
                if self._memory_store is None:
                    return {"error": "Memory store not configured"}
                return await _save_memory(
                    memory_store=self._memory_store,
                    embedder=self._embedder,
                    agent_id=agent_id or "hiris-default",
                    content=inputs["content"],
                    tags=inputs.get("tags") or None,
                    retention_days=self._memory_retention_days,
                )
            if name == "get_ha_health":
                return get_ha_health(self._health_monitor, inputs.get("sections") or ["all"])
            if name == "create_automation_proposal":
                return await create_automation_proposal(
                    self._proposal_store,
                    proposal_type=inputs["type"],
                    name=inputs["name"],
                    description=inputs["description"],
                    config=inputs["config"],
                    routing_reason=inputs["routing_reason"],
                )
            if name == "save_knowledge" and self._knowledge_store:
                return await handle_save_knowledge(
                    self._knowledge_store, self._knowledge_embedder, inputs, owner="home"
                )
            if name == "recall_knowledge" and self._knowledge_store:
                return await handle_recall_knowledge(
                    self._knowledge_store, self._knowledge_embedder, inputs, owner="home",
                    allow_sensitive=knowledge_allow_sensitive,
                    pseudonymizer=self._pseudonymizer,
                    cloud=cloud,
                )
            if name == "link_knowledge" and self._knowledge_store:
                return await handle_link_knowledge(self._knowledge_store, inputs)
            logger.warning("Unknown tool: %s", name)
            return {
                "error": (
                    f"Tool '{name}' non esiste. "
                    "Usa ESCLUSIVAMENTE i tool elencati nel system prompt. "
                    "Non inventare nomi di tool."
                )
            }
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return {"error": str(exc)}
