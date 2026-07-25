"""Regression test for review finding #1 (self-approval): the HTTP
approve/reject endpoints (used by the HIRIS "Approvazioni" ingress page)
must require genuine Supervisor Ingress (a human in the HA UI) — the SAME
X-HIRIS-Internal-Token the MCP gateway already holds to CREATE pendings
must NOT be enough to APPROVE them, or a compromised/malicious gateway
could create a red-tier pending via /api/execute and immediately
self-approve it with zero human involvement.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from hiris.app.server import create_app
from hiris.app.agent_engine import AgentEngine
from hiris.app.chat_store import close_all_stores
from hiris.app.api.handlers_gateway_pending import create_pending, list_pending


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    async def dispatch(self, name, inputs, allowed_services=None, allowed_entities=None,
                       agent_id=None, cloud=True, **kw):
        self.calls.append((name, inputs, allowed_services))
        return {"ok": name}


def _make_app(tmp_path, token, cidrs=None):
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
    app["tool_dispatcher"] = _FakeDispatcher()
    # Default 172.30.32.0/23 does NOT include the test client's loopback IP, so
    # X-Ingress-Path alone must not bypass auth unless explicitly trusted here.
    app["supervisor_ingress_cidrs"] = cidrs or ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def client_with_token(aiohttp_client, tmp_path):
    app = _make_app(tmp_path, "secret-token-abc")
    client = await aiohttp_client(app)
    return client, app, tmp_path


@pytest_asyncio.fixture
async def client_trust_loopback(aiohttp_client, tmp_path):
    """Client whose trusted Supervisor CIDR includes the test loopback, so a
    genuine ingress request (header + trusted source IP) counts as human UI."""
    app = _make_app(tmp_path, "secret-token-abc", cidrs=["127.0.0.0/8", "::1/128"])
    client = await aiohttp_client(app)
    return client, app, tmp_path


def _entry(tmp_path, tier="red"):
    return create_pending(
        str(tmp_path), tool="call_ha_service",
        inputs={"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}},
        tier=tier, origin="mcp-gateway", label="lock.unlock",
    )


@pytest.mark.asyncio
async def test_approve_via_bare_internal_token_is_forbidden(client_with_token):
    """The gateway's own service token must NOT be able to self-approve a
    pending it just created — that defeats the entire step-up model."""
    client, app, tmp_path = client_with_token
    e = _entry(tmp_path)
    resp = await client.post(
        f"/api/gateway/pending/{e['id']}/approve",
        headers={"X-HIRIS-Internal-Token": "secret-token-abc"},
    )
    assert resp.status == 403
    data = await resp.json()
    assert "forbidden" in data["error"].lower()
    # Not approved, not executed.
    assert app["tool_dispatcher"].calls == []
    pend = list_pending(str(tmp_path))
    assert len(pend) == 1 and pend[0]["id"] == e["id"]


@pytest.mark.asyncio
async def test_reject_via_bare_internal_token_is_forbidden(client_with_token):
    client, app, tmp_path = client_with_token
    e = _entry(tmp_path)
    resp = await client.post(
        f"/api/gateway/pending/{e['id']}/reject",
        headers={"X-HIRIS-Internal-Token": "secret-token-abc"},
    )
    assert resp.status == 403
    data = await resp.json()
    assert "forbidden" in data["error"].lower()
    pend = list_pending(str(tmp_path))
    assert len(pend) == 1 and pend[0]["id"] == e["id"]


@pytest.mark.asyncio
async def test_approve_via_genuine_ingress_works(client_trust_loopback):
    """A human opening the HIRIS 'Approvazioni' page under Supervisor Ingress
    (valid X-Ingress-Path AND source IP in a trusted Supervisor CIDR) must
    still be able to approve — this is the legitimate red-tier path."""
    client, app, tmp_path = client_trust_loopback
    e = _entry(tmp_path)
    resp = await client.post(
        f"/api/gateway/pending/{e['id']}/approve",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert len(app["tool_dispatcher"].calls) == 1
    assert list_pending(str(tmp_path)) == []


@pytest.mark.asyncio
async def test_reject_via_genuine_ingress_works(client_trust_loopback):
    client, app, tmp_path = client_trust_loopback
    e = _entry(tmp_path)
    resp = await client.post(
        f"/api/gateway/pending/{e['id']}/reject",
        headers={"X-Ingress-Path": "/api/hassio_ingress/hiris"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert app["tool_dispatcher"].calls == []
    assert list_pending(str(tmp_path)) == []


@pytest.mark.asyncio
async def test_approve_via_forged_ingress_from_untrusted_ip_still_forbidden(client_with_token):
    """CR-1 interplay: X-Ingress-Path from a non-Supervisor source IP is not
    genuine ingress, so it falls through to the token branch — and even with
    the correct token attached, approval must still be forbidden."""
    client, app, tmp_path = client_with_token
    e = _entry(tmp_path)
    resp = await client.post(
        f"/api/gateway/pending/{e['id']}/approve",
        headers={
            "X-Ingress-Path": "/api/hassio_ingress/forged",
            "X-HIRIS-Internal-Token": "secret-token-abc",
        },
    )
    assert resp.status == 403
    assert app["tool_dispatcher"].calls == []
