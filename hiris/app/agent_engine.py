import asyncio
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
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
    strategic_context: str = ""
    allowed_entities: list[str] = field(default_factory=list)
    allowed_services: list[str] = field(default_factory=list)


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
        await self._ha.start_websocket()
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
            strategic_context=data.get("strategic_context", ""),
            allowed_entities=data.get("allowed_entities", []),
            allowed_services=data.get("allowed_services", []),
        )
        self._agents[agent.id] = agent
        if agent.enabled:
            self._schedule_agent(agent)
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
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        self._unschedule_agent(agent_id)
        del self._agents[agent_id]
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
                task.add_done_callback(
                    lambda t: logger.error("Reactive agent task failed: %s", t.exception())
                    if not t.cancelled() and t.exception() else None
                )

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
            return result
        except Exception as exc:
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            return agent.last_result
