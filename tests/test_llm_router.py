import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.backends.base import LLMBackend
from hiris.app.backends.ollama import OllamaBackend
from hiris.app.llm_router import LLMRouter
from hiris.app.claude_runner import _current_tool_calls, _current_thinking_blocks, RunnerBackendError


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
    runner.simple_chat = AsyncMock(return_value='{"sensor.test": {"role": "energy_meter", "label": "Test", "confidence": 0.9}}')
    runner.last_tool_calls = []
    runner.total_input_tokens = 10
    runner.total_output_tokens = 5
    runner.total_requests = 1
    runner.total_cost_usd = 0.001
    runner.total_rate_limit_errors = 0
    runner.usage_last_reset = "2026-04-22T00:00:00Z"
    runner.reset_usage = MagicMock()
    return runner


@pytest.mark.asyncio
async def test_router_chat_delegates_to_runner(mock_runner):
    router = LLMRouter(claude=mock_runner)
    result = await router.chat(user_message="hello", system_prompt="sys")
    mock_runner.chat.assert_awaited_once()
    assert result == "response text"


def test_router_proxies_usage_properties(mock_runner):
    router = LLMRouter(claude=mock_runner)
    assert router.total_input_tokens == 10
    assert router.last_tool_calls == []


def test_router_last_tool_calls_reflects_current_call_not_stale_backend(mock_runner):
    """Review A/#3: LLMRouter.last_tool_calls must proxy the shared per-call
    ContextVar (the exact buffer ClaudeRunner/OpenAICompatRunner.chat()
    populate), not scan registered backends for "whichever has a non-empty
    list". The old scan could return a totally different caller's tool
    calls than the one that actually just ran through this router — a mock
    backend's stale/unrelated `last_tool_calls` attribute must NOT leak
    through the router property."""
    mock_runner.last_tool_calls = [{"tool": "stale_backend_attr", "input": {}}]
    router = LLMRouter(claude=mock_runner)
    token = _current_tool_calls.set([{"tool": "get_home_status", "input": {}}])
    try:
        assert router.last_tool_calls == [{"tool": "get_home_status", "input": {}}]
    finally:
        _current_tool_calls.reset(token)


def test_router_last_thinking_blocks_reflects_current_call(mock_runner):
    """LLMRouter previously had NO last_thinking_blocks property at all, so
    handlers_chat.py's `getattr(runner, "last_thinking_blocks", None)`
    silently returned None whenever chat went through the router — the
    debug payload's thinking_blocks was always empty. Now it proxies the
    same shared per-call ContextVar as ClaudeRunner."""
    router = LLMRouter(claude=mock_runner)
    assert router.last_thinking_blocks == []
    token = _current_thinking_blocks.set(["step 1: ..."])
    try:
        assert router.last_thinking_blocks == ["step 1: ..."]
    finally:
        _current_thinking_blocks.reset(token)


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
# Review C/#13: runners now RAISE RunnerBackendError on API failure instead
# of returning a friendly string — these prove the fallback loop actually
# engages on that exception (it was previously dead code: a returned string
# never raised, so the primary "succeeded" and the healthy secondary was
# never tried).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_chat_fails_over_on_runner_backend_error(mock_runner):
    """Primary raises RunnerBackendError (e.g. rate limit) -> router tries
    the next configured backend and returns ITS reply, not a degraded string.
    Fails on the pre-fix code, where chat() swallowed the API error into a
    returned string and the fallback loop never ran."""
    failing_runner = MagicMock()
    failing_runner.chat = AsyncMock(
        side_effect=RunnerBackendError("Errore temporaneo del servizio AI. Riprova tra poco.")
    )
    mock_ollama = MagicMock()
    mock_ollama.chat = AsyncMock(return_value="ollama fallback")
    router = LLMRouter(claude=failing_runner, ollama=mock_ollama, strategy="quality_first")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "ollama fallback"
    failing_runner.chat.assert_awaited_once()
    mock_ollama.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_chat_all_backends_raise_returns_last_friendly_message(mock_runner):
    """Every backend raises RunnerBackendError -> router returns the LAST
    failure's friendly_message (no exception propagates to the caller)."""
    first = MagicMock()
    first.chat = AsyncMock(side_effect=RunnerBackendError("Errore Claude, riprova."))
    second = MagicMock()
    second.chat = AsyncMock(side_effect=RunnerBackendError("Crediti OpenRouter esauriti."))
    router = LLMRouter(claude=first, openrouter=second, strategy="balanced")
    result = await router.chat(user_message="hello", model="auto")
    assert result == "Crediti OpenRouter esauriti."


