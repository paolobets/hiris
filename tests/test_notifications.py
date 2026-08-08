"""send_notification channels — including Home Assistant persistent notifications.

Persistent (dashboard) notifications were previously unreachable: the agent/gateway
had no tool/channel for persistent_notification, and call_ha_service on it was
blocked by the fail-closed semaforo. These tests cover the new 'ha_persistent'
channel (create + dismiss), title support, and validation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hiris.app.notifiche import send_notification


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
        ha, "ciao", "ha_push", {"ha_notify_service": "notify.mobile_app_test"}, title="Titolo",
    )
    assert ha.calls == [("notify", "mobile_app_test",
                         {"message": "ciao", "title": "Titolo",
                          "data": {"channel": "HIRIS"}})]


@pytest.mark.asyncio
async def test_ha_push_default_service_and_no_title():
    ha = _FakeHA()
    await send_notification(ha, "ciao", "ha_push", {})
    assert ha.calls == [("notify", "notify",
                         {"message": "ciao", "data": {"channel": "HIRIS"}})]


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


# fetta E2 Task 8 ("escono i trentaquattro"): questi tre test vivevano in
# test_tools.py (poi test_weather_tools.py) insieme ai test sui tool morti
# hiris/app/tools/*.py -- spostati qui, non cancellati: `send_notification`
# (hiris/app/notifiche.py) e' viva, i canali telegram/apprise e retropanel
# non hanno copertura altrove in questo file.

@pytest.mark.asyncio
async def test_send_notification_telegram():
    ha = _FakeHA()
    config = {"apprise_urls": ["tgram://test_token/123456"]}
    with patch("hiris.app.notifiche._APPRISE_AVAILABLE", True), \
         patch("hiris.app.notifiche._apprise_lib") as mock_apprise_lib:
        mock_apobj = MagicMock()
        mock_apobj.async_notify = AsyncMock(return_value=True)
        mock_apprise_lib.Apprise.return_value = mock_apobj
        result = await send_notification(ha, "Hello Telegram", "telegram", config)
    assert result is True


@pytest.mark.asyncio
async def test_send_notification_telegram_missing_credentials():
    ha = _FakeHA()
    config = {}  # no token, no chat_id
    result = await send_notification(ha, "Hello", "telegram", config)
    assert result is False


@pytest.mark.asyncio
async def test_send_notification_retropanel():
    ha = _FakeHA()
    config = {"retropanel_url": "http://retropanel:8098"}
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        result = await send_notification(ha, "Hello kiosk", "retropanel", config)

    assert result is True
