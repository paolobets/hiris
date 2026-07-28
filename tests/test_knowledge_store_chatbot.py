import sqlite3
from datetime import datetime, timedelta, timezone

from hiris.app.brain.knowledge_store import KnowledgeStore


def _store(tmp_path):
    return KnowledgeStore(str(tmp_path / "knowledge.db"))


def test_chatbot_item_isolated_from_other_agents(tmp_path):
    s = _store(tmp_path)
    a = s.add_item(kind="memory", content="pref A", owner="paolo", chatbot_id="agentA",
                    status="approved", embedding=[0.1, 0.2])
    got_a = s.search(query_vec=[0.1, 0.2], owner="paolo", chatbot_id="agentA", k=5)
    got_b = s.search(query_vec=[0.1, 0.2], owner="paolo", chatbot_id="agentB", k=5)
    assert any(r["id"] == a for r in got_a)
    assert all(r["id"] != a for r in got_b)
    s.close()


def test_home_knowledge_visible_regardless_of_chatbot(tmp_path):
    s = _store(tmp_path)
    k = s.add_item(kind="fact", content="solare 6kWp", owner="home", chatbot_id=None,
                    status="approved", embedding=[0.3, 0.3])
    got = s.search(query_vec=[0.3, 0.3], owner="paolo", chatbot_id="agentA", k=5)
    assert any(r["id"] == k for r in got)
    s.close()


def test_owner_scoped_not_visible_to_other_user(tmp_path):
    s = _store(tmp_path)
    k = s.add_item(kind="fact", content="scadenza TARI", owner="paolo", chatbot_id=None,
                    status="approved", embedding=[0.4, 0.4])
    got = s.search(query_vec=[0.4, 0.4], owner="altro", chatbot_id=None, k=5)
    assert all(r["id"] != k for r in got)
    s.close()


def test_kinds_filter(tmp_path):
    s = _store(tmp_path)
    s.add_item(kind="memory", content="m", owner="home", status="approved", embedding=[0.5, 0.5])
    f = s.add_item(kind="fact", content="f", owner="home", status="approved", embedding=[0.5, 0.5])
    got = s.search(query_vec=[0.5, 0.5], owner="home", kinds=["fact"], k=5)
    assert [r["id"] for r in got if r["kind"] != "fact"] == []
    assert any(r["id"] == f for r in got)
    s.close()


def test_kinds_empty_list_denies_all(tmp_path):
    """An empty kinds list is the deny-all sentinel (e.g. an agent configured
    with knowledge_access.kinds=[] meaning 'no knowledge access at all') and
    must return nothing. Before this fix `if kinds:` treated [] the same as
    None/'all' (falsy => no filter applied), returning every kind instead of
    none."""
    s = _store(tmp_path)
    s.add_item(kind="memory", content="m", owner="home", status="approved", embedding=[0.55, 0.55])
    s.add_item(kind="fact", content="f", owner="home", status="approved", embedding=[0.55, 0.55])
    got = s.search(query_vec=[0.55, 0.55], owner="home", kinds=[], k=5)
    assert got == []
    s.close()


def test_kinds_none_means_no_filter(tmp_path):
    s = _store(tmp_path)
    s.add_item(kind="memory", content="m", owner="home", status="approved", embedding=[0.65, 0.65])
    s.add_item(kind="fact", content="f", owner="home", status="approved", embedding=[0.65, 0.65])
    got = s.search(query_vec=[0.65, 0.65], owner="home", kinds=None, k=5)
    kinds_seen = {r["kind"] for r in got}
    assert {"memory", "fact"} <= kinds_seen
    s.close()


def test_kinds_all_means_no_filter(tmp_path):
    s = _store(tmp_path)
    s.add_item(kind="memory", content="m", owner="home", status="approved", embedding=[0.6, 0.6])
    s.add_item(kind="fact", content="f", owner="home", status="approved", embedding=[0.6, 0.6])
    got = s.search(query_vec=[0.6, 0.6], owner="home", kinds="all", k=5)
    kinds_seen = {r["kind"] for r in got}
    assert {"memory", "fact"} <= kinds_seen
    s.close()


