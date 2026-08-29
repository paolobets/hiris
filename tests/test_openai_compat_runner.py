"""Regression tests for OpenAICompatRunner construction.

The 0.8.7 → 0.8.8 release passed `total=` to `httpx.Timeout`, which is not a
valid kwarg (httpx uses `timeout` as positional or `connect/read/write/pool`).
This crashed startup with `TypeError: Timeout.__init__() got an unexpected
keyword argument 'total'` whenever an OpenAI key or Ollama URL was configured.
"""
import json
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import RunnerBackendError


def test_init_openai_cloud_does_not_raise(tmp_path):
    """Cloud variant (locale=False) must construct a valid httpx.Timeout."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)


def test_init_ollama_local_does_not_raise(tmp_path):
    """Ollama variant (locale=True) must construct a valid httpx.Timeout.

    Il numero NON viene piu' da `OLLAMA_REQUEST_TIMEOUT`: lo passa il
    chiamante, che lo legge dall'archivio (`ollama.timeout_s`) -- la stessa
    casa da cui la pagina Modelli lo mostra sul connettore. Erano due
    rappresentazioni dello stesso numero (invariante 1), e quella che l'utente
    poteva cambiare non era quella che il turno subiva.
    """
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
        timeout_s=90,
    )
    assert isinstance(runner._client.timeout, httpx.Timeout)
    assert runner._client.timeout.read == 90.0


# fetta E4 Task 6 ("un bot solo"): silenzio dichiarato e pinnato per
# usage.json's "per_agent" -- stessa mossa e stesso motivo del pin gemello in
# tests/test_claude_runner.py (vedi il suo commento per il perche').

# fetta «i consumi, per modello» (22/08/2026): qui vivevano i due test
# della persistenza di `usage.json` -- il silenzio dichiarato su `per_agent`
# di un'installazione precedente e la lettura-modifica-scrittura che non
# doveva perderlo. Escono col loro soggetto: `_load_usage`/`_save_usage` non
# esistono piu', il consumo ha una casa sola (`consumi/store.py`).
#
# Il fatto che difendevano -- «mai dati dell'utente rimossi in silenzio» --
# non esce con loro: i vecchi `usage_*.json` restano sul disco e vengono
# importati una volta sola. Lo pinna `tests/test_consumi_ancora.py`.


def test_circuit_open_message_names_local_backend(tmp_path):
    """Backlog #7 (local variant): Ollama keeps the 'backend locale' wording."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
    )
    assert runner._backend_noun == "Il backend locale"


def test_ollama_disables_sdk_retry(tmp_path):
    """Ollama runner must use max_retries=0 (fail-fast on hang)."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        locale=True, leggi_modello=lambda: "gemma4:e4b",
    )
    assert runner._client.max_retries == 0


def test_openai_cloud_keeps_default_retry(tmp_path):
    """Cloud variant keeps SDK default retry (2) — cloud network is reliable."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    assert runner._client.max_retries == 2


