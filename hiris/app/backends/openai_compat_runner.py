from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from ..claude_runner import (
    ALL_TOOL_DEFS,
    BASE_SYSTEM_PROMPT,
    EVALUATION_ONLY_TOOLS,
    RESTRICT_PROMPT,
    REQUIRE_CONFIRMATION_PROMPT,
    _parse_structured_response,
    _build_action_instructions,
)
from .pricing import PRICING as _PRICING

if TYPE_CHECKING:
    from ..tools.dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)

AUTO_MODEL_MAP: dict[str, str] = {
    "chat":        "gpt-4o",
    "monitor":     "gpt-4o-mini",
    "reactive":    "gpt-4o-mini",
    "preventive":  "gpt-4o-mini",
}

MAX_TOOL_ITERATIONS = 10
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]


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
        self._client = _openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
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
            resp = await self._client.chat.completions.create(
                model=self._fixed_model or "gpt-4o-mini",
                messages=msgs,
                max_tokens=1024,
            )
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
    ) -> str:
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

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                kwargs: dict = {
                    "model": effective_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                response = await self._client.chat.completions.create(**kwargs)
            except _openai.RateLimitError as exc:
                self.total_rate_limit_errors += 1
                logger.error("OpenAI rate limit: %s", exc)
                return "Errore temporaneo del servizio AI. Riprova tra poco."
            except _openai.APIError as exc:
                logger.error("OpenAI/Ollama API error: %s", exc)
                return "Errore temporaneo del servizio AI. Riprova tra poco."

            self._track_usage(response, effective_model, agent_id)
            choice = response.choices[0]

            if choice.finish_reason == "stop":
                return choice.message.content or ""

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
                    except json.JSONDecodeError:
                        tool_input = {}
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
                return choice.message.content or f"Stopped: {choice.finish_reason}"

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
    ):
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
                agent_id=agent_id,
                visible_entity_ids=visible_entity_ids,
            )
        except Exception as exc:
            yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'
            return

        chunk_size = 80
        for i in range(0, len(result), chunk_size):
            yield f'data: {json.dumps({"type": "token", "text": result[i:i + chunk_size]})}\n\n'
        tool_calls = self.last_tool_calls if isinstance(self.last_tool_calls, list) else []
        yield f'data: {json.dumps({"type": "done", "agent_id": agent_id, "tool_calls": tool_calls})}\n\n'

    async def run_with_actions(
        self,
        user_message: str,
        system_prompt: str,
        actions: list[dict],
        allowed_tools: Optional[list[str]] = None,
        allowed_entities: Optional[list[str]] = None,
        allowed_services: Optional[list[str]] = None,
        allowed_endpoints: Optional[list[dict]] = None,
        model: str = "auto",
        max_tokens: int = 4096,
        agent_type: str = "monitor",
        restrict_to_home: bool = False,
        require_confirmation: bool = False,
        agent_id: Optional[str] = None,
    ) -> tuple[str, str | None, str | None]:
        eval_tools = list(EVALUATION_ONLY_TOOLS)
        if allowed_tools:
            eval_tools = [t for t in eval_tools if t in allowed_tools]

        eval_instruction = (
            "\n\n---\n"
            "Analizza il contesto e concludi la risposta con:\n"
            "VALUTAZIONE: OK|ATTENZIONE|ANOMALIA\n"
            "Motivazione: [1-2 righe sintetiche]"
        )
        action_block = _build_action_instructions(actions)
        augmented_prompt = system_prompt + eval_instruction + ("\n\n" + action_block if action_block else "")
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
        )
        return _parse_structured_response(raw_result)
