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
                       allowed_services=None, chatbot_id=None, cloud=True, **kw):
        self.calls.append((name, inputs, allowed_entities, allowed_services))
        # dispatcher.dispatch's kwarg is chatbot_id (Task 6 rename); this
        # attribute is named last_agent_id because in handlers_execute.py the
        # VALUE is a request-origin label ("mcp-gateway"/"unknown"), not a
        # Chatbot id -- kept for readability of the assertions below.
        self.last_agent_id = chatbot_id
        return {"ok": name}


def _make_app(policy, token="secret"):
    app = web.Application()
    app["internal_token"] = token
    app["execute_policy"] = policy
    # Denylist di lettura esplicitamente VUOTA: questi test riguardano la
    # allowlist d'azione e la routing dei tier, non il perimetro di lettura,
    # e la chiave assente varrebbe il default protettivo (fail-closed, vedi
    # handlers_execute._read_denylist). La denylist ha i suoi test in
    # tests/test_read_denylist.py.
    app["read_denylist"] = []
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
    app["gateway_settings"] = {"notify_service": "notify.mobile_app_test"}
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
    assert app["ha_client"].calls[0][1] == "mobile_app_test"


@pytest.mark.asyncio
async def test_execute_smuggled_off_target_entity_is_evaluated(aiohttp_client, tmp_path):
    # review A/#5 C1: the pre-screen must evaluate the UNION of data+target, so a
    # smuggled OFF `target` entity can't ride an approval evaluated only on `data`.
    app = _make_tier_app({"light": "green"}, tmp_path)
    app["execute_policy"]["entity_tiers"] = {"light.blocked": "off"}
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {
            "domain": "light", "service": "turn_on",
            "data": {"entity_id": "light.decoy"},
            "target": {"entity_id": "light.blocked"}}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    res = (await resp.json())["result"]
    assert "error" in res                                    # denied on the off target
    assert res.get("status") != "pending_approval"
    assert app["tool_dispatcher"].calls == []                # never executed