@pytest.mark.asyncio
async def test_ollama_chat_passes_think_false(tmp_path):
    """Ollama runner must inject extra_body={'think': False} on chat call."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        locale=True, leggi_modello=lambda: "gemma4:e4b",
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
async def test_openai_cloud_chat_omits_extra_body(tmp_path):
    """Cloud variant must NOT inject extra_body — keeps OpenAI semantics clean."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
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
async def test_chat_accepts_thinking_budget_kwarg_silently(tmp_path):
    """OpenAI-compat chat() must accept thinking_budget without raising."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
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
    TOOL_LEAK_USER_MSG,
    detect_leaked_tool_call,
)


def test_detect_leaked_tool_call_mistral_pattern():
    """Real-world Mistral-via-OpenRouter sample: tool name + Hebrew separator + JSON."""
    leaked = "get_ha_healthיׂ{\"sections\": [\"all\"]}"
    out = detect_leaked_tool_call(leaked, {"get_ha_health", "get_home_status"})
    assert out == "get_ha_health"


def test_detect_leaked_tool_call_vietnamese_separator():
    """Variant from logs: tool name + Vietnamese 'lớ' separator."""
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
async def test_chat_replaces_leaked_tool_call_with_user_msg(tmp_path):
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
    )
    msg = MagicMock()
    msg.content = "get_ha_healthיׂ{\"sections\": [\"all\"]}"
    msg.tool_calls = None
    choice = MagicMock(finish_reason="stop", message=msg)
    response = MagicMock(choices=[choice])
    response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
    runner._client.chat.completions.create = AsyncMock(return_value=response)

    finti_tool_def = [
        {"name": "get_ha_health", "description": "finto",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_home_status", "description": "finto",
         "input_schema": {"type": "object", "properties": {}}},
    ]
    out = await runner.chat(
        user_message="check health",
        model="mistralai/mistral-large",
        strumenti=finti_tool_def,
    )
    assert out == TOOL_LEAK_USER_MSG
    assert "get_ha_health" not in out  # No leak in returned text


@pytest.mark.asyncio
async def test_chat_passes_through_clean_text(tmp_path):
    """Sanity: a normal text response must not be replaced."""
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )
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
async def test_chat_retries_on_402_afford_message(tmp_path):
    """First call raises 402 with afford message, runner retries with clamp."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )

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
async def test_chat_returns_explicit_error_when_402_retry_also_fails(tmp_path):
    """If even the clamped retry hits 402 (zero credit), give explicit message."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )
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
async def test_chat_non_402_api_error_still_returns_generic_message(tmp_path):
    """Non-402 API errors must keep the existing generic-error behaviour."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )
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
async def test_chat_returns_clear_message_on_upstream_rate_limit(tmp_path):
    """RateLimitError carrying upstream model name → actionable message,
    not the opaque 'Errore temporaneo'."""
    import openai as _openai
    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-or-test",
    )
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
async def test_simple_chat_circuit_breaker_skips_dead_backend(tmp_path):
    """After N consecutive connection failures the breaker opens and further
    calls skip the network — stops a dead backend (stale Ollama tunnel) from
    flooding the log once per classify_entities call."""
    from hiris.app.backends.openai_compat_runner import _CIRCUIT_THRESHOLD
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
    )
    create = AsyncMock(side_effect=httpx.ConnectError("name does not resolve"))
    runner._client.chat.completions.create = create

    for _ in range(_CIRCUIT_THRESHOLD + 10):
        assert await runner.simple_chat([{"role": "user", "content": "x"}]) == ""

    # Network was hit only until the breaker opened; later calls were skipped.
    assert create.call_count == _CIRCUIT_THRESHOLD
    assert runner._circuit_is_open()


@pytest.mark.asyncio
async def test_simple_chat_circuit_resets_on_success(tmp_path):
    """A success before the threshold resets the failure counter (no premature
    open, recovers cleanly)."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
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

def test_openai_compat_runner_ollama_is_not_cloud(tmp_path):
    """Ollama runner (locale=True) must declare _is_cloud=False."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1",
        api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
    )
    assert runner._is_cloud is False


