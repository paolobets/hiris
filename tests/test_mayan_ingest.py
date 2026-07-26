# tests/test_mayan_ingest.py
import pytest
from unittest.mock import AsyncMock, patch
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.mayan_ingest import ingest_tag


@pytest.mark.asyncio
async def test_ingest_tag_creates_document_and_chunks(tmp_path):
    store = KnowledgeStore(str(tmp_path / "b.db"))
    client = AsyncMock()
    client.list_tag_documents = AsyncMock(return_value=[{"id": 42, "label": "Estratto"}])
    client.get_ocr_text = AsyncMock(return_value="riga uno " * 200)  # testo lungo
    embedder = AsyncMock(); embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    n = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n == 1
    assert store.document_exists("42") is True
    # idempotente: una seconda passata non re-ingerisce
    n2 = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n2 == 0
    store.close()


@pytest.mark.asyncio
async def test_ingest_tag_retries_after_transient_embedder_failure(tmp_path):
    """Task L/5: a transient embedder failure must NOT mark the document
    ingested -- `document_exists` must stay False so the NEXT poll retries
    it, instead of creating a permanent, un-repairable gap."""
    store = KnowledgeStore(str(tmp_path / "b.db"))
    client = AsyncMock()
    client.list_tag_documents = AsyncMock(return_value=[{"id": 99, "label": "Fattura"}])
    client.get_ocr_text = AsyncMock(return_value="riga uno " * 200)
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=RuntimeError("embedder temporarily unavailable"))

    n = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")

    assert n == 0
    # the whole point of the fix: NOT marked ingested -> retried next poll
    assert store.document_exists("99") is False
    # no orphaned chunks left behind for a document that was never committed
    row = store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE mayan_doc_id=?", ("99",)
    ).fetchone()
    assert row[0] == 0

    # next poll: embedder recovers -> document is now actually ingested
    embedder.embed = AsyncMock(return_value=[0.1, 0.2])
    n2 = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n2 == 1
    assert store.document_exists("99") is True
    store.close()


@pytest.mark.asyncio
async def test_ingest_tag_rolls_back_item_when_chunk_write_fails(tmp_path):
    """Backlog #5: add_item already makes document_exists() True, so a chunk
    write that raises AFTER it must roll the item back -- otherwise the doc is
    marked ingested forever with partial/no chunks and never retried."""
    store = KnowledgeStore(str(tmp_path / "b.db"))
    client = AsyncMock()
    client.list_tag_documents = AsyncMock(return_value=[{"id": 77, "label": "Contratto"}])
    client.get_ocr_text = AsyncMock(return_value="riga uno " * 200)
    embedder = AsyncMock(); embedder.embed = AsyncMock(return_value=[0.1, 0.2])

    original = store.add_document_chunk
    calls = {"n": 0}

    def flaky_chunk(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk full mid-chunk")
        return original(*args, **kwargs)

    with patch.object(store, "add_document_chunk", side_effect=flaky_chunk):
        n = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")

    assert n == 0
    # item rolled back -> not "ingested", so it retries next poll
    assert store.document_exists("77") is False
    # and its chunks were purged by delete_item (no orphans)
    row = store._conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE mayan_doc_id=?", ("77",)
    ).fetchone()
    assert row[0] == 0

    # next poll with a healthy store -> ingested cleanly, whole
    n2 = await ingest_tag(client, store, embedder, tag_id=7, sensitivity="sensitive")
    assert n2 == 1
    assert store.document_exists("77") is True
    store.close()
