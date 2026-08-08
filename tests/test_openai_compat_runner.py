"""Regression tests for OpenAICompatRunner construction.

The 0.8.7 → 0.8.8 release passed `total=` to `httpx.Timeout`, which is not a
valid kwarg (httpx uses `timeout` as positional or `connect/read/write/pool`).
This crashed startup with `TypeError: Timeout.__init__() got an unexpected
keyword argument 'total'` whenever an OpenAI key or Ollama URL was configured.
"""
import json
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import RunnerBackendError


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


@pytest.mark.asyncio
async def test_circuit_open_message_names_cloud_backend(dispatcher, tmp_path):
    """Backlog #7: an open circuit on a CLOUD backend must not call itself
    'il backend locale' -- the noun tracks _is_cloud."""
    import time as _time
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1", api_key="sk-test",
        dispatcher=dispatcher, usage_path=str(tmp_path / "u.json"),
    )
    assert runner._backend_noun == "Il servizio AI"
    runner._circuit_open_until = _time.monotonic() + 60
    with pytest.raises(RunnerBackendError) as exc_info:
        await runner.chat(user_message="hi", model="gpt-4o", max_tokens=64)
    msg = exc_info.value.friendly_message
    assert "Il servizio AI" in msg and "backend locale" not in msg


def test_circuit_open_message_names_local_backend(dispatcher, tmp_path):
    """Backlog #7 (local variant): Ollama keeps the 'backend locale' wording."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._backend_noun == "Il backend locale"


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


# fetta E3 Task 8: `test_run_with_actions_accepts_thinking_budget_kwarg_
# silently` e' uscito, cancellato e non spostato -- provava
# `OpenAICompatRunner.run_with_actions`, uscito insieme al suo unico
# chiamante (la Sentinella, uscita al Task 7).


def test_openrouter_runner_accepts_thinking_budget_kwarg(tmp_path):
    """OpenRouterRunner inherits the silent-accept behaviour from OpenAICompatRunner."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
        dispatcher=MagicMock(),
        usage_path=str(tmp_path / "u.json"),
    )
    # Just verify the method signature accepts thinking_budget (introspection).
    # fetta E3 Task 8: la seconda meta' di questo test (su `run_with_actions`)
    # e' uscita insieme al metodo stesso -- vedi la nota sopra.
    import inspect
    sig = inspect.signature(runner.chat)
    assert "thinking_budget" in sig.parameters


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
    so chat_store does not persist the corrupted assistant turn.

    fetta E3 Task 8: prima passava `allowed_tools=[...]` senza `strumenti`, e
    contava sul vecchio fallback (EVALUATION_TOOL_DEFS filtrato da
    allowed_tools) per popolare `tool_name_set`, la base su cui
    `detect_leaked_tool_call` riconosce il nome fuoriuscito. Quel fallback e'
    uscito insieme al suo unico chiamante (la Sentinella): senza `strumenti`
    la chat non offre piu' nessun tool, quindi `tool_name_set` sarebbe vuoto e
    la fuga non verrebbe piu' riconosciuta. Il soggetto del test -- la
    detection end-to-end -- e' vivo (e' cosi' che funziona in produzione,
    dove la chat passa sempre `strumenti=STRUMENTI_CONOSCENZA`): si sposta su
    `strumenti`, con due tool_def minimi locali (stesso pattern di
    test_runner_catalogo.py's _FINTO_HTTP_REQUEST_TOOL_DEF)."""
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

    finti_tool_def = [
        {"name": "get_ha_health", "description": "finto", "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_home_status", "description": "finto", "input_schema": {"type": "object", "properties": {}}},
    ]
    out = await runner.chat(
        user_message="check health",
        model="mistralai/mistral-large",
        strumenti=finti_tool_def,
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

    with pytest.raises(RunnerBackendError) as exc_info:
        await runner.chat(
            user_message="hi",
            model="mistralai/mistral-large",
            max_tokens=4096,
        )
    out = exc_info.value.friendly_message
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

    with pytest.raises(RunnerBackendError) as exc_info:
        await runner.chat(user_message="hi", model="gpt-4o", max_tokens=4096)
    assert "Errore temporaneo" in exc_info.value.friendly_message
    # Verify no retry happened
    assert runner._client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Regression: clearer message for OpenRouter free-tier upstream rate limit
# (v0.9.9). Previously caught as RateLimitError → opaque "Errore temporaneo".
# ---------------------------------------------------------------------------

from hiris.app.backends.openai_compat_runner import parse_upstream_rate_limit


def test_parse_upstream_rate_limit_with_model_name():
    """Real OpenRouter free-tier message extracts the model id."""
    class _Err:
        message = (
            "Provider returned error qwen/qwen3-next-80b-a3b-instruct:free is "
            "temporarily rate-limited upstream. Please retry shortly..."
        )
    out = parse_upstream_rate_limit(_Err())
    assert out is not None
    assert "qwen/qwen3-next-80b-a3b-instruct:free" in out
    assert "rate limit" in out.lower()
    assert "openrouter.ai" in out  # actionable link


def test_parse_upstream_rate_limit_generic_phrase():
    """Fallback when the message has the phrase but no model name."""
    class _Err:
        message = "Some upstream provider is rate-limited upstream"
    out = parse_upstream_rate_limit(_Err())
    assert out is not None
    assert "rate limit" in out.lower()


def test_parse_upstream_rate_limit_no_match():
    class _Err:
        message = "Account has exceeded daily quota"
    assert parse_upstream_rate_limit(_Err()) is None


@pytest.mark.asyncio
async def test_chat_returns_clear_message_on_upstream_rate_limit(dispatcher, tmp_path):
    """RateLimitError carrying upstream model name → actionable message,
    not the opaque 'Errore temporaneo'."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    # Use a real OpenRouter-shaped exception body so the runner sees the
    # provider-specific message inside the standard RateLimitError.
    err = _openai.RateLimitError(
        message=(
            "Error code: 429 - {'error': {'message': 'Provider returned error', "
            "'metadata': {'raw': 'qwen/qwen3-next-80b-a3b-instruct:free is "
            "temporarily rate-limited upstream...'}}}"
        ),
        response=MagicMock(),
        body=None,
    )
    runner._client.chat.completions.create = AsyncMock(side_effect=err)
    with pytest.raises(RunnerBackendError) as exc_info:
        await runner.chat(user_message="hi", model="qwen/qwen3-next-80b-a3b-instruct:free")
    out = exc_info.value.friendly_message
    assert "qwen/qwen3-next-80b-a3b-instruct:free" in out
    assert "Errore temporaneo" not in out


@pytest.mark.asyncio
async def test_simple_chat_circuit_breaker_skips_dead_backend(dispatcher, tmp_path):
    """After N consecutive connection failures the breaker opens and further
    calls skip the network — stops a dead backend (stale Ollama tunnel) from
    flooding the log once per classify_entities call."""
    from hiris.app.backends.openai_compat_runner import _CIRCUIT_THRESHOLD
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    create = AsyncMock(side_effect=httpx.ConnectError("name does not resolve"))
    runner._client.chat.completions.create = create

    for _ in range(_CIRCUIT_THRESHOLD + 10):
        assert await runner.simple_chat([{"role": "user", "content": "x"}]) == ""

    # Network was hit only until the breaker opened; later calls were skipped.
    assert create.call_count == _CIRCUIT_THRESHOLD
    assert runner._circuit_is_open()


@pytest.mark.asyncio
async def test_simple_chat_circuit_resets_on_success(dispatcher, tmp_path):
    """A success before the threshold resets the failure counter (no premature
    open, recovers cleanly)."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u2.json"),
    )
    ok = MagicMock()
    ok.choices = [MagicMock(message=MagicMock(content="hi"))]
    runner._client.chat.completions.create = AsyncMock(side_effect=[
        httpx.ConnectError("x"), httpx.ConnectError("x"), ok,
    ])

    assert await runner.simple_chat([{"role": "user", "content": "x"}]) == ""
    assert await runner.simple_chat([{"role": "user", "content": "x"}]) == ""
    assert await runner.simple_chat([{"role": "user", "content": "x"}]) == "hi"
    assert runner._conn_fail_count == 0
    assert not runner._circuit_is_open()