def test_openai_compat_runner_cloud_is_cloud(tmp_path):
    """OpenAI cloud runner (locale=False) must declare _is_cloud=True."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    assert runner._is_cloud is True


def test_openrouter_runner_is_cloud(tmp_path):
    """OpenRouterRunner must always declare _is_cloud=True (US cloud proxy)."""
    from hiris.app.backends.openrouter_runner import OpenRouterRunner
    runner = OpenRouterRunner(
        api_key="sk-or-test",
    )
    assert runner._is_cloud is True


@pytest.mark.asyncio
async def test_chat_length_finish_returns_truncation_notice(tmp_path):
    """finish_reason='length' (OpenAI's max_tokens) must surface a truncation
    notice, not a misleading partial preamble with nothing executed."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
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
# fetta "i riferimenti" (R4, Task 6): l'esaurimento delle iterazioni-
# strumenti (il modello chiede SEMPRE un tool, mai finish_reason='stop') era
# muto e in inglese -- "Max tool iterations reached.", zero log. Gemello del
# difetto chiuso in test_claude_runner.py per ClaudeRunner.chat(); stessa
# costante `_MAX_ITERATIONS_NOTICE`, importata da claude_runner.py (gerarchia
# gia' in un verso solo: questo modulo importa GIA' da li').
# ---------------------------------------------------------------------------

def _risposta_tool_call(nome: str, argomenti: str, tc_id: str):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = nome
    tc.function.arguments = argomenti
    choice = MagicMock(finish_reason="tool_calls")
    choice.message.content = None
    choice.message.tool_calls = [tc]
    resp = MagicMock(choices=[choice])
    resp.usage.prompt_tokens = 5
    resp.usage.completion_tokens = 2
    return resp


@pytest.mark.asyncio
async def test_chat_esaurimento_iterazioni_messaggio_italiano_e_log(tmp_path, caplog, monkeypatch):
    """Deve poter fallire (mutazioni eseguite a mano, task-6-report.md):
    (a) ripristinare `return "Max tool iterations reached."` fa cadere il
        primo assert; (b) togliere il `logger.warning` fa cadere il secondo.
    """
    from hiris.app.claude_runner import _MAX_ITERATIONS_NOTICE
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.MAX_TOOL_ITERATIONS", 3)

    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1", api_key="sk-test",
    )
    runner._client.chat.completions.create = AsyncMock(side_effect=[
        _risposta_tool_call("guarda", '{"area": "cucina"}', "tc-1"),
        _risposta_tool_call("guarda", '{"area": "salotto"}', "tc-2"),
        _risposta_tool_call("cerca", '{"testo": "termostato"}', "tc-3"),
    ])
    finto_dispatcher = MagicMock(dispatch=AsyncMock(return_value={"ok": True}))

    with caplog.at_level(logging.WARNING):
        result = await runner.chat(
            user_message="guarda ogni stanza", model="gpt-4o", dispatcher=finto_dispatcher,
        )

    assert result == _MAX_ITERATIONS_NOTICE
    assert "Max tool iterations reached." not in result
    assert runner._client.chat.completions.create.call_count == 3

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("3" in m and "guarda" in m and "cerca" in m for m in warning_messages), (
        f"nessun warning col conto delle iterazioni e i nomi degli strumenti: {warning_messages}"
    )
    assert not any("cucina" in m or "salotto" in m or "termostato" in m for m in warning_messages)


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
async def test_chat_stream_length_finish_yields_truncation_notice(tmp_path):
    """finish_reason='length' on the streaming path must surface the same
    truncation notice as chat(), not silently end the SSE stream."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )

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
async def test_chat_stream_normal_stop_has_no_truncation_notice(tmp_path):
    """Sanity: a normal finish_reason='stop' must NOT emit the notice."""
    from hiris.app.claude_runner import _TRUNCATION_NOTICE
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )

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
# fetta "i riferimenti" (R4, Task 6): il ramo streaming era il peggiore dei
# due -- il generatore usciva senza evento d'errore ne' testo, un "done"
# muto (nessun `break` nel `for` quando il modello chiede SEMPRE un tool: il
# `for _ in range(max_iter)` si esaurisce e cade dritto sull'ultimo `yield`
# "done", l'unico della funzione). Ora un `for...else` sul loop -- fires solo
# quando il loop non ha mai incontrato il `break` che segna una risposta
# testuale finale -- emette l'evento nella STESSA forma con cui questo
# generatore segnala gia' gli altri errori (circuito aperto, rate limit,
# errore API: `{"type": "error", "message": ...}` seguito da un `return` che
# chiude lo stream senza il "done" finale), invece di inventarne una nuova.
# ---------------------------------------------------------------------------

def _stream_tc_delta(index, *, id_=None, name=None, arguments=None):
    d = MagicMock()
    d.index = index
    d.id = id_
    d.function = MagicMock()
    d.function.name = name
    d.function.arguments = arguments
    return d


def _stream_chunk_tool(tc_deltas, finish_reason=None):
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = tc_deltas
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


@pytest.mark.asyncio
async def test_chat_stream_esaurimento_iterazioni_emette_errore_non_done_muto(
    tmp_path, caplog, monkeypatch
):
    """Deve poter fallire (mutazioni eseguite a mano, task-6-report.md): (c)
    togliendo il `for...else` (tornando al solo `yield` "done" finale di
    prima) lo stream torna muto e il primo assert cade."""
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.MAX_TOOL_ITERATIONS", 3)

    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )

    def _stream_sempre_tool(nome, argomenti, tc_id):
        tc = _stream_tc_delta(0, id_=tc_id, name=nome, arguments=argomenti)
        return _FakeStream([_stream_chunk_tool([tc], finish_reason="tool_calls")])

    runner._client.chat.completions.create = AsyncMock(side_effect=[
        _stream_sempre_tool("guarda", '{"area": "cucina"}', "tc-1"),
        _stream_sempre_tool("guarda", '{"area": "salotto"}', "tc-2"),
        _stream_sempre_tool("cerca", '{"testo": "termostato"}', "tc-3"),
    ])
    finto_dispatcher = MagicMock(dispatch=AsyncMock(return_value={"ok": True}))

    with caplog.at_level(logging.WARNING):
        lines = [line async for line in runner.chat_stream(
            user_message="guarda ogni stanza", model="gpt-4o", dispatcher=finto_dispatcher,
        )]

    assert runner._client.chat.completions.create.call_count == 3

    events = [json.loads(line[len("data: "):]) for line in lines if line.startswith("data: ")]
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1, f"atteso un solo evento 'error', trovati: {events}"
    from hiris.app.claude_runner import _MAX_ITERATIONS_NOTICE
    assert error_events[0]["message"] == _MAX_ITERATIONS_NOTICE
    # mai il "done" muto: lo stream si ferma sull'evento che spiega -- non
    # aggiunge un "done" senza spiegazione dopo.
    assert not any(e.get("type") == "done" for e in events)

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("3" in m and "guarda" in m and "cerca" in m for m in warning_messages), (
        f"nessun warning col conto delle iterazioni e i nomi degli strumenti: {warning_messages}"
    )
    assert not any("cucina" in m or "salotto" in m or "termostato" in m for m in warning_messages)


# ---------------------------------------------------------------------------
# review M3/#2: the connection-failure circuit breaker guarded simple_chat()
# only. The agentic chat()/chat_stream() loop never checked/tripped it, so a
# dead Ollama endpoint was retried at full timeout every turn instead of
# failing fast like simple_chat() already does.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_short_circuits_when_breaker_open(tmp_path):
    """chat() must consult the circuit breaker and fail fast (no network
    call) when it's open, instead of hammering a dead endpoint at full
    timeout on every turn."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
    )
    runner._circuit_open_until = time.monotonic() + 60
    create = AsyncMock()
    runner._client.chat.completions.create = create

    with pytest.raises(RunnerBackendError):
        await runner.chat(user_message="ciao", model="llama3.1:8b")
    create.assert_not_called()


