import pytest
import pytest_asyncio
import re
import pathlib
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import TestClient
from hiris.app.server import create_app
from hiris.app.impostazioni_chat import ImpostazioniChat
from hiris.app.chat_store import close_all_stores


def _cfg_version() -> str:
    cfg = pathlib.Path(__file__).parent.parent / "hiris" / "config.yaml"
    # config.yaml e' UTF-8 per specifica di Home Assistant: leggerlo con la
    # codepage di sistema (il default di read_text) esplode su Windows appena
    # il file contiene un carattere fuori da cp1252.
    m = re.search(r'^version:\s*"([^"]+)"',
                  cfg.read_text(encoding="utf-8"), re.MULTILINE)
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

    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="Test response")
    mock_runner.last_tool_calls = []

    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ImpostazioniChat()
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


# fetta E4 Task 4 ("un bot solo"): test_status_endpoint esercitava
# GET /api/status -- uscita insieme all'entita' Chatbot (Decisione 6 del
# brief: era una rotta solo-test, il suo unico contenuto era un conteggio
# `agents.total`/`agents.enabled` che non significa piu' niente con un bot
# solo). Verificato che cadesse per costruzione (404, rotta non piu'
# registrata) prima della cancellazione.


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

    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ImpostazioniChat()
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


# fetta E4 Task 4 ("un bot solo"): test_chat_with_agent_id_uses_agent_system_
# prompt, test_chat_without_agent_id_uses_default_agent e
# test_chat_with_unknown_agent_id_fallback_to_default pinnavano una
# SELEZIONE fra piu' `Chatbot` diversi per id -- quella selezione non esiste
# piu': c'e' un solo `ImpostazioniChat`, senza id, e il `chatbot_id`/
# `agent_id` che il client manda viene accettato e ignorato (vedi
# handlers_chat.py). Verificato prima di riscriverli: coi vecchi corpi
# ancora in piedi, `client.app["engine"]` solleva `KeyError` -- il
# fixture non lo valorizza piu'. Le tre riscritte sotto verificano lo stesso
# comportamento di fondo (il prompt configurato arriva al runner, un id
# sconosciuto o assente non rompe nulla) senza pretendere una selezione che
# non c'e' piu'.


