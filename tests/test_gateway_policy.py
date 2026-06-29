import pytest
from aiohttp import web

from hiris.app.api.handlers_gateway_policy import (
    GATEWAY_CATEGORIES,
    READ_TOOLS,
    PROPOSE_TOOLS,
    apply_saved_policy,
    derive_execute_policy,
    handle_get_gateway_policy,
    handle_save_gateway_policy,
    load_categories,
    save_categories,
)


def test_derive_empty_is_read_only():
    pol = derive_execute_policy({})
    assert "get_home_status" in pol["tools"]
    assert "call_ha_service" not in pol["tools"]
    assert pol["allowed_services"] is None
    assert pol["allowed_entities"] is None


def test_derive_green_light_adds_call_service_and_glob():
    pol = derive_execute_policy({"light": "green"})
    assert "call_ha_service" in pol["tools"]
    assert pol["allowed_services"] == ["light.*"]
    assert pol["allowed_entities"] == ["light.*"]


def test_derive_yellow_red_requestable_but_held():
    pol = derive_execute_policy({"lock": "red", "climate": "yellow"})
    # requestable (the handler routes them to approval)...
    assert "call_ha_service" in pol["tools"]
    # ...but NOT directly executable (not in the green whitelist)
    assert pol["allowed_services"] is None
    # the tiers map drives the routing
    assert pol["tiers"] == {"lock": "red", "climate": "yellow"}


def test_derive_mixed_tiers():
    pol = derive_execute_policy({"light": "green", "climate": "yellow", "lock": "red", "fan": "off"})
    assert pol["allowed_services"] == ["light.*"]          # only green is whitelisted
    assert pol["tiers"] == {"light": "green", "climate": "yellow", "lock": "red"}


def test_save_load_roundtrip_and_validation(tmp_path):
    save_categories(str(tmp_path), {"light": "green", "bogus": "green", "lock": "weird"})
    cats = load_categories(str(tmp_path))
    assert cats == {"light": "green"}      # invalid id and invalid level dropped


def test_load_missing_is_empty(tmp_path):
    assert load_categories(str(tmp_path)) == {}


def test_apply_saved_policy_overrides(tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["execute_policy"] = {"tools": [], "allowed_entities": None, "allowed_services": None}
    save_categories(str(tmp_path), {"scene": "green"})
    apply_saved_policy(app)
    assert "call_ha_service" in app["execute_policy"]["tools"]
    assert app["execute_policy"]["allowed_services"] == ["scene.*"]


def _app(tmp_path):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["execute_policy"] = {"tools": [], "allowed_entities": None, "allowed_services": None}
    app.router.add_get("/api/gateway/policy", handle_get_gateway_policy)
    app.router.add_post("/api/gateway/policy", handle_save_gateway_policy)
    return app


@pytest.mark.asyncio
async def test_get_returns_categories(aiohttp_client, tmp_path):
    client = await aiohttp_client(_app(tmp_path))
    resp = await client.get("/api/gateway/policy")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["categories"]) == len(GATEWAY_CATEGORIES)
    assert data["levels"] == {}


@pytest.mark.asyncio
async def test_post_saves_and_updates_execute_policy(aiohttp_client, tmp_path):
    app = _app(tmp_path)
    client = await aiohttp_client(app)
    resp = await client.post("/api/gateway/policy", json={"levels": {"light": "green"}})
    assert resp.status == 200
    data = await resp.json()
    assert data["levels"] == {"light": "green"}
    assert "call_ha_service" in data["execute_policy"]["tools"]
    # persisted: a fresh GET reflects it
    resp2 = await client.get("/api/gateway/policy")
    assert (await resp2.json())["levels"] == {"light": "green"}


def test_get_history_is_a_read_tool():
    assert "get_history" in READ_TOOLS


def test_derived_policy_exposes_get_history():
    pol = derive_execute_policy({"light": "green"})
    assert "get_history" in pol["tools"]


def test_get_automation_config_is_read_tool():
    assert "get_automation_config" in READ_TOOLS


def test_propose_tools_always_in_derived_policy():
    pol = derive_execute_policy({})          # no categories at all
    for t in ("create_automation_proposal", "save_knowledge", "list_tasks", "cancel_task"):
        assert t in pol["tools"]
    assert "call_ha_service" not in pol["tools"]   # not actionable -> no action tool
    assert "create_task" not in pol["tools"]       # create_task needs a green domain to constrain it


def test_create_task_exposed_only_when_actionable():
    assert "create_task" not in derive_execute_policy({})["tools"]
    assert "create_task" not in derive_execute_policy({"light": "off"})["tools"]
    pol = derive_execute_policy({"light": "green"})
    assert "create_task" in pol["tools"]
    assert pol["allowed_services"] == ["light.*"]   # so the task's actions are constrained


def test_green_category_still_adds_call_service():
    pol = derive_execute_policy({"light": "green"})
    assert "call_ha_service" in pol["tools"]
    assert "create_automation_proposal" in pol["tools"]
