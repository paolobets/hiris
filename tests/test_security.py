"""
Security regression tests — run on every PR.

These tests validate that the security fixes applied post-audit hold and
do not regress. They are deliberately narrow (fast, no real network calls).
"""
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_with_runner(runner):
    """Minimal aiohttp app wired like the real server but without startup hooks."""
    from hiris.app.api.handlers_chat import handle_chat
    from hiris.app.api.handlers_agents import (
        handle_get_agent, handle_update_agent, handle_delete_agent,
        handle_run_agent, handle_get_agent_usage, handle_reset_agent_usage,
    )
    from hiris.app.server import _security_headers

    agent = MagicMock()
    agent.id = "test-agent"
    agent.is_default = False
    agent.system_prompt = "test"
    agent.strategic_context = ""
    agent.allowed_tools = None
    agent.allowed_entities = None
    agent.allowed_services = None
    agent.model = "auto"
    agent.max_tokens = 4096
    agent.type = "chat"
    agent.restrict_to_home = False
    agent.require_confirmation = False
    agent.max_chat_turns = 0

    engine = MagicMock()
    engine.get_agent.return_value = agent
    engine.get_default_agent.return_value = agent

    app = web.Application(middlewares=[_security_headers])
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["engine"] = engine
    app["data_dir"] = "/tmp"

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/agents/{agent_id}", handle_get_agent)
    app.router.add_put("/api/agents/{agent_id}", handle_update_agent)
    app.router.add_delete("/api/agents/{agent_id}", handle_delete_agent)
    app.router.add_post("/api/agents/{agent_id}/run", handle_run_agent)
    app.router.add_get("/api/agents/{agent_id}/usage", handle_get_agent_usage)
    app.router.add_post("/api/agents/{agent_id}/usage/reset", handle_reset_agent_usage)
    return app


# ---------------------------------------------------------------------------
# SEC-007 — Message length cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_rejects_message_over_4000_chars():
    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "x" * 4001})
        assert resp.status == 413
        data = await resp.json()
        assert "too long" in data["error"]


@pytest.mark.asyncio
async def test_chat_accepts_message_at_4000_chars():
    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    app = _make_app_with_runner(runner)
    with patch("hiris.app.api.handlers_chat.load_history", return_value=[]):
        with patch("hiris.app.api.handlers_chat.append_messages"):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/chat", json={"message": "x" * 4000})
                assert resp.status == 200


# ---------------------------------------------------------------------------
# SEC-014 — agent_id validation in URL path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_path_rejects_path_traversal():
    runner = AsyncMock()
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/../../etc/passwd")
        # aiohttp URL routing won't match, but validate it doesn't 200 OK
        assert resp.status in (400, 404)


@pytest.mark.asyncio
async def test_agent_get_rejects_invalid_id_characters():
    runner = AsyncMock()
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/bad<script>id")
        assert resp.status in (400, 404)


@pytest.mark.asyncio
async def test_agent_get_accepts_valid_uuid():
    runner = AsyncMock()
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/agents/550e8400-e29b-41d4-a716-446655440000")
        # 404 because engine mock returns agent but asdict() might fail; the key
        # check is that we don't get 400 (validation reject)
        assert resp.status != 400


# ---------------------------------------------------------------------------
# SEC-016 — Security headers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_present():
    runner = AsyncMock()
    runner.chat = AsyncMock(return_value="ok")
    runner.last_tool_calls = []
    app = _make_app_with_runner(runner)
    with patch("hiris.app.api.handlers_chat.load_history", return_value=[]):
        with patch("hiris.app.api.handlers_chat.append_messages"):
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/chat", json={"message": "ciao"})
                assert resp.headers.get("X-Content-Type-Options") == "nosniff"
                assert resp.headers.get("X-Frame-Options") == "DENY"
                assert resp.headers.get("Referrer-Policy") == "no-referrer"


# ---------------------------------------------------------------------------
# SEC-010 — domain/service regex in ha_client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ha_client_rejects_invalid_domain():
    from hiris.app.proxy.ha_client import HAClient
    client = HAClient("http://supervisor/core", "token")
    client._session = MagicMock()
    result = await client.call_service("../evil", "turn_on", {})
    assert result is False


@pytest.mark.asyncio
async def test_ha_client_rejects_invalid_service():
    from hiris.app.proxy.ha_client import HAClient
    client = HAClient("http://supervisor/core", "token")
    client._session = MagicMock()
    result = await client.call_service("light", "turn_on; rm -rf /", {})
    assert result is False


@pytest.mark.asyncio
async def test_ha_client_accepts_valid_service():
    from hiris.app.proxy.ha_client import HAClient
    client = HAClient("http://supervisor/core", "token")
    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_resp.status = 200
    mock_session = MagicMock()
    mock_session.post.return_value = mock_resp
    client._session = mock_session
    result = await client.call_service("light", "turn_on", {"entity_id": "light.sala"})
    assert result is True


# ---------------------------------------------------------------------------
# SEC-004 — max_tokens cap
# ---------------------------------------------------------------------------

def test_create_agent_caps_max_tokens():
    from hiris.app.agent_engine import AgentEngine
    from unittest.mock import MagicMock, patch
    engine = AgentEngine(ha_client=MagicMock(), data_path="/tmp/test_agents.json")
    with patch.object(engine, "_save"):
        with patch.object(engine, "_schedule_agent"):
            agent = engine.create_agent({
                "name": "Test",
                "type": "chat",
                "trigger": {"type": "manual"},
                "max_tokens": 99999,
            })
    assert agent.max_tokens == 8192


def test_update_agent_caps_max_tokens():
    from hiris.app.agent_engine import AgentEngine
    from unittest.mock import MagicMock, patch
    engine = AgentEngine(ha_client=MagicMock(), data_path="/tmp/test_agents.json")
    with patch.object(engine, "_save"):
        with patch.object(engine, "_schedule_agent"):
            agent = engine.create_agent({
                "name": "Test",
                "type": "chat",
                "trigger": {"type": "manual"},
                "max_tokens": 4096,
            })
    with patch.object(engine, "_save"):
        with patch.object(engine, "_unschedule_agent"):
            with patch.object(engine, "_schedule_agent"):
                updated = engine.update_agent(agent.id, {"max_tokens": 50000})
    assert updated.max_tokens == 8192


# ---------------------------------------------------------------------------
# SEC-001 — config.yaml does not expose port
# ---------------------------------------------------------------------------

def test_config_yaml_no_direct_port():
    import yaml
    import os
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "hiris", "config.yaml"
    )
    with open(config_path) as f:
        config = yaml.safe_load(f)
    assert "ports" not in config, (
        "config.yaml must not expose ports directly — use Ingress only"
    )


# ---------------------------------------------------------------------------
# SEC-021 — APScheduler cron coalesce
# ---------------------------------------------------------------------------

def test_cron_job_uses_coalesce():
    """Verify that _schedule_agent passes coalesce=True to add_job."""
    from hiris.app.agent_engine import AgentEngine, Agent
    engine = AgentEngine(ha_client=MagicMock())
    mock_scheduler = MagicMock()
    engine._scheduler = mock_scheduler
    agent = Agent(
        id="test",
        name="T",
        type="preventive",
        trigger={"type": "preventive", "cron": "0 8"},
        system_prompt="",
        allowed_tools=[],
        enabled=True,
    )
    engine._schedule_agent(agent)
    call_kwargs = mock_scheduler.add_job.call_args[1]
    assert call_kwargs.get("coalesce") is True
    assert call_kwargs.get("misfire_grace_time") == 60
