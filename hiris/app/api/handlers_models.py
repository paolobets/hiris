from __future__ import annotations
import json
import logging
import os
import re

import aiohttp
from aiohttp import web

from ..env_util import env_bool

logger = logging.getLogger(__name__)

# SP-2 Task 4: models-config store (chain_order + brain_model), see §8 code map.
_VALID_BACKENDS = ("claude", "openai", "openrouter", "ollama")

# SP-2 Task 5C: per-provider DEFAULT model, e.g. {"claude": "claude-opus-4-7"}.
# Empty string ("") = auto (fall back to AUTO_MODEL_MAP). Ollama excluded — it
# always uses its fixed `local_model.model`.
_PROVIDER_MODEL_KEYS = ("claude", "openai", "openrouter")


def _clean_provider_models(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k in _PROVIDER_MODEL_KEYS:
        v = raw.get(k, "")
        out[k] = v if isinstance(v, str) else ""
    return out


def _models_config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "models_config.json")


def load_models_config(data_dir: str) -> dict:
    try:
        with open(_models_config_path(data_dir), encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = {}
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    raw_chain = raw.get("chain_order", [])
    if not isinstance(raw_chain, list):
        raw_chain = []
    chain = [n for n in raw_chain if n in _VALID_BACKENDS]
    brain = raw.get("brain_model", "auto")
    if not isinstance(brain, str) or not brain:
        brain = "auto"
    return {
        "chain_order": chain,
        "brain_model": brain,
        "provider_models": _clean_provider_models(raw.get("provider_models")),
    }


def save_models_config(data_dir: str, data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}
    raw_chain = data.get("chain_order", [])
    if not isinstance(raw_chain, list):
        raw_chain = []
    clean = {
        "chain_order": [n for n in raw_chain if n in _VALID_BACKENDS],
        "brain_model": data.get("brain_model", "auto"),
        "provider_models": _clean_provider_models(data.get("provider_models")),
    }
    if not isinstance(clean["brain_model"], str) or not clean["brain_model"]:
        clean["brain_model"] = "auto"
    path = _models_config_path(data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clean, fh)
    os.replace(tmp, path)
    return clean



# SP-2 Task 7-fix2: each entry also carries "toggle" (raw addon toggle,
# read straight from env — NOT the effective `active`) so the UI can render
# the "toggle ON but credential MISSING" amber state instead of collapsing
# it into "Disattivato".
#
# SP-2 Task 7B: fixed provider order + labels for the enriched config payload.
# Distinct from handle_list_models' "anthropic" id — here we use the same ids
# as app["active_providers"] (subscription/claude/openai/openrouter/ollama) so
# the UI can honestly show ALL five, including subscription and any
# uncredentialed provider, without needing a separate id-mapping table.
_CONFIG_PROVIDERS = (
    ("subscription", "Abbonamento Claude (subscription)"),
    ("claude", "Claude (Anthropic API)"),
    ("openai", "OpenAI"),
    ("openrouter", "OpenRouter"),
    ("ollama", "Locale (Ollama)"),
)


_TOGGLE_ENV_VARS = {
    "subscription": "PROVIDER_SUBSCRIPTION",
    "claude": "PROVIDER_CLAUDE",
    "openai": "PROVIDER_OPENAI",
    "openrouter": "PROVIDER_OPENROUTER",
    "ollama": "PROVIDER_OLLAMA",
}


def _config_raw_toggle(provider_id: str) -> bool:
    """Raw addon toggle value read directly from env — NOT the effective
    `active` (toggle AND credential) computed by
    model_activation.derive_active_providers(). Needed so the UI can detect
    "toggle ON but credential MISSING" (design §3.2 amber "manca
    credenziale"), a state that collapses into active=false and would
    otherwise be indistinguishable from "toggle OFF"."""
    env_var = _TOGGLE_ENV_VARS.get(provider_id)
    if not env_var:
        return False
    return env_bool(env_var)


def _config_has_credential(request: web.Request, provider_id: str) -> bool:
    """Boolean-only credential presence check — NEVER return the secret value."""
    if provider_id == "subscription":
        return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip())
    if provider_id == "claude":
        if os.environ.get("CLAUDE_API_KEY", "").strip():
            return True
        return request.app.get("claude_runner") is not None
    if provider_id == "openai":
        return bool(request.app.get("openai_api_key"))
    if provider_id == "openrouter":
        return bool(request.app.get("openrouter_api_key"))
    if provider_id == "ollama":
        return bool(request.app.get("local_model_url") and request.app.get("local_model_name"))
    return False


