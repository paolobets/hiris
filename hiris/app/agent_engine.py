import asyncio
import logging
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .proxy.ha_client import HAClient

logger = logging.getLogger(__name__)


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


class AgentEngine:
    def __init__(self, ha_client: HAClient) -> None:
        self._ha = ha_client
        self._agents: dict[str, Agent] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None  # set after init via set_claude_runner()

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    async def start(self) -> None:
        self._ha.add_state_listener(self._on_state_changed)
        self._scheduler.start()
        logger.info("AgentEngine started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("AgentEngine stopped")

    def create_agent(self, data: dict) -> Agent:
        agent = Agent(
            id=str(uuid.uuid4()),
            name=data["name"],
            type=data["type"],
            trigger=data["trigger"],
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            enabled=data.get("enabled", True),
        )
        self._agents[agent.id] = agent
        if agent.enabled:
            self._schedule_agent(agent)
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def update_agent(self, agent_id: str, data: dict) -> Optional[Agent]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        self._unschedule_agent(agent_id)
        for key, value in data.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        if agent.enabled:
            self._schedule_agent(agent)
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        self._unschedule_agent(agent_id)
        del self._agents[agent_id]
        return True

    def list_agents(self) -> dict[str, dict]:
        return {a.id: asdict(a) for a in self._agents.values()}

    def _schedule_agent(self, agent: Agent) -> None:
        trigger = agent.trigger
        if trigger["type"] == "schedule":
            minutes = trigger.get("interval_minutes", 5)
            self._scheduler.add_job(
                self._run_agent,
                "interval",
                minutes=minutes,
                args=[agent],
                id=agent.id,
                replace_existing=True,
            )
        elif trigger["type"] == "preventive" and trigger.get("cron"):
            parts = trigger["cron"].split()
            self._scheduler.add_job(
                self._run_agent,
                "cron",
                minute=parts[0],
                hour=parts[1],
                args=[agent],
                id=agent.id,
                replace_existing=True,
            )

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
            if (
                agent.trigger.get("type") == "state_changed"
                and agent.trigger.get("entity_id") == entity_id
            ):
                asyncio.create_task(self._run_agent(agent, context=event_data))

    async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:
        if not self._claude_runner:
            logger.warning("No Claude runner configured")
            return ""
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        try:
            prompt = agent.system_prompt
            if context:
                prompt = f"{prompt}\n\nContext: {context}"
            result = await self._claude_runner.chat(
                user_message=f"[Agent trigger: {agent.trigger.get('type')}]",
                system_prompt=prompt,
                allowed_tools=agent.allowed_tools or None,
            )
            agent.last_result = result
            return result
        except Exception as exc:
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            return agent.last_result
