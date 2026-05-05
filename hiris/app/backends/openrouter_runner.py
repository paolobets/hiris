"""OpenRouter runner — thin subclass of OpenAICompatRunner.

OpenRouter (https://openrouter.ai) is a unified proxy giving access to 200+
models (Claude, GPT, Llama, Gemini, Mistral, Qwen, DeepSeek, ...) through a
single OpenAI-compatible endpoint. Free-tier models are marked with the
':free' suffix.

HIRIS exposes OpenRouter via a model-name prefix:
  - ``openrouter:meta-llama/llama-3.3-70b-instruct:free``
  - ``openrouter/anthropic/claude-sonnet-4-6``  (also accepted)

This runner strips the prefix before sending to OpenRouter and otherwise
behaves like OpenAICompatRunner pointing at https://openrouter.ai/api/v1.

Privacy note: messages and context flow through OpenRouter servers (US)
and then to the chosen provider — see openrouter.ai/privacy.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .openai_compat_runner import OpenAICompatRunner

if TYPE_CHECKING:
    from ..tools.dispatcher import ToolDispatcher


_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _strip_openrouter_prefix(model: str) -> str:
    """Remove the HIRIS-specific 'openrouter:' or 'openrouter/' marker.

    OpenRouter expects model IDs in the form 'provider/model[:variant]'
    (e.g. 'meta-llama/llama-3.3-70b-instruct:free'). HIRIS users prefix
    them with 'openrouter:' for routing clarity; we strip the prefix
    before the API call.
    """
    if model.startswith("openrouter:"):
        return model[len("openrouter:"):]
    if model.startswith("openrouter/"):
        return model[len("openrouter/"):]
    return model


class OpenRouterRunner(OpenAICompatRunner):
    """OpenRouter-backed runner. Inherits all OpenAICompatRunner behaviour."""

    def __init__(
        self,
        api_key: str,
        dispatcher: "ToolDispatcher",
        *,
        usage_path: str = "",
    ) -> None:
        # No `fixed_model`: OpenRouter expects a different model per request,
        # selected by the user via the Designer model field. Default agent
        # behaviour (auto-resolve to a sensible cloud model) handled by
        # _resolve_model below.
        super().__init__(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key,
            dispatcher=dispatcher,
            usage_path=usage_path,
        )

    def _resolve_model(self, model: str, agent_type: str) -> str:
        """Strip 'openrouter:' / 'openrouter/' prefix before sending to OR."""
        if model == "auto":
            # Sensible default: Claude Sonnet via OpenRouter (paid but reliable);
            # users wanting free should set explicit model in Designer.
            return "anthropic/claude-sonnet-4-6"
        return _strip_openrouter_prefix(model)
