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
    from hiris.app.api.handlers_chatbots import (
        handle_get_chatbot, handle_update_chatbot, handle_delete_chatbot,
        handle_run_chatbot, handle_get_chatbot_usage, handle_reset_chatbot_usage,
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
    agent.restrict_to_home = False
    agent.require_confirmation = False
    agent.max_chat_turns = 0

    engine = MagicMock()
    engine.get_chatbot.return_value = agent
    engine.get_default_chatbot.return_value = agent

    app = web.Application(middlewares=[_security_headers])
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["engine"] = engine
    app["data_dir"] = "/tmp"

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chatbots/{agent_id}", handle_get_chatbot)
    app.router.add_put("/api/chatbots/{agent_id}", handle_update_chatbot)
    app.router.add_delete("/api/chatbots/{agent_id}", handle_delete_chatbot)
    app.router.add_post("/api/chatbots/{agent_id}/run", handle_run_chatbot)
    app.router.add_get("/api/chatbots/{agent_id}/usage", handle_get_chatbot_usage)
    app.router.add_post("/api/chatbots/{agent_id}/usage/reset", handle_reset_chatbot_usage)
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
        resp = await client.get("/api/chatbots/../../etc/passwd")
        # aiohttp URL routing won't match, but validate it doesn't 200 OK
        assert resp.status in (400, 404)


@pytest.mark.asyncio
async def test_agent_get_rejects_invalid_id_characters():
    runner = AsyncMock()
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chatbots/bad<script>id")
        assert resp.status in (400, 404)


@pytest.mark.asyncio
async def test_agent_get_accepts_valid_uuid():
    runner = AsyncMock()
    app = _make_app_with_runner(runner)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/chatbots/550e8400-e29b-41d4-a716-446655440000")
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
                assert "X-Frame-Options" not in resp.headers  # HA Ingress richiede iframe
                assert resp.headers.get("Referrer-Policy") == "no-referrer"


# SEC-010 — domain/service regex in ha_client: usciva con `call_service`
# (review finale fetta E3, Important #3 -- l'ultima primitiva di attuazione
# del codebase, zero chiamanti di produzione). Le tre prove qui sopra
# difendevano SOLO quella funzione (dominio/servizio invalidi rifiutati,
# servizio valido accettato): con lei uscita, non restava nessun soggetto
# vivo da difendere.

# ---------------------------------------------------------------------------
# SEC-004 — max_tokens cap
# ---------------------------------------------------------------------------

def test_create_agent_caps_max_tokens():
    """Every persona is a chat entity now (Slice 5 Task 2 dropped `type`),
    so there is a single cap regardless of what a stray "type" payload key
    says — 16000, not the old non-chat 8192."""
    from hiris.app.chatbot_engine import ChatbotEngine
    from unittest.mock import MagicMock, patch
    engine = ChatbotEngine(ha_client=MagicMock(), data_path="/tmp/test_agents.json")
    with patch.object(engine, "_save"):
        agent = engine.create_chatbot({
            "name": "Test",
            "type": "chat",
            "trigger": {"type": "manual"},
            "max_tokens": 99999,
        })
        formerly_non_chat = engine.create_chatbot({
            "name": "Mon",
            "type": "monitor",
            "trigger": {"type": "manual"},
            "max_tokens": 99999,
        })
    assert agent.max_tokens == 16000
    assert formerly_non_chat.max_tokens == 16000  # single cap now — no non-chat variant


def test_update_agent_caps_max_tokens():
    from hiris.app.chatbot_engine import ChatbotEngine
    from unittest.mock import MagicMock, patch
    engine = ChatbotEngine(ha_client=MagicMock(), data_path="/tmp/test_agents.json")
    with patch.object(engine, "_save"):
        agent = engine.create_chatbot({
            "name": "Test",
            "type": "chat",
            "trigger": {"type": "manual"},
            "max_tokens": 4096,
        })
    with patch.object(engine, "_save"):
        with patch.object(engine, "_unschedule_chatbot"):
            updated = engine.update_chatbot(agent.id, {"max_tokens": 50000})
    assert updated.max_tokens == 16000  # chat cap


# ---------------------------------------------------------------------------
# SEC-001 — config.yaml does not expose port
# ---------------------------------------------------------------------------

def test_config_yaml_no_direct_port():
    """SEC-001 — ensure addon non espone porte di default.

    v0.10.11: rilassato — `ports:` può essere declared ma TUTTI i valori
    devono essere `null` (port mappable solo se l'utente attiva esplicitamente
    debug_expose_port + imposta host port nella sezione Network di HA UI).
    Questo permette il toggle "Debug expose port" senza esporre nulla di
    default. Valori non-null = auto-binding = REJECT.
    """
    import yaml
    import os
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "hiris", "config.yaml"
    )
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    ports = config.get("ports")
    if ports is not None:
        for port_spec, host_port in ports.items():
            assert host_port is None, (
                f"config.yaml ports[{port_spec}] must be null (not auto-bound). "
                f"Got: {host_port!r}. User opts-in via HA UI Network section."
            )


# ---------------------------------------------------------------------------
# SEC-021 — APScheduler cron coalesce
# ---------------------------------------------------------------------------
# Retired (Slice 5): _schedule_agent and all autonomous-agent scheduling was
# removed from ChatbotEngine — the Sentinella (watcher/) was the sole
# proactive engine at the time, and did not use APScheduler add_job() at
# all. fetta E3 Task 7: the Sentinella itself (and watcher/) is gone too —
# no proactive engine of any kind remains.

