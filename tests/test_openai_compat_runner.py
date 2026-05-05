"""Regression tests for OpenAICompatRunner construction.

The 0.8.7 → 0.8.8 release passed `total=` to `httpx.Timeout`, which is not a
valid kwarg (httpx uses `timeout` as positional or `connect/read/write/pool`).
This crashed startup with `TypeError: Timeout.__init__() got an unexpected
keyword argument 'total'` whenever an OpenAI key or Ollama URL was configured.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner


@pytest.fixture
def dispatcher():
    return MagicMock()


def test_init_openai_cloud_does_not_raise(dispatcher, tmp_path):
    """Cloud variant (no fixed_model) must construct a valid httpx.Timeout."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "usage.json"),
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)


def test_init_ollama_local_does_not_raise(dispatcher, tmp_path, monkeypatch):
    """Ollama variant (fixed_model set) must construct a valid httpx.Timeout."""
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT", "90")
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "usage_ollama.json"),
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)


def test_ollama_disables_sdk_retry(dispatcher, tmp_path):
    """Ollama runner must use max_retries=0 (fail-fast on hang)."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="gemma4:e4b",
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._client.max_retries == 0


def test_openai_cloud_keeps_default_retry(dispatcher, tmp_path):
    """Cloud variant keeps SDK default retry (2) — cloud network is reliable."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._client.max_retries == 2


@pytest.mark.asyncio
async def test_ollama_chat_passes_think_false(dispatcher, tmp_path):
    """Ollama runner must inject extra_body={'think': False} on chat call."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="gemma4:e4b",
        usage_path=str(tmp_path / "u.json"),
    )
    # Mock the API to return a plain stop response
    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    await runner.chat(user_message="hi", model="gemma4:e4b")

    kwargs = runner._client.chat.completions.create.call_args.kwargs
    assert kwargs.get("extra_body") == {"think": False}


@pytest.mark.asyncio
async def test_openai_cloud_chat_omits_extra_body(dispatcher, tmp_path):
    """Cloud variant must NOT inject extra_body — keeps OpenAI semantics clean."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    await runner.chat(user_message="hi", model="gpt-4o")

    kwargs = runner._client.chat.completions.create.call_args.kwargs
    assert "extra_body" not in kwargs


# ---------------------------------------------------------------------------
# Regression: LLMRouter passes thinking_budget kwarg to all runners (v0.9.5).
# OpenAICompatRunner / OpenRouterRunner must accept it (and ignore it) to not
# crash with TypeError. This bug shipped in v0.9.6 — fixed in v0.9.7.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_accepts_thinking_budget_kwarg_silently(dispatcher, tmp_path):
    """OpenAI-compat chat() must accept thinking_budget without raising."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    # Must not raise — the LLMRouter forwards thinking_budget to every runner
    out = await runner.chat(user_message="hi", model="gpt-4o", thinking_budget=2048)
    assert out == "ok"


@pytest.mark.asyncio
async def test_run_with_actions_accepts_thinking_budget_kwarg_silently(dispatcher, tmp_path):
    """OpenAI-compat run_with_actions() must accept thinking_budget."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="gemma4:e4b",
        usage_path=str(tmp_path / "u.json"),
    )
    msg = MagicMock()
    msg.content = "VALUTAZIONE: OK\nNOTIFICA: -"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    # Must not raise — this is exactly the call path that broke in v0.9.6:
    # agent_engine -> LLMRouter.run_with_actions(**kwargs incl thinking_budget)
    # -> Ollama runner.run_with_actions
    out = await runner.run_with_actions(
        user_message="check",
        system_prompt="be brief",
        thinking_budget=4096,
    )
    assert isinstance(out, tuple) and len(out) == 2


