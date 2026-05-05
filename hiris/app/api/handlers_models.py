from __future__ import annotations
import logging
import re

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# Recent Claude models (Anthropic doesn't expose a public list-models endpoint)
_CLAUDE_MODELS = [
    "auto",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

# Fallback OpenAI models if the API call fails
_OPENAI_FALLBACK = ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]

# Pattern: keep only current-gen GPT + reasoning models, no legacy/instruct/embedding
_OPENAI_KEEP = re.compile(r"^(gpt-4[o.1]|o[1-9](-mini|-preview)?)")
_OPENAI_SKIP = re.compile(r"instruct|embed|vision|realtime|audio|transcribe|tts|whisper")


async def _fetch_openai_models(api_key: str) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.openai.com/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenAI models list returned %s", resp.status)
                    return _OPENAI_FALLBACK
                data = await resp.json()
        models = [
            m["id"] for m in data.get("data", [])
            if _OPENAI_KEEP.match(m["id"]) and not _OPENAI_SKIP.search(m["id"])
        ]
        models.sort()
        return models if models else _OPENAI_FALLBACK
    except Exception as exc:
        logger.warning("Could not fetch OpenAI models: %s", exc)
        return _OPENAI_FALLBACK


async def _fetch_ollama_models(local_model_url: str, local_model_name: str) -> list[str]:
    from ..backends.ollama import _validate_ollama_url
    try:
        _validate_ollama_url(local_model_url)
    except ValueError as exc:
        logger.warning("Invalid local_model_url for Ollama listing: %s", exc)
        return [local_model_name] if local_model_name else []
    base = local_model_url.rstrip("/")
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{base}/api/tags") as resp:
                if resp.status != 200:
                    return [local_model_name] if local_model_name else []
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return [local_model_name] if local_model_name else []


# Curated subset of popular OpenRouter models. The full catalog (200+) is
# obtainable via openrouter.ai/api/v1/models but we surface only the most
# requested presets so the dropdown stays usable. Free-tier models marked
# ':free' have rate limits but no charge. User can still type any model
# manually with prefix 'openrouter:provider/model[:variant]'.
_OPENROUTER_PRESETS = [
    # Free tier (rate-limited but $0)
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    "openrouter:google/gemma-3-27b-it:free",
    "openrouter:qwen/qwen-2.5-72b-instruct:free",
    "openrouter:deepseek/deepseek-chat:free",
    "openrouter:mistralai/mistral-nemo:free",
    "openrouter:nousresearch/hermes-3-llama-3.1-405b:free",
    # Popular paid models accessible through OpenRouter
    "openrouter:anthropic/claude-sonnet-4-6",
    "openrouter:anthropic/claude-opus-4-7",
    "openrouter:openai/gpt-4o",
    "openrouter:openai/gpt-4.1",
    "openrouter:google/gemini-2.5-flash",
    "openrouter:mistralai/mistral-large",
]


async def _fetch_openrouter_models(api_key: str) -> list[str]:
    """Fetch the full OpenRouter model list and filter to a usable subset.

    Falls back to _OPENROUTER_PRESETS if the API call fails.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://openrouter.ai/api/v1/models", headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("OpenRouter models list returned %s", resp.status)
                    return _OPENROUTER_PRESETS
                data = await resp.json()
        # Build curated list: keep our presets first (in order), then free
        # variants of any other model OpenRouter exposes. Avoids overwhelming
        # the dropdown while letting the user pick free options not pre-listed.
        live_ids = {m.get("id") for m in data.get("data", []) if m.get("id")}
        # Validate presets still exist live (some may be retired)
        result = [
            m for m in _OPENROUTER_PRESETS
            if m.removeprefix("openrouter:") in live_ids
        ]
        # Add any other ':free' models not already in presets
        for entry in data.get("data", []):
            mid = entry.get("id", "")
            if mid.endswith(":free"):
                tagged = f"openrouter:{mid}"
                if tagged not in result:
                    result.append(tagged)
        return result if result else _OPENROUTER_PRESETS
    except Exception as exc:
        logger.warning("Could not fetch OpenRouter models: %s", exc)
        return _OPENROUTER_PRESETS


async def handle_list_models(request: web.Request) -> web.Response:
    providers = []

    # Anthropic / Claude
    if request.app.get("claude_runner") is not None:
        providers.append({"id": "anthropic", "label": "Claude (Anthropic)", "models": _CLAUDE_MODELS})

    # OpenAI
    openai_key = request.app.get("openai_api_key", "")
    if openai_key:
        models = await _fetch_openai_models(openai_key)
        providers.append({"id": "openai", "label": "OpenAI", "models": models})

    # OpenRouter (200+ models via single API key, includes free tier)
    openrouter_key = request.app.get("openrouter_api_key", "")
    if openrouter_key:
        models = await _fetch_openrouter_models(openrouter_key)
        providers.append({"id": "openrouter", "label": "OpenRouter (200+ modelli)", "models": models})

    # Ollama / local
    local_url = request.app.get("local_model_url", "")
    local_name = request.app.get("local_model_name", "")
    if local_url:
        models = await _fetch_ollama_models(local_url, local_name)
        if models:
            providers.append({"id": "ollama", "label": "Locale (Ollama)", "models": models})

    return web.json_response({"providers": providers})
