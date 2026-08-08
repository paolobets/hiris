import asyncio
import contextvars
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional
import anthropic
# fetta E2 Task 8 ("escono i trentaquattro"): il catalogo da 34 sparisce, e
# con lui le tre copie divergenti che la mappa del prodotto ha condannato (34
# per la chat -- QUESTO file --, 16 per l'execute API e 15 per l'MCP interno,
# entrambi gia' usciti). La chat non riceve piu' un catalogo da qui: passa
# `strumenti=STRUMENTI_CONOSCENZA` (casa/strumenti.py, quattro strumenti che
# conoscono la casa e non la toccano). Le sole 18 definizioni sotto restano
# perche' le nomina `EVALUATION_ONLY_TOOLS`: l'unico catalogo ancora vivo,
# usato dalla Sentinella via `run_with_actions`.
from .tools.ha_tools import (
    TOOL_DEF as HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
)
from .tools.energy_tools import TOOL_DEF as ENERGY_TOOL
from .tools.history_tools import GET_HISTORY_TOOL_DEF
from .tools.weather_tools import TOOL_DEF as WEATHER_TOOL
from .tools.automation_tools import (
    GET_AUTOMATIONS_TOOL_DEF,
    GET_AUTOMATION_CONFIG_TOOL_DEF,
)
from .tools.task_tools import (
    CREATE_TASK_TOOL_DEF, LIST_TASKS_TOOL_DEF, CANCEL_TASK_TOOL_DEF,
)
from .tools.calendar_tools import GET_CALENDAR_EVENTS_TOOL_DEF
from .tools.memory_tools import RECALL_MEMORY_TOOL_DEF
from .tools.health_tools import GET_HA_HEALTH_TOOL_DEF
from .tools.advisory_tools import GET_ADVISORIES_TOOL_DEF
from .tools.diagnostics_tools import GET_LOGBOOK_TOOL_DEF

logger = logging.getLogger(__name__)


class RunnerBackendError(Exception):
    """Raised by a runner's chat()/run_with_actions() when the underlying
    provider API call itself failed (rate limit, connection error, timeout,
    auth failure, 5xx, or any other persistent outage) — as opposed to the
    model producing a normal (if unusual) reply.

    Review C/#13: ClaudeRunner/OpenAICompatRunner used to CATCH these errors
    and RETURN a friendly Italian string, indistinguishable from a real
    successful reply to any caller. LLMRouter's ordered-backend fallback loop
    wraps chat()/run_with_actions() in `except Exception` specifically to
    fail over to the next configured backend on a primary outage — but a
    returned string never raises, so the loop always "succeeded" on the
    first (broken) backend and the fallback chain was dead code.

    `friendly_message` carries the exact user-facing string the runner used
    to return directly. LLMRouter catches this exception to try the next
    backend, and once every backend in the chain has failed, surfaces the
    LAST failure's `friendly_message` to the end user — the router becomes
    the single place that produces the user-facing degradation. Callers that
    bypass the router (e.g. ChatbotEngine._run_chatbot, handlers_chat.handle_chat
    when an agent pins an explicit non-"auto" model) catch it directly at
    their own call site to preserve their pre-existing graceful-degradation
    behavior instead of crashing.
    """

    def __init__(self, friendly_message: str) -> None:
        super().__init__(friendly_message)
        self.friendly_message = friendly_message

    def __str__(self) -> str:  # so `str(exc)` == the friendly text everywhere
        return self.friendly_message


_TOOL_RESULT_COMPRESS_LEN = 300  # chars to keep per old tool result

def _compress_old_tool_results(messages: list[dict], keep_last: int = 2) -> None:
    """Truncate tool_result content in older iterations to save input tokens.

    Keeps the last `keep_last` tool_result sets at full size; earlier ones
    are truncated because Claude has already processed them and they're only
    re-sent for conversation continuity, not for reasoning.
    """
    tr_indices = [
        i for i, m in enumerate(messages)
        if m["role"] == "user"
        and isinstance(m.get("content"), list)
        and m["content"]
        and isinstance(m["content"][0], dict)
        and m["content"][0].get("type") == "tool_result"
    ]
    for idx in tr_indices[:-keep_last] if len(tr_indices) > keep_last else []:
        compressed = []
        for block in messages[idx]["content"]:
            if block.get("type") == "tool_result":
                raw = block.get("content", "")
                if isinstance(raw, str) and len(raw) > _TOOL_RESULT_COMPRESS_LEN:
                    block = {**block, "content": raw[:_TOOL_RESULT_COMPRESS_LEN] + "…[troncato]"}
            compressed.append(block)
        messages[idx] = {**messages[idx], "content": compressed}

