import pytest

from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reasoner_memory import relevant_memory


class _FakeEmbedder:
    async def embed(self, text):
        return [1.0, 0.0, 0.0]


class _FalsyEmbedder:
    def __init__(self, value):
        self._value = value

    async def embed(self, text):
        return self._value


class _RaisingEmbedder:
    async def embed(self, text):
        raise RuntimeError("embed boom")


class _RaisingSearchStore(KnowledgeStore):
    def search(self, **kwargs):
        raise RuntimeError("search boom")


@pytest.mark.asyncio
async def test_relevant_memory_returns_snippet_for_relevant_insight(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    emb = _FakeEmbedder()

    store.add_item(
        kind="insight",
        content="La caldaia va revisionata ogni anno a ottobre",
        owner="home",
        status="approved",
        embedding=[1.0, 0.0, 0.0],
        sensitivity="normal",
    )

    out = await relevant_memory(
        store, emb, query_text="manutenzione caldaia", allow_sensitive=False,
    )

    assert len(out.snippets) >= 1
    assert any("caldaia" in s for s in out.snippets)
    assert out.by_meaning is True
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_excludes_sensitive_unless_allowed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    emb = _FakeEmbedder()

    store.add_item(
        kind="insight",
        content="Il codice del cancello segreto è 1234",
        owner="home",
        status="approved",
        embedding=[1.0, 0.0, 0.0],
        sensitivity="sensitive",
    )

    out_blocked = await relevant_memory(
        store, emb, query_text="codice cancello", allow_sensitive=False,
    )
    assert not any("cancello" in s for s in out_blocked.snippets)

    out_allowed = await relevant_memory(
        store, emb, query_text="codice cancello", allow_sensitive=True,
    )
    assert any("cancello" in s for s in out_allowed.snippets)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_no_knowledge_store_returns_empty():
    out = await relevant_memory(
        None, _FakeEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )
    assert out.snippets == []
    assert out.by_meaning is False


@pytest.mark.asyncio
async def test_relevant_memory_blank_query_returns_empty(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _FakeEmbedder(), query_text="   ", allow_sensitive=False,
    )
    assert out.snippets == []
    assert out.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_search_raises_returns_empty_no_crash(tmp_path):
    store = _RaisingSearchStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _FakeEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )
    assert out.snippets == []
    assert out.by_meaning is False
    store.close()


# --- Degradation: no embedder / falsy embedding / raising embedder all fall
# through to KnowledgeStore.search's own degrade-to-recent path (same
# confidentiality filters), instead of relevant_memory giving up early. ---


@pytest.mark.asyncio
async def test_relevant_memory_no_embedder_returns_most_recent(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="Nota piu' vecchia", owner="home",
        status="approved", sensitivity="normal",
    )
    store.add_item(
        kind="insight", content="Nota piu' recente", owner="home",
        status="approved", sensitivity="normal",
    )

    out = await relevant_memory(
        store, None, query_text="qualcosa", allow_sensitive=False,
    )

    assert len(out.snippets) >= 1
    assert any("recente" in s for s in out.snippets)
    assert out.by_meaning is False
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("falsy_value", [None, []])
async def test_relevant_memory_falsy_embedding_returns_most_recent(tmp_path, falsy_value):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="Promemoria caldaia annuale", owner="home",
        status="approved", sensitivity="normal",
    )

    out = await relevant_memory(
        store, _FalsyEmbedder(falsy_value), query_text="qualcosa", allow_sensitive=False,
    )

    assert len(out.snippets) >= 1
    assert any("caldaia" in s for s in out.snippets)
    assert out.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_embed_raises_returns_most_recent_no_crash(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="Promemoria caldaia annuale", owner="home",
        status="approved", sensitivity="normal",
    )

    out = await relevant_memory(
        store, _RaisingEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )

    assert len(out.snippets) >= 1
    assert any("caldaia" in s for s in out.snippets)
    assert out.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_respects_char_cap(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    emb = _FakeEmbedder()

    long_text = "Parola " * 40  # ~280 chars, well over the 140-char snippet cap
    for i in range(10):
        store.add_item(
            kind="insight",
            content=f"{long_text} numero {i}",
            owner="home",
            status="approved",
            embedding=[1.0, 0.0, 0.0],
            sensitivity="normal",
        )

    out = await relevant_memory(
        store, emb, query_text="parola", allow_sensitive=False,
        limit=10, char_cap=300,
    )

    assert len(out.snippets) < 10
    assert sum(len(s) for s in out.snippets) <= 300
    assert out.by_meaning is True
    store.close()


# --- Pinning: the char cap, the snippet limit, and the confidentiality
# filter all keep applying on the degraded (no-embedder) path too. ---


@pytest.mark.asyncio
async def test_relevant_memory_degraded_path_respects_char_cap_and_limit(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))

    long_text = "Parola " * 40  # ~280 chars, well over the 140-char snippet cap
    for i in range(10):
        store.add_item(
            kind="insight",
            content=f"{long_text} numero {i}",
            owner="home",
            status="approved",
            sensitivity="normal",
        )

    out = await relevant_memory(
        store, None, query_text="qualsiasi", allow_sensitive=False,
        limit=10, char_cap=300,
    )

    assert len(out.snippets) < 10
    assert sum(len(s) for s in out.snippets) <= 300
    assert out.by_meaning is False
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_degraded_path_hides_sensitive_unless_allowed(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))

    store.add_item(
        kind="insight",
        content="Il codice del cancello segreto è 1234",
        owner="home",
        status="approved",
        sensitivity="sensitive",
    )

    out_blocked = await relevant_memory(
        store, None, query_text="qualsiasi", allow_sensitive=False,
    )
    assert not any("cancello" in s for s in out_blocked.snippets)
    assert out_blocked.by_meaning is False

    out_allowed = await relevant_memory(
        store, None, query_text="qualsiasi", allow_sensitive=True,
    )
    assert any("cancello" in s for s in out_allowed.snippets)
    assert out_allowed.by_meaning is False
    store.close()


# ---------------------------------------------------------------------------
# Fix 1 (CRITICAL, whole-branch review, final fix wave): the proactive
# reasoner's `.declared` field (rendered into the proactive prompt by
# watcher/reasoner.py -- brain/coverage_review.py used to read from the same
# place too, before it exited whole in fetta E3 Task 5) must never surface
# a source='gateway' row,
# mirroring the exclusion already pinned at the store level
# (test_knowledge_store_declared.py) and on the chat surface
# (test_declared_block_chat.py). `.declared` is independent of the embedder
# by design, so query_text/embedder are irrelevant here -- exercised with
# both to show it holds either way.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_relevant_memory_declared_excludes_gateway_source(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="iniettato via gateway MCP remoto", owner="home",
        status="approved", source="gateway",
    )
    store.add_item(
        kind="memory", content="il modulo meteo esterno e' guasto", owner="home",
        status="approved", source="chat",
    )

    out = await relevant_memory(
        store, None, query_text="qualsiasi cosa non correlata", allow_sensitive=False,
    )
    assert not any("gateway" in d for d in out.declared), (
        "una riga source='gateway' non deve mai comparire nel blocco "
        "'dichiarato' del ragionatore proattivo -- e' recuperabile via "
        "recall_memory ma non e' una dichiarazione di una persona"
    )
    assert any("modulo meteo esterno" in d for d in out.declared)
    store.close()
