import pytest
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {"ok": True}


def _disp(policy):
    return ToolDispatcher(ha_client=_FakeHA(), notify_config={}, execute_policy=policy)


async def _call(disp, domain="light", service="turn_on", entity_id="light.kitchen"):
    return await disp.dispatch(
        "call_ha_service",
        {"domain": domain, "service": service, "data": {"entity_id": entity_id}},
    )


@pytest.mark.asyncio
async def test_green_executes():
    d = _disp({"tiers": {"light": "green"}})
    r = await _call(d)
    assert r == {"ok": True}
    assert d._ha.calls == [("light", "turn_on", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_unconfigured_blocked_fail_closed():
    d = _disp({})  # no tiers -> off
    r = await _call(d)
    assert "error" in r and "off" in r["error"].lower()
    assert d._ha.calls == []


@pytest.mark.asyncio
async def test_dangerous_domain_blocked():
    d = _disp({"tiers": {"lock": "green"}})
    r = await _call(d, domain="lock", service="unlock", entity_id="lock.front")
    assert "error" in r and "pericolos" in r["error"].lower()
    assert d._ha.calls == []


@pytest.mark.asyncio
async def test_yellow_requires_confirmation():
    d = _disp({"tiers": {"switch": "yellow"}})
    r = await _call(d, domain="switch", entity_id="switch.boiler")
    assert "error" in r and "conferma" in r["error"].lower()
    assert d._ha.calls == []


@pytest.mark.asyncio
async def test_green_then_per_agent_whitelist_still_applies():
    d = _disp({"tiers": {"light": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on", "data": {"entity_id": "light.kitchen"}},
        allowed_entities=["light.bedroom"],  # kitchen NOT in whitelist
    )
    assert "error" in r and "not permitted" in r["error"]
    assert d._ha.calls == []
