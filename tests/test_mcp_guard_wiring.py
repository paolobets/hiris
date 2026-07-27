import pytest
from fastmcp import Client

from hiris.app.mcp.guard import McpGuard
from hiris.app.mcp.server import build_mcp


class _FakeClient:
    """Records calls and returns whatever payload is queued next, mimicking
    LocalExecuteClient: never raises, signals failure via {"error": ...}."""

    def __init__(self):
        self.calls = []
        self._results = []

    def queue(self, result):
        self._results.append(result)

    async def execute(self, tool, inputs):
        self.calls.append((tool, inputs))
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_killed_short_circuits_before_reaching_client():
    guard = McpGuard()
    guard.set_killed(True)
    fake = _FakeClient()
    mcp = build_mcp(fake, guard)

    async with Client(mcp) as c:
        result = await c.call_tool("call_service", {"inputs": {}})

    assert fake.calls == []
    payload = result.data if hasattr(result, "data") else result
    text = str(payload)
    assert "kill-switch attivo" in text or "blocked" in text
    assert len(guard.audit) == 0


@pytest.mark.asyncio
async def test_record_reflects_payload_outcome_not_just_exceptions():
    guard = McpGuard()
    fake = _FakeClient()
    mcp = build_mcp(fake, guard)

    fake.queue({"result": "ok"})
    async with Client(mcp) as c:
        await c.call_tool("call_service", {"inputs": {}})

    assert len(guard.audit) == 1
    assert guard.audit[-1]["tool"] == "call_ha_service"
    assert guard.audit[-1]["outcome"] == "ok"

    # LocalExecuteClient.execute never raises: a semaforo denial / HTTP error
    # / connectivity failure surfaces as {"error": ...} with a 200-like return,
    # not an exception. The recorded outcome must reflect that.
    fake.queue({"error": "denied"})
    async with Client(mcp) as c:
        await c.call_tool("call_service", {"inputs": {}})

    assert len(guard.audit) == 2
    assert guard.audit[-1]["tool"] == "call_ha_service"
    assert guard.audit[-1]["outcome"] == "error"