def test_openrouter_runner_accepts_thinking_budget_kwarg(tmp_path):
    """OpenRouterRunner inherits the silent-accept behaviour from OpenAICompatRunner."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
        dispatcher=MagicMock(),
        usage_path=str(tmp_path / "u.json"),
    )
    # Just verify the method signature accepts thinking_budget (introspection)
    import inspect
    sig = inspect.signature(runner.chat)
    assert "thinking_budget" in sig.parameters
    sig2 = inspect.signature(runner.run_with_actions)
    assert "thinking_budget" in sig2.parameters


# ---------------------------------------------------------------------------
# Regression: tool-call leaked as text content (v0.9.8).
# Some OpenRouter providers (Mistral, Hermes) fail to translate the model's
# native special tool tokens into the OpenAI tool_calls schema, so the response
# arrives as plain text content like:
#   get_ha_healthיׂ{"sections":["all"]}
# Persisting this verbatim into chat history poisons later turns. The runner
# must detect and replace with a clean error message.
# ---------------------------------------------------------------------------

from hiris.app.backends.openai_compat_runner import (
    detect_leaked_tool_call,
    TOOL_LEAK_USER_MSG,
)


def test_detect_leaked_tool_call_mistral_pattern():
    """Real-world Mistral-via-OpenRouter sample: tool name + Hebrew separator + JSON."""
    leaked = "get_ha_healthיׂ{\"sections\": [\"all\"]}"
    out = detect_leaked_tool_call(leaked, {"get_ha_health", "get_home_status"})
    assert out == "get_ha_health"


def test_detect_leaked_tool_call_vietnamese_separator():
    """Variant from logs: tool name + Vietnamese 'lớ' separator."""
    leaked = "get_ha_health lớ{\"sections\": [\"all\"]}"
    # Note: a leading space breaks the strict-start match, but the original
    # transcript shows no space between name and separator — verify both.
    leaked_no_space = "get_ha_healthớ{\"sections\": [\"all\"]}"
    assert detect_leaked_tool_call(leaked_no_space, {"get_ha_health"}) == "get_ha_health"


def test_detect_leaked_tool_call_unknown_tool_returns_none():
    """Unknown identifier (model-invented tool) must not match — only real tools."""
    leaked = "await_user_confirmationׄ**Confermi?**"
    out = detect_leaked_tool_call(leaked, {"get_ha_health", "send_notification"})
    assert out is None


def test_detect_leaked_tool_call_legit_prose_does_not_match():
    """Plain Italian/English prose (em-dashes, accents) must not false-positive."""
    samples = [
        "Posso usare get_ha_health per controllare lo stato.",
        "Risposta: tutto ok — nessun problema.",
        "La temperatura è 21°C in salotto.",
        "",
        "get_ha_health: Vedo 5 errori",  # ASCII colon = legit prose
    ]
    tools = {"get_ha_health", "send_notification", "call_ha_service"}
    for s in samples:
        assert detect_leaked_tool_call(s, tools) is None, f"false positive on: {s!r}"


def test_detect_leaked_tool_call_empty_tools():
    """No tools available → no detection (cannot leak what isn't requested)."""
    leaked = "get_ha_healthיׂ{\"x\":1}"
    assert detect_leaked_tool_call(leaked, set()) is None
    assert detect_leaked_tool_call(leaked, None) is None


def test_detect_leaked_tool_call_accepts_list_input():
    """Caller passes list of tool names — helper coerces to frozenset."""
    leaked = "get_ha_healthיׂ{}"
    assert detect_leaked_tool_call(leaked, ["get_ha_health"]) == "get_ha_health"


@pytest.mark.asyncio
async def test_chat_replaces_leaked_tool_call_with_user_msg(dispatcher, tmp_path):
    """End-to-end: a leaked tool call must be replaced before returning to the caller,
    so chat_store does not persist the corrupted assistant turn."""
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    msg = MagicMock()
    msg.content = "get_ha_healthיׂ{\"sections\": [\"all\"]}"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    out = await runner.chat(
        user_message="check health",
        model="mistralai/mistral-large",
        allowed_tools=["get_ha_health", "get_home_status"],
    )
    assert out == TOOL_LEAK_USER_MSG
    assert "get_ha_health" not in out  # No leak in returned text


@pytest.mark.asyncio
async def test_chat_passes_through_clean_text(dispatcher, tmp_path):
    """Sanity: a normal text response must not be replaced."""
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    msg = MagicMock()
    msg.content = "Tutto ok — la casa è in buone condizioni."
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=10)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    out = await runner.chat(
        user_message="come stiamo",
        model="mistralai/mistral-large",
        allowed_tools=["get_ha_health"],
    )
    assert out == "Tutto ok — la casa è in buone condizioni."


