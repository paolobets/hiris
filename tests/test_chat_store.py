import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

from hiris.app.chat_store import (
    ChatStore,
    append_messages,
    clear_history,
    close_all_stores,
    count_user_turns,
    get_past_summaries,
    load_history,
)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture(autouse=True)
def reset_stores():
    """Ensure module-level store cache is clean between tests."""
    close_all_stores()
    yield
    close_all_stores()


# ---------------------------------------------------------------------------
# Basic append / load / clear (backward-compat API)
# ---------------------------------------------------------------------------

def test_load_history_empty_when_no_data(tmp_path):
    assert load_history("agent1", str(tmp_path)) == []


def test_append_and_load_roundtrip(tmp_path):
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    append_messages("agent1", msgs, str(tmp_path))
    loaded = load_history("agent1", str(tmp_path))
    assert loaded == msgs


def test_load_strips_timestamps_from_output(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "test"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert "timestamp" not in result[0]


def test_append_accumulates(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "first"}], str(tmp_path))
    append_messages("agent1", [{"role": "assistant", "content": "second"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert len(result) == 2
    assert result[0]["content"] == "first"
    assert result[1]["content"] == "second"


def test_clear_history(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "x"}], str(tmp_path))
    clear_history("agent1", str(tmp_path))
    assert load_history("agent1", str(tmp_path)) == []


def test_clear_history_noop_when_empty(tmp_path):
    clear_history("agent1", str(tmp_path))  # must not raise


def test_different_agents_have_separate_histories(tmp_path):
    append_messages("agent-a", [{"role": "user", "content": "for A"}], str(tmp_path))
    append_messages("agent-b", [{"role": "user", "content": "for B"}], str(tmp_path))
    assert load_history("agent-a", str(tmp_path))[0]["content"] == "for A"
    assert load_history("agent-b", str(tmp_path))[0]["content"] == "for B"


# ---------------------------------------------------------------------------
# 30-day retention filter
# ---------------------------------------------------------------------------

def test_load_filters_messages_older_than_30_days(tmp_path):
    import hiris.app.chat_store as cs
    cs.HISTORY_RETENTION_DAYS = 30
    try:
        store = ChatStore(str(tmp_path / "chat_history.db"))
        old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime(_TS_FMT)
        new_ts = datetime.now(timezone.utc).strftime(_TS_FMT)
        # Inject a session and old+new messages directly
        session_id = "sess-old"
        conn = store._conn
        conn.execute(
            "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at) VALUES(?,?,?,?)",
            (session_id, "agent1", old_ts, new_ts),
        )
        conn.execute(
            "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
            ("agent1", session_id, "user", "old msg", old_ts),
        )
        conn.execute(
            "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
            ("agent1", session_id, "assistant", "new msg", new_ts),
        )
        conn.commit()
        result = store.load_context("agent1")
        contents = [m["content"] for m in result]
        assert "old msg" not in contents
        assert "new msg" in contents
        store.close()
    finally:
        cs.HISTORY_RETENTION_DAYS = 90


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def test_new_session_after_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    chatbot_id = "agent-gap"
    # Create a first session with a timestamp > 2h ago
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid1 = "sess-stale"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (sid1, chatbot_id, old_ts, old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        (chatbot_id, sid1, "assistant", "old reply", old_ts),
    )
    conn.commit()

    # Appending now should start a new session
    store.append(chatbot_id, [{"role": "user", "content": "fresh"}])

    # The old session should now be closed (summary set)
    row = conn.execute(
        "SELECT summary FROM chat_sessions WHERE session_id = ?", (sid1,)
    ).fetchone()
    assert row["summary"] is not None

    # New session message should be in a different session
    active = conn.execute(
        "SELECT session_id FROM chat_sessions WHERE chatbot_id = ? AND summary IS NULL",
        (chatbot_id,),
    ).fetchone()
    assert active is not None
    assert active["session_id"] != sid1
    store.close()


def test_active_session_reused_within_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.append("ag", [{"role": "user", "content": "msg1"}])
    store.append("ag", [{"role": "assistant", "content": "reply1"}])
    conn = store._conn
    sessions = conn.execute("SELECT * FROM chat_sessions WHERE chatbot_id = 'ag'").fetchall()
    assert len(sessions) == 1  # still same session
    store.close()


def test_load_context_returns_empty_for_stale_session(tmp_path):
    """load_context must return [] if the session gap has elapsed (read path)."""
    store = ChatStore(str(tmp_path / "chat_history.db"))
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid = "stale-read"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (sid, "ag", old_ts, old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        ("ag", sid, "user", "old", old_ts),
    )
    conn.commit()
    # load_context must treat stale session as empty — no side effects
    assert store.load_context("ag") == []
    assert store.count_user_turns("ag") == 0
    # Session is still "open" (not closed) since we only read
    still_open = conn.execute(
        "SELECT summary FROM chat_sessions WHERE session_id = ?", (sid,)
    ).fetchone()
    assert still_open["summary"] is None
    store.close()


# ---------------------------------------------------------------------------
# Past summaries
# ---------------------------------------------------------------------------

def test_get_past_summaries_returns_closed_sessions(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    chatbot_id = "agent-mem"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    for i in range(4):
        sid = f"closed-{i}"
        store._conn.execute(
            "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at, summary) "
            "VALUES(?,?,?,?,?)",
            (sid, chatbot_id, ts, ts, f"summary {i}"),
        )
    store._conn.commit()
    summaries = store.get_past_summaries(chatbot_id, n=3)
    assert len(summaries) == 3
    assert all(s["summary"] is not None for s in summaries)
    store.close()


def test_get_past_summaries_empty_when_no_closed_sessions(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.append("agent1", [{"role": "user", "content": "hi"}])
    summaries = store.get_past_summaries("agent1")
    assert summaries == []
    store.close()


def test_module_get_past_summaries(tmp_path):
    append_messages("ag", [{"role": "user", "content": "hi"}], str(tmp_path))
    result = get_past_summaries("ag", str(tmp_path))
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# count_user_turns
# ---------------------------------------------------------------------------

def test_count_user_turns(tmp_path):
    append_messages("ag", [{"role": "user", "content": "q1"}], str(tmp_path))
    append_messages("ag", [{"role": "assistant", "content": "a1"}], str(tmp_path))
    append_messages("ag", [{"role": "user", "content": "q2"}], str(tmp_path))
    assert count_user_turns("ag", str(tmp_path)) == 2


def test_count_user_turns_zero_when_empty(tmp_path):
    assert count_user_turns("ag", str(tmp_path)) == 0


# ---------------------------------------------------------------------------
# JSON migration
# ---------------------------------------------------------------------------

def test_migrate_from_json(tmp_path):
    chatbot_id = "migrated-agent"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    data = {
        "schema_version": 1,
        "agent_id": chatbot_id,  # legacy JSON key, migrate_from_json still reads this literal
        "messages": [
            {"role": "user", "content": "q", "timestamp": ts},
            {"role": "assistant", "content": "a", "timestamp": ts},
        ],
    }
    json_path = tmp_path / f"chat_history_{chatbot_id}.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.migrate_from_json(str(tmp_path))

    # Migrated history should appear as a closed session
    summaries = store.get_past_summaries(chatbot_id)
    assert len(summaries) == 1
    assert summaries[0]["summary"] == "a"
    store.close()


def test_migrate_skips_already_migrated(tmp_path):
    chatbot_id = "ag-skip"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    data = {"schema_version": 1, "agent_id": chatbot_id, "messages": [
        {"role": "user", "content": "x", "timestamp": ts},
    ]}
    json_path = tmp_path / f"chat_history_{chatbot_id}.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.migrate_from_json(str(tmp_path))
    store.migrate_from_json(str(tmp_path))  # second call must be idempotent

    conn = store._conn
    count = conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE chatbot_id = ?", (chatbot_id,)).fetchone()[0]
    assert count == 1
    store.close()


# ---------------------------------------------------------------------------
# Summary truncation
# ---------------------------------------------------------------------------

def test_summary_truncated_to_200_chars(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    long_text = "x" * 300
    ts_old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid = "sess-long"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, chatbot_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (sid, "ag", ts_old, ts_old),
    )
    conn.execute(
        "INSERT INTO chat_messages(chatbot_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        ("ag", sid, "assistant", long_text, ts_old),
    )
    conn.commit()

    store.append("ag", [{"role": "user", "content": "new"}])

    row = conn.execute("SELECT summary FROM chat_sessions WHERE session_id = ?", (sid,)).fetchone()
    assert row["summary"] is not None
    assert len(row["summary"]) <= 201  # 200 + ellipsis char
    store.close()


# ---------------------------------------------------------------------------
# Regression: filter toxic assistant turns on history load (v0.9.9)
# Pre-v0.9.8, some Mistral/Hermes routings on OpenRouter leaked tool calls as
# raw text content (e.g. `get_ha_healthיׂ{...}`); the chat handler also
# persisted generic synthetic errors ("Errore temporaneo del servizio AI...").
# Both poison the history sent to subsequent turns. load_history must purge
# them so existing users recover automatically without manual cleanup.
# ---------------------------------------------------------------------------

from hiris.app.chat_store import _purge_toxic_turns, _is_toxic_assistant


def test_is_toxic_detects_mistral_leak_pattern():
    assert _is_toxic_assistant("get_ha_healthיׂ{\"sections\":[\"all\"]}") is True
    assert _is_toxic_assistant("await_user_confirmationיׄ**Confermi?**") is True
    assert _is_toxic_assistant("get_ha_healthớ{}") is True


def test_is_toxic_detects_synthetic_error_strings():
    assert _is_toxic_assistant("Errore temporaneo del servizio AI. Riprova tra poco.") is True
    assert _is_toxic_assistant("Rate limit — riprova tra poco.") is True
    assert _is_toxic_assistant("") is True
    assert _is_toxic_assistant(
        "Crediti OpenRouter insufficienti per max_tokens=4096. Riduci..."
    ) is True
    assert _is_toxic_assistant(
        "Il modello selezionato non gestisce correttamente i tool tramite questo provider..."
    ) is True


def test_is_toxic_does_not_match_legit_responses():
    legit = [
        "Tutto ok, la casa è in buone condizioni.",
        "La temperatura in salotto è 21°C.",
        "Posso aiutarti — dimmi cosa serve.",
        "**Riepilogo consumi:**\n- Potenza: 550W",
    ]
    for s in legit:
        assert _is_toxic_assistant(s) is False, f"false positive on {s!r}"


def test_purge_drops_toxic_assistant_and_preceding_user():
    msgs = [
        {"role": "user", "content": "verifica salute HA"},
        {"role": "assistant", "content": "get_ha_healthיׂ{\"sections\":[\"all\"]}"},
        {"role": "user", "content": "che luci hai?"},
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "Ciao! Come stai?"},
    ]
    out = _purge_toxic_turns(msgs)
    assert out == [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "Ciao! Come stai?"},
    ]


def test_purge_preserves_clean_history_unchanged():
    msgs = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
        {"role": "assistant", "content": "A2"},
    ]
    assert _purge_toxic_turns(msgs) == msgs


