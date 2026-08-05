"""Task 3 (memoria unica) changes what happens on chatbot deletion:
`delete_by_chatbot` (which DELETEd rows) is retired in favor of
`detach_chatbot_id` (which only clears the now-dangling chatbot_id
reference) -- see the docstring on `KnowledgeStore.detach_chatbot_id` for
why deleting was no longer safe once chatbot_id stopped being a scope.

Task 6 (memoria non evapora) removes `purge_expired_chatbot` entirely: its
only feed of work was `valid_until` set by `handle_save_memory` from
`retention_days`, and that computation is gone (design decision: HIRIS's
knowledge of the house does not expire). The tests that used to pin
`purge_expired_chatbot`'s behavior lived here; what remains is the part
that is still true -- `detach_chatbot_id` never deletes content, only the
dangling chatbot reference."""
from __future__ import annotations

from hiris.app.brain.knowledge_store import KnowledgeStore


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
                    status="approved", embedding=[0.1])
    a2 = s.add_item(kind="memory", content="a-second", owner="home", chatbot_id="agentA",
                    status="approved", embedding=[0.1])
    b1 = s.add_item(kind="memory", content="b-live", owner="home", chatbot_id="agentB",
                    status="approved", embedding=[0.1])
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


def test_detach_chatbot_id_survives_regardless_of_any_leftover_expiry(tmp_path):
    """Prova diretta del rischio di perdita dati citato nel brief: prima
    della fetta, cancellare un chatbot con `delete_by_chatbot` cancellava
    ANCHE le righe gia' scadute (`regardless of expiry`). Con
    `detach_chatbot_id` la riga sopravvive comunque -- non c'e' piu' nessun
    `purge_expired_chatbot` che possa raccoglierla in seguito, perche' quel
    metodo e' stato rimosso (Task 6): nessun percorso di prodotto scrive piu'
    un `valid_until` su un kind='memory', quindi non ha piu' avuto lavoro da
    fare da quando `handle_save_memory` ha smesso di calcolarne uno."""
    s = KnowledgeStore(str(tmp_path / "knowledge.db"))
    dead = s.add_item(kind="memory", content="a-dead", owner="home", chatbot_id="agentA",
                      status="approved", embedding=[0.1], valid_until="2000-01-01T00:00:00Z")

    s.detach_chatbot_id("agentA")
    assert s.get_item(dead) is not None
    assert not hasattr(s, "purge_expired_chatbot"), (
        "purge_expired_chatbot va rimosso del tutto (Task 6): nessun "
        "chiamante gli produce piu' lavoro"
    )
    s.close()
