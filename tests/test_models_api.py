import pytest

# Reuse the aiohttp test-app fixture/factory from test_api.py (creates the real
# app via create_app(), mocks HA + claude_runner, sets app["data_dir"] to a
# tmp_path). Importing the fixture makes pytest pick it up in this module too.
from tests.test_api import client  # noqa: F401


@pytest.mark.asyncio
async def test_get_models_config_defaults(client):
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()
    assert body["brain_model"] == "auto"
    assert "chain_order" in body


@pytest.mark.asyncio
async def test_put_models_config_persists_and_hot_updates(client):
    resp = await client.put("/api/models/config", json={"brain_model": "claude-opus-4-7"})
    assert resp.status == 200
    assert (await resp.json())["brain_model"] == "claude-opus-4-7"
    resp2 = await client.get("/api/models/config")
    assert (await resp2.json())["brain_model"] == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_put_models_config_malformed_chain_order_is_graceful(client):
    """A non-list chain_order (e.g. null or a number) must not 500 — it should
    be coerced to an empty list, matching save_models_config's guard."""
    resp = await client.put("/api/models/config", json={"chain_order": 5})
    assert resp.status == 200
    body = await resp.json()
    assert body["chain_order"] == []


@pytest.mark.asyncio
async def test_list_models_never_leaks_secrets(client):
    resp = await client.get("/api/models")
    assert resp.status == 200
    body = await resp.json()
    dumped = str(body)
    assert "sk-" not in dumped and "api_key" not in dumped


@pytest.mark.asyncio
async def test_list_models_reports_activation_state(client):
    resp = await client.get("/api/models")
    body = await resp.json()
    providers = body["providers"]
    assert providers, "expected at least the mocked claude provider"
    for entry in providers:
        assert "active" in entry
        assert "has_credential" in entry
        assert isinstance(entry["active"], bool)
        assert isinstance(entry["has_credential"], bool)
    claude_entry = next(p for p in providers if p["id"] == "anthropic")
    assert claude_entry["has_credential"] is True