def test_purge_handles_leading_toxic_assistant_with_no_preceding_user():
    """Edge case: assistant comes first (shouldn't happen but be safe)."""
    msgs = [
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "ciao!"},
    ]
    out = _purge_toxic_turns(msgs)
    assert out == [
        {"role": "user", "content": "ciao"},
        {"role": "assistant", "content": "ciao!"},
    ]


def test_load_history_purges_pre_v098_corrupted_history(tmp_path):
    """End-to-end: existing chat with leaked tool calls + error messages comes
    out clean, simulating what happens for users upgrading from v0.9.7."""
    msgs = [
        {"role": "user", "content": "check HA"},
        {"role": "assistant", "content": "get_ha_healthיׂ{\"sections\":[\"all\"]}"},
        {"role": "user", "content": "luci?"},
        {"role": "assistant", "content": "Errore temporaneo del servizio AI. Riprova tra poco."},
        {"role": "user", "content": "ora?"},
        {"role": "assistant", "content": "**Tutto ok**"},
    ]
    append_messages("ag-corrupt", msgs, str(tmp_path))
    out = load_history("ag-corrupt", str(tmp_path))
    # Two corrupted pairs dropped, only the last clean one survives
    assert out == [
        {"role": "user", "content": "ora?"},
        {"role": "assistant", "content": "**Tutto ok**"},
    ]