# fetta E3 Task 8: `test_router_run_with_actions_fails_over_on_runner_
# backend_error` e `test_router_run_with_actions_all_fail_returns_last_
# friendly_message` sono usciti, cancellati e non spostati -- provavano
# `LLMRouter.run_with_actions`, uscito insieme al suo unico chiamante
# (server.py's `_llm_reason`, la Sentinella, uscita al Task 7). La prova
# gemella sul fallback di `chat()` (test_router_chat_fails_over_on_runner_
# backend_error / test_router_chat_all_backends_raise_returns_last_friendly_
# message, sopra) resta: quel meccanismo e' vivo, `chat()` non e' uscito.


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
    # balanced: claude > openrouter > openai > ollama
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
        usage_path=str(tmp_path / "u.json"),
    )
    assert "openrouter.ai/api/v1" in str(runner._client.base_url)
    # No fixed_model -> cloud retry profile
    assert runner._client.max_retries == 2


def test_backend_is_cloud():
    from hiris.app.llm_router import backend_is_cloud
    assert backend_is_cloud("claude-sonnet-4-6") is True
    assert backend_is_cloud("gpt-4o-mini") is True
    assert backend_is_cloud("openrouter:meta/llama") is True
    assert backend_is_cloud("llama3.1:8b") is False   # Ollama locale
    # 'auto' è cloud-first nelle strategie default → trattato come cloud (prudente)
    assert backend_is_cloud("auto") is True


class _Dummy:
    async def chat(self, **k): return "ok"


# fetta E4 Task 7 ("un bot solo"): la modalita' "automatic" e' uscita insieme
# all'ultimo chiamante che passava mode="automatic" (chatbot_engine.py, uscito
# al Task 4) -- con lei sono uscite la seconda policy (automatic_policy) e
# automatic_allows_sensitive(), gia' solo-test dal censimento prima di questo
# task. `test_model_chain_all_local_allows_sensitive`,
# `test_model_chain_with_cloud_blocks_sensitive`,
# `test_none_model_chain_preserves_legacy_two_policies` e
# `test_all_inactive_fails_closed_for_sensitive_egress` sono usciti, cancellati
# e non spostati -- provavano `automatic_allows_sensitive()` e/o la doppia
# policy chat/automatic di `_ordered_backends(mode)`: nessuno dei due soggetti
# esiste piu'. Verificato che cadessero per costruzione
# (`AttributeError: 'LLMRouter' object has no attribute 'automatic_allows_sensitive'`,
# `TypeError: LLMRouter.__init__() got an unexpected keyword argument
# 'automatic_policy'`) prima della cancellazione.


def test_model_chain_sets_single_chain_for_both_modes():
    claude, ollama = _Dummy(), _Dummy()
    r = LLMRouter(claude=claude, ollama=ollama, strategy="balanced",
                  model_chain=["ollama", "claude"])
    # un'unica policy (chat_policy), nell'ordine dato dalla catena
    assert r._ordered_backends() == [ollama, claude]


@pytest.mark.asyncio
async def test_simple_chat_senza_runner_non_finge_una_risposta_vuota():
    """A3: senza alcun provider configurato `simple_chat` restituiva "", che il
    chiamante non puo' distinguere da una risposta vuota del modello. Deve
    dirlo, come gia' fa `chat` nello stesso file."""
    router = LLMRouter()

    res = await router.simple_chat([{"role": "user", "content": "ciao"}])

    assert res, "una stringa vuota e' indistinguibile da una risposta del modello"
    assert "provider" in res.lower()


@pytest.mark.asyncio
async def test_simple_chat_con_runner_resta_trasparente():
    """Il caso opposto: se un runner c'e', la risposta passa cosi' com'e' --
    anche quando e' vuota, perche' li' e' davvero il modello ad aver taciuto."""
    runner = MagicMock()
    runner.simple_chat = AsyncMock(return_value="")
    router = LLMRouter(ollama=runner)

    assert await router.simple_chat([{"role": "user", "content": "ciao"}]) == ""
    runner.simple_chat.assert_awaited_once()