# ---------------------------------------------------------------------------
# Regression: OpenRouter 402 'can only afford X tokens' (v0.9.8).
# Previously bubbled up as opaque "Errore temporaneo". Now the runner parses
# the affordable limit from the error message and retries once with that
# clamped max_tokens before giving up with an explicit, actionable message.
# ---------------------------------------------------------------------------

from hiris.app.backends.openai_compat_runner import parse_afford_limit


def test_parse_afford_limit_real_openrouter_message():
    """The exact message format observed from OpenRouter."""
    class _Err:
        message = (
            "This request requires more credits, or fewer max_tokens. "
            "You requested up to 4096 tokens, but can only afford 3907."
        )
    out = parse_afford_limit(_Err())
    assert out is not None
    # 95% safety margin: 3907 * 0.95 = 3711.65 → 3711
    assert 3500 <= out <= 3907


def test_parse_afford_limit_no_match_returns_none():
    class _Err:
        message = "Some other error not about credits"
    assert parse_afford_limit(_Err()) is None


def test_parse_afford_limit_handles_str_exception():
    """Exception without .message attribute → fall back to str()."""
    exc = ValueError("you can only afford 1000 tokens please")
    out = parse_afford_limit(exc)
    assert out is not None
    assert 900 <= out <= 1000


@pytest.mark.asyncio
async def test_chat_retries_on_402_afford_message(dispatcher, tmp_path):
    """First call raises 402 with afford message, runner retries with clamp."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False

    # Simulate APIError with the OpenRouter 402 message
    err = _openai.APIError(
        message="You requested up to 4096 tokens, but can only afford 3907.",
        request=MagicMock(),
        body=None,
    )

    msg = MagicMock()
    msg.content = "fallback ok"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)

    # First call raises, second call succeeds
    runner._client.chat.completions.create = AsyncMock(
        side_effect=[err, response]
    )

    out = await runner.chat(
        user_message="hi",
        model="mistralai/mistral-large",
        max_tokens=4096,
    )
    assert out == "fallback ok"
    # Verify retry was issued with a clamped max_tokens (< 4096, ~3711)
    second_call = runner._client.chat.completions.create.call_args_list[1]
    retry_max_tokens = second_call.kwargs["max_tokens"]
    assert retry_max_tokens < 4096
    assert retry_max_tokens <= 3907


@pytest.mark.asyncio
async def test_chat_returns_explicit_error_when_402_retry_also_fails(dispatcher, tmp_path):
    """If even the clamped retry hits 402 (zero credit), give explicit message."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    err = _openai.APIError(
        message="You requested up to 4096 tokens, but can only afford 3907.",
        request=MagicMock(),
        body=None,
    )
    err2 = _openai.APIError(
        message="You requested up to 3711 tokens, but can only afford 0.",
        request=MagicMock(),
        body=None,
    )
    runner._client.chat.completions.create = AsyncMock(side_effect=[err, err2])

    out = await runner.chat(
        user_message="hi",
        model="mistralai/mistral-large",
        max_tokens=4096,
    )
    assert "OpenRouter" in out
    assert "max_tokens" in out
    assert "4096" in out  # original requested value mentioned for clarity


@pytest.mark.asyncio
async def test_chat_non_402_api_error_still_returns_generic_message(dispatcher, tmp_path):
    """Non-402 API errors must keep the existing generic-error behaviour."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    err = _openai.APIError(
        message="Internal Server Error",
        request=MagicMock(),
        body=None,
    )
    runner._client.chat.completions.create = AsyncMock(side_effect=err)

    out = await runner.chat(user_message="hi", model="gpt-4o", max_tokens=4096)
    assert "Errore temporaneo" in out
    # Verify no retry happened
    assert runner._client.chat.completions.create.call_count == 1
