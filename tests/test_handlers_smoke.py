"""Smoke tests for API handlers that previously had no dedicated test.

These cover happy-path 200 + the 503/404 fallback when dependencies are
missing, just enough to prevent silent regressions in v0.9.2.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import make_mocked_request


# ---------------------------------------------------------------------------
# handle_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_status_returns_version_and_agent_counts():
    from hiris.app.api.handlers_status import handle_status
    engine = MagicMock()
    engine.list_chatbots.return_value = {
        "a1": {"enabled": True},
        "a2": {"enabled": False},
        "a3": {"enabled": True},
    }
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: engine if k == "engine" else None)
    request = make_mocked_request("GET", "/api/status", app=app)
    resp = await handle_status(request)
    data = json.loads(resp.body)
    assert "version" in data
    assert data["agents"]["total"] == 3
    assert data["agents"]["enabled"] == 2


# ---------------------------------------------------------------------------
# handle_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_config_returns_theme():
    from hiris.app.api.handlers_config import handle_config
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: "dark" if k == "theme" else d)
    request = make_mocked_request("GET", "/api/config", app=app)
    resp = await handle_config(request)
    assert json.loads(resp.body) == {"theme": "dark"}


@pytest.mark.asyncio
async def test_handle_config_default_theme_is_auto():
    from hiris.app.api.handlers_config import handle_config
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: d)  # no theme key
    request = make_mocked_request("GET", "/api/config", app=app)
    resp = await handle_config(request)
    assert json.loads(resp.body) == {"theme": "auto"}


# I quattro smoke test di handle_get_task/handle_cancel_task che vivevano
# qui sono cancellati dalla fetta E3 Task 9 ("esce il Task Engine"): il
# modulo che importavano, `hiris.app.api.handlers_tasks`, e' cancellato per
# intero insieme alle tre rotte /api/tasks* che serviva. Verificato che
# cadono per costruzione: `ModuleNotFoundError: No module named
# 'hiris.app.api.handlers_tasks'` su tutti e quattro, prima della
# cancellazione.

# ---------------------------------------------------------------------------
# handle_get_ha_health / handle_refresh_ha_health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_get_ha_health_no_monitor_returns_503():
    from hiris.app.api.handlers_health import handle_get_ha_health
    app = MagicMock()
    app.get = MagicMock(return_value=None)
    request = make_mocked_request("GET", "/api/health/ha", app=app)
    resp = await handle_get_ha_health(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_handle_get_ha_health_returns_snapshot():
    from hiris.app.api.handlers_health import handle_get_ha_health
    monitor = MagicMock()
    monitor.get_snapshot.return_value = {"unavailable": []}
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: monitor if k == "health_monitor" else d)
    request = make_mocked_request("GET", "/api/health/ha", app=app)
    resp = await handle_get_ha_health(request)
    assert resp.status == 200
    monitor.get_snapshot.assert_called_once_with(["all"], capped=False)


@pytest.mark.asyncio
async def test_handle_get_ha_health_filters_sections_param():
    from hiris.app.api.handlers_health import handle_get_ha_health
    monitor = MagicMock()
    monitor.get_snapshot.return_value = {}
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: monitor if k == "health_monitor" else d)
    request = make_mocked_request(
        "GET", "/api/health/ha?sections=unavailable,integrations", app=app
    )
    await handle_get_ha_health(request)
    monitor.get_snapshot.assert_called_once_with(["unavailable", "integrations"], capped=False)


@pytest.mark.asyncio
async def test_handle_refresh_ha_health_no_monitor_returns_503():
    from hiris.app.api.handlers_health import handle_refresh_ha_health
    app = MagicMock()
    app.get = MagicMock(return_value=None)
    request = make_mocked_request("POST", "/api/health/ha/refresh", app=app)
    resp = await handle_refresh_ha_health(request)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_handle_refresh_ha_health_calls_refresh():
    from hiris.app.api.handlers_health import handle_refresh_ha_health
    monitor = MagicMock()
    monitor.refresh = AsyncMock()
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, d=None: monitor if k == "health_monitor" else d)
    request = make_mocked_request("POST", "/api/health/ha/refresh", app=app)
    resp = await handle_refresh_ha_health(request)
    assert resp.status == 200
    monitor.refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# handle_run_chatbot (handlers_chatbots.py) -- handle_context_preview e'
# uscito con la context map (fetta E3 Task 2, 2.0).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_run_agent_unknown_returns_404():
    from hiris.app.api.handlers_chatbots import handle_run_chatbot
    engine = MagicMock()
    engine.get_chatbot.return_value = None
    app = MagicMock()
    app.__getitem__ = MagicMock(side_effect=lambda k: engine if k == "engine" else None)
    aid = "550e8400-e29b-41d4-a716-446655440000"
    request = make_mocked_request(
        "POST", f"/api/chatbots/{aid}/run",
        match_info={"agent_id": aid},
        app=app,
    )
    resp = await handle_run_chatbot(request)
    assert resp.status == 404


@pytest.mark.asyncio
async def test_handle_run_agent_invalid_id_returns_400():
    from hiris.app.api.handlers_chatbots import handle_run_chatbot
    app = MagicMock()
    request = make_mocked_request(
        "POST", "/api/chatbots/bad<script>id/run",
        match_info={"agent_id": "bad<script>id"},
        app=app,
    )
    resp = await handle_run_chatbot(request)
    assert resp.status == 400
