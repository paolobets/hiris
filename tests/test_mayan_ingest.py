# tests/test_mayan_ingest.py
import pytest
from unittest.mock import AsyncMock
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