def _build_config_providers(request: web.Request) -> list[dict]:
    active_providers = request.app.get("active_providers", {}) or {}
    return [
        {
            "id": pid,
            "label": label,
            "active": bool(active_providers.get(pid)),
            "has_credential": _config_has_credential(request, pid),
            "toggle": _config_raw_toggle(pid),
        }
        for pid, label in _CONFIG_PROVIDERS
    ]


async def handle_get_models_config(request: web.Request) -> web.Response:
    data_dir = request.app.get("data_dir") or "/data"
    payload = load_models_config(data_dir)
    payload["providers"] = _build_config_providers(request)
    payload["llm_strategy"] = os.environ.get("LLM_STRATEGY", "balanced")
    payload["embeddings"] = {
        "provider": os.environ.get("MEMORY_EMBEDDING_PROVIDER", ""),
        "model": os.environ.get("MEMORY_EMBEDDING_MODEL", ""),
    }
    payload["ollama_model"] = request.app.get("local_model_name", "")
    return web.json_response(payload)


async def handle_save_models_config(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    data_dir = request.app.get("data_dir") or "/data"
    clean = save_models_config(data_dir, body if isinstance(body, dict) else {})
    request.app["models_config"] = clean   # hot-update per la sessione corrente
    return web.json_response({"ok": True, **clean})


def _hide_free_models_enabled() -> bool:
    """Return True if HIRIS_HIDE_FREE_MODELS is set to a truthy value.

    Use case: an installer who has paid OpenRouter credit and wants the
    dropdown to surface only paid (more reliable) models — useful when the
    free :free models would otherwise tempt usage but their daily quota /
    upstream rate-limits make them unsuitable for the user's workflow.
    """
    return env_bool("HIRIS_HIDE_FREE_MODELS")

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
#
# All entries SHOULD support tool use — HIRIS always sends the tool schema in
# chat requests. Models without tool support fail with HTTP 404
# "No endpoints found that support tool use" (see hermes-3-llama-3.1-405b:free,
# removed in v0.9.8 after observed failures). The live filter in
# `_fetch_openrouter_models` is authoritative when available.
_OPENROUTER_PRESETS = [
    # Free tier (rate-limited but $0)
    "openrouter:meta-llama/llama-3.3-70b-instruct:free",
    "openrouter:google/gemma-3-27b-it:free",
    "openrouter:qwen/qwen-2.5-72b-instruct:free",
    "openrouter:deepseek/deepseek-chat:free",
    "openrouter:mistralai/mistral-nemo:free",
    # Popular paid models accessible through OpenRouter
    "openrouter:anthropic/claude-sonnet-4-6",
    "openrouter:anthropic/claude-opus-4-7",
    "openrouter:openai/gpt-4o",
    "openrouter:openai/gpt-4.1",
    "openrouter:google/gemini-2.5-flash",
    "openrouter:mistralai/mistral-large",
]


def _supports_tools(entry: dict) -> bool:
    """Return True if an OpenRouter model entry advertises tool/function support.

    OpenRouter exposes per-model capability via the ``supported_parameters``
    array. Models without ``tools`` (or the legacy ``function_calling``) in
    that list will reject any HIRIS chat request with HTTP 404
    ``"No endpoints found that support tool use"`` — exactly the failure
    mode reported on hermes-3-llama-3.1-405b:free. We hide them at list
    time so users can't accidentally pick them.
    """
    params = entry.get("supported_parameters") or []
    if not isinstance(params, list):
        return False
    params_set = {str(p).lower() for p in params}
    return "tools" in params_set or "function_calling" in params_set


async def _fetch_openrouter_models(api_key: str) -> list[str]:
    """Fetch the full OpenRouter model list and filter to a usable, tool-capable subset.

    Falls back to _OPENROUTER_PRESETS (best-effort, may include tool-incapable
    models) only if the live capability check cannot be performed.
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

        # Build live capability index. Tool support is required because every
        # HIRIS agent ships with the standard tool schema in the chat request;
        # picking a non-tool-capable model produces immediate API errors.
        tool_capable_ids: set[str] = set()
        for entry in data.get("data", []):
            mid = entry.get("id")
            if mid and _supports_tools(entry):
                tool_capable_ids.add(mid)

        if not tool_capable_ids:
            # OpenRouter response shape changed or capability data missing —
            # don't silently degrade to a list users cannot use; return
            # presets and let runtime errors surface.
            logger.warning(
                "OpenRouter returned no tool-capable models (capability "
                "field missing?). Falling back to presets."
            )
            return _OPENROUTER_PRESETS

        hide_free = _hide_free_models_enabled()

        # Keep curated presets first (in order), filtered by capability.
        result = [
            m for m in _OPENROUTER_PRESETS
            if m.removeprefix("openrouter:") in tool_capable_ids
            and not (hide_free and m.endswith(":free"))
        ]
        # Add any other ':free' tool-capable models not already in presets.
        # Skip them entirely if HIRIS_HIDE_FREE_MODELS is set.
        if not hide_free:
            for entry in data.get("data", []):
                mid = entry.get("id", "")
                if mid.endswith(":free") and mid in tool_capable_ids:
                    tagged = f"openrouter:{mid}"
                    if tagged not in result:
                        result.append(tagged)
        return result if result else _OPENROUTER_PRESETS
    except Exception as exc:
        logger.warning("Could not fetch OpenRouter models: %s", exc)
        return _OPENROUTER_PRESETS


# `is_openrouter_model_tool_capable` (uscita, fetta E4 Task 3 "un bot
# solo"): validava un modello OpenRouter contro la capability list live al
# salvataggio di un chatbot -- il suo unico chiamante era
# `handlers_chatbots._validate_openrouter_model`, uscito insieme a
# `handle_create_chatbot`/`handle_update_chatbot` (le tre strade di
# creazione sopravvissute alla E3 convergevano tutte su POST /api/chatbots
# con `enabled: true` di default, il contrario di quanto prescrive lo
# scope). Orfana per costruzione di questo task (non prevista dal brief,
# trovata dal censimento), raccolta subito insieme ai suoi sei test in
# tests/test_handlers_models_openrouter.py -- `_supports_tools`/
# `_fetch_openrouter_models`/`_hide_free_models_enabled`/
# `_OPENROUTER_PRESETS` restano vivi (alimentano GET /api/models, il
# dropdown modelli, indipendente dal CRUD chatbot) e non sono toccati.


# Maps the provider "id" used in the /api/models payload to the key used in
# app["active_providers"] (populated by model_activation.derive_active_providers).
# Note: the payload id for Claude is "anthropic" but the activation key is
# "claude" — they diverge, hence the explicit mapping instead of a 1:1 lookup.
_ACTIVE_PROVIDERS_KEY = {
    "anthropic": "claude",
    "openai": "openai",
    "openrouter": "openrouter",
    "ollama": "ollama",
}


def _enrich_provider(request: web.Request, entry: dict, has_credential: bool) -> dict:
    """Attach activation state to a provider entry, never the credential value itself."""
    active_providers = request.app.get("active_providers", {}) or {}
    active_key = _ACTIVE_PROVIDERS_KEY.get(entry["id"], entry["id"])
    entry["active"] = bool(active_providers.get(active_key))
    entry["has_credential"] = bool(has_credential)
    return entry


async def handle_list_models(request: web.Request) -> web.Response:
    providers = []

    # Anthropic / Claude
    claude_runner = request.app.get("claude_runner")
    if claude_runner is not None:
        providers.append(_enrich_provider(
            request,
            {"id": "anthropic", "label": "Claude (Anthropic)", "models": _CLAUDE_MODELS},
            has_credential=True,
        ))

    # OpenAI
    openai_key = request.app.get("openai_api_key", "")
    if openai_key:
        models = await _fetch_openai_models(openai_key)
        providers.append(_enrich_provider(
            request,
            {"id": "openai", "label": "OpenAI", "models": models},
            has_credential=bool(openai_key),
        ))

    # OpenRouter (200+ models via single API key, includes free tier)
    openrouter_key = request.app.get("openrouter_api_key", "")
    if openrouter_key:
        models = await _fetch_openrouter_models(openrouter_key)
        providers.append(_enrich_provider(
            request,
            {"id": "openrouter", "label": "OpenRouter (200+ modelli)", "models": models},
            has_credential=bool(openrouter_key),
        ))

    # Ollama / local
    local_url = request.app.get("local_model_url", "")
    local_name = request.app.get("local_model_name", "")
    if local_url:
        models = await _fetch_ollama_models(local_url, local_name)
        if models:
            providers.append(_enrich_provider(
                request,
                {"id": "ollama", "label": "Locale (Ollama)", "models": models},
                has_credential=bool(local_url),
            ))

    return web.json_response({"providers": providers})
