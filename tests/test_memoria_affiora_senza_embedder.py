"""Task 5 of "memoria fetta 2b" -- the last task, and the one that verifies
what the whole slice exists for.

The previous slice (2a) made memories get WRITTEN on a stock install (no
embedding provider configured -- the factory default builds a NullEmbedder,
whose embed() always returns []). This slice (2b) closed the gap between
"HIRIS remembers" and "HIRIS remembers by itself": three automatic
consumers (chat's RAG injection, the per-event sentinel reasoner, the
holistic daily review) used to give up entirely when there was no query
vector; Tasks 1-4 made them degrade to the most recent rows instead, headed
honestly ("Ultimi ricordi:" when the store fell back to recency, "Cosa so
di rilevante:" / "## Memoria rilevante" when it actually compared meanings).

Tasks 1-4 were each verified on their own terms, with fakes standing in for
the embedder. NONE of them verified the thing the slice exists for, end to
end, with the REAL NullEmbedder that ships in production. That is this
file's job -- see the module docstring convention shared with
tests/test_gather_context_memory.py for why some of these tests stop at a
module-level helper rather than the _on_startup closure (_gather_context)
that is not independently reachable from tests.

Originally three automatic consumers, chat included ("Test 1 -- the chat
remembers by itself" lived here, right below this docstring). Task 3 of the
"nucleo alla chat" slice (.superpowers/sdd/task-3-brief.md, 2.0) retired
that surface: `handle_chat` no longer calls `KnowledgeStore.search()`/
`.declared()` at all -- its context comes from the nucleo (`casa/nucleo.py`)
instead, which has no "degrades to recency when there's no embedder"
mechanic to verify (a nucleo without an embedder is unaffected; it doesn't
compare meanings in the first place). That test, and the chat portion of
Test 4 below, were removed rather than repointed -- there is no equivalent
chat-surface claim left to make here.

fetta E3 Task 5: the holistic daily review, the OTHER of the "two remaining
automatic consumers" mentioned above, exited too -- the Brain
auto-proponente (`brain.coverage_review`, `_holistic_reason`'s caller) is
gone. Test 3 below (`test_holistic_review_surfaces_saved_memory_without_
embedder`) and the holistic half of Test 4 were removed; only the per-event
sentinel reasoner is left to verify end to end below.
"""
import pytest

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.chat_store import close_all_stores
from hiris.app.server import _reason_memory_context
from hiris.app.watcher.reasoner import build_user_message
from hiris.app.watcher.signals import WakeEvent

MEMORY_TEXT = "l'utente preferisce 21 gradi in salotto"


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    """Same convention as tests/test_api.py: close SQLite connections opened
    by handle_chat's history/summary stores so Windows doesn't file-lock
    tmp_path across tests."""
    yield
    close_all_stores()


class _WorkingEmbedder:
    """Non-null embedder used only by Test 4 (non-regression): a stand-in
    for OpenAI/Ollama that returns a real, usable query vector, so the
    consumers take the by-meaning path instead of degrading."""

    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class _LocalRouter:
    """automatic_allows_sensitive() -> True, same shape LLMRouter exposes.
    Not exercising the egress gate itself here -- that is Task 1/2's job
    (tests/test_gather_context_memory.py) -- just a minimal stand-in so
    _reason_memory_context has something to call."""

    def automatic_allows_sensitive(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Test 2 -- the proactive reasoner remembers.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reasoner_prompt_surfaces_saved_memory_without_embedder(tmp_path):
    """The same memory reaches the per-event sentinel reasoner's prompt,
    again under the degraded heading.

    Drives the real chain: `_reason_memory_context` (the module-level
    helper `_gather_context` calls -- `_gather_context` itself is a closure
    inside `_on_startup` and is not independently reachable from tests, the
    same convention tests/test_gather_context_memory.py already
    establishes) with the real NullEmbedder and a real KnowledgeStore, then
    the real `build_user_message` with the context shaped exactly as
    `_gather_context` builds it (`memory` + `memory_by_meaning` alongside
    `friendly_name`).
    """
    store = KnowledgeStore(str(tmp_path / "mem_reasoner.db"))
    store.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home", status="approved",
    )
    app = {"knowledge_store": store, "llm_router": _LocalRouter()}
    wake = WakeEvent(
        signal_kind="temperature_change", entity_id="climate.salotto",
        severity_hint="info", evidence={}, ts=1.0,
    )

    mem = await _reason_memory_context(app, NullEmbedder(), wake, "Salotto")
    assert mem.by_meaning is False
    assert mem.snippets, "relevant_memory degraded to recency but found nothing"

    ctx = {
        "friendly_name": "Salotto",
        "memory": mem.snippets,
        "memory_by_meaning": mem.by_meaning,
    }
    msg = build_user_message(wake, ctx)

    assert "Ultimi ricordi:" in msg
    assert "Cosa so di rilevante" not in msg
    assert "21 gradi" in msg

    store.close()


# ---------------------------------------------------------------------------
# fetta E3 Task 5: Test 3 ("the holistic review remembers, and does not
# abort") lived here -- it exercised `relevant_memory()` for real and fed the
# result into `build_review_context`/`build_review_message`
# (`brain.coverage_review`), pinning the regression where a raw `MemoryRecall`
# hit `list(memory)` and raised inside `_holistic_reason`'s swallowed
# try/except. `brain.coverage_review` is cancelled whole in this task (the
# Brain auto-proponente it belonged to has no executor left to propose to,
# since Task 4); `_holistic_reason` itself was already gone since Task 4.
# No successor -- there is no holistic path left to regress.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Test 4 -- the non-regression (per-event reasoner only, since Task 5).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reasoner_uses_relevant_heading_with_working_embedder(tmp_path):
    """With a WORKING embedder (not the NullEmbedder), the per-event sentinel
    reasoner behaves exactly as it did before this slice: the usual "relevant
    by meaning" heading, because the store actually compared meanings instead
    of degrading to recency. A change that accidentally forces this path onto
    the degraded branch (e.g. always passing `[]` regardless of what embed()
    returned) would fail here even though Tests 1-2 above (which use
    NullEmbedder on purpose) would stay green.

    Was "all THREE surfaces" (chat included) before Task 3 of the "nucleo
    alla chat" slice retired the chat portion, then "both remaining surfaces"
    until fetta E3 Task 5 retired the holistic review -- see the module
    docstring."""
    embedder = _WorkingEmbedder()
    matching_vec = [1.0, 0.0, 0.0]

    store_reasoner = KnowledgeStore(str(tmp_path / "mem_reasoner_wk.db"))
    store_reasoner.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home", status="approved",
        embedding=matching_vec,
    )
    app_r = {"knowledge_store": store_reasoner, "llm_router": _LocalRouter()}
    wake = WakeEvent(
        signal_kind="temperature_change", entity_id="climate.salotto",
        severity_hint="info", evidence={}, ts=1.0,
    )
    mem_r = await _reason_memory_context(app_r, embedder, wake, "Salotto")
    assert mem_r.by_meaning is True
    msg_r = build_user_message(wake, {
        "friendly_name": "Salotto", "memory": mem_r.snippets,
        "memory_by_meaning": mem_r.by_meaning,
    })
    assert "Cosa so di rilevante:" in msg_r
    assert "Ultimi ricordi" not in msg_r
    store_reasoner.close()
