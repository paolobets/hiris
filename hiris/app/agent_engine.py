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
#
# v0.10.4 fix: il default deve almeno coprire il timeout configurato dall'utente
# per il modello locale via local_model.request_timeout (esportato da run.sh
# come OLLAMA_REQUEST_TIMEOUT). Senza questo fallback, anche se l'utente alza
# OLLAMA_REQUEST_TIMEOUT a 600/800s, l'asyncio.wait_for esterno cuttava sempre
# a 300s perché AGENT_RUN_TIMEOUT non è esportato da run.sh. Margine 1.2x
# garantisce che il run completi prima dell'aborto outer.
_OLLAMA_REQUEST_TIMEOUT_FALLBACK = int(os.environ.get("OLLAMA_REQUEST_TIMEOUT", "120"))
_AGENT_RUN_TIMEOUT = int(
    os.environ.get(
        "AGENT_RUN_TIMEOUT",
        str(max(int(_OLLAMA_REQUEST_TIMEOUT_FALLBACK * 1.2), 300)),
    )
)

# Rate-limit auto-backoff per agente (v0.9.10). Quando un agente schedulato
# riceve N risposte indicanti rate-limit upstream entro la finestra, lo
# pausiamo per il cooldown indicato — evita di bruciare la quota giornaliera
# OpenRouter free-tier su trigger ripetuti che falliranno tutti.
_RATE_LIMIT_THRESHOLD = int(os.environ.get("AGENT_RATE_LIMIT_THRESHOLD", "3"))
_RATE_LIMIT_WINDOW_SEC = int(os.environ.get("AGENT_RATE_LIMIT_WINDOW_SEC", "600"))
_RATE_LIMIT_COOLDOWN_SEC = int(os.environ.get("AGENT_RATE_LIMIT_COOLDOWN_SEC", "3600"))
_RATE_LIMIT_RE = re.compile(r"rate[\s\-]?limit", re.IGNORECASE)

logger = logging.getLogger(__name__)


DEFAULT_AGENTS_DATA_PATH = "/data/agents.json"
DEFAULT_AGENT_ID = "hiris-default"


