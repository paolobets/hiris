import pytest
import unittest.mock
import anthropic
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.claude_runner import ClaudeRunner, RESTRICT_PROMPT, resolve_model, AUTO_MODEL_MAP
from hiris.app.tools.dispatcher import ToolDispatcher


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
    dispatcher = ToolDispatcher(mock_ha, {})
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key", dispatcher=dispatcher)
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


@pytest.mark.asyncio
async def test_chat_handles_tool_use(runner):
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.id = "tu_123"
    tool_use_block.name = "get_entity_states"
    tool_use_block.input = {"ids": ["light.living"]}

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "The light is on"

    msg1 = MagicMock()
    msg1.stop_reason = "tool_use"
    msg1.content = [tool_use_block]

    msg2 = MagicMock()
    msg2.stop_reason = "end_turn"
    msg2.content = [text_block]

    runner._ha.get_states = AsyncMock(return_value=[{"entity_id": "light.living", "state": "on", "attributes": {}}])

    with patch("anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(side_effect=[msg1, msg2])
        runner._client = instance
        result = await runner.chat("Is the light on?")

    assert result == "The light is on"


@pytest.mark.asyncio
async def test_allowed_entities_filters_get_entity_states(runner):
    runner._ha.get_states = AsyncMock(return_value=[
        {"entity_id": "climate.soggiorno", "state": "heat", "attributes": {}},
    ])
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_ent"
    tool_block.name = "get_entity_states"
    tool_block.input = {"ids": ["climate.soggiorno", "light.cucina", "sensor.temp"]}
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="Filtrato")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Query entità", allowed_entities=["climate.*"])
    call_args = runner._ha.get_states.call_args[0][0]
    assert "climate.soggiorno" in call_args
    assert "light.cucina" not in call_args
    assert "sensor.temp" not in call_args


@pytest.mark.asyncio
async def test_allowed_entities_empty_means_no_restriction(runner):
    runner._ha.get_states = AsyncMock(return_value=[
        {"entity_id": "light.cucina", "state": "on", "attributes": {}},
    ])
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_full"
    tool_block.name = "get_entity_states"
    tool_block.input = {"ids": ["light.cucina", "sensor.temp"]}
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="OK")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Query libera", allowed_entities=[])
    call_args = runner._ha.get_states.call_args[0][0]
    assert "light.cucina" in call_args
    assert "sensor.temp" in call_args


@pytest.mark.asyncio
async def test_allowed_services_blocks_unauthorized_service(runner):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_svc"
    tool_block.name = "call_ha_service"
    tool_block.input = {"domain": "light", "service": "turn_on", "data": {}}
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="Bloccato")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Accendi luce", allowed_services=["climate.*", "notify.*"])
    runner._ha.call_service.assert_not_called()


@pytest.mark.asyncio
async def test_allowed_services_permits_matching_service(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_svc2"
    tool_block.name = "call_ha_service"
    tool_block.input = {"domain": "climate", "service": "set_temperature", "data": {"temperature": 21}}
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="Temperatura impostata")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Imposta 21°C", allowed_services=["climate.*"])
    runner._ha.call_service.assert_called_once_with("climate", "set_temperature", {"temperature": 21})


