import asyncio
import contextvars
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional
import anthropic
# fetta E3 Task 8 ("esce l'ultimo catalogo"): la E2 aveva lasciato vive le 18
# definizioni sotto (`EVALUATION_ONLY_TOOLS`/`EVALUATION_TOOL_DEFS`) perche'
# erano l'unico catalogo che la Sentinella usava, via `run_with_actions` --
# dichiarato per iscritto: "escono con lei". La Sentinella e' uscita al Task
# 7 di questa fetta: `run_with_actions` non aveva piu' un solo chiamante, e i
# 12 moduli di `tools/` (da cui venivano importate queste definizioni)
# sopravvivevano solo per donargliele. Cataloghi, `run_with_actions` e
# `tools/` escono qui insieme -- la chat riceve il suo catalogo da fuori
# (`strumenti=STRUMENTI_CONOSCENZA`, casa/strumenti.py, quattro strumenti che
# conoscono la casa e non la toccano) da prima di questo task.

logger = logging.getLogger(__name__)


class RunnerBackendError(Exception):
    """Raised by a runner's chat() when the underlying
    provider API call itself failed (rate limit, connection error, timeout,
    auth failure, 5xx, or any other persistent outage) — as opposed to the
    model producing a normal (if unusual) reply.

    Review C/#13: ClaudeRunner/OpenAICompatRunner used to CATCH these errors
    and RETURN a friendly Italian string, indistinguishable from a real
    successful reply to any caller. LLMRouter's ordered-backend fallback loop
    wraps chat() in `except Exception` specifically to
    fail over to the next configured backend on a primary outage — but a
    returned string never raises, so the loop always "succeeded" on the
    first (broken) backend and the fallback chain was dead code.

    `friendly_message` carries the exact user-facing string the runner used
    to return directly. LLMRouter catches this exception to try the next
    backend, and once every backend in the chain has failed, surfaces the
    LAST failure's `friendly_message` to the end user — the router becomes
    the single place that produces the user-facing degradation. Callers that
    bypass the router (e.g. handlers_chat.handle_chat when an agent pins an
    explicit non-"auto" model) catch it directly at their own call site to
    preserve their pre-existing graceful-degradation behavior instead of
    crashing. (ChatbotEngine._run_chatbot used to be the other such caller —
    it's gone, fetta E4 Task 2: the manual "Test Run" it backed was dead by
    construction, see task-2-report.md.)
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
# Review finale fetta E3, Important #1: la versione precedente dichiarava al
# modello «strumenti per leggere stati, controllare dispositivi, inviare
# notifiche, gestire automazioni, calendario, task» e ordinava di chiamare
# `save_memory` -- uno strumento che non esiste piu' (il catalogo di oggi e'
# SOLO cerca/guarda/ricorda/richiama, casa/strumenti.py). Un prompt che
# ordina di chiamare uno strumento inesistente riapre dal lato del prompt
# esattamente il bug per cui `ricorda` e' nato (vedi il docstring in cima a
# casa/strumenti.py): il modello puo' rispondere "preso nota" senza aver
# salvato, perche' la chiamata che gli abbiamo insegnato a fare fallisce in
# silenzio. Riscritta perche' descriva cio' che HIRIS e' oggi: conosce la
# casa e la memoria, risponde, non attua.
BASE_SYSTEM_PROMPT = (
    "Sei HIRIS, assistente AI integrata in Home Assistant: conosci la casa"
    " (aree, entità, dispositivi, automazioni e script) e la memoria di ciò"
    " che le persone ti hanno detto.\n"
    "Hai a disposizione strumenti per cercare e guardare il dettaglio di una"
    " cosa della casa, e per salvare e richiamare ciò che ti viene detto — non"
    " controlli dispositivi, non invii notifiche, non gestisci automazioni o"
    " task: rispondi, non agisci.\n\n"
    "## Regole fondamentali\n"
    "- Usa SEMPRE gli strumenti per dati sulla casa — non inventare stati, valori o entità.\n"
    "- Non dichiarare azioni mai eseguite: se non hai chiamato il tool, non dire di averlo fatto.\n"
    "- Se hai chiamato uno strumento con successo, l'azione è reale:\n"
    "  non aggiungere disclaimers come 'ho inventato', 'ho simulato' o 'non ho realmente eseguito'.\n"
    "- Quando l'utente dichiara qualcosa di duraturo su di sé, sulla casa o su come vuole le cose —"
    " una preferenza, un vincolo, un guasto, una regola operativa — chiama ricorda subito, senza"
    " chiedere il permesso: basta l'affermazione, non serve che dica 'ricordati che'. Non salvare lo"
    " stato di adesso né una richiesta una tantum, né ciò che puoi rileggere da Home Assistant quando"
    " serve.\n"
    "- 'Preso nota' senza aver chiamato ricorda è la stessa azione mai eseguita vietata sopra:"
    " non dirlo se non hai salvato.\n"
    "- Rispondi nella lingua dell'utente."
)

# fetta E3 Task 8: `EVALUATION_TOOL_DEFS` (ex `ALL_TOOL_DEFS`, il catalogo da
# 34) e `EVALUATION_ONLY_TOOLS` (le 18 letture concesse alla Sentinella) sono
# uscite insieme a `run_with_actions`, il loro unico chiamante -- vedi il
# commento in testa al file. La chat non ha mai smesso di ricevere il suo
# catalogo dall'esterno (`strumenti=STRUMENTI_CONOSCENZA`); ora e' l'UNICO
# modo in cui `chat()` vede dei tool, non piu' il ramo di scorta.

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
# una promessa vuota. fetta E4 Task 6 ("un bot solo"): il parametro
# `require_confirmation` stesso e' uscito da `chat()`/`chat_stream()` -- il
# `Chatbot` di cui era un campo di configurazione era gia' uscito al Task 4.


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
# Tasks calling chat()/chat_stream() on the very same runner instance
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
        usage_path: str = "",
        default_model: str = "",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
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
        # Serialize tmp-write + os.replace across concurrent _save_usage() calls.
        # _save_usage runs on every API response and is reachable from multiple
        # concurrent agent runs / chats; without this two writers race on the
        # same .tmp path and can corrupt usage.json (ImpostazioniChat.salva,
        # impostazioni_chat.py, guards its own save the same way).
        self._save_lock = threading.Lock()
        self._load_usage()

    # fetta E4 Task 6 ("un bot solo"): il costruttore perdeva un `dispatcher`
    # "di scorta" -- usato SOLO dal ramo `elif self._dispatcher is not None`
    # dentro `chat()`, uscito con lui in questo stesso task. Nessun chiamante
    # di produzione lo passava mai (fetta E2 Task 7, commit 68d3670: la chat
    # passa SEMPRE il proprio DispatcherConoscenza per-chiamata, il parametro
    # `dispatcher`/`strumenti` che invece resta -- vedi `chat()` sotto). Un
    # tool richiesto senza un dispatcher per-chiamata degrada comunque a "non
    # disponibile", come faceva gia' prima con `self._dispatcher` sempre
    # `None` per costruzione: nessun comportamento osservabile cambia.
    #
    # fetta E3 Task 8: `set_task_engine` era gia' uscito per lo stesso motivo
    # (zero chiamanti di produzione, inoltrava a un metodo che nessun
    # dispatcher di produzione ha mai avuto).

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
            # fetta E4 Task 6 ("un bot solo"): la contabilita' per-chatbot
            # (`per_agent`, get_chatbot_usage/reset_chatbot_usage) esce -- zero
            # lettori di produzione dal Task 3 (rotte usage uscite) e dal
            # Task 4 (ChatbotEngine uscito). Un usage.json scritto da una
            # versione precedente non viene ne' migrato ne' cancellato (mai
            # dati utente rimossi silenziosamente): se la chiave e' presente e
            # non vuota lo dichiariamo in log invece di ignorarla muti --
            # stessa disciplina di tests/test_startup_legacy_db_silence.py.
            # Non piu' letta in `self`: da qui in poi il valore non alimenta
            # piu' nessuno stato del runner. fix round 1 (Important 2 della
            # review indipendente): "non piu' scritta" NON significa "sparisce
            # al prossimo save" -- `_save_usage()` fa lettura-modifica-
            # scrittura e la riporta avanti intatta (vedi sotto), cosi' il
            # commento qui sopra ("mai rimossi silenziosamente") e' vero anche
            # dopo il primo salvataggio, non solo al momento del load.
            _per_agent_legacy = data.get("per_agent")
            if _per_agent_legacy:
                logger.info(
                    "usage.json contiene 'per_agent' (%d voci) di un'installazione "
                    "precedente -- non piu' letto ne' scritto da questa versione.",
                    len(_per_agent_legacy),
                )
        except Exception as exc:
            logger.warning("Failed to load usage from %s: %s", self._usage_path, exc)

    def _save_usage(self) -> None:
        if not self._usage_path:
            return
        tmp = self._usage_path + ".tmp"

        def _write() -> None:
            with self._save_lock:
                try:
                    # fix round 1 (Important 2 della review indipendente):
                    # lettura-modifica-scrittura invece di ricostruire `data`
                    # da zero. La vecchia versione scriveva SOLO le chiavi che
                    # questo runner conosce, quindi il PRIMO salvataggio dopo
                    # un upgrade cancellava silenziosamente `per_agent` di
                    # un'installazione precedente -- il contrario esatto di
                    # quanto dichiarato dal commento in `_load_usage` ("mai
                    # rimossi silenziosamente") e dal log li' sopra ("non piu'
                    # letto ne' scritto", che un operatore legge come "e'
                    # ancora li'"). Ora si legge il file esistente (se c'e'),
                    # si aggiornano SOLO i campi che questo runner possiede, e
                    # si riscrive tutto il resto (`per_agent` incluso) cosi'
                    # com'era -- nessuna chiave sconosciuta viene mai persa.
                    disk_data: dict = {}
                    if os.path.exists(self._usage_path):
                        try:
                            with open(self._usage_path, encoding="utf-8") as f:
                                disk_data = json.load(f)
                        except Exception as exc:
                            logger.warning(
                                "usage.json illeggibile prima del save, si riparte da zero "
                                "(chiavi sconosciute di un file corrotto non recuperabili): %s",
                                exc,
                            )
                            disk_data = {}
                    disk_data.update({
                        "schema_version": 1,
                        "total_input_tokens": self.total_input_tokens,
                        "total_output_tokens": self.total_output_tokens,
                        "total_requests": self.total_requests,
                        "last_reset": self.usage_last_reset,
                        "total_cost_usd": self.total_cost_usd,
                        "total_rate_limit_errors": self.total_rate_limit_errors,
                    })
                    os.makedirs(os.path.dirname(os.path.abspath(tmp)), exist_ok=True)
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(disk_data, f, indent=2)
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

    # fetta E4 Task 6 ("un bot solo"): `_ensure_today_reset`/`get_chatbot_usage`/
    # `reset_chatbot_usage` sono usciti -- zero lettori di produzione (le
    # rotte usage sono uscite al Task 3, ChatbotEngine al Task 4, MQTT in E3;
    # LLMRouter aveva gli stessi due metodi SOLO per aggregarli su piu'
    # runner, usciti con loro). Vedi il commento sul costruttore per la
    # storia completa.

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
        conversation_history: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        strumenti: list[dict] | None = None,
        dispatcher: Any | None = None,
    ) -> str:
        self.last_tool_calls = []
        # Fresh per-exchange pseudonymization map (review B/#7), read by the
        # caller afterwards (handlers_chat.py, pseudonymizer.detokenize).
        # fix round 1 (Important 3 della review indipendente): this used to
        # say "populated by the recall_memory tool path below" -- false since
        # fetta E2 Task 7 ("esce il dispatcher"), and doubly so after this
        # task's own removal of the scorta branch. No path in THIS file
        # writes into it any more: the only writer used to be the removed
        # `elif self._dispatcher is not None` branch, which alone passed
        # `pseudonym_map=self.last_pseudonym_map` to `dispatch()`. The
        # surviving per-call `dispatcher` path calls `dispatch(nome,
        # argomenti)` positional-only (DispatcherConoscenza's minimal
        # interface, casa/strumenti.py — see the dispatch loop below), with
        # no `pseudonym_map` kwarg at all. So today this dict is always reset
        # to `{}` and never filled: the two `pseudonymizer.detokenize(text,
        # pseudonym_map)` calls in handlers_chat.py are currently no-ops
        # (nothing to expand). Pre-existing since fetta E2 Task 7 — NOT a
        # regression of this task — left as-is per this fix round's scope
        # (not repairing, only correcting the comment that hid it); flagged
        # here for the fetta's final review, see task-6-report.md.
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
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito -- vedi il commento sopra `CONFIRMATION_COVERED_
        # TOOLS` (Review finale fetta E2, I-5) per il perche' non aveva gia'
        # piu' alcun effetto sul system prompt da prima di questo task.
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
            # strumenti di DispatcherConoscenza, casa/strumenti.py).
            tools = list(strumenti)
        else:
            # fetta E3 Task 8: non esiste piu' un catalogo di scorta da cui
            # pescare qui. `EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`
            # (il catalogo a 18 letture della Sentinella, filtrato con
            # `allowed_tools`) sono usciti insieme al loro unico chiamante,
            # `run_with_actions` -- la Sentinella e' uscita al Task 7. Nessun
            # chiamante di produzione arriva fin qui senza passare
            # `strumenti` (verificato: api/handlers_chat.py, l'unico
            # chiamante di produzione rimasto dalla fetta E4 Task 4, lo passa
            # sempre); i test del "loop mechanic" che chiamano `chat()` senza
            # `strumenti` provano apposta che la conversazione regge
            # comunque, senza tool_use.
            tools = []
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
                            # interfaccia minima -- dispatch(nome, argomenti).
                            # fetta E4 Task 6: il ramo "dispatcher di scorta"
                            # (self._dispatcher, con le kwargs allowed_entities/
                            # allowed_services/allowed_endpoints/chatbot_id/
                            # visible_entity_ids/knowledge_allow_sensitive/
                            # knowledge_kinds) e' uscito -- zero chiamanti di
                            # produzione lo popolavano (fetta E2 Task 7,
                            # commit 68d3670).
                            result = await dispatcher.dispatch(block.name, block.input)
                        else:
                            # ne' un dispatcher per-chiamata: lo strumento non
                            # e' eseguibile. Mai sollevare qui: un dizionario
                            # leggibile dal modello, come ogni altro dispatch()
                            # di questo ramo.
                            # Minor #7 review finale: questo degrado e'
                            # dichiarato al modello ma prima non lasciava
                            # traccia in log.
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
        conversation_history: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = MAX_TOKENS,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
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
          'data: {"type": "done", "tool_calls": [...]}\\n\\n'
          'data: {"type": "error", "message": "<msg>"}\\n\\n'

        fetta E4 Task 6 ("un bot solo"): il campo `agent_id` del done-event e'
        uscito -- grep su static/ (send.js, hiris-chat-card.js) trova un solo
        lettore del `done` event e legge SOLO `evt.type`, mai `evt.agent_id`;
        la pagina chat (send.js) non usa nemmeno lo streaming. Nessun lettore
        vivo, dichiarato per la E5 (docs/design/2026-08-08-frontend-da-
        rifare.md non lo elenca: non c'era nulla da riparare).

        fetta E4 Task 6, fix round 1 (Important 1 della review indipendente):
        `user_id` e' uscito anche lui da `chat()`/`chat_stream()` -- il suo
        unico lettore era `user_id=user_id` dentro il ramo di scorta
        `elif self._dispatcher is not None` rimosso da questo stesso task
        (era nel commit iniziale insieme agli altri otto kwarg orfani, ma
        sfuggito al primo giro: verificato ora con lo stesso grep dello
        Step 1, zero lettori in produzione).

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
                conversation_history=conversation_history,
                model=model,
                max_tokens=max_tokens,
                agent_type=agent_type,
                restrict_to_home=restrict_to_home,
                response_mode=response_mode,
                thinking_budget=thinking_budget,
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
        yield f'data: {_json.dumps({"type": "done", "tool_calls": tool_calls})}\n\n'

    # fetta E3 Task 8: `run_with_actions` e' uscito. Girava un passaggio
    # agentico ristretto a `EVALUATION_ONLY_TOOLS` (le 18 letture) per conto
    # di UN solo chiamante: `watcher/reasoner.py::_llm_reason`, la Sentinella
    # -- uscita per intero al Task 7 di questa fetta. Senza quel chiamante,
    # `run_with_actions` non aveva piu' nessuno a cui rispondere; usciva
    # insieme ai due cataloghi che esistevano solo per lui
    # (`EVALUATION_TOOL_DEFS`/`EVALUATION_ONLY_TOOLS`, sopra) e alla cartella
    # `tools/` da cui quei cataloghi pescavano le 18 definizioni.

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