@dataclass
class Agent:
    # NOTE (Slice 5): triggers/type/action_mode/rules/states/fallback_action/
    # budget_eur_limit were the "proactive" execution fields — the engine no
    # longer schedules, reacts to state changes, or executes actions/rules for
    # any agent (see AgentEngine._run_agent). They are kept on the dataclass
    # only because handlers_agents.py still validates/persists/reads them
    # (API + config UI backward-compat); trimming the schema is Task 2.
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
    knowledge_access: dict = field(default_factory=lambda: {"allow_sensitive": False, "kinds": "all"})


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class AgentEngine:
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
        self._task_engine: Any = None
        # Serialize tmp-write + os.replace across concurrent _save() calls
        # (executor uses a thread pool — two fire-and-forget _save() can otherwise
        # overlap on the same .tmp file and corrupt state).
        self._save_lock = threading.Lock()
        # Per-agent backoff for upstream rate-limit / generic API errors.
        # _rate_limit_failures[agent_id] = list of monotonic-second timestamps.
        # _rate_limit_paused_until[agent_id] = monotonic seconds, or None.
        # When N=_RATE_LIMIT_THRESHOLD failures occur within
        # _RATE_LIMIT_WINDOW_SEC, the agent is paused for
        # _RATE_LIMIT_COOLDOWN_SEC. Schedule keeps firing but _run_agent
        # short-circuits during the cooldown — quota is preserved.
        self._rate_limit_failures: dict[str, list[float]] = {}
        self._rate_limit_paused_until: dict[str, float] = {}

    def set_claude_runner(self, runner: Any) -> None:
        self._claude_runner = runner

    def set_entity_cache(self, cache: Any) -> None:
        self._entity_cache = cache

    def set_mqtt_publisher(self, publisher) -> None:
        self._mqtt_publisher = publisher

    def set_task_engine(self, engine: Any) -> None:
        self._task_engine = engine

    async def start(self) -> None:
        self._scheduler.start()
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
                    knowledge_access=raw.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
                )
                self._agents[agent.id] = agent
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

    # Output-token ceiling per agent type. Chat needs room for large outputs
    # (multi-view dashboards, long scripts); non-chat agents stay capped low to
    # bound cost, latency, and prompt-injection blast radius. Chat cap mirrors
    # claude_runner.CHAT_MAX_TOKENS (kept in sync deliberately, not imported, to
    # avoid a module cycle).
    _CHAT_MAX_TOKENS_CAP = 16000
    _AGENT_MAX_TOKENS_CAP = 8192

    @classmethod
    def _cap_max_tokens(cls, value: Any, agent_type: str) -> int:
        cap = cls._CHAT_MAX_TOKENS_CAP if agent_type == "chat" else cls._AGENT_MAX_TOKENS_CAP
        return min(int(value), cap)

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
            max_tokens=self._cap_max_tokens(
                data.get("max_tokens", 16000 if normalized_type == "chat" else 4096),
                normalized_type,
            ),
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
            knowledge_access=data.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
        )
        self._agents[agent.id] = agent
        if self._mqtt_publisher:
            asyncio.create_task(
                self._mqtt_publisher.publish_discovery(agent),
                name=f"mqtt_disc_{agent.id}",
            )
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
        "thinking_budget", "knowledge_access",
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
                    setattr(agent, key, self._cap_max_tokens(data[key], agent.type))
                else:
                    setattr(agent, key, data[key])
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
    # Autonomous agent scheduling (interval/cron triggers) and reactive
    # state-change dispatch were retired in Slice 5 — the Sentinella
    # (watcher/) is now the sole proactive engine. `_unschedule_agent`
    # remains as a defensive no-op-safe cleanup for any job left over from
    # a pre-upgrade scheduler state.

    def _unschedule_agent(self, agent_id: str) -> None:
        for job in list(self._scheduler.get_jobs()):
            if job.id == agent_id or job.id.startswith(f"{agent_id}__"):
                try:
                    self._scheduler.remove_job(job.id)
                except Exception as exc:
                    logger.debug("remove_job(%s) failed: %s", job.id, exc)

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
    # Agent run
    # ------------------------------------------------------------------
    # Slice 5 retired the action/rules execution machinery (AZIONI parsing,
    # configured rules, action chains/batches) and the notion of an agent
    # "acting" on its own conclusions. The Sentinella (watcher/) is now the
    # sole proactive/actuating engine. `_run_agent` below only ever produces
    # text via the runner's plain chat() — it never executes actions.

    # ------------------------------------------------------------------
    # Rate-limit backoff helpers (v0.9.10)
    # ------------------------------------------------------------------

    def _is_rate_limited(self, result: str) -> bool:
        """Return True if `result` looks like an upstream rate-limit reply."""
        if not isinstance(result, str):
            return False
        return bool(_RATE_LIMIT_RE.search(result))

    def _record_rate_limit_failure(self, agent_id: str) -> None:
        """Track a rate-limit failure timestamp; pause the agent if the
        threshold is crossed inside the window."""
        now = time.monotonic()
        # Drop timestamps outside the window
        recent = [
            ts for ts in self._rate_limit_failures.get(agent_id, [])
            if now - ts <= _RATE_LIMIT_WINDOW_SEC
        ]
        recent.append(now)
        self._rate_limit_failures[agent_id] = recent
        if len(recent) >= _RATE_LIMIT_THRESHOLD:
            paused_until = now + _RATE_LIMIT_COOLDOWN_SEC
            self._rate_limit_paused_until[agent_id] = paused_until
            logger.warning(
                "Agent %s: %d rate-limit failures in %ds — pausing for %ds. "
                "Considera passare a un modello a pagamento per agenti schedulati.",
                agent_id, len(recent), _RATE_LIMIT_WINDOW_SEC, _RATE_LIMIT_COOLDOWN_SEC,
            )
            # Clear the failure list so the next pause requires fresh evidence
            # after the cooldown — otherwise old failures would re-trigger.
            self._rate_limit_failures[agent_id] = []

    def _clear_rate_limit_failures(self, agent_id: str) -> None:
        """Reset failure history after a successful (non-rate-limited) run."""
        self._rate_limit_failures.pop(agent_id, None)

    def _is_in_rate_limit_pause(self, agent_id: str) -> bool:
        """Return True if the agent is currently in cooldown after too many
        rate-limit failures. Auto-clears expired pauses."""
        until = self._rate_limit_paused_until.get(agent_id)
        if until is None:
            return False
        if time.monotonic() >= until:
            self._rate_limit_paused_until.pop(agent_id, None)
            logger.info("Agent %s: rate-limit cooldown expired, resuming.", agent_id)
            return False
        return True

    async def _run_agent(
        self, agent: Agent, context: Optional[dict] = None, trigger_fired: Optional[dict] = None
    ) -> str:
        """Run a persona once and return its reply text — no autonomous actuation.

        Reachable from the manual "run" API (`run_agent` → `handle_run_agent`).
        `context`/`trigger_fired` are kept for the execution-log record shape;
        callers other than the manual API no longer exist (Slice 5 retired the
        scheduler/reactive triggers that used to pass them).
        """
        if not self._claude_runner:
            logger.warning("No runner configured")
            return ""
        # Per-agent concurrency guard: a manual run landing while another run
        # for the same agent is still in flight is skipped rather than run
        # concurrently — avoids racing on shared ClaudeRunner state
        # (last_tool_calls, usage).
        if agent.id in self._running_agents:
            logger.info("Agent %s already running — skipping overlapping trigger", agent.id)
            return "[skipped: already running]"
        if self._is_in_rate_limit_pause(agent.id):
            remaining = int(self._rate_limit_paused_until[agent.id] - time.monotonic())
            logger.info(
                "Agent %s: skipping run, in rate-limit cooldown for %ds more.",
                agent.id, remaining,
            )
            return f"[skipped: rate-limit cooldown, retry in {remaining}s]"
        logger.info("Running agent: %s (%s)", agent.name, agent.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        self._running_agents.add(agent.id)
        _had_error = False
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

            _ka = (agent.knowledge_access or {}) if isinstance(agent.knowledge_access, dict) else {}
            _allow_sensitive = bool(_ka.get("allow_sensitive", False))
            _kinds_raw = _ka.get("kinds", "all")
            _knowledge_kinds = None if _kinds_raw == "all" else _kinds_raw
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
                        mode="automatic",
                        max_tokens=agent.max_tokens,
                        agent_type=agent.type,
                        restrict_to_home=agent.restrict_to_home,
                        require_confirmation=agent.require_confirmation,
                        agent_id=agent.id,
                        response_mode=agent.response_mode,
                        thinking_budget=agent.thinking_budget,
                        knowledge_allow_sensitive=_allow_sensitive,
                        knowledge_kinds=_knowledge_kinds,
                    ),
                    timeout=_AGENT_RUN_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout dopo {_AGENT_RUN_TIMEOUT}s — il modello non ha risposto in tempo"
                )

            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            agent.last_result = result
            # Track upstream rate-limit replies and pause the agent if they
            # repeat — protects the daily quota on OpenRouter free models.
            if self._is_rate_limited(result):
                self._record_rate_limit_failure(agent.id)
            else:
                self._clear_rate_limit_failures(agent.id)
            # Detect upstream API failures returned as a string by the runner
            # (no exception raised). Without this the row would log success=True
            # while the summary reads "Errore temporaneo del servizio AI…".
            _is_upstream_err = isinstance(result, str) and (
                "Errore temporaneo del servizio AI" in result
                or self._is_rate_limited(result)
            )
            self._append_execution_log(
                agent, result, inp_before, out_before, tool_calls_snapshot,
                success=not _is_upstream_err, trigger_fired=trigger_fired,
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

    def _append_execution_log(
        self,
        agent: Agent,
        result: str,
        inp_before: int,
        out_before: int,
        tool_calls_snapshot: list,
        success: bool,
        trigger_fired: Optional[dict] = None,
    ) -> None:
        inp_after = getattr(self._claude_runner, "total_input_tokens", 0)
        out_after = getattr(self._claude_runner, "total_output_tokens", 0)
        # Capture extended-thinking blocks if any. Truncate per-block to keep
        # the agents.json file from growing unbounded — full reasoning is
        # rarely needed in the UI, just the gist for debug.
        thinking_blocks = list(getattr(self._claude_runner, "last_thinking_blocks", None) or [])
        thinking_blocks = [(t or "")[:2000] for t in thinking_blocks]
        record = {
            "timestamp": agent.last_run,
            "trigger": (trigger_fired or {}).get("type", agent.triggers[0].get("type", "unknown") if agent.triggers else "manual"),
            "tool_calls": [t.get("tool", "") for t in tool_calls_snapshot],
            "input_tokens": inp_after - inp_before,
            "output_tokens": out_after - out_before,
            "result_summary": (result or "")[:1000],
            "success": success and not (result or "").startswith("Error:"),
            # Retired with the action/rules machinery (Slice 5) — kept as None
            # so older frontend log-row rendering (eval badge / action chip)
            # degrades gracefully instead of KeyError-ing on old records.
            "eval_status": None,
            "notifica": None,
            "params": None,
            "action_taken": None,
            "thinking_blocks": thinking_blocks,
        }
        agent.execution_log = (agent.execution_log + [record])[-20:]
