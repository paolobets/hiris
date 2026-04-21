import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from hiris.app.chat_store import load_history, append_messages, clear_history, _path


def test_load_history_returns_empty_when_no_file(tmp_path):
    result = load_history("agent1", str(tmp_path))
    assert result == []


def test_append_and_load_roundtrip(tmp_path):
    msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    append_messages("agent1", msgs, str(tmp_path))
    loaded = load_history("agent1", str(tmp_path))
    assert loaded == msgs


def test_load_strips_timestamps_from_output(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "test"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert "timestamp" not in result[0]


def test_load_filters_messages_older_than_30_days(tmp_path):
    path = _path("agent1", str(tmp_path))
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "schema_version": 1, "agent_id": "agent1",
        "messages": [
            {"role": "user", "content": "old", "timestamp": old_ts},
            {"role": "assistant", "content": "new", "timestamp": new_ts},
        ]
    }
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    result = load_history("agent1", str(tmp_path))
    assert len(result) == 1
    assert result[0]["content"] == "new"


def test_append_messages_accumulates(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "first"}], str(tmp_path))
    append_messages("agent1", [{"role": "assistant", "content": "second"}], str(tmp_path))
    result = load_history("agent1", str(tmp_path))
    assert len(result) == 2
    assert result[0]["content"] == "first"
    assert result[1]["content"] == "second"


def test_clear_history_removes_file(tmp_path):
    append_messages("agent1", [{"role": "user", "content": "x"}], str(tmp_path))
    clear_history("agent1", str(tmp_path))
    assert load_history("agent1", str(tmp_path)) == []


def test_clear_history_noop_when_no_file(tmp_path):
    clear_history("agent1", str(tmp_path))  # must not raise


def test_load_history_returns_empty_on_corrupt_file(tmp_path):
    path = _path("agent1", str(tmp_path))
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w") as f:
        f.write("not json{{{")
    result = load_history("agent1", str(tmp_path))
    assert result == []


def test_different_agents_have_separate_histories(tmp_path):
    append_messages("agent-a", [{"role": "user", "content": "for A"}], str(tmp_path))
    append_messages("agent-b", [{"role": "user", "content": "for B"}], str(tmp_path))
    assert load_history("agent-a", str(tmp_path))[0]["content"] == "for A"
    assert load_history("agent-b", str(tmp_path))[0]["content"] == "for B"