@pytest.mark.asyncio
async def test_chat_usa_il_system_prompt_delle_impostazioni(client):
    client.app["impostazioni_chat"] = ImpostazioniChat(
        nome="Energia", system_prompt="Sei un esperto di energia.",
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta energia")

    resp = await client.post("/api/chat", json={
        "message": "quanto consumo?",
        "chatbot_id": "qualunque-cosa",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["response"] == "risposta energia"
    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["system_prompt"] == "Sei un esperto di energia."


@pytest.mark.asyncio
async def test_chat_senza_chatbot_id_usa_comunque_le_impostazioni(client):
    client.app["impostazioni_chat"] = ImpostazioniChat(system_prompt="Prompt di default HIRIS.")
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="risposta default")

    resp = await client.post("/api/chat", json={"message": "ciao"})
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["system_prompt"] == "Prompt di default HIRIS."


@pytest.mark.asyncio
async def test_chat_con_chatbot_id_sconosciuto_non_rompe_e_ignora_lid(client):
    """Prima un `agent_id` che non corrispondeva a nessun Chatbot ricadeva
    sul default (fallback). Ora non c'e' nessuna ricerca da far fallire: un
    id qualsiasi -- esistito o mai esistito -- non cambia il comportamento,
    perche' non seleziona piu' niente."""
    client.app["impostazioni_chat"] = ImpostazioniChat(system_prompt="Fallback prompt.")
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="fallback")

    resp = await client.post("/api/chat", json={
        "message": "ciao",
        "agent_id": "non-esiste-123",
    })
    assert resp.status == 200
    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["system_prompt"] == "Fallback prompt."


@pytest.mark.asyncio
async def test_chat_con_chatbot_id_si_comporta_come_senza(aiohttp_client, tmp_path):
    """fetta E5 Task 10: la lettura esplicita di `chatbot_id`/`agent_id`
    (`_chatbot_id_ignorato = body.get(...)`, dieci righe di commento incluse)
    esce da handlers_chat.py insieme all'ultimo chiamante della superficie
    che la mandava. Il comportamento dichiarato dal commento cancellato --
    "una richiesta che la porta non si comporta diversamente da una che la
    omette" -- non era mai stato pinnato da un test: qui lo verifichiamo
    davvero, non solo affermato. aiohttp non valida il corpo della request,
    quindi una chiave extra nel JSON non fa differenza nemmeno senza un
    `.get()` esplicito che la legga e la scarti.

    Due app/data_dir indipendenti (non lo stesso `client`/tmp_path condiviso
    delle altre prove qui sopra): la cronologia e' un'unica conversazione
    incondizionata (fetta E4 Task 5), quindi due richieste sullo stesso store
    differirebbero per `conversation_history` a prescindere da `chatbot_id`
    -- un rumore che nasconderebbe il confronto, non lo farebbe."""
    def _build(data_dir_name):
        mock_ha = AsyncMock()
        mock_ha.get_states = AsyncMock(return_value=[])
        mock_ha.start = AsyncMock()
        mock_ha.stop = AsyncMock()
        mock_ha.add_state_listener = MagicMock()
        mock_ha.start_websocket = AsyncMock()
        mock_runner = AsyncMock()
        mock_runner.chat = AsyncMock(return_value="stessa risposta")
        mock_runner.last_tool_calls = []
        app = create_app()
        app["ha_client"] = mock_ha
        app["impostazioni_chat"] = ImpostazioniChat(system_prompt="Prompt fisso.")
        app["claude_runner"] = mock_runner
        app["theme"] = "auto"
        app["data_dir"] = str(tmp_path / data_dir_name)
        app.on_startup.clear()
        app.on_cleanup.clear()
        return app, mock_runner

    app_con, runner_con = _build("con")
    client_con = await aiohttp_client(app_con)
    resp_con = await client_con.post("/api/chat", json={
        "message": "ciao",
        "chatbot_id": "qualunque-cosa",
    })
    assert resp_con.status == 200
    body_con = await resp_con.json()
    kwargs_con = dict(runner_con.chat.call_args.kwargs)

    app_senza, runner_senza = _build("senza")
    client_senza = await aiohttp_client(app_senza)
    resp_senza = await client_senza.post("/api/chat", json={"message": "ciao"})
    assert resp_senza.status == 200
    body_senza = await resp_senza.json()
    kwargs_senza = dict(runner_senza.chat.call_args.kwargs)

    # `dispatcher` e' un oggetto per-app (un'istanza di DispatcherStrumenti
    # per `create_app()`), non qualcosa che `chatbot_id` influenza: due app
    # indipendenti ne creano due identita' diverse per costruzione. Il tipo
    # e' comunque lo stesso, a riprova che non e' un ramo di codice diverso.
    assert type(kwargs_con.pop("dispatcher")) is type(kwargs_senza.pop("dispatcher"))
    assert body_con == body_senza
    assert kwargs_con == kwargs_senza


@pytest.mark.asyncio
async def test_config_endpoint_returns_theme(client):
    resp = await client.get("/api/config")
    assert resp.status == 200
    data = await resp.json()
    assert "theme" in data
    assert data["theme"] == "auto"


@pytest.mark.asyncio
async def test_chat_chiede_sempre_auto_al_runner(client):
    """Si chiamava `test_chat_passes_model_to_runner` e pinnava lo SCAVALCO:
    un modello fissato in «Impostazioni chat» arrivava tale e quale al runner,
    dove `LLMRouter.chat` lo mandava a `_route()` -- una scelta sola, nessuna
    catena, nessun ripiego, e la pagina Modelli che non lo nominava mai.

    fetta «la catena diventa l'unica verità» (Task 4): quel campo è uscito e
    il turno chiede sempre `auto`. Il test non è stato cancellato perché dava
    fastidio: il suo soggetto è cambiato di segno, e questo è l'unico posto
    che lo verifica sull'app VERA (`create_app`), non su un'app di prova."""
    client.app["impostazioni_chat"] = ImpostazioniChat(
        nome="Haiku", system_prompt="Chat test", restrict_to_home=False,
    )
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="ok")

    await client.post("/api/chat", json={"message": "test"})

    call_kwargs = runner.chat.call_args.kwargs
    assert call_kwargs["model"] == "auto"
    # fetta E4 Task 4: `max_tokens` non e' piu' un campo delle impostazioni
    # (era gia' inerte in pratica -- vedi handlers_chat.py) -- la chat usa
    # sempre CHAT_MAX_TOKENS come tetto, non piu' un valore floorato.
    assert call_kwargs["max_tokens"] == 16000
    assert call_kwargs["agent_type"] == "chat"


