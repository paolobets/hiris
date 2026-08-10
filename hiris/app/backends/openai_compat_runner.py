from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional
import httpx as _httpx

from ..claude_runner import (
    BASE_SYSTEM_PROMPT,
    RESTRICT_PROMPT,
    RunnerBackendError,
    _current_tool_calls,
    _current_pseudonym_map,
    _PerCallList,
    _PerCallDict,
)
from .pricing import PRICING as _PRICING

# Circuit-breaker: after this many consecutive connection-class failures, skip
# the backend for the cooldown instead of hammering a dead endpoint. The
# observed failure mode was a stale Ollama tunnel (DNS no longer resolving)
# flooding the log with "Connection error" once per classify_entities call.
_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SEC = 60


# fetta E4 Task 6 ("un bot solo"): `_estimate_tokens` e' uscita -- il suo
# unico chiamante (`_track_usage`'s per-chatbot estimate branch) e' uscito
# con lei, vedi il commento su `_track_usage` piu' sotto.


def _is_conn_error(exc: Exception) -> bool:
    """True for connection/timeout-class errors (endpoint unreachable), as
    opposed to API/validation errors which should NOT trip the breaker."""
    try:
        import openai
        if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
            return True
    except Exception:
        pass
    return isinstance(exc, (_httpx.ConnectError, _httpx.ConnectTimeout, ConnectionError))

logger = logging.getLogger(__name__)

AUTO_MODEL_MAP: dict[str, str] = {
    "chat":  "gpt-4o",
    "agent": "gpt-4o-mini",
}

MAX_TOOL_ITERATIONS = int(os.environ.get("MAX_TOOL_ITERATIONS", "10"))
# Ollama tende a fare più iterazioni a vuoto; limite ridotto per contenere la latenza.
_OLLAMA_MAX_TOOL_ITERATIONS = int(os.environ.get("OLLAMA_MAX_TOOL_ITERATIONS", "5"))


def _to_openai_tools(tool_defs: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_defs
    ]


# Heuristic: identifier of 3+ chars at the start of content immediately
# followed by a non-ASCII non-whitespace codepoint. Some Mistral/Hermes
# routings on OpenRouter fail to translate the model's native special tool
# tokens (e.g. [TOOL_CALLS], rendered as isolated Hebrew/Vietnamese
# codepoints in UTF-8) into the OpenAI tool_calls schema, so the response
# arrives as plain text content like:
#   get_ha_healthיׂ{"sections":["all"]}
#   await_user_confirmationיׄ**Confermi di...**
# Persisting this verbatim into chat history poisons later turns.
_TOOL_LEAK_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]{2,})[^\x00-\x7F\s]")

TOOL_LEAK_USER_MSG = (
    "Il modello selezionato non gestisce correttamente i tool tramite questo "
    "provider (la chiamata al tool è arrivata come testo invece che come "
    "tool_call). Cambia modello — preferisci quelli con tool use nativo "
    "OpenAI — oppure disattiva i tool dell'agente."
)


def detect_leaked_tool_call(content: str, tool_names) -> Optional[str]:
    """Return the matched tool name if `content` is a leaked tool call, else None.

    The identifier must exactly match one of the runner's currently-available
    tool names so legitimate prose mentioning Latin punctuation/em-dashes does
    not trigger.
    """
    if not content or not tool_names:
        return None
    if not isinstance(tool_names, (set, frozenset)):
        tool_names = frozenset(tool_names)
    m = _TOOL_LEAK_RE.match(content)
    if not m:
        return None
    candidate = m.group(1)
    return candidate if candidate in tool_names else None


# OpenRouter 402 'Payment Required' messages embed the maximum affordable
# completion tokens for the current API-key credit balance, e.g.:
#   "You requested up to 4096 tokens, but can only afford 3907."
# (Note: real messages have no 'tokens' word after the number — just the
# integer followed by a period.) We parse this once and retry the same call
# with a clamped value so a transient credit shortage does not produce an
# opaque "Errore temporaneo".
_AFFORD_RE = re.compile(r"can only afford (\d+)", re.IGNORECASE)


def parse_afford_limit(exc: Any) -> Optional[int]:
    """If `exc` carries an OpenRouter 402 'afford X tokens' message, return X
    reduced by a small safety margin. Returns ``None`` if the message does
    not match — caller falls back to generic error handling.
    """
    msg = getattr(exc, "message", None) or str(exc) or ""
    m = _AFFORD_RE.search(msg)
    if not m:
        return None
    try:
        affordable = int(m.group(1))
    except ValueError:
        return None
    # 5% margin leaves room for tokeniser variation between request and
    # OpenRouter's own counting.
    return max(1, int(affordable * 0.95))