# ---------------------------------------------------------------------------
# Regression: runner-declared cloud egress signal (second-brain Phase 2).
# OpenRouterRunner strips its prefix before the model string reaches dispatch,
# so backend_is_cloud(model) would misclassify the egress as local. The runner
# now declares _is_cloud directly at construction time.
# ---------------------------------------------------------------------------

def test_openai_compat_runner_ollama_is_not_cloud(dispatcher, tmp_path):
    """Ollama runner (fixed_model set) must declare _is_cloud=False."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        dispatcher=dispatcher,
        fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._is_cloud is False


def test_openai_compat_runner_cloud_is_cloud(dispatcher, tmp_path):
    """OpenAI cloud runner (no fixed_model) must declare _is_cloud=True."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._is_cloud is True


def test_openrouter_runner_is_cloud(tmp_path):
    """OpenRouterRunner must always declare _is_cloud=True (US cloud proxy)."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
        dispatcher=MagicMock(),
        usage_path=str(tmp_path / "u.json"),
    )
    assert runner._is_cloud is True


@pytest.mark.asyncio
async def test_chat_length_finish_returns_truncation_notice(dispatcher, tmp_path):
    """finish_reason='length' (OpenAI's max_tokens) must surface a truncation
    notice, not a misleading partial preamble with nothing executed."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    msg = MagicMock()
    msg.content = "Ora creo la dashboard!"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="length", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    result = await runner.chat(user_message="crea dashboard", model="gpt-4o")
    assert _TRUNCATION_NOTICE in result
    assert result.startswith("Ora creo la dashboard!")


# ---------------------------------------------------------------------------
# review M3/#1: chat_stream() never checked finish_reason=='length', so a
# truncated streaming response reached the client with NO warning, while the
# non-streaming chat() above DOES surface _TRUNCATION_NOTICE.
# ---------------------------------------------------------------------------

class _FakeStream:
    """Minimal async-iterable stand-in for the OpenAI SDK's streaming response
    (mirrors tests/test_stream_otp_redaction.py's helper)."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            yield c


def _stream_chunk(content=None, finish_reason=None):
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


@pytest.mark.asyncio
async def test_chat_stream_length_finish_yields_truncation_notice(dispatcher, tmp_path):
    """finish_reason='length' on the streaming path must surface the same
    truncation notice as chat(), not silently end the SSE stream."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False

    stream = _FakeStream([
        _stream_chunk(content="Ora creo la dashboard!"),
        _stream_chunk(finish_reason="length"),
    ])
    runner._client.chat.completions.create = AsyncMock(return_value=stream)

    lines = [line async for line in runner.chat_stream(
        user_message="crea dashboard", model="gpt-4o",
    )]
    # SSE lines are 'data: {json}\n\n' -- json.dumps() escapes non-ASCII (the
    # ⚠️ emoji etc.), so reconstruct the streamed text from the parsed
    # payloads rather than substring-searching the raw (escaped) SSE text.
    streamed_text = "".join(
        json.loads(line[len("data: "):])["text"]
        for line in lines
        if '"type": "token"' in line
    )
    assert _TRUNCATION_NOTICE in streamed_text


@pytest.mark.asyncio
async def test_chat_stream_normal_stop_has_no_truncation_notice(dispatcher, tmp_path):
    """Sanity: a normal finish_reason='stop' must NOT emit the notice."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False

    stream = _FakeStream([
        _stream_chunk(content="Tutto ok."),
        _stream_chunk(finish_reason="stop"),
    ])
    runner._client.chat.completions.create = AsyncMock(return_value=stream)

    lines = [line async for line in runner.chat_stream(
        user_message="come stiamo", model="gpt-4o",
    )]
    full_output = "\n".join(lines)
    assert _TRUNCATION_NOTICE not in full_output


# ---------------------------------------------------------------------------
# review M3/#2: the connection-failure circuit breaker guarded simple_chat()
# only. The agentic chat()/chat_stream() loop never checked/tripped it, so a
# dead Ollama endpoint was retried at full timeout every turn instead of
# failing fast like simple_chat() already does.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_short_circuits_when_breaker_open(dispatcher, tmp_path):
    """chat() must consult the circuit breaker and fail fast (no network
    call) when it's open, instead of hammering a dead endpoint at full
    timeout on every turn."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    runner._circuit_open_until = time.monotonic() + 60
    create = AsyncMock()
    runner._client.chat.completions.create = create

    with pytest.raises(RunnerBackendError):
        await runner.chat(user_message="ciao", model="llama3.1:8b")
    create.assert_not_called()


@pytest.mark.asyncio
async def test_chat_stream_short_circuits_when_breaker_open(dispatcher, tmp_path):
    """chat_stream() must consult the circuit breaker too, yielding an SSE
    error event instead of calling the network."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    runner._circuit_open_until = time.monotonic() + 60
    create = AsyncMock()
    runner._client.chat.completions.create = create

    lines = [line async for line in runner.chat_stream(
        user_message="ciao", model="llama3.1:8b",
    )]
    full_output = "\n".join(lines)
    assert '"type": "error"' in full_output
    create.assert_not_called()


@pytest.mark.asyncio
async def test_chat_trips_breaker_on_connection_error(dispatcher, tmp_path):
    """A connection-class failure inside chat()'s agentic loop must trip the
    same breaker simple_chat() uses -- today it only logs a generic API
    error and never calls _record_conn_failure()."""
    from hiris.app.backends.openai_compat_runner import _CIRCUIT_THRESHOLD
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        dispatcher=dispatcher, fixed_model="llama3.1:8b",
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    conn_err = _openai.APIConnectionError(request=MagicMock())
    runner._client.chat.completions.create = AsyncMock(side_effect=conn_err)

    for _ in range(_CIRCUIT_THRESHOLD):
        with pytest.raises(RunnerBackendError):
            await runner.chat(user_message="ciao", model="llama3.1:8b")

    assert runner._circuit_is_open()


@pytest.mark.asyncio
async def test_chat_healthy_backend_behavior_unchanged(dispatcher, tmp_path):
    """Sanity: with the breaker closed and a healthy backend, chat() behaves
    exactly as before (no regression from the new breaker check)."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        dispatcher=dispatcher,
        usage_path=str(tmp_path / "u.json"),
    )
    runner._dispatcher.has_memory = False
    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    out = await runner.chat(user_message="hi", model="gpt-4o")
    assert out == "ok"


# --- render_template e il perimetro delle entita' ---------------------------
# fetta E2 Task 8 ("escono i trentaquattro"): i sei test che vivevano qui
# (gemelli di quelli in tests/test_claude_runner.py, per chat() e
# chat_stream()) sono stati cancellati, non spostati -- stessa ragione del
# file gemello: RENDER_TEMPLATE_TOOL_DEF e' uscita da EVALUATION_TOOL_DEFS
# insieme al resto dei 34 (non nominata da EVALUATION_ONLY_TOOLS, esclusa di
# proposito), e la chat non offre piu' un catalogo da questo file
# (STRUMENTI_CONOSCENZA, casa/strumenti.py). Nessuna combinazione di
# allowed_tools/allowed_entities puo' piu' far comparire "render_template" in
# un catalogo che non lo contiene: tre dei sei test fallivano gia' per
# costruzione, gli altri tre erano diventati vacui.
