"""Write-back of brain actions (autonomous decisions taken by the cognitive
cycle, e.g. auto-tuned detector thresholds) into the unified KnowledgeStore.

Every action the brain takes on its own must leave a trace that is (a)
recallable via `KnowledgeStore.search` -- which requires `status='approved'`
AND `embedding IS NOT NULL` -- and (b) undoable (Slice 6 Task 5 wires
`remove_brain_action` to an undo command). If no embedder is available we
refuse to write a NULL-embedding row: such a row would never surface via
search, making the "trace" irrecoverable in practice, which defeats the
whole point of recording it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Upper bound for the supersede scan, mirroring history_digest's
# _MAX_INSIGHT_SCAN: one row per source_ref, superseded on every write, so
# this only needs to exceed the number of distinct brain-action refs.
_MAX_ACTION_SCAN = 100000


async def record_brain_action(
    knowledge_store, embedder, *, text: str, source_ref: str, owner: str = "home",
) -> str | None:
    """Persist a brain-action trace, embedded and approved so it is
    recallable via KnowledgeStore.search. Supersedes (delete-then-add) any
    prior trace with the same source_ref, exactly like history_digest does
    for insights. Returns the new item's id (as str), or None if no embedder
    is available -- in that case NOTHING is written."""
    if embedder is None:
        logger.warning(
            "record_brain_action: no embedder available, refusing to write "
            "an unrecallable (NULL-embedding) trace for source_ref=%s",
            source_ref,
        )
        return None

    emb = await embedder.embed(text)

    existing = knowledge_store.list_items(kind="brain-action", limit=_MAX_ACTION_SCAN)
    for old in existing:
        if old.get("source_ref") == source_ref:
            try:
                knowledge_store.delete_item(old["id"])
            except Exception:
                pass

    item_id = knowledge_store.add_item(
        kind="brain-action",
        content=text,
        owner=owner,
        source="brain",
        source_ref=source_ref,
        status="approved",
        embedding=emb,
        sensitivity="normal",
    )
    return str(item_id)


async def remove_brain_action(knowledge_store, source_ref: str) -> int:
    """Delete the brain-action trace(s) for this source_ref (used by undo,
    Task 5). Returns the number of rows removed."""
    removed = 0
    existing = knowledge_store.list_items(kind="brain-action", limit=_MAX_ACTION_SCAN)
    for old in existing:
        if old.get("source_ref") == source_ref:
            try:
                knowledge_store.delete_item(old["id"])
                removed += 1
            except Exception:
                pass
    return removed
