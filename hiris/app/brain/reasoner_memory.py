"""Bounded, home-scoped, failure-safe memory retrieval for the proactive
reasoner's context (Slice 6b Task 2).

This is a pure read helper: it embeds a query, searches the unified
KnowledgeStore (Task 1's `LLMRouter.automatic_allows_sensitive()` gate is
expected to be threaded in by the caller as `allow_sensitive`), and renders
a handful of short snippets for the reasoner's prompt. It never mutates the
store or the embedder, never weakens `KnowledgeStore.search`'s scoping, and
never raises -- any failure (bad embedder, search error) degrades to an
empty list so a flaky/absent memory subsystem can never break the reasoner's
cognitive cycle.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 140


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
) -> list[str]:
    """Return up to `limit` short snippets of memory relevant to
    `query_text`, scoped to `owner` and `kinds`, honoring `allow_sensitive`
    as decided by the caller's egress gate. Total rendered length is capped
    at `char_cap`. Returns `[]` on any missing input or failure -- never
    raises."""
    if knowledge_store is None or embedder is None:
        return []
    if not query_text or not query_text.strip():
        return []

    try:
        emb = await embedder.embed(query_text)
    except Exception:
        logger.warning("relevant_memory: embed() failed", exc_info=True)
        return []

    if not emb:
        return []

    try:
        hits = knowledge_store.search(
            query_vec=emb,
            k=limit,
            owner=owner,
            lens=None,
            allow_sensitive=allow_sensitive,
            kinds=list(kinds),
        )
    except Exception:
        logger.warning("relevant_memory: search() failed", exc_info=True)
        return []

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

    return snippets
