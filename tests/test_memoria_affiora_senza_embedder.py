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
tests/test_gather_context_memory.py and tests/test_coverage_review_memory.py
for why some of these tests stop at a module-level helper rather than the
_on_startup closures (_gather_context, _holistic_reason) that are not
independently reachable from tests.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.coverage_review import build_review_context, build_review_message
from hiris.app.brain.knowledge_store import KnowledgeStore
from hiris.app.brain.reasoner_memory import relevant_memory
from hiris.app.chat_store import close_all_stores
from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot, ChatbotEngine
from hiris.app.server import _reason_memory_context, create_app
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


async def _build_chat_client(aiohttp_client, tmp_path):
    """Same wiring as tests/test_api.py's `client` fixture, inlined here so
    this file is self-contained and can attach a fresh KnowledgeStore +
    embedding_provider per test without cross-file fixture coupling."""
    app = create_app()

    mock_ha = AsyncMock()
    mock_ha.get_states = AsyncMock(return_value=[])
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="base prompt",
        allowed_tools=[], enabled=True, is_default=True,
    )

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    return client, mock_runner


# ---------------------------------------------------------------------------
# Test 1 -- the chat remembers by itself.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_surfaces_saved_memory_without_embedder(aiohttp_client, tmp_path):
    """A memory is saved (with the real NullEmbedder wired as
    app["embedding_provider"], exactly what a stock install has), and on a
    SUBSEQUENT chat turn it appears in the prompt context ON ITS OWN --
    nobody asks for it, no tool call, no query_vec -- under the degraded
    heading.

    Goes through the real production HTTP path (POST /api/chat ->
    handlers_chat.handle_chat), not a shortcut straight to the store: the
    assertion reads context_str out of the mocked runner.chat() call, which
    is exactly what handle_chat hands to the LLM.
    """
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)

    store = KnowledgeStore(str(tmp_path / "mem_chat.db"))
    store.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home",
        chatbot_id=DEFAULT_CHATBOT_ID, status="approved",
        # No `embedding=` -- this memory was saved the way a stock install
        # saves one: no vector to compare against.
    )
    client.app["knowledge_store"] = store
    # The real factory default, not a fake -- this is the whole point.
    client.app["embedding_provider"] = NullEmbedder()

    resp = await client.post(
        "/api/chat", json={"message": "che temperatura preferisco in salotto?"}
    )
    assert resp.status == 200

    call_kwargs = mock_runner.chat.call_args.kwargs
    context_str = call_kwargs["context_str"]

    assert "## Ultimi ricordi" in context_str
    assert "## Memoria rilevante" not in context_str
    assert "21 gradi" in context_str

    store.close()


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
# Test 3 -- the holistic review remembers, and does not abort.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_holistic_review_surfaces_saved_memory_without_embedder(tmp_path):
    """This one matters more than it looks.

    Before this slice's Task 3, a `MemoryRecall` reached
    `build_review_context`'s `list(memory)` and raised `TypeError`, which
    `_holistic_reason`'s outer try/except swallowed -- the entire daily
    review aborted silently, and the full suite stayed green because no
    test crossed that path with a REAL `MemoryRecall`. Task 3's own
    regression test (test_coverage_review_memory.py::
    test_holistic_review_produces_message_from_real_memoryrecall) hand-built
    a `MemoryRecall(snippets=[...], by_meaning=True)` instead of getting one
    from `relevant_memory()` -- so when it failed pre-fix, it failed for a
    WEAKER reason (a missing `memory_by_meaning` keyword argument) than the
    real defect (the dataclass itself hitting `list(memory)`).

    This test calls `relevant_memory()` for real -- with the real
    NullEmbedder and a real KnowledgeStore -- and feeds its ACTUAL return
    value into `build_review_context`/`build_review_message`, exactly as
    the fixed `_holistic_reason` call site does (`memory=_mem.snippets,
    memory_by_meaning=_mem.by_meaning`). `_holistic_reason` itself is a
    closure inside `_on_startup` and is not independently reachable from
    tests (same convention as test_coverage_wiring.py /
    test_coverage_review_memory.py), so this is as far end-to-end as this
    file can honestly go: relevant_memory() itself is genuine, not a stand-in;
    only the two-line call-site wiring between it and _llm_reason is
    reproduced rather than executed through the closure.

    The assertion that matters most is the one that doesn't look like an
    assertion: `build_review_message(ctx)` completing at all, instead of
    raising `TypeError` and being swallowed three frames up in production.
    """
    store = KnowledgeStore(str(tmp_path / "mem_holistic.db"))
    store.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home", status="approved",
    )

    mem = await relevant_memory(
        store, NullEmbedder(),
        query_text="stato generale della casa", allow_sensitive=False, limit=5,
    )
    assert mem.by_meaning is False
    assert mem.snippets, "relevant_memory degraded to recency but found nothing"

    ctx = build_review_context(
        {"s": 1}, [{"entity_id": "climate.salotto"}], {},
        memory=mem.snippets, memory_by_meaning=mem.by_meaning,
    )
    msg = build_review_message(ctx)  # must not raise -- this IS the regression check

    assert "Ultimi ricordi:" in msg
    assert "Cosa so di rilevante" not in msg
    assert "21 gradi" in msg

    store.close()


# ---------------------------------------------------------------------------
# Test 4 -- the non-regression.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_three_surfaces_use_relevant_heading_with_working_embedder(
    aiohttp_client, tmp_path,
):
    """With a WORKING embedder (not the NullEmbedder), all three surfaces
    behave exactly as they did before this slice: the usual "relevant by
    meaning" heading, because the store actually compared meanings instead
    of degrading to recency. One test, three surfaces, so a change that
    accidentally forces every path onto the degraded branch (e.g. always
    passing `[]` regardless of what embed() returned) would fail here even
    though Tests 1-3 (which use NullEmbedder on purpose) would stay green.
    """
    embedder = _WorkingEmbedder()
    matching_vec = [1.0, 0.0, 0.0]

    # --- chat -----------------------------------------------------------
    client, mock_runner = await _build_chat_client(aiohttp_client, tmp_path)
    store_chat = KnowledgeStore(str(tmp_path / "mem_chat_wk.db"))
    store_chat.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home",
        chatbot_id=DEFAULT_CHATBOT_ID, status="approved", embedding=matching_vec,
    )
    client.app["knowledge_store"] = store_chat
    client.app["embedding_provider"] = embedder

    resp = await client.post(
        "/api/chat", json={"message": "che temperatura preferisco in salotto?"}
    )
    assert resp.status == 200
    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Memoria rilevante" in context_str
    assert "## Ultimi ricordi" not in context_str
    store_chat.close()

    # --- per-event reasoner ---------------------------------------------
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

    # --- holistic review --------------------------------------------------
    store_holistic = KnowledgeStore(str(tmp_path / "mem_holistic_wk.db"))
    store_holistic.add_item(
        kind="memory", content=MEMORY_TEXT, owner="home", status="approved",
        embedding=matching_vec,
    )
    mem_h = await relevant_memory(
        store_holistic, embedder,
        query_text="stato generale della casa", allow_sensitive=False, limit=5,
    )
    assert mem_h.by_meaning is True
    ctx_h = build_review_context(
        {"s": 1}, [{"entity_id": "climate.salotto"}], {},
        memory=mem_h.snippets, memory_by_meaning=mem_h.by_meaning,
    )
    msg_h = build_review_message(ctx_h)
    assert "Cosa so di rilevante:" in msg_h
    assert "Ultimi ricordi" not in msg_h
    store_holistic.close()
