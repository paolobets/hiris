"""Regression test for the CRITICAL Slice-1 review finding: human-approved
gateway actions (execute_pending) must actually EXECUTE, including on
dangerous domains (killer-feature step-up) — the universal gate must be
skipped for tier_confirmed actions, but NOT for unconfirmed ones.
"""
import pytest
from aiohttp import web

from hiris.app.api.handlers_gateway_pending import create_pending, execute_pending
from hiris.app.tools.dispatcher import ToolDispatcher


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {"ok": True}


def _dispatcher(policy):
    return ToolDispatcher(ha_client=_FakeHA(), notify_config={}, execute_policy=policy)


def _app(tmp_path, dispatcher):
    app = web.Application()
    app["data_dir"] = str(tmp_path)
    app["tool_dispatcher"] = dispatcher
    return app


def _entry(tmp_path, *, domain, service, entity_id, tier):
    return create_pending(
        str(tmp_path), tool="call_ha_service",
        inputs={"domain": domain, "service": service, "data": {"entity_id": entity_id}},
        tier=tier, origin="mcp-gateway", label=f"{domain}.{service}",
    )


POLICY = {"tiers": {"light": "yellow", "lock": "red"}}


@pytest.mark.asyncio
async def test_approved_yellow_action_actually_executes(tmp_path):
    """execute_pending on a yellow action must really call ha.call_service,
    not silently be re-gated into a false 'ok:True' no-op."""
    disp = _dispatcher(POLICY)
    app = _app(tmp_path, disp)
    entry = _entry(tmp_path, domain="light", service="turn_on", entity_id="light.kitchen", tier="yellow")
    result = await execute_pending(app, entry)
    assert result == {"ok": True}
    assert disp._ha.calls == [("light", "turn_on", {"entity_id": "light.kitchen"})]


@pytest.mark.asyncio
async def test_approved_dangerous_domain_action_actually_executes(tmp_path):
    """Human out-of-band approval is a step-up that authorises exactly this
    command, denylist included (killer-feature step-up decision)."""
    disp = _dispatcher(POLICY)
    app = _app(tmp_path, disp)
    entry = _entry(tmp_path, domain="lock", service="unlock", entity_id="lock.front", tier="red")
    result = await execute_pending(app, entry)
    assert result == {"ok": True}
    assert disp._ha.calls == [("lock", "unlock", {"entity_id": "lock.front"})]


@pytest.mark.asyncio
async def test_unconfirmed_yellow_action_is_still_gated(tmp_path):
    """Without tier_confirmed, the same yellow action from chat/agent must
    still be blocked pending confirmation."""
    disp = _dispatcher(POLICY)
    r = await disp.dispatch(
        "call_ha_service",
        {"domain": "light", "service": "turn_on", "data": {"entity_id": "light.kitchen"}},
    )
    assert "error" in r and "conferma" in r["error"].lower()
    assert disp._ha.calls == []


@pytest.mark.asyncio
async def test_unconfirmed_dangerous_domain_action_is_still_denylisted(tmp_path):
    """Without tier_confirmed, the denylist stays absolute for autonomous /
    unconfirmed paths."""
    disp = _dispatcher(POLICY)
    r = await disp.dispatch(
        "call_ha_service",
        {"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}},
    )
    assert "error" in r and "pericolos" in r["error"].lower()
    assert disp._ha.calls == []
