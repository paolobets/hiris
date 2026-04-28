import logging
import aiohttp
from ..proxy.ha_client import HAClient

try:
    import apprise as _apprise_lib
    _APPRISE_AVAILABLE = True
except ImportError:
    _apprise_lib = None  # type: ignore[assignment]
    _APPRISE_AVAILABLE = False

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "send_notification",
    "description": "Send a notification via HA mobile push, Apprise (Telegram/WhatsApp/ntfy/etc.), or Retro Panel kiosk toast.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Notification message text"},
            "channel": {
                "type": "string",
                "enum": ["ha_push", "apprise", "retropanel"],
                "description": (
                    "Delivery channel. "
                    "'ha_push': HA mobile push. "
                    "'apprise': all configured Apprise URLs (Telegram, WhatsApp, ntfy, etc.). "
                    "'retropanel': Retro Panel kiosk toast."
                ),
            },
        },
        "required": ["message", "channel"],
    },
}


async def send_notification(ha: HAClient, message: str, channel: str, config: dict) -> bool:
    """Send a notification via the specified channel."""
    # Normalize legacy channel aliases
    if channel == "ha":
        channel = "ha_push"
    if channel == "telegram":
        channel = "apprise"

    if channel == "ha_push":
        service = config.get("ha_notify_service", "notify.notify")
        try:
            domain, svc = service.split(".", 1)
        except ValueError:
            logger.error("Invalid ha_notify_service format: %s (expected 'domain.service')", service)
            return False
        return await ha.call_service(domain, svc, {"message": message})

    if channel == "apprise":
        if not _APPRISE_AVAILABLE:
            logger.error("apprise library not installed — run: pip install apprise>=1.9.0")
            return False
        urls: list[str] = config.get("apprise_urls") or []
        if not urls:
            logger.warning("Apprise not configured: apprise_urls is empty")
            return False
        apobj = _apprise_lib.Apprise()
        for url in urls:
            apobj.add(url)
        result = await apobj.async_notify(body=message)
        return bool(result)

    if channel == "retropanel":
        rp_url = config.get("retropanel_url", "http://retropanel:8098")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{rp_url}/api/notify", json={"message": message}) as resp:
                return resp.status in (200, 204)

    logger.warning("Unknown notification channel: %s", channel)
    return False
