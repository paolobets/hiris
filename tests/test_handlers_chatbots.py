import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


# NOTE (SP-4 Fase B Task 1): the 5 /api/entities tests that used to live here
# exercised handlers_chatbots.handle_list_entities -- an unreachable copy that
# was never registered on any route (server.py registers
# handlers_entities.handle_list_entities on GET /api/entities instead). That
# dead function has been deleted; its tests were false confidence (green on
# code nothing ever called) and have been moved + rewritten against the real,
# canonical handler in tests/test_handlers_entities.py.

# fetta E4 Task 3 ("un bot solo"): handle_get_chatbot_usage/
# handle_reset_chatbot_usage (and their two tests that lived here,
# test_get_agent_usage_returns_stats/test_reset_agent_usage) are gone with
# every other CRUD/usage route -- verified failing for construction
# (ImportError: cannot import name 'handle_get_chatbot_usage') before
# deletion. handle_create_chatbot/handle_get_chatbot/handle_update_chatbot/
# handle_delete_chatbot and every test below that exercised them are gone
# too, for the same reason: the three surviving creation paths (wizard,
# empty editor, chat onboarding) all converged on POST /api/chatbots with
# `enabled: true` by default, the opposite of what the scope prescribes.
# `handle_list_chatbots` is the one handler left (compatibility surface,
# Global Constraints) -- its tests below are untouched, live subject.

# fetta E4 Task 4 ("un bot solo"): test_list_agents_has_budget_fields e
# test_list_agents_budget_computed_from_usage sono usciti -- il loro
# soggetto (handle_list_chatbots che calcolava budget_eur/usage da
# runner.get_chatbot_usage(agent_id)) e' uscito per intero col resto
# dell'entita' Chatbot: niente piu' usage per-persona con un bot solo senza
# id (l'elenco dei consumi torna nella E5). Verificato che
# cadessero per costruzione prima della cancellazione:
# test_list_agents_has_budget_fields -> AssertionError ("budget_eur" non e'
# piu' nel payload); test_list_agents_budget_computed_from_usage -> KeyError
# "budget_eur". test_list_agents_has_status_field resta: il campo "status"
# c'e' ancora (valore letterale "idle" ora, non piu' un lookup -- vedi
# handlers_chatbots.py).

# ---- Dashboard field tests (Task 2) ----

@pytest.fixture
def _dashboard_app(tmp_path):
    """Shared app factory for dashboard-field tests."""
    from hiris.app.server import create_app
    from hiris.app.impostazioni_chat import ImpostazioniChat
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ImpostazioniChat()
    app["claude_runner"] = mock_runner
    app["llm_router"] = mock_runner
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = ""
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def dashboard_client(aiohttp_client, _dashboard_app):
    from hiris.app.chat_store import close_all_stores
    yield await aiohttp_client(_dashboard_app)
    close_all_stores()


@pytest.mark.asyncio
async def test_list_agents_has_status_field(dashboard_client):
    resp = await dashboard_client.get("/api/chatbots")
    assert resp.status == 200
    agents = await resp.json()
    assert isinstance(agents, list)
    for agent in agents:
        assert "status" in agent
        assert agent["status"] in ("idle", "running", "error")


# fetta E4 Task 3: test_created_agent_has_all_dashboard_fields (POST-then-GET),
# test_delete_agent_cleans_memory_and_chat_history (DELETE), the four
# OpenRouter-model regression tests (POST/PUT), the two bogus-proactive-
# field validation tests, the two "no longer requires type" tests, and the
# four knowledge_access-validation tests (_validate_chatbot_payload direct)
# all exercised handle_create_chatbot/handle_update_chatbot/
# handle_delete_chatbot/_validate_chatbot_payload -- gone with the CRUD
# routes (verified failing for construction: `ImportError: cannot import
# name 'handle_create_chatbot'` before deletion). The three creation paths
# these tests defended (wizard, empty editor, chat onboarding) converged on
# POST /api/chatbots with `enabled: true` by default, the opposite of what
# the scope prescribes.
