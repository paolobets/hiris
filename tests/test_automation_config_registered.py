def test_get_automation_config_registered_in_runner():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_automation_config" in names
    assert "get_automation_config" in EVALUATION_ONLY_TOOLS
