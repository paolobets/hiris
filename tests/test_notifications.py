"""send_notification channels — including Home Assistant persistent notifications.

Persistent (dashboard) notifications were previously unreachable: the agent/gateway
had no tool/channel for persistent_notification, and call_ha_service on it was
blocked by the fail-closed semaforo. These tests cover the new 'ha_persistent'
channel (create + dismiss), title support, and validation.
"""
import pytest

from hiris.app.tools.notify_tools import send_notification


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return True


@pytest.mark.asyncio
async def test_ha_persistent_create_with_title_and_id():
    ha = _FakeHA()
    ok = await send_notification(
        ha, "Corpo del messaggio", "ha_persistent", {},
        title="Promemoria", notification_id="hiris_test",
    )
    assert ok is True
    assert ha.calls == [(
        "persistent_notification", "create",
        {"message": "Corpo del messaggio", "title": "Promemoria", "notification_id": "hiris_test"},
    )]


@pytest.mark.asyncio
async def test_ha_persistent_create_minimal():
    ha = _FakeHA()
    await send_notification(ha, "solo messaggio", "ha_persistent", {})
    domain, service, data = ha.calls[0]
    assert (domain, service) == ("persistent_notification", "create")
    assert data == {"message": "solo messaggio"}       # no title/id keys when absent


@pytest.mark.asyncio
async def test_ha_persistent_dismiss():
    ha = _FakeHA()
    ok = await send_notification(
        ha, "", "ha_persistent", {}, notification_id="hiris_test",
    )
    assert ok is True
    assert ha.calls == [("persistent_notification", "dismiss", {"notification_id": "hiris_test"})]


@pytest.mark.asyncio
async def test_ha_persistent_create_requires_message():
    ha = _FakeHA()
    ok = await send_notification(ha, "", "ha_persistent", {})   # no message, no id
    assert ok is False
    assert ha.calls == []                                       # nothing dispatched


@pytest.mark.asyncio
async def test_ha_push_includes_title_and_uses_configured_service():
    ha = _FakeHA()
    await send_notification(
        ha, "ciao", "ha_push", {"ha_notify_service": "notify.iphone_bet"}, title="Titolo",
    )
    assert ha.calls == [("notify", "iphone_bet", {"message": "ciao", "title": "Titolo"})]


@pytest.mark.asyncio
async def test_ha_push_default_service_and_no_title():
    ha = _FakeHA()
    await send_notification(ha, "ciao", "ha_push", {})
    assert ha.calls == [("notify", "notify", {"message": "ciao"})]


@pytest.mark.asyncio
async def test_legacy_channel_aliases():
    ha = _FakeHA()
    await send_notification(ha, "x", "ha", {})          # legacy alias -> ha_push
    assert ha.calls[0][0] == "notify"


@pytest.mark.asyncio
async def test_unknown_channel_returns_false():
    ha = _FakeHA()
    assert await send_notification(ha, "x", "carrier_pigeon", {}) is False
    assert ha.calls == []
