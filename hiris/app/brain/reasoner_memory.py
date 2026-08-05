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

Task 4 ("memoria unica 3a") adds a second, independent piece to the result:
`MemoryRecall.declared`. `.snippets` above is RECALLED -- it only shows up
when the current wake/holistic query happens to resemble it (or, degraded,
just the most recent rows). `.declared` is the opposite: everything a
PERSON declared (`KnowledgeStore.declared()`, `source` in DECLARED_SOURCES)
rendered unconditionally, regardless of the query, the embedder, or whether
`query_text` is even usable -- because *"the external weather module is
broken"* must not depend on a wake event resembling weather to be known.
Same egress gate (`allow_sensitive`) as `.snippets`, same
confidentiality filters (via `KnowledgeStore.declared()` ->
`_clausole_di_scope`), never raises.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .knowledge_store import DECLARED_MAX, confronta_significati

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
    result).

    `declared` (Task 4): what a person declared (see module docstring) --
    always populated when there is anything to show, independent of
    `by_meaning`/query resemblance. Defaults to `[]` so existing call sites
    that construct `MemoryRecall(snippets=..., by_meaning=...)` without it
    (server.py's failure-fallbacks, older tests) keep working unchanged."""
    snippets: list[str]
    by_meaning: bool
    declared: list[str] = field(default_factory=list)


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
    how `by_meaning` reports which path was taken.

    `declared` (Task 4) is fetched independently of everything above --
    NOT gated on `knowledge_store is None` being false only, but computed
    before the blank-`query_text` early return too, since a person's
    declared facts have nothing to do with there being a usable query."""
    if knowledge_store is None:
        return MemoryRecall(snippets=[], by_meaning=False, declared=[])

    declared = _declared_snippets(knowledge_store, owner=owner, allow_sensitive=allow_sensitive)

    if not query_text or not query_text.strip():
        return MemoryRecall(snippets=[], by_meaning=False, declared=declared)

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
            allow_sensitive=allow_sensitive,
            kinds=list(kinds),
        )
    except Exception:
        logger.warning("relevant_memory: search() failed", exc_info=True)
        return MemoryRecall(snippets=[], by_meaning=False, declared=declared)

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

    return MemoryRecall(
        snippets=snippets, by_meaning=confronta_significati(emb), declared=declared,
    )


def _declared_snippets(
    knowledge_store, *, owner: str, allow_sensitive: bool,
) -> list[str]:
    """Task 4: le righe DICHIARATE (`KnowledgeStore.declared()`, stessi
    filtri di riservatezza di search()/recent() via `_clausole_di_scope`)
    rese come brevi frasi per il prompt del ragionatore -- SEMPRE incluse,
    mai dipendenti da un embedder o da quanto il segnale/la revisione
    corrente somigli al loro contenuto (a differenza di `snippets` sopra).

    Nessun filtro `kinds` qui: cio' che una persona ha dichiarato puo'
    essere di qualsiasi kind (memory, fact, preference, obligation, ...) --
    Task 4 riguarda `source`, non `kind`.

    Non solleva mai: un fallimento qui degrada a lista vuota, come il resto
    di questo modulo (e coerentemente con `declared` default a `[]` su
    `MemoryRecall`).

    Quando KnowledgeStore.declared() riporta piu' righe di quante ne
    restituisce (il limite DECLARED_MAX e' stato raggiunto), l'ultima riga
    della lista lo dice esplicitamente -- mai un troncamento silenzioso,
    stessa disciplina di handlers_chat._render_declared_block."""
    try:
        items, total = knowledge_store.declared(owner=owner, allow_sensitive=allow_sensitive)
    except Exception:
        logger.warning("relevant_memory: declared() failed", exc_info=True)
        return []
    out: list[str] = []
    for item in items:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        out.append(" ".join(content.split()))
    overflow = total - len(items)
    if overflow > 0:
        out.append(
            f"(+ altri {overflow} elementi dichiarati più vecchi, non "
            f"mostrati — limite {DECLARED_MAX})"
        )
    return out
