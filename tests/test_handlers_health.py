import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import make_mocked_request
from hiris.app.api.handlers_health import handle_get_ha_health, handle_refresh_ha_health


def _make_app(health_monitor=None):
    app = MagicMock()
    app.get = MagicMock(side_effect=lambda k, *a: health_monitor if k == "health_monitor" else None)
    return app


@pytest.mark.asyncio
async def test_get_ha_health_returns_snapshot():
    snapshot = {"system": {"version": "2024.1"}, "unavailable": []}
    monitor = MagicMock()
    monitor.get_snapshot = MagicMock(return_value=snapshot)

    request = make_mocked_request("GET", "/api/health/ha", app=_make_app(monitor))
    resp = await handle_get_ha_health(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == snapshot
    monitor.get_snapshot.assert_called_once_with(["all"])


@pytest.mark.asyncio
async def test_get_ha_health_no_monitor_returns_503():
    request = make_mocked_request("GET", "/api/health/ha", app=_make_app(None))
    resp = await handle_get_ha_health(request)

    assert resp.status == 503
    data = json.loads(resp.body)
    assert "error" in data


@pytest.mark.asyncio
async def test_refresh_ha_health_returns_ok():
    monitor = MagicMock()
    monitor.refresh = AsyncMock()

    request = make_mocked_request("POST", "/api/health/ha/refresh", app=_make_app(monitor))
    resp = await handle_refresh_ha_health(request)

    assert resp.status == 200
    data = json.loads(resp.body)
    assert data == {"ok": True}
    monitor.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_no_monitor_returns_503():
    request = make_mocked_request("POST", "/api/health/ha/refresh", app=_make_app(None))
    resp = await handle_refresh_ha_health(request)

    assert resp.status == 503
    data = json.loads(resp.body)
    assert "error" in data
