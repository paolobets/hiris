from hiris.app.mcp.guard import McpGuard


def test_killed_blocks_and_toggles():
    g = McpGuard()
    assert g.is_killed() is False
    g.set_killed(True)
    assert g.is_killed() is True
    g.set_killed(False)
    assert g.is_killed() is False


def test_record_keeps_bounded_audit():
    g = McpGuard(audit_max=2)
    g.record("get_home_status", "ok", 5)
    g.record("call_service", "ok", 9)
    g.record("get_history", "ok", 3)
    assert len(g.audit) == 2 and g.audit[-1]["tool"] == "get_history"