# ── Base system prompt ─────────────────────────────────────────────────────
# Always injected at runtime BEFORE any agent-specific instructions.
# Agents configure WHAT to do and HOW to behave; this layer defines the tools
# available and the invariant anti-hallucination rules.
BASE_SYSTEM_PROMPT = (
    "Sei HIRIS, assistente AI integrata in Home Assistant con accesso completo alla casa.\n"
    "Hai a disposizione strumenti per leggere stati, controllare dispositivi, inviare notifiche,"
    " gestire automazioni, calendario, task, memoria e salute del sistema.\n\n"
    "## Regole fondamentali\n"
    "- Usa SEMPRE gli strumenti per dati sulla casa — non inventare stati, valori o entità.\n"
    "- Non dichiarare azioni mai eseguite: se non hai chiamato il tool, non dire di averlo fatto.\n"
    "- Se hai chiamato uno strumento con successo, l'azione è reale:\n"
    "  non aggiungere disclaimers come 'ho inventato', 'ho simulato' o 'non ho realmente eseguito'.\n"
    "- Quando l'utente dichiara qualcosa di duraturo su di sé, sulla casa o su come vuole le cose —"
    " una preferenza, un vincolo, un guasto, una regola operativa — chiama save_memory subito, senza"
    " chiedere il permesso: basta l'affermazione, non serve che dica 'ricordati che'. Non salvare lo"
    " stato di adesso né una richiesta una tantum, né ciò che puoi rileggere da Home Assistant quando"
    " serve.\n"
    "- 'Preso nota' senza aver chiamato save_memory è la stessa azione mai eseguita vietata sopra:"
    " non dirlo se non hai salvato.\n"
    "- Rispondi nella lingua dell'utente."
)

# fetta E2 Task 8: `CALL_SERVICE_TOOL_DEF`, `DAILY_BRIEFING_TOOL_DEF` e
# `CONFIRM_PENDING_TOOL_DEF` sono usciti da qui insieme al resto dei 34: nessuno
# dei tre e' nominato da `EVALUATION_ONLY_TOOLS` (tutti e tre chat-only per
# costruzione -- attuano, o leggono la memoria/i documenti del maggiordomo), e
# la chat non offre piu' un catalogo da questo file (STRUMENTI_CONOSCENZA,
# casa/strumenti.py). Senza un catalogo che li nomini erano gia' irraggiungibili
# per qualunque chiamante.

# EVALUATION_TOOL_DEFS (fetta E2 Task 8, ex `ALL_TOOL_DEFS`): non e' piu' "il
# catalogo di fabbrica" da cui la chat sceglie -- quel ruolo lo aveva quando
# esisteva un solo posto dove i 34 strumenti vivevano. Oggi la chat riceve il
# suo catalogo dall'esterno (`strumenti=STRUMENTI_CONOSCENZA`); l'unico
# chiamante che arriva ancora fin qui SENZA passare `strumenti` e'
# `run_with_actions` (la Sentinella), che poi restringe con `allowed_tools`
# a `EVALUATION_ONLY_TOOLS` (sotto). Questa lista contiene percio' SOLO le
# definizioni nominate da quel set: cancellare un tool da qui senza prima
# toglierlo da `EVALUATION_ONLY_TOOLS` romperebbe la Sentinella (`t["name"] in
# allowed_tools` non troverebbe piu' nulla per quel nome).
EVALUATION_TOOL_DEFS = [
    HA_TOOL,
    GET_AREA_ENTITIES_TOOL_DEF,
    GET_HOME_STATUS_TOOL_DEF,
    GET_ENTITIES_ON_TOOL_DEF,
    GET_ENTITIES_BY_DOMAIN_TOOL_DEF,
    ENERGY_TOOL,
    GET_HISTORY_TOOL_DEF,
    WEATHER_TOOL,
    GET_AUTOMATIONS_TOOL_DEF,
    GET_AUTOMATION_CONFIG_TOOL_DEF,
    CREATE_TASK_TOOL_DEF,
    LIST_TASKS_TOOL_DEF,
    CANCEL_TASK_TOOL_DEF,
    GET_CALENDAR_EVENTS_TOOL_DEF,
    RECALL_MEMORY_TOOL_DEF,
    GET_HA_HEALTH_TOOL_DEF,
    GET_ADVISORIES_TOOL_DEF,
    GET_LOGBOOK_TOOL_DEF,
]

# Tools available to non-chat agents in evaluation mode.
# Excludes direct-execution tools (send_notification, call_ha_service,
# trigger_automation, toggle_automation, http_request) to prevent prompt
# injection from HA entity state from triggering real-world actions.
EVALUATION_ONLY_TOOLS = frozenset({
    "get_entity_states", "get_area_entities", "get_home_status",
    "get_entities_on", "get_entities_by_domain",
    "get_energy_history", "get_weather_forecast", "get_history",
    "get_ha_automations", "get_automation_config", "get_calendar_events",
    "create_task", "list_tasks", "cancel_task",
    "recall_memory",  # read-only — safe for non-chat agents. Task 2 (memoria
                      # unica) merged the old recall_knowledge into this same
                      # tool, so this single entry now covers both.
    "get_ha_health",  # read-only cached data — safe for proactive monitors
    "get_advisories",  # sola lettura sulle segnalazioni gia' note del Brain:
                       # un agente che sorveglia la casa deve poterle vedere
    "get_logbook",     # sola lettura sulla cronologia degli eventi: sapere cosa
                       # e' successo e' esattamente il mestiere di un sorvegliante
    # render_template excluded ON PURPOSE, and NOT because it writes -- non
    # scrive nulla, HA si limita a renderizzare. Il motivo e' un altro: un
    # template Jinja puo' leggere QUALUNQUE stato di Home Assistant, e un agente
    # non-chat gira proprio SULLO STATO di HA. Il nome o l'attributo di
    # un'entita' sono testo che un dispositivo (o chi lo controlla) puo'
    # scegliere: un'entita' battezzata in modo ostile diventa un'istruzione nel
    # contesto dell'agente, che potrebbe valutare un template arbitrario e
    # rastrellare l'intera casa senza che nessun perimetro di entita' possa
    # fermarlo (un template non ha entity_id da filtrare). In chat la stessa
    # richiesta la fa un umano che sta guardando la risposta: e' un rischio
    # accettato li' e non altrove. Chat-only.
    # create_automation_proposal excluded: writes to store — chat-only
})

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
# Higher default output ceiling for interactive chat: complex requests (a
# multi-view dashboard, a long script) legitimately need more than the 4096
# eval-agent cap. Kept well under the model max so the non-streaming SDK path
# doesn't hit the request-timeout guard; per le plance molto grandi il modello
# propone poche viste per volta invece di una singola risposta gigante.
CHAT_MAX_TOKENS = 16000
MAX_TOOL_ITERATIONS = 10
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]

