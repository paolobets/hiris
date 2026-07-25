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
async def test_area_target_without_entities_blocked_even_if_green():
    # An area/device/label target with no explicit entity_id can't be resolved
    # to a per-entity tier -> fail-closed, even if the domain itself is green.
    d = _disp({"tiers": {"light": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on", "target": {"area_id": "cucina"}},
    )
    assert "error" in r
    assert d._ha.calls == []


@pytest.mark.asyncio
async def test_tier_confirmed_skips_gate_for_yellow():
    d = _disp({"tiers": {"switch": "yellow"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.boiler"}},
        tier_confirmed=True,
    )
    assert r == {"ok": True}
    assert d._ha.calls == [("switch", "turn_on", {"entity_id": "switch.boiler"})]


@pytest.mark.asyncio
async def test_tier_confirmed_skips_gate_for_dangerous_domain():
    d = _disp({"tiers": {"lock": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}},
        tier_confirmed=True,
    )
    assert r == {"ok": True}
    assert d._ha.calls == [("lock", "unlock", {"entity_id": "lock.front"})]


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


# ── review A/#5: target-vs-data split (gated entities must == executed entities) ──


@pytest.mark.asyncio
async def test_target_only_scoped_call_not_broadcast_to_domain():
    # A call scoped via `target` (empty `data`) to a single green entity must be
    # gated for -- and executed against -- exactly that entity. Forwarding empty
    # `data` to HA would make HA treat this as a domain-wide broadcast, actuating
    # every light in the house instead of just light.kitchen.
    d = _disp({"tiers": {"light": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on", "target": {"entity_id": "light.kitchen"}},
    )
    assert r == {"ok": True}
    assert d._ha.calls == [("light", "turn_on", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_target_only_scoped_call_gated_per_entity_not_domain():
    # If the target entity itself is red (needs confirmation) while the domain
    # default is green, the call must be gated on the TARGET entity, not allowed
    # just because `data` (which the old code gated on) was empty.
    d = _disp({"tiers": {"light": "green"}, "entity_tiers": {"light.bedroom": "red"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on", "target": {"entity_id": "light.bedroom"}},
    )
    assert "error" in r and "conferma" in r["error"].lower()
    assert d._ha.calls == []


@pytest.mark.asyncio
async def test_data_and_target_entity_ids_are_unioned_for_gate_and_execution():
    # data and target can both carry an entity_id; both must be gated AND both
    # must reach HA (union), not just whichever one the old "or" picked first.
    d = _disp({"tiers": {"light": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on",
         "data": {"entity_id": "light.kitchen"}, "target": {"entity_id": "light.hall"}},
    )
    assert r == {"ok": True}
    assert d._ha.calls == [("light", "turn_on", {"entity_id": ["light.kitchen", "light.hall"]})]


@pytest.mark.asyncio
async def test_genuine_domain_wide_call_without_entity_still_works():
    # Neither data nor target carries an entity_id (or a group target) -> this is
    # a legitimate domain-wide call gated on the domain tier. Must keep working
    # exactly as before: no entity_id key gets fabricated into `data`.
    d = _disp({"tiers": {"light": "green"}})
    r = await d.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_off", "data": {}},
    )
    assert r == {"ok": True}
    assert d._ha.calls == [("light", "turn_off", {})]
