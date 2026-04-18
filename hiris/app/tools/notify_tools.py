import logging
from typing import Any
import aiohttp
from ..proxy.ha_client import HAClient

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "send_notification",
    "description": "Send a notification to the user via HA mobile push, Telegram, or Retro Panel kiosk toast.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Notification message text"},
            "channel": {
                "type": "string",
                "enum": ["ha_push", "telegram", "retropanel"],
                "description": "Delivery channel",
            },
        },
        "required": ["message", "channel"],
    },
}


async def send_notification(ha: HAClient, message: str, channel: str, config: dict) -> bool:
    """Send a notification via the specified channel."""
    if channel == "ha_push":
        service = config.get("ha_notify_service", "notify.notify")
        domain, svc = service.split(".", 1)
        return await ha.call_service(domain, svc, {"message": message})

    if channel == "telegram":
        token = config.get("telegram_token", "")
        chat_id = config.get("telegram_chat_id", "")
        if not token or not chat_id:
            logger.warning("Telegram not configured")
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": chat_id, "text": message}) as resp:
                return resp.status == 200

    if channel == "retropanel":
        rp_url = config.get("retropanel_url", "http://retropanel:8098")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{rp_url}/api/notify", json={"message": message}) as resp:
                return resp.status in (200, 204)

    logger.warning("Unknown notification channel: %s", channel)
    return False
