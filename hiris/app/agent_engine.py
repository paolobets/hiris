import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .proxy.ha_client import HAClient

logger = logging.getLogger(__name__)

DEFAULT_AGENTS_DATA_PATH = "/data/agents.json"
DEFAULT_AGENT_ID = "hiris-default"


@dataclass
class Agent:
    id: str
    name: str
    type: str  # monitor | reactive | preventive | chat
    trigger: dict  # {type: schedule|state_changed|manual, interval_minutes?, entity_id?, cron?}
    system_prompt: str
    allowed_tools: list[str]
    enabled: bool
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    strategic_context: str = ""
    allowed_entities: list[str] = field(default_factory=list)
    allowed_services: list[str] = field(default_factory=list)
    is_default: bool = False


class AgentEngine:
    def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_AGENTS_DATA_PATH) -> None:
        self._agents: dict[str, Agent] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None  # set after init via set_claude_runner()
        self._ha = ha_client
        self._data_path = data_path

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    async def start(self) -> None:
        self._scheduler.start()
        self._ha.add_state_listener(self._on_state_changed)
        await self._ha.start_websocket()
        self._load()
        self._seed_default_agent()
        logger.info("AgentEngine started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("AgentEngine stopped")

    def _save(self) -> None:
        try:
            data = {"schema_version": 1, "agents": [asdict(a) for a in self._agents.values()]}
            tmp = self._data_path + ".tmp"
            os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp, self._data_path)
        except Exception as exc:
            logger.error("Failed to persist agents to %s: %s", self._data_path, exc)

    def _load(self) -> None:
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("agents", []):
                agent = Agent(
                    id=raw["id"],
                    name=raw["name"],
                    type=raw["type"],
                    trigger=raw["trigger"],
                    system_prompt=raw.get("system_prompt", ""),
                    allowed_tools=raw.get("allowed_tools", []),
                    enabled=raw.get("enabled", True),
                    is_default=raw.get("is_default", False),
                    last_run=raw.get("last_run"),
                    last_result=raw.get("last_result"),
                    strategic_context=raw.get("strategic_context", ""),
                    allowed_entities=raw.get("allowed_entities", []),
                    allowed_services=raw.get("allowed_services", []),
                )
                self._agents[agent.id] = agent
                if agent.enabled and agent.type in ("monitor", "preventive"):
                    self._schedule_agent(agent)
        except Exception as exc:
            logger.error("Failed to load agents from %s: %s", self._data_path, exc)

    _DEFAULT_SYSTEM_PROMPT = (
        "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
        "Strumenti disponibili:\n"
        "- get_home_status(): panoramica compatta di tutti i dispositivi utili. Usalo come prima chiamata.\n"
        "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
        "- search_entities(query, top_k, domain): ricerca semantica di entità per linguaggio naturale.\n"
        "- get_entities_by_domain(domain): tutte le entità di un dominio (es. 'light', 'sensor').\n"
        "- get_entity_states(ids): stato attuale di entità specifiche per ID.\n"
        "- get_area_entities(): scopre stanze/aree e i dispositivi associati.\n"
        "- get_ha_automations(): elenco delle automazioni.\n"
        "- get_energy_history(days): storico consumi energetici.\n"
        "- get_weather_forecast(hours): previsioni meteo.\n"
        "- call_ha_service(domain, service, data): controlla dispositivi.\n\n"
        "Regole:\n"
        "- Per qualsiasi domanda sulla casa usa SEMPRE gli strumenti per dati reali.\n"
        "- Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
        "- Non inventare dati: usa gli strumenti.\n"
        "- Rispondi nella lingua dell'utente."
    )

    # Old factory prompts that can be safely overwritten on upgrade
    _LEGACY_DEFAULT_PROMPTS = {
        "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente.",
        "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
    }

    def _seed_default_agent(self) -> None:
        if DEFAULT_AGENT_ID not in self._agents:
            agent = Agent(
                id=DEFAULT_AGENT_ID,
                name="HIRIS",
                type="chat",
                trigger={"type": "manual"},
                system_prompt=self._DEFAULT_SYSTEM_PROMPT,
                allowed_tools=[],
                enabled=True,
                is_default=True,
            )
            self._agents[DEFAULT_AGENT_ID] = agent
            self._save()
        else:
            agent = self._agents[DEFAULT_AGENT_ID]
            if agent.system_prompt in self._LEGACY_DEFAULT_PROMPTS:
                agent.system_prompt = self._DEFAULT_SYSTEM_PROMPT
                self._save()
                logger.info("Migrated default agent system prompt to v0.0.9")

    def get_default_agent(self) -> Optional[Agent]:
        return self._agents.get(DEFAULT_AGENT_ID)

    def create_agent(self, data: dict) -> Agent:
        agent = Agent(
            id=str(uuid.uuid4()),
            name=data["name"],
            type=data["type"],
            trigger=data["trigger"],
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            enabled=data.get("enabled", True),
            is_default=False,
            strategic_context=data.get("strategic_context", ""),
            allowed_entities=data.get("allowed_entities", []),
            allowed_services=data.get("allowed_services", []),
        )
        self._agents[agent.id] = agent
        if agent.enabled:
            self._schedule_agent(agent)
        self._save()
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    UPDATABLE_FIELDS = {
        "name", "type", "trigger", "system_prompt", "allowed_tools", "enabled",
        "strategic_context", "allowed_entities", "allowed_services",
    }

    def update_agent(self, agent_id: str, data: dict) -> Optional[Agent]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        self._unschedule_agent(agent_id)
        for key in self.UPDATABLE_FIELDS:
            if key in data:
                setattr(agent, key, data[key])
        if agent.enabled:
            self._schedule_agent(agent)
        self._save()
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        if agent.is_default:
            return False
        self._unschedule_agent(agent_id)
        del self._agents[agent_id]
        self._save()
        return True

    async def run_agent(self, agent: "Agent") -> str:
        return await self._run_agent(agent)

    def list_agents(self) -> dict[str, dict]:
        return {a.id: asdict(a) for a in self._agents.values()}

    def _schedule_agent(self, agent: Agent) -> None:
        trigger = agent.trigger
        if trigger["type"] == "schedule":
            try:
                minutes = trigger.get("interval_minutes", 5)
                self._scheduler.add_job(
                    self._run_agent,
                    "interval",
                    minutes=minutes,
                    args=[agent],
                    id=agent.id,
                    replace_existing=True,
                    coalesce=True,
                )
            except Exception as exc:
                logger.error("Failed to schedule agent %s: %s", agent.id, exc)
        elif trigger["type"] == "preventive" and trigger.get("cron"):
            try:
                parts = trigger["cron"].split()
                if len(parts) < 2:
                    logger.error("Invalid cron for agent %s: %s", agent.id, trigger["cron"])
                    return
                kwargs: dict = {
                    "minute": parts[0],
                    "hour": parts[1],
                }
                if len(parts) >= 3:
                    kwargs["day"] = parts[2]
                if len(parts) >= 4:
                    kwargs["month"] = parts[3]
                if len(parts) >= 5:
                    kwargs["day_of_week"] = parts[4]
                self._scheduler.add_job(
                    self._run_agent,
                    "cron",
                    **kwargs,
                    args=[agent],
                    id=agent.id,
                    replace_existing=True,
                )
            except Exception as exc:
                logger.error("Failed to schedule agent %s: %s", agent.id, exc)

    def _unschedule_agent(self, agent_id: str) -> None:
        try:
            self._scheduler.remove_job(agent_id)
        except Exception:
            pass

    def _on_state_changed(self, event_data: dict) -> None:
        entity_id = event_data.get("entity_id", "")
        for agent in self._agents.values():
            if not agent.enabled:
                continue
            if agent.trigger.get("type") == "state_changed" and agent.trigger.get("entity_id") == entity_id:
                task = asyncio.create_task(self._run_agent(agent, context=event_data))
                def _on_task_done(t: asyncio.Task) -> None:
                    if not t.cancelled() and (exc := t.exception()):
                        logger.error("Reactive agent task failed: %s", exc)
                task.add_done_callback(_on_task_done)

    async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:
        if not self._claude_runner:
            logger.warning("No Claude runner configured")
            return ""
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        try:
            agent.last_run = datetime.now(timezone.utc).isoformat()
            if agent.strategic_context:
                effective_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
            else:
                effective_prompt = agent.system_prompt
            if context:
                effective_prompt = f"{effective_prompt}\n\nContext: {context}"
            result = await self._claude_runner.chat(
                user_message=f"[Agent trigger: {agent.trigger.get('type')}]",
                system_prompt=effective_prompt,
                allowed_tools=agent.allowed_tools or None,
                allowed_entities=agent.allowed_entities or None,
                allowed_services=agent.allowed_services or None,
            )
            agent.last_result = result
            self._save()
            return result
        except Exception as exc:
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            self._save()
            return agent.last_result
