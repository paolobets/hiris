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

# ---- Dashboard field tests (Task 2) ----

@pytest.fixture
def _dashboard_app(tmp_path):
    """Shared app factory for dashboard-field tests."""
    from hiris.app.server import create_app
    from hiris.app.chatbot_engine import ChatbotEngine
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = ChatbotEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    mock_runner = AsyncMock()
    mock_runner.chat = AsyncMock(return_value="ok")
    mock_runner.last_tool_calls = []
    mock_runner.get_chatbot_usage = MagicMock(return_value={
        "input_tokens": 100, "output_tokens": 50,
        "requests": 2, "cost_usd": 0.13, "last_run": None,
    })
    engine.set_claude_runner(mock_runner)
    app["ha_client"] = mock_ha
    app["engine"] = engine
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


@pytest.mark.asyncio
async def test_list_agents_has_budget_fields(dashboard_client):
    """Task 3: `budget_limit_eur` is gone from the /api/chatbots payload — it
    was a defensive `.get("budget_eur_limit", 0.0)` read of a dataclass field
    Task 2 already removed, so it was always hardcoded 0.0. `budget_eur`
    (actual computed usage cost) is the only budget field left."""
    resp = await dashboard_client.get("/api/chatbots")
    assert resp.status == 200
    agents = await resp.json()
    for agent in agents:
        assert "budget_eur" in agent
        assert isinstance(agent["budget_eur"], float)
        assert "budget_limit_eur" not in agent


@pytest.mark.asyncio
async def test_list_agents_budget_computed_from_usage(dashboard_client):
    resp = await dashboard_client.get("/api/chatbots")
    assert resp.status == 200
    agents = await resp.json()
    # mock_runner returns cost_usd=0.13, EUR rate=0.92 → 0.1196
    for agent in agents:
        assert agent["budget_eur"] == round(0.13 * 0.92, 4)


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
