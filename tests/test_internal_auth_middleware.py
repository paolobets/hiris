import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


def _make_app(tmp_path, token):
    app = create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    engine = AgentEngine(ha_client=mock_ha, data_path=str(tmp_path / "agents.json"))
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    app["ha_client"] = mock_ha
    app["engine"] = engine
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["data_dir"] = str(tmp_path)
    app["internal_token"] = token
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def client_no_token(aiohttp_client, tmp_path):
    return await aiohttp_client(_make_app(tmp_path, ""))


@pytest_asyncio.fixture
async def client_with_token(aiohttp_client, tmp_path):
    return await aiohttp_client(_make_app(tmp_path, "secret-token-abc"))


@pytest.mark.asyncio
async def test_no_secret_configured_all_requests_pass(client_no_token):
    """When internal_token is empty, all requests pass regardless of headers."""
    resp = await client_no_token.get("/api/health")
    assert resp.status == 200


@pytest.mark.asyncio
async def test_valid_token_accepted(client_with_token):
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-HIRIS-Internal-Token": "secret-token-abc"},
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_wrong_token_rejected(client_with_token):
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-HIRIS-Internal-Token": "wrong-token"},
    )
    assert resp.status == 401
    data = await resp.json()
    assert data["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_missing_token_rejected(client_with_token):
    resp = await client_with_token.get("/api/health")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_header_bypasses_auth(client_with_token):
    """Requests with valid HA Supervisor X-Ingress-Path bypass token check."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"},
    )
    assert resp.status == 200


# ---------------------------------------------------------------------------
# SEC-023 — X-Ingress-Path must match Supervisor pattern, not any non-empty value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingress_path_empty_string_does_not_bypass(client_with_token):
    """An empty X-Ingress-Path must not bypass auth."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-Ingress-Path": ""},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_arbitrary_value_does_not_bypass(client_with_token):
    """X-Ingress-Path with arbitrary value (not Supervisor format) must not bypass."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-Ingress-Path": "/foo/bar"},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_ingress_path_real_supervisor_token_pattern_passes(client_with_token):
    """Real Supervisor format /api/hassio_ingress/<random-token>/ passes."""
    resp = await client_with_token.get(
        "/api/health",
        headers={"X-Ingress-Path": "/api/hassio_ingress/AbCdEf123-XyZ_456/"},
    )
    assert resp.status == 200
