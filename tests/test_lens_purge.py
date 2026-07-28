"""Slice 3 Task 4: retention purge moves from the retired MemoryStore onto
the unified KnowledgeStore. purge_expired_chatbot() must only remove
chatbot-scoped (per-agent working memory) rows past their valid_until --
never non-chatbot knowledge, and never rows that are still fresh or have no
expiry."""
from __future__ import annotations

from hiris.app.brain.knowledge_store import KnowledgeStore


def test_purge_removes_only_expired_chatbot(tmp_path):
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    live = s.add_item(kind="memory", content="live", owner="home", chatbot_id="a",
                      status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    dead = s.add_item(kind="memory", content="dead", owner="home", chatbot_id="a",
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    knNo = s.add_item(kind="fact", content="knowledge", owner="home", chatbot_id=None,
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    n = s.purge_expired_chatbot()
    assert n == 1
    assert s.get_item(dead) is None
    assert s.get_item(live) is not None
    assert s.get_item(knNo) is not None  # non-chatbot NON si purga anche se scaduta
    s.close()


def test_delete_by_chatbot_removes_only_that_agents_rows(tmp_path):
    """delete_by_chatbot is the KnowledgeStore equivalent of the retired
    MemoryStore.delete_by_agent (used by handle_delete_agent to clean up an
    agent's own working memory). It must remove every row for that
    chatbot_id regardless of expiry, and leave other chatbots and
    non-chatbot knowledge untouched."""
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    a1 = s.add_item(kind="memory", content="a-live", owner="home", chatbot_id="agentA",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    a2 = s.add_item(kind="memory", content="a-dead", owner="home", chatbot_id="agentA",
                    status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    b1 = s.add_item(kind="memory", content="b-live", owner="home", chatbot_id="agentB",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    knNo = s.add_item(kind="fact", content="shared knowledge", owner="home", chatbot_id=None,
                      status="approved", embedding=[0.1])

    n = s.delete_by_chatbot("agentA")

    assert n == 2
    assert s.get_item(a1) is None
    assert s.get_item(a2) is None
    assert s.get_item(b1) is not None
    assert s.get_item(knNo) is not None
    s.close()
