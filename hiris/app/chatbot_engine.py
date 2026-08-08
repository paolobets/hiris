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
from .claude_runner import RunnerBackendError
from .config import EUR_RATE

# Timeout complessivo per un singolo run di chatbot. Evita che un modello locale
# lento (Ollama) blocchi APScheduler per ore. Configurabile via env.
#
# v0.10.4 fix: il default deve almeno coprire il timeout configurato dall'utente
# per il modello locale via local_model.request_timeout (esportato da run.sh
# come OLLAMA_REQUEST_TIMEOUT). Senza questo fallback, anche se l'utente alza
# OLLAMA_REQUEST_TIMEOUT a 600/800s, l'asyncio.wait_for esterno cuttava sempre
# a 300s perché CHATBOT_RUN_TIMEOUT non è esportato da run.sh. Margine 1.2x
# garantisce che il run completi prima dell'aborto outer.
_OLLAMA_REQUEST_TIMEOUT_FALLBACK = int(os.environ.get("OLLAMA_REQUEST_TIMEOUT", "120"))
_CHATBOT_RUN_TIMEOUT = int(
    os.environ.get(
        "CHATBOT_RUN_TIMEOUT",
        str(max(int(_OLLAMA_REQUEST_TIMEOUT_FALLBACK * 1.2), 300)),
    )
)

# Rate-limit auto-backoff per chatbot (v0.9.10). Quando un chatbot schedulato
# riceve N risposte indicanti rate-limit upstream entro la finestra, lo
# pausiamo per il cooldown indicato — evita di bruciare la quota giornaliera
# OpenRouter free-tier su trigger ripetuti che falliranno tutti.
_RATE_LIMIT_THRESHOLD = int(os.environ.get("CHATBOT_RATE_LIMIT_THRESHOLD", "3"))
_RATE_LIMIT_WINDOW_SEC = int(os.environ.get("CHATBOT_RATE_LIMIT_WINDOW_SEC", "600"))
_RATE_LIMIT_COOLDOWN_SEC = int(os.environ.get("CHATBOT_RATE_LIMIT_COOLDOWN_SEC", "3600"))
_RATE_LIMIT_RE = re.compile(r"rate[\s\-]?limit", re.IGNORECASE)

logger = logging.getLogger(__name__)


# Fix 4 (Important, whole-branch review, final fix wave): nomi dei due tool ritirati
# dalla fusione di Task 2 (recall_knowledge/save_knowledge -> recall_memory/
# save_memory). Un Chatbot creato PRIMA di questo branch puo' averli ancora
# nel proprio `allowed_tools` persistito (erano due checkbox separate); lo
# stesso vale per la CSV EXECUTE_API_TOOLS delle opzioni dell'add-on. Il
# filtro per nome esatto (claude_runner.py:713, `t["name"] in allowed_tools`)
# non li riconosce piu': un nome non mappato fa perdere in silenzio
# lettura/scrittura del second brain a un bot il cui system prompt di base
# ora ordina di chiamare save_memory subito -- il modello non puo' obbedire
# e viene spinto proprio nel "preso nota" che quell'ordine vieta.
LEGACY_TOOL_ALIASES = {
    "recall_knowledge": "recall_memory",
    "save_knowledge": "save_memory",
}


def normalize_tool_names(names: list[str]) -> list[str]:
    """Applica LEGACY_TOOL_ALIASES e de-duplica, preservando l'ordine di
    prima comparsa. Idempotente: rieseguirla sul proprio output non cambia
    nulla. Va chiamata in OGNI punto che legge un elenco di nomi di tool
    persistito/configurato da prima della fusione -- oggi
    `chatbot_engine.py` (Chatbot.allowed_tools, al caricamento) e
    `handlers_execute.py` (parse_execute_policy, la CSV EXECUTE_API_TOOLS)."""
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        mapped = LEGACY_TOOL_ALIASES.get(n, n)
        if mapped not in seen:
            seen.add(mapped)
            out.append(mapped)
    return out


DEFAULT_CHATBOTS_DATA_PATH = "/data/chatbots.json"
DEFAULT_CHATBOT_ID = "hiris-default"