@pytest.mark.asyncio
async def test_execute_floor_id_group_target_fail_closed(aiohttp_client, tmp_path):
    # review A/#5 I2: floor_id is a group target -> fail-closed even alongside a
    # green entity_id (HA would actuate the whole floor).
    app = _make_tier_app({"light": "green"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {
            "domain": "light", "service": "turn_on",
            "data": {"entity_id": "light.ok", "floor_id": "notte"}}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    res = (await resp.json())["result"]
    assert "error" in res
    assert app["tool_dispatcher"].calls == []


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


# ---------------------------------------------------------------------------
# S-1 (falla di sicurezza, review indipendente su bee3ab1): questo
# prescreening decideva giallo/rosso leggendo SOLO effective_tier, senza mai
# consultare DANGEROUS_DOMAINS -- un dominio pericoloso configurato giallo
# produceva un pending giallo, quindi una notifica ACTIONABLE (bottoni
# Approva/Nega, nessun authenticationRequired -- valida anche a telefono
# bloccato) invece di passare da _require_human_auth. All'approvazione
# execute_pending salta l'intero _gate() (killer-feature step-up, per
# design), quindi il giallo bastava per aprire una serratura con un tocco.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_dangerous_domain_yellow_forces_red(aiohttp_client, tmp_path):
    """Un dominio pericoloso (lock) configurato GIALLO deve nascere ROSSO:
    stesso dominio in inputs['domain'] e nell'entita' target."""
    app = _make_tier_app({"lock": "yellow"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {
            "domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    res = (await resp.json())["result"]
    assert res["status"] == "pending_approval" and res["tier"] == "red", (
        "un dominio pericoloso a giallo deve nascere pending ROSSO, non giallo")
    assert app["tool_dispatcher"].calls == []                # held, not executed
    assert len(app["ha_client"].calls) == 1
    push = app["ha_client"].calls[0][2]["data"]
    assert "actions" not in push, (
        "il pending forzato a rosso non deve avere pulsanti Approva/Nega sulla notifica")


@pytest.mark.asyncio
async def test_execute_dangerous_target_entity_yellow_forces_red_even_if_service_domain_safe(
    aiohttp_client, tmp_path
):
    """Stesso esito quando il dominio PERICOLOSO e' solo quello di
    un'entita' target, non del servizio chiamato (es. homeassistant.turn_off
    su lock.front): la denylist deve coprire anche questo caso, non solo
    inputs['domain']."""
    app = _make_tier_app({"lock": "yellow"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {
            "domain": "homeassistant", "service": "turn_off",
            "data": {"entity_id": "lock.front"}}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    assert resp.status == 200
    res = (await resp.json())["result"]
    assert res["status"] == "pending_approval" and res["tier"] == "red", (
        "un'entita' target di dominio pericoloso deve forzare rosso anche se "
        "il dominio del servizio non e' nella denylist")
    push = app["ha_client"].calls[0][2]["data"]
    assert "actions" not in push


@pytest.mark.asyncio
async def test_execute_non_dangerous_domain_yellow_stays_yellow_and_actionable(aiohttp_client, tmp_path):
    """Controprova: la correzione S-1 non deve spegnere il percorso normale
    -- un dominio non pericoloso a giallo resta giallo e la notifica resta
    azionabile (bottoni Approva/Nega)."""
    app = _make_tier_app({"climate": "yellow"}, tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service", "input": {"domain": "climate", "service": "set_temperature"}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    res = (await resp.json())["result"]
    assert res["status"] == "pending_approval" and res["tier"] == "yellow"
    push = app["ha_client"].calls[0][2]["data"]
    assert "actions" in push, "un dominio innocuo a giallo deve restare azionabile dalla notifica"


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


# ---------------------------------------------------------------------------
# Per-entity override tests (TDD: added before implementation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_blocks_off_entity_in_green_domain(aiohttp_client):
    # switch domain green, but switch.gate overridden off -> must be blocked, NOT dispatched
    policy = {"tools": ["call_ha_service"], "allowed_entities": ["switch.*"],
              "allowed_services": ["switch.*"], "tiers": {"switch": "green"},
              "entity_tiers": {"switch.gate": "off"}}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "call_ha_service",
        "input": {"domain": "switch", "service": "turn_on",
                  "data": {"entity_id": "switch.gate"}}})
    assert resp.status == 200
    res = (await resp.json())["result"]
    assert "error" in res                                # blocked
    assert app["tool_dispatcher"].calls == []            # NEVER dispatched


@pytest.mark.asyncio
async def test_execute_red_entity_in_green_domain_held(aiohttp_client, tmp_path):
    # switch domain green, but switch.boiler overridden red -> must be held for approval
    app = _make_tier_app({"switch": "green"}, tmp_path)
    # Add entity_tiers to the existing policy
    app["execute_policy"]["entity_tiers"] = {"switch.boiler": "red"}
    app["execute_policy"]["allowed_entities"] = ["switch.*"]
    app["execute_policy"]["allowed_services"] = ["switch.*"]
    client = await aiohttp_client(app)
    resp = await client.post(
        "/api/execute",
        json={"tool": "call_ha_service",
              "input": {"domain": "switch", "service": "turn_on",
                        "data": {"entity_id": "switch.boiler"}}},
        headers={"X-HIRIS-Internal-Token": "secret"},
    )
    res = (await resp.json())["result"]
    assert res.get("status") == "pending_approval" and res["tier"] == "red"
    assert app["tool_dispatcher"].calls == []            # held, not executed


@pytest.mark.asyncio
async def test_execute_green_entity_dispatches(aiohttp_client):
    app = _make_app({"tools": ["call_ha_service"], "allowed_entities": ["switch.lamp"],
                     "allowed_services": ["switch.*"], "tiers": {}, "entity_tiers": {"switch.lamp": "green"}})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "call_ha_service",
        "input": {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.lamp"}}})
    assert resp.status == 200
    assert app["tool_dispatcher"].calls and app["tool_dispatcher"].calls[0][0] == "call_ha_service"


# ---------------------------------------------------------------------------
# create_task semaforo guard tests (TDD: added before implementation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_create_task_rejects_action_on_off_entity(aiohttp_client):
    policy = {"tools": ["create_task"], "allowed_entities": ["switch.*"],
              "allowed_services": ["switch.*"], "tiers": {"switch": "green"},
              "entity_tiers": {"switch.gate": "off"}}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_task", "input": {
        "label": "x", "trigger": {}, "actions": [
            {"type": "call_ha_service", "domain": "switch", "service": "turn_on",
             "data": {"entity_id": "switch.gate"}}]}})
    assert resp.status == 200
    res = (await resp.json())["result"]
    assert "error" in res
    assert app["tool_dispatcher"].calls == []          # never dispatched


@pytest.mark.asyncio
async def test_execute_create_task_rejects_red_entity_action(aiohttp_client):
    policy = {"tools": ["create_task"], "allowed_entities": ["switch.*"],
              "allowed_services": ["switch.*"], "tiers": {"switch": "green"},
              "entity_tiers": {"switch.boiler": "red"}}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_task", "input": {
        "label": "x", "trigger": {}, "actions": [
            {"type": "call_ha_service", "domain": "switch", "service": "turn_on",
             "data": {"entity_id": "switch.boiler"}}]}})
    assert "error" in (await resp.json())["result"]
    assert app["tool_dispatcher"].calls == []


@pytest.mark.asyncio
async def test_execute_create_task_allows_green_entity_action(aiohttp_client):
    policy = {"tools": ["create_task"], "allowed_entities": ["switch.*"],
              "allowed_services": ["switch.*"], "tiers": {"switch": "green"}, "entity_tiers": {}}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_task", "input": {
        "label": "x", "trigger": {}, "actions": [
            {"type": "call_ha_service", "domain": "switch", "service": "turn_on",
             "data": {"entity_id": "switch.lamp"}}]}})
    assert resp.status == 200
    assert app["tool_dispatcher"].calls and app["tool_dispatcher"].calls[0][0] == "create_task"


