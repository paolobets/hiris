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
