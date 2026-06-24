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
