import pytest
from aiohttp import web

from hiris.app.api.handlers_execute import handle_execute, parse_execute_policy


def test_parse_execute_policy_defaults():
    pol = parse_execute_policy(tools="", entities="", services="")
    assert pol["tools"] == []          # empty => nothing exposed (fail-closed)
    assert pol["allowed_entities"] is None
    assert pol["allowed_services"] is None


def test_parse_execute_policy_csv():
    pol = parse_execute_policy(
        tools="get_home_status, get_entity_states ,create_task",
        entities="light.*, switch.garden",
        services="light.*",
    )
    assert pol["tools"] == ["get_home_status", "get_entity_states", "create_task"]
    assert pol["allowed_entities"] == ["light.*", "switch.garden"]
    assert pol["allowed_services"] == ["light.*"]


class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, name, inputs, allowed_entities=None,
                       allowed_services=None, cloud=True, **kw):
        self.calls.append((name, inputs, allowed_entities, allowed_services))
        return {"ok": name}


def _make_app(policy, token="secret"):
    app = web.Application()
    app["internal_token"] = token
    app["execute_policy"] = policy
    app["tool_dispatcher"] = _FakeDispatcher()
    app.router.add_post("/api/execute", handle_execute)
    return app


async def _post(client, body, token="secret"):
    headers = {"X-HIRIS-Internal-Token": token} if token is not None else {}
    return await client.post("/api/execute", json=body, headers=headers)


@pytest.mark.asyncio
async def test_execute_rejects_missing_token(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}}, token=None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_execute_rejects_wrong_token(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}}, token="nope")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_execute_rejects_tool_not_in_allowlist(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "call_ha_service", "input": {}})
    assert resp.status == 403
    assert "not exposed" in (await resp.json())["error"]


@pytest.mark.asyncio
async def test_execute_dispatches_and_passes_whitelists(aiohttp_client):
    policy = {"tools": ["get_home_status"], "allowed_entities": ["light.*"], "allowed_services": ["light.*"]}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {"a": 1}})
    assert resp.status == 200
    assert (await resp.json())["result"] == {"ok": "get_home_status"}
    name, inputs, ents, svcs = app["tool_dispatcher"].calls[0]
    assert name == "get_home_status"
    assert inputs == {"a": 1}
    assert ents == ["light.*"]
    assert svcs == ["light.*"]


@pytest.mark.asyncio
async def test_execute_rejects_when_token_unset(aiohttp_client):
    # Empty internal_token must fail closed, never match an empty client token.
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None}, token="")
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}}, token="")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_execute_rejects_invalid_json(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await client.post("/api/execute", data="not json",
                             headers={"X-HIRIS-Internal-Token": "secret"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_execute_rejects_non_object_input(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": [1, 2]})
    assert resp.status == 400
