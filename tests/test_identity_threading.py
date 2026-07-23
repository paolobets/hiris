import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    async def call_service(self, d, s, data): return {"ok": True}


@pytest.mark.asyncio
async def test_dispatch_accepts_user_id():
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"light": "green"}})
    # user_id is accepted and does not break a normal green call
    r = await disp.dispatch("call_ha_service",
                            {"domain": "light", "service": "turn_on",
                             "data": {"entity_id": "light.k"}},
                            user_id="paolo")
    assert r == {"ok": True}