@pytest.mark.asyncio
async def test_execute_create_task_rejects_broadcast_action(aiohttp_client):
    policy = {"tools": ["create_task"], "allowed_entities": ["switch.*"],
              "allowed_services": ["switch.*"], "tiers": {"switch": "green"}, "entity_tiers": {}}
    app = _make_app(policy)
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "create_task", "input": {
        "label": "x", "trigger": {}, "actions": [
            {"type": "call_ha_service", "domain": "switch", "service": "turn_on"}]}})
    res = (await resp.json())["result"]
    assert "error" in res
    assert res.get("ok") is False          # observability: not mistakable for success
    assert app["tool_dispatcher"].calls == []


# ---------------------------------------------------------------------------
# send_notification always-exposed (notifiche "sempre permesse")
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_send_notification_exposed_without_policy(aiohttp_client):
    # Notifications are informational; send_notification is dispatchable even when
    # the saved EXECUTE_API_TOOLS policy is empty (fail-closed for everything else).
    app = _make_app({"tools": [], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "send_notification",
        "input": {"channel": "ha_persistent", "title": "Ciao", "message": "test"}})
    assert resp.status == 200
    assert app["tool_dispatcher"].calls and app["tool_dispatcher"].calls[0][0] == "send_notification"


@pytest.mark.asyncio
async def test_execute_other_tool_still_fail_closed_without_policy(aiohttp_client):
    # The always-exposed bypass must be limited to send_notification.
    app = _make_app({"tools": [], "allowed_entities": None, "allowed_services": None})
    client = await aiohttp_client(app)
    resp = await _post(client, {"tool": "call_ha_service", "input": {"domain": "light", "service": "turn_on"}})
    assert resp.status == 403
