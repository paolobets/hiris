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
