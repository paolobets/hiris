"""Smoke tests for API handlers that previously had no dedicated test.

These cover happy-path 200 + the 503/404 fallback when dependencies are
missing, just enough to prevent silent regressions in v0.9.2.
"""
import json
import pytest
from unittest.mock import MagicMock
from aiohttp.test_utils import make_mocked_request


# ---------------------------------------------------------------------------
# handle_status -- fetta E4 Task 4 ("un bot solo"): test_handle_status_
# returns_version_and_agent_counts e' uscito insieme all'entita' Chatbot.
# handlers_status.py (il modulo che importava) e' cancellato per intero
# (Decisione 6 del brief: GET /api/status era gia' una rotta solo-test,
# il suo unico contenuto era un conteggio agents.total/agents.enabled che
# non significa piu' niente con un bot solo). Verificato che cadesse per
# costruzione: `ModuleNotFoundError: No module named
# 'hiris.app.api.handlers_status'`, prima della cancellazione.
# ---------------------------------------------------------------------------

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

# I cinque smoke test di handle_get_ha_health/handle_refresh_ha_health che
# vivevano qui sono cancellati dalla fetta E3 Task 11 ("esce il monitor di
# salute HA"): il modulo che importavano, `hiris.app.api.handlers_health`,
# e' cancellato per intero insieme all'HealthMonitor che serviva (il suo
# unico consumatore reale, `snapshot["ha_health"]`, era gia' caduto col
# Task 4). Erano un duplicato di `tests/test_handlers_health.py`, anch'esso
# cancellato nello stesso task. Verificato che cadano per costruzione:
# `ModuleNotFoundError: No module named 'hiris.app.api.handlers_health'`
# su tutti e cinque, prima della cancellazione.

# ---------------------------------------------------------------------------
# handle_run_chatbot (handlers_chatbots.py) e' uscito con l'intero Test Run
# (fetta E4 Task 2, 2.0): morto per costruzione (TypeError su ogni chiamata
# reale, difeso solo da un AsyncMock -- vedi task-2-report.md). I due smoke
# test che lo esercitavano cadevano per costruzione con `ImportError: cannot
# import name 'handle_run_chatbot'`, verificato prima della cancellazione.
# `handle_context_preview` e' uscito con la context map (fetta E3 Task 2, 2.0).
# ---------------------------------------------------------------------------
