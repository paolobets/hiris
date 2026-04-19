import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.claude_runner import ClaudeRunner, RESTRICT_PROMPT


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
            restrict_to_home=True,
        )


@pytest.mark.asyncio
async def test_restrict_to_home_injects_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="ok")])

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao")
    system_used = captured[0]["system"]
    assert "SOLO" in system_used or "solo" in system_used.lower()
    assert RESTRICT_PROMPT in system_used


@pytest.mark.asyncio
async def test_restrict_to_home_false_does_not_inject(runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="ok")])

    runner._client.messages.create = capture
    await runner.chat("Ciao", system_prompt="Prompt originale")
    assert captured[0]["system"] == "Prompt originale"


@pytest.mark.asyncio
async def test_restrict_to_home_appends_to_existing_prompt(restricted_runner):
    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)
        return MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="ok")])

    restricted_runner._client.messages.create = capture
    await restricted_runner.chat("Ciao", system_prompt="Sei un agente energia.")
    system_used = captured[0]["system"]
    assert "agente energia" in system_used
    assert RESTRICT_PROMPT in system_used