def test_expired_valid_until_excluded(tmp_path):
    s = _store(tmp_path)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    expired = s.add_item(kind="fact", content="scaduto", owner="home", status="approved",
                          embedding=[0.7, 0.7], valid_until=past)
    active = s.add_item(kind="fact", content="valido", owner="home", status="approved",
                         embedding=[0.7, 0.7], valid_until=future)
    got = s.search(query_vec=[0.7, 0.7], owner="home", k=5)
    ids = [r["id"] for r in got]
    assert expired not in ids
    assert active in ids
    s.close()


def test_get_item_includes_chatbot_id(tmp_path):
    s = _store(tmp_path)
    a = s.add_item(kind="memory", content="pref A", owner="paolo", chatbot_id="agentA",
                    status="approved", embedding=[0.1, 0.2])
    row = s.get_item(a)
    assert row["chatbot_id"] == "agentA"
    s.close()


_V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    owner        TEXT NOT NULL DEFAULT 'home',
    title        TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL,
    data         TEXT NOT NULL DEFAULT '{}',
    amount       REAL,
    due_date     TEXT,
    category     TEXT,
    embedding    BLOB,
    sensitivity  TEXT NOT NULL DEFAULT 'normal',
    source       TEXT NOT NULL DEFAULT 'manual',
    source_ref   TEXT,
    confidence   REAL NOT NULL DEFAULT 1.0,
    status       TEXT NOT NULL DEFAULT 'approved',
    valid_from   TEXT,
    valid_until  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""

_V2_SCHEMA = _V1_SCHEMA.replace(
    "updated_at   TEXT NOT NULL\n);",
    "updated_at   TEXT NOT NULL,\n    lens         TEXT\n);",
)


def test_migration_v1_to_v3_ends_with_chatbot_id(tmp_path):
    # Build a genuine pre-Slice3 v1 DB (no lens/chatbot_id column,
    # user_version=1) by hand, mirroring the schema KnowledgeStore used
    # before Slice 3. Reopening it must cascade v1->v2 (adds `lens`) then
    # v2->v3 (renames `lens`->`chatbot_id`), landing on `chatbot_id` with no
    # `lens` column left behind.
    db = str(tmp_path / "knowledge.db")
    conn = sqlite3.connect(db)
    conn.executescript(_V1_SCHEMA)
    now = "2026-01-01T00:00:00Z"
    cur = conn.execute(
        "INSERT INTO knowledge_items(kind, owner, title, content, data, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?)",
        ("fact", "home", "", "x", "{}", now, now),
    )
    old = cur.lastrowid
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    s2 = KnowledgeStore(db)  # reopen triggers v1 -> v2 -> v3 migration chain
    row = s2.get_item(old)
    assert "chatbot_id" in row and row["chatbot_id"] is None
    assert "lens" not in row
    conn2 = sqlite3.connect(db)
    cols = {r[1] for r in conn2.execute("PRAGMA table_info(knowledge_items)").fetchall()}
    assert "chatbot_id" in cols
    assert "lens" not in cols
    conn2.close()
    s2.close()


def test_migration_v2_to_v3_renames_lens_to_chatbot_id_preserving_data(tmp_path):
    """Dedicated v2->v3 test: build a knowledge.db already at user_version=2
    (the real production shape -- a genuine `lens` column with data), open it
    through KnowledgeStore and assert the rename to `chatbot_id` happened and
    every row's data (including the scoping value) survived intact."""
    db = str(tmp_path / "knowledge.db")
    conn = sqlite3.connect(db)
    conn.executescript(_V2_SCHEMA)
    now = "2026-01-01T00:00:00Z"
    cur1 = conn.execute(
        "INSERT INTO knowledge_items"
        "(kind, owner, title, content, data, created_at, updated_at, lens)"
        " VALUES(?,?,?,?,?,?,?,?)",
        ("memory", "home", "", "scoped to agentA", "{}", now, now, "agentA"),
    )
    scoped_id = cur1.lastrowid
    cur2 = conn.execute(
        "INSERT INTO knowledge_items"
        "(kind, owner, title, content, data, created_at, updated_at, lens)"
        " VALUES(?,?,?,?,?,?,?,?)",
        ("fact", "home", "", "shared knowledge", "{}", now, now, None),
    )
    shared_id = cur2.lastrowid
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    s = KnowledgeStore(db)  # reopen triggers v2 -> v3 migration (RENAME COLUMN)

    conn2 = sqlite3.connect(db)
    cols = {r[1] for r in conn2.execute("PRAGMA table_info(knowledge_items)").fetchall()}
    assert "chatbot_id" in cols
    assert "lens" not in cols
    conn2.close()

    scoped = s.get_item(scoped_id)
    assert scoped["chatbot_id"] == "agentA"
    assert scoped["content"] == "scoped to agentA"

    shared = s.get_item(shared_id)
    assert shared["chatbot_id"] is None
    assert shared["content"] == "shared knowledge"

    s.close()


