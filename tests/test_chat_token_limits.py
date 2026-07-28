import pytest
from unittest.mock import AsyncMock

from hiris.app.chatbot_engine import ChatbotEngine
from hiris.app.claude_runner import _max_tokens_message, _TRUNCATION_NOTICE, CHAT_MAX_TOKENS


@pytest.fixture
def engine(tmp_path):
    return ChatbotEngine(ha_client=AsyncMock(), data_path=str(tmp_path / "agents.json"))


# --- Part 1: max_tokens cap ---
# Slice 5 Task 2 dropped the `type` field — every persona is a chat entity
# now, so there is a single cap (there is no more non-chat "agent"/"monitor"
# variant to clamp lower).

def test_cap_allows_up_to_16000():
    assert ChatbotEngine._cap_max_tokens(16000) == 16000
    assert ChatbotEngine._cap_max_tokens(99999) == 16000  # clamped to the cap
    assert ChatbotEngine._cap_max_tokens(12000) == 12000  # below cap kept


def test_create_agent_keeps_high_max_tokens(engine):
    agent = engine.create_chatbot({"name": "Chat", "max_tokens": 16000})
    assert agent.max_tokens == 16000


def test_create_agent_clamped_to_16000(engine):
    agent = engine.create_chatbot({"name": "Persona", "max_tokens": 99999})
    assert agent.max_tokens == 16000


def test_update_agent_raises_cap(engine):
    agent = engine.create_chatbot({"name": "Chat", "max_tokens": 4096})
    engine.update_chatbot(agent.id, {"max_tokens": 16000})
    assert engine.get_chatbot(agent.id).max_tokens == 16000


def test_chat_max_tokens_constant_matches_cap():
    # The runtime chat floor and the persistence cap must agree.
    assert CHAT_MAX_TOKENS == ChatbotEngine._CHAT_MAX_TOKENS_CAP == 16000


# --- Part 2: max_tokens truncation message ---

def test_max_tokens_message_with_prefix_appends_notice():
    msg = _max_tokens_message(["Ora creo la dashboard!"])
    assert msg.startswith("Ora creo la dashboard!")
    assert _TRUNCATION_NOTICE in msg


def test_max_tokens_message_without_prefix_is_the_notice():
    assert _max_tokens_message([]) == _TRUNCATION_NOTICE
    assert _max_tokens_message(["   "]) == _TRUNCATION_NOTICE