@pytest.mark.asyncio
async def test_allowed_services_empty_means_no_restriction(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_free"
    tool_block.name = "call_ha_service"
    tool_block.input = {"domain": "light", "service": "turn_on", "data": {}}
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    text_block = MagicMock(type="text", text="OK")
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Accendi", allowed_services=[])
    runner._ha.call_service.assert_called_once()


@pytest.fixture
def restricted_runner(mock_ha):
    dispatcher = ToolDispatcher(mock_ha, {})
    with patch("anthropic.AsyncAnthropic"):
        r = ClaudeRunner(api_key="test-key", dispatcher=dispatcher)
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


@pytest.mark.asyncio
async def test_dispatch_get_area_entities(runner):
    runner._ha.get_area_registry = AsyncMock(return_value=[
        {"area_id": "cucina", "name": "Cucina"}
    ])
    runner._ha.get_entity_registry = AsyncMock(return_value=[
        {"entity_id": "light.luce_cucina", "area_id": "cucina"}
    ])
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "tu_area"
    tool_block.name = "get_area_entities"
    tool_block.input = {}
    text_block = MagicMock(type="text", text="Cucina: light.luce_cucina")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Accendi le luci della cucina")
    assert result == "Cucina: light.luce_cucina"
    runner._ha.get_area_registry.assert_awaited_once()
    runner._ha.get_entity_registry.assert_awaited_once()


def test_get_area_entities_in_all_tool_defs():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    names = [t["name"] for t in ALL_TOOL_DEFS]
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


def test_resolve_model_auto_monitor_returns_haiku():
    assert resolve_model("auto", "monitor") == "claude-haiku-4-5-20251001"


def test_resolve_model_auto_reactive_returns_haiku():
    assert resolve_model("auto", "reactive") == "claude-haiku-4-5-20251001"


def test_resolve_model_explicit_overrides_auto():
    assert resolve_model("claude-sonnet-4-6", "monitor") == "claude-sonnet-4-6"


def test_resolve_model_auto_unknown_type_defaults_to_sonnet():
    assert resolve_model("auto", "unknown_type") == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_chat_uses_resolved_model_for_monitor(runner):
    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 10
    success.usage.output_tokens = 5
    runner._client.messages.create = AsyncMock(return_value=success)
    await runner.chat("Test", model="auto", agent_type="monitor")
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


def test_build_action_instructions_notify():
    from hiris.app.claude_runner import _build_action_instructions
    actions = [{"type": "notify", "label": "Avvisa via Telegram", "channel": "telegram"}]
    instructions = _build_action_instructions(actions)
    assert "VALUTAZIONE:" in instructions
    assert "AZIONE:" in instructions
    assert "Avvisa via Telegram" in instructions


def test_build_action_instructions_call_service():
    from hiris.app.claude_runner import _build_action_instructions
    actions = [
        {"type": "call_service", "label": "Spegni luci",
         "domain": "light", "service": "turn_off", "entity_pattern": "light.*"},
    ]
    instructions = _build_action_instructions(actions)
    assert "Spegni luci" in instructions
    assert "light.turn_off" in instructions


def test_build_action_instructions_empty():
    from hiris.app.claude_runner import _build_action_instructions
    assert _build_action_instructions([]) == ""


def test_parse_structured_response_extracts_fields():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Il sistema è normale.\n\nVALUTAZIONE: OK\nAZIONE: nessuna azione necessaria"
    text, status, action = _parse_structured_response(raw)
    assert status == "OK"
    assert action == "nessuna azione necessaria"
    assert "VALUTAZIONE:" not in text
    assert "AZIONE:" not in text
    assert "Il sistema è normale." in text


def test_parse_structured_response_attenzione():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Anomalia rilevata.\nVALUTAZIONE: ANOMALIA\nAZIONE: Notifica inviata via Telegram"
    text, status, action = _parse_structured_response(raw)
    assert status == "ANOMALIA"
    assert action == "Notifica inviata via Telegram"


def test_parse_structured_response_missing_lines():
    from hiris.app.claude_runner import _parse_structured_response
    raw = "Risposta senza struttura"
    text, status, action = _parse_structured_response(raw)
    assert text == raw
    assert status is None
    assert action is None


def test_parse_structured_response_no_false_positive():
    from hiris.app.claude_runner import _parse_structured_response
    # VALUTAZIONE mid-paragraph should NOT be consumed
    raw = "La VALUTAZIONE: scarsa dell'impianto è allarmante.\n\nVALUTAZIONE: ANOMALIA\nAZIONE: notifica"
    text, status, action = _parse_structured_response(raw)
    assert status == "ANOMALIA"
    assert action == "notifica"
    # The mid-body mention should remain in clean text
    assert "VALUTAZIONE: scarsa" in text


@pytest.mark.asyncio
async def test_run_with_actions_injects_instructions_and_parses():
    from unittest.mock import AsyncMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner.__new__(ClaudeRunner)
    runner.chat = AsyncMock(return_value="Tutto OK.\n\nVALUTAZIONE: OK\nAZIONE: nessuna azione necessaria")

    actions = [{"type": "notify", "label": "Test", "channel": "ha"}]
    text, status, action = await runner.run_with_actions(
        user_message="test",
        system_prompt="base system",
        actions=actions,
    )

    assert status == "OK"
    assert action == "nessuna azione necessaria"
    assert "Tutto OK." in text
    # Verify the augmented prompt was passed to chat()
    call_kwargs = runner.chat.call_args.kwargs
    assert "VALUTAZIONE:" in call_kwargs["system_prompt"]
    assert "base system" in call_kwargs["system_prompt"]


def test_get_agent_usage_returns_zeros_for_unknown_agent():
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner
    runner = ClaudeRunner(
        api_key="test",
        dispatcher=ToolDispatcher(MagicMock(), {}),
        usage_path="",
    )
    usage = runner.get_agent_usage("agent-xyz")
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["cost_usd"] == 0.0
    assert usage["last_run"] is None


def test_per_agent_usage_accumulates_after_chat():
    """chat() with agent_id accumulates tokens in _per_agent_usage."""
    import asyncio
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test",
        dispatcher=ToolDispatcher(MagicMock(), {}),
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

    asyncio.run(runner.chat(user_message="hello", agent_id="agent-abc"))

    usage = runner.get_agent_usage("agent-abc")
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["requests"] == 1
    assert usage["cost_usd"] > 0
    assert usage["last_run"] is not None


def test_reset_agent_usage_clears_counters():
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    runner = ClaudeRunner(
        api_key="test",
        dispatcher=ToolDispatcher(MagicMock(), {}),
        usage_path="",
    )
    runner._per_agent_usage["agent-abc"] = {
        "input_tokens": 500, "output_tokens": 200,
        "requests": 3, "cost_usd": 0.002, "last_run": "2026-01-01T00:00:00Z",
    }
    runner.reset_agent_usage("agent-abc")
    usage = runner.get_agent_usage("agent-abc")
    assert usage["input_tokens"] == 0
    assert usage["requests"] == 0
    assert usage["last_run"] is None


def test_per_agent_usage_persists_and_reloads(tmp_path):
    from unittest.mock import MagicMock
    from hiris.app.claude_runner import ClaudeRunner

    usage_file = str(tmp_path / "usage.json")
    runner = ClaudeRunner(
        api_key="test",
        dispatcher=ToolDispatcher(MagicMock(), {}),
        usage_path=usage_file,
    )
    runner._per_agent_usage["agent-persist"] = {
        "input_tokens": 1000, "output_tokens": 400,
        "requests": 5, "cost_usd": 0.005, "last_run": "2026-04-01T10:00:00Z",
    }
    runner._save_usage()

    runner2 = ClaudeRunner(
        api_key="test",
        dispatcher=ToolDispatcher(MagicMock(), {}),
        usage_path=usage_file,
    )
    usage = runner2.get_agent_usage("agent-persist")
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
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    names = [t["name"] for t in ALL_TOOL_DEFS]
    assert "get_calendar_events" in names


@pytest.mark.asyncio
async def test_dispatch_get_calendar_events_all_calendars(runner):
    runner._ha.get_calendars = AsyncMock(return_value=[
        {"entity_id": "calendar.home", "name": "Home"},
    ])
    runner._ha.get_calendar_events_range = AsyncMock(return_value=[
        {"summary": "Meeting", "start": {"dateTime": "2026-04-24T10:00:00+00:00"}, "end": {"dateTime": "2026-04-24T11:00:00+00:00"}},
    ])
    # MagicMock's `name` kwarg sets the mock's internal repr, not the .name attribute.
    # Assign .name explicitly so _dispatch_tool sees the correct string.
    tool_block = MagicMock(type="tool_use", id="tu_cal", input={"hours": 24})
    tool_block.name = "get_calendar_events"
    text_block = MagicMock(type="text", text="Hai un meeting alle 10.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Cosa ho in agenda oggi?")
    assert result == "Hai un meeting alle 10."
    runner._ha.get_calendars.assert_awaited_once()
    runner._ha.get_calendar_events_range.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_get_calendar_events_specific_calendar(runner):
    runner._ha.get_calendar_events_range = AsyncMock(return_value=[])
    runner._ha.get_calendars = AsyncMock()
    tool_block = MagicMock(type="tool_use", id="tu_cal2", input={"hours": 48, "calendar_entity": "calendar.work"})
    tool_block.name = "get_calendar_events"
    text_block = MagicMock(type="text", text="Nessun evento.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Impegni di lavoro nei prossimi 2 giorni?")
    assert result == "Nessun evento."
    runner._ha.get_calendar_events_range.assert_awaited_once_with(
        "calendar.work", unittest.mock.ANY, unittest.mock.ANY
    )
    runner._ha.get_calendars.assert_not_awaited()


def test_set_input_helper_in_all_tool_defs():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    names = [t["name"] for t in ALL_TOOL_DEFS]
    assert "set_input_helper" in names


@pytest.mark.asyncio
async def test_dispatch_set_input_helper_boolean_on(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock(type="tool_use", id="tu_ih1",
                           input={"entity_id": "input_boolean.guest_mode", "value": True})
    tool_block.name = "set_input_helper"
    text_block = MagicMock(type="text", text="Modalità ospite attivata.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Attiva la modalità ospite.")
    assert result == "Modalità ospite attivata."
    runner._ha.call_service.assert_awaited_once_with(
        "input_boolean", "turn_on", {"entity_id": "input_boolean.guest_mode"}
    )


@pytest.mark.asyncio
async def test_dispatch_set_input_helper_number(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock(type="tool_use", id="tu_ih2",
                           input={"entity_id": "input_number.target_temp", "value": 21.5})
    tool_block.name = "set_input_helper"
    text_block = MagicMock(type="text", text="Temperatura impostata a 21.5°C.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Imposta temperatura target a 21.5.")
    assert result == "Temperatura impostata a 21.5°C."
    runner._ha.call_service.assert_awaited_once_with(
        "input_number", "set_value", {"entity_id": "input_number.target_temp", "value": 21.5}
    )


@pytest.mark.asyncio
async def test_dispatch_set_input_helper_select(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock(type="tool_use", id="tu_ih3",
                           input={"entity_id": "input_select.house_mode", "value": "Away"})
    tool_block.name = "set_input_helper"
    text_block = MagicMock(type="text", text="Modalità impostata su Away.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    result = await runner.chat("Imposta modalità casa su Away.")
    assert result == "Modalità impostata su Away."
    runner._ha.call_service.assert_awaited_once_with(
        "input_select", "select_option", {"entity_id": "input_select.house_mode", "option": "Away"}
    )


@pytest.mark.asyncio
async def test_set_input_helper_blocked_by_allowed_services(runner):
    runner._ha.call_service = AsyncMock(return_value=True)
    tool_block = MagicMock(type="tool_use", id="tu_ih4",
                           input={"entity_id": "input_boolean.guest_mode", "value": True})
    tool_block.name = "set_input_helper"
    text_block = MagicMock(type="text", text="Bloccato.")
    msg1 = MagicMock(stop_reason="tool_use", content=[tool_block])
    msg2 = MagicMock(stop_reason="end_turn", content=[text_block])
    runner._client.messages.create = AsyncMock(side_effect=[msg1, msg2])
    await runner.chat("Attiva guest mode.", allowed_services=["light.*", "climate.*"])
    runner._ha.call_service.assert_not_called()
