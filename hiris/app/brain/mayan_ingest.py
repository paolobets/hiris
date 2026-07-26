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
        chunks = chunk_text(text)
        # Embed ALL chunks BEFORE persisting anything (review L/5): if the
        # embedder fails transiently partway through, the document must NOT
        # be marked ingested (store.add_item, which document_exists() keys
        # off of), otherwise it would be skipped forever on every future
        # poll with no retry/repair path. Collecting embeddings first means
        # a failure here leaves no trace on disk -- the doc is retried
        # whole, from scratch, next time this tag is polled.
        try:
            embeddings = [await embedder.embed(ch) for ch in chunks]
        except Exception:
            logger.warning(
                "Mayan: embedding fallita per documento %s (%s) -- verrà "
                "ritentato al prossimo poll, nessuna scrittura effettuata",
                doc_id, d.get("label", ""), exc_info=True)
            continue
        item_id = await loop.run_in_executor(None, lambda: store.add_item(
            kind="document", content=d.get("label", "") or f"doc {doc_id}",
            owner=owner, source="mayan", source_ref=doc_id,
            sensitivity=sensitivity, status="approved"))
        # add_item already makes document_exists(doc_id) True. If a chunk write
        # now fails, the doc would be marked ingested forever but with partial
        # or no chunks and never retried. Roll the item back (delete_item also
        # purges its chunks) so the whole doc is retried cleanly next poll.
        try:
            for idx, (ch, emb) in enumerate(zip(chunks, embeddings)):
                await loop.run_in_executor(None, lambda i=item_id, idx=idx, ch=ch, emb=emb:
                    store.add_document_chunk(item_id=i, mayan_doc_id=doc_id,
                                             chunk_index=idx, content=ch,
                                             embedding=emb or None))
        except Exception:
            logger.warning(
                "Mayan: scrittura chunk fallita per documento %s (%s) -- "
                "rollback dell'item, verrà ritentato al prossimo poll",
                doc_id, d.get("label", ""), exc_info=True)
            await loop.run_in_executor(None, lambda i=item_id: store.delete_item(i))
            continue
        ingested += 1
        logger.info("Mayan: ingerito documento %s (%s)", doc_id, d.get("label", ""))
    return ingested
