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
from hiris.app.brain.reasoner_memory import DECLARED_ITEM_MAX
from hiris.app.chat_store import close_all_stores
from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot, ChatbotEngine
from hiris.app.server import create_app

DECLARED_TEXT = "il modulo meteo esterno e' guasto, non proporre sensori esterni"


@pytest.fixture(autouse=True)
def _close_chat_stores_after_each_test():
    yield
    close_all_stores()


async def _build_chat_client(aiohttp_client, tmp_path, *, store=None, embedder=None,
                             knowledge_access=None):
    """Same wiring as test_memoria_affiora_senza_embedder.py's
    _build_chat_client -- kept local/self-contained on purpose (same
    reasoning as that file's own docstring).

    `knowledge_access` (Fix 2, whole-branch review, final fix wave): lets a
    test configure the default Chatbot's `knowledge_access.kinds` egress,
    exactly the value declared() must now honor -- None keeps the previous
    default (no restriction), matching every pre-existing test in this file
    byte-for-byte."""
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
    default_chatbot_kwargs = dict(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="base prompt",
        allowed_tools=[], enabled=True, is_default=True,
    )
    if knowledge_access is not None:
        default_chatbot_kwargs["knowledge_access"] = knowledge_access
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(**default_chatbot_kwargs)

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
# Fix 1 (CRITICAL, whole-branch review, final fix wave): source='gateway'
# (a save_memory call routed through the remote MCP gateway) must not appear
# in the chat declared block, while source='chat' (the local chat path)
# still does -- the exact regression this test pins on the chat surface.
# ---------------------------------------------------------------------------

def _declared_section(context_str: str) -> str:
    """Slice out just the "## Fatti dichiarati" block, mirroring
    test_memoria_ricorda.py's `_declared_section` for build_user_message.
    Needed here because a kind='memory' row is ALSO eligible for the
    query-independent RAG block below ("## Ultimi ricordi"/"## Memoria
    rilevante", via KnowledgeStore.search -- which does NOT filter by
    `source`, by design: it is the "recallable" surface, not the "declared"
    one) -- asserting over the whole context_str would conflate the two."""
    marker = "## Fatti dichiarati"
    if marker not in context_str:
        return ""
    start = context_str.index(marker)
    rest = context_str[start:]
    end = rest.find("\n\n##")
    return rest if end == -1 else rest[:end]


@pytest.mark.asyncio
async def test_gateway_sourced_item_does_not_appear_declared_but_chat_sourced_does(
    aiohttp_client, tmp_path,
):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="memory", content="iniettato via gateway MCP remoto", owner="home",
        status="approved", source="gateway",
    )
    store.add_item(
        kind="memory", content=DECLARED_TEXT, owner="home",
        chatbot_id=DEFAULT_CHATBOT_ID, status="approved", source="chat",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "che ore sono?"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    declared_section = _declared_section(context_str)
    assert declared_section, "il blocco 'Fatti dichiarati' deve comunque comparire"
    assert "iniettato via gateway MCP remoto" not in declared_section, (
        "una riga con source='gateway' non deve mai entrare nel blocco "
        "'Fatti dichiarati' della chat -- resta recuperabile altrove "
        "(es. '## Ultimi ricordi', che NON filtra per source: e' la "
        "superficie 'recuperabile', non quella 'dichiarata'), ma non deve "
        "essere iniettata come se una persona l'avesse detta"
    )
    assert "modulo meteo esterno" in declared_section, (
        "una riga con source='chat' (percorso di chat locale) deve "
        "continuare a comparire nel blocco dichiarati, invariata da questo fix"
    )
    store.close()


# ---------------------------------------------------------------------------
# Fix 2 (Important, whole-branch review, final fix wave): the declared block
# must honor the agent's knowledge_access.kinds egress -- before this fix,
# declared() was called with no kinds at all, so a chatbot configured with
# kinds=[] ("no second-brain access", a value the UI permits) or
# kinds=['fact'] was correctly refused when it ASKED for a fact via
# recall_memory, yet received that same fact (and every other declared item)
# injected into its prompt on every single turn regardless.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declared_block_respects_kinds_empty_but_keeps_own_memory(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="fact", content=DECLARED_TEXT, owner="home",
        status="approved", source="chat",
    )
    store.add_item(
        kind="memory", content="nota privata dell'agente", owner="home",
        chatbot_id=DEFAULT_CHATBOT_ID, status="approved", source="chat",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
        knowledge_access={"allow_sensitive": False, "kinds": []},
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "modulo meteo esterno" not in context_str, (
        "kinds=[] ('nessun accesso al second brain') deve bloccare un "
        "dichiarato di kind='fact' anche nel blocco 'dichiarati', non solo "
        "su recall_memory"
    )
    assert "nota privata dell'agente" in context_str, (
        "kinds=[] non deve bloccare la memoria propria dell'agente "
        "(kind='memory', unita da union_memory_kind)"
    )
    store.close()


@pytest.mark.asyncio
async def test_declared_block_respects_kinds_restricted_to_fact(aiohttp_client, tmp_path):
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="expense", content="bolletta luce 123 euro", owner="home",
        status="approved", source="chat",
    )
    store.add_item(
        kind="fact", content=DECLARED_TEXT, owner="home",
        status="approved", source="chat",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
        knowledge_access={"allow_sensitive": False, "kinds": ["fact"]},
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert "modulo meteo esterno" in context_str
    assert "bolletta luce" not in context_str, (
        "kinds=['fact'] deve escludere un dichiarato di kind='expense' dal "
        "blocco 'dichiarati'"
    )
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


# ---------------------------------------------------------------------------
# Fix 5 (Minor, whole-branch review, final fix wave): a single declared item
# has no per-item cap on this surface -- the manual API accepts content up to
# 1000 characters, so an oversized item entered EVERY chat prompt in full,
# forever. The two proactive surfaces already cap at DECLARED_ITEM_MAX (500)
# with a visible "… (troncato)" marker via reasoner_memory.
# sanitize_declared_item; this pins the same helper being reused here rather
# than a second, possibly-diverging cap.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_declared_block_caps_a_single_oversized_item(aiohttp_client, tmp_path):
    long_content = "x" * 900  # under the manual API's 1000-char ceiling
    store = KnowledgeStore(str(tmp_path / "mem.db"))
    store.add_item(
        kind="note", content=long_content, owner="home",
        status="approved", source="manual",
    )
    client, mock_runner = await _build_chat_client(
        aiohttp_client, tmp_path, store=store, embedder=NullEmbedder(),
    )

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200

    context_str = mock_runner.chat.call_args.kwargs["context_str"]
    assert long_content not in context_str, (
        "un item dichiarato piu' lungo di DECLARED_ITEM_MAX deve essere "
        "tagliato, non entrare per intero nel prompt"
    )
    assert "x" * DECLARED_ITEM_MAX in context_str
    assert "(troncato)" in context_str, (
        "il taglio deve essere dichiarato esplicitamente, mai silenzioso"
    )
    store.close()
