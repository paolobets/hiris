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

from ..providers import OPENROUTER
from .openai_compat_runner import OpenAICompatRunner

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Il modello che questo runner usa quando nessuno ne ha scelto uno: pagante ma
# affidabile, e NON quello di OpenAI (`OPENAI.auto_model`, che su OpenRouter
# darebbe un nome inesistente). Era una stringa scritta dentro
# `_resolve_model`, poi una costante di questo modulo (`AUTO_OPENROUTER`): dal
# Task 9 della Tappa 7 e' `OPENROUTER.auto_model`, letto da qui e dalla pagina
# Modelli, che devono dire la stessa cosa.


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
        *,
        read_model=None,
        log_usage=None,
    ) -> None:
        # `local=False`: OpenRouter serve piu' modelli, e quello da usare lo
        # sceglie l'utente nella pagina Modelli (`read_model`); senza una
        # scelta vale `OPENROUTER.auto_model` (`_resolve_model`, qui sotto).
        super().__init__(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key,
            read_model=read_model,
            log_usage=log_usage,
        )
        # OpenRouter is always a US cloud proxy — override the parent default
        # (_is_cloud = not local would yield True since local=False here too,
        # but we set it explicitly for clarity and correctness).
        self._is_cloud = True
        # Il nome col quale i consumi finiscono nell'archivio. Senza questa
        # riga sarebbero scritti sulla riga di OpenAI: questa classe eredita
        # da `OpenAICompatRunner`, che si dichiara OpenAI.
        self.provider_name = OPENROUTER.id

    def _resolve_model(self, model: str) -> str:
        """Strip 'openrouter:' / 'openrouter/' prefix before sending to OR."""
        if model == "auto":
            # SP-2 T5C: user-chosen per-provider default wins; otherwise the
            # sensible built-in default (Claude Sonnet via OpenRouter — paid
            # but reliable). Strip in both cases since the stored default may
            # carry the HIRIS 'openrouter:' tag (same format as the picker).
            default = self._chosen_model() or OPENROUTER.auto_model
            return _strip_openrouter_prefix(default)
        return _strip_openrouter_prefix(model)
