import json

import pytest

# Reuse the aiohttp test-app fixture/factory from test_api.py (creates the real
# app via create_app(), mocks HA + claude_runner, sets app["data_dir"] to a
# tmp_path). Importing the fixture makes pytest pick it up in this module too.
from tests.test_api import client  # noqa: F401

_CONFIG_PROVIDER_IDS = ("subscription", "claude", "openai", "openrouter", "ollama")


@pytest.mark.asyncio
async def test_get_models_config_defaults(client):
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()
    assert body["brain_model"] == "auto"
    assert "chain_order" in body


@pytest.mark.asyncio
async def test_get_models_config_enriched_providers(client):
    """SP-2 T7B: the config endpoint must list ALL five providers (incl.
    subscription and any uncredentialed one), each with active/has_credential
    booleans, so the #/models UI can render them honestly."""
    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()

    providers = body["providers"]
    assert [p["id"] for p in providers] == list(_CONFIG_PROVIDER_IDS)
    for entry in providers:
        assert set(entry.keys()) == {"id", "label", "active", "has_credential"}
        assert isinstance(entry["label"], str) and entry["label"]
        assert isinstance(entry["active"], bool)
        assert isinstance(entry["has_credential"], bool)

    # The test client fixture wires app["claude_runner"] to a mock — so the
    # "claude" provider must report a credential even without CLAUDE_API_KEY.
    claude_entry = next(p for p in providers if p["id"] == "claude")
    assert claude_entry["has_credential"] is True

    # No app["active_providers"]/openai_api_key/etc. are wired in the test
    # fixture (on_startup is cleared) — the other providers must report False
    # rather than raising or defaulting to True.
    for pid in ("subscription", "openai", "openrouter", "ollama"):
        entry = next(p for p in providers if p["id"] == pid)
        assert entry["has_credential"] is False


@pytest.mark.asyncio
async def test_get_models_config_enriched_fields(client, monkeypatch):
    monkeypatch.setenv("LLM_STRATEGY", "cheap")
    monkeypatch.setenv("MEMORY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("MEMORY_EMBEDDING_MODEL", "text-embedding-3-small")
    client.app["local_model_name"] = "llama3.1:8b"

    resp = await client.get("/api/models/config")
    body = await resp.json()

    assert body["llm_strategy"] == "cheap"
    assert body["embeddings"] == {
        "provider": "openai",
        "model": "text-embedding-3-small",
    }
    assert body["ollama_model"] == "llama3.1:8b"


@pytest.mark.asyncio
async def test_get_models_config_never_leaks_secrets(client, monkeypatch):
    """Boolean has_credential only — the actual secret VALUE must never
    appear anywhere in the /api/models/config JSON payload."""
    fake_oauth_token = "sk-ant-oat01-super-secret-token-value"
    fake_claude_key = "sk-ant-api03-another-secret-value"
    fake_openai_key = "sk-openai-fake-secret-value"
    fake_openrouter_key = "sk-or-fake-secret-value"

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", fake_oauth_token)
    monkeypatch.setenv("CLAUDE_API_KEY", fake_claude_key)
    client.app["openai_api_key"] = fake_openai_key
    client.app["openrouter_api_key"] = fake_openrouter_key
    client.app["active_providers"] = {
        "subscription": True,
        "claude": True,
        "openai": True,
        "openrouter": True,
        "ollama": False,
    }

    resp = await client.get("/api/models/config")
    assert resp.status == 200
    body = await resp.json()
    dumped = json.dumps(body)

    for secret in (fake_oauth_token, fake_claude_key, fake_openai_key, fake_openrouter_key):
        assert secret not in dumped
    assert "sk-" not in dumped
    assert "api_key" not in dumped
    assert "token" not in dumped.lower()

    # Credentials ARE reflected as booleans, just never as values.
    providers_by_id = {p["id"]: p for p in body["providers"]}
    assert providers_by_id["subscription"]["has_credential"] is True
    assert providers_by_id["claude"]["has_credential"] is True
    assert providers_by_id["openai"]["has_credential"] is True
    assert providers_by_id["openrouter"]["has_credential"] is True


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