AUTO_MODEL_MAP: dict[str, str] = {
    "chat": "claude-sonnet-4-6",
    "agent": "claude-haiku-4-5-20251001",
}

from .backends.pricing import PRICING as _PRICING


def resolve_model(model: str, agent_type: str, default_model: str = "") -> str:
    if model == "auto":
        return default_model or AUTO_MODEL_MAP.get(agent_type, MODEL)
    return model

# Models that support Anthropic Extended Thinking. For others (e.g. Haiku 4.5,
# Sonnet < 4.5) the API errors with 400 if `thinking` is supplied. Pattern-based
# so future model strings (claude-sonnet-4-7, claude-opus-4-8 ...) work without
# editing this list.
_THINKING_CAPABLE_PATTERNS = ("sonnet-4-5", "sonnet-4-6", "sonnet-4-7", "opus-4")


def _build_thinking_param(
    thinking_budget: int, effective_model: str, max_tokens: int
) -> Optional[dict]:
    """Build the `thinking` kwarg for Anthropic messages.create, or None.

    Returns None when thinking is disabled / unsupported by the model.
    The runner silently disables thinking on non-capable models to avoid
    surprising the user with an API 400 — frontend validation already prevents
    this for new agents but legacy agents.json may carry stale combos.
    """
    if thinking_budget <= 0:
        return None
    if not any(p in effective_model for p in _THINKING_CAPABLE_PATTERNS):
        logger.warning(
            "thinking_budget=%d but model %s is not thinking-capable — disabling",
            thinking_budget, effective_model,
        )
        return None
    if thinking_budget < 1024:
        logger.warning("thinking_budget=%d below Anthropic minimum 1024 — disabling", thinking_budget)
        return None
    if thinking_budget >= max_tokens:
        clamped = max_tokens - 1
        if clamped < 1024:
            logger.warning(
                "thinking_budget=%d >= max_tokens=%d and max_tokens too small for minimum 1024 — disabling",
                thinking_budget, max_tokens,
            )
            return None
        logger.warning(
            "thinking_budget=%d >= max_tokens=%d — clamping to %d",
            thinking_budget, max_tokens, clamped,
        )
        thinking_budget = clamped
    return {"type": "enabled", "budget_tokens": thinking_budget}


_TRUNCATION_NOTICE = (
    "⚠️ La risposta è stata troncata perché ha raggiunto il limite di token "
    "(max_tokens). Se stavi creando qualcosa di grande (es. una dashboard con "
    "molte stanze), chiedimi di crearla in modo incrementale — prima la dashboard "
    "con poche viste, poi una vista/stanza alla volta — oppure semplifica la richiesta."
)


def _max_tokens_message(text_blocks: list[str]) -> str:
    """Message returned when generation is cut off by max_tokens. Surfaces the
    truncation explicitly instead of returning a misleading partial preamble
    (which reads as 'done' to the user while nothing was actually executed)."""
    prefix = "\n".join(text_blocks).strip()
    return f"{prefix}\n\n{_TRUNCATION_NOTICE}" if prefix else _TRUNCATION_NOTICE


RESTRICT_PROMPT = (
    "Sei HIRIS, assistente per la smart home. "
    "Rispondi SOLO a domande relative alla casa, domotica, energia, clima, sicurezza. "
    "Per qualsiasi altro argomento, rispondi educatamente che non puoi aiutare su quel tema."
)

# Review finale fetta E2, I-5: `CONFIRMATION_COVERED_TOOLS` e
# `REQUIRE_CONFIRMATION_PROMPT` sono uscite. Nominavano cinque strumenti che
# ATTUANO (call_ha_service, trigger_automation, toggle_automation,
# set_input_helper, create_ha_config): nessuno dei cinque esiste in un
# catalogo raggiungibile da nessun runner (chat = i quattro strumenti di
# conoscenza di STRUMENTI_CONOSCENZA; Sentinella = soli read + task, ne'
# l'uno ne' l'altro li offre). L'iniezione nel system prompt (qui sotto e nei
# due punti gemelli di backends/openai_compat_runner.py) istruiva il modello
# a chiedere conferma prima di strumenti che non puo' comunque chiamare --
# una promessa vuota. `require_confirmation` resta un campo di
# configurazione del Chatbot (UI/persistenza), ma oggi non ha alcun effetto
# osservabile sul system prompt.


