"""Prove that stores migrated to the shared storage helper open in WAL mode
and stamp user_version=1."""
import os
import pytest


def test_history_store_opens_in_wal(tmp_path):
    from hiris.app.history.store import HistoryStore

    s = HistoryStore(str(tmp_path / "h.db"))
    assert s._conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert s._conn.execute("PRAGMA user_version").fetchone()[0] == 1
    s.close()


def test_knowledge_store_opens_in_wal(tmp_path):
    from hiris.app.brain.knowledge_store import KnowledgeStore

    s = KnowledgeStore(str(tmp_path / "k.db"))
    assert s._conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert s._conn.execute("PRAGMA user_version").fetchone()[0] == 1
    s.close()