@pytest.mark.asyncio
async def test_chat_stream_short_circuits_when_breaker_open(tmp_path):
    """chat_stream() must consult the circuit breaker too, yielding an SSE
    error event instead of calling the network."""
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
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
async def test_chat_trips_breaker_on_connection_error(tmp_path):
    """A connection-class failure inside chat()'s agentic loop must trip the
    same breaker simple_chat() uses -- today it only logs a generic API
    error and never calls _record_conn_failure()."""
    import openai as _openai

    from hiris.app.backends.openai_compat_runner import _CIRCUIT_THRESHOLD
    runner = OpenAICompatRunner(
        base_url="http://192.168.1.50:11434/v1", api_key="ollama",
        locale=True, leggi_modello=lambda: "llama3.1:8b",
    )
    conn_err = _openai.APIConnectionError(request=MagicMock())
    runner._client.chat.completions.create = AsyncMock(side_effect=conn_err)

    for _ in range(_CIRCUIT_THRESHOLD):
        with pytest.raises(RunnerBackendError):
            await runner.chat(user_message="ciao", model="llama3.1:8b")

    assert runner._circuit_is_open()


@pytest.mark.asyncio
async def test_chat_healthy_backend_behavior_unchanged(tmp_path):
    """Sanity: with the breaker closed and a healthy backend, chat() behaves
    exactly as before (no regression from the new breaker check)."""
    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
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