@dataclass
class Chatbot:
    # Slice 5 Task 2: this dataclass is a persona (used only by chat) — the
    # "proactive" execution fields that used to describe an autonomous agent
    # (type, triggers, action_mode, rules, states, fallback_action,
    # budget_eur_limit) are gone. Task 1 already retired the engine code that
    # scheduled/reacted/executed on them (see ChatbotEngine._run_chatbot); this
    # task trims the schema itself now that nothing reads those fields.
    id: str
    name: str
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
    max_chat_turns: int = 0              # chat only
    allowed_endpoints: Optional[list] = None
    response_mode: str = "auto"
    # Extended Thinking budget tokens (0 = disabled).
    # When >0, Claude returns thinking blocks alongside the answer (sonnet-4.5+/
    # opus-4+ only). The runner clamps to max_tokens-1 if invalid.
    thinking_budget: int = 0
    knowledge_access: dict = field(default_factory=lambda: {"allow_sensitive": False, "kinds": "all"})


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ChatbotEngine:
    def __init__(self, ha_client: HAClient, data_path: str = DEFAULT_CHATBOTS_DATA_PATH) -> None:
        self._chatbots: dict[str, Chatbot] = {}
        self._scheduler = AsyncIOScheduler()
        self._claude_runner: Any = None
        self._ha = ha_client
        self._data_path = data_path
        self._entity_cache: Any = None
        self._running_chatbots: set[str] = set()
        self._error_chatbots: set[str] = set()
        self._mqtt_publisher = None
        self._task_engine: Any = None
        # Serialize tmp-write + os.replace across concurrent _save() calls
        # (executor uses a thread pool — two fire-and-forget _save() can otherwise
        # overlap on the same .tmp file and corrupt state).
        self._save_lock = threading.Lock()
        # Per-chatbot backoff for upstream rate-limit / generic API errors.
        # _rate_limit_failures[agent_id] = list of monotonic-second timestamps.
        # _rate_limit_paused_until[agent_id] = monotonic seconds, or None.
        # When N=_RATE_LIMIT_THRESHOLD failures occur within
        # _RATE_LIMIT_WINDOW_SEC, the chatbot is paused for
        # _RATE_LIMIT_COOLDOWN_SEC. Schedule keeps firing but _run_chatbot
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
        self._seed_default_chatbot()
        logger.info("ChatbotEngine started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("ChatbotEngine stopped")

    def _save(self) -> None:
        # schema_version 4 (SP-4 Fase A Task 1: Agent -> Chatbot rename).
        # schema_version 3 (Slice 5 Task 2) dropped the proactive-only
        # fields (type/triggers/action_mode/rules/states/fallback_action/
        # budget_eur_limit) from the persisted shape. No migration on load —
        # a v1/v2 file simply has those keys ignored by _load()'s explicit
        # field list below.
        data = {"schema_version": 4, "chatbots": [asdict(c) for c in self._chatbots.values()]}
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
                    logger.error("Failed to persist chatbots: %s", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def _load(self) -> None:
        # One-time migration agents.json -> chatbots.json (idempotente).
        legacy = self._data_path.replace("chatbots.json", "agents.json")
        if not os.path.exists(self._data_path) and os.path.exists(legacy):
            try:
                with open(legacy, encoding="utf-8") as f:
                    raw = json.load(f)
                raw.setdefault("chatbots", raw.pop("agents", []))
                raw["schema_version"] = 4
                tmp = self._data_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(raw, f, indent=2, default=str)
                os.replace(tmp, self._data_path)
                logger.info("Migrated agents.json -> chatbots.json")
            except Exception:
                logger.warning("agents.json migration failed", exc_info=True)
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, encoding="utf-8") as f:
                data = json.load(f)
            for raw in data.get("chatbots", data.get("agents", [])):
                chatbot = Chatbot(
                    id=raw["id"],
                    name=raw["name"],
                    system_prompt=raw.get("system_prompt", ""),
                    # Fix 4 (whole-branch review, final fix wave): a Chatbot persisted
                    # before the memoria-unica merge may still name the
                    # retired recall_knowledge/save_knowledge tools here --
                    # normalize_tool_names maps them to the current
                    # recall_memory/save_memory (and de-duplicates, in case
                    # both the old and new name were ever saved together).
                    allowed_tools=normalize_tool_names(raw.get("allowed_tools", [])),
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
                    max_chat_turns=int(raw.get("max_chat_turns", 0)),
                    allowed_endpoints=raw.get("allowed_endpoints"),
                    response_mode=raw.get("response_mode", "auto"),
                    thinking_budget=int(raw.get("thinking_budget", 0) or 0),
                    knowledge_access=raw.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
                )
                self._chatbots[chatbot.id] = chatbot
        except Exception as exc:
            logger.error("Failed to load chatbots from %s: %s", self._data_path, exc)

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

    def _seed_default_chatbot(self) -> None:
        if DEFAULT_CHATBOT_ID not in self._chatbots:
            chatbot = Chatbot(
                id=DEFAULT_CHATBOT_ID,
                name="HIRIS",
                system_prompt=self._DEFAULT_SYSTEM_PROMPT,
                allowed_tools=[],
                enabled=True,
                is_default=True,
            )
            self._chatbots[DEFAULT_CHATBOT_ID] = chatbot
            self._save()
        else:
            chatbot = self._chatbots[DEFAULT_CHATBOT_ID]
            changed = False
            if chatbot.system_prompt in self._LEGACY_DEFAULT_PROMPTS:
                chatbot.system_prompt = self._DEFAULT_SYSTEM_PROMPT
                changed = True
            if chatbot.allowed_tools:
                chatbot.allowed_tools = []
                changed = True
            if changed:
                self._save()

    def get_default_chatbot(self) -> Optional[Chatbot]:
        return self._chatbots.get(DEFAULT_CHATBOT_ID)

    # Output-token ceiling for personas. Chat needs room for large outputs
    # (multi-view dashboards, long scripts) — every persona is a chat entity
    # now (Slice 5 Task 2 dropped the non-chat "agent" type), so there is a
    # single cap. Kept as a class attr (not imported from claude_runner) to
    # avoid a module cycle — CHAT_MAX_TOKENS there must stay in sync.
    _CHAT_MAX_TOKENS_CAP = 16000

    @classmethod
    def _cap_max_tokens(cls, value: Any) -> int:
        return min(int(value), cls._CHAT_MAX_TOKENS_CAP)

    def create_chatbot(self, data: dict) -> Chatbot:
        chatbot = Chatbot(
            id=str(uuid.uuid4()),
            name=data["name"],
            system_prompt=data.get("system_prompt", ""),
            allowed_tools=data.get("allowed_tools", []),
            enabled=data.get("enabled", True),
            is_default=False,
            strategic_context=data.get("strategic_context", ""),
            allowed_entities=data.get("allowed_entities", []),
            allowed_services=data.get("allowed_services", []),
            model=data.get("model", "auto"),
            max_tokens=self._cap_max_tokens(data.get("max_tokens", 16000)),
            restrict_to_home=bool(data.get("restrict_to_home", False)),
            require_confirmation=bool(data.get("require_confirmation", False)),
            max_chat_turns=int(data.get("max_chat_turns", 0)),
            allowed_endpoints=data.get("allowed_endpoints"),
            response_mode=data.get("response_mode", "auto"),
            thinking_budget=max(0, int(data.get("thinking_budget", 0) or 0)),
            knowledge_access=data.get("knowledge_access", {"allow_sensitive": False, "kinds": "all"}),
        )
        self._chatbots[chatbot.id] = chatbot
        if self._mqtt_publisher:
            asyncio.create_task(
                self._mqtt_publisher.publish_discovery(chatbot),
                name=f"mqtt_disc_{chatbot.id}",
            )
        self._save()
        return chatbot

    def get_chatbot(self, agent_id: str) -> Optional[Chatbot]:
        return self._chatbots.get(agent_id)

    UPDATABLE_FIELDS = {
        "name", "system_prompt", "allowed_tools", "enabled",
        "strategic_context", "allowed_entities", "allowed_services",
        "model", "max_tokens", "restrict_to_home", "require_confirmation",
        "max_chat_turns", "allowed_endpoints",
        "response_mode", "thinking_budget", "knowledge_access",
    }

    def update_chatbot(self, agent_id: str, data: dict) -> Optional[Chatbot]:
        chatbot = self._chatbots.get(agent_id)
        if not chatbot:
            return None
        enabled_before = chatbot.enabled
        self._unschedule_chatbot(agent_id)
        _BOOL_FIELDS = {"restrict_to_home", "require_confirmation"}
        _INT_FIELDS = {"max_chat_turns"}
        for key in self.UPDATABLE_FIELDS:
            if key in data:
                if key in _BOOL_FIELDS:
                    setattr(chatbot, key, bool(data[key]))
                elif key in _INT_FIELDS:
                    setattr(chatbot, key, int(data[key]))
                elif key == "max_tokens":
                    setattr(chatbot, key, self._cap_max_tokens(data[key]))
                else:
                    setattr(chatbot, key, data[key])
        self._save()
        if self._mqtt_publisher and chatbot.enabled != enabled_before:
            try:
                asyncio.create_task(
                    self._mqtt_publisher.publish_chatbot_state(chatbot, budget_eur=0.0, status="idle"),
                    name=f"mqtt_enable_{chatbot.id}",
                )
            except RuntimeError:
                pass
        return chatbot

    def delete_chatbot(self, agent_id: str) -> bool:
        chatbot = self._chatbots.get(agent_id)
        if chatbot is None or chatbot.is_default:
            return False
        self._unschedule_chatbot(agent_id)
        del self._chatbots[agent_id]
        self._save()
        return True

    async def run_chatbot(self, chatbot: "Chatbot") -> str:
        return await self._run_chatbot(chatbot)

    def list_chatbots(self) -> dict[str, dict]:
        return {c.id: asdict(c) for c in self._chatbots.values()}

    def get_chatbot_status(self, agent_id: str) -> str:
        if agent_id in self._running_chatbots:
            return "running"
        if agent_id in self._error_chatbots:
            return "error"
        return "idle"

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------
    # Autonomous agent scheduling (interval/cron triggers) and reactive
    # state-change dispatch were retired in Slice 5 — the Sentinella
    # (watcher/) is now the sole proactive engine. `_unschedule_chatbot`
    # remains as a defensive no-op-safe cleanup for any job left over from
    # a pre-upgrade scheduler state.

    def _unschedule_chatbot(self, agent_id: str) -> None:
        for job in list(self._scheduler.get_jobs()):
            if job.id == agent_id or job.id.startswith(f"{agent_id}__"):
                try:
                    self._scheduler.remove_job(job.id)
                except Exception as exc:
                    logger.debug("remove_job(%s) failed: %s", job.id, exc)

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def _build_entity_context(self, chatbot: "Chatbot") -> str:
        if self._entity_cache is None:
            return ""
        all_entities = self._entity_cache.get_all_useful()
        if chatbot.allowed_entities:
            relevant = [
                e for e in all_entities
                if any(fnmatch.fnmatch(e["id"], pat) for pat in chatbot.allowed_entities)
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

    # ------------------------------------------------------------------
    # Chatbot run
    # ------------------------------------------------------------------
    # Slice 5 retired the action/rules execution machinery (AZIONI parsing,
    # configured rules, action chains/batches) and the notion of an agent
    # "acting" on its own conclusions. The Sentinella (watcher/) is now the
    # sole proactive/actuating engine. `_run_chatbot` below only ever produces
    # text via the runner's plain chat() — it never executes actions.
    #
    # Slice 5 Task 2: every persona is a chat entity now (the "agent"/
    # "monitor" type and its dedicated entity-context injection are gone
    # along with the `type` field) — `_build_entity_context` above is kept
    # only as a directly-tested helper, no longer called from here.

    # ------------------------------------------------------------------
    # Rate-limit backoff helpers (v0.9.10)
    # ------------------------------------------------------------------

    def _is_rate_limited(self, result: str) -> bool:
        """Return True if `result` looks like an upstream rate-limit reply."""
        if not isinstance(result, str):
            return False
        return bool(_RATE_LIMIT_RE.search(result))

    def _record_rate_limit_failure(self, agent_id: str) -> None:
        """Track a rate-limit failure timestamp; pause the chatbot if the
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
                "Chatbot %s: %d rate-limit failures in %ds — pausing for %ds. "
                "Considera passare a un modello a pagamento per chatbot schedulati.",
                agent_id, len(recent), _RATE_LIMIT_WINDOW_SEC, _RATE_LIMIT_COOLDOWN_SEC,
            )
            # Clear the failure list so the next pause requires fresh evidence
            # after the cooldown — otherwise old failures would re-trigger.
            self._rate_limit_failures[agent_id] = []

    def _clear_rate_limit_failures(self, agent_id: str) -> None:
        """Reset failure history after a successful (non-rate-limited) run."""
        self._rate_limit_failures.pop(agent_id, None)

    def _is_in_rate_limit_pause(self, agent_id: str) -> bool:
        """Return True if the chatbot is currently in cooldown after too many
        rate-limit failures. Auto-clears expired pauses."""
        until = self._rate_limit_paused_until.get(agent_id)
        if until is None:
            return False
        if time.monotonic() >= until:
            self._rate_limit_paused_until.pop(agent_id, None)
            logger.info("Chatbot %s: rate-limit cooldown expired, resuming.", agent_id)
            return False
        return True

    async def _run_chatbot(
        self, chatbot: Chatbot, context: Optional[dict] = None, trigger_fired: Optional[dict] = None
    ) -> str:
        """Run a persona once and return its reply text — no autonomous actuation.

        Reachable from the manual "run" API (`run_chatbot` → `handle_run_agent`).
        `context`/`trigger_fired` are kept for the execution-log record shape;
        callers other than the manual API no longer exist (Slice 5 retired the
        scheduler/reactive triggers that used to pass them).
        """
        if not self._claude_runner:
            logger.warning("No runner configured")
            return ""
        # Per-chatbot concurrency guard: a manual run landing while another run
        # for the same chatbot is still in flight is skipped rather than run
        # concurrently — avoids racing on shared ClaudeRunner state
        # (last_tool_calls, usage).
        if chatbot.id in self._running_chatbots:
            logger.info("Chatbot %s already running — skipping overlapping trigger", chatbot.id)
            return "[skipped: already running]"
        if self._is_in_rate_limit_pause(chatbot.id):
            remaining = int(self._rate_limit_paused_until[chatbot.id] - time.monotonic())
            logger.info(
                "Chatbot %s: skipping run, in rate-limit cooldown for %ds more.",
                chatbot.id, remaining,
            )
            return f"[skipped: rate-limit cooldown, retry in {remaining}s]"
        logger.info("Running chatbot: %s (%s)", chatbot.name, chatbot.id)
        inp_before = getattr(self._claude_runner, "total_input_tokens", 0)
        out_before = getattr(self._claude_runner, "total_output_tokens", 0)
        self._running_chatbots.add(chatbot.id)
        _had_error = False
        try:
            chatbot.last_run = datetime.now(timezone.utc).isoformat()
            effective_prompt = (
                f"{chatbot.strategic_context}\n\n---\n\n{chatbot.system_prompt}"
                if chatbot.strategic_context else chatbot.system_prompt
            )
            if context:
                effective_prompt = f"{effective_prompt}\n\nContext: {context}"

            fired_type = (trigger_fired or {}).get("type", "unknown")
            user_message = f"[Agent trigger: {fired_type}]"

            _ka = (chatbot.knowledge_access or {}) if isinstance(chatbot.knowledge_access, dict) else {}
            _allow_sensitive = bool(_ka.get("allow_sensitive", False))
            _kinds_raw = _ka.get("kinds", "all")
            _knowledge_kinds = None if _kinds_raw == "all" else _kinds_raw
            try:
                # asyncio.timeout (not wait_for): wait_for wraps the coroutine in
                # a NEW Task on Python 3.11, which gets a COPY of the context, so
                # the runner's per-call ContextVar tool-calls/thinking (review A/#3)
                # would be invisible here. asyncio.timeout awaits in THIS Task.
                async with asyncio.timeout(_CHATBOT_RUN_TIMEOUT):
                    result = await self._claude_runner.chat(
                        user_message=user_message,
                        system_prompt=effective_prompt,
                        allowed_tools=chatbot.allowed_tools or None,
                        allowed_entities=chatbot.allowed_entities or None,
                        allowed_services=chatbot.allowed_services or None,
                        allowed_endpoints=chatbot.allowed_endpoints,
                        model=chatbot.model,
                        mode="automatic",
                        max_tokens=chatbot.max_tokens,
                        # Every persona is the chat entity now (Slice 5 Task 2
                        # dropped the `type` field) — "chat" is not read off
                        # `chatbot`, it's simply what a persona is.
                        agent_type="chat",
                        restrict_to_home=chatbot.restrict_to_home,
                        require_confirmation=chatbot.require_confirmation,
                        agent_id=chatbot.id,
                        response_mode=chatbot.response_mode,
                        thinking_budget=chatbot.thinking_budget,
                        knowledge_allow_sensitive=_allow_sensitive,
                        knowledge_kinds=_knowledge_kinds,
                    )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Timeout dopo {_CHATBOT_RUN_TIMEOUT}s — il modello non ha risposto in tempo"
                )
            except RunnerBackendError as exc:
                # Runner API failure (rate limit/connection/timeout/auth/5xx).
                # Before review C/#13's fix this came back as a plain string
                # from chat() (no exception at all); reproduce that exact
                # shape here so the rest of this method (rate-limit
                # detection/pause, execution-log success flag, return value)
                # behaves exactly as it did — a hard crash into the generic
                # `except Exception` below would prefix "Error: " and skip
                # the rate-limit bookkeeping this branch relies on.
                result = exc.friendly_message

            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            chatbot.last_result = result
            # Track upstream rate-limit replies and pause the chatbot if they
            # repeat — protects the daily quota on OpenRouter free models.
            if self._is_rate_limited(result):
                self._record_rate_limit_failure(chatbot.id)
            else:
                self._clear_rate_limit_failures(chatbot.id)
            # Detect upstream API failures returned as a string by the runner
            # (no exception raised). Without this the row would log success=True
            # while the summary reads "Errore temporaneo del servizio AI…".
            _is_upstream_err = isinstance(result, str) and (
                "Errore temporaneo del servizio AI" in result
                or self._is_rate_limited(result)
            )
            self._append_execution_log(
                chatbot, result, inp_before, out_before, tool_calls_snapshot,
                success=not _is_upstream_err, trigger_fired=trigger_fired,
            )
            self._save()
            return result
        except Exception as exc:
            tool_calls_snapshot = list(getattr(self._claude_runner, "last_tool_calls", None) or [])
            _had_error = True
            logger.error("Chatbot %s failed: %s", chatbot.name, exc)
            chatbot.last_result = f"Error: {exc}"
            self._append_execution_log(
                chatbot, chatbot.last_result, inp_before, out_before, tool_calls_snapshot, success=False
            )
            self._save()
            return chatbot.last_result
        finally:
            self._running_chatbots.discard(chatbot.id)
            if _had_error:
                self._error_chatbots.add(chatbot.id)
            else:
                self._error_chatbots.discard(chatbot.id)
            if self._mqtt_publisher:
                runner = self._claude_runner
                budget_eur = 0.0
                tokens_today = 0
                if runner and hasattr(runner, "get_chatbot_usage"):
                    try:
                        usage = runner.get_chatbot_usage(chatbot.id)
                        budget_eur = round(usage.get("cost_usd", 0.0) * EUR_RATE, 4)
                        tokens_today = usage.get("tokens_today", 0)
                    except Exception as exc:
                        logger.debug("get_chatbot_usage(%s) failed: %s", chatbot.id, exc)
                asyncio.create_task(
                    self._mqtt_publisher.publish_chatbot_state(
                        chatbot, budget_eur=budget_eur,
                        status="error" if _had_error else "idle",
                        # No more per-chatbot budget_eur_limit (Slice 5 Task 2) —
                        # there is nothing left to subtract a remainder from.
                        budget_remaining_eur="unlimited",
                        tokens_used_today=tokens_today,
                    ),
                    name=f"mqtt_pub_{chatbot.id}",
                )

    def _append_execution_log(
        self,
        chatbot: Chatbot,
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
        # the chatbots.json file from growing unbounded — full reasoning is
        # rarely needed in the UI, just the gist for debug.
        thinking_blocks = list(getattr(self._claude_runner, "last_thinking_blocks", None) or [])
        thinking_blocks = [(t or "")[:2000] for t in thinking_blocks]
        record = {
            "timestamp": chatbot.last_run,
            # No more `chatbot.triggers` to fall back on (Slice 5 Task 2 removed
            # the field) — "manual" is the only source left for a persona run.
            "trigger": (trigger_fired or {}).get("type", "manual"),
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
        chatbot.execution_log = (chatbot.execution_log + [record])[-20:]
