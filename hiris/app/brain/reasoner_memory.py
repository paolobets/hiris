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

from ..proxy._sanitize import sanitize_text
from .knowledge_store import DECLARED_MAX, confronta_significati, render_declared_overflow_note

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 140

# Fix 1 (review wave, task-4-fixes): the cap applied to a single DECLARED
# item, chosen deliberately instead of inheriting sanitize_ha_value's
# 120-char clamp meant for terse HA attribute values. A declared fact is a
# full sentence or two a person typed to be remembered forever -- not a
# preview like a recalled snippet (capped separately at _SNIPPET_MAX=140,
# always truncated by design). 500 comfortably fits two or three sentences
# of Italian prose (the production examples in DECLARED_MAX's comment above
# -- "chi amministra la casa", "il modulo meteo esterno e' guasto" -- are
# all under 60) while still bounding one row's worst-case contribution to
# the prompt. If a single item is still longer than that (pasted text, not
# a "fact"), `sanitize_declared_item` below cuts it VISIBLY -- never
# silently: this is exactly the trap this module's Task 4 docstring already
# documents for the portrait (see watcher/reasoner.py's comment at the top
# of build_user_message), applied to declared facts instead of clamping
# them through the generic 120-char HA-value sanitizer by accident.
DECLARED_ITEM_MAX = 500


def sanitize_declared_item(content) -> str:
    """Sanitize+flatten a single declared fact for a prompt, at the source
    (or, defensively, wherever it is rendered -- watcher/reasoner.py's
    build_user_message calls this on the way out too, so a caller that hands
    it a raw, unsanitized `declared` list directly -- bypassing
    `_declared_snippets` entirely -- still gets the same treatment. brain/
    coverage_review.py's build_review_message used to call this too, on the
    now-exited holistic path -- fetta E3 Task 5).

    Runs the shared injection filter (`sanitize_text`) so a poisoned
    declared row can't smuggle an instruction-override phrase, then
    flattens whitespace/newlines (same reason as the memory-snippet
    flattening alongside this function's callers: a raw multi-line row
    could otherwise break the prompt's line structure or open a fake ```
    fence). Length is capped at `DECLARED_ITEM_MAX`, chosen above -- NOT
    the 120-char clamp sanitize_ha_value would apply, and never silent: an
    item cut for length gets an explicit "… (troncato)" marker, the same
    discipline `_SNIPPET_MAX` uses above (via its own explicit "…") and the
    overflow note uses for whole items dropped past DECLARED_MAX.

    Idempotent by construction -- callers apply this both at the source
    (`_declared_snippets` below) and defensively downstream (watcher/
    reasoner.py), so re-running it on its own output must reproduce that
    output exactly. The slice point is always
    the fixed `DECLARED_ITEM_MAX` offset with NO `.rstrip()` beforehand:
    stripping trailing whitespace before appending the marker would make
    the cut position content-dependent, so a second pass over an
    already-marked string (marker included) could land the same
    `[:DECLARED_ITEM_MAX]` slice a few characters short of where the first
    pass did, splicing a fresh marker onto a fragment of the previous one."""
    flat = " ".join(str(content).split())
    # sanitize_text's own default clamp (2000) sits well above
    # DECLARED_ITEM_MAX (500): whether or not it silently bites first makes
    # no difference to the outcome below, since only the first 500 chars of
    # its result are ever kept either way -- but the injection filter runs
    # over up to 2000 chars first, not 120.
    cleaned = sanitize_text(flat)
    if len(cleaned) > DECLARED_ITEM_MAX:
        return cleaned[:DECLARED_ITEM_MAX] + "… (troncato)"
    return cleaned


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
    stessa disciplina di handlers_chat._render_declared_block. Il testo
    della nota vive in un solo posto (`knowledge_store.
    render_declared_overflow_note`), non duplicato qui -- Fix 2 della
    review wave task-4-fixes.

    Ogni elemento passa da `sanitize_declared_item` (Fix 1, stessa review
    wave): il contenuto e' sanificato/appiattito/capped QUI, alla fonte --
    non lasciato grezzo per essere poi tronco a 120 caratteri in silenzio
    dal sanitize_ha_value generico che watcher/reasoner.py applicava a
    tutto il contesto (`_san(_raw_ctx)`)."""
    limit = DECLARED_MAX
    try:
        items, total = knowledge_store.declared(
            owner=owner, allow_sensitive=allow_sensitive, limit=limit,
        )
    except Exception:
        logger.warning("relevant_memory: declared() failed", exc_info=True)
        return []
    out: list[str] = []
    for item in items:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        out.append(sanitize_declared_item(content))
    note = render_declared_overflow_note(total, len(items), limit)
    if note:
        out.append(note)
    return out