# ---------------------------------------------------------------------------
# fetta E5 Task 2, fix round 1 (I-2): il silenzio su thinking_budget si chiude
# ---------------------------------------------------------------------------

def test_thinking_budget_ignorato_lo_dice_nel_log(caplog):
    """Prima di questo fix le due `del thinking_budget` di questo runner erano
    MUTE, col commento «no warning: legitimately unused» -- vero finche' quel
    valore si poteva cambiare solo scrivendo a mano il JSON in /data. Dal Task
    2 della fetta E5 l'utente lo imposta dalla pagina, legge «Salvato», e su
    OpenAI/OpenRouter/Ollama non succedeva niente e nessuno lo diceva."""
    from hiris.app.backends.openai_compat_runner import avvisa_thinking_ignorato

    with caplog.at_level("WARNING"):
        avvisa_thinking_ignorato("Il backend locale", 8000)
    detto = " ".join(r.getMessage() for r in caplog.records)
    assert "thinking_budget=8000" in detto, (
        "il valore scartato va detto, non genericamente 'ignorato'"
    )
    assert "NON viene applicato" in detto
    assert "Il backend locale" in detto
    assert "resta salvata" in detto, "deve dire che l'impostazione risulta salvata"


def test_thinking_budget_a_zero_non_dice_niente(caplog):
    """A 0 non c'e' niente da dichiarare: e' il default, e un warning per turno
    su ogni installazione sarebbe rumore che insegna a ignorare i log."""
    from hiris.app.backends.openai_compat_runner import avvisa_thinking_ignorato

    with caplog.at_level("WARNING"):
        avvisa_thinking_ignorato("Il servizio AI", 0)
    assert not [r for r in caplog.records if "thinking_budget" in r.getMessage()]


def test_entrambi_i_percorsi_del_runner_avvisano():
    """`chat()` e `chat_stream()` scartano entrambi il parametro: il ramo SSE
    serve la card Lovelace, dove il silenzio sarebbe identico. Guardia sul
    sorgente perche' esercitare i due loop agentici richiederebbe un finto
    server OpenAI completo -- il comportamento del messaggio e' gia' coperto
    dai due test sopra."""
    import ast
    import inspect

    from hiris.app.backends import openai_compat_runner as modulo

    albero = ast.parse(inspect.getsource(modulo))
    chiamate = [
        n for n in ast.walk(albero)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "avvisa_thinking_ignorato"
    ]
    assert len(chiamate) == 2, (
        "ogni punto che scarta thinking_budget deve dichiararlo: attesi 2 "
        f"(chat, chat_stream), trovati {len(chiamate)}"
    )
    scarti = [
        n for n in ast.walk(albero)
        if isinstance(n, ast.Delete)
        and any(isinstance(t, ast.Name) and t.id == "thinking_budget" for t in n.targets)
    ]
    assert len(scarti) == len(chiamate), "uno scarto muto e' rientrato"


# ---------------------------------------------------------------------------
# Il circuito, e cio' che l'errore porta con se' (Task 11)
# ---------------------------------------------------------------------------


