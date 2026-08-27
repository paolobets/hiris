"""
Security regression tests — run on every PR.

These tests validate that the security fixes applied post-audit hold and
do not regress. They are deliberately narrow (fast, no real network calls).
"""
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_with_runner(runner):
    """Minimal aiohttp app wired like the real server but without startup hooks.

    fetta E4 Task 3 ("un bot solo"): this used to also register the
    /api/chatbots/{agent_id} GET/PUT/DELETE and .../usage routes, for the
    SEC-014 tests below. Those handlers are gone with the rest of the CRUD
    (three creation paths all converged on POST /api/chatbots with
    `enabled: true` by default, the opposite of the scope) -- only /api/chat
    is left as a live subject here, so only that route is registered now.
    """
    from hiris.app.api.handlers_chat import handle_chat
    from hiris.app.impostazioni_chat import ImpostazioniChat
    from hiris.app.server import _security_headers

    app = web.Application(middlewares=[_security_headers])
    app["llm_router"] = runner
    app["claude_runner"] = runner
    app["impostazioni_chat"] = ImpostazioniChat(system_prompt="test")
    app["data_dir"] = "/tmp"

    app.router.add_post("/api/chat", handle_chat)
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
# Retired (fetta E4 Task 3, "un bot solo"): all three tests defended
# `_check_chatbot_id` inside `handle_get_chatbot` (GET /api/chatbots/
# {agent_id}) -- gone with the rest of the CRUD. Verified failing for
# construction (`ImportError: cannot import name 'handle_get_chatbot'` from
# `_make_app_with_runner`, before that helper was itself trimmed) prior to
# deletion. Even with the helper trimmed, the route no longer resolves at
# all: path-traversal/invalid-char/valid-uuid would all just 404 for "no
# such route" instead of exercising any validation -- no live subject left
# to test.

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

# Retired (fetta E4 Task 3, "un bot solo"): test_create_agent_caps_max_tokens
# / test_update_agent_caps_max_tokens pinned `ChatbotEngine.create_chatbot`/
# `update_chatbot` clamping `max_tokens` via `_cap_max_tokens` at save time --
# both the two CRUD methods and the cap helper are gone (their only callers
# were create/update). Verified failing for construction
# (`AttributeError: 'ChatbotEngine' object has no attribute 'create_chatbot'`)
# before deletion. The runtime chat floor (`claude_runner.CHAT_MAX_TOKENS`,
# which floors every request's max_tokens regardless of the stored
# per-persona value) is a different, still-live mechanism and is not
# affected -- see tests/test_chat_token_limits.py Part 2 and
# tests/test_api.py::test_chat_passes_model_to_runner.


# ---------------------------------------------------------------------------
# SEC-001 — config.yaml does not expose port
# ---------------------------------------------------------------------------

def test_config_yaml_no_direct_port():
    """SEC-001 — ensure addon non espone porte di default.

    v0.10.11: rilassato — `ports:` può essere declared ma TUTTI i valori
    devono essere `null` (port mappable solo se l'utente imposta la host port
    nella sezione Network di HA UI). Questo permette la diagnostica senza
    esporre nulla di default. Valori non-null = auto-binding = REJECT.

    Versione B (3.0.0): l'opzione `debug_expose_port` che questo commento
    citava e' USCITA -- non apriva niente, stampava sette righe di promemoria
    nel registro. Il meccanismo che questo test sorveglia e' sempre stato
    `ports:`, e non e' cambiato.
    """
    import os

    import yaml
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
# four `DispatcherStrumenti` tools (fetta E2 Task 2, "il Test Run passa ai
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
#
# fetta «comandare» (Task 7). One present-tense clause above has stopped being
# true and is NOT rewritten -- the block is a dated record of why these tests
# were deleted, and it was correct on its date. The clause is
# "`casa/strumenti.py`'s STRUMENTI_CONOSCENZA has no automation tool at all".
# It still has no automation-SPECIFIC tool, but since Task 5 it has `esegui`,
# which calls any Home Assistant service the installation declares -- and
# `automation.turn_on` on an `automation.*` entity passes the verification and
# executes. So the capability this section used to gate is reachable again,
# by a different road and with no gate: that is the deliberate decision of
# this fetta (capability first, safeguards as a designed phase). What replaces
# the gate today is verification, not authorisation -- `azione/verifica.py`
# checks the service, the entity and the parameters against THIS installation,
# and `azione/porta.py` reads the state back. The gating logic these deleted
# tests covered is still gone, and is not coming back in this form.

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