# ---------------------------------------------------------------------------
# SEC-022 / SEC-022b — automation tools rispettano allowed_services/
# allowed_entities/semaforo, automation_id validato.
# ---------------------------------------------------------------------------
# Retired (fetta E2 Task 7, "esce il dispatcher"): this whole section drove
# its assertions through `ToolDispatcher.dispatch("trigger_automation"/
# "toggle_automation"/"set_input_helper", ...)`, testing gating logic
# (allowed_services/allowed_entities checks, the semaforo `_gate`,
# `_AUTOMATION_ID_RE` validation) that lived ONLY inside `tools/
# dispatcher.py` -- `automation_tools.py`'s own trigger_automation/
# toggle_automation and `calendar_tools.py`'s set_input_helper never did
# this validation themselves. Checked, not assumed: none of the three tools
# is a valid Task action type (`_ALLOWED_TASK_ACTIONS` in the now-deleted
# dispatcher.py was `{"call_ha_service", "send_notification",
# "create_task"}`), so they were never reachable via `task_engine._run_action`
# either -- their ONLY caller was direct LLM tool dispatch. That caller was
# already gone before this task: the chat/Test Run surfaces switched to the
# four `DispatcherConoscenza` tools (fetta E2 Task 2, "il Test Run passa ai
# 4 strumenti"; `casa/strumenti.py`'s STRUMENTI_CONOSCENZA has no automation
# tool at all), and `EVALUATION_ONLY_TOOLS` (claude_runner.py) has
# deliberately excluded all three from the Sentinel/Agentbot evaluation
# catalog since before this fetta -- "Strumenti che ATTUANO davvero" are
# excluded there by design. So this gating logic had NO live caller left
# even while `ToolDispatcher` still existed (Tasks 3-6 of this fetta) --
# the capability itself (chat/an agent triggering/toggling an automation or
# setting an input helper) was ALREADY unreachable before this task, since
# fetta E2 Task 2 switched chat/Test Run away from the 34-tool catalog; this
# task removes the last code that implemented its (already inert) gating.
# Not a new regression, but newly UNDENIABLE: with the code gone there is
# nothing left claiming to test a live path, which is why the tests are
# deleted here rather than carried forward pointing at nothing.

# ---------------------------------------------------------------------------
# SEC-025 — CSRF middleware (require X-Requested-With on state-changing API)
# ---------------------------------------------------------------------------

def _make_csrf_app():
    """Mini app wired with CSRF middleware to verify behavior in isolation."""
    from hiris.app.api.middleware_csrf import csrf_middleware
    app = web.Application(middlewares=[csrf_middleware])
    app.router.add_post("/api/x", lambda r: web.json_response({"ok": True}))
    app.router.add_get("/api/x", lambda r: web.json_response({"ok": True}))
    app.router.add_delete("/api/x", lambda r: web.json_response({"ok": True}))
    app.router.add_post("/static/x", lambda r: web.json_response({"ok": True}))
    return app


@pytest.fixture
def csrf_strict(monkeypatch):
    """Override the test-suite default HIRIS_ALLOW_NO_CSRF=1 so CSRF middleware blocks again."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_CSRF", "")
    yield


@pytest.mark.asyncio
async def test_csrf_blocks_post_without_xrw(csrf_strict):
    async with TestClient(TestServer(_make_csrf_app())) as c:
        resp = await c.post("/api/x")
        assert resp.status == 403
        data = await resp.json()
        assert data["error"] == "csrf_required"


@pytest.mark.asyncio
async def test_csrf_blocks_delete_without_xrw(csrf_strict):
    async with TestClient(TestServer(_make_csrf_app())) as c:
        resp = await c.delete("/api/x")
        assert resp.status == 403


@pytest.mark.asyncio
async def test_csrf_allows_get_without_xrw(csrf_strict):
    """GET is a safe method — must always pass."""
    async with TestClient(TestServer(_make_csrf_app())) as c:
        resp = await c.get("/api/x")
        assert resp.status == 200


@pytest.mark.asyncio
async def test_csrf_allows_post_with_xrw(csrf_strict):
    """Any non-empty X-Requested-With value is accepted (browsers block CORS)."""
    async with TestClient(TestServer(_make_csrf_app())) as c:
        resp = await c.post("/api/x", headers={"X-Requested-With": "fetch"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_csrf_does_not_apply_to_non_api_paths(csrf_strict):
    """Static and Lovelace card paths are not protected (no auth surface)."""
    async with TestClient(TestServer(_make_csrf_app())) as c:
        resp = await c.post("/static/x")
        assert resp.status == 200


def _make_csrf_app_with_token(token="srv-secret"):
    """CSRF app that also carries an internal_token, to exercise the
    server-to-server exemption."""
    from aiohttp import web
    from hiris.app.api.middleware_csrf import csrf_middleware
    app = web.Application(middlewares=[csrf_middleware])
    app["internal_token"] = token
    app.router.add_post("/api/x", lambda r: web.json_response({"ok": True}))
    return app


@pytest.mark.asyncio
async def test_csrf_exempts_valid_internal_token_without_xrw(csrf_strict):
    """A server-to-server client with a valid X-HIRIS-Internal-Token is exempt
    from CSRF (it is not a browser, and it already proves the shared secret).
    This is what lets the MCP gateway and the Retro Panel proxy POST/PUT."""
    async with TestClient(TestServer(_make_csrf_app_with_token())) as c:
        resp = await c.post("/api/x", headers={"X-HIRIS-Internal-Token": "srv-secret"})
        assert resp.status == 200


@pytest.mark.asyncio
async def test_csrf_wrong_internal_token_not_exempt(csrf_strict):
    """An invalid token does not earn the CSRF exemption."""
    async with TestClient(TestServer(_make_csrf_app_with_token())) as c:
        resp = await c.post("/api/x", headers={"X-HIRIS-Internal-Token": "wrong"})
        assert resp.status == 403
