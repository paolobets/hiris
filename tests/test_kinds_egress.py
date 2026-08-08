"""Slice 3 Task 6 — kinds egress: `kinds` filtra `KnowledgeStore.search`,
chiudendo la config morta su Agent.knowledge_access.kinds.

fetta E2 Task 8 ("escono i trentaquattro"): questi test chiamavano
`handle_recall_memory` (tools/memory_tools.py), ma quel wrapper si limitava a
inoltrare `kinds` invariato a `KnowledgeStore.search` -- la normalizzazione
verificata qui (lista, o stringa singola trattata come lista) vive TUTTA in
`_clausole_di_scope` (knowledge_store.py), non nel wrapper. Il wrapper e'
uscito -- orfano dal Task 7 (`ToolDispatcher`, l'unico chiamante, e' uscito
lui per primo) -- ma il soggetto vero di questi test (la normalizzazione)
sopravvive intatto: chiamano `store.search` direttamente.

Also covers the Task 1 review Low: a plain string kinds="fact" (not "all")
must behave like ["fact"], not be iterated character-by-character.
"""
import pytest
from unittest.mock import AsyncMock

from hiris.app.brain.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_recall_memory_kinds_list_filters_out_other_kinds(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    store.add_item(kind="expense", content="Bonifico affitto", owner="home",
                    status="approved", embedding=[0.5, 0.5])
    fact_id = store.add_item(kind="fact", content="Il gatto si chiama Fufi", owner="home",
                              status="approved", embedding=[0.5, 0.5])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.5, 0.5])

    qv = await embedder.embed("gatto")
    results = store.search(query_vec=qv, k=5, owner="home", kinds=["fact"])
    kinds_seen = {r["kind"] for r in results}
    assert "expense" not in kinds_seen
    assert any(r["id"] == fact_id for r in results)
    store.close()


@pytest.mark.asyncio
async def test_recall_memory_kinds_plain_string_behaves_like_list(tmp_path):
    """Task 1 review Low: kinds="fact" (plain string, not "all") must be
    normalized to ["fact"], not iterated per-character into ('f','a','c','t')."""
    store = KnowledgeStore(str(tmp_path / "b2.db"))
    store.add_item(kind="expense", content="Bonifico affitto", owner="home",
                    status="approved", embedding=[0.5, 0.5])
    fact_id = store.add_item(kind="fact", content="Il gatto si chiama Fufi", owner="home",
                              status="approved", embedding=[0.5, 0.5])
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.5, 0.5])

    qv = await embedder.embed("gatto")
    results = store.search(query_vec=qv, k=5, owner="home", kinds="fact")
    kinds_seen = {r["kind"] for r in results}
    assert "expense" not in kinds_seen
    assert any(r["id"] == fact_id for r in results)
    store.close()
