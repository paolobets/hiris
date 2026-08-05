"""Task 4 of "memoria unica 3a", chat side: `handlers_chat.handle_chat` gains
an always-present "## Fatti dichiarati" block, built from
`KnowledgeStore.declared()` -- independent of the embedder and of whether the
current message resembles the declared content at all (unlike the existing
"## Memoria rilevante" / "## Ultimi ricordi" RAG block, which IS query-
dependent).

Follows the real-HTTP-path convention established by
tests/test_memoria_affiora_senza_embedder.py (reads context_str out of the
mocked runner.chat() call -- exactly what handle_chat hands to the LLM).
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from hiris.app.backends.embeddings import NullEmbedder
from hiris.app.brain.knowledge_store import DECLARED_MAX, KnowledgeStore
from hiris.app.chat_store import close_all_stores
from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot, ChatbotEngine
from hiris.app.server import create_app

DECLARED_TEXT = "il modulo meteo esterno e' guasto, non proporre sensori esterni"


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


async def _build_chat_client(aiohttp_client, tmp_path, *, store=None, embedder=None):
    """Same wiring as test_memoria_affiora_senza_embedder.py's
    _build_chat_client -- kept local/self-contained on purpose (same
    reasoning as that file's own docstring)."""
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
    if store is not None:
        app["knowledge_store"] = store
    if embedder is not None:
        app["embedding_provider"] = embedder
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    return client, mock_runner


# ---------------------------------------------------------------------------
# Requirement 1: a declared item appears WITHOUT an embedder and WITHOUT the
# question resembling it -- the behaviour that does not exist before Task 4.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declared_item_appears_without_embedder_or_resemblance(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content=DECLARED_TEXT, owner="home",
        chatbot_id=DEFAULT_CHATBOT_ID, status="approved", source="chat",
        # No embedding -- the point is this must appear with NO embedder
        # configured at all (NullEmbedder below) and a totally unrelated
        # question.
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post(
        "/api/chat", json={"message": "che ore sono?"}
    )
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Fatti dichiarati" in context_str
    assert "modulo meteo esterno" in context_str
    store.close()


# ---------------------------------------------------------------------------
# Requirement 2: an insight does NOT appear in the declared block.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insight_does_not_appear_in_declared_block(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="insight", content="media settimanale del consumo elettrico",
        owner="home", status="approved", source="history-digest",
        embedding=[1.0, 0.0, 0.0],
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "media settimanale" not in context_str
    store.close()


# ---------------------------------------------------------------------------
# Requirement 4: with zero declared items, the prompt is byte-identical to
# before -- no block, no stray blank line.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_byte_identical_context_when_no_declared_items(aiohttp_client, tmp_path):
    client_no_store, mock_runner_no_store = await _build_chat_client(
        aiohttp_client, tmp_path,
    )
    resp = await client_no_store.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200
    reference = mock_runner_no_store.chat.call_args.kwargs["context_str"]
    assert "Fatti dichiarati" not in reference

    store = KnowledgeStore(str(tmp_path / "mem_empty.db"))
    client_empty_store, mock_runner_empty_store = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )
    resp2 = await client_empty_store.post("/api/chat", json={"message": "ciao"})
    assert resp2.status == 200
    with_empty_store = mock_runner_empty_store.chat.call_args.kwargs["context_str"]

    assert with_empty_store == reference
    store.close()


# ---------------------------------------------------------------------------
# Requirement 5: sensitive/owner filters apply exactly as elsewhere -- an
# item of another owner marked sensitive must never appear.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declared_block_hides_other_owners_sensitive_item(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="segreto personale di un altro abitante",
        owner="qualcun_altro", status="approved", source="chat",
        sensitivity="sensitive",
    )
    store.add_item(
        kind="memory", content=DECLARED_TEXT, owner="home",
        status="approved", source="chat",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "segreto personale" not in context_str
    assert "modulo meteo esterno" in context_str
    store.close()


# ---------------------------------------------------------------------------
# Requirement 3: the limit is respected, and overflow is declared, not
# silent.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declared_block_states_overflow_when_limit_exceeded(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    for i in range(DECLARED_MAX + 3):
        store.add_item(
            kind="memory", content=f"fatto dichiarato numero {i}", owner="home",
            status="approved", source="chat",
        )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "## Fatti dichiarati" in context_str
    assert "+ altri 3" in context_str
    store.close()


@pytest.mark.asyncio
async def test_declared_block_no_overflow_note_when_under_limit(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content=DECLARED_TEXT, owner="home",
        status="approved", source="chat",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "non mostrat" not in context_str
    store.close()
