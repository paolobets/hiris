"""Slice 3 Task 4: retention purge moves from the retired MemoryStore onto
the unified KnowledgeStore. purge_expired_lens() must only remove lens-scoped
(per-agent working memory) rows past their valid_until -- never non-lens
knowledge, and never rows that are still fresh or have no expiry."""
from __future__ import annotations

from hiris.app.brain.knowledge_store import KnowledgeStore


def test_purge_removes_only_expired_lens(tmp_path):
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    live = s.add_item(kind="memory", content="live", owner="home", lens="a",
                      status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    dead = s.add_item(kind="memory", content="dead", owner="home", lens="a",
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    knNo = s.add_item(kind="fact", content="knowledge", owner="home", lens=None,
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    n = s.purge_expired_lens()
    assert n == 1
    assert s.get_item(dead) is None
    assert s.get_item(live) is not None
    assert s.get_item(knNo) is not None  # non-lens NON si purga anche se scaduta
    s.close()


def test_delete_by_lens_removes_only_that_agents_rows(tmp_path):
    """delete_by_lens is the KnowledgeStore equivalent of the retired
    MemoryStore.delete_by_agent (used by handle_delete_agent to clean up an
    agent's own working memory). It must remove every row for that lens
    regardless of expiry, and leave other lenses and non-lens knowledge
    untouched."""
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    a1 = s.add_item(kind="memory", content="a-live", owner="home", lens="agentA",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    a2 = s.add_item(kind="memory", content="a-dead", owner="home", lens="agentA",
                    status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    b1 = s.add_item(kind="memory", content="b-live", owner="home", lens="agentB",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    knNo = s.add_item(kind="fact", content="shared knowledge", owner="home", lens=None,
                      status="approved", embedding=[0.1])

    n = s.delete_by_lens("agentA")

    assert n == 2
    assert s.get_item(a1) is None
    assert s.get_item(a2) is None
    assert s.get_item(b1) is not None
    assert s.get_item(knNo) is not None
    s.close()
