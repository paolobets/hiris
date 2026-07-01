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
    "description": (
        "Send a notification to the user. Use THIS tool for ANY notification — do NOT "
        "call_ha_service on persistent_notification/notify. "
        "Channels: 'ha_persistent' = a persistent notification card in the Home Assistant "
        "dashboard (supports title + message; to remove one later, pass its notification_id "
        "together with an empty message to dismiss it); "
        "'ha_push' = mobile push (supports title); "
        "'apprise' = all configured Apprise URLs (Telegram/WhatsApp/ntfy/etc.); "
        "'retropanel' = Retro Panel kiosk toast."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "Notification body text. Leave empty ONLY to dismiss an existing "
                    "persistent notification (together with its notification_id)."
                ),
            },
            "title": {
                "type": "string",
                "description": "Optional title/heading (used by 'ha_persistent' and 'ha_push').",
            },
            "channel": {
                "type": "string",
                "enum": ["ha_persistent", "ha_push", "apprise", "retropanel"],
                "description": "Delivery channel (see tool description).",
            },
            "notification_id": {
                "type": "string",
                "description": (
                    "Optional stable id for a persistent notification, so it can be "
                    "updated (same id overwrites) or dismissed later."
                ),
            },
        },
        "required": ["channel"],
    },
}


async def send_notification(
    ha: HAClient,
    message: str,
    channel: str,
    config: dict,
    *,
    title: str | None = None,
    notification_id: str | None = None,
) -> bool:
    """Send a notification via the specified channel.

    Notifications are informational (they never actuate devices), so this path is
    intentionally NOT gated by the gateway semaforo — it is the sanctioned way for
    the agent/gateway to reach the user, including Home Assistant persistent
    (dashboard) notifications, which are otherwise unreachable via call_ha_service.
    """
    message = message or ""
    # Normalize legacy channel aliases
    if channel == "ha":
        channel = "ha_push"
    if channel == "telegram":
        channel = "apprise"

    if channel == "ha_persistent":
        # Dismiss an existing persistent notification: empty message + id.
        if not message and notification_id:
            return await ha.call_service(
                "persistent_notification", "dismiss", {"notification_id": notification_id}
            )
        if not message:
            logger.warning("ha_persistent: 'message' required to create a persistent notification")
            return False
        data: dict = {"message": message}
        if title:
            data["title"] = title
        if notification_id:
            data["notification_id"] = notification_id
        return await ha.call_service("persistent_notification", "create", data)

    if channel == "ha_push":
        if not message:
            logger.warning("ha_push: 'message' required")
            return False
        service = config.get("ha_notify_service", "notify.notify")
        try:
            domain, svc = service.split(".", 1)
        except ValueError:
            logger.error("Invalid ha_notify_service format: %s (expected 'domain.service')", service)
            return False
        data = {"message": message}
        if title:
            data["title"] = title
        return await ha.call_service(domain, svc, data)

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
        result = await apobj.async_notify(body=message, title=title or "")
        return bool(result)

    if channel == "retropanel":
        rp_url = config.get("retropanel_url", "http://retropanel:8098")
        payload = {"message": message}
        if title:
            payload["title"] = title
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{rp_url}/api/notify", json=payload) as resp:
                return resp.status in (200, 204)

    logger.warning("Unknown notification channel: %s", channel)
    return False
