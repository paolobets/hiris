import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, d, s, data):
        self.calls.append((d, s, data))
        return {"ok": True}


@pytest.mark.asyncio
async def test_confirm_creates_pending_and_returns_confirmation_required():
    seen = {}

    async def sink(*, tool, inputs, tier, user):
        seen.update(tool=tool, tier=tier, user=user, entity=inputs["data"]["entity_id"])
        return {"id": "nonce123", "otp_sent": True}

    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"switch": "yellow"}},
                          request_confirmation=sink)
    r = await disp.dispatch("call_ha_service",
                            {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.boiler"}},
                            user_id="paolo")
    assert r["status"] == "confirmation_required" and r["id"] == "nonce123"
    assert r["tier"] == "yellow"
    assert "message" in r
    assert seen == {"tool": "call_ha_service", "tier": "yellow",
                    "user": "paolo", "entity": "switch.boiler"}
    assert disp._ha.calls == []  # NON eseguita finché non confermata


@pytest.mark.asyncio
async def test_confirm_without_callback_falls_back_to_error():
    disp = ToolDispatcher(ha_client=_FakeHA(), notify_config={},
                          execute_policy={"tiers": {"switch": "yellow"}})
    r = await disp.dispatch("call_ha_service",
                            {"domain": "switch", "service": "turn_on",
                             "data": {"entity_id": "switch.x"}}, user_id="paolo")
    assert "error" in r
