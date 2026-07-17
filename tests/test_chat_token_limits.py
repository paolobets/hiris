import pytest
from unittest.mock import AsyncMock

from hiris.app.agent_engine import AgentEngine
from hiris.app.claude_runner import _max_tokens_message, _TRUNCATION_NOTICE, CHAT_MAX_TOKENS


@pytest.fixture
def engine(tmp_path):
    return AgentEngine(ha_client=AsyncMock(), data_path=str(tmp_path / "agents.json"))


# --- Part 1: type-aware max_tokens cap ---

def test_cap_chat_allows_up_to_16000():
    assert AgentEngine._cap_max_tokens(16000, "chat") == 16000
    assert AgentEngine._cap_max_tokens(99999, "chat") == 16000  # clamped to chat cap
    assert AgentEngine._cap_max_tokens(12000, "chat") == 12000  # below cap kept


def test_cap_non_chat_stays_at_8192():
    assert AgentEngine._cap_max_tokens(16000, "agent") == 8192
    assert AgentEngine._cap_max_tokens(4096, "agent") == 4096


def test_create_chat_agent_keeps_high_max_tokens(engine):
    agent = engine.create_agent({"name": "Chat", "type": "chat", "max_tokens": 16000})
    assert agent.max_tokens == 16000


def test_create_non_chat_agent_clamped_to_8192(engine):
    agent = engine.create_agent({"name": "Mon", "type": "monitor", "max_tokens": 16000})
    assert agent.max_tokens == 8192


def test_update_chat_agent_raises_cap(engine):
    agent = engine.create_agent({"name": "Chat", "type": "chat", "max_tokens": 4096})
    engine.update_agent(agent.id, {"max_tokens": 16000})
    assert engine.get_agent(agent.id).max_tokens == 16000


def test_chat_max_tokens_constant_matches_cap():
    # The runtime chat floor and the persistence cap must agree.
    assert CHAT_MAX_TOKENS == AgentEngine._CHAT_MAX_TOKENS_CAP == 16000


# --- Part 2: max_tokens truncation message ---

def test_max_tokens_message_with_prefix_appends_notice():
    msg = _max_tokens_message(["Ora creo la dashboard!"])
    assert msg.startswith("Ora creo la dashboard!")
    assert _TRUNCATION_NOTICE in msg


def test_max_tokens_message_without_prefix_is_the_notice():
    assert _max_tokens_message([]) == _TRUNCATION_NOTICE
    assert _max_tokens_message(["   "]) == _TRUNCATION_NOTICE
