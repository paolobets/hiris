from __future__ import annotations
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
import httpx as _httpx

from ..claude_runner import (
    ALL_TOOL_DEFS,
    BASE_SYSTEM_PROMPT,
    EVALUATION_ONLY_TOOLS,
    RESTRICT_PROMPT,
    REQUIRE_CONFIRMATION_PROMPT,
    _parse_structured_output,
)
from .pricing import PRICING as _PRICING

if TYPE_CHECKING:
    from ..tools.dispatcher import ToolDispatcher

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


class OpenAICompatRunner:
    """Agentic LLM runner for OpenAI-compatible APIs (OpenAI cloud + Ollama local)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        dispatcher: "ToolDispatcher",
        *,
        fixed_model: str = "",
        usage_path: str = "",
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
        # cumulativamente possono superare il wrapper agent_engine 300s
        # producendo "Timeout dopo 300s" generico senza log specifici. Con
        # max_retries=0 il primo APIError/Timeout viene loggato e ritornato.
        # Cloud OpenAI: lascia il default (2) — la rete cloud è meno volatile.
        _max_retries = 0 if fixed_model else 2
        self._client = _openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url,
            timeout=_client_timeout, max_retries=_max_retries,
        )
        self._dispatcher = dispatcher
        self._fixed_model = fixed_model   # Ollama: always use this model; empty for OpenAI
        self._usage_path = usage_path
        self.last_tool_calls: list[dict] = []
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_requests: int = 0
        self.total_cost_usd: float = 0.0
        self.total_rate_limit_errors: int = 0
        self.usage_last_reset: str = datetime.now(timezone.utc).isoformat()
        self._per_agent_usage: dict[str, dict] = {}
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
            self._per_agent_usage = data.get("per_agent", {})
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
            "per_agent": dict(self._per_agent_usage),
        }
        tmp = self._usage_path + ".tmp"

        def _write() -> None:
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

    def get_agent_usage(self, agent_id: str) -> dict:
        pau = self._per_agent_usage.get(agent_id)
        if pau is None:
            return {
                "input_tokens": 0, "output_tokens": 0,
                "requests": 0, "cost_usd": 0.0, "last_run": None,
                "tokens_today": 0, "tokens_today_date": "",
            }
        self._ensure_today_reset(pau)
        return dict(pau)

    def reset_agent_usage(self, agent_id: str) -> None:
        self._per_agent_usage[agent_id] = {
            "input_tokens": 0, "output_tokens": 0,
            "requests": 0, "cost_usd": 0.0, "last_run": None,
            "tokens_today": 0, "tokens_today_date": "",
        }
        self._save_usage()

    def _track_usage(self, response: Any, model: str, agent_id: Optional[str]) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            logger.debug("Model %s did not return usage info — token tracking skipped", model)
            return
        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        prices = _PRICING.get(model, _PRICING["_default"])
        cost = (inp * prices["input"] + out * prices["output"]) / 1_000_000
        self.total_input_tokens += inp
        self.total_output_tokens += out
        self.total_cost_usd += cost
        if agent_id:
            if agent_id not in self._per_agent_usage:
                self._per_agent_usage[agent_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                    "tokens_today": 0, "tokens_today_date": "",
                }
            pau = self._per_agent_usage[agent_id]
            pau["input_tokens"] += inp
            pau["output_tokens"] += out
            pau["cost_usd"] += cost
            self._ensure_today_reset(pau)
            pau["tokens_today"] = pau.get("tokens_today", 0) + inp + out
        self._save_usage()

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------

    def _resolve_model(self, model: str, agent_type: str) -> str:
        if self._fixed_model:
            return self._fixed_model
        if model == "auto":
            return AUTO_MODEL_MAP.get(agent_type, "gpt-4o-mini")
        return model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def simple_chat(self, messages: list[dict], system: str = "") -> str:
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
            return resp.choices[0].message.content or ""
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
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        visible_entity_ids: Optional[frozenset] = None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
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

        if agent_id:
            if agent_id not in self._per_agent_usage:
                self._per_agent_usage[agent_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                    "tokens_today": 0, "tokens_today_date": "",
                }
            self._per_agent_usage[agent_id]["requests"] += 1
            self._per_agent_usage[agent_id]["last_run"] = datetime.now(timezone.utc).isoformat()
        self.last_tool_calls = []
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
        if require_confirmation:
            system_parts.append(REQUIRE_CONFIRMATION_PROMPT)
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
        tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
        if allowed_endpoints is None:
            tools = [t for t in tools if t["name"] != "http_request"]
        if not self._dispatcher.has_memory:
            tools = [t for t in tools if t["name"] not in ("recall_memory", "save_memory")]
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
                        "Ollama call: model=%s iter=%d/%d agent=%s tools=%d msg_chars=%d",
                        effective_model, iter_idx + 1, max_iter,
                        agent_id or "-", len(oai_tools or []), msg_chars,
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
                return "Errore temporaneo del servizio AI. Riprova tra poco."
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
                        return (
                            f"Crediti OpenRouter insufficienti per max_tokens={max_tokens}. "
                            f"Riduci max_tokens dell'agente sotto {affordable} "
                            f"oppure aggiungi credito su openrouter.ai."
                        )
                else:
                    logger.error("OpenAI/Ollama API error: %s", exc)
                    return "Errore temporaneo del servizio AI. Riprova tra poco."

            self._track_usage(response, effective_model, agent_id)
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
                    result = await self._dispatcher.dispatch(
                        tc.function.name, tool_input,
                        allowed_entities=allowed_entities,
                        allowed_services=allowed_services,
                        allowed_endpoints=allowed_endpoints,
                        agent_id=agent_id,
                        visible_entity_ids=visible_entity_ids,
                    )
                    self.last_tool_calls.append({"tool": tc.function.name, "input": tool_input})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    })
            else:
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
        allowed_tools: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "chat",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        visible_entity_ids=None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
    ):
        """Vero streaming SSE: i token arrivano mentre il modello genera.
        Le iterazioni tool-call vengono risolte prima di cedere il controllo
        al loop successivo; il testo finale è streamato token per token.
        """
        # See chat() for rationale on accepting+ignoring thinking_budget here.
        del thinking_budget
        import openai as _openai

        self.last_tool_calls = []
        self.total_requests += 1
        if agent_id:
            if agent_id not in self._per_agent_usage:
                self._per_agent_usage[agent_id] = {
                    "input_tokens": 0, "output_tokens": 0,
                    "requests": 0, "cost_usd": 0.0, "last_run": None,
                    "tokens_today": 0, "tokens_today_date": "",
                }
            self._per_agent_usage[agent_id]["requests"] += 1
            self._per_agent_usage[agent_id]["last_run"] = datetime.now(timezone.utc).isoformat()

        effective_model = self._resolve_model(model, agent_type)
        system_parts = [BASE_SYSTEM_PROMPT]
        if system_prompt:
            system_parts.append(system_prompt)
        if context_str:
            system_parts.append(context_str)
        if restrict_to_home:
            system_parts.append(RESTRICT_PROMPT)
        if require_confirmation:
            system_parts.append(REQUIRE_CONFIRMATION_PROMPT)
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

        tools = [t for t in ALL_TOOL_DEFS if allowed_tools is None or t["name"] in allowed_tools]
        if allowed_endpoints is None:
            tools = [t for t in tools if t["name"] != "http_request"]
        if not self._dispatcher.has_memory:
            tools = [t for t in tools if t["name"] not in ("recall_memory", "save_memory")]
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
                    yield f'data: {json.dumps({"type": "error", "message": "Rate limit — riprova tra poco."})}\n\n'
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
                        logger.error("OpenAI/Ollama API error (stream): %s", exc)
                        yield f'data: {json.dumps({"type": "error", "message": "Errore temporaneo del servizio AI."})}\n\n'
                        return

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
                    result = await self._dispatcher.dispatch(
                        tc_data["name"], tool_input,
                        allowed_entities=allowed_entities,
                        allowed_services=allowed_services,
                        allowed_endpoints=allowed_endpoints,
                        agent_id=agent_id,
                        visible_entity_ids=visible_entity_ids,
                    )
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

        yield f'data: {json.dumps({"type": "done", "agent_id": agent_id, "tool_calls": self.last_tool_calls})}\n\n'

    async def run_with_actions(
        self,
        user_message: str,
        system_prompt: str,
        action_mode: str = "automatic",
        states: Optional[list[str]] = None,
        rules: Optional[list[dict]] = None,
        allowed_tools: Optional[list[str]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "agent",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
        response_mode: str = "auto",
        thinking_budget: int = 0,
    ) -> tuple[str, dict]:
        # thinking_budget accepted for runner-contract symmetry with
        # ClaudeRunner; not applicable on OpenAI-compat APIs (Ollama uses
        # extra_body think:false instead, applied unconditionally in chat()).
        del thinking_budget
        eval_tools = list(EVALUATION_ONLY_TOOLS)
        if allowed_tools:
            eval_tools = [t for t in eval_tools if t in allowed_tools]

        _states = states if states else ["OK", "ATTENZIONE", "ANOMALIA"]
        states_str = "|".join(_states)
        motivazione = "1 riga sintetica" if response_mode == "minimal" else "1-2 righe sintetiche"

        if action_mode == "automatic":
            eval_instruction = (
                "\n\n---\n"
                "ISTRUZIONI DI RISPOSTA:\n"
                "Analizza il contesto e concludi la risposta con queste righe esatte:\n\n"
                f"VALUTAZIONE: {states_str}\n"
                f"NOTIFICA: [messaggio da inviare — {motivazione}]\n"
                "[PARAM nome: valore  ← aggiungi una riga per ogni parametro dinamico necessario]\n"
                "AZIONI:\n"
                "[una azione per riga — formato: comando entità [valore]]\n\n"
                "Comandi AZIONI (vanno scritti in testo nel blocco AZIONI:, NON come tool calls):\n"
                "  turn_on <entity_id>\n"
                "  turn_off <entity_id>\n"
                "  set_value <entity_id> <value>\n"
                "  wait <minuti>\n"
                "  notify <channel> <message>\n"
                "  call_service <domain.service> <entity_id> [key=value ...]\n\n"
                "Se non sono necessarie azioni ometti il blocco AZIONI: completamente."
            )
        else:  # configured
            eval_instruction = (
                "\n\n---\n"
                "ISTRUZIONI DI RISPOSTA:\n"
                "Analizza il contesto e concludi la risposta con queste righe esatte:\n\n"
                f"VALUTAZIONE: {states_str}\n"
                f"NOTIFICA: [messaggio da inviare — {motivazione}]\n"
                "[PARAM nome: valore  ← aggiungi una riga per ogni parametro dinamico necessario]"
            )

        augmented_prompt = system_prompt + eval_instruction
        raw_result = await self.chat(
            user_message=user_message,
            system_prompt=augmented_prompt,
            allowed_tools=eval_tools,
            allowed_entities=allowed_entities,
            allowed_services=allowed_services,
            allowed_endpoints=allowed_endpoints,
            model=model,
            max_tokens=max_tokens,
            agent_type=agent_type,
            restrict_to_home=restrict_to_home,
            require_confirmation=require_confirmation,
            agent_id=agent_id,
            response_mode=response_mode,
        )
        clean_text, structured = _parse_structured_output(raw_result)
        return clean_text, structured
