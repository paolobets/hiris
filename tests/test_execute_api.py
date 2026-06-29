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
                       allowed_services=None, agent_id=None, cloud=True, **kw):
        self.calls.append((name, inputs, allowed_entities, allowed_services))
        self.last_agent_id = agent_id
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
async def test_execute_action_passes_whitelists(aiohttp_client):
    # Action tools MUST receive the entity/service whitelist (that is the
    # gateway's action safety boundary).
    policy = {"tools": ["call_ha_service"], "allowed_entities": ["light.*"],
              "allowed_services": ["light.*"]}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "call_ha_service",
                                "input": {"domain": "light", "service": "turn_on"}})
    assert resp.status == 200
    name, inputs, ents, svcs = app["tool_dispatcher"].calls[0]
    assert name == "call_ha_service"
    assert ents == ["light.*"]
    assert svcs == ["light.*"]


@pytest.mark.asyncio
async def test_execute_read_bypasses_action_whitelist(aiohttp_client):
    # Reads are non-destructive: the action whitelist (derived from the green
    # action domains) must NOT restrict what a read can see — otherwise asking
    # for sensor temperatures returns empty as soon as any category is green.
    policy = {"tools": ["get_home_status", "get_entity_states"],
              "allowed_entities": ["light.*"], "allowed_services": ["light.*"]}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {"a": 1}})
    assert resp.status == 200
    assert (await resp.json())["result"] == {"ok": "get_home_status"}
    name, inputs, ents, svcs = app["tool_dispatcher"].calls[0]
    assert name == "get_home_status"
    assert inputs == {"a": 1}
    assert ents is None          # read sees everything, not just green domains
    assert svcs is None


@pytest.mark.asyncio
async def test_execute_rejects_when_token_unset(aiohttp_client):
    # Empty internal_token must fail closed, never match an empty client token.
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None}, token="")
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}}, token="")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_execute_passes_origin_as_agent_id(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    await client.post("/api/execute",
                      json={"tool": "get_home_status", "input": {}, "origin": "mcp-gateway"},
                      headers={"X-HIRIS-Internal-Token": "secret"})
    assert app["tool_dispatcher"].last_agent_id == "mcp-gateway"


@pytest.mark.asyncio
async def test_execute_sanitizes_bad_origin(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    await client.post("/api/execute",
                      json={"tool": "get_home_status", "input": {}, "origin": "evil <script>"},
                      headers={"X-HIRIS-Internal-Token": "secret"})
    assert app["tool_dispatcher"].last_agent_id == "mcp-gateway"   # invalid -> default


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return True


def _make_tier_app(tiers, tmp_path):
    app = web.Application()
    app["internal_token"] = "secret"
    app["execute_policy"] = {"tools": ["call_ha_service"], "allowed_services": ["light.*"],
                             "allowed_entities": ["light.*"], "tiers": tiers}
    app["tool_dispatcher"] = _FakeDispatcher()
    app["data_dir"] = str(tmp_path)
    app["ha_client"] = _FakeHA()
    app["gateway_notify_service"] = "notify.iphone_bet"
    app.router.add_post("/api/execute", handle_execute)
    return app


@pytest.mark.asyncio
async def test_execute_yellow_action_held_and_notified(aiohttp_client, tmp_path):
    app = _make_tier_app({"climate": "yellow"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {"domain": "climate", "service": "set_temperature"}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    res = (await resp.json())["result"]
    assert res["status"] == "pending_approval" and res["tier"] == "yellow"
    assert app["tool_dispatcher"].calls == []                # held, not executed
    assert len(app["ha_client"].calls) == 1                  # actionable notification sent
    assert app["ha_client"].calls[0][1] == "iphone_bet"


@pytest.mark.asyncio
async def test_execute_green_action_dispatches_directly(aiohttp_client, tmp_path):
    app = _make_tier_app({"light": "green"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {"domain": "light", "service": "turn_on"}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    assert app["tool_dispatcher"].calls                      # executed directly
    assert app["ha_client"].calls == []                      # no notification


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


@pytest.mark.asyncio
async def test_execute_get_history_bypasses_action_whitelist(aiohttp_client):
    policy = {"tools": ["get_history"], "allowed_entities": ["light.*"],
              "allowed_services": ["light.*"]}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_history",
                                "input": {"entity_ids": ["sensor.temp"], "days": 3}})
    assert resp.status == 200
    name, inputs, ents, svcs = app["tool_dispatcher"].calls[0]
    assert name == "get_history"
    assert ents is None and svcs is None     # read sees everything


@pytest.mark.asyncio
async def test_execute_hard_rejects_tool_outside_server_allowlist(aiohttp_client):
    # Even if the policy lists it, http_request must never be dispatchable.
    app = _make_app({"tools": ["http_request"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "http_request", "input": {"url": "http://x"}})
    assert resp.status == 403
    assert "not permitted" in (await resp.json())["error"]


@pytest.mark.asyncio
async def test_execute_hard_allows_known_read_tool(aiohttp_client):
    app = _make_app({"tools": ["get_home_status"], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "get_home_status", "input": {}})
    assert resp.status == 200