# Review finale fetta E2, I-4: `_redact_stream_tool_calls` e' uscita.
# Redigeva l'OTP di `confirm_pending` prima di emetterlo in un evento SSE
# "done" -- ma `confirm_pending` non e' dichiarato in nessun catalogo
# raggiungibile (STRUMENTI_CONOSCENZA, EVALUATION_TOOL_DEFS): un modello non
# puo' emettere un tool_use per un tool mai offerto, quindi il ramo che
# redigeva non era mai raggiungibile da nessun input reale -- un OTP dentro
# un tool input non esiste piu' in tutto il prodotto (l'impianto OTP e'
# uscito col Task 5). `handlers_chat.py`'s `_debug_input` (la controparte
# non-streaming) e' uscita per lo stesso motivo.


# ── Per-call tool-call / thinking-block isolation (review A/#3) ────────────
# ClaudeRunner and OpenAICompatRunner are long-lived singletons shared by
# every interactive chat request AND every scheduler-driven agent run on the
# same event loop. `last_tool_calls`/`last_thinking_blocks` used to be plain
# unlocked instance attributes: chat() reset them to [] then appended after
# `await` points. Two overlapping calls on the SAME runner instance (e.g. a
# chat request racing a background persona run) could interleave their
# resets/appends and leak one call's tool-call inputs (entity IDs,
# memory-recall content, HTTP payloads) into a completely different call's
# debug_payload / SSE `done` event, or silently wipe them.
#
# Fix: back both attributes with a contextvars.ContextVar instead of a plain
# instance attribute, via the _PerCallList descriptor below. asyncio.Task
# creation copies the current Context, and ContextVar.set() inside a Task
# mutates only that Task's own copy — never a sibling Task's. Two concurrent
# Tasks calling chat()/run_with_actions() on the very same runner instance
# therefore never observe each other's resets or appends, even though they
# share the object. Within a single Task (the normal, non-overlapping case —
# e.g. handlers_chat.py reading `runner.last_tool_calls` right after
# `await runner.chat(...)`), the value set inside chat() is still visible to
# the caller immediately afterward: that is just a regular attribute read
# within the same unmodified Context, so single-call behavior is unchanged.
#
# The ContextVar objects are module-level so ClaudeRunner and
# OpenAICompatRunner (which imports them below) share the exact same
# isolation buffers, and so LLMRouter (llm_router.py) can proxy its own
# last_tool_calls/last_thinking_blocks properties to the SAME per-call state
# instead of scanning its registered backends for "whichever has a
# non-empty list" (the old LLMRouter property — that scan could return a
# totally different caller's tool calls than the one that just ran through
# the router, amplifying the same race).
_current_tool_calls: "contextvars.ContextVar[Optional[list]]" = contextvars.ContextVar(
    "hiris_current_tool_calls", default=None
)
_current_thinking_blocks: "contextvars.ContextVar[Optional[list]]" = contextvars.ContextVar(
    "hiris_current_thinking_blocks", default=None
)
# Per-request pseudonymization token map (review B/#7 — PII cross-leak fix).
# Same ContextVar-per-Task isolation rationale as the two ContextVars above:
# chat()/chat_stream() reset this dict to {} at the start of every call, the
# recall_memory tool path (dispatcher.dispatch -> memory_tools) records
# token->value pairs into it as it pseudonymizes sensitive content for THIS
# exchange, and the caller (handlers_chat.py / server.py) reads it back
# AFTER chat()/chat_stream() returns (same Task, so the ContextVar value is
# still visible) to detokenize the model's reply using ONLY this exchange's
# own tokens — never falling back to the shared, unscoped vault.
_current_pseudonym_map: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar(
    "hiris_current_pseudonym_map", default=None
)


class _PerCallList:
    """Descriptor for a list attribute backed by a contextvars.ContextVar.

    `obj.attr` reads the current Task's buffer (or `[]` if never set in this
    Task); `obj.attr = value` sets it for the current Task only. See the
    module comment above for the full isolation rationale.
    """

    def __init__(self, var: "contextvars.ContextVar[Optional[list]]") -> None:
        self._var = var

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # `is not None`, NOT `or []` -- the reset step (chat() does
        # `self.last_tool_calls = []` before any appends) legitimately sets
        # the ContextVar to an empty-but-real list. `val or []` would treat
        # that falsy `[]` as "unset" and hand back a throwaway literal `[]`
        # on every read instead of the stored list, silently discarding every
        # subsequent `.append()` (they'd mutate a list nobody keeps a
        # reference to). Only a genuine `None` (never set in this Task) falls
        # back to a fresh empty list.
        val = self._var.get()
        return val if val is not None else []

    def __set__(self, obj, value) -> None:
        self._var.set(value)


class _PerCallDict:
    """Same per-Task ContextVar-backed isolation as ``_PerCallList``, but for
    a dict attribute (used by ``last_pseudonym_map`` — review B/#7)."""

    def __init__(self, var: "contextvars.ContextVar[Optional[dict]]") -> None:
        self._var = var

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        val = self._var.get()
        return val if val is not None else {}

    def __set__(self, obj, value) -> None:
        self._var.set(value)


