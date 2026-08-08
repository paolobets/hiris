"""fetta E2 Task 7 ("esce il dispatcher"): this file used to exercise
ClaudeRunner's tool-dispatch loop through a REAL `ToolDispatcher` -- both to
prove the loop mechanic itself (parse tool_use -> dispatch -> tool_result)
AND, for a chunk of tests, to prove ToolDispatcher's OWN routing/gating
(allowed_entities/allowed_services filtering, per-tool argument mapping to
HA service calls). `ToolDispatcher` is gone; checked test by test rather
than assumed:

  - Tests whose assertion is about the LOOP MECHANIC or something else
    entirely (prompt injection, usage tracking, thinking params, cache
    control, model resolution, catalog membership, `last_tool_calls`
    bookkeeping which is appended unconditionally regardless of dispatch
    outcome) do not need a real dispatcher at all -- `dispatcher` now
    defaults to `None` on the runner and stays that way here.
  - Tests whose assertion was specifically about ToolDispatcher's OWN
    behaviour (`test_chat_handles_tool_use`, `test_allowed_entities_*`,
    `test_allowed_services_*`, `test_dispatch_get_area_entities`,
    `test_dispatch_get_calendar_events_*`, `test_dispatch_set_input_helper_*`,
    `test_set_input_helper_blocked_by_allowed_services`) died with it: with
    `self._dispatcher` now `None` by construction, the runner's fallback
    dispatch branch returns a generic "non disponibile" error for ANY tool
    (see claude_runner.py's `chat()`), so there is no surviving path that
    still applies `allowed_entities`/`allowed_services` filtering or maps
    tool arguments onto real HA service calls the way ToolDispatcher did --
    that specific 34-tool-catalog routing has no successor (it is explicitly
    OUT of scope for this fetta per .superpowers/sdd/progress.md: the
    Sentinel's EVALUATION_ONLY_TOOLS/run_with_actions catalog stays as CODE,
    not as working dispatch). Those tests were deleted, not moved.
  - The two concurrency/security tests near the end
    (`test_chat_concurrent_calls_do_not_leak_tool_calls`,
    `test_chat_concurrent_calls_do_not_leak_pseudonym_map`) needed a
    dispatcher-shaped stand-in to keep proving the runner's OWN ContextVar
    isolation under concurrency; see their own comments for what replaced
    `ToolDispatcher` there.
"""
import asyncio
import pytest
import anthropic
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.claude_runner import ClaudeRunner, RESTRICT_PROMPT, resolve_model, AUTO_MODEL_MAP


def _sys_text(system) -> str:
    """Flatten system blocks list to a plain string for assertions."""
    if isinstance(system, str):
        return system
    return "\n".join(b.get("text", "") for b in system if b.get("type") == "text")


@pytest.fixture
def mock_ha():
    ha = AsyncMock()
    ha.get_states = AsyncMock(return_value=[])
    ha.get_history = AsyncMock(return_value=[])
    ha.call_service = AsyncMock(return_value=True)
    ha.get_automations = AsyncMock(return_value=[])
    return ha


@pytest.fixture
def runner(mock_ha):
    # Nessun dispatcher di scorta (ToolDispatcher e' uscito): i test qui
    # sotto non ne hanno bisogno -- vedi il docstring del modulo.
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key")
    r._ha = mock_ha  # shortcut for tests
    return r


@pytest.mark.asyncio
async def test_chat_returns_text_response(runner):
    fake_message = MagicMock()
    fake_message.stop_reason = "end_turn"
    fake_message.content = [MagicMock(type="text", text="Hello from Claude")]

    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=fake_message)

        runner._client = instance
        result = await runner.chat("Ciao")

    assert result == "Hello from Claude"


@pytest.fixture
def restricted_runner(mock_ha):
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key")
    r._ha = mock_ha
    return r


@pytest.mark.asyncio
async def test_restrict_to_home_injects_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao", restrict_to_home=True)
    system_text = _sys_text(captured[0]["system"])
    assert "solo" in system_text.lower()
    assert RESTRICT_PROMPT in system_text