# OpenRouter free-tier rate-limit messages embed the upstream provider error
# verbatim under metadata.raw, e.g.:
#   "qwen/qwen3-next-80b-a3b-instruct:free is temporarily rate-limited upstream.
#    Please retry shortly, or add your own key..."
# We surface this clearer message instead of the opaque "Errore temporaneo".
_UPSTREAM_RATELIMIT_RE = re.compile(
    r"([\w\-./]+:free)\s+is\s+temporarily\s+rate-limited\s+upstream",
    re.IGNORECASE,
)


def parse_upstream_rate_limit(exc: Any) -> Optional[str]:
    """Detect free-tier upstream rate limit and return an actionable Italian
    message. Returns ``None`` if the exception is not this specific case.
    """
    msg = getattr(exc, "message", None) or str(exc) or ""
    m = _UPSTREAM_RATELIMIT_RE.search(msg)
    if not m:
        # Some providers emit the plain phrase without naming the model.
        if "rate-limited upstream" in msg.lower():
            return (
                "Il modello :free selezionato ha esaurito il rate limit "
                "upstream. Riprova tra qualche minuto oppure passa a un "
                "modello a pagamento (o aggiungi una tua API key del provider "
                "su openrouter.ai/settings/integrations)."
            )
        return None
    model_name = m.group(1)
    return (
        f"Il modello {model_name} ha esaurito il rate limit upstream. "
        "Riprova tra qualche minuto oppure passa a un modello a pagamento "
        "(o aggiungi una tua API key del provider su "
        "openrouter.ai/settings/integrations)."
    )


