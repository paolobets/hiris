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
    store = ChatStore(str(tmp_path / "chat_history.db"))
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime(_TS_FMT)
    new_ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    # Inject a session and old+new messages directly
    session_id = "sess-old"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (session_id, "agent1", old_ts, new_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        ("agent1", session_id, "user", "old msg", old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        ("agent1", session_id, "assistant", "new msg", new_ts),
    )
    conn.commit()
    result = store.load_context("agent1")
    contents = [m["content"] for m in result]
    assert "old msg" not in contents
    assert "new msg" in contents
    store.close()


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def test_new_session_after_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    agent_id = "agent-gap"
    # Create a first session with a timestamp > 2h ago
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(_TS_FMT)
    sid1 = "sess-stale"
    conn = store._conn
    conn.execute(
        "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (sid1, agent_id, old_ts, old_ts),
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        (agent_id, sid1, "assistant", "old reply", old_ts),
    )
    conn.commit()

    # Appending now should start a new session
    store.append(agent_id, [{"role": "user", "content": "fresh"}])

    # The old session should now be closed (summary set)
    row = conn.execute(
        "SELECT summary FROM chat_sessions WHERE session_id = ?", (sid1,)
    ).fetchone()
    assert row["summary"] is not None

    # New session message should be in a different session
    active = conn.execute(
        "SELECT session_id FROM chat_sessions WHERE agent_id = ? AND summary IS NULL",
        (agent_id,),
    ).fetchone()
    assert active is not None
    assert active["session_id"] != sid1
    store.close()


def test_active_session_reused_within_gap(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.append("ag", [{"role": "user", "content": "msg1"}])
    store.append("ag", [{"role": "assistant", "content": "reply1"}])
    conn = store._conn
    sessions = conn.execute("SELECT * FROM chat_sessions WHERE agent_id = 'ag'").fetchall()
    assert len(sessions) == 1  # still same session
    store.close()


# ---------------------------------------------------------------------------
# Past summaries
# ---------------------------------------------------------------------------

def test_get_past_summaries_returns_closed_sessions(tmp_path):
    store = ChatStore(str(tmp_path / "chat_history.db"))
    agent_id = "agent-mem"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    for i in range(4):
        sid = f"closed-{i}"
        store._conn.execute(
            "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at, summary) "
            "VALUES(?,?,?,?,?)",
            (sid, agent_id, ts, ts, f"summary {i}"),
        )
    store._conn.commit()
    summaries = store.get_past_summaries(agent_id, n=3)
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
    agent_id = "migrated-agent"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    data = {
        "schema_version": 1,
        "agent_id": agent_id,
        "messages": [
            {"role": "user", "content": "q", "timestamp": ts},
            {"role": "assistant", "content": "a", "timestamp": ts},
        ],
    }
    json_path = tmp_path / f"chat_history_{agent_id}.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.migrate_from_json(str(tmp_path))

    # Migrated history should appear as a closed session
    summaries = store.get_past_summaries(agent_id)
    assert len(summaries) == 1
    assert summaries[0]["summary"] == "a"
    store.close()


def test_migrate_skips_already_migrated(tmp_path):
    agent_id = "ag-skip"
    ts = datetime.now(timezone.utc).strftime(_TS_FMT)
    data = {"schema_version": 1, "agent_id": agent_id, "messages": [
        {"role": "user", "content": "x", "timestamp": ts},
    ]}
    json_path = tmp_path / f"chat_history_{agent_id}.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    store = ChatStore(str(tmp_path / "chat_history.db"))
    store.migrate_from_json(str(tmp_path))
    store.migrate_from_json(str(tmp_path))  # second call must be idempotent

    conn = store._conn
    count = conn.execute("SELECT COUNT(*) FROM chat_sessions WHERE agent_id = ?", (agent_id,)).fetchone()[0]
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
        "INSERT INTO chat_sessions(session_id, agent_id, started_at, last_msg_at) VALUES(?,?,?,?)",
        (sid, "ag", ts_old, ts_old),
    )
    conn.execute(
        "INSERT INTO chat_messages(agent_id, session_id, role, content, timestamp) VALUES(?,?,?,?,?)",
        ("ag", sid, "assistant", long_text, ts_old),
    )
    conn.commit()

    store.append("ag", [{"role": "user", "content": "new"}])

    row = conn.execute("SELECT summary FROM chat_sessions WHERE session_id = ?", (sid,)).fetchone()
    assert row["summary"] is not None
    assert len(row["summary"]) <= 201  # 200 + ellipsis char
    store.close()
