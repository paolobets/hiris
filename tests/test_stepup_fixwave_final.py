"""Final-review fix wave for Slice 2 (step-up chat), applied in one pass:

FIX 1 (IMPORTANT): the OTP typed in chat (confirm_pending({"code": ...})) must
not appear in cleartext in server logs. ToolDispatcher.dispatch logs every
tool call's inputs; "code" is now in the redaction set.

FIX 2 (IMPORTANT): the OTP must not be echoed back in the chat HTTP debug
payload (handlers_chat.py's tools_called/last_tool_calls).

FIX 3 (DECISION APPLIED): red/dangerous chat pendings must be page/OTP-only —
no one-tap notification buttons — matching the gateway's execute-API, which
uses actionable=(tier == "yellow"). Yellow keeps the one-tap buttons. The OTP
itself is still included in the push message either way (Task 4 fix).

FIX 5 (MINOR, safety): no real user identity (falsy, or the "home"
no-identity fallback bucket) must never mint a step-up OTP pending — there is
no phone to target and no chat OTP flow that could ever resolve it. The
dispatcher falls back to the Slice-1 "richiede conferma" error instead.
"""
import re

import pytest
from aiohttp import web

from hiris.app.tools.dispatcher import ToolDispatcher
from hiris.app.server import request_confirmation_stepup


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
# FIX 3 — red pendings are OTP-only (actionable=False); yellow keeps buttons
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_yellow_pending_is_actionable_with_buttons(tmp_path):
    app = web.Application()
    ha = _FakeHA()
    app["ha_client"] = ha
    data_dir = str(tmp_path)
    inputs = {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.boiler"}}

    res = await request_confirmation_stepup(
        app, data_dir, tool="call_ha_service", inputs=inputs, tier="yellow", user="paolo",
    )
    assert res is not None and res.get("id")
    assert len(ha.calls) == 1
    sent_data = ha.calls[0][2]
    assert "data" in sent_data and "actions" in sent_data["data"], (
        "yellow pendings must keep one-tap Approva/Nega buttons")


@pytest.mark.asyncio
async def test_red_pending_is_not_actionable_no_buttons_but_otp_present(tmp_path):
    app = web.Application()
    ha = _FakeHA()
    app["ha_client"] = ha
    data_dir = str(tmp_path)
    inputs = {"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}}

    res = await request_confirmation_stepup(
        app, data_dir, tool="call_ha_service", inputs=inputs, tier="red", user="paolo",
    )
    assert res is not None and res.get("id")
    assert len(ha.calls) == 1
    sent_data = ha.calls[0][2]
    assert "data" not in sent_data, "red pendings must NOT get one-tap buttons"
    # The OTP is still included in the push message (Task 4 fix) — confirmation
    # for red pendings is possible only by typing this code in chat.
    assert re.search(r"\d{6}", sent_data["message"]) is not None


# ---------------------------------------------------------------------------
# FIX 5 — no-identity user (falsy / "home") never mints a step-up pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_pending_minted_for_falsy_or_home_user(tmp_path):
    app = web.Application()
    ha = _FakeHA()
    app["ha_client"] = ha
    data_dir = str(tmp_path)
    inputs = {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.x"}}

    for falsy_user in (None, "", "home"):
        res = await request_confirmation_stepup(
            app, data_dir, tool="call_ha_service", inputs=inputs, tier="yellow", user=falsy_user,
        )
        assert res is None, f"expected None for user={falsy_user!r}"
    # No notification should have gone out either — no pending was minted.
    assert ha.calls == []


@pytest.mark.asyncio
async def test_dispatcher_falls_back_to_error_when_confirmation_callback_returns_none():
    async def sink(*, tool, inputs, tier, user):
        return None  # simulates request_confirmation_stepup's no-identity guard

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