def test_il_circuito_resta_aperto_per_tutto_il_raffreddamento(monkeypatch):
    """Una finta che si richiude appena una chiamata riesce nasconderebbe il
    comportamento vero: finche' il circuito e' aperto la rete NON viene toccata,
    quindi non c'e' nessuna chiamata che possa richiuderlo."""
    orologio = [100.0]
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.time.monotonic",
                        lambda: orologio[0])
    r = OpenAICompatRunner(base_url="http://x/v1", api_key="k")
    for _ in range(3):
        r._record_conn_failure()
    assert r.stato_circuito() == 60.0
    orologio[0] += 59
    assert r.stato_circuito() == 1.0, "a 59 secondi il circuito e' ancora aperto"
    orologio[0] += 2
    assert r.stato_circuito() == 0.0


def test_sotto_la_soglia_il_circuito_non_si_apre(monkeypatch):
    """Due errori di connessione non bastano: la soglia e' tre. Un
    `stato_circuito` che restituisse un numero prima della soglia farebbe
    dire alla pagina «lo sto saltando» di un provider che il prodotto sta
    ancora interrogando -- una parola piu' larga del fatto."""
    orologio = [100.0]
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.time.monotonic",
                        lambda: orologio[0])
    r = OpenAICompatRunner(base_url="http://x/v1", api_key="k")
    r._record_conn_failure()
    r._record_conn_failure()
    assert r.stato_circuito() == 0.0


def test_lo_stato_del_circuito_e_letto_da_una_parte_sola(monkeypatch):
    """`_circuit_is_open` DERIVA da `stato_circuito`: e' il confronto
    sull'orologio scritto una volta. Due confronti sullo stesso numero
    sarebbero due rappresentazioni della stessa cosa, e la rotta che la
    espone potrebbe dire il contrario del ramo che salta la rete."""
    orologio = [100.0]
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.time.monotonic",
                        lambda: orologio[0])
    r = OpenAICompatRunner(base_url="http://x/v1", api_key="k")
    for _ in range(3):
        r._record_conn_failure()
    for salto in (0, 59, 2):
        orologio[0] += salto
        assert r._circuit_is_open() == (r.stato_circuito() > 0.0)
    assert r._circuit_is_open() is False


@pytest.mark.asyncio
async def test_il_circuito_aperto_rifiuta_dicendo_che_non_ha_interrogato(monkeypatch):
    """Il circuito aperto e' «non l'ho interrogato», non «errore temporaneo».
    L'eccezione porta la famiglia `irraggiungibile` e NESSUN codice, perche'
    nessuna risposta e' arrivata da cui prenderlo: e' cosi' che il registro
    puo' scrivere «non risponde all'indirizzo» invece di inventare una causa.
    """
    orologio = [100.0]
    monkeypatch.setattr("hiris.app.backends.openai_compat_runner.time.monotonic",
                        lambda: orologio[0])
    r = OpenAICompatRunner(base_url="http://x/v1", api_key="k")
    for _ in range(3):
        r._record_conn_failure()

    with pytest.raises(RunnerBackendError) as info:
        await r.chat(user_message="ciao")
    assert info.value.famiglia == "irraggiungibile"
    assert info.value.codice is None
    # La frase per l'utente NON cambia: questa fetta non tocca cio' che si
    # legge in chat.
    assert "circuito aperto" in info.value.friendly_message


@pytest.mark.asyncio
async def test_un_404_del_provider_arriva_al_router_come_famiglia_modello(tmp_path):
    """Il punto in cui il codice smetteva di esistere. `chat()` collassava OGNI
    `openai.APIError` in «Errore temporaneo del servizio AI», quindi «il
    modello che hai scelto non esiste piu'» e «i crediti sono finiti» erano la
    stessa identica riga -- e nessuna delle due arrivava alla pagina."""
    import openai

    runner = OpenAICompatRunner(
        base_url="https://api.openai.com/v1", api_key="sk-test")

    class _Sparito(openai.APIError):
        def __init__(self):
            Exception.__init__(self, "model_not_found")
            self.status_code = 404
            self.body = None

    runner._client.chat.completions.create = AsyncMock(side_effect=_Sparito())
    with pytest.raises(RunnerBackendError) as info:
        await runner.chat(user_message="hi", model="gpt-4o")

    assert info.value.famiglia == "modello" and info.value.codice == 404
    assert info.value.friendly_message == (
        "Errore temporaneo del servizio AI. Riprova tra poco."
    )


