"""Review fixes on Task 4 (chat step-up confirmation push):

FIX 1 (MEDIUM): the phone push must name the TARGET ENTITY, not just
domain.service — the tap/OTP executes exactly the frozen `inputs`
(denylist included), so this notification IS the entire human-in-the-loop
safety check. Covers `hiris.app.server._confirmation_push_message`.

FIX 2 (LOW): `handlers_gateway_pending.notify(...)` must report success/
failure honestly (bool) instead of swallowing every failure silently.
"""
import pytest
from aiohttp import web

from hiris.app.server import _confirmation_push_message
from hiris.app.api import handlers_gateway_pending as P
from hiris.app.api.handlers_gateway_policy import notify_service_for_user


# ---------------------------------------------------------------------------
# FIX 1 — entity extraction / message content
# ---------------------------------------------------------------------------

def test_message_contains_entity_from_data_entity_id_string():
    msg = _confirmation_push_message(
        "switch.turn_on",
        {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.boiler"}},
        "123456",
    )
    assert "switch.boiler" in msg
    assert "123456" in msg
    assert "switch.turn_on" in msg


def test_message_contains_entities_from_target_entity_id_list():
    msg = _confirmation_push_message(
        "light.turn_on",
        {"domain": "light", "service": "turn_on",
         "target": {"entity_id": ["light.kitchen", "light.hall"]}},
        "654321",
    )
    assert "light.kitchen" in msg
    assert "light.hall" in msg


def test_message_prefers_data_entity_id_over_target():
    msg = _confirmation_push_message(
        "lock.unlock",
        {"data": {"entity_id": "lock.front"}, "target": {"entity_id": "lock.back"}},
        "000000",
    )
    assert "lock.front" in msg
    assert "lock.back" not in msg


def test_message_falls_back_to_placeholder_when_no_entity():
    msg = _confirmation_push_message(
        "notify.notify", {"domain": "notify", "service": "notify"}, "111111",
    )
    assert "(nessuna entità)" in msg


def test_message_does_not_swallow_prompt_injection_scenario():
    """The exact scenario the reviewer called out: an LLM asked to turn on
    switch.boiler must be visible in the push even if the request looks like
    it's about something else at the `domain.service` label level alone."""
    msg = _confirmation_push_message(
        "switch.turn_on",
        {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.boiler"}},
        "999999",
    )
    assert "switch.boiler" in msg, "human must see the actual target entity, not just the label"


# ---------------------------------------------------------------------------
# FIX 2 — notify() honest bool return
# ---------------------------------------------------------------------------

class _FakeHA:
    def __init__(self, raise_on_call: bool = False):
        self.calls: list[tuple] = []
        self._raise = raise_on_call

    async def call_service(self, domain, service, data):
        if self._raise:
            raise RuntimeError("boom")
        self.calls.append((domain, service, data))


@pytest.mark.asyncio
async def test_notify_returns_true_on_success():
    app = web.Application()
    ha = _FakeHA()
    app["ha_client"] = ha
    ok = await P.notify(app, message="hello", actionable=True, nonce="n1",
                        service="notify.mobile_app_test")
    assert ok is True
    assert len(ha.calls) == 1


@pytest.mark.asyncio
async def test_notify_returns_false_without_ha_client():
    app = web.Application()
    ok = await P.notify(app, message="x", actionable=False, nonce="n2")
    assert ok is False


@pytest.mark.asyncio
async def test_notify_returns_false_on_invalid_service_string():
    app = web.Application()
    app["ha_client"] = _FakeHA()
    ok = await P.notify(app, message="x", actionable=False, nonce="n3",
                        service="no-dot-in-here")
    assert ok is False


@pytest.mark.asyncio
async def test_notify_returns_false_when_call_service_raises():
    app = web.Application()
    app["ha_client"] = _FakeHA(raise_on_call=True)
    ok = await P.notify(app, message="x", actionable=False, nonce="n4",
                        service="notify.mobile_app_test")
    assert ok is False


# ---------------------------------------------------------------------------
# Combined: what actually reaches the fake HA client's call_service, using the
# REAL create_pending / notify / notify_service_for_user / message-builder —
# the closest we get to exercising server.py's _request_confirmation body
# without paying for the full `_on_startup` (Supervisor/MQTT/etc. side effects
# — see test_sentinel_wiring.py's convention for why that's avoided here).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirmation_push_reaches_ha_with_entity_and_otp(tmp_path):
    app = web.Application()
    ha = _FakeHA()
    app["ha_client"] = ha
    data_dir = str(tmp_path)

    inputs = {"domain": "switch", "service": "turn_on", "data": {"entity_id": "switch.boiler"}}
    label = f"{inputs['domain']}.{inputs['service']}"
    user = "paolo"

    P.invalidate_user_otp_pendings(data_dir, user)
    entry = P.create_pending(
        data_dir, tool="call_ha_service", inputs=inputs, tier="yellow",
        origin="chat", label=label, user=user, with_otp=True,
    )
    svc = notify_service_for_user(app, user)
    msg = _confirmation_push_message(label, inputs, entry["otp"])
    otp_sent = await P.notify(app, message=msg, actionable=True, nonce=entry["id"], service=svc)

    assert otp_sent is True
    assert len(ha.calls) == 1
    sent_message = ha.calls[0][2]["message"]
    assert "switch.boiler" in sent_message
    assert entry["otp"] in sent_message


@pytest.mark.asyncio
async def test_confirmation_push_reports_failure_when_ha_client_missing(tmp_path):
    """Fail-safe: no ha_client means the push never went out — otp_sent must
    say so honestly (the pending still exists and simply expires; this test
    only asserts the flag is truthful, not any behaviour change to the pending)."""
    app = web.Application()  # no "ha_client" set
    data_dir = str(tmp_path)
    inputs = {"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.front"}}
    label = f"{inputs['domain']}.{inputs['service']}"
    entry = P.create_pending(
        data_dir, tool="call_ha_service", inputs=inputs, tier="red",
        origin="chat", label=label, user="paolo", with_otp=True,
    )
    msg = _confirmation_push_message(label, inputs, entry["otp"])
    otp_sent = await P.notify(app, message=msg, actionable=True, nonce=entry["id"])
    assert otp_sent is False
