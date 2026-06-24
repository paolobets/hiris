import sqlite3
from hiris.app.brain.knowledge_store import KnowledgeStore


def test_init_creates_tables(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    conn = sqlite3.connect(str(tmp_path / "brain.db"))
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "knowledge_items" in names
    assert "knowledge_links" in names
    store.close()


def test_add_and_get_item(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    item_id = store.add_item(
        kind="preference", owner="home",
        title="Intolleranza lattosio",
        content="Paolo è intollerante al lattosio",
        embedding=[0.1, 0.2, 0.3],
        sensitivity="normal", source="manual", status="approved",
    )
    got = store.get_item(item_id)
    assert got["kind"] == "preference"
    assert got["content"] == "Paolo è intollerante al lattosio"
    assert got["status"] == "approved"
    store.close()


def test_list_approve_delete(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="proposto", status="pending")
    assert [i["id"] for i in store.list_items(status="pending")] == [pid]
    store.approve(pid)
    assert store.get_item(pid)["status"] == "approved"
    assert store.list_items(status="pending") == []
    store.delete_item(pid)
    assert store.get_item(pid) is None
    store.close()
