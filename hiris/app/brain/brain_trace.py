"""Write-back of brain actions (autonomous decisions taken by the cognitive
cycle, e.g. auto-tuned detector thresholds) into the unified KnowledgeStore.

Every action the brain takes on its own must leave a trace that is (a)
recallable when possible via `KnowledgeStore.search` -- which prefers
`status='approved'` AND `embedding IS NOT NULL` but degrades to `recent()`
when there is no query vector -- and (b) undoable (Slice 6 Task 5 wires
`remove_brain_action` to an undo command). The undo-ability is what actually
matters: the trace is what lets the "Annulla" button exist for a change the
Brain made to itself, so it is always written, even with no embedder, an
embedder that returns a falsy vector, or one whose `embed()` call raises --
a NULL-embedding row still shows up via `recent()`/`list_items` and is
still findable and removable by `remove_brain_action`.
"""
from __future__ import annotations

# Upper bound for the supersede scan, mirroring history_digest's
# _MAX_INSIGHT_SCAN: one row per source_ref, superseded on every write, so
# this only needs to exceed the number of distinct brain-action refs.
_MAX_ACTION_SCAN = 100000


async def record_brain_action(
    knowledge_store, embedder, *, text: str, source_ref: str, owner: str = "home",
) -> str:
    """Persist a brain-action trace, approved and embedded when a vector is
    available, so it is recallable via KnowledgeStore.search. Supersedes
    (delete-then-add) any prior trace with the same source_ref, exactly like
    history_digest does for insights. Returns the new item's id (as str).

    Always writes, even with no embedder (embedder=None), one that returns
    a falsy vector, or one that raises: the trace is what makes a brain
    action undoable, and losing that safety net because no embedder happens
    to be configured -- or a configured one is briefly unreachable -- would
    be worse than a trace that only degrades to recent() instead of vector
    search. `embedder.embed()` raising IS caught here: doing so does not
    swallow anything, because it still results in the trace being written
    (the whole point of this function), and the caller's own try/except
    (e.g. cognitive_loop.auto_tune_detectors) still guards the rest of its
    own work regardless of whether this function raises or not. All four
    sibling write paths (save_memory, recall_memory's degrade, save_knowledge,
    recall_knowledge) already treat a raising embedder as "write without a
    vector"; this is the same rule."""
    try:
        emb: list[float] = await embedder.embed(text) if embedder is not None else []
    except Exception:
        emb = []

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
        embedding=emb or None,
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
