import pytest
import pytest_asyncio
import re
import pathlib
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.chatbot_engine import ChatbotEngine, DEFAULT_CHATBOT_ID, Chatbot
from hiris.app.chat_store import close_all_stores


def _cfg_version() -> str:
    cfg = pathlib.Path(__file__).parent.parent / "hiris" / "config.yaml"
    m = re.search(r'^version:\s*"([^"]+)"', cfg.read_text(), re.MULTILINE)
    return m.group(1) if m else "unknown"


@pytest.fixture(autouse=True)
def reset_chat_stores():
    """Close SQLite connections after each test to avoid file-lock on Windows."""
    yield
    close_all_stores()


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
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

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Test response")
    mock_runner.last_tool_calls = []
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)

    app.on_startup.clear()
    app.on_cleanup.clear()

    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["version"] == _cfg_version()


@pytest.mark.asyncio
async def test_status_endpoint(client):
    resp = await client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "agents" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_chat_endpoint(client):
    resp = await client.post("/api/chat", json={"message": "Ciao"})
    assert resp.status == 200
    data = await resp.json()
    assert "response" in data


# fetta E4 Task 3 ("un bot solo"): test_agents_crud esercitava
# POST/GET-single/DELETE su /api/chatbots -- le tre strade di creazione
# sopravvissute alla E3 convergevano tutte li' con `enabled: true` di
# default, il contrario di quanto prescrive lo scope. Verificato che cadesse
# per costruzione (POST risponde 405, la rotta non e' piu' registrata)
# prima della cancellazione.


@pytest.mark.asyncio
async def test_chat_missing_message(client):
    resp = await client.post("/api/chat", json={})
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_chat_no_runner(aiohttp_client):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()

    from hiris.app.chatbot_engine import ChatbotEngine
    engine = ChatbotEngine(ha_client=mock_ha)
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = None
    app.on_startup.clear()
    app.on_cleanup.clear()

    c = await aiohttp_client(app)
    resp = await c.post("/api/chat", json={"message": "Hello"})
    assert resp.status == 503


# fetta E4 Task 3: test_agent_not_found (GET-single, `/api/chatbots/
# nonexistent-id`) is gone too -- not because it failed for construction
# (an unmatched route also 404s, so the assertion happened to still pass by
# coincidence) but because its subject, handle_get_chatbot, is gone; a
# passing assertion on a dead route is false confidence, the same trap the
# NOTE at the top of test_handlers_chatbots.py already names. test_agent_update
# (PUT after POST) exercised handle_create_chatbot/handle_update_chatbot,
# verified failing for construction (POST /api/chatbots -> 405) before
# deletion.


# test_agent_run (POST /api/chatbots/{id}/run) e' uscito con l'intero Test
# Run (fetta E4 Task 2, 2.0): morto per costruzione (TypeError su ogni
# chiamata reale ai runner, mai una risposta valida). Verificato che cadesse
# per costruzione prima della cancellazione: 404 invece del 200 atteso
# (route rimossa da server.py) -- vedi task-2-report.md.


# fetta E4 Task 3: test_delete_default_agent_returns_409 (DELETE
# /api/chatbots/{default_id}) exercised handle_delete_chatbot, gone with
# the rest of the CRUD -- verified failing for construction (405, route no
# longer registered) before deletion. The 409-on-default-delete guard lived
# only in the handler; ChatbotEngine.delete_chatbot itself (which also
# returned False for the default before saving) is gone too, per brief.


