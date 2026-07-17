import pytest
from aiohttp import web
from unittest.mock import AsyncMock

from hiris.app.api.handlers_execute import handle_execute
from hiris.app.api.handlers_gateway_policy import PROPOSE_TOOLS


class _FakeDispatcher:
    def __init__(self):
        self.calls = []
    async def dispatch(self, name, inputs, **kw):
        self.calls.append(name)
        return {"ok": name}


def _make_app(store):
    app = web.Application()
    app["internal_token"] = "secret"
    app["execute_policy"] = {"tools": ["create_ha_config"], "allowed_entities": None,
                             "allowed_services": None, "tiers": {}, "entity_tiers": {}}
    app["tool_dispatcher"] = _FakeDispatcher()
    app["proposal_store"] = store
    app.router.add_post("/api/execute", handle_execute)
    return app


async def _post(client, body):
    return await client.post("/api/execute", json=body,
                             headers={"X-HIRIS-Internal-Token": "secret"})


def test_create_ha_config_in_propose_tools():
    assert "create_ha_config" in PROPOSE_TOOLS


@pytest.mark.asyncio
async def test_mcp_create_ha_config_is_pending_not_dispatched(aiohttp_client):
    store = AsyncMock()
    store.save = AsyncMock(return_value="prop-123")
    app = _make_app(store)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_ha_config", "input": {
        "kind": "script", "name": "Luci sera", "slug": "luci_sera",
        "config": {"sequence": []},
    }})
    assert resp.status == 200
    data = await resp.json()
    assert data["result"]["status"] == "pending_approval"
    assert data["result"]["proposal_id"] == "prop-123"
    store.save.assert_awaited_once()
    # crucially NOT dispatched (would be a direct write):
    assert app["tool_dispatcher"].calls == []


@pytest.mark.asyncio
async def test_mcp_create_ha_config_bad_input(aiohttp_client):
    store = AsyncMock()
    store.save = AsyncMock(return_value="x")
    app = _make_app(store)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_ha_config", "input": {
        "kind": "nope", "name": "x", "slug": "x", "config": {"a": 1},
    }})
    data = await resp.json()
    assert data["result"]["ok"] is False
    store.save.assert_not_awaited()
