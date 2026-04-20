import pytest
import anthropic
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.claude_runner import ClaudeRunner, RESTRICT_PROMPT, resolve_model, AUTO_MODEL_MAP


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
    with patch("anthropic.AsyncAnthropic"):
        return ClaudeRunner(
            api_key="test-key",
            ha_client=mock_ha,
            notify_config={},
        )


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
    with patch("anthropic.AsyncAnthropic"):
        return ClaudeRunner(
            api_key="test-key",
            ha_client=mock_ha,
            notify_config={},
        )


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
    system_used = captured[0]["system"]
    assert "SOLO" in system_used or "solo" in system_used.lower()
    assert RESTRICT_PROMPT in system_used


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
    assert captured[0]["system"] == "Prompt originale"


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
    system_used = captured[0]["system"]
    assert "agente energia" in system_used
    assert RESTRICT_PROMPT in system_used


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
async def test_chat_injects_home_profile_when_cache_available(runner):
    cache = MagicMock()
    cache.get_all_useful.return_value = [
        {"id": "light.test", "state": "on", "name": "Test", "unit": ""},
    ]
    runner._cache = cache

    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2
    runner._client.messages.create = AsyncMock(return_value=success)

    await runner.chat("Ciao", system_prompt="Base prompt")

    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert "CASA [aggiornato" in call_kwargs["system"]
    assert "Base prompt" in call_kwargs["system"]


@pytest.mark.asyncio
async def test_chat_skips_home_profile_when_no_cache(runner):
    runner._cache = None

    success = MagicMock()
    success.stop_reason = "end_turn"
    success.content = [MagicMock(type="text", text="ok")]
    success.usage.input_tokens = 5
    success.usage.output_tokens = 2
    runner._client.messages.create = AsyncMock(return_value=success)

    await runner.chat("Ciao", system_prompt="Solo prompt")

    call_kwargs = runner._client.messages.create.call_args.kwargs
    assert "CASA" not in call_kwargs["system"]
    assert call_kwargs["system"] == "Solo prompt"


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
    system_used = captured[0]["system"]
    assert REQUIRE_CONFIRMATION_PROMPT in system_used
    assert "Base" in system_used


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
    assert "Base" in system_used
    assert RESTRICT_PROMPT in system_used
    assert REQUIRE_CONFIRMATION_PROMPT in system_used
