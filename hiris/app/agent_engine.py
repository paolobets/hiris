import asyncio
import fnmatch
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .proxy.ha_client import HAClient
from .proxy._sanitize import sanitize_ha_value as _sanitize_ha_value
from .config import EUR_RATE

# Timeout complessivo per un singolo run di agente. Evita che un modello locale
# lento (Ollama) blocchi APScheduler per ore. Configurabile via env.
_AGENT_RUN_TIMEOUT = int(os.environ.get("AGENT_RUN_TIMEOUT", "300"))

logger = logging.getLogger(__name__)


DEFAULT_AGENTS_DATA_PATH = "/data/agents.json"
DEFAULT_AGENT_ID = "hiris-default"


@dataclass
class Agent:
    id: str
    name: str
    type: str                   # "chat" | "agent"
    triggers: list              # list of trigger dicts: [{type, interval_minutes?|entity_id?|cron?}]
    system_prompt: str
    allowed_tools: list
    enabled: bool
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    strategic_context: str = ""
    allowed_entities: list = field(default_factory=list)
    allowed_services: list = field(default_factory=list)
    is_default: bool = False
    model: str = "auto"
    max_tokens: int = 4096
    restrict_to_home: bool = False
    require_confirmation: bool = False   # chat only
    execution_log: list = field(default_factory=list)
    budget_eur_limit: float = 0.0
    max_chat_turns: int = 0              # chat only
    allowed_endpoints: Optional[list] = None
    states: list = field(default_factory=lambda: ["OK", "ATTENZIONE", "ANOMALIA"])
    action_mode: str = "automatic"       # "automatic" | "configured"
    rules: list = field(default_factory=list)  # [{states:[...], actions:[...]}]
    fallback_action: Optional[dict] = None
    response_mode: str = "auto"
    # Extended Thinking budget tokens (0 = disabled).
    # When >0, Claude returns thinking blocks alongside the answer (sonnet-4.5+/
    # opus-4+ only). The runner clamps to max_tokens-1 if invalid.
    thinking_budget: int = 0


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def _migrate_agent_raw(raw: dict) -> dict:
    """Migrate agents.json entries from old schema to new schema. Idempotent."""
    # 1. type: monitor|reactive|preventive → agent
    old_type = raw.get("type", "chat")
    if old_type in ("monitor", "reactive", "preventive"):
        raw["type"] = "agent"

    # 2. trigger (singular) → triggers (list)
    if "trigger" in raw and "triggers" not in raw:
        old_trigger = raw.pop("trigger")
        t_type = old_trigger.get("type", "manual")
        # rename old preventive trigger type
        if t_type == "preventive":
            old_trigger["type"] = "cron"
        if t_type == "manual" or raw["type"] == "chat":
            raw["triggers"] = []
        else:
            raw["triggers"] = [old_trigger]
    elif "triggers" not in raw:
        raw["triggers"] = []

    # 3. trigger_on + actions → rules
    if "actions" in raw and "rules" not in raw:
        old_actions = raw.pop("actions", [])
        old_trigger_on = raw.pop("trigger_on", ["ANOMALIA"])
        if old_actions and old_trigger_on:
            raw["rules"] = [{"states": old_trigger_on, "actions": old_actions}]
            raw.setdefault("action_mode", "configured")
        else:
            raw["rules"] = []
            raw.setdefault("action_mode", "automatic")
    else:
        # Clean up stale fields even if migration already ran partially
        raw.pop("trigger_on", None)
        raw.pop("actions", None)
        raw.setdefault("rules", [])
        raw.setdefault("action_mode", "automatic")

    return raw


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AgentEngine:
    _MQTT_RUN_COOLDOWN = 30

    def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_AGENTS_DATA_PATH) -> None:
        self._agents: dict[str, Agent] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None
        self._ha = ha_client
        self._data_path = data_path
        self._entity_cache: Any = None
        self._running_agents: set[str] = set()
        self._error_agents: set[str] = set()
        self._mqtt_publisher = None
        self._pending_mqtt_runs: set[str] = set()
        self._task_engine: Any = None
        self._mqtt_last_run: dict[str, float] = {}
        # Serialize tmp-write + os.replace across concurrent _save() calls
        # (executor uses a thread pool — two fire-and-forget _save() can otherwise
        # overlap on the same .tmp file and corrupt state).
        self._save_lock = threading.Lock()

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    def set_entity_cache(self, cache: Any) -> None:
        self._entity_cache = cache

    def set_mqtt_publisher(self, publisher) -> None:
        self._mqtt_publisher = publisher
        publisher.set_command_callback(self._handle_mqtt_command)

    def set_task_engine(self, engine: Any) -> None:
        self._task_engine = engine

    async def _handle_mqtt_command(self, agent_id: str, command: str, payload: str) -> None:
        agent = self._agents.get(agent_id)
        if not agent:
            return
        if command == "enabled":
            new_enabled = payload.upper() == "ON"
            if agent.enabled != new_enabled:
                self.update_agent(agent_id, {"enabled": new_enabled})
        elif command == "run_now" and payload.upper() == "PRESS":
            if time.time() - self._mqtt_last_run.get(agent_id, 0) < self._MQTT_RUN_COOLDOWN:
                logger.warning("MQTT run_now cooldown active for agent %s, ignoring", agent_id)
            elif agent_id in self._running_agents:
                self._pending_mqtt_runs.add(agent_id)
            else:
                self._mqtt_last_run[agent_id] = time.time()
                asyncio.create_task(self._run_agent(agent), name=f"mqtt_run_{agent_id}")

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
        data = {"schema_version": 2, "agents": [asdict(a) for a in self._agents.values()]}
        tmp = self._data_path + ".tmp"
        lock = self._save_lock

        def _write() -> None:
            with lock:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, default=str)
                    os.replace(tmp, self._data_path)
                except Exception as exc:
                    logger.error("Failed to persist agents: %s", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def _load(self) -> None:
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("agents", []):
                raw = _migrate_agent_raw(raw)
                agent = Agent(
                    id=raw["id"],
                    name=raw["name"],
                    type=raw["type"],
                    triggers=raw.get("triggers", []),
                    system_prompt=raw.get("system_prompt", ""),
                    allowed_tools=raw.get("allowed_tools", []),
                    enabled=raw.get("enabled", True),
                    is_default=raw.get("is_default", False),
                    last_run=raw.get("last_run"),
                    last_result=raw.get("last_result"),
                    strategic_context=raw.get("strategic_context", ""),
                    allowed_entities=raw.get("allowed_entities", []),
                    allowed_services=raw.get("allowed_services", []),
                    model=raw.get("model", "auto"),
                    max_tokens=raw.get("max_tokens", 4096),
                    restrict_to_home=raw.get("restrict_to_home", False),
                    require_confirmation=raw.get("require_confirmation", False),
                    execution_log=raw.get("execution_log", []),
                    budget_eur_limit=raw.get("budget_eur_limit", 0.0),
                    max_chat_turns=int(raw.get("max_chat_turns", 0)),
                    allowed_endpoints=raw.get("allowed_endpoints"),
                    states=raw.get("states", ["OK", "ATTENZIONE", "ANOMALIA"]),
                    action_mode=raw.get("action_mode", "automatic"),
                    rules=raw.get("rules", []),
                    fallback_action=raw.get("fallback_action"),
                    response_mode=raw.get("response_mode", "auto"),
                    thinking_budget=int(raw.get("thinking_budget", 0) or 0),
                )
                self._agents[agent.id] = agent
                if agent.enabled and agent.type == "agent":
                    self._schedule_agent(agent)
        except Exception as exc:
            logger.error("Failed to load agents from %s: %s", self._data_path, exc)

    _DEFAULT_SYSTEM_PROMPT = (
        "Sei l'assistente principale per la gestione della smart home.\n"
        "Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
        "La sezione CASA in fondo al prompt è uno snapshot di orientamento:"
        " usa i tool per valori precisi come temperature e stati correnti."
    )

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
                triggers=[],
                system_prompt=self._DEFAULT_SYSTEM_PROMPT,
                allowed_tools=[],
                enabled=True,
                is_default=True,
            )
            self._agents[DEFAULT_AGENT_ID] = agent
            self._save()
        else:
            agent = self._agents[DEFAULT_AGENT_ID]
            changed = False
            if agent.system_prompt in self._LEGACY_DEFAULT_PROMPTS:
                agent.system_prompt = self._DEFAULT_SYSTEM_PROMPT
                changed = True
            if agent.allowed_tools:
                agent.allowed_tools = []
                changed = True
            if changed:
                self._save()

    def get_default_agent(self) -> Optional[Agent]:
        return self._agents.get(DEFAULT_AGENT_ID)

    _LEGACY_TYPE_MAP = {"monitor": "agent", "reactive": "agent", "preventive": "agent"}

    def create_agent(self, data: dict) -> Agent:
        raw_type = data["type"]
        normalized_type = self._LEGACY_TYPE_MAP.get(raw_type, raw_type)
        agent = Agent(
            id=str(uuid.uuid4()),
            name=data["name"],
            type=normalized_type,
            triggers=data.get("triggers", []),
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            enabled=data.get("enabled", True),
            is_default=False,
            strategic_context=data.get("strategic_context", ""),
            allowed_entities=data.get("allowed_entities", []),
            allowed_services=data.get("allowed_services", []),
            model=data.get("model", "auto"),
            max_tokens=min(int(data.get("max_tokens", 4096)), 8192),
            restrict_to_home=bool(data.get("restrict_to_home", False)),
            require_confirmation=bool(data.get("require_confirmation", False)),
            budget_eur_limit=float(data.get("budget_eur_limit", 0.0)),
            max_chat_turns=int(data.get("max_chat_turns", 0)),
            allowed_endpoints=data.get("allowed_endpoints"),
            states=data.get("states", ["OK", "ATTENZIONE", "ANOMALIA"]),
            action_mode=data.get("action_mode", "automatic"),
            rules=data.get("rules", []),
            fallback_action=data.get("fallback_action"),
            response_mode=data.get("response_mode", "auto"),
            thinking_budget=max(0, int(data.get("thinking_budget", 0) or 0)),
        )
        self._agents[agent.id] = agent
        if self._mqtt_publisher:
            asyncio.create_task(
                self._mqtt_publisher.publish_discovery(agent),
                name=f"mqtt_disc_{agent.id}",
            )
        if agent.enabled and agent.type == "agent":
            self._schedule_agent(agent)
        self._save()
        return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    UPDATABLE_FIELDS = {
        "name", "type", "triggers", "system_prompt", "allowed_tools", "enabled",
        "strategic_context", "allowed_entities", "allowed_services",
        "model", "max_tokens", "restrict_to_home", "require_confirmation",
        "budget_eur_limit", "max_chat_turns", "allowed_endpoints",
        "states", "action_mode", "rules", "fallback_action", "response_mode",
        "thinking_budget",
    }

    def update_agent(self, agent_id: str, data: dict) -> Optional[Agent]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        enabled_before = agent.enabled
        self._unschedule_agent(agent_id)
        _BOOL_FIELDS = {"restrict_to_home", "require_confirmation"}
        _FLOAT_FIELDS = {"budget_eur_limit"}
        _INT_FIELDS = {"max_chat_turns"}
        for key in self.UPDATABLE_FIELDS:
            if key in data:
                if key in _BOOL_FIELDS:
                    setattr(agent, key, bool(data[key]))
                elif key in _FLOAT_FIELDS:
                    setattr(agent, key, float(data[key]))
                elif key in _INT_FIELDS:
                    setattr(agent, key, int(data[key]))
                elif key == "max_tokens":
                    setattr(agent, key, min(int(data[key]), 8192))
                else:
                    setattr(agent, key, data[key])
        if agent.enabled and agent.type == "agent":
            self._schedule_agent(agent)
        self._save()
        if self._mqtt_publisher and agent.enabled != enabled_before:
            try:
                asyncio.create_task(
                    self._mqtt_publisher.publish_agent_state(agent, budget_eur=0.0, status="idle"),
                    name=f"mqtt_enable_{agent.id}",
                )
            except RuntimeError:
                pass
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None or agent.is_default:
            return False
        self._unschedule_agent(agent_id)
        del self._agents[agent_id]
        self._save()
        return True

    async def run_agent(self, agent: "Agent") -> str:
        return await self._run_agent(agent)

    def list_agents(self) -> dict[str, dict]:
        return {a.id: asdict(a) for a in self._agents.values()}

    def get_agent_status(self, agent_id: str) -> str:
        if agent_id in self._running_agents:
            return "running"
        if agent_id in self._error_agents:
            return "error"
        return "idle"

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_agent(self, agent: Agent) -> None:
        for i, trigger in enumerate(agent.triggers):
            job_id = f"{agent.id}__{i}"
            t_type = trigger.get("type")
            try:
                if t_type == "schedule":
                    minutes = max(1, int(trigger.get("interval_minutes", 5)))
                    self._scheduler.add_job(
                        self._run_agent, "interval",
                        minutes=minutes,
                        args=[agent, None, trigger],
                        id=job_id, replace_existing=True, coalesce=True,
                        misfire_grace_time=60,
                    )
                elif t_type == "cron" and trigger.get("cron"):
                    parts = trigger["cron"].split()
                    if len(parts) < 2:
                        logger.error("Invalid cron for agent %s: %s", agent.id, trigger["cron"])
                        continue
                    kwargs: dict = {"minute": parts[0], "hour": parts[1]}
                    if len(parts) >= 3:
                        kwargs["day"] = parts[2]
                    if len(parts) >= 4:
                        kwargs["month"] = parts[3]
                    if len(parts) >= 5:
                        kwargs["day_of_week"] = parts[4]
                    self._scheduler.add_job(
                        self._run_agent, "cron",
                        **kwargs,
                        args=[agent, None, trigger],
                        id=job_id, replace_existing=True, coalesce=True,
                        misfire_grace_time=60,
                    )
            except Exception as exc:
                logger.error("Failed to schedule agent %s trigger %d: %s", agent.id, i, exc)

    def _unschedule_agent(self, agent_id: str) -> None:
        for job in list(self._scheduler.get_jobs()):
            if job.id == agent_id or job.id.startswith(f"{agent_id}__"):
                try:
                    self._scheduler.remove_job(job.id)
                except Exception as exc:
                    logger.debug("remove_job(%s) failed: %s", job.id, exc)

    def _on_state_changed(self, event_data: dict) -> None:
        entity_id = event_data.get("entity_id", "")
        for agent in self._agents.values():
            if not agent.enabled or agent.type != "agent":
                continue
            for trigger in agent.triggers:
                if trigger.get("type") == "state_changed" and trigger.get("entity_id") == entity_id:
                    task = asyncio.create_task(
                        self._run_agent(agent, context=event_data, trigger_fired=trigger)
                    )
                    def _on_done(t: asyncio.Task) -> None:
                        if not t.cancelled() and (exc := t.exception()):
                            logger.error("Reactive agent task failed: %s", exc)
                    task.add_done_callback(_on_done)
                    break

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def _build_entity_context(self, agent: "Agent") -> str:
        if self._entity_cache is None:
            return ""
        all_entities = self._entity_cache.get_all_useful()
        if agent.allowed_entities:
            relevant = [
                e for e in all_entities
                if any(fnmatch.fnmatch(e["id"], pat) for pat in agent.allowed_entities)
            ]
        else:
            relevant = all_entities
        if not relevant:
            return ""
        lines = [
            "[INIZIO DATI NON AFFIDABILI — fonte: Home Assistant]",
            "[CONTESTO ENTITÀ]",
        ]
        for e in relevant[:50]:
            name = _sanitize_ha_value(e.get("name") or e["id"])
            state = _sanitize_ha_value(str(e.get("state", "")))
            unit = f" {e['unit']}" if e.get("unit") else ""
            lines.append(f"- {name}: {state}{unit}")
        lines.append("[FINE DATI NON AFFIDABILI]")
        return "\n".join(lines)

    def _check_budget_auto_disable(self, agent: "Agent") -> None:
        if not (agent.budget_eur_limit > 0 and self._claude_runner):
            return
        try:
            usage = self._claude_runner.get_agent_usage(agent.id)
            cost_eur = usage.get("cost_usd", 0.0) * EUR_RATE
            if cost_eur >= agent.budget_eur_limit:
                logger.warning("Agent %s auto-disabled: cost €%.4f >= limit €%.4f",
                               agent.name, cost_eur, agent.budget_eur_limit)
                agent.enabled = False
                self._save()
        except Exception as exc:
            logger.warning("Budget check failed for %s: %s", agent.name, exc)

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_param(value: str, params: dict, notifica: str, default: Any = None) -> str:
        """Resolve {{param.X}} and {{notifica}} placeholders in a string."""
        if not isinstance(value, str):
            return str(value) if value is not None else (str(default) if default is not None else "")
        value = re.sub(r'\{\{notifica\}\}', notifica or "", value, flags=re.IGNORECASE)
        value = re.sub(r'\{\{valutazione\}\}', params.get("__valutazione__", ""), value, flags=re.IGNORECASE)
        def _repl(m: re.Match) -> str:
            key = m.group(1)
            return str(params.get(key, m.group(0)))
        return re.sub(r'\{\{param\.(\w+)\}\}', _repl, value)

    @staticmethod
    def _resolve_minutes(raw: Any, params: dict, default: int = 5) -> int:
        """Resolve a minutes value that may contain {{param.X}}."""
        if isinstance(raw, (int, float)):
            return max(1, int(raw))
        s = AgentEngine._resolve_param(str(raw), params, "", default)
        try:
            return max(1, int(float(s)))
        except (ValueError, TypeError):
            return max(1, default)

    @staticmethod
    def _split_chain_at_waits(actions: list, params: dict) -> list[tuple[int, list]]:
        """Split an action list into (cumulative_delay_minutes, [actions]) batches at each wait."""
        batches: list[tuple[int, list]] = []
        current_delay = 0
        current_batch: list = []
        for action in actions:
            if action.get("type") == "wait":
                if current_batch:
                    batches.append((current_delay, current_batch))
                    current_batch = []
                raw = action.get("minutes", action.get("default", 5))
                current_delay += AgentEngine._resolve_minutes(raw, params, default=int(action.get("default", 5)))
            else:
                current_batch.append(action)
        if current_batch:
            batches.append((current_delay, current_batch))
        return batches

    def _action_to_task_format(self, action: dict, params: dict, notifica: str) -> dict:
        """Convert a rule action dict to task_engine action format."""
        a_type = action.get("type", "")
        resolve = lambda v, d=None: self._resolve_param(str(v) if v is not None else "", params, notifica, d)

        if a_type == "turn_on":
            return {"type": "call_ha_service", "domain": "homeassistant", "service": "turn_on",
                    "data": {"entity_id": resolve(action.get("entity_id", ""))}}
        if a_type == "turn_off":
            return {"type": "call_ha_service", "domain": "homeassistant", "service": "turn_off",
                    "data": {"entity_id": resolve(action.get("entity_id", ""))}}
        if a_type == "set_value":
            entity_id = resolve(action.get("entity_id", ""))
            value = resolve(action.get("value", ""))
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            service = "set_temperature" if domain == "climate" else "turn_on"
            data: dict = {"entity_id": entity_id}
            if domain == "climate":
                try:
                    data["temperature"] = float(value)
                except (ValueError, TypeError):
                    data["temperature"] = value
            return {"type": "call_ha_service", "domain": domain, "service": service, "data": data}
        if a_type == "call_service":
            entity_id = resolve(action.get("entity_id", action.get("entity_pattern", "")))
            return {"type": "call_ha_service",
                    "domain": action.get("domain", ""),
                    "service": action.get("service", ""),
                    "data": {"entity_id": entity_id} if entity_id else {}}
        if a_type == "notify":
            return {"type": "send_notification",
                    "message": resolve(action.get("message", "{{notifica}}")),
                    "channel": action.get("channel", "ha_push")}
        return action  # pass through unknown types

    def _validate_action(self, action: dict, agent: "Agent") -> bool:
        """Return True if action is permitted by agent's allowed_services and allowed_entities."""
        a_type = action.get("type", "")
        if not agent.allowed_services and not agent.allowed_entities:
            return True

        if a_type in ("turn_on", "turn_off"):
            svc = f"homeassistant.{a_type}"
            entity_id = action.get("entity_id", "")
        elif a_type == "set_value":
            entity_id = action.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            svc = f"{domain}.set_temperature" if domain == "climate" else f"homeassistant.turn_on"
        elif a_type == "call_service":
            svc = f"{action.get('domain','')}.{action.get('service','')}"
            entity_id = action.get("entity_id", action.get("entity_pattern", ""))
        elif a_type == "notify":
            return True  # notifications always allowed
        else:
            return True

        if agent.allowed_services and not any(fnmatch.fnmatch(svc, p) for p in agent.allowed_services):
            logger.warning("Action blocked (service not allowed): %s", svc)
            return False
        if agent.allowed_entities and entity_id and not any(
            fnmatch.fnmatch(entity_id, p) for p in agent.allowed_entities
        ):
            logger.warning("Action blocked (entity not allowed): %s", entity_id)
            return False
        return True

    async def _execute_action_batch(
        self, agent: "Agent", actions: list, params: dict, notifica: str,
        delay_minutes: int = 0, label_suffix: str = "",
    ) -> list[str]:
        """Schedule a batch of (non-wait) actions via task_engine, optionally delayed."""
        if not actions or not self._task_engine:
            return []
        task_actions = [self._action_to_task_format(a, params, notifica) for a in actions
                        if self._validate_action(a, agent)]
        if not task_actions:
            return ["batch:all_blocked"]
        trigger = {"type": "delay", "minutes": delay_minutes} if delay_minutes > 0 else {"type": "immediate"}
        label = f"{agent.name}{label_suffix}"
        try:
            self._task_engine.add_task(
                {"label": label, "trigger": trigger, "actions": task_actions, "one_shot": True},
                agent_id=agent.id,
            )
            return [f"batch({'delayed+' + str(delay_minutes) + 'min' if delay_minutes else 'immediate'}):queued({len(task_actions)})"]
        except Exception as exc:
            return [f"batch:FAILED({exc})"]

    async def _execute_action_chain(
        self, agent: "Agent", actions: list, params: dict, notifica: str,
    ) -> str:
        """Execute a sequential action chain, splitting at wait steps into scheduled tasks."""
        batches = self._split_chain_at_waits(actions, params)
        results: list[str] = []
        for i, (delay, batch) in enumerate(batches):
            suffix = f" — step {i+1}" if len(batches) > 1 else ""
            batch_results = await self._execute_action_batch(
                agent, batch, params, notifica, delay_minutes=delay, label_suffix=suffix
            )
            results.extend(batch_results)
        return "; ".join(results) if results else ""

    # ------------------------------------------------------------------
    # Automatic mode: parse AZIONI block from LLM output
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_azioni_lines(lines: list[str]) -> list[dict]:
        """Parse raw AZIONI command lines (list[str]) into action dicts.

        Each entry in ``lines`` is one command in the format: cmd entity [value]
        """
        actions: list[dict] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 2)
            cmd = parts[0].lower()
            if cmd == "turn_on" and len(parts) >= 2:
                actions.append({"type": "turn_on", "entity_id": parts[1]})
            elif cmd == "turn_off" and len(parts) >= 2:
                actions.append({"type": "turn_off", "entity_id": parts[1]})
            elif cmd == "set_value" and len(parts) >= 3:
                actions.append({"type": "set_value", "entity_id": parts[1], "value": parts[2]})
            elif cmd == "call_service" and len(parts) >= 2:
                svc_parts = parts[1].split(".", 1)
                domain = svc_parts[0]
                service = svc_parts[1] if len(svc_parts) > 1 else ""
                entity_id = parts[2] if len(parts) > 2 else ""
                actions.append({"type": "call_service", "domain": domain, "service": service, "entity_id": entity_id})
            elif cmd == "wait" and len(parts) >= 2:
                try:
                    minutes = max(1, int(float(parts[1])))
                except ValueError:
                    minutes = 5
                actions.append({"type": "wait", "minutes": minutes})
            elif cmd == "notify" and len(parts) >= 3:
                actions.append({"type": "notify", "channel": parts[1], "message": " ".join(parts[2:])})
        return actions

    async def _execute_automatic_actions(
        self, agent: "Agent", structured: dict,
    ) -> str:
        """Execute AZIONI block (automatic mode) or fallback if absent."""
        azioni_lines: list[str] = structured.get("azioni", [])
        notifica = structured.get("notifica", "")
        params = structured.get("params", {})
        if not azioni_lines:
            if agent.fallback_action:
                result = await self._execute_action_chain(
                    agent, [agent.fallback_action], params, notifica
                )
                return f"fallback:{result}"
            return ""
        # Parse raw command lines into action dicts; cap to 20 to prevent runaway
        azioni = self._parse_azioni_lines(azioni_lines[:20])
        if not azioni:
            if azioni_lines:
                logger.warning(
                    "Agent %s: AZIONI block had %d line(s) but none were parseable: %s",
                    agent.id, len(azioni_lines), azioni_lines[:5],
                )
            return ""
        return await self._execute_action_chain(agent, azioni, params, notifica)

    async def _execute_configured_rules(
        self, agent: "Agent", structured: dict,
    ) -> str:
        """Execute configured rules based on VALUTAZIONE (configured mode)."""
        valutazione = (structured.get("valutazione") or "").strip().upper()
        notifica = structured.get("notifica", "")
        params = dict(structured.get("params", {}))
        params["__valutazione__"] = valutazione

        matched_rule = None
        for rule in agent.rules:
            rule_states = [s.strip().upper() for s in rule.get("states", [])]
            if valutazione in rule_states:
                matched_rule = rule
                break

        if matched_rule is None:
            if agent.fallback_action:
                result = await self._execute_action_chain(
                    agent, [agent.fallback_action], params, notifica
                )
                return f"fallback:{result}"
            return ""

        actions = matched_rule.get("actions", [])
        if not actions:
            return ""
        return await self._execute_action_chain(agent, actions, params, notifica)

    async def _execute_actions_for_agent(self, agent: "Agent", structured: dict) -> str:
        """Dispatch to automatic or configured action execution."""
        if agent.action_mode == "configured":
            return await self._execute_configured_rules(agent, structured)
        return await self._execute_automatic_actions(agent, structured)

    # ------------------------------------------------------------------
    # Agent run
    # ------------------------------------------------------------------

    async def _run_agent(
        self, agent: Agent, context: Optional[dict] = None, trigger_fired: Optional[dict] = None
    ) -> str:
        if not self._claude_runner:
            logger.warning("No runner configured")
            return ""
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        self._running_agents.add(agent.id)
        _had_error = False
        structured: dict = {}
        try:
            agent.last_run = datetime.now(timezone.utc).isoformat()
            effective_prompt = (
                f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
                if agent.strategic_context else agent.system_prompt
            )
            if context:
                effective_prompt = f"{effective_prompt}\n\nContext: {context}"

            fired_type = (trigger_fired or {}).get("type", "unknown")
            user_message = f"[Agent trigger: {fired_type}]"

            if agent.type == "agent":
                entity_ctx = self._build_entity_context(agent)
                if entity_ctx:
                    user_message = f"{user_message}\n\n{entity_ctx}"
                try:
                    result, structured = await asyncio.wait_for(
                        self._claude_runner.run_with_actions(
                            user_message=user_message,
                            system_prompt=effective_prompt,
                            action_mode=agent.action_mode,
                            states=agent.states,
                            rules=agent.rules,
                            allowed_tools=agent.allowed_tools or None,
                            allowed_entities=agent.allowed_entities or None,
                            allowed_services=agent.allowed_services or None,
                            allowed_endpoints=agent.allowed_endpoints,
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            agent_type=agent.type,
                            restrict_to_home=agent.restrict_to_home,
                            agent_id=agent.id,
                            response_mode=agent.response_mode,
                        ),
                        timeout=_AGENT_RUN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"Timeout dopo {_AGENT_RUN_TIMEOUT}s — il modello non ha risposto in tempo"
                    )
                action_taken = await self._execute_actions_for_agent(agent, structured)
            else:
                try:
                    result = await asyncio.wait_for(
                        self._claude_runner.chat(
                            user_message=user_message,
                            system_prompt=effective_prompt,
                            allowed_tools=agent.allowed_tools or None,
                            allowed_entities=agent.allowed_entities or None,
                            allowed_services=agent.allowed_services or None,
                            allowed_endpoints=agent.allowed_endpoints,
                            model=agent.model,
                            max_tokens=agent.max_tokens,
                            agent_type=agent.type,
                            restrict_to_home=agent.restrict_to_home,
                            require_confirmation=agent.require_confirmation,
                            agent_id=agent.id,
                            response_mode=agent.response_mode,
                        ),
                        timeout=_AGENT_RUN_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"Timeout dopo {_AGENT_RUN_TIMEOUT}s — il modello non ha risposto in tempo"
                    )
                action_taken = None

            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            agent.last_result = result
            self._append_execution_log(
                agent, result, inp_before, out_before, tool_calls_snapshot,
                success=True, structured=structured, action_taken=action_taken,
                trigger_fired=trigger_fired,
            )
            self._save()
            self._check_budget_auto_disable(agent)
            return result
        except Exception as exc:
            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            _had_error = True
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            self._append_execution_log(
                agent, agent.last_result, inp_before, out_before, tool_calls_snapshot, success=False
            )
            self._save()
            self._check_budget_auto_disable(agent)
            return agent.last_result
        finally:
            self._running_agents.discard(agent.id)
            if _had_error:
                self._error_agents.add(agent.id)
            else:
                self._error_agents.discard(agent.id)
            if self._mqtt_publisher:
                runner = self._claude_runner
                budget_eur = 0.0
                tokens_today = 0
                if runner and hasattr(runner, "get_agent_usage"):
                    try:
                        usage = runner.get_agent_usage(agent.id)
                        budget_eur = round(usage.get("cost_usd", 0.0) * EUR_RATE, 4)
                        tokens_today = usage.get("tokens_today", 0)
                    except Exception as exc:
                        logger.debug("get_agent_usage(%s) failed: %s", agent.id, exc)
                remaining: Any = (
                    max(0.0, agent.budget_eur_limit - budget_eur)
                    if agent.budget_eur_limit > 0 else "unlimited"
                )
                asyncio.create_task(
                    self._mqtt_publisher.publish_agent_state(
                        agent, budget_eur=budget_eur,
                        status="error" if _had_error else "idle",
                        budget_remaining_eur=remaining,
                        tokens_used_today=tokens_today,
                    ),
                    name=f"mqtt_pub_{agent.id}",
                )
            if agent.id in self._pending_mqtt_runs:
                self._pending_mqtt_runs.discard(agent.id)
                asyncio.create_task(self._run_agent(agent), name=f"mqtt_queued_{agent.id}")

    def _append_execution_log(
        self,
        agent: Agent,
        result: str,
        inp_before: int,
        out_before: int,
        tool_calls_snapshot: list,
        success: bool,
        structured: Optional[dict] = None,
        action_taken: Optional[str] = None,
        trigger_fired: Optional[dict] = None,
    ) -> None:
        inp_after = getattr(self._claude_runner, "total_input_tokens", 0)
        out_after = getattr(self._claude_runner, "total_output_tokens", 0)
        s = structured or {}
        record = {
            "timestamp": agent.last_run,
            "trigger": (trigger_fired or {}).get("type", agent.triggers[0].get("type", "unknown") if agent.triggers else "manual"),
            "tool_calls": [t.get("tool", "") for t in tool_calls_snapshot],
            "input_tokens": inp_after - inp_before,
            "output_tokens": out_after - out_before,
            "result_summary": (result or "")[:1000],
            "success": success and not (result or "").startswith("Error:"),
            "eval_status": s.get("valutazione"),
            "notifica": s.get("notifica"),
            "params": s.get("params"),
            "action_taken": action_taken,
        }
        agent.execution_log = (agent.execution_log + [record])[-20:]