def test_migration_v2_to_v3_idempotent_when_reopened_twice(tmp_path):
    """Reopening an already-migrated (v3) DB must not fail or re-run the
    RENAME COLUMN (which would raise since `lens` no longer exists)."""
    db = str(tmp_path / "knowledge.db")
    s1 = KnowledgeStore(db)
    s1.add_item(kind="memory", content="x", chatbot_id="agentA")
    s1.close()

    s2 = KnowledgeStore(db)  # second open at already-v3: must be a no-op
    items = s2.list_items(limit=10)
    assert len(items) == 1
    assert items[0]["chatbot_id"] == "agentA"
    s2.close()


def test_chatbot_memory_not_leaked_across_users_of_same_agent(tmp_path):
    """Two different HA users chatting with the SAME agent (same chatbot_id)
    must not see each other's chatbot-scoped memory. Before the owner-scope
    fix, the search WHERE was `(lens=:lens OR (lens IS NULL AND (owner=...
    )))` — once `lens` matched, `owner` was ignored entirely, leaking
    userA's memory to userB. The fix ANDs the owner-scope with the
    chatbot_id clause."""
    s = _store(tmp_path)
    a = s.add_item(kind="memory", content="userA pref 21C", owner="userA",
                    chatbot_id="agentA", status="approved", embedding=[0.2, 0.2])
    got_by_a = s.search(query_vec=[0.2, 0.2], owner="userA", chatbot_id="agentA", k=5)
    got_by_b = s.search(query_vec=[0.2, 0.2], owner="userB", chatbot_id="agentA", k=5)
    assert any(r["id"] == a for r in got_by_a)
    assert all(r["id"] != a for r in got_by_b)
    s.close()


def test_home_owned_chatbot_memory_shared_across_users_of_same_agent(tmp_path):
    """A chatbot-scoped item explicitly owned by 'home' is shared across
    users of that agent (owner='home' still matches the
    (owner=? OR owner='home') clause)."""
    s = _store(tmp_path)
    h = s.add_item(kind="memory", content="shared agent note", owner="home",
                    chatbot_id="agentA", status="approved", embedding=[0.25, 0.25])
    got_by_a = s.search(query_vec=[0.25, 0.25], owner="userA", chatbot_id="agentA", k=5)
    got_by_b = s.search(query_vec=[0.25, 0.25], owner="userB", chatbot_id="agentA", k=5)
    assert any(r["id"] == h for r in got_by_a)
    assert any(r["id"] == h for r in got_by_b)
    s.close()


def test_backward_compat_chatbot_id_none_equivalent_to_previous_owner_scope(tmp_path):
    """With chatbot_id=None, the unified WHERE must give identical results
    to the pre-Slice3 scope filter (owner=? OR owner='home')."""
    s = _store(tmp_path)
    mine = s.add_item(kind="fact", content="mio", owner="paolo", status="approved",
                       embedding=[0.9, 0.1])
    home = s.add_item(kind="fact", content="casa", owner="home", status="approved",
                       embedding=[0.9, 0.1])
    other = s.add_item(kind="fact", content="altrui", owner="altro", status="approved",
                        embedding=[0.9, 0.1])
    got = s.search(query_vec=[0.9, 0.1], owner="paolo", k=5)
    ids = {r["id"] for r in got}
    assert mine in ids
    assert home in ids
    assert other not in ids
    s.close()
