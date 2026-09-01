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

from .openai_compat_runner import OpenAICompatRunner

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Il modello che questo runner usa quando nessuno ne ha scelto uno: pagante ma
# affidabile, e NON quello di `AUTO_MODEL_MAP` (che è la mappa di OpenAI e su
# OpenRouter darebbe un nome inesistente). Era una stringa scritta dentro
# `_resolve_model` e basta: la pagina Modelli, che deve dire quale modello
# risponderebbe adesso, leggeva `AUTO_MODEL_MAP["chat"]` e scriveva `gpt-4o`
# nella riga di OpenRouter -- un modello che quel runner non chiederebbe mai.
# Una costante sola, letta dai due posti che devono dire la stessa cosa.
AUTO_OPENROUTER = "anthropic/claude-sonnet-4-6"


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
        leggi_modello=None,
        registra_consumo=None,
    ) -> None:
        # `locale=False`: OpenRouter expects a different model per request,
        # selected by the user via the Designer model field. Default agent
        # behaviour (auto-resolve to a sensible cloud model) handled by
        # _resolve_model below.
        #
        # fetta E4 Task 6 ("un bot solo"): il proprio `dispatcher` "di scorta"
        # -- una pura pass-through verso OpenAICompatRunner.__init__, uscito
        # li' -- e' uscito anche qui, stessa mossa. Nessun chiamante di
        # produzione lo passava (server.py costruisce sempre OpenRouterRunner
        # senza `dispatcher=`).
        super().__init__(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key,
            leggi_modello=leggi_modello,
            registra_consumo=registra_consumo,
        )
        # OpenRouter is always a US cloud proxy — override the parent default
        # (_is_cloud = not locale would yield True since locale=False here too,
        # but we set it explicitly for clarity and correctness).
        self._is_cloud = True
        # Il nome col quale i consumi finiscono nell'archivio. Senza questa
        # riga sarebbero scritti sulla riga di OpenAI: questa classe eredita
        # da `OpenAICompatRunner`, che si dichiara `"openai"`.
        self.provider_name = "openrouter"

    def _resolve_model(self, model: str, agent_type: str) -> str:
        """Strip 'openrouter:' / 'openrouter/' prefix before sending to OR."""
        if model == "auto":
            # SP-2 T5C: user-chosen per-provider default wins; otherwise the
            # sensible built-in default (Claude Sonnet via OpenRouter — paid
            # but reliable). Strip in both cases since the stored default may
            # carry the HIRIS 'openrouter:' tag (same format as the picker).
            default = self._modello_scelto() or AUTO_OPENROUTER
            return _strip_openrouter_prefix(default)
        return _strip_openrouter_prefix(model)
