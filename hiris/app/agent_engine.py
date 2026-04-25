import asyncio
import fnmatch
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
    model: str = "auto"
    max_tokens: int = 4096
    restrict_to_home: bool = False
    require_confirmation: bool = False
    execution_log: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    budget_eur_limit: float = 0.0
    max_chat_turns: int = 0


class AgentEngine:
    def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_AGENTS_DATA_PATH) -> None:
        self._agents: dict[str, Agent] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None  # set after init via set_claude_runner()
        self._ha = ha_client
        self._data_path = data_path
        self._entity_cache: Any = None
        self._running_agents: set[str] = set()
        self._mqtt_publisher = None

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    def set_entity_cache(self, cache: Any) -> None:
        self._entity_cache = cache

    def set_mqtt_publisher(self, publisher) -> None:
        self._mqtt_publisher = publisher

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
                    model=raw.get("model", "auto"),
                    max_tokens=raw.get("max_tokens", 4096),
                    restrict_to_home=raw.get("restrict_to_home", False),
                    require_confirmation=raw.get("require_confirmation", False),
                    execution_log=raw.get("execution_log", []),
                    actions=raw.get("actions", []),
                    budget_eur_limit=raw.get("budget_eur_limit", 0.0),
                    max_chat_turns=int(raw.get("max_chat_turns", 0)),
                )
                self._agents[agent.id] = agent
                if agent.enabled and agent.type in ("monitor", "preventive"):
                    self._schedule_agent(agent)
        except Exception as exc:
            logger.error("Failed to load agents from %s: %s", self._data_path, exc)

    # Agent-specific instructions only — tool list and base rules are injected
    # at runtime via BASE_SYSTEM_PROMPT in claude_runner.py.
    _DEFAULT_SYSTEM_PROMPT = (
        "Sei l'assistente principale per la gestione della smart home.\n"
        "Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
        "La sezione CASA in fondo al prompt è uno snapshot di orientamento:"
        " usa i tool per valori precisi come temperature e stati correnti."
    )

    # Old factory prompts that can be safely overwritten on upgrade
    _LEGACY_DEFAULT_PROMPTS = {
        "Sei HIRIS, assistente per la smart home. Rispondi nella lingua dell'utente.",
        "You are HIRIS, an AI assistant for smart home management. Respond in the same language as the user.",
        # v0.0.9: missing trigger/toggle/send_notification, no snapshot note
        (
            "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
            "Strumenti disponibili:\n"
            "- get_home_status(): panoramica compatta di tutti i dispositivi utili. Usalo come prima chiamata.\n"
            "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
            "- search_entities(query, top_k, domain): ricerca semantica di entità per linguaggio naturale.\n"
            "- get_entities_by_domain(domain): tutte le entità di un dominio (es. 'light', 'sensor').\n"
            "- get_entity_states(ids): stato attuale di entità specifiche per ID.\n"
            "- get_area_entities(): scopre stanze/aree e i dispositivi associati.\n"
            "- get_ha_automazioni(): elenco delle automazioni.\n"
            "- get_energy_history(days): storico consumi energetici.\n"
            "- get_weather_forecast(hours): previsioni meteo.\n"
            "- call_ha_service(domain, service, data): controlla dispositivi.\n\n"
            "Regole:\n"
            "- Per qualsiasi domanda sulla casa usa SEMPRE gli strumenti per dati reali.\n"
            "- Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
            "- Non inventare dati: usa gli strumenti.\n"
            "- Rispondi nella lingua dell'utente."
        ),
        # v0.1.7: had search_entities (deleted tool) — must migrate
        (
            "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
            "Strumenti disponibili:\n"
            "- get_home_status(): panoramica compatta di tutti i dispositivi utili. Usalo come prima chiamata.\n"
            "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
            "- search_entities(query, top_k, domain): ricerca semantica di entità per linguaggio naturale.\n"
            "- get_entities_by_domain(domain): tutte le entità di un dominio (es. 'light', 'sensor').\n"
            "- get_entity_states(ids): stato attuale e attributi di entità specifiche per ID."
            " Per i termostati (climate.*) restituisce anche temperatura attuale e setpoint.\n"
            "- get_area_entities(): scopre stanze/aree e i dispositivi associati.\n"
            "- get_ha_automations(): elenco delle automazioni HA.\n"
            "- trigger_automation(id): esegue manualmente un'automazione.\n"
            "- toggle_automation(id, enabled): attiva o disattiva un'automazione.\n"
            "- get_energy_history(days): storico consumi energetici.\n"
            "- get_weather_forecast(hours): previsioni meteo.\n"
            "- call_ha_service(domain, service, data): controlla dispositivi.\n"
            "- send_notification(message, channel): invia notifiche (HA push, Telegram).\n\n"
            "Regole:\n"
            "- Per qualsiasi domanda sulla casa usa SEMPRE gli strumenti per dati reali.\n"
            "- La sezione CASA in fondo a questo prompt è uno snapshot di orientamento (aggiornato ogni 60s):"
            " usa i tool per valori precisi come temperature, stati correnti, sensori.\n"
            "- Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
            "- Non inventare dati: usa gli strumenti.\n"
            "- Rispondi nella lingua dell'utente."
        ),
        # v0.3.13: missing task tools and no-disclaimer rule
        (
            "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
            "Strumenti disponibili:\n"
            "- get_home_status(): panoramica compatta di tutti i dispositivi utili. Usalo come prima chiamata.\n"
            "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
            "- get_entities_by_domain(domain): tutte le entità di un dominio (es. 'light', 'sensor').\n"
            "- get_entity_states(ids): stato attuale e attributi di entità specifiche per ID."
            " Per i termostati (climate.*) restituisce anche temperatura attuale e setpoint.\n"
            "- get_area_entities(): scopre stanze/aree e i dispositivi associati.\n"
            "- get_ha_automations(): elenco delle automazioni HA.\n"
            "- trigger_automation(id): esegue manualmente un'automazione.\n"
            "- toggle_automation(id, enabled): attiva o disattiva un'automazione.\n"
            "- get_energy_history(days): storico consumi energetici.\n"
            "- get_weather_forecast(hours): previsioni meteo.\n"
            "- call_ha_service(domain, service, data): controlla dispositivi.\n"
            "- send_notification(message, channel): invia notifiche (HA push, Telegram).\n\n"
            "Regole:\n"
            "- Per qualsiasi domanda sulla casa usa SEMPRE gli strumenti per dati reali.\n"
            "- La sezione CASA in fondo a questo prompt è uno snapshot di orientamento (aggiornato ogni 60s):"
            " usa i tool per valori precisi come temperature, stati correnti, sensori.\n"
            "- Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
            "- Non inventare dati: usa gli strumenti.\n"
            "- Rispondi nella lingua dell'utente."
        ),
        # v0.3.14: full tool list in system_prompt (now moved to BASE_SYSTEM_PROMPT)
        (
            "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n\n"
            "Strumenti disponibili:\n"
            "- get_home_status(): panoramica compatta di tutti i dispositivi utili. Usalo come prima chiamata.\n"
            "- get_entities_on(): tutti i dispositivi attualmente accesi.\n"
            "- get_entities_by_domain(domain): tutte le entità di un dominio (es. 'light', 'sensor').\n"
            "- get_entity_states(ids): stato attuale e attributi di entità specifiche per ID."
            " Per i termostati (climate.*) restituisce anche temperatura attuale e setpoint.\n"
            "- get_area_entities(): scopre stanze/aree e i dispositivi associati.\n"
            "- get_ha_automations(): elenco delle automazioni HA.\n"
            "- trigger_automation(id): esegue manualmente un'automazione.\n"
            "- toggle_automation(id, enabled): attiva o disattiva un'automazione.\n"
            "- get_energy_history(days): storico consumi energetici.\n"
            "- get_weather_forecast(hours): previsioni meteo.\n"
            "- call_ha_service(domain, service, data): controlla dispositivi.\n"
            "- send_notification(message, channel): invia notifiche (HA push, Telegram).\n"
            "- create_task(label, trigger, actions): pianifica un'azione futura (es. accendi luce tra 30 min).\n"
            "- list_tasks(agent_id, status): elenca i task pianificati.\n"
            "- cancel_task(task_id): annulla un task pianificato.\n\n"
            "Regole:\n"
            "- Per qualsiasi domanda sulla casa usa SEMPRE gli strumenti per dati reali.\n"
            "- La sezione CASA in fondo a questo prompt è uno snapshot di orientamento (aggiornato ogni 60s):"
            " usa i tool per valori precisi come temperature, stati correnti, sensori.\n"
            "- Per scoprire cosa c'è in casa chiama get_home_status() o get_area_entities().\n"
            "- Non inventare dati: usa gli strumenti.\n"
            "- Se hai chiamato uno strumento e ha risposto con successo, l'azione o il dato è reale:"
            " non aggiungere disclaimers come 'ho inventato', 'ho simulato' o 'non ho eseguito nulla'.\n"
            "- Rispondi nella lingua dell'utente."
        ),
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
            changed = False
            if agent.system_prompt in self._LEGACY_DEFAULT_PROMPTS:
                agent.system_prompt = self._DEFAULT_SYSTEM_PROMPT
                changed = True
            # Default agent must always have all tools unrestricted
            if agent.allowed_tools:
                agent.allowed_tools = []
                changed = True
            if changed:
                self._save()
                logger.info("Migrated default agent to v0.3.15")

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
            model=data.get("model", "auto"),
            max_tokens=min(int(data.get("max_tokens", 4096)), 8192),
            restrict_to_home=bool(data.get("restrict_to_home", False)),
            require_confirmation=bool(data.get("require_confirmation", False)),
            actions=data.get("actions", []),
            budget_eur_limit=float(data.get("budget_eur_limit", 0.0)),
            max_chat_turns=int(data.get("max_chat_turns", 0)),
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
        "model", "max_tokens", "restrict_to_home", "require_confirmation",
        "actions", "budget_eur_limit", "max_chat_turns",
    }

    def update_agent(self, agent_id: str, data: dict) -> Optional[Agent]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        self._unschedule_agent(agent_id)
        _BOOL_FIELDS = {"restrict_to_home", "require_confirmation"}
        _FLOAT_FIELDS = {"budget_eur_limit"}
        _INT_FIELDS = {"max_chat_turns"}
        _MAX_TOKENS_CAP = 8192
        for key in self.UPDATABLE_FIELDS:
            if key in data:
                if key in _BOOL_FIELDS:
                    setattr(agent, key, bool(data[key]))
                elif key in _FLOAT_FIELDS:
                    setattr(agent, key, float(data[key]))
                elif key in _INT_FIELDS:
                    setattr(agent, key, int(data[key]))
                elif key == "max_tokens":
                    setattr(agent, key, min(int(data[key]), _MAX_TOKENS_CAP))
                else:
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

    def get_agent_status(self, agent_id: str) -> str:
        if agent_id in self._running_agents:
            return "running"
        agent = self._agents.get(agent_id)
        if agent is None or not agent.enabled:
            return "idle"
        return "idle"

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
                    coalesce=True,
                    misfire_grace_time=60,
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

    def _build_entity_context(self, agent: "Agent") -> str:
        """Build entity state context string for pre-injection into proactive agent runs."""
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
        lines = ["[CONTESTO ENTITÀ]"]
        for e in relevant[:50]:
            name = e.get("name") or e["id"]
            unit = f" {e['unit']}" if e.get("unit") else ""
            lines.append(f"- {name}: {e['state']}{unit}")
        return "\n".join(lines)

    async def _run_agent(self, agent: Agent, context: Optional[dict] = None) -> str:
        if not self._claude_runner:
            logger.warning("No Claude runner configured")
            return ""
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        self._running_agents.add(agent.id)
        try:
            agent.last_run = datetime.now(timezone.utc).isoformat()
            if agent.strategic_context:
                effective_prompt = f"{agent.strategic_context}\n\n---\n\n{agent.system_prompt}"
            else:
                effective_prompt = agent.system_prompt
            if context:
                effective_prompt = f"{effective_prompt}\n\nContext: {context}"
            # Pre-inject current entity states for proactive agents
            user_message = f"[Agent trigger: {agent.trigger.get('type')}]"
            if agent.type in ("monitor", "reactive", "preventive"):
                entity_ctx = self._build_entity_context(agent)
                if entity_ctx:
                    user_message = f"{user_message}\n\n{entity_ctx}"

            agent_actions: list = list(getattr(agent, "actions", []) or [])
            if agent_actions:
                result, eval_status, action_taken = await self._claude_runner.run_with_actions(
                    user_message=user_message,
                    system_prompt=effective_prompt,
                    actions=agent_actions,
                    allowed_tools=agent.allowed_tools or None,
                    allowed_entities=agent.allowed_entities or None,
                    allowed_services=agent.allowed_services or None,
                    model=agent.model,
                    max_tokens=agent.max_tokens,
                    agent_type=agent.type,
                    restrict_to_home=agent.restrict_to_home,
                    require_confirmation=agent.require_confirmation,
                    agent_id=agent.id,
                )
            else:
                result = await self._claude_runner.chat(
                    user_message=user_message,
                    system_prompt=effective_prompt,
                    allowed_tools=agent.allowed_tools or None,
                    allowed_entities=agent.allowed_entities or None,
                    allowed_services=agent.allowed_services or None,
                    model=agent.model,
                    max_tokens=agent.max_tokens,
                    agent_type=agent.type,
                    restrict_to_home=agent.restrict_to_home,
                    require_confirmation=agent.require_confirmation,
                    agent_id=agent.id,
                )
                eval_status = None
                action_taken = None
            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            agent.last_result = result
            self._append_execution_log(agent, result, inp_before, out_before, tool_calls_snapshot, success=True,
                                       eval_status=eval_status, action_taken=action_taken)
            self._save()
            # Auto-disable if budget_eur_limit exceeded
            if agent.budget_eur_limit > 0 and self._claude_runner:
                try:
                    usage = self._claude_runner.get_agent_usage(agent.id)
                    cost_eur = usage.get("cost_usd", 0.0) * 0.92
                    if cost_eur >= agent.budget_eur_limit:
                        logger.warning(
                            "Agent %s auto-disabled: cost €%.4f >= limit €%.4f",
                            agent.name, cost_eur, agent.budget_eur_limit,
                        )
                        agent.enabled = False
                        self._save()
                except Exception as exc:
                    logger.warning("Budget check failed for %s: %s", agent.name, exc)
            return result
        except Exception as exc:
            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            logger.error("Agent %s failed: %s", agent.name, exc)
            agent.last_result = f"Error: {exc}"
            self._append_execution_log(agent, agent.last_result, inp_before, out_before, tool_calls_snapshot, success=False)
            self._save()
            if agent.budget_eur_limit > 0 and self._claude_runner:
                try:
                    usage = self._claude_runner.get_agent_usage(agent.id)
                    cost_eur = usage.get("cost_usd", 0.0) * 0.92
                    if cost_eur >= agent.budget_eur_limit:
                        logger.warning(
                            "Agent %s auto-disabled on failure: cost €%.4f >= limit €%.4f",
                            agent.name, cost_eur, agent.budget_eur_limit,
                        )
                        agent.enabled = False
                        self._save()
                except Exception as budget_exc:
                    logger.warning("Budget check failed for %s: %s", agent.name, budget_exc)
            return agent.last_result
        finally:
            self._running_agents.discard(agent.id)

    def _append_execution_log(
        self,
        agent: Agent,
        result: str,
        inp_before: int,
        out_before: int,
        tool_calls_snapshot: list,
        success: bool,
        eval_status: Optional[str] = None,
        action_taken: Optional[str] = None,
    ) -> None:
        inp_after = getattr(self._claude_runner, "total_input_tokens", 0)
        out_after = getattr(self._claude_runner, "total_output_tokens", 0)
        tool_calls = [t.get("tool", "") for t in tool_calls_snapshot]
        record = {
            "timestamp": agent.last_run,
            "trigger": agent.trigger.get("type", "unknown"),
            "tool_calls": tool_calls,
            "input_tokens": inp_after - inp_before,
            "output_tokens": out_after - out_before,
            "result_summary": (result or "")[:1000],
            "success": success and not (result or "").startswith("Error:"),
            "eval_status": eval_status,
            "action_taken": action_taken,
        }
        agent.execution_log = (agent.execution_log + [record])[-20:]
