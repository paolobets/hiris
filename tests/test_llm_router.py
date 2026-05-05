import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.backends.base import LLMBackend
from hiris.app.backends.ollama import OllamaBackend
from hiris.app.llm_router import LLMRouter


def test_llm_backend_is_abstract():
    import inspect
    assert inspect.isabstract(LLMBackend)


@pytest.mark.asyncio
async def test_ollama_backend_simple_chat():
    backend = OllamaBackend(url="http://localhost:11434", model="llama3.2")
    mock_resp_data = {"message": {"content": '{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}'}}
    with patch("aiohttp.ClientSession") as MockSession:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.json = AsyncMock(return_value=mock_resp_data)
        ctx.raise_for_status = MagicMock()
        session_inst = MagicMock()
        session_inst.__aenter__ = AsyncMock(return_value=session_inst)
        session_inst.__aexit__ = AsyncMock(return_value=False)
        session_inst.post = MagicMock(return_value=ctx)
        MockSession.return_value = session_inst

        result = await backend.simple_chat([{"role": "user", "content": "classify"}])
        assert isinstance(result, str)
        assert "energy_meter" in result


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.chat = AsyncMock(return_value="response text")
    runner.run_with_actions = AsyncMock(return_value=("text", "OK", "action"))
    runner.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
    runner.last_tool_calls = []
    runner.total_input_tokens = 10
    runner.total_output_tokens = 5
    runner.total_requests = 1
    runner.total_cost_usd = 0.001
    runner.total_rate_limit_errors = 0
    runner.usage_last_reset = "2026-04-22T00:00:00Z"
    runner.get_agent_usage = MagicMock(return_value={"input_tokens": 10})
    runner.reset_agent_usage = MagicMock()
    runner.reset_usage = MagicMock()
    return runner


@pytest.mark.asyncio
async def test_router_chat_delegates_to_runner(mock_runner):
    router = LLMRouter(claude=mock_runner)
    result = await router.chat(user_message="hello", system_prompt="sys")
    mock_runner.chat.assert_awaited_once()
    assert result == "response text"


@pytest.mark.asyncio
async def test_router_classify_entities_no_local_uses_runner(mock_runner):
    router = LLMRouter(claude=mock_runner)
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    result = await router.classify_entities(entities)
    mock_runner.simple_chat.assert_awaited_once()
    assert "sensor.test" in result
    assert result["sensor.test"]["role"] == "energy_meter"


@pytest.mark.asyncio
async def test_router_classify_entities_uses_ollama_if_configured(mock_runner):
    mock_ollama = MagicMock()
    mock_ollama.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
    router = LLMRouter(claude=mock_runner, ollama=mock_ollama)
    entities = [{"id": "sensor.test", "state": "100", "name": "Test", "unit": "W"}]
    result = await router.classify_entities(entities)
    mock_ollama.simple_chat.assert_awaited_once()
    mock_runner.simple_chat.assert_not_awaited()


def test_router_proxies_usage_properties(mock_runner):
    router = LLMRouter(claude=mock_runner)
    assert router.total_input_tokens == 10
    assert router.last_tool_calls == []


def test_router_strategy_defaults_to_balanced(mock_runner):
    router = LLMRouter(claude=mock_runner)
    assert router._strategy == "balanced"


def test_router_strategy_invalid_falls_back_to_balanced(mock_runner):
    router = LLMRouter(claude=mock_runner, strategy="unknown_strategy")
    assert router._strategy == "balanced"


def test_router_strategy_cost_first_orders_ollama_first(mock_runner):
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama response")
    router = LLMRouter(claude=mock_runner, ollama=mock_ollama, strategy="cost_first")
    backends = router._ordered_backends()
    assert backends[0] is mock_ollama
    assert backends[1] is mock_runner


def test_router_strategy_quality_first_orders_claude_first(mock_runner):
    mock_ollama = MagicMock()
    router = LLMRouter(claude=mock_runner, ollama=mock_ollama, strategy="quality_first")
    backends = router._ordered_backends()
    assert backends[0] is mock_runner
    assert backends[1] is mock_ollama


@pytest.mark.asyncio
async def test_router_chat_fallback_on_exception(mock_runner):
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(side_effect=Exception("backend down"))
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama fallback")
    router = LLMRouter(claude=failing_runner, ollama=mock_ollama, strategy="quality_first")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "ollama fallback"
    failing_runner.chat.assert_awaited_once()
    mock_ollama.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_chat_all_fail_returns_error_message(mock_runner):
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(side_effect=Exception("down"))
    router = LLMRouter(claude=failing_runner, strategy="balanced")
    result = await router.chat(user_message="hello", model="auto")
    assert "non disponibili" in result


# ---------------------------------------------------------------------------
# OpenRouter routing (v0.9.6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_routes_openrouter_prefix_colon(mock_runner):
    or_runner = MagicMock()
    or_runner.chat = AsyncMock(return_value="from openrouter")
    or_runner.last_tool_calls = []
    router = LLMRouter(openrouter=or_runner, strategy="balanced")
    result = await router.chat(
        user_message="hi",
        model="openrouter:meta-llama/llama-3.3-70b-instruct:free",
    )
    assert result == "from openrouter"
    or_runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_routes_openrouter_prefix_slash(mock_runner):
    or_runner = MagicMock()
    or_runner.chat = AsyncMock(return_value="from openrouter")
    or_runner.last_tool_calls = []
    router = LLMRouter(openrouter=or_runner, strategy="balanced")
    result = await router.chat(
        user_message="hi",
        model="openrouter/anthropic/claude-sonnet-4-6",
    )
    assert result == "from openrouter"
    or_runner.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_claude_prefix_skips_openrouter(mock_runner):
    """Plain 'claude-*' must still route to Claude runner, not OpenRouter."""
    claude_runner = MagicMock()
    claude_runner.chat = AsyncMock(return_value="from claude")
    claude_runner.last_tool_calls = []
    or_runner = MagicMock()
    or_runner.chat = AsyncMock()
    or_runner.last_tool_calls = []
    router = LLMRouter(claude=claude_runner, openrouter=or_runner, strategy="balanced")
    result = await router.chat(user_message="hi", model="claude-sonnet-4-6")
    assert result == "from claude"
    or_runner.chat.assert_not_awaited()


def test_router_strategy_includes_openrouter_in_chain():
    or_runner = MagicMock()
    claude_runner = MagicMock()
    router = LLMRouter(claude=claude_runner, openrouter=or_runner, strategy="balanced")
    backends = router._ordered_backends()
    # balanced: claude > openai > openrouter > ollama
    assert backends[0] is claude_runner
    assert or_runner in backends


def test_openrouter_runner_strips_prefix_in_resolve_model():
    from hiris.app.backends.openrouter_runner import OpenRouterRunner, _strip_openrouter_prefix
    assert _strip_openrouter_prefix("openrouter:foo/bar:free") == "foo/bar:free"
    assert _strip_openrouter_prefix("openrouter/foo/bar") == "foo/bar"
    assert _strip_openrouter_prefix("anthropic/claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"


def test_openrouter_runner_init(tmp_path):
    """OpenRouterRunner constructs with OpenRouter base URL + max_retries default."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
        dispatcher=MagicMock(),
        usage_path=str(tmp_path / "u.json"),
    )
    assert "openrouter.ai/api/v1" in str(runner._client.base_url)
    # No fixed_model -> cloud retry profile
    assert runner._client.max_retries == 2