class ClaudeRunner:
    # Per-call, per-asyncio-Task isolated — NOT shared mutable instance state,
    # even though this object is a long-lived singleton (see comment above).
    last_tool_calls = _PerCallList(_current_tool_calls)
    last_thinking_blocks = _PerCallList(_current_thinking_blocks)
    last_pseudonym_map = _PerCallDict(_current_pseudonym_map)

    def __init__(
        self,
        api_key: str,
        dispatcher: Any = None,
        usage_path: str = "",
        default_model: str = "",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        # fetta E2 Task 7: nessun chiamante costruisce piu' un ToolDispatcher
        # (uscito -- 818 righe, 16 dipendenze, un semaforo spento). Questo e'
        # il dispatcher "di scorta" usato SOLO da chat()/run_with_actions()
        # quando il chiamante non passa il suo (il parametro dispatcher/
        # strumenti per-chiamata, che invece resta: la chat ci passa
        # DispatcherConoscenza). Resta None per costruzione: gli strumenti
        # che lo richiedono (EVALUATION_ONLY_TOOLS, unico catalogo rimasto
        # della Sentinella) degradano a "non disponibile" invece di
        # attuare -- vedi has_memory/il ramo `dispatcher is None` sotto.
        self._dispatcher = dispatcher
        self._usage_path = usage_path
        self._default_model = default_model  # SP-2 T5C: user-chosen default for "auto"
        self._is_cloud = True  # Anthropic cloud — always pseudonymize sensitive content
        # last_tool_calls / last_thinking_blocks are intentionally NOT
        # initialized here — they are per-call/per-Task class-level
        # descriptors (see above); chat() resets them at the start of every
        # call, scoped to the calling Task.
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._per_chatbot_usage: dict[str, dict] = {}
        # Serialize tmp-write + os.replace across concurrent _save_usage() calls.
        # _save_usage runs on every API response and is reachable from multiple
        # concurrent agent runs / chats; without this two writers race on the
        # same .tmp path and can corrupt usage.json (chatbot_engine._save already
        # guards its own save the same way).
        self._save_lock = threading.Lock()
        self._load_usage()

    def set_task_engine(self, engine: Any) -> None:
        # fetta E2 Task 7: nessun chiamante di produzione lo invoca piu' (il
        # cablaggio era in server.py, uscito con ToolDispatcher) -- resta per
        # chi costruisce il runner senza dispatcher e lo chiama comunque.
        if self._dispatcher is not None:
            self._dispatcher.set_task_engine(engine)

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
            self._per_chatbot_usage = data.get("per_agent", {})
        except Exception as exc:
            logger.warning("Failed to load usage from %s: %s", self._usage_path, exc)

    def _save_usage(self) -> None:
        if not self._usage_path:
            return
        data = {
            "schema_version": 1,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_requests": self.total_requests,
            "last_reset": self.usage_last_reset,
            "total_cost_usd": self.total_cost_usd,
            "total_rate_limit_errors": self.total_rate_limit_errors,
            "per_agent": dict(self._per_chatbot_usage),
        }
        tmp = self._usage_path + ".tmp"

        def _write() -> None:
            with self._save_lock:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    os.replace(tmp, self._usage_path)
                except Exception as exc:
                    logger.error("Failed to save usage to %s: %s", self._usage_path, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _write)
        except RuntimeError:
            _write()

    def reset_usage(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.total_cost_usd = 0.0
        self.total_rate_limit_errors = 0
        self.usage_last_reset = datetime.now(timezone.utc).isoformat()
        self._save_usage()

    def _ensure_today_reset(self, pau: dict) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if pau.get("tokens_today_date", "") != today:
            pau["tokens_today"] = 0
            pau["tokens_today_date"] = today

    def get_chatbot_usage(self, chatbot_id: str) -> dict:
        """Return usage stats for a specific agent. Returns zero-filled dict if not found."""
        pau = self._per_chatbot_usage.get(chatbot_id)
        if pau is None:
            return {
                "input_tokens": 0, "output_tokens": 0,
                "requests": 0, "cost_usd": 0.0, "last_run": None,
                "tokens_today": 0, "tokens_today_date": "",
            }
        self._ensure_today_reset(pau)
        return dict(pau)

    def reset_chatbot_usage(self, chatbot_id: str) -> None:
        """Reset usage counters for a specific agent."""
        self._per_chatbot_usage[chatbot_id] = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        self._save_usage()

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        """Single API call with no tools and no retry loop — for classification tasks."""
        kwargs: dict = {"model": MODEL, "max_tokens": 1024, "messages": messages}
        if system:
            kwargs["system"] = system
        try:
            response = await self._client.messages.create(**kwargs)
            return next((b.text for b in response.content if b.type == "text"), "")
        except Exception as exc:
            logger.error("simple_chat failed: %s", exc)
            return ""

    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        chatbot_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        knowledge_allow_sensitive: bool = False,
        knowledge_kinds: list[str] | str | None = None,
        user_id: str | None = None,
        strumenti: list[dict] | None = None,
        dispatcher: Any | None = None,
    ) -> str:
        if chatbot_id:
            if chatbot_id not in self._per_chatbot_usage:
                self._per_chatbot_usage[chatbot_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                    "tokens_today": 0, "tokens_today_date": "",
                }
            self._per_chatbot_usage[chatbot_id]["requests"] += 1
            self._per_chatbot_usage[chatbot_id]["last_run"] = datetime.now(timezone.utc).isoformat()
        self.last_tool_calls = []
        # Fresh per-exchange pseudonymization map (review B/#7) — populated by
        # the recall_memory tool path below, read by the caller afterwards.
        self.last_pseudonym_map = {}
        # ── System prompt blocks with prompt caching ─────────────────────────
        # Anthropic prompt caching is *cumulative*: a single cache_control
        # breakpoint caches everything from the start of the request up to that
        # point. So all stable per-agent content (BASE, agent prompt, behaviour
        # modifiers) is emitted WITHOUT individual breakpoints, and ONE
        # breakpoint on the last stable block captures them all. The volatile,
        # query-dependent context_str is appended after it, uncached.
        #
        # This keeps the request within Anthropic's hard cap of 4 cache_control
        # breakpoints. Previously BASE, the agent prompt and the last modifier
        # each carried their own breakpoint (3); together with the tool-defs
        # breakpoint and the conversation-history breakpoint that reached 5 on
        # follow-up turns, and the API rejected the request with a 400
        # (regression introduced in v0.9.5, surfaced to the user as a generic
        # "Errore temporaneo del servizio AI" on the 2nd message of a chat).
        system_blocks: list[dict] = [{"type": "text", "text": BASE_SYSTEM_PROMPT}]
        if system_prompt:
            system_blocks.append({"type": "text", "text": system_prompt})
        # Behaviour modifiers — stable per agent config, must precede context_str.
        if restrict_to_home:
            system_blocks.append({"type": "text", "text": RESTRICT_PROMPT})
        # Review finale fetta E2, I-5: l'iniezione di REQUIRE_CONFIRMATION_PROMPT
        # e' uscita -- vedi il commento sopra `CONFIRMATION_COVERED_TOOLS`
        # (rimossa insieme). `require_confirmation` non ha piu' alcun effetto
        # sul system prompt.
        if response_mode == "compact":
            system_blocks.append({"type": "text", "text": "Rispondi in modo conciso, massimo 2-3 frasi."})
        elif response_mode == "minimal":
            system_blocks.append({"type": "text", "text": (
                "Rispondi SOLO in formato chiave: valore, una riga per dato. "
                "Esempio:\nStato: acceso\nTemperatura: 21°C"
            )})
        # Single cumulative cache breakpoint on the last stable block (captures
        # BASE + agent prompt + modifiers), placed before the volatile context_str.
        system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}
        if context_str:
            system_blocks.append({"type": "text", "text": context_str})
        effective_model = resolve_model(model, agent_type, self._default_model)
        if strumenti is not None:
            # Il catalogo arriva gia' deciso dal chiamante (es. i quattro
            # strumenti di DispatcherConoscenza, casa/strumenti.py): i quattro
            # filtri in cascata sotto esistono per restringere EVALUATION_TOOL_DEFS,
            # il catalogo della Sentinella -- applicarli anche qui sarebbe una
            # seconda regola nascosta sopra una decisione gia' presa altrove
            # (Task 2, .superpowers/sdd/task-2-brief.md).
            tools = list(strumenti)
        else:
            tools = [t for t in EVALUATION_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
            # render_template valuta un template Jinja: non ha un entity_id da
            # filtrare, quindi legge TUTTA la casa per costruzione. Concederlo resta
            # possibile, ma solo esplicitamente -- e' la casella del Designer, che
            # avvisa chi la spunta. Senza whitelist esplicita di tool il bot
            # riceverebbe l'intero catalogo, e un bot con perimetro di entita' si
            # ritroverebbe in mano proprio lo strumento che quel perimetro lo
            # scavalca ({{ states('lock.portone') }}) senza che nessuno gliel'abbia
            # concesso -- ed e' la configurazione piu' comune. Chi NON ha perimetro
            # vede gia' tutto: togliergli il tool sarebbe una regressione inutile.
            if not allowed_tools and allowed_entities is not None:
                tools = [t for t in tools if t["name"] != "render_template"]
            if allowed_endpoints is None:
                tools = [t for t in tools if t["name"] != "http_request"]
            # Senza dispatcher (fetta E2 Task 7: nessuno ne costruisce piu' uno
            # di produzione) non c'e' memoria da interrogare -- stessa
            # degradazione di un dispatcher che dichiara has_memory=False.
            if self._dispatcher is None or not self._dispatcher.has_memory:
                tools = [t for t in tools if t["name"] not in ("recall_memory", "save_memory")]
        # Cache tool definitions — stable per agent config, reused across turns
        if tools:
            tools = tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral"}}]
        hist = list(conversation_history or [])
        messages: list[dict] = []
        if hist:
            for msg in hist[:-1]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            last = hist[-1]
            content = last["content"]
            if isinstance(content, str):
                cached_content = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
            elif isinstance(content, list) and content:
                # Preserve structured blocks; attach cache_control to the last block only
                cached_content = content[:-1] + [{**content[-1], "cache_control": {"type": "ephemeral"}}]
            else:
                cached_content = content  # empty list or unexpected type: skip caching
            messages.append({"role": last["role"], "content": cached_content})
        messages.append({"role": "user", "content": user_message})
        self.total_requests += 1  # one per user exchange, regardless of tool iterations

        thinking_param = _build_thinking_param(thinking_budget, effective_model, max_tokens)
        # Collect thinking blocks across all tool-use iterations for downstream
        # surfacing in the execution log / chat debug panel.
        self.last_thinking_blocks = []

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                _api_kwargs: dict = {
                    "model": effective_model,
                    "max_tokens": max_tokens,
                    "system": system_blocks,
                    "tools": tools,
                    "messages": messages,
                }
                if thinking_param is not None:
                    _api_kwargs["thinking"] = thinking_param
                response = await self._call_api(**_api_kwargs)
            except anthropic.APIError as exc:
                logger.error("Claude API error: %s", exc)
                raise RunnerBackendError(
                    "Errore temporaneo del servizio AI. Riprova tra poco."
                ) from exc

            for block in response.content:
                if getattr(block, "type", None) == "thinking":
                    self.last_thinking_blocks.append(getattr(block, "thinking", ""))

            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            self.total_input_tokens += inp + cache_creation + cache_read
            self.total_output_tokens += out
            prices = _PRICING.get(effective_model, _PRICING["_default"])
            cost = (
                inp * prices["input"]
                + cache_creation * prices.get("cache_write", prices["input"] * 1.25)
                + cache_read * prices.get("cache_read", prices["input"] * 0.1)
                + out * prices["output"]
            ) / 1_000_000
            self.total_cost_usd += cost
            if chatbot_id and chatbot_id in self._per_chatbot_usage:
                pau = self._per_chatbot_usage[chatbot_id]
                pau["input_tokens"] += inp + cache_creation + cache_read
                pau["output_tokens"] += out
                pau["cost_usd"] += cost
                self._ensure_today_reset(pau)
                pau["tokens_today"] = pau.get("tokens_today", 0) + inp + cache_creation + cache_read + out
            self._save_usage()

            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        if dispatcher is not None:
                            # DispatcherConoscenza (e affini) espone la stessa
                            # interfaccia minima -- dispatch(nome, argomenti) --
                            # non le kwargs pensate per il dispatcher di scorta
                            # sotto: si chiama posizionale.
                            result = await dispatcher.dispatch(block.name, block.input)
                        elif self._dispatcher is not None:
                            result = await self._dispatcher.dispatch(
                                block.name, block.input,
                                allowed_entities=allowed_entities,
                                allowed_services=allowed_services,
                                allowed_endpoints=allowed_endpoints,
                                chatbot_id=chatbot_id,
                                visible_entity_ids=visible_entity_ids,
                                knowledge_allow_sensitive=knowledge_allow_sensitive,
                                knowledge_kinds=knowledge_kinds,
                                cloud=self._is_cloud,
                                user_id=user_id,
                                pseudonym_map=self.last_pseudonym_map,
                            )
                        else:
                            # fetta E2 Task 7: ne' un dispatcher per-chiamata
                            # ne' un ToolDispatcher di scorta -- lo strumento
                            # non e' eseguibile. Mai sollevare qui: un
                            # dizionario leggibile dal modello, come ogni
                            # altro dispatch() di questo ramo.
                            # Minor #7 review finale: questo degrado e'
                            # dichiarato al modello ma prima non lasciava
                            # traccia in log -- una ronda della Sentinella che
                            # gira a vuoto (ogni suo tool degrada qui per
                            # costruzione, self._dispatcher e' sempre None in
                            # produzione) era invisibile all'operatore.
                            logger.debug(
                                "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                                "(degradazione dichiarata, non un errore)", block.name)
                            result = {"error": f"Strumento '{block.name}' non disponibile."}
                        self.last_tool_calls.append({"tool": block.name, "input": block.input})
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})
                _compress_old_tool_results(messages)
            elif response.stop_reason == "max_tokens":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return _max_tokens_message(text_blocks)
            else:
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks) if text_blocks else f"Stopped: {response.stop_reason}"

        return "Max tool iterations reached."

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        chatbot_id: Optional[str] = None,
        visible_entity_ids=None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        knowledge_allow_sensitive: bool = False,
        knowledge_kinds: list[str] | str | None = None,
        user_id: str | None = None,
        strumenti: list[dict] | None = None,
        dispatcher: Any | None = None,
    ):
        """Async generator yielding SSE-formatted lines for the chat response.

        Phase 1 implementation: awaits the full chat() response, then slices it
        into 80-char chunks for SSE framing. The client sees all tokens arrive
        after the full Claude round-trip (same latency as non-streaming).
        Phase 2 will replace this with true Anthropic streaming API calls.

        Yields lines in the form:
          'data: {"type": "token", "text": "<chunk>"}\\n\\n'
          'data: {"type": "done", "agent_id": "<id>", "tool_calls": [...]}\\n\\n'
          'data: {"type": "error", "message": "<msg>"}\\n\\n'

        `strumenti`/`dispatcher` (Task 3 of the nucleo-alla-chat slice):
        forwarded to `self.chat()` unchanged -- since this generator is
        already just a thin wrapper around it (see Phase 1 above), accepting
        the two here and passing them through is enough to keep the SSE path
        (Lovelace card) and the non-streaming path (chat page) offering the
        SAME tools/context, instead of the card silently keeping the old
        34-tool catalog while the page switched to the four that know the
        house.
        """
        import json as _json
        try:
            result = await self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
                context_str=context_str,
                allowed_tools=allowed_tools,
                conversation_history=conversation_history,
                allowed_entities=allowed_entities,
                allowed_services=allowed_services,
                allowed_endpoints=allowed_endpoints,
                model=model,
                max_tokens=max_tokens,
                agent_type=agent_type,
                restrict_to_home=restrict_to_home,
                require_confirmation=require_confirmation,
                chatbot_id=chatbot_id,
                visible_entity_ids=visible_entity_ids,
                response_mode=response_mode,
                thinking_budget=thinking_budget,
                knowledge_allow_sensitive=knowledge_allow_sensitive,
                knowledge_kinds=knowledge_kinds,
                user_id=user_id,
                strumenti=strumenti,
                dispatcher=dispatcher,
            )
        except Exception as exc:
            yield f'data: {_json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f'data: {_json.dumps({"type": "token", "text": result[i:i + chunk_size]})}\n\n'

        tool_calls = self.last_tool_calls if isinstance(self.last_tool_calls, list) else []
        yield f'data: {_json.dumps({"type": "done", "agent_id": chatbot_id, "tool_calls": tool_calls})}\n\n'

    async def run_with_actions(
        self,
        user_message: str,
        system_prompt: str,
        allowed_tools: Optional[list[str]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "agent",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        chatbot_id: Optional[str] = None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        knowledge_allow_sensitive: bool = False,
        knowledge_kinds: list[str] | str | None = None,
        user_id: str | None = None,
    ) -> tuple[str, dict]:
        """Run a tool-restricted evaluation pass — used solely by the Sentinella.

        Slice 5 retired the action/rules execution machinery (AZIONI blocks,
        configured rules): this is now a plain agentic loop that runs the given
        system prompt restricted to read-only (``EVALUATION_ONLY_TOOLS``) tools
        and returns the model's raw text, unmodified. The Sentinella reasoner
        (``watcher/reasoner.py``) parses its own ```json``` block out of the
        returned text; it does not depend on the ``structured`` dict.

        Args:
            user_message: Trigger message (may contain event context or a cron prompt).
            system_prompt: Caller-provided instructions (not augmented here).
            allowed_tools: Whitelist of tool names, or None for all evaluation tools.
            allowed_entities: Entity glob patterns allowed for this agent.
            allowed_services: Service patterns allowed for this agent.
            allowed_endpoints: HTTP endpoint whitelist.
            model: Model ID or ``"auto"``.
            max_tokens: Response token budget.
            agent_type: Used for model auto-resolution (``"agent"`` maps to Haiku).
            restrict_to_home: Inject home-topic restriction prompt.
            require_confirmation: Not used for agents; present for API symmetry.
            chatbot_id: Chatbot ID for per-chatbot usage tracking.
            response_mode: ``"minimal"`` for terse motivazione, ``"auto"`` for standard.

        Returns:
            Tuple of ``(clean_text, structured)``. Nothing instructs the model
            to emit a VALUTAZIONE/NOTIFICA/PARAM/AZIONI block anymore, so
            ``structured`` is always the all-defaults (None/empty) shape kept
            for backward-compat callers, and ``clean_text`` is the model's raw
            text unmodified (Slice 5 Task 2 dropped the dead
            ``_parse_structured_output`` scanning pass — the Sentinella
            reasoner parses its own ```json``` block out of ``clean_text``
            directly, never touching ``structured``).
        """
        # Restrict to evaluation-only tools — Claude may read HA state but
        # cannot directly call action services (prevents prompt-injection attacks).
        eval_tools = list(EVALUATION_ONLY_TOOLS)
        if allowed_tools:
            eval_tools = [t for t in eval_tools if t in allowed_tools]

        raw_result = await self.chat(
            user_message=user_message,
            system_prompt=system_prompt,
            allowed_tools=eval_tools,
            allowed_entities=allowed_entities,
            allowed_services=allowed_services,
            allowed_endpoints=allowed_endpoints,
            model=model,
            max_tokens=max_tokens,
            agent_type=agent_type,
            restrict_to_home=restrict_to_home,
            require_confirmation=require_confirmation,
            chatbot_id=chatbot_id,
            response_mode=response_mode,
            thinking_budget=thinking_budget,
            knowledge_allow_sensitive=knowledge_allow_sensitive,
            knowledge_kinds=knowledge_kinds,
            user_id=user_id,
        )
        # Slice 5 Task 2: dropped the _parse_structured_output scanning pass —
        # nothing emits VALUTAZIONE/NOTIFICA/PARAM/AZIONI markers anymore, so
        # it always returned clean_text == raw_result (mod trailing
        # whitespace) and an all-defaults structured dict. Return that same
        # shape directly instead of paying for a 40-line bottom-up scan on
        # every Sentinella evaluation.
        clean_text = raw_result.rstrip() if isinstance(raw_result, str) else raw_result
        structured = {"valutazione": None, "notifica": None, "params": {}, "azioni": []}
        return clean_text, structured

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

