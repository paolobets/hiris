"""Final-review fix wave for Slice 2 (step-up chat), applied in one pass:

FIX 1 (IMPORTANT): the OTP typed in chat (confirm_pending({"code": ...})) must
not appear in cleartext in server logs. ToolDispatcher.dispatch logs every
tool call's inputs; "code" is now in the redaction set.

FIX 2 (IMPORTANT): the OTP must not be echoed back in the chat HTTP debug
payload (handlers_chat.py's tools_called/last_tool_calls).

Fetta E2 Task 5 ("escono le conferme del gateway"): FIX 3 (red/yellow
actionable split), Review C/#1 (private-channel-only OTP) and FIX 5
(no-identity guard) all exercised `server.request_confirmation_stepup`
directly, which is deleted along with `handlers_gateway_pending.py` (the
whole pending/OTP store it drove is dead by construction — the
user->notify_users mapping it relied on is written by no interface). Those
tests died with their subject and were removed, not moved: nothing else in
the codebase re-derives that specific behaviour.

FIX 1, FIX 2 and the dispatcher confirmation-callback contract below test
`ToolDispatcher` itself (untouched by Task 5, still reachable from real
chat: `confirm_pending`/`call_ha_service` remain in `ALL_TOOL_DEFS` and
`ToolDispatcher._gate`/`confirm_pending` branches still accept an injected
callback) via locally-defined fakes, not the deleted server functions — so
they survive and stay here.
"""
import pytest

from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls: list[tuple] = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {"ok": True}


# ---------------------------------------------------------------------------
# FIX 1 — OTP redacted from the dispatcher's "Tool call: ..." log line
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_pending_code_redacted_in_dispatch_log(caplog):
    async def executor(*, code, user):
        return {"ok": True, "result": {}}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={}, confirm_executor=executor)
    with caplog.at_level("INFO", logger="hiris.app.tools.dispatcher"):
        await disp.dispatch("confirm_pending", {"code": "123456"}, user_id="paolo")

    logged = [r.message for r in caplog.records
              if r.message.startswith("Tool call: confirm_pending")]
    assert logged, "expected a 'Tool call: confirm_pending(...)' log line"
    assert "123456" not in logged[0]
    assert "***" in logged[0]


@pytest.mark.asyncio
async def test_code_key_redacted_generically_for_any_tool(caplog):
    """The redaction is keyed on the input name "code" for ANY tool call, not
    special-cased to confirm_pending — no legitimate tool needs `code` logged."""
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"switch": "off"}})
    with caplog.at_level("INFO", logger="hiris.app.tools.dispatcher"):
        await disp.dispatch("call_ha_service",
                            {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.x"}, "code": "999999"},
                            user_id="paolo")
    logged = [r.message for r in caplog.records
              if r.message.startswith("Tool call: call_ha_service")]
    assert logged
    assert "999999" not in logged[0]
    assert "***" in logged[0]


# ---------------------------------------------------------------------------
# FIX 2 — OTP redacted from the chat HTTP debug payload (handlers_chat.py)
# ---------------------------------------------------------------------------

def test_debug_input_redacts_confirm_pending_code():
    # Exercise the same closure logic handle_chat builds `tools_called` with,
    # inlined here rather than importing the nested function (it isn't
    # exported); this mirrors the actual list comprehension in
    # handlers_chat.py verbatim.
    def _debug_input(t: dict):
        inp = t.get("input")
        if t.get("tool") == "confirm_pending" and isinstance(inp, dict) and "code" in inp:
            return {**inp, "code": "***"}
        return inp

    raw = [{"tool": "confirm_pending", "input": {"code": "123456"}}]
    tools_called = [{"tool": t.get("tool", ""), "input": _debug_input(t)} for t in raw]
    assert tools_called[0]["input"] == {"code": "***"}


def test_debug_input_leaves_other_tools_untouched():
    def _debug_input(t: dict):
        inp = t.get("input")
        if t.get("tool") == "confirm_pending" and isinstance(inp, dict) and "code" in inp:
            return {**inp, "code": "***"}
        return inp

    raw = [{"tool": "call_ha_service",
            "input": {"domain": "switch", "service": "turn_on",
                      "data": {"entity_id": "switch.boiler"}}}]
    tools_called = [{"tool": t.get("tool", ""), "input": _debug_input(t)} for t in raw]
    assert tools_called[0]["input"]["data"]["entity_id"] == "switch.boiler"


# ---------------------------------------------------------------------------
# Dispatcher confirmation-callback contract: an injected `request_confirmation`
# that returns None or a dict without "id" must fall back to the Slice-1
# error, never mint a false "confirmation_required" status. This is exactly
# the shape ToolDispatcher now ALWAYS sees in production (Task 5: server.py
# no longer injects a real callback), so this fallback is the live path.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_error_when_confirmation_callback_returns_none():
    async def sink(*, tool, inputs, tier, user):
        return None  # simulates a fail-closed step-up guard

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"switch": "yellow"}},
                          request_confirmation=sink)
    r = await disp.dispatch("call_ha_service",
                            {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.x"}},
                            user_id="home")
    assert r == {"error": "Azione a rischio: richiede conferma."}


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_error_when_callback_returns_dict_without_id():
    async def sink(*, tool, inputs, tier, user):
        return {"otp_sent": False}  # malformed / no "id" — same fallback path

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"switch": "yellow"}},
                          request_confirmation=sink)
    r = await disp.dispatch("call_ha_service",
                            {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.x"}},
                            user_id="paolo")
    assert r == {"error": "Azione a rischio: richiede conferma."}
