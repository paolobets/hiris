import os
import sqlite3
import struct

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.memory_migration import migrate_agent_memories


def _seed_legacy(data_dir, rows):
    """Create a legacy hiris_memory.db with the real agent_memories schema
    (the schema formerly defined by the now-removed proxy/memory_store.py,
    Slice 3 Task 4) and insert `rows`, each a tuple (agent_id, content,
    tags_json, embedding_blob_or_None, created_at, expires_at_or_None)."""
    db = os.path.join(data_dir, "hiris_memory.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE agent_memories (id INTEGER PRIMARY KEY, agent_id TEXT, "
        "content TEXT, tags TEXT, embedding BLOB, created_at TEXT, expires_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO agent_memories"
        " (agent_id, content, tags, embedding, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def _by_chatbot(store, chatbot_id, kind="memory"):
    return [it for it in store.list_items(kind=kind, limit=200) if it["chatbot_id"] == chatbot_id]


def test_migration_moves_rows_and_is_idempotent(tmp_path):
    d = str(tmp_path)
    _seed_legacy(d, [
        ("agentA", "memoria vecchia", "[]", None,
         "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
    ])
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    n = migrate_agent_memories(d, store)
    assert n == 1

    # the memory is now a chatbot-scoped item, recallable/gettable for that agent
    matches = _by_chatbot(store, "agentA")
    assert len(matches) == 1
    item = matches[0]
    assert item["content"] == "memoria vecchia"
    assert item["owner"] == "home"
    assert item["status"] == "approved"
    assert item["sensitivity"] == "normal"
    assert item["source"] == "migrated"
    assert item["valid_until"] == "2027-01-01T00:00:00Z"
    full = store.get_item(item["id"])
    assert full is not None and full["chatbot_id"] == "agentA"

    # legacy db renamed -> a second run is a no-op
    assert not os.path.exists(os.path.join(d, "hiris_memory.db"))
    assert os.path.exists(os.path.join(d, "hiris_memory.db.migrated"))
    assert migrate_agent_memories(d, store) == 0
    # and no duplicate got created by the no-op second run
    assert len(_by_chatbot(store, "agentA")) == 1
    store.close()


def test_migration_keeps_null_embedding_rows(tmp_path):
    """NULL-embedding rows must be migrated, never dropped."""
    d = str(tmp_path)
    _seed_legacy(d, [
        ("agentB", "no vector here", "[]", None, "2026-02-01T00:00:00Z", None),
    ])
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    n = migrate_agent_memories(d, store)
    assert n == 1

    matches = _by_chatbot(store, "agentB")
    assert len(matches) == 1
    assert matches[0]["content"] == "no vector here"
    assert matches[0]["valid_until"] is None
    store.close()


def test_migration_decodes_real_embedding_and_tags(tmp_path):
    d = str(tmp_path)
    vec = [0.1, 0.2, 0.3]
    blob = struct.pack(f"{len(vec)}f", *vec)
    _seed_legacy(d, [
        ("agentC", "with vector", '["pref"]', blob, "2026-03-01T00:00:00Z", None),
    ])
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    n = migrate_agent_memories(d, store)
    assert n == 1

    # recallable via vector search using the decoded embedding
    got = store.search(query_vec=vec, owner="home", k=5)
    assert any("with vector" in (r.get("content") or "") for r in got)

    # tags preserved into `data`
    match = _by_chatbot(store, "agentC")[0]
    assert match["data"].get("tags") == ["pref"]
    store.close()


def test_migration_handles_corrupt_embedding_blob_without_dropping_row(tmp_path):
    """A blob that fails to decode must not cause the row to be lost --
    it is migrated with embedding=None instead."""
    d = str(tmp_path)
    _seed_legacy(d, [
        ("agentD", "corrupt blob", "[]", b"\x01\x02\x03", "2026-04-01T00:00:00Z", None),
    ])
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    n = migrate_agent_memories(d, store)
    assert n == 1

    matches = _by_chatbot(store, "agentD")
    assert len(matches) == 1
    assert matches[0]["content"] == "corrupt blob"
    store.close()


def test_migration_multiple_rows_and_agents(tmp_path):
    d = str(tmp_path)
    _seed_legacy(d, [
        ("agentA", "m1", "[]", None, "2026-01-01T00:00:00Z", None),
        ("agentA", "m2", "[]", None, "2026-01-02T00:00:00Z", None),
        ("agentE", "m3", "[]", None, "2026-01-03T00:00:00Z", None),
    ])
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    n = migrate_agent_memories(d, store)
    assert n == 3
    assert len(_by_chatbot(store, "agentA")) == 2
    assert len(_by_chatbot(store, "agentE")) == 1
    store.close()


def test_migration_no_legacy_db_is_noop(tmp_path):
    d = str(tmp_path)
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    assert migrate_agent_memories(d, store) == 0
    assert store.list_items(kind="memory") == []
    store.close()


def test_migration_already_migrated_marker_short_circuits(tmp_path):
    """If a hiris_memory.db.migrated marker is already present (e.g. from a
    previous startup), migration must not run even if a hiris_memory.db
    happens to exist alongside it (e.g. left over from before MemoryStore
    was retired in Slice 3 Task 4)."""
    d = str(tmp_path)
    _seed_legacy(d, [
        ("agentF", "should be ignored", "[]", None, "2026-05-01T00:00:00Z", None),
    ])
    marker = os.path.join(d, "hiris_memory.db.migrated")
    with open(marker, "wb"):
        pass
    store = KnowledgeStore(os.path.join(d, "knowledge.db"))
    assert migrate_agent_memories(d, store) == 0
    assert store.list_items(kind="memory") == []
    store.close()
