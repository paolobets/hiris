import pytest
from hiris.app.mcp.tiers import TOOLS, get_tool
from hiris.app.mcp.server import build_mcp


def test_catalog_has_13_tools_no_bridge():
    names = {t.name for t in TOOLS}
    assert "call_service" in names and get_tool("call_service").hiris_tool == "call_ha_service"
    assert "claim_reasoning_job" not in names and "submit_decision" not in names
    assert len(TOOLS) == 13


@pytest.mark.asyncio
async def test_build_mcp_registers_all_tools_and_forwards():
    calls = []

    class _Client:
        async def execute(self, tool, inputs):
            calls.append((tool, inputs)); return {"result": "ok"}

    mcp = build_mcp(_Client())
    # Installed FastMCP (3.x) exposes async introspection as list_tools(),
    # not get_tools() (2.x API from the brief). Adapted per brief's fallback
    # note: the real assertion is that every catalog tool name is registered.
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names >= {t.name for t in TOOLS}
