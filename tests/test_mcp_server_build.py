import pytest
from fastmcp import Client
from hiris.app.mcp.tiers import TOOLS, get_tool
from hiris.app.mcp.server import build_mcp


def test_catalog_has_15_tools_no_bridge():
    names = {t.name for t in TOOLS}
    assert "call_service" in names and get_tool("call_service").hiris_tool == "call_ha_service"
    assert "claim_reasoning_job" not in names and "submit_decision" not in names
    # get_logbook e' nel catalogo: la denylist di lettura pota la sua risposta,
    # quindi l'enumerazione della cronologia non e' piu' illimitata.
    # render_template resta fuori per una ragione diversa e ancora valida: un
    # template non ha un entity_id da filtrare, quindi la denylist non lo
    # coprirebbe. Le ragioni stanno in hiris/app/mcp/tiers.py, e l'assenza e'
    # pinnata anche per NOME in tests/test_diagnostics_tools.py.
    assert "get_logbook" in names
    assert "render_template" not in names
    assert len(TOOLS) == 15  # +get_advisories, +get_logbook (READ)


@pytest.mark.asyncio
async def test_build_mcp_registers_all_tools_and_forwards():
    calls = []

    class _Client:
        async def execute(self, tool, inputs):
            calls.append((tool, inputs)); return {"result": "ok"}

    mcp = build_mcp(_Client())
    # Pinned dependency is fastmcp>=2.11.0,<3.0.0 (resolves to 2.14.7), whose
    # async introspection API is get_tools() -> dict[str, Tool], not the 3.x
    # list_tools(). Assert every catalog tool name is registered.
    tools = await mcp.get_tools()
    assert set(tools.keys()) >= {t.name for t in TOOLS}

    # Forwarding: invoke one tool through the public in-memory FastMCP client
    # and assert the fake client received the translated hiris_tool name and
    # inputs.
    async with Client(mcp) as c:
        await c.call_tool("call_service", {"inputs": {"x": 1}})
    assert ("call_ha_service", {"x": 1}) in calls
