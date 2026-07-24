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

    assert len(out) >= 1
    assert any("caldaia" in s for s in out)
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
    assert not any("cancello" in s for s in out_blocked)

    out_allowed = await relevant_memory(
        store, emb, query_text="codice cancello", allow_sensitive=True,
    )
    assert any("cancello" in s for s in out_allowed)
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_no_knowledge_store_returns_empty():
    out = await relevant_memory(
        None, _FakeEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )
    assert out == []


@pytest.mark.asyncio
async def test_relevant_memory_no_embedder_returns_empty(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, None, query_text="qualcosa", allow_sensitive=False,
    )
    assert out == []
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_blank_query_returns_empty(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _FakeEmbedder(), query_text="   ", allow_sensitive=False,
    )
    assert out == []
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("falsy_value", [None, []])
async def test_relevant_memory_falsy_embedding_returns_empty(tmp_path, falsy_value):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _FalsyEmbedder(falsy_value), query_text="qualcosa", allow_sensitive=False,
    )
    assert out == []
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_embed_raises_returns_empty_no_crash(tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _RaisingEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )
    assert out == []
    store.close()


@pytest.mark.asyncio
async def test_relevant_memory_search_raises_returns_empty_no_crash(tmp_path):
    store = _RaisingSearchStore(str(tmp_path / "mem.db"))
    out = await relevant_memory(
        store, _FakeEmbedder(), query_text="qualcosa", allow_sensitive=False,
    )
    assert out == []
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

    assert len(out) < 10
    assert sum(len(s) for s in out) <= 300
    store.close()
