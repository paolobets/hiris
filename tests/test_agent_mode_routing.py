import pytest
from unittest.mock import AsyncMock

from hiris.app.llm_router import LLMRouter
from hiris.app.agent_engine import AgentEngine


class _R:
    def __init__(self, name):
        self.name = name
        self.seen = []

    async def chat(self, **kw):
        self.seen.append(kw)
        return self.name

    async def run_with_actions(self, **kw):
        self.seen.append(kw)
        return (self.name, None, None)


@pytest.mark.asyncio
async def test_scheduled_chat_agent_uses_automatic_policy():
    # agentA chat scheduled run should route via automatic_policy (ollama first),
    # NOT chat_policy (claude first)
    claude, ollama = _R("claude"), _R("ollama")
    router = LLMRouter(claude=claude, ollama=ollama,
                        automatic_policy=["ollama", "claude"], chat_policy=["claude"])
    # simulate the scheduled-chat call site: chat(model="auto", mode="automatic")
    out = await router.chat(model="auto", mode="automatic")
    assert out == "ollama"


@pytest.fixture
def mock_ha():
    return AsyncMock()


@pytest.fixture
def engine(mock_ha, tmp_path):
    return AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))


@pytest.mark.asyncio
async def test_scheduled_chat_agent_run_passes_mode_automatic_to_runner(engine):
    """The real call site: agent_engine's scheduled type=='chat' run must pass
    mode="automatic" to router.chat(...) so it routes via automatic_policy
    (autonomous run), not chat_policy (reserved for interactive chat)."""
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Scheduled Chat Agent", "type": "chat",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "do stuff", "allowed_tools": [], "enabled": False,
        "model": "auto",
    })
    await engine.run_agent(agent)

    call_kwargs = mock_runner.chat.call_args.kwargs
    assert call_kwargs["mode"] == "automatic"
    assert call_kwargs["model"] == "auto"


@pytest.mark.asyncio
async def test_agent_type_run_does_not_pass_mode_explicitly(engine):
    """agent_engine.py:910 (type=='agent') relies on run_with_actions' own
    default (automatic) and must not need to pass mode explicitly."""
    mock_runner = AsyncMock()
    mock_runner.run_with_actions = AsyncMock(return_value=("result", {}))
    mock_runner.last_tool_calls = []
    mock_runner.total_input_tokens = 0
    mock_runner.total_output_tokens = 0
    engine.set_claude_runner(mock_runner)

    agent = engine.create_agent({
        "name": "Proactive Agent", "type": "agent",
        "triggers": [{"type": "schedule", "interval_minutes": 5}],
        "system_prompt": "do stuff", "allowed_tools": [], "enabled": False,
        "model": "auto",
    })
    await engine.run_agent(agent)

    call_kwargs = mock_runner.run_with_actions.call_args.kwargs
    assert "mode" not in call_kwargs
