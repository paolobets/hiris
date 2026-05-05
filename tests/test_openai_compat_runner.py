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