@pytest.mark.asyncio
async def test_chat_max_turns_blocks_when_limit_reached(client):
    from hiris.app.chat_store import append_messages
    client.app["impostazioni_chat"] = ImpostazioniChat(max_chat_turns=2)
    data_dir = client.app["data_dir"]
    # Pre-fill 2 user turns nell'UNICA cronologia server-side (fetta E4
    # Task 5: chat_store non prende piu' un id -- vedi handlers_chat.py).
    append_messages([
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply2"},
    ], data_dir)

    resp = await client.post("/api/chat", json={"message": "third message"})
    assert resp.status == 200
    data = await resp.json()
    assert data.get("error") == "max_turns_reached"
    assert data["turns"] == 2
    assert data["limit"] == 2


@pytest.mark.asyncio
async def test_chat_persists_exchange_in_history(client):
    from hiris.app.chat_store import load_history
    data_dir = client.app["data_dir"]
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value="stored response")

    await client.post("/api/chat", json={"message": "persist me"})

    history = load_history(data_dir)
    assert any(m["content"] == "persist me" for m in history)
    assert any(m["content"] == "stored response" for m in history)


@pytest.mark.asyncio
async def test_chat_does_not_persist_toxic_response(client):
    """Regression v0.9.9: synthetic-error responses (rate limit, leaked
    tool calls, etc.) must not be persisted to chat history — they would
    poison subsequent turns and the user already sees the error in the
    current response payload."""
    from hiris.app.chat_store import load_history
    data_dir = client.app["data_dir"]
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(
        return_value="Errore temporaneo del servizio AI. Riprova tra poco."
    )

    await client.post("/api/chat", json={"message": "fail me"})

    history = load_history(data_dir)
    assert history == []  # nothing persisted


@pytest.mark.asyncio
async def test_chat_does_not_persist_leaked_tool_call_response(client):
    """Same protection for the TOOL_LEAK_USER_MSG sentinel returned by the
    runner when a model emits a tool call as raw text content."""
    from hiris.app.chat_store import load_history
    from hiris.app.backends.openai_compat_runner import TOOL_LEAK_USER_MSG
    data_dir = client.app["data_dir"]
    runner = client.app["claude_runner"]
    runner.chat = AsyncMock(return_value=TOOL_LEAK_USER_MSG)

    await client.post("/api/chat", json={"message": "leak me"})

    history = load_history(data_dir)
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
# caller. KnowledgeStore.search()/.declared() were not deleted back then: they
# simply stopped being called from here. La fetta "esce il documentale" le ha
# poi cancellate insieme all'intero KnowledgeStore -- da allora non avevano
# ripreso nessun chiamante di produzione -- e con loro
# tests/test_knowledge_store*.py.


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
# risponde 404 (era atteso 200). Le due interfacce che restavano rotte --
# la pagina #/tasks (config/tasks-route.js) e il pannello Task della chat
# (chat/tasks.js) -- sono uscite con la fetta E5 Task 6.


# Fetta "esce il documentale": qui vivevano `test_chat_detokenizes_response` e
# `test_chat_does_not_detokenize_cross_request_token`. Cadono PER COSTRUZIONE,
# non per fastidio: il loro soggetto -- `hiris.app.brain.privacy`
# (`VaultStore`/`Pseudonymizer`) e la chiamata a `pseudonymizer.detokenize()`
# dentro `handle_chat` -- e' uscito con questa fetta. Entrambi importavano
# `from hiris.app.brain.privacy import VaultStore, Pseudonymizer` alla prima
# riga del corpo: senza il modulo sollevano ModuleNotFoundError prima ancora
# di arrivare a un'asserzione, e non esiste una riscrittura che li salvi
# perche' non c'e' piu' nessun token da riespandere.
#
# Non lasciano un buco di copertura: la pseudonimizzazione era INERTE da
# tempo. Nessun percorso di produzione chiamava piu' `pseudonymize()`, quindi
# `last_pseudonym_map` era sempre vuota; questi due test la valorizzavano A
# MANO sul finto runner (`mock_runner.last_pseudonym_map = {...}`) per poter
# osservare la riespansione. Provavano una funzione che nessun utente
# raggiungeva.
