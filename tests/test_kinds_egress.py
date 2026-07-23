"""Slice 3 Task 6 — kinds egress: handle_recall_knowledge forwards `kinds` to
KnowledgeStore.search, closing the dead-config on Agent.knowledge_access.kinds.

Also covers the Task 1 review Low: a plain string kinds="fact" (not "all")
must behave like ["fact"], not be iterated character-by-character.
"""
import pytest
from unittest.mock import AsyncMock

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.tools.knowledge_tools import handle_recall_knowledge


@pytest.mark.asyncio
async def test_recall_knowledge_kinds_list_filters_out_other_kinds(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico affitto", owner="home",
                    status="approved", embedding=[0.5, 0.5])
    fact_id = store.add_item(kind="fact", content="Il gatto si chiama Fufi", owner="home",
                              status="approved", embedding=[0.5, 0.5])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.5, 0.5])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "gatto"}, owner="home", kinds=["fact"],
    )
    kinds_seen = {r["kind"] for r in res["results"]}
    assert "expense" not in kinds_seen
    assert any(r["id"] == fact_id for r in res["results"])
    store.close()


@pytest.mark.asyncio
async def test_recall_knowledge_kinds_plain_string_behaves_like_list(tmp_path):
    """Task 1 review Low: kinds="fact" (plain string, not "all") must be
    normalized to ["fact"], not iterated per-character into ('f','a','c','t')."""
    store = KnowledgeStore(str(tmp_path / "b2.db"))
    store.add_item(kind="expense", content="Bonifico affitto", owner="home",
                    status="approved", embedding=[0.5, 0.5])
    fact_id = store.add_item(kind="fact", content="Il gatto si chiama Fufi", owner="home",
                              status="approved", embedding=[0.5, 0.5])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.5, 0.5])

    res = await handle_recall_knowledge(
        store, embedder, {"query": "gatto"}, owner="home", kinds="fact",
    )
    kinds_seen = {r["kind"] for r in res["results"]}
    assert "expense" not in kinds_seen
    assert any(r["id"] == fact_id for r in res["results"])
    store.close()
