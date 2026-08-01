def test_get_advisories_registered_in_runner():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    names = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_advisories" in names
    assert "get_advisories" in EVALUATION_ONLY_TOOLS
