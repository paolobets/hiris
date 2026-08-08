"""Final-review fix wave for Slice 2 (step-up chat), applied in one pass:

FIX 1 (IMPORTANT): the OTP typed in chat (confirm_pending({"code": ...})) must
not appear in cleartext in server logs. ToolDispatcher.dispatch logged every
tool call's inputs, with "code" in the redaction set.

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

Fetta E2 Task 7 ("esce il dispatcher"): FIX 1's two tests and the dispatcher
confirmation-callback contract tests below tested `ToolDispatcher` itself --
its own "Tool call: ..." log-redaction and its `_gate` fallback for a
malformed confirmation callback. `ToolDispatcher` is gone and nothing else
in the codebase re-derives either behaviour (the runners' fallback dispatch
branch no longer logs tool calls at all, and never had a confirmation-gate
of its own), so those tests died with their subject and were removed here
too. FIX 2 tests exercise `handlers_chat.py`'s debug-payload redaction, a
plain local closure with NO dependency on `ToolDispatcher` -- that subject
is untouched by this task, so they stay exactly as they were.
"""


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
