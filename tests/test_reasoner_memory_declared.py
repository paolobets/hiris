"""Task 4 of "memoria unica 3a", proactive-reasoner side: `relevant_memory()`
gains a `.declared` field carrying the DICHIARATI (KnowledgeStore.declared())
-- rendered unconditionally, never gated on an embedder or on the current
wake/holistic query resembling their content, unlike `.snippets`.

Mirrors tests/test_reasoner_memory.py's structure and
tests/test_knowledge_store_declared.py's classification -- see those files
for the source-value / confidentiality-filter groundwork this builds on.
"""
import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reasoner_memory import MemoryRecall, relevant_memory


class _RaisingDeclaredStore(KnowledgeStore):
    def declared(self, **kwargs):
        raise RuntimeError("declared boom")


@pytest.mark.asyncio
async def test_relevant_memory_declared_present_without_embedder_and_unrelated_query(tmp_path):
    """Requirement 1, reasoner side: a declared item appears WITHOUT an
    embedder and without the query resembling it at all."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="il modulo meteo esterno e' guasto",
        owner="home", status="approved", source="chat",
    )

    out = await relevant_memory(
        store, None, query_text="batteria del sensore ingresso", allow_sensitive=False,
    )

    assert any("modulo meteo esterno" in d for d in out.declared)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_excludes_insight(tmp_path):
    """Requirement 2, reasoner side: an insight (source='history-digest')
    must never appear in .declared, even though it DOES appear in
    .snippets via the normal recall path."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="la caldaia consuma di piu' il lunedi'",
        owner="home", status="approved", source="history-digest",
        embedding=[1.0, 0.0, 0.0],
    )

    out = await relevant_memory(
        store, None, query_text="caldaia", allow_sensitive=False, kinds=("insight", "memory"),
    )

    assert not any("caldaia" in d for d in out.declared)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_present_even_on_blank_query(tmp_path):
    """The blank-query early return only ever concerned recall (.snippets,
    which needs something to compare against) -- .declared has no such
    dependency and must survive it."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="chi amministra la casa e' Paolo",
        owner="home", status="approved", source="manual",
    )

    out = await relevant_memory(
        store, None, query_text="   ", allow_sensitive=False,
    )

    assert out.snippets == []
    assert any("amministra la casa" in d for d in out.declared)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_no_knowledge_store_returns_empty():
    out = await relevant_memory(None, None, query_text="qualcosa", allow_sensitive=False)
    assert out.declared == []


@pytest.mark.asyncio
async def test_relevant_memory_declared_failure_degrades_to_empty_no_crash(tmp_path):
    store = _RaisingDeclaredStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(store, None, query_text="qualcosa", allow_sensitive=False)
    assert out.declared == []
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_respects_egress_gate(tmp_path):
    """Constraint: the egress gate does not move -- allow_sensitive governs
    .declared exactly as it governs .snippets."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="codice del cancello 1234", owner="home",
        status="approved", source="chat", sensitivity="sensitive",
    )

    blocked = await relevant_memory(store, None, query_text="x", allow_sensitive=False)
    assert not any("cancello" in d for d in blocked.declared)

    allowed = await relevant_memory(store, None, query_text="x", allow_sensitive=True)
    assert any("cancello" in d for d in allowed.declared)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_cross_owner_sensitive_hidden(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="segreto di paolo", owner="paolo",
        status="approved", source="chat", sensitivity="sensitive",
    )
    out = await relevant_memory(
        store, None, query_text="x", allow_sensitive=True, owner="giulia",
    )
    assert not any("segreto di paolo" in d for d in out.declared)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_limit_overflow_is_declared_not_silent(tmp_path):
    """Requirement 3, reasoner side: pin the overflow behaviour -- when there
    are more declared items than the limit, the extra count is stated in the
    rendered list, never silently dropped."""
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    for i in range(5):
        store.add_item(
            kind="memory", content=f"fatto numero {i}", owner="home",
            status="approved", source="chat",
        )

    out = await relevant_memory(store, None, query_text="qualcosa", allow_sensitive=False)

    # All 5 fit comfortably under DECLARED_MAX (30) in this test -- assert
    # the no-overflow case is clean (no stray note) here, and the overflow
    # note itself directly against KnowledgeStore.declared()'s contract in
    # test_knowledge_store_declared.py (limit=3 case). This test instead
    # pins that relevant_memory NEVER truncates .declared itself beyond
    # what KnowledgeStore.declared() already decided.
    assert len([d for d in out.declared if d.startswith("fatto numero")]) == 5
    assert not any("non mostrat" in d for d in out.declared)
    store.close()


def test_memory_recall_declared_field_defaults_to_empty_list():
    """Existing call sites that construct MemoryRecall without `declared=`
    (server.py's failure-fallbacks, other tests) must keep working."""
    mem = MemoryRecall(snippets=[], by_meaning=False)
    assert mem.declared == []


# ---------------------------------------------------------------------------
# Fix 1 (review wave, task-4-fixes): declared facts over 120 chars must not
# be silently truncated by the 120-char sanitize_ha_value clamp that used to
# reach them via watcher/reasoner.py's `_san(_raw_ctx)`. Pinned here at the
# source (`_declared_snippets`, exercised through `relevant_memory`), and
# again at both proactive render surfaces in
# tests/test_declared_block_reasoner.py.
# ---------------------------------------------------------------------------

LONG_DECLARED_TEXT = (
    "Il termostato del salotto e' stato sostituito con un nuovo modello "
    "smart che supporta la programmazione settimanale e l'integrazione "
    "diretta con Home Assistant tramite MQTT."
)


@pytest.mark.asyncio
async def test_relevant_memory_declared_item_over_120_chars_survives_intact(tmp_path):
    assert len(LONG_DECLARED_TEXT) > 120  # the old, wrong clamp
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content=LONG_DECLARED_TEXT, owner="home",
        status="approved", source="chat",
    )
    out = await relevant_memory(store, None, query_text="x", allow_sensitive=False)
    assert LONG_DECLARED_TEXT in out.declared
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_declared_item_over_cap_is_marked_not_silently_cut(tmp_path):
    """Beyond DECLARED_ITEM_MAX (500) the item IS cut -- but visibly, never
    silently: the raw over-cap text must not appear whole, and a marker
    must say so."""
    huge_text = "y" * 700
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content=huge_text, owner="home",
        status="approved", source="chat",
    )
    out = await relevant_memory(store, None, query_text="x", allow_sensitive=False)
    assert not any(huge_text in d for d in out.declared)
    assert any("troncato" in d for d in out.declared)
    store.close()
