"""Task 6: a chat-origin pending, resolved via the notification tap
(``approve`` → ``execute_pending``), executes the frozen action exactly like
a gateway-origin pending — including ``tier_confirmed=True``."""
import pytest
from hiris.app.api import handlers_gateway_pending as P


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, d, s, data):
        self.calls.append((d, s, data))
        return {"ok": True}


class _Disp:
    def __init__(self, ha):
        self._ha = ha

    async def dispatch(self, tool, inputs, **kw):
        assert kw.get("tier_confirmed") is True
        return await self._ha.call_service(inputs["domain"], inputs["service"], inputs.get("data", {}))


@pytest.mark.asyncio
async def test_tap_executes_chat_pending(tmp_path):
    ha = _FakeHA()
    app = {"data_dir": str(tmp_path), "tool_dispatcher": _Disp(ha)}
    entry = P.create_pending(str(tmp_path), tool="call_ha_service",
                             inputs={"domain": "switch", "service": "turn_on",
                                     "data": {"entity_id": "switch.boiler"}},
                             tier="yellow", origin="chat", label="switch.turn_on",
                             user="paolo", with_otp=True)
    res = await P.approve(app, entry["id"])
    assert res["ok"] is True
    assert ha.calls == [("switch", "turn_on", {"entity_id": "switch.boiler"})]
