import pytest
from aiohttp import web

from hiris.app.api.handlers_gateway_policy import (
    GATEWAY_CATEGORIES,
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


def test_derive_yellow_red_not_executable_in_v1():
    pol = derive_execute_policy({"lock": "red", "climate": "yellow"})
    assert "call_ha_service" not in pol["tools"]
    assert pol["allowed_services"] is None


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
