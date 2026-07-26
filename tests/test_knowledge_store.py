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


def test_list_items_owner_scoping_includes_home(tmp_path):
    """owner filter on list_items must mean 'this owner OR home', mirroring
    search()'s unified scoping (review B/#16 IDOR fix)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")
    b_id = store.add_item(kind="fact", content="B", owner="userB", status="pending")
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")

    ids_for_a = {i["id"] for i in store.list_items(status="pending", owner="userA")}
    assert ids_for_a == {a_id, home_id}
    assert b_id not in ids_for_a

    store.close()


def test_approve_rejects_cross_owner_and_leaves_item_unchanged(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")

    ok = store.approve(a_id, owner="userB")
    assert ok is False
    assert store.get_item(a_id)["status"] == "pending"

    ok2 = store.approve(a_id, owner="userA")
    assert ok2 is True
    assert store.get_item(a_id)["status"] == "approved"

    store.close()


def test_approve_allows_home_item_for_any_owner(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    home_id = store.add_item(kind="fact", content="shared", owner="home", status="pending")
    ok = store.approve(home_id, owner="anyUser")
    assert ok is True
    assert store.get_item(home_id)["status"] == "approved"
    store.close()


def test_delete_item_rejects_cross_owner_and_leaves_item_unchanged(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a_id = store.add_item(kind="fact", content="A", owner="userA", status="pending")

    ok = store.delete_item(a_id, owner="userB")
    assert ok is False
    assert store.get_item(a_id) is not None

    ok2 = store.delete_item(a_id, owner="userA")
    assert ok2 is True
    assert store.get_item(a_id) is None

    store.close()


def test_delete_item_purges_document_chunks(tmp_path):
    """Backlog #5: delete_item must also drop the item's document_chunks, so a
    deleted document leaves no orphan chunks (the Mayan ingest rollback relies
    on this)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    item_id = store.add_item(kind="document", content="Doc", owner="home",
                             source="mayan", source_ref="900", status="approved")
    store.add_document_chunk(item_id=item_id, mayan_doc_id="900",
                             chunk_index=0, content="pezzo", embedding=[0.1, 0.2])
    assert store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 1

    assert store.delete_item(item_id) is True
    assert store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 0
    store.close()


def test_approve_delete_owner_none_preserves_unscoped_behavior(tmp_path):
    """Internal callers (brain_trace, history_digest) call approve/delete_item
    without an owner arg -- must keep acting unconditionally (backward compat)."""
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    pid = store.add_item(kind="fact", content="x", owner="userA", status="pending")
    ok = store.approve(pid)
    assert ok is True
    assert store.get_item(pid)["status"] == "approved"
    ok2 = store.delete_item(pid)
    assert ok2 is True
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


def test_upcoming_obligations_returns_parsed_data(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    store.add_item(
        kind="obligation", content="IMU",
        due_date="2026-06-30", data={"note": "prima rata"},
    )
    store.add_item(
        kind="obligation", content="Bolletta gas",
        due_date="2026-07-15", data={"note": "bolletta estiva"},
    )
    due = store.upcoming_obligations(before="2026-07-01")
    assert len(due) == 1
    item = due[0]
    assert "data" in item, "upcoming_obligations deve restituire il campo 'data'"
    assert isinstance(item["data"], dict), "'data' deve essere un dict"
    assert item["data"] == {"note": "prima rata"}
    store.close()


def test_links_and_neighbors(tmp_path):
    store = KnowledgeStore(str(tmp_path / "brain.db"))
    a = store.add_item(kind="expense", content="Cena")
    b = store.add_item(kind="preference", content="Pizza")
    store.add_link(src_id=a, dst_id=b, relation="related")
    nb = store.neighbors(a)
    assert [n["content"] for n in nb] == ["Pizza"]
    store.close()


def test_document_chunks_add_search_exists(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    doc = store.add_item(kind="document", content="Estratto conto giugno",
                         source="mayan", source_ref="42", sensitivity="sensitive")
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=0,
                             content="bonifico 50 euro", embedding=[1.0, 0.0])
    store.add_document_chunk(item_id=doc, mayan_doc_id="42", chunk_index=1,
                             content="prelievo bancomat", embedding=[0.0, 1.0])
    assert store.document_exists("42") is True
    assert store.document_exists("99") is False
    hits = store.search_chunks(query_vec=[1.0, 0.0], k=1, allow_sensitive=True)
    assert hits[0]["content"] == "bonifico 50 euro"
    assert hits[0]["sensitivity"] == "sensitive"
    store.close()
