# hiris/app/brain/mayan_ingest.py
from __future__ import annotations
import asyncio
import logging
from .chunking import chunk_text

logger = logging.getLogger(__name__)


async def ingest_tag(client, store, embedder, *, tag_id: int,
                     sensitivity: str = "sensitive", owner: str = "home") -> int:
    docs = await client.list_tag_documents(tag_id)
    loop = asyncio.get_running_loop()
    ingested = 0
    for d in docs:
        doc_id = str(d["id"])
        if await loop.run_in_executor(None, lambda: store.document_exists(doc_id)):
            continue
        text = await client.get_ocr_text(d["id"])
        if not text or not text.strip():
            continue
        item_id = await loop.run_in_executor(None, lambda: store.add_item(
            kind="document", content=d.get("label", "") or f"doc {doc_id}",
            owner=owner, source="mayan", source_ref=doc_id,
            sensitivity=sensitivity, status="approved"))
        for idx, ch in enumerate(chunk_text(text)):
            try:
                emb = await embedder.embed(ch)
            except Exception:
                emb = []
            await loop.run_in_executor(None, lambda i=item_id, idx=idx, ch=ch, emb=emb:
                store.add_document_chunk(item_id=i, mayan_doc_id=doc_id,
                                         chunk_index=idx, content=ch,
                                         embedding=emb or None))
        ingested += 1
        logger.info("Mayan: ingerito documento %s (%s)", doc_id, d.get("label", ""))
    return ingested
