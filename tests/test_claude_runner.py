import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hiris.app.claude_runner import ClaudeRunner


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

    with patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = fake_message

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

    with patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = [msg1, msg2]
        runner._client = instance
        result = await runner.chat("Is the light on?")

    assert result == "The light is on"