# ---------------------------------------------------------------------------
# SP-4a Task 6: agent_id -> chatbot_id schema migration (v1 -> v2)
# ---------------------------------------------------------------------------

def _make_legacy_v1_db(db_path: str) -> None:
    """Build a v1 chat_history.db exactly as pre-Task-6 HIRIS would have
    left it: agent_id columns + idx_msg_agent/idx_sess_agent indexes, no
    user_version stamped (pre-versioning DB, same as init_schema's
    'pre_tables > 0 and user_version == 0' baseline-to-1 case)."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE chat_messages ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, "
        "session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, "
        "timestamp TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE chat_sessions ("
        "session_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, "
        "started_at TEXT NOT NULL, last_msg_at TEXT NOT NULL, summary TEXT)"
    )
    conn.execute("CREATE INDEX idx_msg_agent ON chat_messages(agent_id, timestamp)")
    conn.execute("CREATE INDEX idx_sess_agent ON chat_sessions(agent_id, last_msg_at)")
    conn.execute(
        "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at, summary) "
        "VALUES('sess-legacy', 'legacy-bot', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:05:00Z', 'old summary')"
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) "
        "VALUES('legacy-bot', 'sess-legacy', 'user', 'ciao', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) "
        "VALUES('legacy-bot', 'sess-legacy', 'assistant', 'salve', '2026-01-01T00:01:00Z')"
    )
    conn.commit()
    conn.close()


def test_migration_renames_agent_id_column_and_indexes_preserving_data(tmp_path):
    """Opening a legacy v1 db (agent_id columns + idx_msg_agent/idx_sess_agent)
    through ChatStore must: rename both columns to chatbot_id, drop the old
    indexes, create idx_msg_chatbot/idx_sess_chatbot, preserve every row, and
    leave the db queryable via the new column name -- with no data loss."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v1_db(db_path)

    store = ChatStore(db_path)
    try:
        conn = store._conn

        msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        sess_cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        assert "chatbot_id" in msg_cols and "agent_id" not in msg_cols
        assert "chatbot_id" in sess_cols and "agent_id" not in sess_cols

        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_msg_chatbot" in indexes
        assert "idx_sess_chatbot" in indexes
        assert "idx_msg_agent" not in indexes
        assert "idx_sess_agent" not in indexes

        # Data preserved, queryable via the new column name.
        msg_row = conn.execute(
            "SELECT chatbot_id, role, content FROM chat_messages ORDER BY id"
        ).fetchall()
        assert [dict(r) for r in msg_row] == [
            {"chatbot_id": "legacy-bot", "role": "user", "content": "ciao"},
            {"chatbot_id": "legacy-bot", "role": "assistant", "content": "salve"},
        ]
        sess_row = conn.execute(
            "SELECT chatbot_id, summary FROM chat_sessions WHERE session_id = 'sess-legacy'"
        ).fetchone()
        assert dict(sess_row) == {"chatbot_id": "legacy-bot", "summary": "old summary"}

        # user_version stamped at the latest schema version.
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2

        # The public, chatbot_id-keyed API works against the migrated rows too.
        summaries = store.get_past_summaries("legacy-bot")
        assert len(summaries) == 1
        assert summaries[0]["summary"] == "old summary"
    finally:
        store.close()


def test_migration_is_idempotent_on_reopen(tmp_path):
    """A second ChatStore open (simulating an add-on restart post-migration)
    must not fail or re-run the rename against an already-migrated db."""
    db_path = str(tmp_path / "chat_history.db")
    _make_legacy_v1_db(db_path)

    store1 = ChatStore(db_path)
    store1.close()

    store2 = ChatStore(db_path)  # must not raise
    try:
        conn = store2._conn
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        assert "chatbot_id" in cols and "agent_id" not in cols
        count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        assert count == 2  # rows not duplicated by re-running migration
    finally:
        store2.close()
