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


def test_search_ranks_by_cosine_and_excludes_sensitive(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="fact", content="vicino", embedding=[1.0, 0.0])
    store.add_item(kind="fact", content="lontano", embedding=[0.0, 1.0])
    store.add_item(kind="fact", content="segreto", embedding=[1.0, 0.0],
                   sensitivity="sensitive")
    res = store.search(query_vec=[1.0, 0.0], k=5, allow_sensitive=False)
    contents = [r["content"] for r in res]
    assert contents[0] == "vicino"          # cosine = 1.0
    assert "segreto" not in contents        # sensitive escluso
    store.close()


def test_structured_queries(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(kind="obligation", content="TARI", due_date="2026-07-01")
    store.add_item(kind="obligation", content="Bollo", due_date="2026-12-31")
    store.add_item(kind="expense", content="Spesa", amount=42.0, category="cibo")
    store.add_item(kind="expense", content="Cena", amount=8.0, category="cibo")

    due = store.upcoming_obligations(before="2026-08-01")
    assert [d["content"] for d in due] == ["TARI"]

    agg = store.expenses_by_category()
    assert agg["cibo"] == 50.0
    store.close()