@pytest.mark.asyncio
async def test_restrict_to_home_false_does_not_inject(runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Prompt originale", restrict_to_home=False)
    system_text = _sys_text(captured[0]["system"])
    assert "Prompt originale" in system_text
    assert RESTRICT_PROMPT not in system_text


def test_get_area_entities_in_all_tool_defs():
    from hiris.app.claude_runner import EVALUATION_TOOL_DEFS
    names = [t["name"] for t in EVALUATION_TOOL_DEFS]
    assert "get_area_entities" in names


@pytest.mark.asyncio
async def test_restrict_to_home_appends_to_existing_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao", system_prompt="Sei un agente energia.", restrict_to_home=True)
    system_text = _sys_text(captured[0]["system"])
    assert "agente energia" in system_text
    assert RESTRICT_PROMPT in system_text


def test_resolve_model_auto_chat_returns_sonnet():
    assert resolve_model("auto", "chat") == "claude-sonnet-4-6"


def test_resolve_model_auto_agent_returns_haiku():
    assert resolve_model("auto", "agent") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_overrides_auto():
    assert resolve_model("claude-sonnet-4-6", "agent") == "claude-sonnet-4-6"


def test_resolve_model_auto_unknown_type_defaults_to_sonnet():
    assert resolve_model("auto", "unknown_type") == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_chat_uses_resolved_model_for_agent(runner):
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 10
    success.usage.output_tokens = 5
    runner._client.messages.create = AsyncMock(return_value=success)
    await runner.chat("Test", model="auto", agent_type="agent")
    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_rate_limit_retries_once_and_succeeds(runner):
    """_call_api retries on 429 and succeeds on second attempt."""
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise anthropic.APIStatusError(
                "rate limited",
                response=MagicMock(status_code=429),
                body={},
            )
        return success

    with patch.object(runner._client.messages, "create", side_effect=fake_create), \
         patch("hiris.app.claude_runner.asyncio.sleep", new_callable=AsyncMock):
        result = await runner._call_api(
            model="claude-sonnet-4-6", max_tokens=100, messages=[]
        )

    assert result is success
    assert call_count == 2
    assert runner.total_rate_limit_errors == 1


@pytest.mark.asyncio
async def test_rate_limit_exhausts_retries_raises(runner):
    """_call_api raises after MAX_RETRIES 429 errors."""
    from hiris.app.claude_runner import MAX_RETRIES

    call_count = 0

    async def always_rate_limit(**kwargs):
        nonlocal call_count
        call_count += 1
        raise anthropic.APIStatusError(
            "rate limited",
            response=MagicMock(status_code=429),
            body={},
        )

    with patch.object(runner._client.messages, "create", side_effect=always_rate_limit), \
         patch("hiris.app.claude_runner.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(anthropic.APIStatusError):
            await runner._call_api(
                model="claude-sonnet-4-6", max_tokens=100, messages=[]
            )

    assert runner.total_rate_limit_errors == MAX_RETRIES
    assert call_count == MAX_RETRIES + 1


@pytest.mark.asyncio
async def test_require_confirmation_injects_prompt(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Base", require_confirmation=True)
    system_text = _sys_text(captured[0]["system"])
    assert REQUIRE_CONFIRMATION_PROMPT in system_text
    assert "Base" in system_text


@pytest.mark.asyncio
async def test_require_confirmation_false_does_not_inject(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Base", require_confirmation=False)
    system_used = captured[0]["system"]
    assert REQUIRE_CONFIRMATION_PROMPT not in system_used


@pytest.mark.asyncio
async def test_require_confirmation_combines_with_restrict(runner):
    from hiris.app.claude_runner import REQUIRE_CONFIRMATION_PROMPT, RESTRICT_PROMPT
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage.input_tokens = 5
        m.usage.output_tokens = 2
        return m

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Base", restrict_to_home=True, require_confirmation=True)
    system_used = captured[0]["system"]
    system_text = _sys_text(system_used)
    assert "Base" in system_text
    assert RESTRICT_PROMPT in system_text
    assert REQUIRE_CONFIRMATION_PROMPT in system_text
    block_texts = [b["text"] for b in system_used if b.get("type") == "text"]
    idx_restrict = next(i for i, t in enumerate(block_texts) if RESTRICT_PROMPT in t)
    idx_confirm = next(i for i, t in enumerate(block_texts) if REQUIRE_CONFIRMATION_PROMPT in t)
    assert idx_restrict < idx_confirm


@pytest.mark.asyncio
async def test_run_with_actions_is_plain_agentic_loop():
    """Slice 5: run_with_actions no longer injects VALUTAZIONE/AZIONI
    instructions into the system prompt — it passes it through unmodified
    and returns whatever text the model produced (plus a best-effort
    structured dict, normally empty since nothing asks for that block)."""
    from unittest.mock import AsyncMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner.__new__(ClaudeRunner)
    runner.chat = AsyncMock(return_value="Tutto OK, nessuna anomalia rilevata.")

    text, structured = await runner.run_with_actions(
        user_message="test",
        system_prompt="base system",
    )

    assert text == "Tutto OK, nessuna anomalia rilevata."
    assert structured["valutazione"] is None
    assert structured["azioni"] == []
    call_kwargs = runner.chat.call_args.kwargs
    # No more prompt augmentation — the system prompt passes through as-is.
    assert call_kwargs["system_prompt"] == "base system"
    assert "VALUTAZIONE:" not in call_kwargs["system_prompt"]
    assert "AZIONI:" not in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_run_with_actions_restricts_to_evaluation_only_tools():
    """The Sentinella relies on run_with_actions never exposing actuation
    tools — verify the eval_tools restriction (EVALUATION_ONLY_TOOLS ∩
    allowed_tools) still applies post-simplification."""
    from unittest.mock import AsyncMock
    from hiris.app.claude_runner import ClaudeRunner, EVALUATION_ONLY_TOOLS

    runner = ClaudeRunner.__new__(ClaudeRunner)
    runner.chat = AsyncMock(return_value="ok")

    await runner.run_with_actions(
        user_message="test",
        system_prompt="base system",
        allowed_tools=[],
    )

    call_kwargs = runner.chat.call_args.kwargs
    assert set(call_kwargs["allowed_tools"]) == set(EVALUATION_ONLY_TOOLS)


def test_empty_allowed_tools_does_not_narrow_evaluation_set():
    """allowed_tools=[] e' falsy: NON restringe. Il ragionatore riceve tutti
    gli EVALUATION_ONLY_TOOLS. L'invariante e' che quel set esclude i tool
    che attuano -- non che i tool siano zero."""
    from hiris.app.claude_runner import EVALUATION_ONLY_TOOLS
    for actuating in ("call_ha_service", "send_notification", "trigger_automation",
                      "toggle_automation", "http_request"):
        assert actuating not in EVALUATION_ONLY_TOOLS
    assert "create_task" in EVALUATION_ONLY_TOOLS   # la capacita' c'e': documentala


def test_resolve_model_auto_agent_returns_haiku():
    assert resolve_model("auto", "agent") == "claude-haiku-4-5-20251001"


def test_get_chatbot_usage_returns_zeros_for_unknown_agent():
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner
    runner = ClaudeRunner(
        api_key="test",
        usage_path="",
    )
    usage = runner.get_chatbot_usage("agent-xyz")
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["cost_usd"] == 0.0
    assert usage["last_run"] is None


def test_per_chatbot_usage_accumulates_after_chat():
    """chat() with agent_id accumulates tokens in _per_chatbot_usage."""
    import asyncio
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test",
        usage_path="",
    )

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(type="text", text="ok")]
    mock_response.usage = MagicMock(
        input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
    )

    async def fake_call(**kwargs):
        return mock_response

    runner._call_api = fake_call

    asyncio.run(runner.chat(user_message="hello", chatbot_id="agent-abc"))

    usage = runner.get_chatbot_usage("agent-abc")
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["requests"] == 1
    assert usage["cost_usd"] > 0
    assert usage["last_run"] is not None


def test_reset_chatbot_usage_clears_counters():
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test",
        usage_path="",
    )
    runner._per_chatbot_usage["agent-abc"] = {
        "input_tokens": 500, "output_tokens": 200,
        "requests": 3, "cost_usd": 0.002, "last_run": "2026-01-01T00:00:00Z",
    }
    runner.reset_chatbot_usage("agent-abc")
    usage = runner.get_chatbot_usage("agent-abc")
    assert usage["input_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["last_run"] is None


def test_per_chatbot_usage_persists_and_reloads(tmp_path):
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    usage_file = str(tmp_path / "usage.json")
    runner = ClaudeRunner(
        api_key="test",
        usage_path=usage_file,
    )
    runner._per_chatbot_usage["agent-persist"] = {
        "input_tokens": 1000, "output_tokens": 400,
        "requests": 5, "cost_usd": 0.005, "last_run": "2026-04-01T10:00:00Z",
    }
    runner._save_usage()

    runner2 = ClaudeRunner(
        api_key="test",
        usage_path=usage_file,
    )
    usage = runner2.get_chatbot_usage("agent-persist")
    assert usage["input_tokens"] == 1000
    assert usage["requests"] == 5


@pytest.mark.asyncio
async def test_simple_chat_returns_text(runner):
    fake_message = MagicMock()
    fake_message.content = [MagicMock(type="text", text='{"result": "ok"}')]
    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=fake_message)
        runner._client = instance
        result = await runner.simple_chat(
            [{"role": "user", "content": "classify"}],
            system="Classify entities",
        )
    assert result == '{"result": "ok"}'


def test_get_calendar_events_in_all_tool_defs():
    from hiris.app.claude_runner import EVALUATION_TOOL_DEFS
    names = [t["name"] for t in EVALUATION_TOOL_DEFS]
    assert "get_calendar_events" in names


# fetta E2 Task 8 ("escono i trentaquattro"): `test_set_input_helper_in_all_
# tool_defs` e' stato cancellato, non spostato -- `set_input_helper` ATTUA
# (scrive su un input helper di Home Assistant), quindi non fa parte di
# `EVALUATION_ONLY_TOOLS` per costruzione (lo stesso motivo per cui non ci
# sono `call_ha_service`/`trigger_automation`/`toggle_automation`/
# `http_request`, vedi test_empty_allowed_tools_does_not_narrow_evaluation_
# set sotto): il catalogo ridotto a EVALUATION_TOOL_DEFS non lo contiene piu',
# e nessun altro catalogo lo offre (la chat riceve i quattro strumenti di
# STRUMENTI_CONOSCENZA, casa/strumenti.py). Il soggetto -- SET_INPUT_HELPER_
# TOOL_DEF nel catalogo del runner -- non esiste piu' in nessun percorso.


# ---------------------------------------------------------------------------
# Extended Thinking - _build_thinking_param + chat() integration
# ---------------------------------------------------------------------------

def test_build_thinking_param_disabled_when_zero():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(0, "claude-sonnet-4-6", 4096) is None


def test_build_thinking_param_enabled_on_sonnet_4_6():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(2048, "claude-sonnet-4-6", 4096)
    assert out == {"type": "enabled", "budget_tokens": 2048}


def test_build_thinking_param_enabled_on_opus_4_7():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(2048, "claude-opus-4-7", 4096)
    assert out == {"type": "enabled", "budget_tokens": 2048}


def test_build_thinking_param_disabled_on_haiku():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(2048, "claude-haiku-4-5-20251001", 4096) is None


def test_build_thinking_param_disabled_below_anthropic_minimum():
    from hiris.app.claude_runner import _build_thinking_param
    assert _build_thinking_param(512, "claude-sonnet-4-6", 4096) is None


def test_build_thinking_param_clamps_when_geq_max_tokens():
    from hiris.app.claude_runner import _build_thinking_param
    out = _build_thinking_param(8000, "claude-sonnet-4-6", 4000)
    assert out == {"type": "enabled", "budget_tokens": 3999}


def test_build_thinking_param_returns_none_if_clamp_drops_below_minimum():
    from hiris.app.claude_runner import _build_thinking_param
    # max_tokens too small: even after clamp budget < 1024 -> disabled
    assert _build_thinking_param(2048, "claude-sonnet-4-6", 1024) is None


@pytest.mark.asyncio
async def test_chat_passes_thinking_param_when_capable(runner):
    """chat() with thinking_budget>0 on capable model passes thinking= to API."""
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", max_tokens=4096, thinking_budget=2048)
    kwargs = runner._client.messages.create.call_args.kwargs
    assert kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 2048}