class OpenAICompatRunner:
    """Agentic LLM runner for OpenAI-compatible APIs (OpenAI cloud + Ollama local)."""

    # Per-call, per-asyncio-Task isolated — shares the SAME ContextVar as
    # ClaudeRunner (review A/#3 — see claude_runner.py's module comment for
    # the full rationale). No last_thinking_blocks here: OpenAI-compatible
    # backends don't support Anthropic Extended Thinking (thinking_budget is
    # accepted-and-ignored in chat() below).
    last_tool_calls = _PerCallList(_current_tool_calls)
    # Per-request pseudonymization token map (review B/#7) — same ContextVar
    # shared with ClaudeRunner; see claude_runner.py's module comment.
    last_pseudonym_map = _PerCallDict(_current_pseudonym_map)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        fixed_model: str = "",
        usage_path: str = "",
        default_model: str = "",
    ) -> None:
        if fixed_model:
            from ..backends.ollama import _validate_ollama_url
            _validate_ollama_url(base_url)
        import openai as _openai
        # Ollama su hardware lento: timeout esplicito per evitare hang infiniti.
        # Cloud OpenAI: 600s (rispetta default SDK per risposte lunghe).
        if fixed_model:
            _req_timeout = float(os.environ.get("OLLAMA_REQUEST_TIMEOUT", "120"))
            _client_timeout = _httpx.Timeout(_req_timeout, connect=5.0)
        else:
            _client_timeout = _httpx.Timeout(600.0, connect=5.0)
        # Ollama: disabilita auto-retry SDK. Default openai 2.x = 2 retry, che
        # cumulativamente possono superare il wrapper chatbot_engine 300s
        # producendo "Timeout dopo 300s" generico senza log specifici. Con
        # max_retries=0 il primo APIError/Timeout viene loggato e ritornato.
        # Cloud OpenAI: lascia il default (2) — la rete cloud è meno volatile.
        _max_retries = 0 if fixed_model else 2
        self._client = _openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url,
            timeout=_client_timeout, max_retries=_max_retries,
        )
        # fetta E4 Task 6 ("un bot solo"): il costruttore perdeva un
        # `dispatcher` "di scorta" -- vedi il commento gemello in
        # ClaudeRunner.__init__ per la storia completa (fetta E2 Task 7,
        # commit 68d3670: zero chiamanti di produzione lo popolavano).
        self._default_model = default_model  # SP-2 T5C: user-chosen default for "auto" (unused for Ollama, see fixed_model)
        self._fixed_model = fixed_model   # Ollama: always use this model; empty for OpenAI
        self._is_cloud = not bool(fixed_model)  # True = cloud (OpenAI); False = local (Ollama)
        # Circuit-breaker message noun, so a cloud backend doesn't report
        # itself as "il backend locale" (review backlog #7).
        self._backend_noun = "Il servizio AI" if self._is_cloud else "Il backend locale"
        self._usage_path = usage_path
        self._base_url = base_url
        # Serialize usage.json writes (see ClaudeRunner._save_lock for rationale).
        self._save_lock = threading.Lock()
        # Circuit-breaker state for connection-class failures (dead endpoint).
        self._conn_fail_count = 0
        self._circuit_open_until = 0.0
        # last_tool_calls is intentionally NOT initialized here — it's a
        # per-call/per-Task class-level descriptor (see above); chat() resets
        # it at the start of every call, scoped to the calling Task.
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._load_usage()

    # ------------------------------------------------------------------
    # Usage tracking
    # ------------------------------------------------------------------

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
            # fetta E4 Task 6 ("un bot solo"): stessa mossa di claude_runner.py
            # -- la contabilita' per-chatbot esce, "per_agent" di un
            # usage.json legacy non viene ne' migrata ne' cancellata, solo
            # dichiarata in log se presente e non vuota (silenzio dichiarato,
            # modello tests/test_startup_legacy_db_silence.py). fix round 1
            # (Important 2 della review indipendente): "non piu' scritta" NON
            # significa "sparisce al prossimo save" -- vedi `_save_usage`
            # sotto, che la riporta avanti intatta con una lettura-modifica-
            # scrittura invece di ricostruire il file da zero.
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
                    # lettura-modifica-scrittura -- stessa mossa e stesso
                    # motivo del commento gemello in claude_runner.py (la
                    # vecchia versione cancellava silenziosamente `per_agent`
                    # al primo save dopo un upgrade, il contrario esatto di
                    # quanto dichiarato in `_load_usage`).
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
    # `reset_chatbot_usage` sono usciti -- stessa mossa e stessa storia del
    # commento gemello in claude_runner.py.

    def _track_usage(self, response: Any, model: str) -> None:
        """Aggiorna i contatori GLOBALI (total_input_tokens/total_output_tokens/
        total_cost_usd) e persiste. fetta E4 Task 6: la stima per-chatbot che
        viveva qui (quando `response` non porta `usage`, tipico di OpenRouter/
        Ollama, stimata da `est_input_chars` -- il conteggio caratteri dei
        messaggi inviati) esisteva SOLO per far "mordere" un budget
        per-esecuzione che leggeva `get_chatbot_usage` -- quel lettore e'
        uscito al Task 3 (rotte usage) insieme a `server.py`'s
        `agent_run_usage`, gia' morto prima di questo task (verificato: zero
        occorrenze in produzione). Con lui muore anche lo scopo dell'unico
        chiamante di `_estimate_tokens` (uscita insieme, verificato zero altri
        chiamanti) e il parametro `est_input_chars` (nessun altro lettore):
        senza `usage` non c'e' piu' nulla da stimare o da scrivere, solo da
        dichiarare in log. Anche PRIMA di questo task il ramo "nessun usage"
        non alimentava i contatori globali (solo quelli per-chatbot, ora
        usciti): nessuna regressione sui totali globali.
        """
        usage = getattr(response, "usage", None)
        if not usage:
            logger.debug("Model %s: risposta senza 'usage' -- nessun contatore aggiornato", model)
            return
        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        prices = _PRICING.get(model, _PRICING["_default"])
        cost = (inp * prices["input"] + out * prices["output"]) / 1_000_000
        self.total_input_tokens += inp
        self.total_output_tokens += out
        self.total_cost_usd += cost
        self._save_usage()

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------

    def _resolve_model(self, model: str, agent_type: str) -> str:
        if self._fixed_model:
            return self._fixed_model
        if model == "auto":
            return self._default_model or AUTO_MODEL_MAP.get(agent_type, "gpt-4o-mini")
        return model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _circuit_is_open(self) -> bool:
        return time.monotonic() < self._circuit_open_until

    def _record_conn_failure(self) -> None:
        self._conn_fail_count += 1
        if self._conn_fail_count >= _CIRCUIT_THRESHOLD and not self._circuit_is_open():
            self._circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN_SEC
            logger.warning(
                "Backend %s unreachable (%d consecutive connection failures) — "
                "circuit open for %ds, skipping calls.",
                self._base_url, self._conn_fail_count, _CIRCUIT_COOLDOWN_SEC,
            )

    def _record_success(self) -> None:
        if self._conn_fail_count or self._circuit_open_until:
            self._conn_fail_count = 0
            self._circuit_open_until = 0.0

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
        # Skip the network entirely while the breaker is open — this is what
        # stops a dead backend (e.g. a stale Ollama tunnel) from flooding the
        # log and wasting connect timeouts once per classify_entities call.
        if self._circuit_is_open():
            return ""
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        try:
            kwargs: dict = {
                "model": self._fixed_model or "gpt-4o-mini",
                "messages": msgs,
                "max_tokens": 1024,
            }
            if self._fixed_model:
                kwargs["extra_body"] = {"think": False}
            resp = await self._client.chat.completions.create(**kwargs)
            self._record_success()
            return resp.choices[0].message.content or ""
        except Exception as exc:
            if _is_conn_error(exc):
                self._record_conn_failure()
                # Log the first failures, then go quiet (the open-circuit warning
                # is logged once) so a dead endpoint doesn't flood the log.
                if self._conn_fail_count < _CIRCUIT_THRESHOLD:
                    logger.warning("simple_chat connection error: %s", exc)
            else:
                logger.error("simple_chat failed: %s", exc)
            return ""

    # fetta E4 Task 6, fix round 1 (Important 1 della review indipendente):
    # `user_id` e' uscito da `chat()`/`chat_stream()` -- stessa mossa, stessa
    # storia del commento gemello in claude_runner.py (il suo unico lettore
    # era il ramo di scorta rimosso da questo stesso task, sfuggito al primo
    # giro).
    async def chat(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        strumenti: list[dict] | None = None,
        dispatcher: Any | None = None,
    ) -> str:
        # thinking_budget is part of the runner contract since v0.9.5 because
        # ClaudeRunner uses it for Anthropic Extended Thinking. OpenAI/Ollama/
        # OpenRouter don't surface a comparable per-request budget knob in the
        # OpenAI-compatible spec — Ollama uses `extra_body={"think": False}`
        # for reasoning-default models, applied unconditionally below.
        # The kwarg is accepted to match the LLMRouter common signature; it
        # is intentionally ignored here (no warning: legitimately unused).
        del thinking_budget
        import openai as _openai

        # review M3/#2: the connection-failure circuit breaker used to guard
        # simple_chat() only. The agentic loop below never consulted it, so a
        # dead Ollama endpoint was retried at full timeout every single turn
        # instead of failing fast like simple_chat() already does.
        if self._circuit_is_open():
            raise RunnerBackendError(
                f"{self._backend_noun} non risponde da diversi tentativi "
                "consecutivi (circuito aperto). Riprova tra qualche istante."
            )

        self.last_tool_calls = []
        # Fresh per-exchange pseudonymization map (review B/#7).
        self.last_pseudonym_map = {}
        self.total_requests += 1

        effective_model = self._resolve_model(model, agent_type)

        # Build system message (OpenAI uses a single system message)
        system_parts = [BASE_SYSTEM_PROMPT]
        if system_prompt:
            system_parts.append(system_prompt)
        if context_str:
            system_parts.append(context_str)
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito da `chat()`/`chat_stream()` -- vedi il commento
        # gemello in claude_runner.py per il perche' non aveva gia' piu'
        # alcun effetto sul system prompt da prima di questo task.
        if response_mode == "compact":
            system_parts.append("Rispondi in modo conciso, massimo 2-3 frasi.")
        elif response_mode == "minimal":
            system_parts.append(
                "Rispondi SOLO in formato chiave: valore, una riga per dato. "
                "Esempio:\nStato: acceso\nTemperatura: 21°C"
            )

        messages: list[dict] = [{"role": "system", "content": "\n\n---\n\n".join(system_parts)}]
        for msg in (conversation_history or []):
            messages.append({"role": msg["role"], "content": str(msg["content"])})
        messages.append({"role": "user", "content": user_message})

        # Build tool list
        if strumenti is not None:
            # Il catalogo arriva gia' deciso dal chiamante. Stessa regola di
            # ClaudeRunner.chat() (vedi il suo commento gemello).
            tools = list(strumenti)
        else:
            # fetta E3 Task 8: nessun catalogo di scorta da cui pescare --
            # vedi il commento gemello in claude_runner.chat().
            tools = []
        oai_tools = _to_openai_tools(tools) if tools else None
        tool_name_set = frozenset(t["name"] for t in tools)

        # I modelli locali (Ollama) tendono a inventare nomi di tool non presenti nello schema.
        # Iniettare la lista esplicita nel system prompt riduce fortemente le allucinazioni.
        if self._fixed_model and tools:
            tool_names = ", ".join(t["name"] for t in tools)
            messages[0]["content"] += (
                f"\n\n---\n\nTool disponibili: {tool_names}.\n"
                "NON chiamare tool non presenti in questa lista."
            )

        max_iter = _OLLAMA_MAX_TOOL_ITERATIONS if self._fixed_model else MAX_TOOL_ITERATIONS
        for iter_idx in range(max_iter):
            try:
                kwargs: dict = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                # Ollama-specific: disabilita reasoning/thinking di default per
                # modelli che lo abilitano on-by-default (Gemma 4, Qwen QwQ,
                # DeepSeek R1, ecc.). Questi modelli emettono token "thinking"
                # per molti secondi prima di emettere "content"; in modalita'
                # non-streaming la risposta non arriva mai entro il timeout
                # HTTP e la chiamata HIRIS finisce in timeout 300s senza log
                # specifici. `think: false` e' un parametro non-OpenAI che
                # viene passato via extra_body al body JSON: i modelli senza
                # thinking lo ignorano, quelli con thinking lo disattivano.
                if self._fixed_model:
                    kwargs["extra_body"] = {"think": False}
                if self._fixed_model:
                    msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
                    logger.info(
                        "Ollama call: model=%s iter=%d/%d tools=%d msg_chars=%d",
                        effective_model, iter_idx + 1, max_iter,
                        len(oai_tools or []), msg_chars,
                    )
                response = await self._client.chat.completions.create(**kwargs)
                if self._fixed_model:
                    _content = (response.choices[0].message.content or "") if response.choices else ""
                    logger.info(
                        "Ollama response: finish=%s content_len=%d tools=%d",
                        response.choices[0].finish_reason if response.choices else "?",
                        len(_content),
                        len(response.choices[0].message.tool_calls or []) if response.choices else 0,
                    )
            except _openai.RateLimitError as exc:
                self.total_rate_limit_errors += 1
                logger.error("OpenAI rate limit: %s", exc)
                upstream = parse_upstream_rate_limit(exc)
                raise RunnerBackendError(
                    upstream or "Errore temporaneo del servizio AI. Riprova tra poco."
                ) from exc
            except _openai.APIError as exc:
                # OpenRouter 402: the API key has insufficient credit for the
                # current max_tokens. The error message tells us the highest
                # affordable budget — retry once with that lower value before
                # giving up so a transient credit shortage doesn't kill the
                # turn with an opaque "Errore temporaneo".
                affordable = parse_afford_limit(exc)
                if affordable and affordable < kwargs.get("max_tokens", 0):
                    logger.warning(
                        "OpenRouter 402 on %s: requested max_tokens=%d, "
                        "retrying with %d (key credit limit).",
                        effective_model, kwargs["max_tokens"], affordable,
                    )
                    kwargs["max_tokens"] = affordable
                    try:
                        response = await self._client.chat.completions.create(**kwargs)
                    except _openai.APIError as retry_exc:
                        logger.error(
                            "OpenRouter 402 retry failed: %s", retry_exc,
                        )
                        raise RunnerBackendError(
                            f"Crediti OpenRouter insufficienti per max_tokens={max_tokens}. "
                            f"Riduci max_tokens dell'agente sotto {affordable} "
                            f"oppure aggiungi credito su openrouter.ai."
                        ) from retry_exc
                else:
                    # review M3/#2: connection-class failures (dead endpoint)
                    # must trip the same breaker simple_chat() uses, so a
                    # stale Ollama tunnel fails fast on the NEXT turn instead
                    # of being retried at full timeout forever.
                    if _is_conn_error(exc):
                        self._record_conn_failure()
                    logger.error("OpenAI/Ollama API error: %s", exc)
                    raise RunnerBackendError(
                        "Errore temporaneo del servizio AI. Riprova tra poco."
                    ) from exc

            self._record_success()
            self._track_usage(response, effective_model)
            choice = response.choices[0]

            if choice.finish_reason == "stop":
                raw_content = choice.message.content or ""
                leaked = detect_leaked_tool_call(raw_content, tool_name_set)
                if leaked:
                    logger.warning(
                        "Model %s leaked tool call '%s' as text content "
                        "(provider does not translate native tool tokens). Sample: %r",
                        effective_model, leaked, raw_content[:160],
                    )
                    return TOOL_LEAK_USER_MSG
                return raw_content

            if choice.finish_reason == "tool_calls":
                tool_calls = choice.message.tool_calls or []
                # Reconstruct assistant message cleanly.
                # content is None per OpenAI spec when finish_reason=="tool_calls";
                # omit it to avoid rejection by strict OpenAI-compatible endpoints.
                assistant_msg: dict = {"role": "assistant"}
                if choice.message.content is not None:
                    assistant_msg["content"] = choice.message.content
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)
                for tc in tool_calls:
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as json_exc:
                        logger.warning(
                            "Tool %s: argomenti JSON non validi %r: %s",
                            tc.function.name, tc.function.arguments[:120], json_exc,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({
                                "error": (
                                    f"Argomenti JSON non validi per '{tc.function.name}'. "
                                    "Correggi il JSON e riprova."
                                )
                            }),
                        })
                        continue
                    if dispatcher is not None:
                        # DispatcherConoscenza (e affini): stessa interfaccia
                        # minima dispatch(nome, argomenti). fetta E4 Task 6:
                        # il ramo "dispatcher di scorta" (self._dispatcher,
                        # con le kwargs allowed_entities/allowed_services/
                        # allowed_endpoints/chatbot_id/visible_entity_ids/
                        # knowledge_allow_sensitive/knowledge_kinds) e' uscito
                        # -- vedi il commento gemello in ClaudeRunner.chat().
                        result = await dispatcher.dispatch(tc.function.name, tool_input)
                    else:
                        # ne' un dispatcher per-chiamata -- vedi il commento
                        # gemello in ClaudeRunner.chat().
                        logger.debug(
                            "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                            "(degradazione dichiarata, non un errore)", tc.function.name)
                        result = {"error": f"Strumento '{tc.function.name}' non disponibile."}
                    self.last_tool_calls.append({"tool": tc.function.name, "input": tool_input})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
            else:
                if choice.finish_reason == "length":
                    # OpenAI's analog of Anthropic max_tokens: generation cut off
                    # (possibly mid tool call). Surface the truncation instead of
                    # returning a misleading partial preamble with nothing executed.
                    from ..claude_runner import _max_tokens_message
                    return _max_tokens_message([choice.message.content or ""])
                raw_content = choice.message.content or f"Stopped: {choice.finish_reason}"
                leaked = detect_leaked_tool_call(raw_content, tool_name_set)
                if leaked:
                    logger.warning(
                        "Model %s leaked tool call '%s' as text content "
                        "(finish_reason=%s). Sample: %r",
                        effective_model, leaked, choice.finish_reason, raw_content[:160],
                    )
                    return TOOL_LEAK_USER_MSG
                return raw_content

        return "Max tool iterations reached."

    async def chat_stream(
        self,
        user_message: str,
        system_prompt: str = "",
        context_str: str = "",
        conversation_history: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        response_mode: str = "auto",
        thinking_budget: int = 0,
        strumenti: list[dict] | None = None,
        dispatcher: Any | None = None,
    ):
        """Vero streaming SSE: i token arrivano mentre il modello genera.
        Le iterazioni tool-call vengono risolte prima di cedere il controllo
        al loop successivo; il testo finale è streamato token per token.

        `strumenti`/`dispatcher` (Task 3 della fetta "il contesto della chat
        viene dal nucleo"): a differenza di `ClaudeRunner.chat_stream`, che e'
        gia' un guscio sottile attorno a `chat()`, questo metodo costruisce il
        proprio loop agentico da zero -- quindi i due punti dove `chat()`
        applica la stessa regola (catalogo tool, dispatch) sono replicati qui
        sotto uno per uno, non ereditati per delega. Senza questo, il ramo SSE
        (la card Lovelace) sarebbe rimasto sul catalogo di trentaquattro
        strumenti mentre la pagina chat (che non streamma, vedi
        static/chat/send.js) passava ai quattro del nucleo -- due strade
        divergenti per la stessa conversazione, esattamente il difetto che
        questa fetta esiste per chiudere.
        """
        # See chat() for rationale on accepting+ignoring thinking_budget here.
        del thinking_budget
        import openai as _openai

        # review M3/#2: see chat() above -- the streaming agentic loop must
        # also consult the circuit breaker instead of hammering a dead
        # endpoint at full timeout on every turn.
        if self._circuit_is_open():
            yield (
                'data: '
                + json.dumps({
                    "type": "error",
                    "message": (
                        f"{self._backend_noun} non risponde da diversi tentativi "
                        "consecutivi (circuito aperto). Riprova tra qualche istante."
                    ),
                })
                + '\n\n'
            )
            return

        self.last_tool_calls = []
        # Fresh per-exchange pseudonymization map (review B/#7).
        self.last_pseudonym_map = {}
        self.total_requests += 1

        effective_model = self._resolve_model(model, agent_type)
        system_parts = [BASE_SYSTEM_PROMPT]
        if system_prompt:
            system_parts.append(system_prompt)
        if context_str:
            system_parts.append(context_str)
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
        # fetta E4 Task 6 ("un bot solo"): il parametro `require_confirmation`
        # stesso e' uscito -- vedi il commento gemello in chat() sopra.
        if response_mode == "compact":
            system_parts.append("Rispondi in modo conciso, massimo 2-3 frasi.")
        elif response_mode == "minimal":
            system_parts.append(
                "Rispondi SOLO in formato chiave: valore, una riga per dato. "
                "Esempio:\nStato: acceso\nTemperatura: 21°C"
            )

        messages: list[dict] = [{"role": "system", "content": "\n\n---\n\n".join(system_parts)}]
        for msg in (conversation_history or []):
            messages.append({"role": msg["role"], "content": str(msg["content"])})
        messages.append({"role": "user", "content": user_message})

        if strumenti is not None:
            # Il catalogo arriva gia' deciso dal chiamante -- stessa regola di
            # chat() (vedi il suo commento gemello).
            tools = list(strumenti)
        else:
            # fetta E3 Task 8: nessun catalogo di scorta da cui pescare --
            # vedi il commento gemello in claude_runner.chat(). Lo streaming
            # non e' una porta di servizio: stessa regola di chat().
            tools = []
        oai_tools = _to_openai_tools(tools) if tools else None
        tool_name_set = frozenset(t["name"] for t in tools)

        if self._fixed_model and tools:
            tool_names = ", ".join(t["name"] for t in tools)
            messages[0]["content"] += (
                f"\n\n---\n\nTool disponibili: {tool_names}.\n"
                "NON chiamare tool non presenti in questa lista."
            )

        max_iter = _OLLAMA_MAX_TOOL_ITERATIONS if self._fixed_model else MAX_TOOL_ITERATIONS
        try:
            for _ in range(max_iter):
                kwargs: dict = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": True,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                # Ollama-specific: vedi commento in chat() per think:false.
                if self._fixed_model:
                    kwargs["extra_body"] = {"think": False}

                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                except _openai.RateLimitError as exc:
                    self.total_rate_limit_errors += 1
                    logger.error("OpenAI rate limit (stream): %s", exc)
                    upstream = parse_upstream_rate_limit(exc)
                    err_msg = upstream or "Rate limit — riprova tra poco."
                    yield f'data: {json.dumps({"type": "error", "message": err_msg})}\n\n'
                    return
                except _openai.APIError as exc:
                    # OpenRouter 402: see chat() for full rationale.
                    affordable = parse_afford_limit(exc)
                    if affordable and affordable < kwargs.get("max_tokens", 0):
                        logger.warning(
                            "OpenRouter 402 stream on %s: requested max_tokens=%d, "
                            "retrying with %d (key credit limit).",
                            effective_model, kwargs["max_tokens"], affordable,
                        )
                        kwargs["max_tokens"] = affordable
                        try:
                            stream = await self._client.chat.completions.create(**kwargs)
                        except _openai.APIError as retry_exc:
                            logger.error(
                                "OpenRouter 402 stream retry failed: %s", retry_exc,
                            )
                            err = (
                                f"Crediti OpenRouter insufficienti per max_tokens={max_tokens}. "
                                f"Riduci max_tokens dell'agente sotto {affordable} "
                                f"oppure aggiungi credito su openrouter.ai."
                            )
                            yield f'data: {json.dumps({"type": "error", "message": err})}\n\n'
                            return
                    else:
                        # review M3/#2: see chat() for full rationale — trip
                        # the breaker on connection-class failures so a dead
                        # endpoint fails fast on subsequent turns.
                        if _is_conn_error(exc):
                            self._record_conn_failure()
                        logger.error("OpenAI/Ollama API error (stream): %s", exc)
                        yield f'data: {json.dumps({"type": "error", "message": "Errore temporaneo del servizio AI."})}\n\n'
                        return

                self._record_success()
                collected_text = ""
                finish_reason: Optional[str] = None
                # {index: {id, name, args}} — assembla i frammenti tool-call dallo stream
                tc_fragments: dict[int, dict] = {}

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta

                    if delta.content:
                        collected_text += delta.content
                        yield f'data: {json.dumps({"type": "token", "text": delta.content})}\n\n'

                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tc_fragments:
                                tc_fragments[idx] = {"id": "", "name": "", "args": ""}
                            if tc_delta.id:
                                tc_fragments[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc_fragments[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc_fragments[idx]["args"] += tc_delta.function.arguments

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                if not tc_fragments:
                    # Risposta testuale finale — stream completato.
                    # Verifica leak di tool call come testo (Mistral/Hermes su
                    # OpenRouter): se rilevato, dì al frontend di scartare i
                    # token già renderizzati e mostra un errore esplicito,
                    # così la chat history non viene avvelenata al prossimo
                    # turno.
                    leaked = detect_leaked_tool_call(collected_text, tool_name_set)
                    if leaked:
                        logger.warning(
                            "Stream from %s leaked tool call '%s' as text content. "
                            "Sample: %r",
                            effective_model, leaked, collected_text[:160],
                        )
                        yield f'data: {json.dumps({"type": "discard_collected"})}\n\n'
                        yield f'data: {json.dumps({"type": "error", "message": TOOL_LEAK_USER_MSG})}\n\n'
                        return
                    if finish_reason == "length":
                        # review M3/#1: chat() surfaces _TRUNCATION_NOTICE
                        # when finish_reason=='length' (see the "else" branch
                        # below the tool_calls check there); this streaming
                        # path used to just `break` silently, leaving the
                        # client with a truncated response and no warning.
                        from ..claude_runner import _TRUNCATION_NOTICE
                        notice = f"\n\n{_TRUNCATION_NOTICE}"
                        yield f'data: {json.dumps({"type": "token", "text": notice})}\n\n'
                    break

                # Ci sono tool calls: eseguili e continua il loop
                tcs = sorted(tc_fragments.items())
                assistant_msg: dict = {"role": "assistant"}
                if collected_text:
                    assistant_msg["content"] = collected_text
                assistant_msg["tool_calls"] = [
                    {
                        "id": d["id"],
                        "type": "function",
                        "function": {"name": d["name"], "arguments": d["args"]},
                    }
                    for _, d in tcs
                ]
                messages.append(assistant_msg)

                for _, tc_data in tcs:
                    try:
                        tool_input = json.loads(tc_data["args"])
                    except json.JSONDecodeError as json_exc:
                        logger.warning(
                            "chat_stream tool %s: JSON non valido %r: %s",
                            tc_data["name"], tc_data["args"][:120], json_exc,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_data["id"],
                            "content": json.dumps({
                                "error": (
                                    f"Argomenti JSON non validi per '{tc_data['name']}'. "
                                    "Correggi il JSON e riprova."
                                )
                            }),
                        })
                        continue
                    if dispatcher is not None:
                        # DispatcherConoscenza (e affini): stessa interfaccia
                        # minima dispatch(nome, argomenti). fetta E4 Task 6:
                        # il ramo "dispatcher di scorta" (self._dispatcher) e'
                        # uscito -- vedi il commento gemello in chat().
                        result = await dispatcher.dispatch(tc_data["name"], tool_input)
                    else:
                        # ne' un dispatcher per-chiamata -- vedi il commento
                        # gemello in chat().
                        logger.debug(
                            "Strumento '%s' richiesto ma nessun dispatcher disponibile "
                            "(degradazione dichiarata, non un errore)", tc_data["name"])
                        result = {"error": f"Strumento '{tc_data['name']}' non disponibile."}
                    self.last_tool_calls.append({"tool": tc_data["name"], "input": tool_input})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_data["id"],
                        "content": json.dumps(result),
                    })

        except Exception as exc:
            logger.error("chat_stream error: %s", exc)
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        # fetta E4 Task 6: il campo `agent_id` esce -- vedi il commento
        # gemello nel docstring di ClaudeRunner.chat_stream() (nessun lettore
        # in static/, grep verificato).
        yield f'data: {json.dumps({"type": "done", "tool_calls": self.last_tool_calls})}\n\n'

    # fetta E3 Task 8: `run_with_actions` e' uscito -- vedi il commento
    # gemello in claude_runner.py (stesso motivo: il suo unico chiamante, la
    # Sentinella, e' uscito al Task 7 di questa fetta).
