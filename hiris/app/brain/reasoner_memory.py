"""Bounded, home-scoped, failure-safe memory retrieval for the proactive
reasoner's context (Slice 6b Task 2; degrade-and-declare added in fetta 2b
Task 1).

This is a pure read helper: it embeds a query, searches the unified
KnowledgeStore (Task 1's `LLMRouter.automatic_allows_sensitive()` gate is
expected to be threaded in by the caller as `allow_sensitive`), and renders
a handful of short snippets for the reasoner's prompt. It never mutates the
store or the embedder, never weakens `KnowledgeStore.search`'s scoping, and
never raises -- any failure (bad embedder, search error) degrades to an
empty result so a flaky/absent memory subsystem can never break the
reasoner's cognitive cycle.

Stock HIRIS ships with no embedding provider (`NullEmbedder.embed()` ->
`[]`), so an empty/missing query vector is the NORMAL case, not an edge
case. This function never gives up on that alone: it always calls
`knowledge_store.search(query_vec=emb or [], ...)` and lets the store
itself decide how to degrade -- `KnowledgeStore.search` compares meanings
when it has a vector to compare, and falls back to the most recent rows
(same confidentiality filters, via `recent()`) when it doesn't. That choice
lives in exactly one place (the store) so the two automatic callers of this
function can never diverge on it -- this function never calls `recent()`
directly.

Because the caller has to label its prompt block truthfully (a block of the
most recent rows must not be headed as if it were chosen by relevance), the
result also reports *how* the snippets were obtained via `MemoryRecall.
by_meaning`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .knowledge_store import confronta_significati

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 140


@dataclass
class MemoryRecall:
    """Result of `relevant_memory`: the snippets, and how they were chosen.

    `by_meaning=True` means the snippets were ranked by comparing meanings
    (a working embedder produced a usable query vector). `by_meaning=False`
    means `KnowledgeStore.search` degraded to the most recent rows instead
    -- no embedder configured, an empty/falsy embedding, or `embed()`
    raising all land here. Callers must use this to head their prompt block
    honestly (e.g. not "Cosa so di rilevante" for a degraded/recency-only
    result)."""
    snippets: list[str]
    by_meaning: bool


async def relevant_memory(
    knowledge_store,
    embedder,
    *,
    query_text: str,
    allow_sensitive: bool,
    owner: str = "home",
    kinds: tuple[str, ...] = ("insight", "memory"),
    limit: int = 5,
    char_cap: int = 600,
) -> MemoryRecall:
    """Return up to `limit` short snippets of memory relevant to
    `query_text`, scoped to `owner` and `kinds`, honoring `allow_sensitive`
    as decided by the caller's egress gate. Total rendered length is capped
    at `char_cap`. Degrades (never raises, never gives up early just
    because there's no embedder or it failed) -- see module docstring for
    how `by_meaning` reports which path was taken."""
    if knowledge_store is None:
        return MemoryRecall(snippets=[], by_meaning=False)
    if not query_text or not query_text.strip():
        return MemoryRecall(snippets=[], by_meaning=False)

    emb: list[float] = []
    if embedder is not None:
        try:
            emb = await embedder.embed(query_text) or []
        except Exception:
            logger.warning("relevant_memory: embed() failed", exc_info=True)
            emb = []

    try:
        hits = knowledge_store.search(
            query_vec=emb,
            k=limit,
            owner=owner,
            chatbot_id=None,
            allow_sensitive=allow_sensitive,
            kinds=list(kinds),
        )
    except Exception:
        logger.warning("relevant_memory: search() failed", exc_info=True)
        return MemoryRecall(snippets=[], by_meaning=False)

    snippets: list[str] = []
    total = 0
    for hit in hits or []:
        content = (hit.get("content") or "").strip()
        if not content:
            continue
        snippet = " ".join(content.split())
        if len(snippet) > _SNIPPET_MAX:
            snippet = snippet[: _SNIPPET_MAX].rstrip() + "…"
        if total + len(snippet) > char_cap:
            break
        snippets.append(snippet)
        total += len(snippet)

    return MemoryRecall(snippets=snippets, by_meaning=confronta_significati(emb))