@pytest.mark.asyncio
async def test_chat_with_agent_id_uses_agent_system_prompt(client):
    from hiris.app.chatbot_engine import Chatbot
    engine = client.app["engine"]
    engine._chatbots["agent-chat-001"] = Chatbot(
        id="agent-chat-001", name="Energia", system_prompt="Sei un esperto di energia.",
        allowed_tools=[], enabled=True, is_default=False,
        strategic_context="Contesto: casa a Milano.",
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta energia")

    resp = await client.post("/api/chat", json={
        "message": "quanto consumo?",
        "agent_id": "agent-chat-001",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["response"] == "risposta energia"
    call_kwargs = runner.chat.call_args.kwargs
    assert "Contesto: casa a Milano." in call_kwargs["system_prompt"]
    assert "esperto di energia" in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_chat_without_agent_id_uses_default_agent(client):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    engine = client.app["engine"]
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="Prompt default HIRIS.",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta default")

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert "Prompt default HIRIS." in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_chat_with_unknown_agent_id_fallback_to_default(client):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    engine = client.app["engine"]
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="Fallback prompt.",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="fallback")

    resp = await client.post("/api/chat", json={
        "message": "ciao",
        "agent_id": "non-esiste-123",
    })
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert "Fallback prompt." in call_kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_config_endpoint_returns_theme(client):
    resp = await client.get("/api/config")
    assert resp.status == 200
    data = await resp.json()
    assert "theme" in data
    assert data["theme"] == "auto"


@pytest.mark.asyncio
async def test_chat_passes_model_to_runner(client):
    from hiris.app.chatbot_engine import Chatbot
    engine = client.app["engine"]
    engine._chatbots["agent-haiku-001"] = Chatbot(
        id="agent-haiku-001", name="Haiku Agent", system_prompt="Chat test",
        allowed_tools=[], enabled=True, is_default=False,
        model="claude-haiku-4-5-20251001", max_tokens=1024, restrict_to_home=False,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="ok")

    await client.post("/api/chat", json={"message": "test", "agent_id": "agent-haiku-001"})

    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    # chat is floored up to CHAT_MAX_TOKENS regardless of the stored per-agent
    # value — max_tokens is a ceiling, not a target, so this doesn't raise cost
    # for normal replies but prevents truncation of large outputs (dashboards).
    assert call_kwargs["max_tokens"] == 16000
    assert call_kwargs["agent_type"] == "chat"


@pytest.mark.asyncio
async def test_chat_max_turns_blocks_when_limit_reached(client):
    from hiris.app.chatbot_engine import Chatbot
    from hiris.app.chat_store import append_messages
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._chatbots["agent-limited"] = Chatbot(
        id="agent-limited", name="Limited", system_prompt="test",
        allowed_tools=[], enabled=True, is_default=False,
        max_chat_turns=2,
    )
    # Pre-fill 2 user turns in server-side history
    append_messages("agent-limited", [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply2"},
    ], data_dir)

    resp = await client.post("/api/chat", json={
        "message": "third message",
        "agent_id": "agent-limited",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data.get("error") == "max_turns_reached"
    assert data["turns"] == 2
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_chat_persists_exchange_in_history(client):
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    from hiris.app.chat_store import load_history
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="test",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="stored response")

    await client.post("/api/chat", json={"message": "persist me"})

    history = load_history(DEFAULT_CHATBOT_ID, data_dir)
    assert any(m["content"] == "persist me" for m in history)
    assert any(m["content"] == "stored response" for m in history)


@pytest.mark.asyncio
async def test_chat_does_not_persist_toxic_response(client):
    """Regression v0.9.9: synthetic-error responses (rate limit, leaked
    tool calls, etc.) must not be persisted to chat history — they would
    poison subsequent turns and the user already sees the error in the
    current response payload."""
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    from hiris.app.chat_store import load_history
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="test",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(
        return_value="Errore temporaneo del servizio AI. Riprova tra poco."
    )

    await client.post("/api/chat", json={"message": "fail me"})

    history = load_history(DEFAULT_CHATBOT_ID, data_dir)
    assert history == []  # nothing persisted


@pytest.mark.asyncio
async def test_chat_does_not_persist_leaked_tool_call_response(client):
    """Same protection for the TOOL_LEAK_USER_MSG sentinel returned by the
    runner when a model emits a tool call as raw text content."""
    from hiris.app.chatbot_engine import DEFAULT_CHATBOT_ID, Chatbot
    from hiris.app.chat_store import load_history
    from hiris.app.backends.openai_compat_runner import TOOL_LEAK_USER_MSG
    engine = client.app["engine"]
    data_dir = client.app["data_dir"]
    engine._chatbots[DEFAULT_CHATBOT_ID] = Chatbot(
        id=DEFAULT_CHATBOT_ID, name="HIRIS", system_prompt="test",
        allowed_tools=[], enabled=True, is_default=True,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value=TOOL_LEAK_USER_MSG)

    await client.post("/api/chat", json={"message": "leak me"})

    history = load_history(DEFAULT_CHATBOT_ID, data_dir)
    assert history == []


# test_chat_context_map_injects_area_context and the six test_chat_rag_*
# tests that used to live here were removed by Task 3 of the "nucleo alla
# chat" slice (.superpowers/sdd/task-3-brief.md, 2.0): they pinned the exact
# wiring that task retired -- SemanticContextMap.get_context() and
# KnowledgeStore.search()/.declared() called FROM handle_chat, with their
# output injected into context_str/visible_entity_ids. handle_chat stopped
# calling either; its context comes from the nucleo (hiris/app/casa/
# nucleo.py, via handlers_casa.costruisci_nucleo) -- see
# tests/test_chat_al_nucleo.py for the tests that replace these.
# SemanticContextMap itself (and knowledge_db, its only persistence) are gone
# now too -- fetta E3 Task 2 (2.0): the context-preview route was their last
# caller. KnowledgeStore.search()/.declared() were not deleted: they simply
# are not called from here anymore (their tests live in
# tests/test_knowledge_store*.py, untouched by this task).


# test_create_task_tool_via_chat, che viveva qui, e' cancellato dalla fetta
# E3 Task 9 ("esce il Task Engine"): montava un `task_engine` finto,
# chiamava `ClaudeRunner.set_task_engine` (gia' uscito col Task 8: il
# dispatcher di scorta a cui inoltrava non e' mai esistito in produzione) e
# verificava solo che /api/chat rispondesse 200 con `runner.chat` mockato --
# non esercitava mai `add_task`/`create_task` per davvero. Il modulo che
# importava (`hiris.app.task_engine`) e' cancellato: verificato che il test
# cade per costruzione con `ModuleNotFoundError: No module named
# 'hiris.app.task_engine'` prima della cancellazione.


@pytest.mark.asyncio
async def test_chat_debug_tools_called_returns_objects(client):
    """debug.tools_called must carry {tool, input} objects so the panel's
    appendDebug() can render chips without crashing.

    Regression: the handler used t.get("name") but last_tool_calls keys are
    "tool"/"input", so every entry was None. index.html appendDebug() then
    threw on t.input AFTER the answer had already rendered, surfacing a
    spurious "Errore di connessione. Riprova tra poco." with no backend error.
    """
    from unittest.mock import AsyncMock

    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="Ecco i consumi energia")
    runner.last_tool_calls = [
        {"tool": "get_energy_history", "input": {"hours": 24}},
        {"tool": "get_home_status", "input": {}},
    ]

    resp = await client.post("/api/chat", json={"message": "consumi energia"})
    assert resp.status == 200
    data = await resp.json()
    assert data["debug"]["tools_called"] == [
        {"tool": "get_energy_history", "input": {"hours": 24}},
        {"tool": "get_home_status", "input": {}},
    ]


# test_list_tasks_api_empty, che viveva qui, e' cancellato dalla fetta E3
# Task 9: colpiva GET /api/tasks, una delle tre rotte uscite col Task
# Engine. Verificato che cade per costruzione: senza la rotta registrata
# risponde 404 (era atteso 200) -- la pagina #/tasks (tasks-route.js) e il
# pannello Task della chat restano rotti apposta, vedi il report del task.


@pytest.mark.asyncio
async def test_chat_detokenizes_response(aiohttp_client, tmp_path):
    """Task 7 — de-tokenize: the handler must replace vault tokens in the
    runner's reply with real PII values before returning the JSON response,
    using ONLY the current exchange's own per-request token map (review
    B/#7) — never a global/vault-wide lookup. ``last_pseudonym_map`` here
    simulates the mapping the real recall_memory tool path would have
    populated during THIS exchange's own pseudonymize call."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    vault = VaultStore(str(tmp_path / "vault.db"))
    pseudonymizer = Pseudonymizer(vault)

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

    mock_runner = AsyncMock()
    # Runner returns a response that contains the vault token (not the real IBAN)
    mock_runner.chat = AsyncMock(return_value="Saldo su [IBAN_1].")
    mock_runner.last_tool_calls = []
    # This exchange's own per-request token map — as if recall_memory had
    # pseudonymized this IBAN into [IBAN_1] earlier in THIS same tool loop.
    mock_runner.last_pseudonym_map = {"[IBAN_1]": "IT60X0542811101000000123456"}
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["pseudonymizer"] = pseudonymizer

    app.on_startup.clear()
    app.on_cleanup.clear()

    c = await aiohttp_client(app)
    resp = await c.post("/api/chat", json={"message": "qual è il mio IBAN?"})
    assert resp.status == 200
    data = await resp.json()
    # The token must be replaced with the real value
    assert "IT60X0542811101000000123456" in data["response"]
    assert "[IBAN_1]" not in data["response"]
    vault.close()


@pytest.mark.asyncio
async def test_chat_does_not_detokenize_cross_request_token(aiohttp_client, tmp_path):
    """SECURITY (review B/#7): a reply containing a [TYPE_N]-shaped token that
    was NOT created by THIS exchange's own pseudonymize call (e.g. minted by
    a different conversation/user, hallucinated by the model, or injected via
    a poisoned document) must be returned VERBATIM — never expanded against
    the shared vault, even though the vault happens to hold a real mapping
    for that exact token string."""
    from hiris.app.brain.privacy import VaultStore, Pseudonymizer

    # A DIFFERENT conversation's PII lives in the shared vault under [IBAN_1].
    vault = VaultStore(str(tmp_path / "vault.db"))
    vault.token_for("iban", "IT00OTHERUSERSECRET000000001")  # creates [IBAN_1]
    pseudonymizer = Pseudonymizer(vault)

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

    mock_runner = AsyncMock()
    # THIS exchange's reply happens to mention the same token string, but
    # THIS exchange never pseudonymized anything -- its own map is empty.
    mock_runner.chat = AsyncMock(return_value="Il tuo saldo è su [IBAN_1].")
    mock_runner.last_tool_calls = []
    mock_runner.last_pseudonym_map = {}
    engine.set_claude_runner(mock_runner)

    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["pseudonymizer"] = pseudonymizer

    app.on_startup.clear()
    app.on_cleanup.clear()

    c = await aiohttp_client(app)
    resp = await c.post("/api/chat", json={"message": "qual è il mio IBAN?"})
    assert resp.status == 200
    data = await resp.json()
    # Must NOT leak the other conversation's real IBAN.
    assert "IT00OTHERUSERSECRET000000001" not in data["response"]
    assert "[IBAN_1]" in data["response"]
    vault.close()
