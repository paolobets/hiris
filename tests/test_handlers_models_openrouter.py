"""Regression tests for OpenRouter model listing (v0.9.8).

Free models without tool-use support (e.g. nousresearch/hermes-3-llama-3.1-405b:free)
were surfaced in the dropdown but failed with HTTP 404 "No endpoints found that
support tool use" on every call. The fix filters by the model's
`supported_parameters` array.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hiris.app.api import handlers_models


def _mock_openrouter_response(payload: dict):
    """Build the (session, response) mock pair for aiohttp's context manager."""
    response_cm = MagicMock()
    response_cm.__aenter__ = AsyncMock(return_value=MagicMock(
        status=200,
        json=AsyncMock(return_value=payload),
    ))
    response_cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = MagicMock(return_value=response_cm)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return session_cm


def test_supports_tools_with_tools_param():
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["max_tokens", "tools", "tool_choice"]}
    ) is True


def test_supports_tools_with_function_calling_alias():
    """Older OpenRouter responses used 'function_calling' instead of 'tools'."""
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["function_calling"]}
    ) is True


def test_supports_tools_missing_param_returns_false():
    assert handlers_models._supports_tools({"id": "x"}) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": []}
    ) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": ["max_tokens", "temperature"]}
    ) is False


def test_supports_tools_handles_malformed_input():
    """Defensive: capability field is None or wrong type → False, not crash."""
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": None}
    ) is False
    assert handlers_models._supports_tools(
        {"id": "x", "supported_parameters": "tools"}  # string, not list
    ) is False


@pytest.mark.asyncio
async def test_fetch_filters_out_non_tool_capable_models():
    """Models without 'tools' in supported_parameters must not be listed."""
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6",
             "supported_parameters": ["tools", "max_tokens"]},
            {"id": "nousresearch/hermes-3-llama-3.1-405b:free",
             "supported_parameters": ["max_tokens"]},  # NO tools
            {"id": "meta-llama/llama-3.3-70b-instruct:free",
             "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert "openrouter:anthropic/claude-sonnet-4-6" in models
    assert "openrouter:meta-llama/llama-3.3-70b-instruct:free" in models
    # The model that ACTUALLY broke for the user
    assert "openrouter:nousresearch/hermes-3-llama-3.1-405b:free" not in models


@pytest.mark.asyncio
async def test_fetch_keeps_free_models_when_tool_capable():
    """Free models with tool support must still be added (even outside presets)."""
    payload = {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6",
             "supported_parameters": ["tools"]},
            {"id": "some-new-provider/cool-model:free",
             "supported_parameters": ["tools"]},
        ],
    }
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert "openrouter:some-new-provider/cool-model:free" in models


@pytest.mark.asyncio
async def test_fetch_falls_back_when_capability_field_missing():
    """If OpenRouter response shape changes (no capability data), use presets."""
    payload = {"data": [{"id": "x"}, {"id": "y"}]}
    session_cm = _mock_openrouter_response(payload)
    with patch("aiohttp.ClientSession", return_value=session_cm):
        models = await handlers_models._fetch_openrouter_models("sk-or-test")

    assert models == handlers_models._OPENROUTER_PRESETS


def test_presets_no_longer_include_known_broken_hermes3():
    """Regression: hermes-3-llama-3.1-405b:free does not support tools and was
    removed from presets (v0.9.8) after observed 404s."""
    assert "openrouter:nousresearch/hermes-3-llama-3.1-405b:free" not in (
        handlers_models._OPENROUTER_PRESETS
    )