@pytest.mark.asyncio
async def test_un_402_di_openrouter_arriva_al_router_come_credenziale(tmp_path):
    """OpenRouter risponde 402 quando il credito e' finito: e' il gemello del
    400 di Anthropic, e la pagina deve poterlo dire con le stesse parole."""
    import openai

    runner = OpenAICompatRunner(
        base_url="https://openrouter.ai/api/v1", api_key="sk-or-test")

    class _Credito(openai.APIError):
        def __init__(self):
            Exception.__init__(self, "insufficient credits")
            self.status_code = 402
            self.body = None

    runner._client.chat.completions.create = AsyncMock(side_effect=_Credito())
    with pytest.raises(RunnerBackendError) as info:
        await runner.chat(user_message="hi", model="gpt-4o")

    assert info.value.famiglia == "credenziale" and info.value.codice == 402


def test_il_codice_di_un_errore_d_api_si_legge_e_quello_di_una_connessione_no():
    """`_codice_di` e' il punto in cui il numero smette di andare perso.
    `APIConnectionError` non ne ha uno -- una risposta non c'e' mai stata --
    e il `None` di quel caso e' il fatto, non un valore di comodo."""
    from hiris.app.backends.openai_compat_runner import _codice_di

    class _Api(Exception):
        status_code = 402

    class _Conn(Exception):
        status_code = None

    class _Strano(Exception):
        # Un provider dietro un proxy che mette una STRINGA li' dentro. Non e'
        # teorico: `status_code` non e' garantito da nessun contratto, e la
        # frase della pagina lo formatta con `%d`. Senza la guardia, la riga
        # di stato di un provider farebbe esplodere il GET dell'intera pagina
        # Modelli -- il registro nato per raccontare i guasti che ne produce
        # uno nuovo.
        status_code = "402"

    assert _codice_di(_Api()) == 402
    assert _codice_di(_Conn()) is None
    assert _codice_di(Exception("nudo")) is None
    assert _codice_di(_Strano()) is None


# --- un messaggio non afferma cio' che non sa --------------------------------

def test_il_rate_limit_senza_nome_NON_inventa_che_il_modello_e_gratuito():
    """Visto dal vivo il 21/08/2026 sull'installazione del proprietario: il suo
    modello OpenRouter era `mistralai/mistral-large`, a PAGAMENTO, e HIRIS
    rispondeva «il modello :free selezionato ha esaurito il rate limit».

    Il ramo esiste per il caso in cui il provider dice «rate-limited upstream»
    senza nominare il modello. Non sapendo QUALE sia, non puo' nemmeno sapere
    che sia gratuito -- e affermarlo manda a cercare un problema che non c'e',
    esattamente come la diagnosi inventata di `azione/porta.py` mando' il
    proprietario a cercare un guasto di comunicazione inesistente."""
    from hiris.app.backends.openai_compat_runner import parse_upstream_rate_limit

    class _Exc(Exception):
        message = "Provider returned error: temporarily rate-limited upstream"

    messaggio = parse_upstream_rate_limit(_Exc())

    assert messaggio, "il caso va comunque riconosciuto e spiegato"
    assert ":free" not in messaggio, (
        "non sappiamo quale modello sia: non possiamo dire che sia gratuito")
    assert "rate limit" in messaggio.lower()


def test_quando_il_provider_NOMINA_il_modello_gratuito_lo_si_dice():
    """L'altra meta': quando il nome c'e', si usa quello. Il ramo che sa non
    va sacrificato per riparare il ramo che non sa."""
    from hiris.app.backends.openai_compat_runner import parse_upstream_rate_limit

    class _Exc(Exception):
        message = ("meta-llama/llama-3.3-70b-instruct:free is temporarily "
                   "rate-limited upstream")

    messaggio = parse_upstream_rate_limit(_Exc())

    assert "meta-llama/llama-3.3-70b-instruct:free" in messaggio