@pytest.mark.asyncio
async def test_chat_no_thinking_param_when_disabled(runner):
    """chat() with thinking_budget=0 omits thinking= entirely."""
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", thinking_budget=0)
    kwargs = runner._client.messages.create.call_args.kwargs
    assert "thinking" not in kwargs


def _count_cache_breakpoints(kwargs: dict) -> int:
    """Count cache_control blocks across system, tools and message content."""
    def _count(blocks) -> int:
        if not isinstance(blocks, list):
            return 0
        return sum(1 for b in blocks if isinstance(b, dict) and b.get("cache_control"))
    n = _count(kwargs.get("system")) + _count(kwargs.get("tools"))
    for msg in kwargs.get("messages", []):
        n += _count(msg.get("content"))
    return n


@pytest.mark.asyncio
async def test_cache_control_within_limit_with_modifiers_and_history(runner):
    """Worst-case config must stay within Anthropic's hard cap of 4 cache_control.

    Regression for the v0.9.5 overflow: BASE + agent prompt + last modifier each
    carried their own breakpoint (3), which together with the tool-defs and the
    conversation-history breakpoints reached 5 on a follow-up turn and made the
    API return a 400 — surfaced to the user as the generic
    "Errore temporaneo del servizio AI" on the 2nd message of a chat.
    """
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage = MagicMock(input_tokens=5, output_tokens=2,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return m

    runner._client.messages.create = capture
    await runner.chat(
        "Domanda di follow-up",
        system_prompt="Prompt agente",
        context_str="## Contesto casa\nluce: accesa",
        conversation_history=[
            {"role": "user", "content": "prima domanda"},
            {"role": "assistant", "content": "prima risposta"},
        ],
        restrict_to_home=True,
        require_confirmation=True,
        response_mode="compact",
    )
    n = _count_cache_breakpoints(captured[0])
    assert n <= 4, f"too many cache_control breakpoints: {n}"


@pytest.mark.asyncio
async def test_cache_control_single_system_breakpoint(runner):
    """All stable system content shares ONE cumulative breakpoint, not one each."""
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        m = MagicMock()
        m.stop_reason = "end_turn"
        m.content = [MagicMock(type="text", text="ok")]
        m.usage = MagicMock(input_tokens=5, output_tokens=2,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return m

    runner._client.messages.create = capture
    await runner.chat(
        "Ciao",
        system_prompt="Prompt agente",
        restrict_to_home=True,
        require_confirmation=True,
    )
    system = captured[0]["system"]
    n_system = sum(1 for b in system if isinstance(b, dict) and b.get("cache_control"))
    assert n_system == 1


@pytest.mark.asyncio
async def test_chat_collects_thinking_blocks(runner):
    """Thinking blocks in response.content are captured in last_thinking_blocks."""
    thinking_block = MagicMock(type="thinking", thinking="step 1: check state\nstep 2: decide")
    text_block = MagicMock(type="text", text="ok")
    msg = MagicMock(stop_reason="end_turn", content=[thinking_block, text_block])
    msg.usage = MagicMock(input_tokens=10, output_tokens=5,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)
    runner._client.messages.create = AsyncMock(return_value=msg)
    await runner.chat("ciao", model="claude-sonnet-4-6", thinking_budget=2048)
    assert runner.last_thinking_blocks == ["step 1: check state\nstep 2: decide"]


@pytest.mark.asyncio
async def test_chat_populates_last_tool_calls_single_call(runner):
    """Baseline for 'single-call behavior unchanged' (review A/#3): a lone,
    non-overlapping chat() call must still populate last_tool_calls with its
    own tool call after switching from a plain instance attribute to the
    per-call ContextVar-backed descriptor."""
    tool_block = MagicMock(type="tool_use", id="tu_x", input={"ids": ["light.living"]})
    tool_block.name = "get_entity_states"
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="ok")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._ha.get_states = AsyncMock(return_value=[])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("ciao")
    assert runner.last_tool_calls == [{"tool": "get_entity_states", "input": {"ids": ["light.living"]}}]


@pytest.mark.asyncio
async def test_chat_concurrent_calls_do_not_leak_tool_calls(runner):
    """Two overlapping chat() calls on the SAME runner instance must not
    leak or wipe each other's tool_calls (review A/#3 concurrency fix).

    Before the ContextVar-based isolation, last_tool_calls was a single
    unlocked instance attribute: both calls reset it to [] at the start and
    appended to it after awaiting the (fake) API. Interleaving two calls —
    call B resets/appends while call A is still in flight — meant the SAME
    shared list ended up holding entries from BOTH calls, and a caller
    reading `runner.last_tool_calls` right after its own `await
    runner.chat(...)` could see the other call's tool inputs (or its own
    silently wiped). This test deterministically interleaves two calls via
    asyncio.gather + real awaits and fails on the pre-fix shared-attribute
    code; it passes once collection is isolated per asyncio Task.
    """

    def _usage():
        return MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def _tool_response(tool_name: str, entity_id: str):
        block = MagicMock(type="tool_use", id=f"id-{tool_name}", input={"entity_id": entity_id})
        block.name = tool_name
        return MagicMock(stop_reason="tool_use", content=[block], usage=_usage())

    def _end_response(text: str):
        block = MagicMock(type="text", text=text)
        return MagicMock(stop_reason="end_turn", content=[block], usage=_usage())

    async def fake_create(**kwargs):
        msgs = kwargs["messages"]
        is_call_a = msgs[0]["content"] == "call-A"
        first_iteration = len(msgs) == 1
        # call B is intentionally faster than call A so their two API
        # round-trips interleave deterministically (B's iter1 resolves
        # before A's iter1; B finishes entirely before A's iter2 finishes).
        await asyncio.sleep(0.02 if is_call_a else 0.01)
        if first_iteration:
            return _tool_response(
                "get_area_entities" if is_call_a else "get_home_status",
                "entity-A" if is_call_a else "entity-B",
            )
        return _end_response("done-A" if is_call_a else "done-B")

    runner._client.messages.create = AsyncMock(side_effect=fake_create)
    # Dispatcher di scorta finto: la meccanica sotto test (isolamento per-Task
    # di last_tool_calls) non dipende da COSA risponde il dispatch, solo dal
    # fatto che risponda -- ToolDispatcher e' uscito, fetta E2 Task 7.
    runner._dispatcher = MagicMock(dispatch=AsyncMock(return_value={"ok": True}))

    async def call_a():
        text = await runner.chat("call-A")
        return text, list(runner.last_tool_calls)

    async def call_b():
        text = await runner.chat("call-B")
        return text, list(runner.last_tool_calls)

    (text_a, tools_a), (text_b, tools_b) = await asyncio.gather(call_a(), call_b())

    assert text_a == "done-A"
    assert text_b == "done-B"
    assert tools_a == [{"tool": "get_area_entities", "input": {"entity_id": "entity-A"}}]
    assert tools_b == [{"tool": "get_home_status", "input": {"entity_id": "entity-B"}}]


class _DispatcherPseudonimizzaDiScorta:
    """fetta E2 Task 8: sostituisce `_DispatcherRecallMemoryDiScorta` (Task 7).

    Quella classe stava al posto di `ToolDispatcher` (uscito nel Task 7) SOLO
    per il test sotto, che deve provare l'isolamento per-Task di
    `last_pseudonym_map` attraverso un dispatch VERO (non mockato) fino a
    `Pseudonymizer` -- l'unico modo di far girare quella prova end-to-end.
    Per arrivarci chiamava `tools/memory_tools.handle_recall_memory`, che pero'
    e' uscita a sua volta in questo stesso task: era orfana dallo stesso Task
    7 che le aveva gia' tolto l'unico chiamante (`ToolDispatcher`), quindi
    nessun test doveva piu' dipenderne. Il soggetto di QUESTO test non e' mai
    stato "la ricerca semantica trova il contenuto giusto" -- e' "due chat
    concorrenti sullo stesso runner non si scambiano il vettore di
    pseudonimizzazione" -- quindi qui si pseudonimizza direttamente un
    contenuto canonico per query, senza passare da KnowledgeStore/embedder:
    stessa `Pseudonymizer`/vault reali, stesso forwarding di `pseudonym_map`,
    una dipendenza in meno."""

    has_memory = True

    _CONTENUTO_PER_QUERY = {
        "query-A": "Bonifico su IT60X0542811101000000123456",
        "query-B": "Contatto: segreto.userB@example.it",
    }

    def __init__(self, pseudonymizer):
        self._pseudonymizer = pseudonymizer

    async def dispatch(self, name, inputs, *, pseudonym_map=None, **_ignored):
        assert name == "recall_memory"
        contenuto = self._pseudonymizer.pseudonymize(
            self._CONTENUTO_PER_QUERY[inputs["query"]], pseudonym_map)
        return {"results": [{"content": contenuto}], "count": 1, "degraded": False}


@pytest.mark.asyncio
async def test_chat_concurrent_calls_do_not_leak_pseudonym_map(tmp_path):
    """SECURITY (review B/#7): two overlapping chat() calls on the SAME
    runner instance -- sharing the SAME dispatcher/Pseudonymizer/vault,
    exactly as two concurrent real users would on a live server -- must never
    leak each other's per-request pseudonymize token map. Each call's own
    recall_memory tool invocation pseudonymizes DIFFERENT sensitive PII into
    the SAME global vault; `last_pseudonym_map` read right after each call's
    own `await runner.chat(...)` must contain ONLY that call's own token, and
    using it to detokenize would never resolve the other call's PII.

    This is the concurrency-flavored counterpart to
    test_chat_concurrent_calls_do_not_leak_tool_calls above, exercising a
    REAL dispatch -> Pseudonymizer path end-to-end (dispatch is not mocked
    here) so the ContextVar-based per-Task isolation is proven against the
    actual security-sensitive code path, not just last_tool_calls
    bookkeeping. `ToolDispatcher` used to be that dispatcher; it is gone
    (fetta E2 Task 7). `_DispatcherPseudonimizzaDiScorta` above stands in for
    it -- see its own docstring for why it no longer routes through
    KnowledgeStore/memory_tools (fetta E2 Task 8)."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    vault = VaultStore(str(tmp_path / "vault.db"))
    pseudonymizer = Pseudonymizer(vault)

    dispatcher = _DispatcherPseudonimizzaDiScorta(pseudonymizer)
    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key", dispatcher=dispatcher)

    def _usage():
        return MagicMock(input_tokens=1, output_tokens=1,
                          cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def _tool_response(query: str):
        # k=1: with only 2 sensitive items in the store, an unbounded k would
        # return BOTH regardless of query vector, defeating the point of this
        # test (each call must only ever pseudonymize ITS OWN best match).
        block = MagicMock(type="tool_use", id=f"id-{query}", input={"query": query, "k": 1})
        block.name = "recall_memory"
        return MagicMock(stop_reason="tool_use", content=[block], usage=_usage())

    def _end_response(text: str):
        block = MagicMock(type="text", text=text)
        return MagicMock(stop_reason="end_turn", content=[block], usage=_usage())

    async def fake_create(**kwargs):
        msgs = kwargs["messages"]
        is_call_a = msgs[0]["content"] == "call-A"
        first_iteration = len(msgs) == 1
        # Same deterministic interleave as the tool_calls test above.
        await asyncio.sleep(0.02 if is_call_a else 0.01)
        if first_iteration:
            return _tool_response("query-A" if is_call_a else "query-B")
        return _end_response("done-A" if is_call_a else "done-B")

    runner._client.messages.create = AsyncMock(side_effect=fake_create)

    async def call_a():
        text = await runner.chat(
            "call-A", allowed_tools=["recall_memory"],
            knowledge_allow_sensitive=True,
        )
        return text, dict(runner.last_pseudonym_map)

    async def call_b():
        text = await runner.chat(
            "call-B", allowed_tools=["recall_memory"],
            knowledge_allow_sensitive=True,
        )
        return text, dict(runner.last_pseudonym_map)

    (text_a, map_a), (text_b, map_b) = await asyncio.gather(call_a(), call_b())

    assert text_a == "done-A"
    assert text_b == "done-B"

    # Each call's own map holds ONLY its own PII, never the other's.
    assert "IT60X0542811101000000123456" in map_a.values()
    assert "segreto.userB@example.it" not in map_a.values()
    assert "segreto.userB@example.it" in map_b.values()
    assert "IT60X0542811101000000123456" not in map_b.values()

    # Cross-request expansion attempt: a token minted for call A must not
    # resolve using call B's map (and vice versa) -- the exact shape of the
    # review B/#7 leak, now proven against the real end-to-end path.
    token_a = next(iter(map_a))
    assert pseudonymizer.detokenize(f"testo con {token_a}", map_b) == f"testo con {token_a}"

    vault.close()


def test_save_usage_concurrent_writes_keep_valid_json(tmp_path):
    """Concurrent _save_usage() calls must not corrupt usage.json.

    _save_usage runs on every API response and is reachable from multiple
    concurrent agent runs / chats; without the write lock two threads race on
    the same .tmp path and leave invalid JSON on disk.
    """
    import json as _json
    import threading
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test",
        usage_path=str(tmp_path / "usage.json"),
    )

    def worker():
        for _ in range(25):
            runner.total_requests += 1
            runner._save_usage()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(runner._usage_path, encoding="utf-8") as f:
        data = _json.load(f)  # corrupt file would raise here
    assert data["total_requests"] >= 25


# --- render_template e il perimetro delle entita' ---------------------------
# fetta E2 Task 8 ("escono i trentaquattro"): i tre test che vivevano qui
# (render_template tolto sotto perimetro, lasciato senza, concedibile
# esplicitamente) sono stati cancellati, non spostati. Il loro soggetto era
# la presenza CONDIZIONATA di `render_template` nel catalogo che `chat()`
# offre quando `strumenti` non e' passato -- ma quella definizione (RENDER_
# TEMPLATE_TOOL_DEF) e' uscita da EVALUATION_TOOL_DEFS insieme al resto dei
# 34: non e' nominata da EVALUATION_ONLY_TOOLS (esclusa di proposito, vedi il
# commento su quel set in claude_runner.py), e la chat non offre piu' un
# catalogo da questo file (STRUMENTI_CONOSCENZA, casa/strumenti.py). Nessuna
# combinazione di allowed_tools/allowed_entities puo' piu' far comparire
# "render_template" in un catalogo che non lo contiene: due dei tre test
# fallivano gia' per costruzione, il terzo era diventato vacuo. Il filtro
# stesso (la riga `tools = [t for t in tools if t["name"] != "render_
# template"]` in claude_runner.chat()) resta nel codice come no-op innocuo,
# non e' stato toccato da questo task.
