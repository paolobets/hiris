"""Slice 3 Task 4: retention purge moves from the retired MemoryStore onto
the unified KnowledgeStore. purge_expired_chatbot() must only remove rows
that carry their own expired retention (valid_until) -- never non-chatbot
knowledge, and never rows that are still fresh or have no expiry.

Task 3 (memoria unica) changes what happens on chatbot deletion:
`delete_by_chatbot` (which DELETEd rows) is retired in favor of
`detach_chatbot_id` (which only clears the now-dangling chatbot_id
reference) -- see the docstring on `KnowledgeStore.detach_chatbot_id` for
why deleting was no longer safe once chatbot_id stopped being a scope."""
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


def test_detach_chatbot_id_clears_reference_without_deleting_rows(tmp_path):
    """`detach_chatbot_id` is what `delete_by_chatbot` became under Task 3
    (memoria unica). A chatbot's rows are house knowledge now (owner +
    sensitivity govern visibility, not chatbot_id) -- deleting the chatbot
    must not delete them. This pins the data-loss fix directly: every row
    that carried this chatbot_id survives, readable, with chatbot_id cleared
    to NULL; rows of other chatbots and non-chatbot knowledge are untouched
    (including their chatbot_id, where they had one)."""
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    a1 = s.add_item(kind="memory", content="a-live", owner="home", chatbot_id="agentA",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    a2 = s.add_item(kind="memory", content="a-dead", owner="home", chatbot_id="agentA",
                    status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")
    b1 = s.add_item(kind="memory", content="b-live", owner="home", chatbot_id="agentB",
                    status="approved", embedding=[0.1], valid_until="2999-01-01T00:00:00")
    knNo = s.add_item(kind="fact", content="shared knowledge", owner="home", chatbot_id=None,
                      status="approved", embedding=[0.1])

    n = s.detach_chatbot_id("agentA")

    assert n == 2
    row_a1 = s.get_item(a1)
    row_a2 = s.get_item(a2)
    assert row_a1 is not None and row_a1["chatbot_id"] is None, (
        "il contenuto sopravvive: e' conoscenza di casa, non del chatbot "
        "cancellato -- solo il riferimento pendente va ripulito"
    )
    assert row_a2 is not None and row_a2["chatbot_id"] is None
    row_b1 = s.get_item(b1)
    assert row_b1 is not None and row_b1["chatbot_id"] == "agentB"
    assert s.get_item(knNo) is not None
    s.close()


def test_detach_chatbot_id_survives_expiry_that_would_have_purged_it(tmp_path):
    """Prova diretta del rischio di perdita dati citato nel brief: prima
    della fetta, cancellare un chatbot con `delete_by_chatbot` cancellava
    ANCHE le righe gia' scadute (`regardless of expiry`). Con
    `detach_chatbot_id` la riga sopravvive comunque -- e sopravvive anche a
    un successivo giro di `purge_expired_chatbot`, perche' senza chatbot_id
    non porta piu' una politica di retention da far scadere."""
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    dead = s.add_item(kind="memory", content="a-dead", owner="home", chatbot_id="agentA",
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00")

    s.detach_chatbot_id("agentA")
    assert s.get_item(dead) is not None

    purged = s.purge_expired_chatbot()
    assert purged == 0
    assert s.get_item(dead) is not None
    s.close()
