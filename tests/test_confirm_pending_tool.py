import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, d, s, data):
        self.calls.append((d, s, data))
        return {"ok": True}


@pytest.mark.asyncio
async def test_confirm_pending_wrong_code():
    async def executor(*, code, user):
        return {"error": "Codice non valido o scaduto."} if code != "111111" else {"ok": True}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    r = await disp.dispatch("confirm_pending", {"code": "000000"}, user_id="paolo")
    assert "error" in r


@pytest.mark.asyncio
async def test_confirm_pending_right_code_executes():
    async def executor(*, code, user):
        assert user == "paolo"
        return {"ok": True, "result": {"ok": True}} if code == "111111" else {"error": "x"}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    r = await disp.dispatch("confirm_pending", {"code": "111111"}, user_id="paolo")
    assert r.get("ok") is True


@pytest.mark.asyncio
async def test_confirm_pending_no_executor_configured():
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={})
    r = await disp.dispatch("confirm_pending", {"code": "111111"}, user_id="paolo")
    assert r == {"error": "Conferma non disponibile"}


@pytest.mark.asyncio
async def test_confirm_pending_missing_code():
    async def executor(*, code, user):
        raise AssertionError("executor should not be called with a missing code")

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    r = await disp.dispatch("confirm_pending", {}, user_id="paolo")
    assert "error" in r


@pytest.mark.asyncio
async def test_confirm_pending_strips_code_whitespace():
    seen = {}

    async def executor(*, code, user):
        seen["code"] = code
        return {"ok": True, "result": {}}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    r = await disp.dispatch("confirm_pending", {"code": "  111111  "}, user_id="paolo")
    assert r.get("ok") is True
    assert seen["code"] == "111111"


@pytest.mark.asyncio
async def test_confirm_pending_user_comes_from_dispatch_user_id_not_input():
    # Security: `user` passed to the executor must be the trusted dispatch
    # user_id, never something the LLM could smuggle in via tool inputs.
    seen = {}

    async def executor(*, code, user):
        seen["user"] = user
        return {"ok": True, "result": {}}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    await disp.dispatch("confirm_pending", {"code": "111111", "user": "attacker"}, user_id="paolo")
    assert seen["user"] == "paolo"


# --- server.confirm_pending_execute (the REAL executor, not a replica) ---
# These call the module-level function extracted from server.py's
# _confirm_executor closure directly, so the 6-digit validation gate and the
# frozen-entry execution get real coverage instead of a hand-rebuilt copy.

class _RecordingDispatcher:
    """Fake tool_dispatcher that records what dispatch() actually executed,
    so we can assert the FROZEN pending entry's inputs are what runs — never
    whatever `code` (or anything else) the confirm_pending tool call carried."""

    def __init__(self):
        self.calls = []

    async def dispatch(self, tool, inputs, **kwargs):
        self.calls.append((tool, inputs, kwargs))
        return {"executed": True}


@pytest.mark.asyncio
async def test_confirm_pending_execute_rejects_garbage_code_without_verify_or_dispatch(tmp_path):
    from aiohttp import web
    from hiris.app.api import handlers_gateway_pending as P
    from hiris.app.server import confirm_pending_execute

    data_dir = str(tmp_path)
    frozen_inputs = {"domain": "lock", "service": "unlock",
                      "data": {"entity_id": "lock.front_door"}}
    entry = P.create_pending(
        data_dir, tool="call_ha_service", inputs=frozen_inputs, tier="red",
        origin="chat", label="lock.unlock", user="paolo", with_otp=True,
    )

    app = web.Application()
    app["data_dir"] = data_dir
    recorder = _RecordingDispatcher()
    app["tool_dispatcher"] = recorder

    result = await confirm_pending_execute(app, code="not-a-code", user="paolo")

    assert result == {"error": "Codice non valido."}
    # Nothing was dispatched...
    assert recorder.calls == []
    # ...and the garbage code did not burn a lockout attempt against the real
    # pending: the correct OTP must still verify afterwards.
    found = P.verify_otp(data_dir, "paolo", entry["otp"])
    assert found is not None
    P.resolve_pending(data_dir, found["id"], "approved")


@pytest.mark.asyncio
async def test_confirm_pending_execute_executes_frozen_entry_not_tool_call_inputs(tmp_path):
    from aiohttp import web
    from hiris.app.api import handlers_gateway_pending as P
    from hiris.app.server import confirm_pending_execute

    data_dir = str(tmp_path)
    frozen_inputs = {"domain": "lock", "service": "unlock",
                      "data": {"entity_id": "lock.front_door"}}
    entry = P.create_pending(
        data_dir, tool="call_ha_service", inputs=frozen_inputs, tier="red",
        origin="chat", label="lock.unlock", user="paolo", with_otp=True,
    )
    otp = entry["otp"]

    app = web.Application()
    app["data_dir"] = data_dir
    recorder = _RecordingDispatcher()
    app["tool_dispatcher"] = recorder

    result = await confirm_pending_execute(app, code=otp, user="paolo")

    assert result["ok"] is True
    assert len(recorder.calls) == 1
    tool, inputs, kwargs = recorder.calls[0]
    assert tool == "call_ha_service"
    # The executed inputs are the FROZEN ones from the pending record, not
    # anything derived from the confirm_pending tool call (which only ever
    # carried `code`).
    assert inputs == frozen_inputs
    assert kwargs.get("tier_confirmed") is True

    # Pending is resolved as approved and single-use (OTP already consumed).
    again = P.verify_otp(data_dir, "paolo", otp)
    assert again is None


@pytest.mark.asyncio
async def test_confirm_pending_execute_rejects_non_ascii_digits(tmp_path):
    from aiohttp import web
    from hiris.app.api import handlers_gateway_pending as P
    from hiris.app.server import confirm_pending_execute

    data_dir = str(tmp_path)
    frozen_inputs = {"domain": "lock", "service": "unlock",
                      "data": {"entity_id": "lock.front_door"}}
    entry = P.create_pending(
        data_dir, tool="call_ha_service", inputs=frozen_inputs, tier="red",
        origin="chat", label="lock.unlock", user="paolo", with_otp=True,
    )

    app = web.Application()
    app["data_dir"] = data_dir
    recorder = _RecordingDispatcher()
    app["tool_dispatcher"] = recorder

    # Arabic-Indic digits: str.isdigit() is True for these, but they are not
    # ASCII 0-9 and must be rejected before ever reaching verify_otp.
    non_ascii_code = "١٢٣٤٥٦"  # ١٢٣٤٥٦
    assert non_ascii_code.isdigit()  # sanity: confirms isdigit() alone would pass this

    result = await confirm_pending_execute(app, code=non_ascii_code, user="paolo")

    assert result == {"error": "Codice non valido."}
    assert recorder.calls == []
    found = P.verify_otp(data_dir, "paolo", entry["otp"])
    assert found is not None
    P.resolve_pending(data_dir, found["id"], "approved")
