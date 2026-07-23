import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, d, s, data):
        self.calls.append((d, s, data))
        return {"ok": True}


@pytest.mark.asyncio
async def test_mixed_entity_and_area_blocked_unconfirmed():
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"light": "green"}})
    r = await disp.dispatch("call_ha_service",
                            {"domain": "light", "service": "turn_on",
                             "data": {"entity_id": "light.green_lamp", "area_id": "soggiorno"}})
    assert "error" in r and disp._ha.calls == []
